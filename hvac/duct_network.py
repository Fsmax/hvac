# -*- coding: utf-8 -*-
"""Детальный аэродинамический расчёт воздуховодной сети.

Дополнение к hvac/duct_sizing.py: вместо упрощённой схемы
«магистраль → ветка → терминал» строит полное дерево участков
с узлами (тройники, отводы, диффузоры, регуляторы) и считает
ΔP по каждой ветви до подбора магистрального вентилятора.

Алгоритм
--------
1. Сеть задаётся как DAG из DuctEdge (прямые участки) и DuctFitting
   (местные сопротивления). Корень — вентилятор/AHU, листья — диффузоры.
2. Для каждой ветви (путь от корня до листа) суммируется:
       ΔP_branch = Σ ΔP_friction + Σ ΔP_local + ΔP_terminal
3. «Диктующая ветвь» — с максимальным ΔP. Её значение определяет
   требуемое статическое давление вентилятора.
4. Балансировка остальных ветвей — установкой регуляторов с
   ΔP_reg = ΔP_max − ΔP_branch (чтобы давления выровнялись).

Местные сопротивления (ζ) — по АВОК Справочнику 5.5 и ASHRAE Duct
Fitting Database.

Единицы
-------
Расход: м³/ч; длина: м; диаметр: мм; ΔP: Па; скорость: м/с.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from hvac.duct_sizing import (
    AIR_DENSITY_KG_M3, FRICTION_FACTOR_GALV, hydraulic_diameter_mm,
)


# ============================================================================
# Таблица типичных коэффициентов местных сопротивлений ζ
# Источник: АВОК Справочник 5.5 (Internal Pressure Loss), ASHRAE Duct
# Fitting Database, БНТУ «Аэродинамика систем вентиляции» 2018
# ============================================================================

LOCAL_LOSS_COEFFICIENTS: Dict[str, float] = {
    # Отводы (на единственный отвод)
    "elbow_90_round_r1d":    0.35,   # R=D, гладкий, плавный
    "elbow_90_round_r15d":   0.22,   # R=1.5D
    "elbow_90_round_segmented": 0.55,   # сегментный 3 секции
    "elbow_90_rect":         0.30,   # прямоугольный гладкий
    "elbow_90_rect_vanes":   0.10,   # с направляющими лопатками
    "elbow_45_round":        0.18,
    "elbow_45_rect":         0.22,

    # Тройники симметричные, проход:
    "tee_branch":            1.20,   # ответвление под 90° (на сторону ветви)
    "tee_straight":          0.20,   # прямой проход (на сторону прохода)
    "tee_45_branch":         0.65,   # косой 45° на ветвь
    "tee_45_straight":       0.10,

    # Диффузоры и конфузоры (резкие переходы):
    "diffuser_gradual":      0.15,   # плавное расширение
    "diffuser_abrupt":       0.85,   # резкое
    "confuser":              0.07,   # сужение
    "reducer":               0.05,

    # Терминалы:
    "grille_supply":         1.50,   # приточная решётка / диффузор
    "grille_exhaust":        1.80,   # вытяжная (фильтр + решётка)
    "diffuser_ceiling":      2.20,   # потолочный 4-сторонний
    "anemostat":             3.00,
    "kitchen_hood_filter":   2.50,   # зонт с жироуловителем
    "smoke_damper":          3.00,   # клапан дымоудаления (открытый)

    # Регуляторы и заслонки:
    "damper_open":           0.20,
    "damper_30deg":          1.20,
    "damper_45deg":          5.20,
    "iris_damper":           1.50,

    # Воздухозабор / выброс:
    "intake_louver":         2.00,   # наружная решётка с фильтром
    "weather_louver":        1.30,
    "exhaust_cap":           1.20,

    # Фильтры (статика для оценки при чистом фильтре):
    "filter_g4_clean":       0.50,   # ≈ 50 Па, ζ при v=5 м/с очень условный
    "filter_f7_clean":       1.20,
    "filter_h13_clean":      6.50,
    # Точнее — задавайте ΔP напрямую через extra_pressure_pa в Fitting

    # Калорифер / охладитель (медно-алюминиевый):
    "coil_2row":             0.80,
    "coil_4row":             1.80,
    "coil_6row":             3.00,
    "coil_with_eliminator":  4.50,   # с каплеуловителем

    # Шумоглушители:
    "silencer_short":        0.70,
    "silencer_medium":       1.20,
    "silencer_long":         1.80,
}


# ============================================================================
# Модели элементов сети
# ============================================================================

@dataclass
class DuctFitting:
    """Местное сопротивление (фитинг) или элемент с заданным Δp.

    Можно задать одним из способов:
      • kind — ключ из LOCAL_LOSS_COEFFICIENTS (ζ берётся оттуда)
      • zeta — задать ζ напрямую
      • extra_pressure_pa — фиксированный Δp в Па (для фильтра-каталога,
        калорифера-каталога, шумоглушителя по даташиту)

    Расчёт: Δp = ζ · ρv²/2 + extra_pressure_pa
    """
    kind: str = ""                         # тип фитинга
    zeta: Optional[float] = None           # ручное ζ (переопределяет kind)
    extra_pressure_pa: float = 0.0         # фикс. Δp из каталога
    quantity: int = 1                      # количество одинаковых
    note: str = ""

    def coefficient(self) -> float:
        """Эффективное ζ с учётом quantity (без extra_pressure_pa)."""
        z = self.zeta if self.zeta is not None else \
            LOCAL_LOSS_COEFFICIENTS.get(self.kind, 0.0)
        return z * self.quantity

    def pressure_drop_pa(self, velocity_m_s: float,
                          rho: float = AIR_DENSITY_KG_M3) -> float:
        zeta = self.coefficient()
        dynamic = 0.5 * rho * velocity_m_s ** 2
        return zeta * dynamic + self.extra_pressure_pa * self.quantity


@dataclass
class DuctEdge:
    """Прямой участок воздуховода между двумя узлами дерева.

    Параметры
    ---------
    edge_id          : уникальный идентификатор
    parent_id        : id родительского узла («» = корень от вентилятора)
    flow_m3_h        : расход через участок
    length_m         : длина прямого участка, м
    diameter_mm      : диаметр круглого (если shape='round')
    width_mm/height_mm : размеры прямоугольного (если shape='rect')
    shape            : 'round' | 'rect'
    fittings         : список DuctFitting, установленных на этом участке
    terminal_name    : имя помещения/диффузора если это листовая ветвь
    is_terminal      : концевой ли участок
    """
    edge_id: str
    parent_id: str = ""
    flow_m3_h: float = 0.0
    length_m: float = 0.0
    shape: str = "round"                   # round / rect
    diameter_mm: float = 0.0
    width_mm: float = 0.0
    height_mm: float = 0.0
    fittings: List[DuctFitting] = field(default_factory=list)
    terminal_name: str = ""
    is_terminal: bool = False
    note: str = ""

    # Расчётные (заполняются)
    velocity_m_s: float = 0.0
    dp_friction_pa: float = 0.0
    dp_local_pa: float = 0.0
    dp_total_pa: float = 0.0

    # ---------- Геометрия ----------
    def cross_section_m2(self) -> float:
        if self.shape == "round":
            d = self.diameter_mm / 1000.0
            return math.pi * d * d / 4.0
        w = self.width_mm / 1000.0
        h = self.height_mm / 1000.0
        return w * h

    def hydraulic_diameter_mm(self) -> float:
        if self.shape == "round":
            return self.diameter_mm
        return hydraulic_diameter_mm(self.width_mm, self.height_mm)

    # ---------- Расчёт ----------
    def compute(self, rho: float = AIR_DENSITY_KG_M3,
                 friction_factor: float = FRICTION_FACTOR_GALV) -> None:
        a = self.cross_section_m2()
        if a <= 0:
            self.velocity_m_s = 0.0
            self.dp_friction_pa = 0.0
            self.dp_local_pa = 0.0
            self.dp_total_pa = 0.0
            return
        v = (self.flow_m3_h / 3600.0) / a
        self.velocity_m_s = v
        # Трение (Δp = λ · L/d · ρv²/2). Опираемся на формулу из
        # hvac.duct_sizing, но плотность учтена через дин. напор отдельно.
        dh_mm = self.hydraulic_diameter_mm()
        if dh_mm > 0:
            d_m = dh_mm / 1000.0
            self.dp_friction_pa = (friction_factor * self.length_m / d_m
                                     * 0.5 * rho * v * v)
        else:
            self.dp_friction_pa = 0.0
        # Местные
        self.dp_local_pa = sum(
            f.pressure_drop_pa(v, rho=rho) for f in self.fittings)
        self.dp_total_pa = self.dp_friction_pa + self.dp_local_pa


# ============================================================================
# Сеть и расчёт
# ============================================================================

@dataclass
class BranchPath:
    """Описание одной ветви — путь от корня до концевого участка."""
    terminal_edge_id: str
    terminal_name: str
    flow_m3_h: float
    edges: List[str] = field(default_factory=list)   # ids участков по порядку
    dp_total_pa: float = 0.0
    # Требуемое сопротивление регулятора для балансировки (Pmax − Pi)
    balancing_dp_pa: float = 0.0


@dataclass
class DuctNetworkDetailed:
    """Полная аэродинамическая сеть приточной/вытяжной системы."""

    system_name: str = ""
    role: str = "supply"                  # supply / exhaust / smoke
    rho_kg_m3: float = AIR_DENSITY_KG_M3
    friction_factor: float = FRICTION_FACTOR_GALV

    edges: Dict[str, DuctEdge] = field(default_factory=dict)

    # Результаты последнего compute()
    branches: List[BranchPath] = field(default_factory=list)
    critical_branch_id: str = ""
    fan_pressure_required_pa: float = 0.0
    fan_flow_m3_h: float = 0.0
    fan_safety_factor: float = 1.10       # запас на загрязнение/износ

    note: str = ""

    # ---------- Построение ----------
    def add_edge(self, edge: DuctEdge) -> DuctEdge:
        if edge.edge_id in self.edges:
            raise ValueError(f"Участок {edge.edge_id!r} уже существует")
        self.edges[edge.edge_id] = edge
        return edge

    def _children_of(self, parent_id: str) -> List[DuctEdge]:
        return [e for e in self.edges.values() if e.parent_id == parent_id]

    def _root_edges(self) -> List[DuctEdge]:
        return self._children_of("")

    def _terminal_edges(self) -> List[DuctEdge]:
        # Терминал — либо помечен явно, либо не имеет потомков
        terminals: List[DuctEdge] = []
        for e in self.edges.values():
            children = self._children_of(e.edge_id)
            if e.is_terminal or not children:
                terminals.append(e)
        return terminals

    def _path_from_root(self, edge_id: str) -> List[str]:
        """Идёт от листа к корню и возвращает путь [root_id, ..., edge_id]."""
        path: List[str] = []
        cur = edge_id
        guard = 0
        while cur and guard < 10_000:
            path.append(cur)
            e = self.edges.get(cur)
            if e is None or not e.parent_id:
                break
            cur = e.parent_id
            guard += 1
        path.reverse()
        return path

    # ---------- Расчёт ----------
    def compute(self) -> None:
        """Считает velocity / dp каждого участка и формирует BranchPath
        для каждой концевой точки.

        После расчёта:
            fan_pressure_required_pa — нужно вентилятору для диктующей ветви;
            critical_branch_id      — id листа диктующей ветви;
            каждая BranchPath получает balancing_dp_pa.
        """
        for edge in self.edges.values():
            edge.compute(rho=self.rho_kg_m3,
                          friction_factor=self.friction_factor)

        branches: List[BranchPath] = []
        for term in self._terminal_edges():
            path_ids = self._path_from_root(term.edge_id)
            dp = sum(self.edges[eid].dp_total_pa for eid in path_ids)
            branches.append(BranchPath(
                terminal_edge_id=term.edge_id,
                terminal_name=term.terminal_name or term.edge_id,
                flow_m3_h=term.flow_m3_h,
                edges=path_ids,
                dp_total_pa=dp,
            ))

        if branches:
            critical = max(branches, key=lambda b: b.dp_total_pa)
            for b in branches:
                b.balancing_dp_pa = max(critical.dp_total_pa - b.dp_total_pa, 0.0)
            self.critical_branch_id = critical.terminal_edge_id
            self.fan_pressure_required_pa = (
                critical.dp_total_pa * self.fan_safety_factor)
            # Расход вентилятора = сумма по всем терминалам
            self.fan_flow_m3_h = sum(b.flow_m3_h for b in branches)
        else:
            self.critical_branch_id = ""
            self.fan_pressure_required_pa = 0.0
            self.fan_flow_m3_h = 0.0

        self.branches = branches

    # ---------- Сводки ----------
    def summary(self) -> Dict[str, object]:
        return {
            "n_edges": len(self.edges),
            "n_terminals": len(self.branches),
            "fan_flow_m3_h": self.fan_flow_m3_h,
            "fan_pressure_pa": self.fan_pressure_required_pa,
            "critical_branch": self.critical_branch_id,
            "max_velocity_m_s": max(
                (e.velocity_m_s for e in self.edges.values()), default=0.0),
        }


# ============================================================================
# Удобные хелперы для типовых случаев
# ============================================================================

def make_simple_tree(system_name: str,
                      trunk_flow_m3_h: float, trunk_len_m: float,
                      trunk_d_mm: float,
                      terminals: List[Tuple[str, float, float, float]],
                      role: str = "supply") -> DuctNetworkDetailed:
    """Быстрая сборка сети «магистраль + N ответвлений».

    terminals : список (name, flow_m3h, branch_len_m, branch_d_mm)
                — каждое ответвление от магистрали с одной точкой.

    Магистраль получает 1 тройник прохода на каждый отвод, каждое
    ответвление — 1 тройник на ответвление + диффузор на конце.
    """
    net = DuctNetworkDetailed(system_name=system_name, role=role)

    trunk = DuctEdge(
        edge_id="trunk", parent_id="",
        flow_m3_h=trunk_flow_m3_h, length_m=trunk_len_m,
        shape="round", diameter_mm=trunk_d_mm,
        fittings=[
            DuctFitting(kind="tee_straight", quantity=max(len(terminals)-1, 0)),
            DuctFitting(kind="weather_louver"),  # наружная решётка
        ],
    )
    net.add_edge(trunk)

    for i, (name, flow, length, dia) in enumerate(terminals, start=1):
        net.add_edge(DuctEdge(
            edge_id=f"branch_{i}", parent_id="trunk",
            flow_m3_h=flow, length_m=length,
            shape="round", diameter_mm=dia,
            fittings=[
                DuctFitting(kind="tee_branch"),
                DuctFitting(kind="elbow_90_round_r15d"),
                DuctFitting(
                    kind=("grille_exhaust" if role == "exhaust"
                          else "grille_supply"),
                ),
            ],
            terminal_name=name, is_terminal=True,
        ))
    return net
