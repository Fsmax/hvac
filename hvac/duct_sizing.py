# -*- coding: utf-8 -*-
"""Подбор сечений воздуховодов (упрощённая аэродинамика).

Для каждой вентиляционной системы (приточной или вытяжной):

  1. Собирает все обслуживаемые помещения (по sp.system_ventilation).
  2. Считает суммарные расходы Σ Supply и Σ Exhaust.
  3. Строит упрощённую сеть: магистраль (trunk) + ветки на этажи (branches)
     + ответвления на помещения (terminals).
  4. Для каждого участка по расходу подбирает диаметр (круглый) или
     прямоугольное сечение AxB, чтобы скорость не превышала рекомендованную.
  5. Считает падение давления по трению (Альтшуль) + местные сопротивления.

Рекомендованные скорости (СП 60.13330 / АВОК 7.6):

    Участок                 Магистраль        Ветка/ответвление
    ─────────────────────────────────────────────────────────────
    Общественные здания     6.0…8.0 м/с       4.0…5.0 м/с
    Жилые                   4.0…5.0           3.0…4.0
    Промышленные            10…15             6…10
    Хладопровод/кухни       8…10              5…6

Стандартные диаметры круглых воздуховодов (ГОСТ Р 56638-2015 / EN 1506):
    100, 125, 160, 200, 250, 315, 400, 500, 630, 800, 1000, 1250, 1600, 2000

Стандартные размеры прямоугольных (мм):
    100, 125, 160, 200, 250, 300, 400, 500, 600, 800, 1000, 1200, 1500

Падение давления (формула Дарси-Вейсбаха):
    Δp_тр = λ · L/d · ρv²/2

где λ — коэф. трения (для оцинкованной стали ≈ 0.02..0.03),
    L — длина участка, м,  d — гидравлический диаметр, м,
    ρ — плотность воздуха ≈ 1.20 кг/м³, v — скорость, м/с.

Местные сопротивления (отводы, тройники, диффузоры) учитываются как
ΣΔp_мест = ΣΖ · ρv²/2, где Σζ зависит от типа участка.
"""

from __future__ import annotations
import math
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple, TYPE_CHECKING

if TYPE_CHECKING:
    from hvac.project import HVACProject
    from hvac.models import Space


# ============================================================================
# Константы
# ============================================================================

AIR_DENSITY_KG_M3 = 1.20             # ρ воздуха при 20°C
ROUGHNESS_GALV_MM = 0.15             # абсолют. шерох. оцинк. стали, мм
FRICTION_FACTOR_GALV = 0.022         # средний λ для оцинк. в типовом диапазоне

# Стандартные круглые диаметры (ГОСТ Р 56638-2015), мм
STD_ROUND_DIAMETERS_MM = [
    80, 100, 125, 160, 200, 250, 315, 400, 500, 630, 800, 1000, 1250, 1600, 2000
]

# Стандартный ряд прямоугольных размеров (мм), сторона
STD_RECT_SIZES_MM = [
    100, 125, 150, 160, 200, 250, 300, 400, 500, 600, 800, 1000, 1200, 1500, 2000
]

# Рекомендованные скорости по типу здания (м/с), max
RECOMMENDED_VELOCITIES = {
    "public": {"trunk": 7.0, "branch": 5.0, "terminal": 3.5},
    "residential": {"trunk": 4.5, "branch": 3.5, "terminal": 2.5},
    "industrial": {"trunk": 12.0, "branch": 8.0, "terminal": 5.0},
    "kitchen_exhaust": {"trunk": 10.0, "branch": 6.0, "terminal": 4.0},
    "smoke_removal": {"trunk": 15.0, "branch": 12.0, "terminal": 8.0},
}


# ============================================================================
# Структуры данных
# ============================================================================

@dataclass
class DuctSection:
    """Один расчётный участок воздуховода."""
    id: str                              # уникальный идентификатор участка
    section_type: str = "branch"         # trunk / branch / terminal
    role: str = "supply"                 # supply / exhaust / hood / smoke

    # Геометрия
    flow_m3h: float = 0.0                # расход воздуха в этом участке
    length_m: float = 5.0                # длина участка
    shape: str = "round"                 # round / rect

    # Сечение
    diameter_mm: float = 0.0             # круглый, мм
    width_mm: float = 0.0                # прямоуг., мм
    height_mm: float = 0.0               # прямоуг., мм

    # Расчётные
    velocity_m_s: float = 0.0
    hydraulic_diameter_mm: float = 0.0
    cross_section_m2: float = 0.0
    pressure_loss_friction_pa: float = 0.0   # ΔP по трению
    pressure_loss_local_pa: float = 0.0      # местные
    pressure_loss_total_pa: float = 0.0      # сумма

    # Связи
    serves_space_ids: List[str] = field(default_factory=list)
    note: str = ""


