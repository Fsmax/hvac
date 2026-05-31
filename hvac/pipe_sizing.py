# -*- coding: utf-8 -*-
"""Подбор сечений труб отопления (упрощённая гидравлика).

Для каждой системы отопления (по sp.system_heating):

  1. Собирает помещения с heat_loss_w > 0.
  2. Из системы (HeatingSystem) берёт Δt = t_supply - t_return.
  3. Считает массовый/объёмный расход теплоносителя для каждого помещения.
  4. Строит упрощённую сеть: котёл → магистраль → стояки → ответвления → приборы.
  5. Для каждого участка подбирает Ø, чтобы скорость v ≤ v_max.
  6. Считает падение давления Δp по формуле Дарси (с учётом местных).

Формулы:

    G (массовый, кг/ч) = Q (Вт) · 3.6 / (c · Δt) = Q / (1.163 · Δt)
        где c = 4.186 кДж/(кг·К) = 1.163 Вт·ч/(кг·К)
    G (объёмный, м³/ч) = G_масс / ρ_воды ≈ G_масс / 970 (при 70°C)

Подбор Ø:
    Q = v · A = v · π·d²/4 → d = √(4·G / (π·v·ρ·3600))
    где G — кг/ч, ρ — плотность кг/м³ (≈ 970 при 70°C).

Стандартные диаметры труб (DN, мм), ГОСТ 3262 (стальные водогазопровод.):
    10, 15, 20, 25, 32, 40, 50, 65, 80, 100, 125, 150
PEX-Al-PEX (металлопластик): 16, 20, 26, 32, 40
PPR: 20, 25, 32, 40, 50, 63, 75, 90, 110

Скорости (СП 60 / СП 60 А.4):
    DN 10..15:  0.20..0.50 м/с (приборные подводки)
    DN 20..32:  0.50..0.80 (ветки, стояки)
    DN 40..80:  0.70..1.50 (главная магистраль)
    DN 100+:    1.0..2.0   (вводы)

Падение давления (формула Дарси для жидкости):
    Δp_тр = λ · L/d · ρv²/2

λ зависит от шероховатости и Re. Для практичности используем
аппроксимацию Альтшуля:
    λ = 0.11 · (k_e/d + 68/Re)^0.25

или упрощённо для турбулентного потока в трубах 0.030 (как СП 60 А.7).
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

WATER_SPECIFIC_HEAT_WH_KG_K = 1.163        # Вт·ч/(кг·К)
WATER_DENSITY_70C = 977.7                  # кг/м³ при 70°C
WATER_DENSITY_45C = 990.2                  # кг/м³ при 45°C (тёплый пол)
WATER_DENSITY_7C = 999.9                   # кг/м³ при 7°C (холодоснабжение)
WATER_VISCOSITY_70C = 0.413e-6             # ν, м²/с при 70°C
WATER_VISCOSITY_45C = 0.605e-6             # ν, м²/с при 45°C
WATER_VISCOSITY_7C = 1.428e-6              # ν, м²/с при 7°C
ROUGHNESS_STEEL_MM = 0.2                   # абс. шерох. стальной трубы, мм
ROUGHNESS_PEX_MM = 0.01                    # PEX/PPR/металлопластик, мм


def water_properties(t_avg_c: float) -> Tuple[float, float]:
    """Возвращает (плотность кг/м³, кинематическая вязкость м²/с) для воды
    при средней температуре контура. Линейная интерполяция между опорными
    точками (7, 45, 70 °C)."""
    if t_avg_c <= 7:
        return WATER_DENSITY_7C, WATER_VISCOSITY_7C
    if t_avg_c >= 70:
        return WATER_DENSITY_70C, WATER_VISCOSITY_70C
    if t_avg_c <= 45:
        # Интерполяция 7..45
        k = (t_avg_c - 7) / (45 - 7)
        rho = WATER_DENSITY_7C + k * (WATER_DENSITY_45C - WATER_DENSITY_7C)
        nu = WATER_VISCOSITY_7C + k * (WATER_VISCOSITY_45C - WATER_VISCOSITY_7C)
        return rho, nu
    # Интерполяция 45..70
    k = (t_avg_c - 45) / (70 - 45)
    rho = WATER_DENSITY_45C + k * (WATER_DENSITY_70C - WATER_DENSITY_45C)
    nu = WATER_VISCOSITY_45C + k * (WATER_VISCOSITY_70C - WATER_VISCOSITY_45C)
    return rho, nu

# Стандартные DN стальной трубы (ГОСТ 3262), мм
STD_STEEL_DN = [10, 15, 20, 25, 32, 40, 50, 65, 80, 100, 125, 150, 200]
# Реальные внутр. диаметры (приближённо) для DN стали, мм
STEEL_INNER_DIAMETER = {
    10: 12.6, 15: 15.7, 20: 21.2, 25: 27.1, 32: 35.9, 40: 41.0,
    50: 53.0, 65: 68.0, 80: 80.5, 100: 105.3, 125: 130.0,
    150: 155.0, 200: 207.0,
}

# Полимерные трубы PEX-Al-PEX (Uponor, Rehau), наружный × внутренний
PEX_AL_PEX = {
    16: 12.0, 20: 16.0, 26: 20.0, 32: 26.0, 40: 33.0, 50: 41.0,
}

# Рекомендованные скорости теплоносителя по диапазонам DN, м/с
RECOMMENDED_VELOCITY_WATER = [
    # (max_dn, v_min, v_max)
    (15,  0.20, 0.40),
    (25,  0.30, 0.60),
    (40,  0.50, 0.90),
    (80,  0.70, 1.30),
    (200, 1.00, 2.00),
]


# ============================================================================
# Структуры данных
# ============================================================================

@dataclass
class PipeSection:
    """Один расчётный участок трубопровода отопления."""
    id: str
    section_type: str = "branch"         # main / riser / branch / connection
    role: str = "supply_return"          # supply / return / supply_return (двухтр.)

    # Нагрузка
    heat_load_w: float = 0.0             # суммарная нагрузка на участке, Вт
    flow_kg_h: float = 0.0               # массовый расход, кг/ч
    flow_m3_h: float = 0.0               # объёмный расход, м³/ч

    # Геометрия (ред-ся пользователем после первого расчёта)
    length_m: float = 5.0                # длина участка, м
    elevation_m: float = 0.0             # перепад высот, м (для статич. давления)
    local_zeta_sum: float = 0.0          # Σζ местных сопротивлений (если 0 —
                                          # используется дефолт по section_type)
    pipe_material: str = "steel"         # steel / pex / ppr

    # Сечение
    dn_mm: float = 0.0                   # условный диаметр
    inner_diameter_mm: float = 0.0       # фактический внутренний

    # Расчётные
    velocity_m_s: float = 0.0
    pressure_loss_friction_pa: float = 0.0
    pressure_loss_local_pa: float = 0.0
    pressure_loss_total_pa: float = 0.0

    # Связи
    serves_space_ids: List[str] = field(default_factory=list)
    is_virtual: bool = False             # True для AHU (виртуальный потребитель —
                                          # калорифер/охладитель приточки)
    note: str = ""


@dataclass
class PipeNetwork:
    """Гидравлическая сеть одного отопительного/холодильного контура."""
    system_name: str = ""                # имя контура: "ТП-1", "Рад-1" (или
                                          # системы для совместимости со старыми)
    parent_system: str = ""              # имя HeatingSystem/CoolingSystem (ИТП)
    circuit_type: str = ""               # radiator / floor / fancoil / ahu_heater /
                                          # cooling_fancoil / cooling_ahu
    medium: str = "heating"              # heating / cooling

    total_heat_load_w: float = 0.0       # Σ нагрузка контура (Вт)
    total_flow_kg_h: float = 0.0         # Σ G (кг/ч)
    delta_t_k: float = 20.0              # Δt теплоносителя/хладоносителя
    t_supply_c: float = 80.0             # температура подачи
    t_return_c: float = 60.0             # температура обратки

    n_terminals: int = 0
    sections: List[PipeSection] = field(default_factory=list)

    # Сумма падений по самой нагруженной ветке (для подбора циркуляц. насоса)
    total_pressure_loss_pa: float = 0.0
    pump_head_m: float = 0.0             # требуемый напор насоса с запасом
    pump_flow_m3_h: float = 0.0          # требуемая подача
    pump_model: str = ""                 # подобранная модель из мини-каталога

    pipe_material: str = "steel"
    insulated: bool = False              # для холода True (изоляция)
    note: str = ""


# ============================================================================
# Базовые формулы
# ============================================================================

def mass_flow_kg_h(heat_load_w: float, delta_t_k: float) -> float:
    """Массовый расход теплоносителя, кг/ч.

    G = Q / (c · Δt)
    где c в Вт·ч/(кг·К) = 1.163, Q в Вт, Δt в К.
    """
    if heat_load_w <= 0 or delta_t_k <= 0:
        return 0.0
    return heat_load_w / (WATER_SPECIFIC_HEAT_WH_KG_K * delta_t_k)


def volume_flow_m3_h(heat_load_w: float, delta_t_k: float,
                     density_kg_m3: float = WATER_DENSITY_70C) -> float:
    """Объёмный расход воды, м³/ч."""
    return mass_flow_kg_h(heat_load_w, delta_t_k) / density_kg_m3


def velocity_in_pipe_m_s(flow_m3_h: float, inner_d_mm: float) -> float:
    """Скорость теплоносителя в трубе, м/с."""
    if inner_d_mm <= 0 or flow_m3_h <= 0:
        return 0.0
    area_m2 = math.pi * (inner_d_mm / 1000.0) ** 2 / 4.0
    return (flow_m3_h / 3600.0) / area_m2


def recommended_velocity(dn_mm: float) -> Tuple[float, float]:
    """Возвращает (v_min, v_max) для DN, м/с."""
    for max_dn, v_min, v_max in RECOMMENDED_VELOCITY_WATER:
        if dn_mm <= max_dn:
            return v_min, v_max
    return RECOMMENDED_VELOCITY_WATER[-1][1:]


def pick_dn(flow_m3_h: float, pipe_material: str = "steel",
            v_max_override: Optional[float] = None) -> Tuple[int, float, float]:
    """Подбирает DN трубы под расход.

    Логика: ищет наименьший DN, при котором v ≤ v_max для этого DN.
    
    Возвращает (DN, внутр. d, фактическая v).
    """
    if flow_m3_h <= 0:
        return (0, 0.0, 0.0)

    if pipe_material == "pex":
        diameters = PEX_AL_PEX
    else:
        diameters = STEEL_INNER_DIAMETER

    sorted_dns = sorted(diameters.keys())
    for dn in sorted_dns:
        inner_d = diameters[dn]
        v = velocity_in_pipe_m_s(flow_m3_h, inner_d)
        v_min, v_max = recommended_velocity(dn)
        v_max_eff = v_max_override or v_max
        if v <= v_max_eff:
            return (dn, inner_d, v)

    # Слишком большой расход — берём максимальный DN с warning
    dn = sorted_dns[-1]
    inner_d = diameters[dn]
    v = velocity_in_pipe_m_s(flow_m3_h, inner_d)
    return (dn, inner_d, v)


def reynolds(velocity_m_s: float, inner_d_mm: float,
             kin_visc: float = WATER_VISCOSITY_70C) -> float:
    """Число Рейнольдса для воды в трубе."""
    if inner_d_mm <= 0 or velocity_m_s <= 0:
        return 0.0
    return velocity_m_s * (inner_d_mm / 1000.0) / kin_visc


def friction_factor_altshul(velocity_m_s: float, inner_d_mm: float,
                             roughness_mm: float = ROUGHNESS_STEEL_MM,
                             kin_visc: float = WATER_VISCOSITY_70C) -> float:
    """Коэф. трения по формуле Альтшуля.

    λ = 0.11 · (k_e/d + 68/Re)^0.25

    Для турбулентного режима (Re > 4000) — типичный случай отопления.
    kin_visc — кинематическая вязкость теплоносителя, м²/с (по умолчанию
    для 70 °C; для тёплого пола/холодоснабжения передавать своё значение
    из water_properties()).
    """
    if inner_d_mm <= 0 or velocity_m_s <= 0:
        return 0.03  # дефолт
    re = reynolds(velocity_m_s, inner_d_mm, kin_visc)
    if re < 100:
        return 64.0 / max(re, 1.0)  # ламинар
    k_rel = roughness_mm / inner_d_mm
    return 0.11 * (k_rel + 68.0 / re) ** 0.25


def pressure_loss_friction_water_pa(length_m: float, inner_d_mm: float,
                                     velocity_m_s: float,
                                     roughness_mm: float = ROUGHNESS_STEEL_MM,
                                     density_kg_m3: float = WATER_DENSITY_70C,
                                     kin_visc: float = WATER_VISCOSITY_70C
                                     ) -> float:
    """Падение давления по трению, Па (Дарси-Вейсбах).

    Δp = λ · L/d · ρv²/2

    Для контуров не на 70 °C передавать density_kg_m3 и kin_visc из
    water_properties(t_avg) (основной расчёт сети это уже делает).
    """
    if inner_d_mm <= 0 or velocity_m_s <= 0:
        return 0.0
    d_m = inner_d_mm / 1000.0
    lam = friction_factor_altshul(velocity_m_s, inner_d_mm, roughness_mm, kin_visc)
    return lam * (length_m / d_m) * (density_kg_m3 * velocity_m_s ** 2 / 2.0)


def pressure_loss_local_water_pa(sum_zeta: float, velocity_m_s: float,
                                  density_kg_m3: float = WATER_DENSITY_70C
                                  ) -> float:
    """Местные сопротивления, Па.
    
    Типовые Σζ:
      • прибор + вентиль + 2 фитинга:    7.0
      • ветка (2 отвода + тройник):       3.0
      • стояк (на 10 м):                  4.0
      • магистраль (фильтры, балансир.):  6.0
    """
    if velocity_m_s <= 0:
        return 0.0
    return sum_zeta * density_kg_m3 * velocity_m_s ** 2 / 2.0


# ============================================================================
# Дефолтные Σζ местных сопротивлений по типу участка
# ============================================================================

DEFAULT_ZETA_BY_SECTION = {
    "connection": 7.0,    # прибор + вентиль + 2 фитинга
    "branch":     4.0,    # ветка / стояк (отвод + тройник + ~10 м)
    "main":       6.0,    # магистраль (фильтр + насос + балансир.)
    "riser":      4.0,
}

# Надбавка к Σζ для холодоснабжения (изоляция, конденсатоотводы, балансир.)
COOLING_ZETA_MULTIPLIER = 1.25


# ============================================================================
# Мини-каталог циркуляционных насосов (Grundfos / Wilo / DAB)
# Точки максимальной подачи (Q_max, м³/ч) и максимального напора (H_max, м).
# Подбор: ищем модель, у которой Q_max >= Q*1.1 И H_max >= H*1.0
# ============================================================================

PUMP_CATALOG = [
    # (Модель, Q_max м³/ч, H_max м, тип)
    ("Grundfos UPS 25-40 180",      2.5,  4.0, "wet_rotor"),
    ("Grundfos UPS 25-60 180",      3.5,  6.0, "wet_rotor"),
    ("Grundfos UPS 25-80 180",      4.5,  8.0, "wet_rotor"),
    ("Grundfos UPS 32-80 180",      6.0,  8.0, "wet_rotor"),
    ("Grundfos Magna1 25-60",       4.0,  6.0, "ec_wet_rotor"),
    ("Grundfos Magna1 32-100",      9.0, 10.0, "ec_wet_rotor"),
    ("Grundfos Magna1 40-120 F",   16.0, 12.0, "ec_wet_rotor"),
    ("Grundfos Magna1 50-100 F",   25.0, 10.0, "ec_wet_rotor"),
    ("Grundfos Magna1 65-120 F",   45.0, 12.0, "ec_wet_rotor"),
    ("Grundfos Magna3 80-100 F",   70.0, 10.0, "ec_wet_rotor"),
    ("Grundfos Magna3 100-120 F", 120.0, 12.0, "ec_wet_rotor"),
    ("Grundfos TPE 80-120",       150.0, 12.0, "inline_dry"),
    ("Grundfos TPE 100-200",      300.0, 20.0, "inline_dry"),
]


def select_pump(flow_m3_h: float, head_m: float,
                flow_reserve: float = 1.1,
                head_reserve: float = 1.3
                ) -> Tuple[str, float, float]:
    """Подбирает циркуляционный насос из мини-каталога.

    Параметры
    ---------
    flow_m3_h    : расчётная подача
    head_m       : расчётный напор (уже с запасом по гидравл. сопротивлению)
    flow_reserve : запас по подаче (1.1 = +10%)
    head_reserve : запас по напору (1.3 = +30% на загрязнение, балансировку,
                   износ крыльчатки)

    Возвращает (модель, Q_max, H_max). Если ни одна модель не подходит —
    возвращает последнюю (самую крупную) с пометкой.
    """
    if flow_m3_h <= 0 or head_m <= 0:
        return ("—", 0.0, 0.0)
    q_req = flow_m3_h * flow_reserve
    h_req = head_m * head_reserve
    for model, q_max, h_max, _ in PUMP_CATALOG:
        if q_max >= q_req and h_max >= h_req:
            return (model, q_max, h_max)
    # Слишком большой расход — берём самый крупный с пометкой
    model, q_max, h_max, _ = PUMP_CATALOG[-1]
    return (f"{model} (требует уточнения — превышен каталог)", q_max, h_max)


# ============================================================================
# Универсальный builder контура (heating / cooling)
# ============================================================================

def _load_for_space(sp: "Space", medium: str) -> float:
    """Нагрузка помещения на контур: для тепла — heat_loss_w,
    для холода — heat_gain_w (полное теплопоступление = sensible + latent)."""
    if medium == "cooling":
        return getattr(sp, "heat_gain_w", 0.0) or 0.0
    return getattr(sp, "heat_loss_w", 0.0) or 0.0


def build_circuit_network(
        circuit_name: str,
        spaces: List["Space"],
        ahu_loads: Optional[List[Tuple[str, float]]] = None,
        parent_system: str = "",
        circuit_type: str = "radiator",
        medium: str = "heating",
        t_supply: float = 80.0,
        t_return: float = 60.0,
        pipe_material: str = "steel",
        connection_length_m: float = 4.0,
        branch_length_m: float = 8.0,
        main_length_m: float = 30.0,
        insulated: bool = False,
) -> PipeNetwork:
    """Строит гидравлическую сеть одного контура (отопление или холод).

    Параметры
    ---------
    ahu_loads : список (имя AHU, нагрузка Вт). Каждая AHU добавляется
                как виртуальная "подводка" к контуру.
    medium    : "heating" → берёт sp.heat_loss_w
                "cooling" → берёт sp.heat_gain_w (полное)
    """
    delta_t_k = abs(t_supply - t_return)
    t_avg = (t_supply + t_return) / 2.0
    density, kin_visc = water_properties(t_avg)

    net = PipeNetwork(
        system_name=circuit_name,
        parent_system=parent_system,
        circuit_type=circuit_type,
        medium=medium,
        delta_t_k=delta_t_k,
        t_supply_c=t_supply,
        t_return_c=t_return,
        pipe_material=pipe_material,
        insulated=insulated or medium == "cooling",
    )

    # Помещения с ненулевой нагрузкой
    loaded: List[Tuple["Space", float]] = []
    for sp in spaces:
        q = _load_for_space(sp, medium)
        if q > 0:
            loaded.append((sp, q))

    # Виртуальные потребители — AHU
    ahu_loads = ahu_loads or []

    if not loaded and not ahu_loads:
        return net

    total_q = sum(q for _, q in loaded) + sum(q for _, q in ahu_loads)
    net.total_heat_load_w = total_q
    net.total_flow_kg_h = mass_flow_kg_h(total_q, delta_t_k)
    net.n_terminals = len(loaded) + len(ahu_loads)

    roughness = ROUGHNESS_PEX_MM if pipe_material == "pex" else ROUGHNESS_STEEL_MM
    zeta_mult = COOLING_ZETA_MULTIPLIER if medium == "cooling" else 1.0

    def _section_dp(length_m: float, v_m_s: float, inner_d_mm: float,
                    sum_zeta: float) -> Tuple[float, float]:
        """Считает Δp трения и местные. Возвращает (dp_тр, dp_мест)."""
        if inner_d_mm <= 0 or v_m_s <= 0:
            return (0.0, 0.0)
        re = v_m_s * (inner_d_mm / 1000.0) / kin_visc
        if re < 100:
            lam = 64.0 / max(re, 1.0)
        else:
            lam = 0.11 * (roughness / inner_d_mm + 68.0 / re) ** 0.25
        d_m = inner_d_mm / 1000.0
        dp_tr = lam * (length_m / d_m) * (density * v_m_s ** 2 / 2.0)
        dp_loc = sum_zeta * density * v_m_s ** 2 / 2.0
        return (dp_tr, dp_loc)

    # ===== Подводки к приборам =====
    for sp, q in loaded:
        g = mass_flow_kg_h(q, delta_t_k)
        v_m3h = g / density
        dn, inner_d, v = pick_dn(v_m3h, pipe_material)
        zeta = DEFAULT_ZETA_BY_SECTION["connection"] * zeta_mult
        dp_tr, dp_loc = _section_dp(connection_length_m, v, inner_d, zeta)
        net.sections.append(PipeSection(
            id=f"{circuit_name}/C-{sp.number}",
            section_type="connection",
            heat_load_w=q,
            flow_kg_h=g,
            flow_m3_h=v_m3h,
            length_m=connection_length_m,
            local_zeta_sum=zeta,
            pipe_material=pipe_material,
            dn_mm=dn,
            inner_diameter_mm=inner_d,
            velocity_m_s=v,
            pressure_loss_friction_pa=dp_tr,
            pressure_loss_local_pa=dp_loc,
            pressure_loss_total_pa=dp_tr + dp_loc,
            serves_space_ids=[sp.space_id],
            note=f"подводка к '{sp.number} {sp.name}'",
        ))

    # ===== Виртуальные подводки к AHU (калорифер/охладитель) =====
    for ahu_name, q_ahu in ahu_loads:
        g = mass_flow_kg_h(q_ahu, delta_t_k)
        v_m3h = g / density
        dn, inner_d, v = pick_dn(v_m3h, pipe_material)
        zeta = DEFAULT_ZETA_BY_SECTION["connection"] * zeta_mult
        # У AHU обычно более длинная подводка (трасса по техэтажу)
        ahu_conn_length = max(connection_length_m * 2, 10.0)
        dp_tr, dp_loc = _section_dp(ahu_conn_length, v, inner_d, zeta)
        net.sections.append(PipeSection(
            id=f"{circuit_name}/AHU-{ahu_name}",
            section_type="connection",
            heat_load_w=q_ahu,
            flow_kg_h=g,
            flow_m3_h=v_m3h,
            length_m=ahu_conn_length,
            local_zeta_sum=zeta,
            pipe_material=pipe_material,
            dn_mm=dn,
            inner_diameter_mm=inner_d,
            velocity_m_s=v,
            pressure_loss_friction_pa=dp_tr,
            pressure_loss_local_pa=dp_loc,
            pressure_loss_total_pa=dp_tr + dp_loc,
            is_virtual=True,
            note=f"калорифер/охладитель AHU '{ahu_name}'",
        ))

    # ===== Ветки/стояки по уровням =====
    from collections import defaultdict
    by_level: Dict[str, List[Tuple["Space", float]]] = defaultdict(list)
    for sp, q in loaded:
        by_level[sp.level].append((sp, q))

    worst_branch_pa = 0.0
    for level, items in by_level.items():
        q_branch = sum(q for _, q in items)
        g_branch = mass_flow_kg_h(q_branch, delta_t_k)
        v_m3h = g_branch / density
        dn, inner_d, v = pick_dn(v_m3h, pipe_material)
        zeta = DEFAULT_ZETA_BY_SECTION["branch"] * zeta_mult
        dp_tr, dp_loc = _section_dp(branch_length_m, v, inner_d, zeta)
        sec = PipeSection(
            id=f"{circuit_name}/B-{level}",
            section_type="branch",
            heat_load_w=q_branch,
            flow_kg_h=g_branch,
            flow_m3_h=v_m3h,
            length_m=branch_length_m,
            local_zeta_sum=zeta,
            pipe_material=pipe_material,
            dn_mm=dn,
            inner_diameter_mm=inner_d,
            velocity_m_s=v,
            pressure_loss_friction_pa=dp_tr,
            pressure_loss_local_pa=dp_loc,
            pressure_loss_total_pa=dp_tr + dp_loc,
            serves_space_ids=[sp.space_id for sp, _ in items],
            note=f"ветка/стояк {level} ({len(items)} приборов)",
        )
        net.sections.append(sec)
        worst_branch_pa = max(worst_branch_pa, sec.pressure_loss_total_pa)

    # ===== Магистраль =====
    g_total = net.total_flow_kg_h
    v_m3h_total = g_total / density
    dn, inner_d, v = pick_dn(v_m3h_total, pipe_material)
    zeta = DEFAULT_ZETA_BY_SECTION["main"] * zeta_mult
    dp_tr, dp_loc = _section_dp(main_length_m, v, inner_d, zeta)
    main_sec = PipeSection(
        id=f"{circuit_name}/MAIN",
        section_type="main",
        heat_load_w=total_q,
        flow_kg_h=g_total,
        flow_m3_h=v_m3h_total,
        length_m=main_length_m,
        local_zeta_sum=zeta,
        pipe_material=pipe_material,
        dn_mm=dn,
        inner_diameter_mm=inner_d,
        velocity_m_s=v,
        pressure_loss_friction_pa=dp_tr,
        pressure_loss_local_pa=dp_loc,
        pressure_loss_total_pa=dp_tr + dp_loc,
        note="магистраль источник → ветки",
    )
    net.sections.append(main_sec)

    # Падение по худшей ветке (подача+обратка)
    worst_conn_pa = max((s.pressure_loss_total_pa for s in net.sections
                         if s.section_type == "connection"), default=0.0)
    net.total_pressure_loss_pa = 2.0 * (worst_conn_pa + worst_branch_pa
                                        + main_sec.pressure_loss_total_pa)
    # Напор насоса с запасом 1.3 = 30%
    pump_head = net.total_pressure_loss_pa / (density * 9.81) * 1.3
    net.pump_head_m = pump_head
    net.pump_flow_m3_h = g_total / density
    model, _, _ = select_pump(net.pump_flow_m3_h, pump_head / 1.3)
    net.pump_model = model

    return net


def build_network_for_heating_system(
        system_name: str, spaces: List["Space"],
        delta_t_k: float = 20.0, pipe_material: str = "steel",
        connection_length_m: float = 4.0, branch_length_m: float = 8.0,
        main_length_m: float = 30.0,
) -> PipeNetwork:
    """Обёртка для обратной совместимости: считает сеть как один контур
    отопления с радиаторным графиком 80/60 (если delta_t_k=20).

    Новый код должен использовать build_circuit_network.
    """
    t_supply = 80.0
    t_return = t_supply - delta_t_k
    return build_circuit_network(
        circuit_name=system_name, spaces=spaces,
        circuit_type="radiator", medium="heating",
        t_supply=t_supply, t_return=t_return,
        pipe_material=pipe_material,
        connection_length_m=connection_length_m,
        branch_length_m=branch_length_m,
        main_length_m=main_length_m,
    )


# ============================================================================
# Подсчёт и распределение нагрузок по контурам в проекте
# ============================================================================

def _ahu_heating_load_for_circuit(project: "HVACProject",
                                   circuit_name: str) -> List[Tuple[str, float]]:
    """Список AHU, чей калорифер привязан к данному контуру отопления."""
    result: List[Tuple[str, float]] = []
    ahu_loads = getattr(project, "ahu_loads", {}) or {}
    for ahu_name, ahu in project.ventilation_systems.items():
        if getattr(ahu, "heating_circuit", "") == circuit_name:
            info = ahu_loads.get(ahu_name, {})
            q = info.get("q_heater_w", 0.0)
            if q > 0:
                result.append((ahu_name, q))
    return result


def _ahu_cooling_load_for_circuit(project: "HVACProject",
                                   circuit_name: str) -> List[Tuple[str, float]]:
    """Список AHU, чей охладитель привязан к данному контуру холода."""
    result: List[Tuple[str, float]] = []
    ahu_loads = getattr(project, "ahu_loads", {}) or {}
    for ahu_name, ahu in project.ventilation_systems.items():
        if getattr(ahu, "cooling_circuit", "") == circuit_name:
            info = ahu_loads.get(ahu_name, {})
            q = info.get("q_cooler_total_w", 0.0)
            if q > 0:
                result.append((ahu_name, q))
    return result


def size_project_pipes(project: "HVACProject",
                       pipe_material: str = "steel"
                       ) -> Dict[str, PipeNetwork]:
    """Гидравлический расчёт всех контуров отопления проекта.

    Логика:
    1. Если у помещения задан circuit_heating — попадает в этот контур.
    2. Помещения с system_heating без circuit_heating группируются по
       системе как "виртуальный" контур (для обратной совместимости).
    3. Для каждого AHU с heating_circuit добавляется нагрузка калорифера
       как виртуальная подводка.
    """
    from collections import defaultdict
    result: Dict[str, PipeNetwork] = {}

    # 1. Явно определённые контуры
    for circ_name, circ in project.heating_circuits.items():
        spaces = [sp for sp in project.spaces
                  if sp.circuit_heating == circ_name]
        ahu_loads = _ahu_heating_load_for_circuit(project, circ_name)
        if not spaces and not ahu_loads:
            continue
        net = build_circuit_network(
            circuit_name=circ_name, spaces=spaces, ahu_loads=ahu_loads,
            parent_system=circ.parent_system,
            circuit_type=circ.circuit_type, medium="heating",
            t_supply=circ.t_supply, t_return=circ.t_return,
            pipe_material=circ.pipe_material or pipe_material,
        )
        result[circ_name] = net

    # 2. Помещения с system_heating без явного контура (fallback)
    orphans: Dict[str, List["Space"]] = defaultdict(list)
    for sp in project.spaces:
        if (sp.system_heating and not sp.circuit_heating
                and _load_for_space(sp, "heating") > 0):
            orphans[sp.system_heating].append(sp)

    for sys_name, spaces in orphans.items():
        if sys_name in result:
            continue  # уже посчитан как контур
        hs = project.heating_systems.get(sys_name)
        t_sup = hs.t_supply if hs else 80.0
        t_ret = hs.t_return if hs else 60.0
        net = build_circuit_network(
            circuit_name=sys_name, spaces=spaces,
            parent_system=sys_name,
            circuit_type="radiator", medium="heating",
            t_supply=t_sup, t_return=t_ret,
            pipe_material=pipe_material,
        )
        result[sys_name] = net

    return result


def size_project_cooling_pipes(project: "HVACProject",
                                pipe_material: str = "steel"
                                ) -> Dict[str, PipeNetwork]:
    """Гидравлический расчёт всех контуров холодоснабжения проекта.

    Симметрично size_project_pipes, но:
    - группировка по circuit_cooling / system_cooling
    - нагрузка = sp.heat_gain_w (полное теплопоступление)
    - типовой график 7/12 °C, плотность ≈ 1000
    - Σζ увеличен на 25% (изоляция, конденсат, балансировка)
    """
    from collections import defaultdict
    result: Dict[str, PipeNetwork] = {}

    # 1. Явные контуры холода
    for circ_name, circ in project.cooling_circuits.items():
        spaces = [sp for sp in project.spaces
                  if sp.circuit_cooling == circ_name]
        ahu_loads = _ahu_cooling_load_for_circuit(project, circ_name)
        if not spaces and not ahu_loads:
            continue
        net = build_circuit_network(
            circuit_name=circ_name, spaces=spaces, ahu_loads=ahu_loads,
            parent_system=circ.parent_system,
            circuit_type=f"cooling_{circ.circuit_type}",
            medium="cooling",
            t_supply=circ.t_supply, t_return=circ.t_return,
            pipe_material=circ.pipe_material or pipe_material,
            insulated=circ.insulated,
        )
        result[circ_name] = net

    # 2. Fallback по system_cooling
    orphans: Dict[str, List["Space"]] = defaultdict(list)
    for sp in project.spaces:
        if (sp.system_cooling and not sp.circuit_cooling
                and _load_for_space(sp, "cooling") > 0):
            orphans[sp.system_cooling].append(sp)

    for sys_name, spaces in orphans.items():
        if sys_name in result:
            continue
        cs = project.cooling_systems.get(sys_name)
        t_sup = cs.t_supply if cs else 7.0
        t_ret = cs.t_return if cs else 12.0
        net = build_circuit_network(
            circuit_name=sys_name, spaces=spaces,
            parent_system=sys_name,
            circuit_type="cooling_fancoil", medium="cooling",
            t_supply=t_sup, t_return=t_ret,
            pipe_material=pipe_material, insulated=True,
        )
        result[sys_name] = net

    return result


# ============================================================================
# Пересчёт сети после ручной правки длин/Σζ участков
# ============================================================================

def recompute_pipe_network(net: PipeNetwork) -> None:
    """Пересчитывает Δp всех участков сети по текущим length_m / local_zeta_sum
    / elevation_m. Используется после ручного редактирования.

    Расход и DN остаются прежними (рассчитаны при первом построении сети);
    пересчитываются только потери давления и напор насоса.
    """
    t_avg = (net.t_supply_c + net.t_return_c) / 2.0
    density, kin_visc = water_properties(t_avg)
    roughness = (ROUGHNESS_PEX_MM if net.pipe_material == "pex"
                 else ROUGHNESS_STEEL_MM)
    zeta_mult = COOLING_ZETA_MULTIPLIER if net.medium == "cooling" else 1.0

    for s in net.sections:
        if s.inner_diameter_mm <= 0 or s.velocity_m_s <= 0:
            s.pressure_loss_friction_pa = 0.0
            s.pressure_loss_local_pa = 0.0
            s.pressure_loss_total_pa = 0.0
            continue
        v = s.velocity_m_s
        d_m = s.inner_diameter_mm / 1000.0
        re = v * d_m / kin_visc
        if re < 100:
            lam = 64.0 / max(re, 1.0)
        else:
            lam = 0.11 * (roughness / s.inner_diameter_mm + 68.0 / re) ** 0.25
        zeta = s.local_zeta_sum
        if zeta <= 0:
            zeta = DEFAULT_ZETA_BY_SECTION.get(s.section_type, 4.0) * zeta_mult
        s.pressure_loss_friction_pa = (lam * (s.length_m / d_m)
                                       * (density * v ** 2 / 2.0))
        s.pressure_loss_local_pa = zeta * density * v ** 2 / 2.0
        s.pressure_loss_total_pa = (s.pressure_loss_friction_pa
                                    + s.pressure_loss_local_pa)

    # Перерасчёт суммарного Δp по худшей ветке
    worst_conn_pa = max((s.pressure_loss_total_pa for s in net.sections
                         if s.section_type == "connection"), default=0.0)
    worst_branch_pa = max((s.pressure_loss_total_pa for s in net.sections
                           if s.section_type == "branch"), default=0.0)
    main_pa = sum(s.pressure_loss_total_pa for s in net.sections
                  if s.section_type == "main")
    net.total_pressure_loss_pa = 2.0 * (worst_conn_pa + worst_branch_pa + main_pa)

    # Учёт перепада высот (статическое давление на самой высокой подводке)
    max_elev = max((s.elevation_m for s in net.sections), default=0.0)
    static_pa = density * 9.81 * max_elev

    pump_head = (net.total_pressure_loss_pa + static_pa) / (density * 9.81) * 1.3
    net.pump_head_m = pump_head
    net.pump_flow_m3_h = net.total_flow_kg_h / density
    model, _, _ = select_pump(net.pump_flow_m3_h, pump_head / 1.3)
    net.pump_model = model


# ============================================================================
# Сводка
# ============================================================================

def network_summary(net: PipeNetwork) -> Dict:
    """Краткая сводка по сети."""
    t_avg = (net.t_supply_c + net.t_return_c) / 2.0
    density, _ = water_properties(t_avg)
    mains = [s for s in net.sections if s.section_type == "main"]
    return {
        "system_name": net.system_name,
        "parent_system": net.parent_system,
        "circuit_type": net.circuit_type,
        "medium": net.medium,
        "t_supply_c": net.t_supply_c,
        "t_return_c": net.t_return_c,
        "total_heat_load_kw": net.total_heat_load_w / 1000.0,
        "total_flow_m3_h": net.total_flow_kg_h / density,
        "n_terminals": net.n_terminals,
        "main_dn": mains[0].dn_mm if mains else 0,
        "main_velocity_m_s": mains[0].velocity_m_s if mains else 0.0,
        "max_velocity_m_s": max((s.velocity_m_s for s in net.sections),
                                default=0.0),
        "total_pressure_loss_kpa": net.total_pressure_loss_pa / 1000.0,
        "pump_head_m": net.pump_head_m,
        "pump_flow_m3_h": net.pump_flow_m3_h,
        "pump_model": net.pump_model,
    }
