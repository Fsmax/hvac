# -*- coding: utf-8 -*-
"""Каталог воздухораспределительных решёток и подбор по расходу/шуму.

Данные — каталог ARKTIKA/Арктос (изд. 8.02), раздел «Воздухораспредели-
тельные устройства». Для каждого типоразмера приводится живое сечение
F0 и набор рабочих точек: при разных уровнях звуковой мощности
LwA = 25/35/45 дБ(А) — расход L0 (м³/ч), полная потеря давления ΔPполн
(Па) и дальнобойность струи (м) при разных конечных скоростях Vx. Часть
семейств (переточные АП) заданы по скорости в живом сечении, напольные
РНБ/РНР — только живым сечением (аэродинамика по номограмме).

Подбор (основной критерий — шум): для требуемого расхода L подбирается
наименьший типоразмер, у которого расход при допустимом уровне шума
LwA_доп не ниже требуемого. Дополнительно ограничивается скорость в
живом сечении и ΔPполн. В рабочей точке выдаются фактические LwA, ΔP,
скорость и дальнобойность. Это каталожный предподбор; финальный — по
программе изготовителя.

Данные вынесены в hvac/catalogs/data/grilles.json; пользовательские
дополнения — JSON-файлы типа "grilles" в ~/.hvac_calc/catalogs/
(формат см. hvac/catalogs/user_catalogs.py).
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from importlib.resources import files
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Union

from hvac.catalogs.user_catalogs import iter_user_catalogs

RHO_AIR = 1.2  # плотность воздуха, кг/м³

# Рекомендуемые предельные скорости в живом сечении, м/с (ориентир СП 60,
# каталоги изготовителей): приток в обслуживаемую зону — умереннее.
DEFAULT_MAX_LWA = 35.0          # дБ(А) — типичный предел для жилых/офисных
TRANSFER_MAX_V = 1.0            # переточные решётки — по скорости
FLOOR_MAX_V = 2.0              # напольные — по скорости


# ============================================================================
# Модель каталога
# ============================================================================

@dataclass
class GrillePoint:
    """Каталожная рабочая точка типоразмера."""
    l0: float                       # расход, м³/ч
    lwa: Optional[float] = None     # уровень звуковой мощности, дБ(А)
    dp: Optional[float] = None      # ΔPполн, Па
    v: Optional[float] = None       # скорость в живом сечении, м/с (переточные)
    throw: Dict[str, float] = field(default_factory=dict)  # {Vx: дальнобойность}


@dataclass
class GrilleModel:
    """Один типоразмер решётки (семейство + размер)."""
    family_code: str
    family_name: str
    variants: List[str]
    mount: str                      # wall/plenum/round_duct/slot/transfer/floor
    kind: str                       # universal/supply/exhaust/transfer
    layout: str                     # noise/slot/transfer/floor
    f0_m2: float                    # живое сечение, м²
    a_mm: Optional[int] = None
    b_mm: Optional[int] = None
    f_free_m2: Optional[float] = None   # для переточных (Fж.с.)
    slots: Optional[int] = None         # для щелевых — число щелей
    length_m: Optional[float] = None    # для щелевых — длина (база каталога)
    points: List[GrillePoint] = field(default_factory=list)
    regulator: Optional[dict] = None    # {open_pct,K,dLwA} для -Р вариантов
    page: int = 0

    # ---- геометрия ----
    @property
    def effective_area_m2(self) -> float:
        """Площадь для расчёта скорости (живое сечение)."""
        return self.f_free_m2 or self.f0_m2

    @property
    def face_area_m2(self) -> float:
        """Габаритная площадь лицевой части (для ранжирования размера)."""
        if self.a_mm and self.b_mm:
            return self.a_mm * self.b_mm / 1e6
        return self.f0_m2

    def size_label(self) -> str:
        if self.slots:
            return f"{self.slots}×{self.length_m or 1:g} м"
        if self.a_mm and self.b_mm:
            return f"{self.a_mm}×{self.b_mm}"
        if self.a_mm:
            return f"Ø{self.a_mm}"
        return ""

    def label(self) -> str:
        """«АМН/АМР/АДН/АДР 200×100»."""
        v = "/".join(self.variants)
        return f"{v} {self.size_label()}".strip()

    def velocity(self, l0_m3h: float) -> float:
        """Скорость в живом сечении при расходе L0, м/с."""
        a = self.effective_area_m2
        return l0_m3h / (3600.0 * a) if a > 0 else 0.0

    # ---- аэродинамика/акустика (интерполяция каталожных точек) ----
    def _noise_anchors(self) -> List[Tuple[float, float]]:
        """[(LwA, max L0)] по возрастанию LwA; дубли LwA схлопнуты к max L0."""
        by_lwa: Dict[float, float] = {}
        for p in self.points:
            if p.lwa is None:
                continue
            by_lwa[p.lwa] = max(by_lwa.get(p.lwa, 0.0), p.l0)
        return sorted(by_lwa.items())

    def _dp_anchors(self) -> List[Tuple[float, float]]:
        """[(L0, ΔP)] по возрастанию L0 (только точки с заданным ΔP)."""
        pts = [(p.l0, p.dp) for p in self.points if p.dp is not None]
        return sorted(pts)

    def max_l0_for_noise(self, lwa_target: float) -> Optional[float]:
        """Макс. расход L0 при уровне шума ≤ lwa_target (интерполяция).

        None — у типоразмера нет данных по шуму (переточные/напольные).
        За пределами таблицы значение усекается к краю (консервативно).
        """
        a = self._noise_anchors()
        if not a:
            return None
        if lwa_target <= a[0][0]:
            return a[0][1]
        if lwa_target >= a[-1][0]:
            return a[-1][1]
        for (l1, q1), (l2, q2) in zip(a, a[1:]):
            if l1 <= lwa_target <= l2:
                f = (lwa_target - l1) / (l2 - l1) if l2 > l1 else 0.0
                return q1 + f * (q2 - q1)
        return a[-1][1]

    def lwa_at(self, l0_m3h: float) -> Optional[float]:
        """Уровень шума LwA при расходе L0 (интерполяция), дБ(А)."""
        a = self._noise_anchors()
        if not a:
            return None
        pts = sorted((q, lw) for lw, q in a)        # по возрастанию L0
        if l0_m3h <= pts[0][0]:
            return pts[0][1]
        if l0_m3h >= pts[-1][0]:
            return pts[-1][1]
        for (q1, lw1), (q2, lw2) in zip(pts, pts[1:]):
            if q1 <= l0_m3h <= q2:
                f = (l0_m3h - q1) / (q2 - q1) if q2 > q1 else 0.0
                return lw1 + f * (lw2 - lw1)
        return pts[-1][1]

    def dp_at(self, l0_m3h: float) -> Optional[float]:
        """ΔPполн при расходе L0, Па. Вне диапазона — квадратично (ΔP∝L0²)."""
        a = self._dp_anchors()
        if not a:
            return None
        if l0_m3h <= a[0][0]:
            q0, dp0 = a[0]
            return dp0 * (l0_m3h / q0) ** 2 if q0 > 0 else dp0
        if l0_m3h >= a[-1][0]:
            q1, dp1 = a[-1]
            return dp1 * (l0_m3h / q1) ** 2 if q1 > 0 else dp1
        for (q1, d1), (q2, d2) in zip(a, a[1:]):
            if q1 <= l0_m3h <= q2:
                f = (l0_m3h - q1) / (q2 - q1) if q2 > q1 else 0.0
                return d1 + f * (d2 - d1)
        return a[-1][1]

    def throw_at(self, l0_m3h: float, vx: str = "0.5") -> Optional[float]:
        """Дальнобойность струи (м) при расходе L0 и конечной скорости Vx.

        Берётся ближайшая по L0 каталожная точка, где задана дальнобойность
        для данного Vx.
        """
        cand = [(abs(p.l0 - l0_m3h), p.throw.get(vx))
                for p in self.points if p.throw.get(vx) is not None]
        if not cand:
            return None
        cand.sort(key=lambda c: c[0])
        return cand[0][1]

    def allowable_l0(self, *, max_lwa: Optional[float] = None,
                     max_velocity: Optional[float] = None,
                     max_dp: Optional[float] = None) -> Optional[float]:
        """Допустимый расход одной решётки по активным ограничениям, м³/ч."""
        limits: List[float] = []
        if max_lwa is not None:
            q = self.max_l0_for_noise(max_lwa)
            if q is not None:
                limits.append(q)
        if max_velocity is not None:
            limits.append(max_velocity * self.effective_area_m2 * 3600.0)
        if max_dp is not None:
            q = self._l0_for_dp(max_dp)
            if q is not None:
                limits.append(q)
        return min(limits) if limits else None

    def _l0_for_dp(self, dp_target: float) -> Optional[float]:
        """Расход, при котором ΔPполн = dp_target (обратная dp_at)."""
        a = self._dp_anchors()
        if not a:
            return None
        # ΔP монотонно растёт по L0 — ищем обратное, на хвостах квадратично
        if dp_target <= a[0][1]:
            q0, dp0 = a[0]
            return q0 * math.sqrt(dp_target / dp0) if dp0 > 0 else q0
        if dp_target >= a[-1][1]:
            q1, dp1 = a[-1]
            return q1 * math.sqrt(dp_target / dp1) if dp1 > 0 else q1
        for (q1, d1), (q2, d2) in zip(a, a[1:]):
            if d1 <= dp_target <= d2:
                f = (dp_target - d1) / (d2 - d1) if d2 > d1 else 0.0
                return q1 + f * (q2 - q1)
        return a[-1][0]


# ============================================================================
# Загрузка каталога
# ============================================================================

def _models_from_catalog_dict(data: dict) -> List[GrilleModel]:
    """Разворачивает JSON {families:[{...,sizes:[...]}]} в плоский список."""
    models: List[GrilleModel] = []
    for fam in data.get("families", []):
        meta = dict(
            family_code=fam.get("code", ""),
            family_name=fam.get("name", ""),
            variants=list(fam.get("variants", [])),
            mount=fam.get("mount", "wall"),
            kind=fam.get("kind", "universal"),
            layout=fam.get("layout", "noise"),
            regulator=fam.get("regulator"),
            page=fam.get("page", 0),
        )
        for s in fam.get("sizes", []):
            pts = [GrillePoint(
                l0=p["l0"], lwa=p.get("lwa"), dp=p.get("dp"),
                v=p.get("v"),
                throw={k: float(v) for k, v in (p.get("throw") or {}).items()},
            ) for p in s.get("points", [])]
            models.append(GrilleModel(
                f0_m2=s["f0"], a_mm=s.get("a"), b_mm=s.get("b"),
                f_free_m2=s.get("f_free"), slots=s.get("slots"),
                length_m=s.get("length_m"), points=pts, **meta,
            ))
    return models


def _load_builtin() -> List[GrilleModel]:
    """Читает встроенный каталог из hvac/catalogs/data/grilles.json."""
    raw = (files("hvac.catalogs") / "data" / "grilles.json").read_text("utf-8")
    return _models_from_catalog_dict(json.loads(raw))


def load_grille_catalog(
        user_dir: Optional[Union[str, Path]] = None) -> List[GrilleModel]:
    """Встроенный каталог + пользовательские каталоги типа "grilles"."""
    models = _load_builtin()
    for data in iter_user_catalogs("grilles", user_dir):
        models.extend(_models_from_catalog_dict(data))
    return models


GRILLE_CATALOG: List[GrilleModel] = load_grille_catalog()


def grille_families() -> List[Tuple[str, str]]:
    """[(code, name)] уникальных семейств каталога (для UI-фильтра)."""
    seen: Dict[str, str] = {}
    for m in GRILLE_CATALOG:
        seen.setdefault(m.family_code, m.family_name)
    return list(seen.items())


def grille_mounts() -> List[str]:
    """Уникальные типы монтажа (wall/plenum/round_duct/slot/transfer/floor)."""
    out: List[str] = []
    for m in GRILLE_CATALOG:
        if m.mount not in out:
            out.append(m.mount)
    return out


# ============================================================================
# Подбор
# ============================================================================

@dataclass
class GrillePick:
    """Результат подбора решётки под расход."""
    model: GrilleModel
    n_units: int                    # число решёток
    l0_per_unit: float              # расход на одну решётку, м³/ч
    l0_total: float                 # суммарный требуемый расход
    velocity: float                 # скорость в живом сечении, м/с
    lwa: Optional[float]            # фактический уровень шума, дБ(А)
    dp: Optional[float]             # ΔPполн в рабочей точке, Па
    throw_05: Optional[float]       # дальнобойность при Vx=0.5 м/с
    warnings: List[str] = field(default_factory=list)


def _passes_filters(m: GrilleModel, mount, families, kinds) -> bool:
    if mount and m.mount != mount:
        return False
    if families and m.family_code not in families:
        return False
    if kinds and m.kind not in kinds:
        return False
    return True


def select_grilles(
    l0_required_m3h: float,
    *,
    max_lwa: Optional[float] = DEFAULT_MAX_LWA,
    max_velocity: Optional[float] = None,
    max_dp: Optional[float] = None,
    max_a_mm: Optional[int] = None,
    max_b_mm: Optional[int] = None,
    mount: Optional[str] = None,
    families: Optional[List[str]] = None,
    kinds: Optional[List[str]] = None,
    catalog: Optional[List[GrilleModel]] = None,
    n_best: int = 5,
    allow_multiple: bool = True,
    max_units: int = 8,
) -> List[GrillePick]:
    """Варианты решёток под требуемый расход L0.

    Главный критерий — шум: для каждого типоразмера берётся допустимый
    расход по ограничениям (LwA ≤ max_lwa, скорость ≤ max_velocity,
    ΔP ≤ max_dp) и проверяется, покрывает ли он требуемый. Если одной
    решётки мало и allow_multiple — берётся несколько одинаковых.

    Габарит лицевой части можно ограничить max_a_mm / max_b_mm (ширина A
    и высота B по каталогу) — например, чтобы решётка вписалась в проём
    или короб; ограничение B при свободной A фактически фиксирует высоту
    и подбирает ширину. На типоразмеры без заданной стороны (щелевые,
    круглые) соответствующее ограничение не влияет.

    Возвращает до n_best вариантов: предпочтительны решения одной
    решёткой и наименьший габарит. Пусто — ничего не подошло.
    """
    if l0_required_m3h <= 0:
        raise ValueError("Расход должен быть положительным")

    cat = catalog if catalog is not None else GRILLE_CATALOG
    # для семейств без данных по шуму — критерий по скорости
    eff_max_v = max_velocity

    picks: List[GrillePick] = []
    for m in cat:
        if not _passes_filters(m, mount, families, kinds):
            continue
        if max_a_mm and m.a_mm and m.a_mm > max_a_mm:
            continue
        if max_b_mm and m.b_mm and m.b_mm > max_b_mm:
            continue
        mv = eff_max_v
        ml = max_lwa
        if not m._noise_anchors():           # нет данных по шуму
            ml = None
            if mv is None:
                mv = TRANSFER_MAX_V if m.mount == "transfer" else FLOOR_MAX_V
        allow = m.allowable_l0(max_lwa=ml, max_velocity=mv, max_dp=max_dp)
        if not allow or allow <= 0:
            continue

        if allow >= l0_required_m3h:
            n = 1
        elif allow_multiple:
            n = math.ceil(l0_required_m3h / allow)
            if n > max_units:
                continue
        else:
            continue

        per = l0_required_m3h / n
        v = m.velocity(per)
        pick = GrillePick(
            model=m, n_units=n, l0_per_unit=per, l0_total=l0_required_m3h,
            velocity=v, lwa=m.lwa_at(per), dp=m.dp_at(per),
            throw_05=m.throw_at(per, "0.5"),
        )
        if v < 0.5:
            pick.warnings.append(
                f"Низкая скорость {v:.1f} м/с — решётка завышена, слабая струя")
        if m.layout == "floor" and m.dp_at(per) is None:
            pick.warnings.append("ΔP по номограмме изготовителя (нет в таблице)")
        picks.append(pick)

    # ранжирование: меньше решёток, плотнее по расходу (меньше габарит)
    picks.sort(key=lambda p: (p.n_units, p.model.face_area_m2 * p.n_units))
    # уникализируем по семейству+размеру, сохраняя лучшие
    seen = set()
    uniq: List[GrillePick] = []
    for p in picks:
        key = (p.model.family_code, p.model.size_label())
        if key in seen:
            continue
        seen.add(key)
        uniq.append(p)
    return uniq[:max(n_best, 1)]


def select_grille(l0_required_m3h: float, **kwargs) -> Optional[GrillePick]:
    """Лучший вариант решётки под расход или None."""
    picks = select_grilles(l0_required_m3h, n_best=1, **kwargs)
    return picks[0] if picks else None


@dataclass
class GrilleRoomPick:
    """Подбор приточной и вытяжной решётки для одного помещения."""
    supply: Optional[GrillePick] = None      # под supply_m3h
    exhaust: Optional[GrillePick] = None      # под exhaust_m3h


def select_grilles_for_room(
    supply_m3h: float,
    exhaust_m3h: float,
    **kwargs,
) -> GrilleRoomPick:
    """Подбор решёток помещения: приток и вытяжка по своим расходам.

    kwargs передаются в select_grille (max_lwa, mount, families, …).
    """
    sup = select_grille(supply_m3h, **kwargs) if supply_m3h > 0 else None
    exh = select_grille(exhaust_m3h, **kwargs) if exhaust_m3h > 0 else None
    return GrilleRoomPick(supply=sup, exhaust=exh)