@dataclass
class DuctNetwork:
    """Аэродинамическая сеть одной вентиляционной системы или зоны."""
    system_name: str = ""                # "AHU-1 (приток)", "AHU-1/Зона А (приток)"
    role: str = "supply"                 # supply / exhaust
    parent_ahu: str = ""                 # имя VentilationSystem (если это зона)
    zone_name: str = ""                  # имя DuctZone (если зональная сеть)
    total_flow_m3h: float = 0.0          # суммарный расход
    n_terminals: int = 0                 # количество концевых точек
    sections: List[DuctSection] = field(default_factory=list)

    # Сумма падений давления по самой нагруженной ветке (для подбора AHU)
    total_pressure_loss_pa: float = 0.0

    # Зонный вентилятор (если у DuctZone has_zone_fan=True)
    has_zone_fan: bool = False
    zone_fan_flow_m3_h: float = 0.0
    zone_fan_pressure_pa: float = 0.0

    # Параметры подбора
    building_type: str = "public"        # для выбора скоростей
    note: str = ""


# ============================================================================
# Подбор сечения
# ============================================================================

def round_up_to_std_round(diameter_mm: float) -> int:
    """Округляет вверх до стандартного круглого диаметра."""
    for d in STD_ROUND_DIAMETERS_MM:
        if d >= diameter_mm:
            return d
    return STD_ROUND_DIAMETERS_MM[-1]


def round_up_to_std_rect(size_mm: float) -> int:
    """Округляет вверх до стандартного прямоугольного размера."""
    for s in STD_RECT_SIZES_MM:
        if s >= size_mm:
            return s
    return STD_RECT_SIZES_MM[-1]


def diameter_for_flow_and_velocity(flow_m3h: float, v_max_m_s: float) -> float:
    """Расчётный (не округлённый) диаметр круглого воздуховода, мм.

    Q = v · A = v · π·d²/4 → d = √(4·Q / (π·v))
    Q в м³/с, d в м.
    """
    if flow_m3h <= 0 or v_max_m_s <= 0:
        return 0.0
    q_m3s = flow_m3h / 3600.0
    d_m = math.sqrt(4.0 * q_m3s / (math.pi * v_max_m_s))
    return d_m * 1000.0


def pick_round_diameter(flow_m3h: float, v_max_m_s: float) -> Tuple[int, float]:
    """Подбирает стандартный круглый Ø, возвращает (диаметр, фактическая скорость).

    Если требуемое сечение > 2000 мм — возвращает 2000 + предупреждение
    через фактическую скорость (она будет выше нормативной).
    """
    if flow_m3h <= 0:
        return (0, 0.0)
    d_calc = diameter_for_flow_and_velocity(flow_m3h, v_max_m_s)
    d_std = round_up_to_std_round(d_calc)
    # Фактическая скорость на стандартном размере
    area_m2 = math.pi * (d_std / 1000.0) ** 2 / 4.0
    v_actual = (flow_m3h / 3600.0) / area_m2
    return (d_std, v_actual)


def pick_rect_section(flow_m3h: float, v_max_m_s: float,
                      max_aspect_ratio: float = 3.0,
                      preferred_height_mm: Optional[int] = None
                      ) -> Tuple[int, int, float]:
    """Подбирает прямоуг. сечение AxB (мм) для расхода и скорости.

    Если preferred_height_mm задан — выбирает ширину для этой высоты.
    Иначе ищет компактное сечение с aspect ratio ≤ max_aspect_ratio.
    
    Возвращает (width_mm, height_mm, фактическая_скорость).
    """
    if flow_m3h <= 0:
        return (0, 0, 0.0)
    q_m3s = flow_m3h / 3600.0
    area_needed = q_m3s / v_max_m_s  # м²
    area_needed_mm2 = area_needed * 1e6

    if preferred_height_mm:
        # Фиксированная высота
        h = round_up_to_std_rect(preferred_height_mm)
        w_needed = area_needed_mm2 / h
        w = round_up_to_std_rect(w_needed)
        area_actual = w * h / 1e6
        v_actual = q_m3s / area_actual
        return (w, h, v_actual)

    # Компактное сечение: близкое к квадрату
    side = math.sqrt(area_needed_mm2)
    h = round_up_to_std_rect(side)
    w_needed = area_needed_mm2 / h
    w = round_up_to_std_rect(w_needed)

    # Aspect ratio
    if w / h > max_aspect_ratio:
        # Берём следующую высоту
        idx = STD_RECT_SIZES_MM.index(h)
        if idx < len(STD_RECT_SIZES_MM) - 1:
            h = STD_RECT_SIZES_MM[idx + 1]
            w_needed = area_needed_mm2 / h
            w = round_up_to_std_rect(w_needed)

    area_actual = w * h / 1e6
    v_actual = q_m3s / area_actual
    return (w, h, v_actual)


