# -*- coding: utf-8 -*-
"""Расчёт точек процесса в приточной установке (AHU).

Дополнение к hvac/ahu_load.py: даёт детальный психрометрический разбор
по точкам процесса для построения i-d диаграммы и инженерного отчёта.

Модель установки (типовая компоновка)
-------------------------------------
    1) outdoor          — наружный воздух
    2) after_recovery   — после теплоутилизатора (только если has_recovery)
    3) after_mix        — после смесительной камеры (если есть рециркуляция)
    4) after_heater     — после калорифера (зима / межсезонье)
    5) after_cooler     — после охладителя (лето)
    6) after_humid      — после увлажнителя (если задан, обычно зима)
    7) supply           — конечный приточный воздух (= последняя из точек 4-6)

Сценарии расчёта
----------------
    "winter"        — выбор зимнего расчётного режима
    "summer"        — летний расчётный режим
    "transitional"  — межсезонье (наружный t_trans, типично +5°C)

Использование
-------------
    from hvac.ahu_process import compute_ahu_process
    proc = compute_ahu_process(ahu_load, params, mode="winter")
    for name, state in proc.points.items():
        print(name, state.t_c, state.w_g_kg, state.rh)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Optional, TYPE_CHECKING

from hvac.psychro import (
    AirState, air_power_kw, cool_dehumidify, heat,
    heat_recovery, humidify_adiabatic, humidify_steam,
    mass_flow_from_volume, mix_streams, sensible_power_kw,
    latent_power_kw, humidity_ratio_from_rh,
)

if TYPE_CHECKING:
    from hvac.ahu_load import AHULoad
    from hvac.models import ProjectParameters


# ============================================================================
# Дефолты межсезонья и параметров охладителя
# ============================================================================

T_TRANSITIONAL_C = 5.0
RH_TRANSITIONAL = 0.7
COOLER_BYPASS_FACTOR_DEFAULT = 0.15
COOLER_ADP_OFFSET = 3.0   # ADP ≈ t_supply − 3°C для типовых охладителей


# ============================================================================
# Результат расчёта процесса
# ============================================================================

@dataclass
class AHUProcess:
    """Полный психрометрический расчёт одного режима работы AHU."""

    ahu_name: str
    mode: str                              # winter / summer / transitional

    # Точки процесса (упорядочены по ходу воздуха)
    points: Dict[str, AirState] = field(default_factory=dict)

    # Массовый расход сухого воздуха, кг/с (по плотности на входе)
    mass_flow_kg_s: float = 0.0
    volume_flow_m3_h: float = 0.0

    # Доля рециркуляции (0 — 100% свежий, 1 — полная рециркуляция)
    recirculation_ratio: float = 0.0

    # Расчётные мощности секций, кВт (+ нагрев, − охлаждение)
    q_recovery_kw: float = 0.0
    q_heater_kw: float = 0.0
    q_cooler_total_kw: float = 0.0
    q_cooler_sensible_kw: float = 0.0
    q_cooler_latent_kw: float = 0.0
    q_humidifier_kw: float = 0.0           # для пара — мощность парогенератора

    # Расход влаги увлажнителя, кг/ч (для пароувлажнителя или форсунок)
    humidifier_water_kg_h: float = 0.0

    # Конденсат с охладителя, кг/ч
    condensate_kg_h: float = 0.0


# ============================================================================
# Основная функция
# ============================================================================

def compute_ahu_process(
    load: "AHULoad",
    params: "ProjectParameters",
    mode: str = "winter",
    *,
    outdoor_rh_winter: float = 0.85,
    outdoor_rh_summer: float = 0.45,
    indoor_rh_winter: float = 0.35,
    indoor_rh_summer: float = 0.50,
    recovery_w_eff_winter: float = 0.0,
    recovery_w_eff_summer: float = 0.0,
    recirculation_ratio: float = 0.0,
    cooler_bypass_factor: float = COOLER_BYPASS_FACTOR_DEFAULT,
    humidifier_target_rh: Optional[float] = None,
    humidifier_kind: str = "steam",        # steam / adiabatic
    humidifier_adiabatic_eff: float = 0.85,
) -> AHUProcess:
    """Считает все точки процесса для одного режима работы AHU.

    Параметры
    ---------
    load                   : AHULoad (расходы, температуры, рекуператор)
    params                 : ProjectParameters (наружные температуры,
                              w_out_summer_g_kg, w_in_summer_g_kg)
    mode                   : "winter" | "summer" | "transitional"

    Ключевые именованные:
        outdoor_rh_winter    : φ наружного зимой (по умолчанию 85%)
        outdoor_rh_summer    : φ наружного летом (45%)
        indoor_rh_winter/summer : φ внутри (для оценки вытяжного состояния
                              и работы рекуператора)
        recovery_w_eff_*     : эффективность рекуператора по ВЛАГЕ (для
                              энтальпийных роторов; пластинчатый = 0)
        recirculation_ratio  : доля рециркуляции (0..1)
        cooler_bypass_factor : BF охладителя (типично 0.15)
        humidifier_target_rh : целевая φ после увлажнителя; None — без увлажн.
        humidifier_kind      : steam (W растёт, t≈const) или
                              adiabatic (Twb≈const, t падает)
    """
    proc = AHUProcess(ahu_name=load.system_name, mode=mode)

    # ---------- 1. Наружный воздух ----------
    if mode == "winter":
        t_out = params.t_out_heating
        rh_out = outdoor_rh_winter
    elif mode == "summer":
        t_out = params.t_out_cooling
        # Лето: при наличии w_out_summer_g_kg задаём W напрямую
        outdoor = AirState(
            t_c=t_out,
            W=params.w_out_summer_g_kg / 1000.0,
        )
        proc.points["outdoor"] = outdoor
        rh_out = None  # уже задали через W
    elif mode == "transitional":
        t_out = T_TRANSITIONAL_C
        rh_out = RH_TRANSITIONAL
    else:
        raise ValueError(f"Неизвестный режим: {mode!r}. "
                          f"Допустимо: winter/summer/transitional")

    if mode != "summer":
        outdoor = AirState.from_t_rh(t_out, rh_out)
        proc.points["outdoor"] = outdoor

    # Удалённый воздух — задаём из внутренней температуры и RH
    if mode == "summer":
        extract_rh = indoor_rh_summer
        # Внутреннее состояние — из w_in_summer_g_kg, если задано;
        # иначе из RH
        if params.w_in_summer_g_kg > 0:
            extract = AirState(
                t_c=load.t_indoor_avg_summer,
                W=params.w_in_summer_g_kg / 1000.0,
            )
        else:
            extract = AirState.from_t_rh(load.t_indoor_avg_summer,
                                          extract_rh)
    else:
        extract_rh = indoor_rh_winter
        extract = AirState.from_t_rh(load.t_indoor_avg_winter, extract_rh)
    proc.points["extract"] = extract

    # ---------- 2. Рекуператор ----------
    if load.has_recovery and load.supply_m3_h > 0:
        eta_t = (load.recovery_eff_winter if mode != "summer"
                  else load.recovery_eff_summer)
        eta_w = (recovery_w_eff_winter if mode != "summer"
                  else recovery_w_eff_summer)
        after_rec = heat_recovery(outdoor, extract,
                                   efficiency_t=eta_t,
                                   efficiency_w=eta_w)
        proc.points["after_recovery"] = after_rec
        current = after_rec
    else:
        current = outdoor

    # ---------- 3. Смесительная камера (рециркуляция) ----------
    r = max(0.0, min(1.0, recirculation_ratio))
    proc.recirculation_ratio = r
    if r > 0:
        # Массовые доли: (1−r) свежего + r вытяжного
        mixed = mix_streams([(current, 1.0 - r), (extract, r)])
        proc.points["after_mix"] = mixed
        current = mixed

    # Массовый расход — по плотности подаваемого воздуха в supply-точке
    # (после всех секций). Для расчёта мощностей принимаем плотность
    # на наружном воздухе (консервативно).
    proc.volume_flow_m3_h = load.supply_m3_h
    proc.mass_flow_kg_s = mass_flow_from_volume(load.supply_m3_h, outdoor)
    m_kg_s = proc.mass_flow_kg_s

    # ---------- 4. Калорифер / Охладитель ----------
    if mode == "summer":
        t_supply = load.t_supply_summer
        t_adp = max(t_supply - COOLER_ADP_OFFSET, 5.0)
        after_cooler = cool_dehumidify(current, t_adp, cooler_bypass_factor)
        proc.points["after_cooler"] = after_cooler
        # Полная нагрузка охладителя
        proc.q_cooler_total_kw = -air_power_kw(m_kg_s, current, after_cooler)
        proc.q_cooler_sensible_kw = -sensible_power_kw(
            m_kg_s, current.t_c, after_cooler.t_c,
            W_avg=0.5 * (current.W + after_cooler.W),
        )
        proc.q_cooler_latent_kw = -latent_power_kw(
            m_kg_s, current.W, after_cooler.W)
        # Конденсат
        if after_cooler.W < current.W:
            proc.condensate_kg_h = (current.W - after_cooler.W) * m_kg_s * 3600.0
        current = after_cooler
        # Если t_supply > t_adp — догрев после охладителя (post-heat).
        # Большинство AHU не имеют post-heat, но для офисных систем
        # обычно target t_supply ≈ t_adp + 3°C, что и приняли.
        if current.t_c < t_supply - 0.1:
            after_postheat = heat(current, t_supply)
            proc.points["after_postheat"] = after_postheat
            proc.q_heater_kw = air_power_kw(m_kg_s, current, after_postheat)
            current = after_postheat
    else:
        # Зима / межсезонье: нагрев до t_supply_winter
        t_supply = load.t_supply_winter
        if current.t_c < t_supply:
            after_heater = heat(current, t_supply)
            proc.points["after_heater"] = after_heater
            proc.q_heater_kw = air_power_kw(m_kg_s, current, after_heater)
            current = after_heater

    # ---------- 5. Увлажнитель (опционально) ----------
    if humidifier_target_rh is not None and humidifier_target_rh > 0:
        W_target = humidity_ratio_from_rh(current.t_c, humidifier_target_rh,
                                            current.p)
        if W_target > current.W:
            if humidifier_kind == "steam":
                after_humid = humidify_steam(current, W_target)
            else:  # adiabatic
                after_humid = humidify_adiabatic(current,
                                                   humidifier_adiabatic_eff)
            proc.points["after_humid"] = after_humid
            proc.q_humidifier_kw = air_power_kw(m_kg_s, current, after_humid)
            proc.humidifier_water_kg_h = (
                (after_humid.W - current.W) * m_kg_s * 3600.0)
            current = after_humid

    # ---------- 6. Финальная точка ----------
    proc.points["supply"] = current

    return proc


# ============================================================================
# Удобный API: все три режима одной AHU
# ============================================================================

def compute_all_modes(load: "AHULoad",
                       params: "ProjectParameters",
                       **kwargs) -> Dict[str, AHUProcess]:
    """Возвращает {mode: AHUProcess} для winter/summer/transitional."""
    return {
        mode: compute_ahu_process(load, params, mode=mode, **kwargs)
        for mode in ("winter", "summer", "transitional")
    }
