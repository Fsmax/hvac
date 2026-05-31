# -*- coding: utf-8 -*-
"""Гидравлика контура отопления: насос, расширительный бак, подпитка.

Дополнение к hvac/pipe_sizing.py:

    • Подбор циркуляционного насоса (Q, H) с учётом запаса
    • Расчёт объёма мембранного расширительного бака
    • Подбор давления подпитки и предохранительного клапана
    • Подбор типового насоса из встроенного каталога (Wilo / Grundfos)
    • Подбор типового бака из встроенного каталога

Расширительный бак (ГОСТ 17032 / СП 60.13330 п. 6.4):

    V_бак = V_сист · (ρ_min/ρ_max − 1) · (P_max + 1) / (P_max − P_init)

где:
    V_сист — объём воды в системе, л
    ρ_min  — плотность при t_min (10°C для холодной воды)
    ρ_max  — плотность при t_max (t_supply)
    P_max  — макс. рабочее давление (избыточное), бар
    P_init — давление зарядки бака (= статическое + 0.2), бар

В практических расчётах удобнее работать с α_T (коэф. температурного
расширения воды):

    V_бак = V_сист · α_T · K_давл

    K_давл = (P_max + 1) / (P_max − P_init)

α_T для воды (СП 60 / DIN 4807):
    40°C → 0.0079
    50°C → 0.0121
    60°C → 0.0171
    70°C → 0.0228
    80°C → 0.0290
    90°C → 0.0359

Циркуляционный насос:

    Q_насос = G_сист (м³/ч)
    H_насос = ΔP_сети / (ρ·g)  +  H_зап

    Запас H обычно 1.2..1.3 (на загрязнение, балансировочные клапаны).

Подбор типового насоса:
    - подбор по Q и H ближайшего из каталога (с запасом)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from hvac.pipe_sizing import PipeNetwork


# ============================================================================
# Физика воды
# ============================================================================

G_M_S2 = 9.80665                       # ускорение свободного падения

# Плотность воды [кг/м³] от температуры [°C]
WATER_DENSITY_TABLE = {
    10: 999.7, 20: 998.2, 30: 995.6, 40: 992.2,
    50: 988.0, 60: 983.2, 70: 977.7, 80: 971.8,
    90: 965.3, 100: 958.4,
}

# Коэффициент температурного расширения воды от t=10°C к t_supply
# (по DIN 4807 / СП 60). Линейная интерполяция между точками.
ALPHA_T_TABLE = {
    30: 0.0043, 40: 0.0079, 50: 0.0121, 60: 0.0171,
    70: 0.0228, 80: 0.0290, 90: 0.0359, 100: 0.0435,
}


def water_density(t_c: float) -> float:
    """Плотность воды линейной интерполяцией по таблице."""
    return _interp_table(WATER_DENSITY_TABLE, t_c)


def alpha_t(t_supply_c: float) -> float:
    """Коэффициент температурного расширения воды от 10°C до t_supply."""
    return _interp_table(ALPHA_T_TABLE, t_supply_c)


def _interp_table(table: Dict[float, float], x: float) -> float:
    keys = sorted(table.keys())
    if x <= keys[0]:
        return table[keys[0]]
    if x >= keys[-1]:
        return table[keys[-1]]
    for i in range(len(keys) - 1):
        if keys[i] <= x <= keys[i + 1]:
            x0, x1 = keys[i], keys[i + 1]
            y0, y1 = table[x0], table[x1]
            return y0 + (y1 - y0) * (x - x0) / (x1 - x0)
    return table[keys[-1]]


# ============================================================================
# Объём воды в системе (приближение)
# ============================================================================

# Удельный объём воды на единицу мощности отопления, л/кВт.
# Используется когда фактический объём не задан явно.
# Источник: Stuhrmann / Hennings + СП 60 п. 7.4
SYSTEM_VOLUME_BY_TYPE_L_PER_KW = {
    "radiator":   13.5,    # стальные радиаторы + чугунные
    "convector":  10.0,
    "floor":      17.0,    # тёплый пол, с большим объёмом труб
    "fancoil":     4.0,
    "ahu_heater":  6.0,
}


def estimate_system_volume_l(heat_load_kw: float,
                              circuit_type: str = "radiator",
                              custom_l_per_kw: Optional[float] = None) -> float:
    """Оценка объёма воды в системе по тепловой нагрузке.

    Параметры
    ---------
    heat_load_kw     : полная тепловая нагрузка контура, кВт
    circuit_type     : тип контура — ключ из SYSTEM_VOLUME_BY_TYPE_L_PER_KW
    custom_l_per_kw  : переопределить удельный объём

    Для точного расчёта суммируйте фактические объёмы по элементам сети
    (трубы + радиаторы + котёл + AHU-калорифер).
    """
    if custom_l_per_kw is not None:
        return heat_load_kw * custom_l_per_kw
    return heat_load_kw * SYSTEM_VOLUME_BY_TYPE_L_PER_KW.get(
        circuit_type, 13.5)


# ============================================================================
# Расширительный бак
# ============================================================================

@dataclass
class ExpansionTank:
    """Результат расчёта мембранного расширительного бака."""

    # Входные параметры
    system_volume_l: float = 0.0
    t_supply_c: float = 80.0
    t_min_c: float = 10.0
    p_max_bar: float = 4.0                 # макс. рабочее, изб., бар
    p_init_bar: float = 0.0                # давление зарядки бака
    safety_factor: float = 1.10            # запас (по СП 60 п. 6.5.6)

    # Расчётные
    alpha_t: float = 0.0
    expansion_volume_l: float = 0.0        # ΔV расширения, л
    pressure_factor: float = 0.0           # K_p = (P_max+1)/(P_max−P_init)
    required_tank_volume_l: float = 0.0
    selected_model: str = ""               # имя из каталога

    # Безопасный предохранительный клапан (Predохр)
    relief_valve_pressure_bar: float = 0.0


def calculate_expansion_tank(
    system_volume_l: float,
    t_supply_c: float = 80.0,
    *,
    static_height_m: float = 0.0,
    p_max_bar: Optional[float] = None,
    p_min_bar: float = 0.5,
    safety_factor: float = 1.10,
    p_init_offset_bar: float = 0.2,
) -> ExpansionTank:
    """Расчёт мембранного расширительного бака.

    Параметры
    ---------
    system_volume_l   : объём воды в системе, л
    t_supply_c        : температура подачи, °C
    static_height_m   : статическая высота здания (от насоса до верх. точки)
    p_max_bar         : макс. рабочее давление; по умолчанию = static + 1.5
    p_min_bar         : минимальное в верхней точке (для отсутствия закипания)
    safety_factor     : запас 1.05..1.20
    p_init_offset_bar : смещение давления зарядки от P_min (типично 0.2)
    """
    # Давление статики: 1 бар на 10 м высоты
    p_static = static_height_m / 10.0
    if p_max_bar is None:
        p_max_bar = max(p_static + 1.5, 2.5)
    # Давление зарядки бака
    p_init_bar = max(p_static + p_min_bar + p_init_offset_bar, p_min_bar)

    if p_max_bar <= p_init_bar:
        # Зарядка слишком высокая — поднимаем P_max
        p_max_bar = p_init_bar + 0.5

    a = alpha_t(t_supply_c)
    delta_v = system_volume_l * a
    k_p = (p_max_bar + 1.0) / (p_max_bar - p_init_bar)
    v_tank = delta_v * k_p * safety_factor

    return ExpansionTank(
        system_volume_l=system_volume_l,
        t_supply_c=t_supply_c,
        p_max_bar=p_max_bar,
        p_init_bar=p_init_bar,
        safety_factor=safety_factor,
        alpha_t=a,
        expansion_volume_l=delta_v,
        pressure_factor=k_p,
        required_tank_volume_l=v_tank,
        relief_valve_pressure_bar=p_max_bar + 0.5,
    )


# Стандартный ряд мембранных баков (Reflex N, Wester WRV), л:
STD_EXPANSION_TANK_LITERS = [
    8, 12, 18, 25, 35, 50, 80, 100, 140, 200, 300, 500, 750, 1000,
]


def pick_expansion_tank(required_l: float) -> int:
    """Возвращает ближайший типоразмер бака не меньше required_l."""
    for v in STD_EXPANSION_TANK_LITERS:
        if v >= required_l:
            return v
    return STD_EXPANSION_TANK_LITERS[-1]


# ============================================================================
# Циркуляционный насос
# ============================================================================

@dataclass
class PumpRequirement:
    """Параметры точки рабочего режима насоса."""

    flow_m3_h: float = 0.0
    head_m: float = 0.0
    network_dp_pa: float = 0.0             # без запаса
    head_reserve_factor: float = 1.30
    t_medium_c: float = 70.0

    # Подобранный насос
    selected_model: str = ""
    selected_flow_m3_h: float = 0.0
    selected_head_m: float = 0.0
    selected_power_w: float = 0.0


def required_pump_head_m(network_dp_pa: float,
                          t_medium_c: float = 70.0,
                          reserve_factor: float = 1.30) -> float:
    """Напор насоса в метрах водяного столба из ΔP сети в Па.

        H = ΔP · k / (ρ · g)
    """
    rho = water_density(t_medium_c)
    if rho <= 0:
        return 0.0
    return (network_dp_pa * reserve_factor) / (rho * G_M_S2)


# Каталог типовых циркуляционных насосов (Wilo Stratos / Grundfos UPM / Magna).
# Список (model, flow_m3_h_nominal, head_m_nominal, power_w_nominal).
PUMP_CATALOG: List[tuple] = [
    ("Grundfos UPM3 25-40",  2.5,  4.0,  45),
    ("Grundfos UPM3 25-60",  3.0,  6.0,  65),
    ("Wilo Yonos 25/6",      3.0,  6.0,  65),
    ("Wilo Yonos 30/7",      4.5,  7.0,  85),
    ("Grundfos Magna1 32-80", 6.0,  8.0, 120),
    ("Grundfos Magna1 32-100", 8.0, 10.0, 180),
    ("Wilo Stratos 40/1-12", 12.0, 12.0, 280),
    ("Wilo Stratos 50/1-12", 18.0, 12.0, 380),
    ("Grundfos Magna3 65-120", 30.0, 12.0, 600),
    ("Wilo Stratos 80/1-12", 50.0, 12.0, 1100),
    ("Wilo Stratos 100/1-12", 80.0, 12.0, 1800),
]


def pick_pump(required_flow_m3_h: float, required_head_m: float
               ) -> Optional[tuple]:
    """Подбирает насос: первая запись каталога, чей Q ≥ required и H ≥ required.

    Возвращает (model, flow, head, power_w) или None если ничего не подходит.
    """
    for entry in PUMP_CATALOG:
        model, q, h, p_w = entry
        if q >= required_flow_m3_h and h >= required_head_m:
            return entry
    return None


def design_pump(network: "PipeNetwork",
                 reserve_factor: float = 1.30) -> PumpRequirement:
    """Полный расчёт точки работы и подбор насоса для PipeNetwork.

    Использует уже заполненные network.total_flow_kg_h и
    network.total_pressure_loss_pa. Для каждого контура запас 1.3 — норма
    для типовой системы отопления (закладывает балансировку + загрязнение).
    """
    rho = water_density(network.t_supply_c)
    flow_m3_h = (network.total_flow_kg_h / rho) if rho > 0 else 0.0
    head_m = required_pump_head_m(
        network.total_pressure_loss_pa,
        t_medium_c=network.t_supply_c,
        reserve_factor=reserve_factor,
    )

    req = PumpRequirement(
        flow_m3_h=flow_m3_h,
        head_m=head_m,
        network_dp_pa=network.total_pressure_loss_pa,
        head_reserve_factor=reserve_factor,
        t_medium_c=network.t_supply_c,
    )

    pick = pick_pump(flow_m3_h, head_m)
    if pick is not None:
        model, q, h, p_w = pick
        req.selected_model = model
        req.selected_flow_m3_h = q
        req.selected_head_m = h
        req.selected_power_w = p_w
    return req


# ============================================================================
# Подпитка и предохранительный клапан
# ============================================================================

@dataclass
class MakeupValveSpec:
    """Подпитка системы (восполнение испарения и утечек)."""

    system_volume_l: float = 0.0
    daily_makeup_l: float = 0.0            # ~0.5% объёма в сутки
    cold_water_pressure_bar: float = 4.0
    relief_valve_pressure_bar: float = 0.0


def design_makeup(system_volume_l: float,
                   relief_valve_pressure_bar: float,
                   daily_loss_fraction: float = 0.005) -> MakeupValveSpec:
    """Параметры узла подпитки.

    daily_loss_fraction = 0.005 → 0.5% системы в сутки (норматив СП 60).
    """
    return MakeupValveSpec(
        system_volume_l=system_volume_l,
        daily_makeup_l=system_volume_l * daily_loss_fraction,
        relief_valve_pressure_bar=relief_valve_pressure_bar,
    )


# ============================================================================
# Высокоуровневая обёртка
# ============================================================================

@dataclass
class HeatingHydraulicsResult:
    """Полный результат гидравлического расчёта контура."""

    network_name: str = ""
    pump: PumpRequirement = field(default_factory=PumpRequirement)
    expansion_tank: ExpansionTank = field(default_factory=ExpansionTank)
    makeup: MakeupValveSpec = field(default_factory=MakeupValveSpec)


def design_hydraulics_for_network(
    network: "PipeNetwork",
    *,
    circuit_type: str = "radiator",
    static_height_m: float = 10.0,
    pump_reserve_factor: float = 1.30,
    system_volume_l: Optional[float] = None,
) -> HeatingHydraulicsResult:
    """Полный расчёт «насос + бак + подпитка» для одного PipeNetwork.

    Возвращает HeatingHydraulicsResult со всеми тремя компонентами.
    Если system_volume_l не задан — оценивается по тепловой нагрузке
    через estimate_system_volume_l().
    """
    pump = design_pump(network, reserve_factor=pump_reserve_factor)
    vol = system_volume_l
    if vol is None:
        vol = estimate_system_volume_l(
            heat_load_kw=network.total_heat_load_w / 1000.0,
            circuit_type=circuit_type,
        )
    tank = calculate_expansion_tank(
        system_volume_l=vol,
        t_supply_c=network.t_supply_c,
        static_height_m=static_height_m,
    )
    tank.selected_model = f"Бак {pick_expansion_tank(tank.required_tank_volume_l)} л"
    makeup = design_makeup(
        system_volume_l=vol,
        relief_valve_pressure_bar=tank.relief_valve_pressure_bar,
    )
    return HeatingHydraulicsResult(
        network_name=network.system_name, pump=pump,
        expansion_tank=tank, makeup=makeup,
    )