def hydraulic_diameter_mm(width_mm: float, height_mm: float) -> float:
    """Эквивалентный гидравлический диаметр прямоуг. воздуховода, мм.

    d_h = 4A / P = 4·a·b / (2(a+b)) = 2·a·b / (a+b)
    """
    if width_mm <= 0 or height_mm <= 0:
        return 0.0
    return 2.0 * width_mm * height_mm / (width_mm + height_mm)


def pressure_loss_friction_pa(length_m: float, d_h_mm: float, v_m_s: float,
                              friction: float = FRICTION_FACTOR_GALV) -> float:
    """Падение давления по трению (Дарси-Вейсбах), Па.

    Δp = λ · L/d · ρv²/2
    """
    if d_h_mm <= 0 or v_m_s <= 0:
        return 0.0
    d_m = d_h_mm / 1000.0
    return friction * (length_m / d_m) * (AIR_DENSITY_KG_M3 * v_m_s ** 2 / 2.0)


def pressure_loss_local_pa(sum_zeta: float, v_m_s: float) -> float:
    """Падение на местных сопротивлениях, Па.

    Δp = Σζ · ρv²/2
    
    Типовые Σζ:
      • терминал (анемостат + гибкий рукав): 2.5
      • ветка (1 отвод + 1 тройник):           1.0
      • магистраль (фитинги + изменения):       0.8 на 10 м
    """
    if v_m_s <= 0:
        return 0.0
    return sum_zeta * AIR_DENSITY_KG_M3 * v_m_s ** 2 / 2.0


# ============================================================================
# Построение сети
# ============================================================================

def _typical_velocities(building_type: str, role: str) -> Dict[str, float]:
    """Возвращает рекомендованные скорости для типа здания/роли."""
    if role == "smoke":
        return RECOMMENDED_VELOCITIES["smoke_removal"]
    if role == "hood":
        return RECOMMENDED_VELOCITIES["kitchen_exhaust"]
    return RECOMMENDED_VELOCITIES.get(building_type, RECOMMENDED_VELOCITIES["public"])


