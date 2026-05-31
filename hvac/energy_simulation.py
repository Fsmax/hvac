# -*- coding: utf-8 -*-
"""8760-часовая симуляция энергопотребления здания.

Для каждого помещения проекта строится годовой почасовой профиль
(8760 значений) тепловой нагрузки на отопление и охлаждение с учётом:

    • синтетического профиля наружной температуры из ГСОП и расчётных T;
    • расписания присутствия людей и оборудования (по типу здания);
    • базовых внутренних тепловыделений (освещение / люди / оборудование);
    • инфильтрации (зимой/летом);
    • запаздывания массы здания (упрощённо — экспоненциальное сглаживание).

Получаем годовые показатели:
    • E_heat — потребление на отопление, кВт·ч/год
    • E_cool — потребление на охлаждение, кВт·ч/год
    • Q_peak_heat / Q_peak_cool — расчётные пики
    • h_at_peak — сколько часов в году нагрузка ≥ 90% от пика
    • удельные показатели на 1 м² (для энергопаспорта)

Применяется для:
    • уточнённого энергопаспорта (СП 50.13330 Прил. Г);
    • оценки эффективности рекуперации, экономайзера, ночного отступления;
    • расчёта окупаемости энергоэффективных решений.

Не претендует на точность EnergyPlus / TRNSYS — это инженерная оценка
с погрешностью ±10..15% от подробной модели.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Dict, List, Optional, TypedDict, TYPE_CHECKING

if TYPE_CHECKING:
    from hvac.project import HVACProject
    from hvac.models import Space


class _SpaceParams(TypedDict):
    """Предрасчитанные коэффициенты помещения для почасовой симуляции."""
    space: "Space"
    u_loss: float
    u_gain: float
    q_internal: float
    schedule: str


# ============================================================================
# Расписания (фактор присутствия / нагрузки от 0..1 по часу суток)
# ============================================================================

# Будни / выходные — отдельно. Индекс 0..23 = часы 00:00..23:00.
SCHEDULES: Dict[str, Dict[str, Optional[List[float]]]] = {
    # Жилое: дома утром, вечером и ночью
    "residential": {
        "weekday": [
            1.0, 1.0, 1.0, 1.0, 1.0, 1.0,   # 0-5: ночь
            0.9, 0.7, 0.4, 0.3,             # 6-9: подъём / уход
            0.3, 0.3, 0.4, 0.4, 0.4, 0.5,   # 10-15: день
            0.7, 0.9, 1.0, 1.0, 1.0, 1.0,   # 16-21: возвращение
            1.0, 1.0,                       # 22-23: вечер
        ],
        "weekend": [1.0] * 24,
    },
    # Офис: будни 8-18, выходные пусто
    "office": {
        "weekday": [
            0.05, 0.05, 0.05, 0.05, 0.05, 0.05,
            0.10, 0.30, 0.80, 0.95, 1.00, 1.00,
            0.70, 0.95, 1.00, 1.00, 0.95, 0.50,
            0.20, 0.10, 0.05, 0.05, 0.05, 0.05,
        ],
        "weekend": [0.05] * 24,
    },
    # Школа: будни 8-15, ниже офиса вечером
    "school": {
        "weekday": [
            0.0, 0.0, 0.0, 0.0, 0.0, 0.0,
            0.1, 0.4, 0.95, 1.0, 1.0, 1.0,
            1.0, 1.0, 0.9, 0.4, 0.1, 0.05,
            0.0, 0.0, 0.0, 0.0, 0.0, 0.0,
        ],
        "weekend": [0.0] * 24,
    },
    # Гостиница: пик ночью, провал днём
    "hotel": {
        "weekday": [
            0.95, 0.95, 0.95, 0.95, 0.95, 0.9,
            0.8, 0.7, 0.5, 0.4, 0.3, 0.3,
            0.4, 0.4, 0.4, 0.4, 0.5, 0.7,
            0.8, 0.9, 0.95, 0.95, 0.95, 0.95,
        ],
        "weekend": None,        # копируем weekday
    },
    # Магазин / ТРЦ: 10-22
    "mall": {
        "weekday": [
            0.0, 0.0, 0.0, 0.0, 0.0, 0.0,
            0.05, 0.10, 0.30, 0.50, 0.90, 1.0,
            1.0, 1.0, 1.0, 1.0, 1.0, 1.0,
            1.0, 1.0, 1.0, 0.80, 0.30, 0.05,
        ],
        "weekend": None,
    },
    # Технические — постоянно
    "industrial": {
        "weekday": [1.0] * 24,
        "weekend": [1.0] * 24,
    },
}


def schedule_for_room_type(room_type: str) -> str:
    """Возвращает ключ расписания по типу помещения."""
    mapping = {
        "Жилая комната": "residential",
        "Спальня": "residential",
        "Гостиничный номер": "hotel",
        "Офис": "office",
        "Конференц-зал": "office",
        "Класс / аудитория": "school",
        "Магазин / торговля": "mall",
        "Ресторан / кухня": "mall",
        "Спортзал": "school",
        "Серверная": "industrial",
        "Технич. помещение": "industrial",
        "Гараж / автостоянка": "industrial",
    }
    return mapping.get(room_type, "office")


def occupancy_factor(schedule_key: str, hour_of_year: int) -> float:
    """Множитель занятости в час hour_of_year (0..8759)."""
    schedules = SCHEDULES.get(schedule_key) or SCHEDULES["office"]
    day_of_year = hour_of_year // 24
    hour_of_day = hour_of_year % 24
    # 365 дней: считаем понедельники с 0-го дня (упрощение).
    is_weekend = (day_of_year % 7) >= 5
    profile = (schedules.get("weekend") if is_weekend
                else schedules.get("weekday"))
    if not profile:                       # weekend=None → берём будни
        profile = schedules.get("weekday")
    if not profile:
        return 0.0
    return float(profile[hour_of_day])


# ============================================================================
# Синтез почасового профиля наружной температуры
# ============================================================================

# Северное полушарие: пик летнего тепла ≈ 15 июля (~196-й день),
# пик зимы ≈ 15 января (~15-й день).
SUMMER_PEAK_DAY = 196
WINTER_PEAK_DAY = 15
HOURS_IN_YEAR = 8760


def synth_outdoor_temperature(
    t_winter: float, t_summer: float, daily_amplitude: float,
    hour_of_year: int,
) -> float:
    """Синтетическая модель T_наружного воздуха по часу года.

    Сезонная составляющая — синусоида от t_winter к t_summer.
    Суточная — синусоида амплитудой daily_amplitude/2 вокруг сезонного.
    Пик суточный в 15:00, минимум в 5:00.
    """
    day = hour_of_year // 24
    hour = hour_of_year % 24

    # Сезонная составляющая
    t_mean_summer = t_summer - daily_amplitude * 0.3       # средне-летняя
    t_mean_winter = t_winter + daily_amplitude * 0.2       # средне-зимняя
    season_amp = (t_mean_summer - t_mean_winter) / 2.0
    season_mid = (t_mean_summer + t_mean_winter) / 2.0
    season_phase = 2.0 * math.pi * (day - SUMMER_PEAK_DAY) / 365.0
    t_season = season_mid + season_amp * math.cos(season_phase)

    # Суточная составляющая
    day_phase = 2.0 * math.pi * (hour - 15) / 24.0
    t = t_season + (daily_amplitude / 2.0) * math.cos(day_phase)
    return t


# ============================================================================
# Результат симуляции
# ============================================================================

@dataclass
class EnergySimulationResult:
    """Годовой результат симуляции для всего проекта."""
    # Помещения
    n_spaces: int = 0
    total_area_m2: float = 0.0

    # Энергопотребление
    e_heat_kwh: float = 0.0
    e_cool_kwh: float = 0.0
    e_heat_kwh_m2: float = 0.0
    e_cool_kwh_m2: float = 0.0
    e_total_kwh_m2: float = 0.0

    # Пики
    q_peak_heat_w: float = 0.0
    q_peak_cool_w: float = 0.0
    hour_of_peak_heat: int = 0
    hour_of_peak_cool: int = 0

    # Часы работы на пике (Q ≥ 0.9·Q_peak)
    hours_at_peak_heat: int = 0
    hours_at_peak_cool: int = 0
    # Сезонные часы работы (когда Q > 0)
    heating_hours: int = 0
    cooling_hours: int = 0

    # Профиль по часам (опционально — для графика). 8760 значений каждый.
    hourly_q_heat_w: Optional[List[float]] = None
    hourly_q_cool_w: Optional[List[float]] = None
    hourly_t_out_c: Optional[List[float]] = None


# ============================================================================
# Главная функция
# ============================================================================

def simulate_year(
    project: "HVACProject",
    *,
    keep_hourly: bool = False,
    thermal_mass_tau_h: float = 12.0,
    heating_setpoint_offset: float = 0.0,
    cooling_setpoint_offset: float = 0.0,
) -> EnergySimulationResult:
    """Прогоняет 8760-часовую симуляцию для всего проекта.

    Параметры
    ---------
    keep_hourly             : сохранить почасовые массивы в результате
                              (8760 значений × 3 — занимает ~70 КБ ОЗУ).
    thermal_mass_tau_h      : постоянная времени тепловой массы здания (часы).
                              5-8 ч — лёгкое здание, 12-20 ч — массивное.
    heating_setpoint_offset : сдвиг уставки отопления на ночь (например -2°C
                              экономит ~5-8% при включённом расписании).
    cooling_setpoint_offset : сдвиг уставки охлаждения (например +2°C ночью).
    """
    p = project.params
    spaces = [sp for sp in project.spaces if sp.area_m2 > 0]
    if not spaces:
        return EnergySimulationResult()

    result = EnergySimulationResult(
        n_spaces=len(spaces),
        total_area_m2=sum(sp.area_m2 for sp in spaces),
    )

    # Расчётные удельные значения для каждого помещения (для линейного
    # масштабирования с T_out)
    space_params: List[_SpaceParams] = []
    for sp in spaces:
        # K·F·(t_внутр − t_наружн) — линейная зависимость от ΔT.
        # Используем результат уже выполненного расчёта на расчётные условия:
        #   heat_loss_w / (t_in − t_out_winter) = коэффициент потерь
        dt_winter = max(sp.t_in_heat - p.t_out_heating, 1e-3)
        u_loss_w_k = sp.heat_loss_w / dt_winter
        # Для охлаждения: учтём ΔT и солнце. heat_gain_w на расчётные.
        # У нас sensible + latent. Упрощённо считаем sensible линейной по ΔT,
        # а latent — постоянной (от внутренних источников + влажности).
        dt_summer = max(p.t_out_cooling - sp.t_in_cool, 1e-3)
        u_gain_w_k = sp.heat_gain_sensible_w / dt_summer
        q_internal_const = (sp.heat_gain_w - sp.heat_gain_sensible_w
                             - u_gain_w_k * dt_summer) + (
            sp.area_m2 * sp.lighting_w_m2 * 0.5    # средняя освещ.
            + sp.area_m2 * sp.equipment_w_m2 * 0.5
            + sp.occupancy_people * 100.0          # 100 Вт/чел
        )
        space_params.append({
            "space": sp,
            "u_loss": u_loss_w_k,
            "u_gain": u_gain_w_k,
            "q_internal": q_internal_const,
            "schedule": schedule_for_room_type(sp.room_type),
        })

    # Постоянная времени → коэф. сглаживания (RC-фильтр)
    alpha = 1.0 - math.exp(-1.0 / max(thermal_mass_tau_h, 0.5))

    q_heat_smooth = [0.0] * len(spaces)
    q_cool_smooth = [0.0] * len(spaces)

    hourly_t = [0.0] * HOURS_IN_YEAR if keep_hourly else None
    hourly_h = [0.0] * HOURS_IN_YEAR if keep_hourly else None
    hourly_c = [0.0] * HOURS_IN_YEAR if keep_hourly else None

    e_heat_total = 0.0
    e_cool_total = 0.0
    q_peak_h = 0.0
    q_peak_c = 0.0
    hour_peak_h = 0
    hour_peak_c = 0
    heating_hours = 0
    cooling_hours = 0

    for h in range(HOURS_IN_YEAR):
        t_out = synth_outdoor_temperature(
            p.t_out_heating, p.t_out_cooling, p.daily_amplitude, h,
        )
        if hourly_t is not None:
            hourly_t[h] = t_out

        sum_q_heat = 0.0
        sum_q_cool = 0.0

        for i, params in enumerate(space_params):
            sp = params["space"]
            occ = occupancy_factor(params["schedule"], h)

            # Уставка с учётом ночного отступления
            t_in_heat = sp.t_in_heat + (
                heating_setpoint_offset if occ < 0.3 else 0.0)
            t_in_cool = sp.t_in_cool + (
                cooling_setpoint_offset if occ < 0.3 else 0.0)

            # Базовая «инстантная» нагрузка
            q_h_raw = max(0.0,
                           params["u_loss"] * (t_in_heat - t_out)
                           - params["q_internal"] * occ * 0.7)
            q_c_raw = max(0.0,
                           params["u_gain"] * (t_out - t_in_cool)
                           + params["q_internal"] * occ)

            # Сглаживание через тепловую массу (RC-фильтр)
            q_heat_smooth[i] += alpha * (q_h_raw - q_heat_smooth[i])
            q_cool_smooth[i] += alpha * (q_c_raw - q_cool_smooth[i])

            sum_q_heat += q_heat_smooth[i]
            sum_q_cool += q_cool_smooth[i]

        e_heat_total += sum_q_heat       # Вт·ч (×1 ч = Вт·ч)
        e_cool_total += sum_q_cool
        if sum_q_heat > q_peak_h:
            q_peak_h = sum_q_heat
            hour_peak_h = h
        if sum_q_cool > q_peak_c:
            q_peak_c = sum_q_cool
            hour_peak_c = h
        if sum_q_heat > 100:
            heating_hours += 1
        if sum_q_cool > 100:
            cooling_hours += 1
        if hourly_h is not None:
            hourly_h[h] = sum_q_heat
        if hourly_c is not None:
            hourly_c[h] = sum_q_cool

    # Часы работы на пике
    if hourly_h is not None and q_peak_h > 0:
        threshold = q_peak_h * 0.9
        result.hours_at_peak_heat = sum(1 for v in hourly_h if v >= threshold)
    if hourly_c is not None and q_peak_c > 0:
        threshold = q_peak_c * 0.9
        result.hours_at_peak_cool = sum(1 for v in hourly_c if v >= threshold)

    result.e_heat_kwh = e_heat_total / 1000.0
    result.e_cool_kwh = e_cool_total / 1000.0
    result.q_peak_heat_w = q_peak_h
    result.q_peak_cool_w = q_peak_c
    result.hour_of_peak_heat = hour_peak_h
    result.hour_of_peak_cool = hour_peak_c
    result.heating_hours = heating_hours
    result.cooling_hours = cooling_hours

    if result.total_area_m2 > 0:
        result.e_heat_kwh_m2 = result.e_heat_kwh / result.total_area_m2
        result.e_cool_kwh_m2 = result.e_cool_kwh / result.total_area_m2
        result.e_total_kwh_m2 = (result.e_heat_kwh + result.e_cool_kwh
                                  ) / result.total_area_m2

    if keep_hourly:
        result.hourly_q_heat_w = hourly_h
        result.hourly_q_cool_w = hourly_c
        result.hourly_t_out_c = hourly_t

    return result


def hour_to_iso_datetime(hour_of_year: int, year: int = 2026) -> str:
    """Форматирует час года в дату-время для отчёта."""
    from datetime import datetime, timedelta
    base = datetime(year, 1, 1)
    return (base + timedelta(hours=hour_of_year)).strftime("%Y-%m-%d %H:%M")
