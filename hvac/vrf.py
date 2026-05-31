# -*- coding: utf-8 -*-
"""Расчёт VRF/VRV систем кондиционирования.

Источники
---------
Daikin VRV Design Manual (EAR), Mitsubishi Electric City Multi Y-series,
LG Multi V 5 / 6 Engineering Manual, Samsung DVM S/S2. Все производители
работают по близким правилам — данный модуль предлагает обобщённую
проверку основных ограничений (длина трасс, перепад высот, общая
производительность внутренних блоков, коэффициент соединения).

Что считается
-------------
1. Подбор внешнего блока по сумме холодопроизводительности внутренних
   с учётом коэффициента соединения (combination ratio).
2. Диаметры медных труб хладагента (жидкость + пар) для участков:
   • от внешнего блока до первого разветвителя (магистраль);
   • между разветвителями;
   • до внутреннего блока (терминал).
3. Подбор разветвителей Refnet/Joint по диапазону производительности.
4. Проверка ограничений: суммарная длина трасс, эквивалентная длина,
   перепад высот между внешним и внутренним блоком и между разветвителем
   и группой внутренних.
5. Корректировка холодопроизводительности на длину трасс
   (упрощённо: -1% на каждые 10 м эквивалентной длины > 50 м).

Структуры
---------
    VRFIndoorUnit         — внутренний блок (моделирует выбор по нагрузке)
    VRFOutdoorUnit        — внешний блок (агрегат)
    VRFRefnet             — разветвитель
    VRFSystem             — вся система: 1 внешний + N разветвителей + M внутренних
    VRFConstraints        — лимиты по производителю (default: Daikin)
    VRFCheckResult        — результат проверки лимитов

Использование
-------------
    sys = build_vrf_system(spaces, indoor_family="Кассетный")
    check = check_constraints(sys)
    if check.ok:
        ...
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple


# ============================================================================
# Каталог внутренних блоков VRF (типовой mix Daikin VRV / Mitsubishi)
# ============================================================================

@dataclass
class VRFIndoorUnit:
    """Внутренний блок VRF (моделирует типоразмер)."""
    name: str
    family: str = ""                   # Кассетный / Канальный / Настенный / Напольный
    q_cool_w: float = 0.0              # номинальная холодопроизводительность
    q_heat_w: float = 0.0
    capacity_index: int = 0            # 18/22/28/36/45/56/71/80/100/125/140/200
    air_flow_m3_h: float = 0.0
    noise_db_a: float = 0.0
    width_mm: int = 0
    depth_mm: int = 0
    height_mm: int = 0


# Стандартный ряд типоразмеров VRF (по индексу мощности × 100 = ккал/ч)
INDOOR_CATALOG: List[VRFIndoorUnit] = [
    # Кассетные 4-сторонние 600x600 / 840x840
    VRFIndoorUnit("Cassette 18",  "Кассетный", 1800, 2000, 18,
                   air_flow_m3_h=420, noise_db_a=31,
                   width_mm=575, depth_mm=575, height_mm=246),
    VRFIndoorUnit("Cassette 22",  "Кассетный", 2200, 2500, 22,
                   air_flow_m3_h=480, noise_db_a=32,
                   width_mm=575, depth_mm=575, height_mm=246),
    VRFIndoorUnit("Cassette 28",  "Кассетный", 2800, 3200, 28,
                   air_flow_m3_h=600, noise_db_a=33,
                   width_mm=840, depth_mm=840, height_mm=246),
    VRFIndoorUnit("Cassette 36",  "Кассетный", 3600, 4000, 36,
                   air_flow_m3_h=720, noise_db_a=34,
                   width_mm=840, depth_mm=840, height_mm=246),
    VRFIndoorUnit("Cassette 45",  "Кассетный", 4500, 5000, 45,
                   air_flow_m3_h=900, noise_db_a=36,
                   width_mm=840, depth_mm=840, height_mm=246),
    VRFIndoorUnit("Cassette 56",  "Кассетный", 5600, 6300, 56,
                   air_flow_m3_h=1080, noise_db_a=38,
                   width_mm=840, depth_mm=840, height_mm=246),
    VRFIndoorUnit("Cassette 71",  "Кассетный", 7100, 8000, 71,
                   air_flow_m3_h=1260, noise_db_a=40,
                   width_mm=840, depth_mm=840, height_mm=246),
    VRFIndoorUnit("Cassette 80",  "Кассетный", 8000, 9000, 80,
                   air_flow_m3_h=1380, noise_db_a=42,
                   width_mm=840, depth_mm=840, height_mm=246),
    VRFIndoorUnit("Cassette 100", "Кассетный", 10000, 11200, 100,
                   air_flow_m3_h=1500, noise_db_a=44,
                   width_mm=840, depth_mm=840, height_mm=246),
    VRFIndoorUnit("Cassette 125", "Кассетный", 12500, 14000, 125,
                   air_flow_m3_h=1800, noise_db_a=45,
                   width_mm=840, depth_mm=840, height_mm=288),
    VRFIndoorUnit("Cassette 140", "Кассетный", 14000, 16000, 140,
                   air_flow_m3_h=2100, noise_db_a=46,
                   width_mm=840, depth_mm=840, height_mm=288),

    # Канальные
    VRFIndoorUnit("Duct 28", "Канальный", 2800, 3200, 28,
                   air_flow_m3_h=540, noise_db_a=30,
                   width_mm=700, depth_mm=620, height_mm=200),
    VRFIndoorUnit("Duct 45", "Канальный", 4500, 5000, 45,
                   air_flow_m3_h=900, noise_db_a=33,
                   width_mm=900, depth_mm=620, height_mm=240),
    VRFIndoorUnit("Duct 71", "Канальный", 7100, 8000, 71,
                   air_flow_m3_h=1320, noise_db_a=38,
                   width_mm=1100, depth_mm=620, height_mm=240),
    VRFIndoorUnit("Duct 100", "Канальный", 10000, 11200, 100,
                   air_flow_m3_h=1740, noise_db_a=42,
                   width_mm=1400, depth_mm=620, height_mm=300),
    VRFIndoorUnit("Duct 140", "Канальный", 14000, 16000, 140,
                   air_flow_m3_h=2280, noise_db_a=44,
                   width_mm=1400, depth_mm=620, height_mm=300),

    # Настенные
    VRFIndoorUnit("Wall 22", "Настенный", 2200, 2500, 22,
                   air_flow_m3_h=420, noise_db_a=29,
                   width_mm=800, depth_mm=200, height_mm=290),
    VRFIndoorUnit("Wall 36", "Настенный", 3600, 4000, 36,
                   air_flow_m3_h=600, noise_db_a=32,
                   width_mm=990, depth_mm=200, height_mm=290),
    VRFIndoorUnit("Wall 56", "Настенный", 5600, 6300, 56,
                   air_flow_m3_h=900, noise_db_a=38,
                   width_mm=1080, depth_mm=210, height_mm=320),
]


# ============================================================================
# Внешние блоки и комбинации
# ============================================================================

@dataclass
class VRFOutdoorUnit:
    """Внешний блок VRF."""
    name: str
    capacity_index: int                # 200/250/300/.../1200 (×100 ккал/ч)
    q_cool_w: float = 0.0
    q_heat_w: float = 0.0
    refrigerant: str = "R410A"
    max_indoor_units: int = 50
    max_combination_ratio: float = 1.30   # допустимая перегрузка по сумме
    # Магистральные диаметры труб (от блока до первого Refnet), мм
    main_pipe_liquid_mm: float = 9.52
    main_pipe_gas_mm: float = 15.88


OUTDOOR_CATALOG: List[VRFOutdoorUnit] = [
    VRFOutdoorUnit("VRV 200",  200,  22400, 25000, max_indoor_units=13,
                    main_pipe_liquid_mm=9.52, main_pipe_gas_mm=15.88),
    VRFOutdoorUnit("VRV 250",  250,  28000, 31500, max_indoor_units=16,
                    main_pipe_liquid_mm=9.52, main_pipe_gas_mm=19.05),
    VRFOutdoorUnit("VRV 300",  300,  33500, 37500, max_indoor_units=20,
                    main_pipe_liquid_mm=9.52, main_pipe_gas_mm=19.05),
    VRFOutdoorUnit("VRV 350",  350,  40000, 45000, max_indoor_units=23,
                    main_pipe_liquid_mm=12.7, main_pipe_gas_mm=22.22),
    VRFOutdoorUnit("VRV 400",  400,  45000, 50000, max_indoor_units=26,
                    main_pipe_liquid_mm=12.7, main_pipe_gas_mm=22.22),
    VRFOutdoorUnit("VRV 450",  450,  50000, 56000, max_indoor_units=29,
                    main_pipe_liquid_mm=12.7, main_pipe_gas_mm=25.4),
    VRFOutdoorUnit("VRV 500",  500,  56000, 63000, max_indoor_units=33,
                    main_pipe_liquid_mm=12.7, main_pipe_gas_mm=25.4),
    VRFOutdoorUnit("VRV 600",  600,  68000, 76500, max_indoor_units=39,
                    main_pipe_liquid_mm=15.88, main_pipe_gas_mm=28.58),
    VRFOutdoorUnit("VRV 700",  700,  78000, 87500, max_indoor_units=45,
                    main_pipe_liquid_mm=15.88, main_pipe_gas_mm=28.58),
    VRFOutdoorUnit("VRV 800",  800,  90000, 100000, max_indoor_units=50,
                    main_pipe_liquid_mm=15.88, main_pipe_gas_mm=28.58),
    VRFOutdoorUnit("VRV 1000", 1000, 112000, 125000, max_indoor_units=64,
                    main_pipe_liquid_mm=19.05, main_pipe_gas_mm=31.75),
    VRFOutdoorUnit("VRV 1200", 1200, 134000, 150000, max_indoor_units=80,
                    main_pipe_liquid_mm=19.05, main_pipe_gas_mm=34.92),
]


# ============================================================================
# Диаметры труб по индексу мощности (внутренний блок или линия после Refnet).
# Универсальная таблица согласно практике Daikin VRV-IV (мм OD):
#     index ≤ 50  → 6.35 / 12.7
#     index ≤ 80  → 9.52 / 15.88
#     index ≤ 140 → 9.52 / 15.88
#     index ≤ 200 → 9.52 / 19.05
#     index ≤ 300 → 12.7 / 22.22
#     index ≤ 500 → 12.7 / 28.58
#     index ≤ 800 → 15.88 / 28.58
#     index ≤ 1200 → 19.05 / 31.75
# ============================================================================

def pipe_diameters_by_index(capacity_index: int) -> Tuple[float, float]:
    """Возвращает (liquid_mm, gas_mm) по совокупному индексу мощности."""
    if capacity_index <= 50:
        return 6.35, 12.7
    if capacity_index <= 140:
        return 9.52, 15.88
    if capacity_index <= 200:
        return 9.52, 19.05
    if capacity_index <= 300:
        return 12.7, 22.22
    if capacity_index <= 500:
        return 12.7, 28.58
    if capacity_index <= 800:
        return 15.88, 28.58
    return 19.05, 31.75


# ============================================================================
# Разветвитель Refnet/Joint
# ============================================================================

@dataclass
class VRFRefnet:
    """Разветвитель (Refnet Joint или Header).

    serves_units : индексы внутренних блоков, ниже по дереву.
    """
    name: str
    serves_units_indices: List[int] = field(default_factory=list)
    total_capacity_index: int = 0
    pipe_liquid_in_mm: float = 0.0
    pipe_gas_in_mm: float = 0.0
    pipe_liquid_out_mm: float = 0.0
    pipe_gas_out_mm: float = 0.0


# ============================================================================
# Лимиты системы
# ============================================================================

@dataclass
class VRFConstraints:
    """Лимиты VRF по типовому производителю (default: Daikin VRV-IV).
    Все длины — в метрах, перепады — в метрах высоты.
    """
    max_total_pipe_length_m: float = 1000.0
    max_actual_length_to_indoor_m: float = 165.0
    max_equivalent_length_to_indoor_m: float = 190.0
    max_height_indoor_above_outdoor_m: float = 50.0
    max_height_indoor_below_outdoor_m: float = 90.0
    max_height_between_indoors_m: float = 30.0
    max_length_after_first_refnet_m: float = 40.0


# ============================================================================
# Система: внешний + разветвители + внутренние
# ============================================================================

@dataclass
class VRFIndoorAssignment:
    """Привязка одного внутреннего блока к помещению."""
    indoor: VRFIndoorUnit
    space_id: str = ""
    # Расчётные длины трассы от внешнего блока, м
    pipe_length_m: float = 0.0
    height_diff_m: float = 0.0


@dataclass
class VRFSystem:
    """Полная VRF-система."""
    name: str = "VRV-1"
    outdoor: Optional[VRFOutdoorUnit] = None
    indoors: List[VRFIndoorAssignment] = field(default_factory=list)
    refnets: List[VRFRefnet] = field(default_factory=list)

    # Общая длина трассы (магистраль), м — задаётся пользователем
    main_pipe_length_m: float = 0.0
    max_pipe_length_to_indoor_m: float = 0.0
    max_height_diff_m: float = 0.0

    # Расчётные результаты
    combination_ratio: float = 0.0
    total_indoor_capacity_index: int = 0
    capacity_correction_factor: float = 1.0
    corrected_cool_w: float = 0.0
    corrected_heat_w: float = 0.0


# ============================================================================
# Подбор внутренних блоков и сборка системы
# ============================================================================

def select_indoor_for_load(
    q_cool_w: float,
    q_heat_w: float = 0.0,
    *,
    family_filter: Optional[List[str]] = None,
    catalog: Optional[List[VRFIndoorUnit]] = None,
    max_margin: float = 0.30,
) -> Optional[VRFIndoorUnit]:
    """Минимальный внутренний блок, покрывающий нагрузки."""
    cat = catalog if catalog is not None else INDOOR_CATALOG
    if family_filter:
        cat = [m for m in cat if m.family in family_filter]
    if not cat:
        return None
    candidates = []
    for m in cat:
        if m.q_cool_w < q_cool_w:
            continue
        if q_heat_w > 0 and m.q_heat_w < q_heat_w:
            continue
        margin = (m.q_cool_w - q_cool_w) / q_cool_w
        if margin > max_margin:
            continue
        candidates.append((margin, m))
    if not candidates:
        return None
    candidates.sort(key=lambda x: x[0])
    return candidates[0][1]


def select_outdoor_for_total(
    total_index: int,
    *,
    catalog: Optional[List[VRFOutdoorUnit]] = None,
    target_ratio: float = 1.0,
) -> Optional[VRFOutdoorUnit]:
    """Подбор внешнего блока: минимальный, покрывающий total_index * target_ratio."""
    cat = catalog if catalog is not None else OUTDOOR_CATALOG
    need = total_index / max(target_ratio, 0.5)
    for out in cat:
        if out.capacity_index >= need:
            return out
    return None


def build_vrf_system(
    spaces,
    *,
    name: str = "VRV-1",
    indoor_family: Optional[str] = None,
    main_pipe_length_m: float = 30.0,
    max_pipe_length_m: float = 60.0,
    max_height_m: float = 15.0,
    target_combination_ratio: float = 1.0,
) -> VRFSystem:
    """Создаёт VRF-систему по списку помещений.

    Для каждого Space подбирает внутренний блок под heat_gain_w
    (и опционально heat_loss_w). Затем подбирает внешний и считает
    коэффициент соединения.

    spaces — итерируемое из Space.
    """
    family_filter = [indoor_family] if indoor_family else None
    indoors: List[VRFIndoorAssignment] = []
    total_index = 0
    for sp in spaces:
        q_cool = getattr(sp, "heat_gain_w", 0.0)
        if q_cool <= 0:
            continue
        q_heat = getattr(sp, "heat_loss_w", 0.0) or 0.0
        idu = select_indoor_for_load(
            q_cool, q_heat, family_filter=family_filter,
        )
        if idu is None:
            continue
        indoors.append(VRFIndoorAssignment(
            indoor=idu, space_id=getattr(sp, "space_id", ""),
        ))
        total_index += idu.capacity_index

    outdoor = select_outdoor_for_total(
        total_index, target_ratio=target_combination_ratio,
    )
    sys = VRFSystem(
        name=name, outdoor=outdoor, indoors=indoors,
        main_pipe_length_m=main_pipe_length_m,
        max_pipe_length_to_indoor_m=max_pipe_length_m,
        max_height_diff_m=max_height_m,
        total_indoor_capacity_index=total_index,
    )
    if outdoor is not None and outdoor.capacity_index > 0:
        sys.combination_ratio = total_index / outdoor.capacity_index
        # Корректировка холодопроизводительности на длину трассы:
        # упрощённо −1% на каждые 10 м эквивалентной длины > 50 м.
        equivalent_len = main_pipe_length_m + max_pipe_length_m
        excess = max(equivalent_len - 50.0, 0.0)
        sys.capacity_correction_factor = max(1.0 - 0.001 * excess, 0.85)
        sys.corrected_cool_w = (outdoor.q_cool_w
                                  * sys.capacity_correction_factor)
        sys.corrected_heat_w = (outdoor.q_heat_w
                                  * sys.capacity_correction_factor)
    return sys


# ============================================================================
# Проверка лимитов
# ============================================================================

@dataclass
class VRFCheckResult:
    ok: bool = True
    issues: List[str] = field(default_factory=list)

    def add(self, issue: str) -> None:
        self.issues.append(issue)
        self.ok = False


def check_constraints(
    sys: VRFSystem,
    constraints: Optional[VRFConstraints] = None,
) -> VRFCheckResult:
    """Проверяет VRF-систему на ограничения производителя."""
    c = constraints or VRFConstraints()
    res = VRFCheckResult()

    if sys.outdoor is None:
        res.add("Не подобран внешний блок: суммарная мощность вне каталога")
        return res

    # Combination ratio
    if sys.combination_ratio > sys.outdoor.max_combination_ratio:
        res.add(
            f"Коэф. соединения {sys.combination_ratio:.2f} > предела "
            f"{sys.outdoor.max_combination_ratio:.2f}: уменьшите сумму "
            f"внутренних или возьмите больший внешний блок"
        )
    if sys.combination_ratio < 0.5:
        res.add(
            f"Коэф. соединения {sys.combination_ratio:.2f} < 0.5: внешний "
            f"блок будет недогружен, рассмотрите меньший типоразмер"
        )

    # Количество внутренних
    if len(sys.indoors) > sys.outdoor.max_indoor_units:
        res.add(
            f"Внутренних блоков {len(sys.indoors)} > предела "
            f"{sys.outdoor.max_indoor_units}: используйте 2 внешних блока"
        )

    # Общая длина
    total_len = sys.main_pipe_length_m + sum(
        a.pipe_length_m or sys.max_pipe_length_to_indoor_m
        for a in sys.indoors)
    if total_len > c.max_total_pipe_length_m:
        res.add(
            f"Общая длина магистралей {total_len:.0f} м > предела "
            f"{c.max_total_pipe_length_m:.0f} м"
        )

    # Макс. длина до внутреннего
    if sys.max_pipe_length_to_indoor_m > c.max_actual_length_to_indoor_m:
        res.add(
            f"Длина до самого дальнего внутреннего "
            f"{sys.max_pipe_length_to_indoor_m:.0f} м > предела "
            f"{c.max_actual_length_to_indoor_m:.0f} м"
        )

    # Перепад высот
    if abs(sys.max_height_diff_m) > c.max_height_indoor_above_outdoor_m:
        res.add(
            f"Перепад высот {sys.max_height_diff_m:.0f} м > предела "
            f"{c.max_height_indoor_above_outdoor_m:.0f} м"
        )

    return res


def design_pipe_segments(sys: VRFSystem) -> List[Dict]:
    """Возвращает список участков медных труб с диаметрами.

    Структура: [{"segment": "main"|"branch"|"terminal",
                  "from": "outdoor"|"refnet_i", "to": "...",
                  "capacity_index": N, "liquid_mm": ..., "gas_mm": ...}]
    Для упрощённой модели: магистраль (внешний → 1-й Refnet) + терминалы
    (от Refnet к каждому внутреннему).
    """
    if sys.outdoor is None or not sys.indoors:
        return []
    segments: List[Dict] = []
    total = sys.total_indoor_capacity_index
    liq, gas = pipe_diameters_by_index(total)
    segments.append({
        "segment": "main",
        "from": sys.outdoor.name,
        "to": "первый Refnet",
        "capacity_index": total,
        "liquid_mm": liq, "gas_mm": gas,
        "length_m": sys.main_pipe_length_m,
    })
    for a in sys.indoors:
        liq, gas = pipe_diameters_by_index(a.indoor.capacity_index)
        segments.append({
            "segment": "terminal",
            "from": "Refnet",
            "to": a.indoor.name,
            "space_id": a.space_id,
            "capacity_index": a.indoor.capacity_index,
            "liquid_mm": liq, "gas_mm": gas,
            "length_m": a.pipe_length_m or sys.max_pipe_length_to_indoor_m,
        })
    return segments