def build_network_for_system(system_name: str, spaces: List["Space"],
                             role: str = "supply",
                             shape: str = "round",
                             building_type: str = "public",
                             terminal_length_m: float = 4.0,
                             branch_length_m: float = 8.0,
                             trunk_length_m: float = 25.0
                             ) -> DuctNetwork:
    """Строит сеть воздуховодов для одной системы.

    Упрощённая 3-уровневая иерархия:
      terminal — на каждое помещение
      branch   — на этаж/группу (сумма помещений уровня)
      trunk    — магистраль (сумма всех веток)

    role: 'supply' / 'exhaust' / 'hood' / 'smoke'
    shape: 'round' / 'rect'
    """
    net = DuctNetwork(system_name=system_name, role=role,
                      building_type=building_type)

    # Фильтр расхода в зависимости от роли
    if role == "supply":
        flows = [(sp, sp.supply_m3h) for sp in spaces if sp.supply_m3h > 0]
    elif role == "exhaust":
        flows = [(sp, sp.exhaust_m3h) for sp in spaces if sp.exhaust_m3h > 0]
    elif role == "hood":
        flows = [(sp, sp.hood_m3h) for sp in spaces if sp.hood_m3h > 0]
    else:
        return net

    if not flows:
        return net

    total = sum(f for _, f in flows)
    net.total_flow_m3h = total
    net.n_terminals = len(flows)
    velocities = _typical_velocities(building_type, role)

    # ===== Терминалы =====
    for sp, flow in flows:
        sec = DuctSection(
            id=f"{system_name}/T-{sp.number}",
            section_type="terminal",
            role=role,
            flow_m3h=flow,
            length_m=terminal_length_m,
            shape=shape,
            serves_space_ids=[sp.space_id],
            note=f"к помещению {sp.number} {sp.name}",
        )
        _size_section(sec, velocities["terminal"], shape)
        sec.pressure_loss_friction_pa = pressure_loss_friction_pa(
            sec.length_m, sec.hydraulic_diameter_mm, sec.velocity_m_s,
        )
        sec.pressure_loss_local_pa = pressure_loss_local_pa(
            sum_zeta=2.5, v_m_s=sec.velocity_m_s,  # анемостат + гибкий рукав
        )
        sec.pressure_loss_total_pa = (sec.pressure_loss_friction_pa
                                      + sec.pressure_loss_local_pa)
        net.sections.append(sec)

    # ===== Ветки (по уровням) =====
    from collections import defaultdict
    by_level: Dict[str, List[Tuple["Space", float]]] = defaultdict(list)
    for sp, flow in flows:
        by_level[sp.level].append((sp, flow))

    worst_branch_pa = 0.0
    for level, items in by_level.items():
        branch_flow = sum(f for _, f in items)
        sec = DuctSection(
            id=f"{system_name}/B-{level}",
            section_type="branch",
            role=role,
            flow_m3h=branch_flow,
            length_m=branch_length_m,
            shape=shape,
            serves_space_ids=[sp.space_id for sp, _ in items],
            note=f"ветка уровня {level} ({len(items)} помещений)",
        )
        _size_section(sec, velocities["branch"], shape)
        sec.pressure_loss_friction_pa = pressure_loss_friction_pa(
            sec.length_m, sec.hydraulic_diameter_mm, sec.velocity_m_s,
        )
        sec.pressure_loss_local_pa = pressure_loss_local_pa(
            sum_zeta=1.5, v_m_s=sec.velocity_m_s,
        )
        sec.pressure_loss_total_pa = (sec.pressure_loss_friction_pa
                                      + sec.pressure_loss_local_pa)
        net.sections.append(sec)
        worst_branch_pa = max(worst_branch_pa, sec.pressure_loss_total_pa)

    # ===== Магистраль =====
    trunk_sec = DuctSection(
        id=f"{system_name}/TRUNK",
        section_type="trunk",
        role=role,
        flow_m3h=total,
        length_m=trunk_length_m,
        shape=shape,
        note="магистраль AHU → этажи",
    )
    _size_section(trunk_sec, velocities["trunk"], shape)
    trunk_sec.pressure_loss_friction_pa = pressure_loss_friction_pa(
        trunk_sec.length_m, trunk_sec.hydraulic_diameter_mm,
        trunk_sec.velocity_m_s,
    )
    trunk_sec.pressure_loss_local_pa = pressure_loss_local_pa(
        sum_zeta=2.0, v_m_s=trunk_sec.velocity_m_s,  # фильтр, рекуп., фитинги
    )
    trunk_sec.pressure_loss_total_pa = (trunk_sec.pressure_loss_friction_pa
                                        + trunk_sec.pressure_loss_local_pa)
    net.sections.append(trunk_sec)

    # Суммарное давление по худшей ветке (для подбора вентилятора)
    # Худший терминал + худшая ветка + магистраль + запас на установки (300 Па)
    worst_terminal_pa = max((s.pressure_loss_total_pa for s in net.sections
                             if s.section_type == "terminal"), default=0.0)
    net.total_pressure_loss_pa = (worst_terminal_pa + worst_branch_pa
                                  + trunk_sec.pressure_loss_total_pa
                                  + 300.0)  # запас на фильтр/калорифер/рекуп.

    return net


def _size_section(sec: DuctSection, v_max: float, shape: str) -> None:
    """Заполняет diameter/width/height/velocity/cross_section/d_h."""
    if shape == "round":
        d, v = pick_round_diameter(sec.flow_m3h, v_max)
        sec.diameter_mm = d
        sec.velocity_m_s = v
        sec.hydraulic_diameter_mm = d
        sec.cross_section_m2 = math.pi * (d / 1000.0) ** 2 / 4.0
    else:  # rect
        w, h, v = pick_rect_section(sec.flow_m3h, v_max)
        sec.width_mm = w
        sec.height_mm = h
        sec.velocity_m_s = v
        sec.hydraulic_diameter_mm = hydraulic_diameter_mm(w, h)
        sec.cross_section_m2 = (w * h) / 1e6


# ============================================================================
# Расчёт для проекта
# ============================================================================

def _build_role_networks(name_prefix: str, spaces: List["Space"],
                         parent_ahu: str, zone_name: str,
                         shape: str, building_type: str,
                         zone_obj=None) -> Dict[str, DuctNetwork]:
    """Создаёт supply/exhaust/hood сети для одной группы помещений (зоны).

    Если zone_obj задан и has_zone_fan=True — отмечает сеть как имеющую
    зональный вентилятор и заполняет zone_fan_pressure_pa из настроек зоны.
    """
    out: Dict[str, DuctNetwork] = {}
    roles = [
        ("supply",  " (приток)",  lambda sp: sp.supply_m3h),
        ("exhaust", " (вытяжка)", lambda sp: sp.exhaust_m3h),
        ("hood",    " (зонт)",    lambda sp: sp.hood_m3h),
    ]
    for role, suffix, getter in roles:
        if not any(getter(sp) > 0 for sp in spaces):
            continue
        net_name = name_prefix + suffix
        net = build_network_for_system(
            net_name, spaces, role=role, shape=shape,
            building_type=building_type,
        )
        net.parent_ahu = parent_ahu
        net.zone_name = zone_name
        if zone_obj is not None and getattr(zone_obj, "has_zone_fan", False):
            net.has_zone_fan = True
            net.zone_fan_flow_m3_h = net.total_flow_m3h
            # Сумма Δp по сети + требуемое давление зоны
            net.zone_fan_pressure_pa = (net.total_pressure_loss_pa
                                        + getattr(zone_obj,
                                                  "static_pressure_pa", 0.0))
        out[net.system_name] = net
    return out


def size_project_ducts(project: "HVACProject",
                       shape: str = "round",
                       building_type: str = "public"
                       ) -> Dict[str, DuctNetwork]:
    """Рассчитывает сети воздуховодов для всех вент. систем проекта.

    Двухуровневая группировка:
    1. По AHU (sp.system_ventilation). Помещения без duct_zone образуют
       единую сеть AHU (старое поведение).
    2. Если у AHU есть DuctZone — помещения с duct_zone=<имя> образуют
       отдельную зональную подсеть с суффиксом "/<зона>" в имени.
       Если в зоне DuctZone.has_zone_fan=True — отмечается зональный
       вентилятор.

    Возвращает {network_name: DuctNetwork}. Имена:
      - "AHU-1 (приток)"            — главная сеть AHU
      - "AHU-1/Зона А (приток)"     — зональная подсеть
    """
    from collections import defaultdict
    by_system: Dict[str, List["Space"]] = defaultdict(list)
    for sp in project.spaces:
        if sp.system_ventilation:
            by_system[sp.system_ventilation].append(sp)

    # Зоны воздуховодов, сгруппированные по родительскому AHU
    zones_by_ahu: Dict[str, Dict[str, object]] = defaultdict(dict)
    for zname, zone in getattr(project, "duct_zones", {}).items():
        zones_by_ahu[zone.parent_ahu][zname] = zone

    result: Dict[str, DuctNetwork] = {}
    for sys_name, spaces in by_system.items():
        zones_here = zones_by_ahu.get(sys_name, {})

        if not zones_here:
            # Старое поведение: одна сеть на всю систему
            nets = _build_role_networks(
                sys_name, spaces, parent_ahu=sys_name, zone_name="",
                shape=shape, building_type=building_type,
            )
            result.update(nets)
            continue

        # Разбиваем помещения по зонам
        by_zone: Dict[str, List["Space"]] = defaultdict(list)
        unzoned: List["Space"] = []
        for sp in spaces:
            zn = getattr(sp, "duct_zone", "") or ""
            if zn and zn in zones_here:
                by_zone[zn].append(sp)
            else:
                unzoned.append(sp)

        # Зональные подсети
        for zname, zone_spaces in by_zone.items():
            zone_obj = zones_here[zname]
            nets = _build_role_networks(
                f"{sys_name}/{zname}", zone_spaces,
                parent_ahu=sys_name, zone_name=zname,
                shape=shape, building_type=building_type,
                zone_obj=zone_obj,
            )
            result.update(nets)

        # Помещения без зоны — главная сеть AHU (магистральная часть)
        if unzoned:
            nets = _build_role_networks(
                sys_name, unzoned, parent_ahu=sys_name, zone_name="",
                shape=shape, building_type=building_type,
            )
            result.update(nets)

    return result


def network_summary(net: DuctNetwork) -> Dict:
    """Краткая сводка по сети."""
    trunks = [s for s in net.sections if s.section_type == "trunk"]
    return {
        "system_name": net.system_name,
        "role": net.role,
        "total_flow_m3h": net.total_flow_m3h,
        "n_terminals": net.n_terminals,
        "n_sections": len(net.sections),
        "trunk_size_mm": (trunks[0].diameter_mm if trunks
                          else 0) if net.sections and trunks[0].shape == "round"
                         else (f"{trunks[0].width_mm}x{trunks[0].height_mm}"
                               if trunks else 0),
        "max_velocity_m_s": max((s.velocity_m_s for s in net.sections),
                                default=0.0),
        "total_pressure_loss_pa": net.total_pressure_loss_pa,
    }
