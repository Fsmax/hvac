# -*- coding: utf-8 -*-
"""Энергетический паспорт здания / годовое потребление энергии
по СП 50.13330.2012 (Приложение Г) и СП 23-101-2004.

Считает годовые удельные расходы тепловой энергии на:
  • отопление и вентиляцию (qh_у, кВт·ч/(м²·год))
  • охлаждение (упрощённо, по часам выше t_бал летом)
  • ГВС (если рассчитано)

И присваивает класс энергоэффективности по СП 50 Табл. 14 (А, B, C, D, E).

Методика — упрощённый bin-метод на основе ГСОП (градусо-сутки отопительного
периода):

    Q_отоп_год = q_расч · (ГСОП · 24) / (t_в - t_н_расч) · k_рег
    
где k_рег = коэффициент регулирования (0.8 для ИТП с погодной автоматикой,
          1.0 без регулирования)

Расход на нагрев инфильтрации/вентиляции рассчитан в q_расч (он включён
в теплопотери). Бытовые/солнечные внутр. поступления (СП 50 п. 5.3):

    q_внутр = 17 Вт/м² × ΔZ = 17 × (1 - z_отоп) Вт/м² усреднённо
            или просто 5..15 Вт/м² (СП 50: 17 для жилья, 10-12 для общ.)

Эффективная теплопроизводительность системы отопления:
    Q_год_итого = Q_отоп - η_внутр · Q_внутр

где η_внутр = коэф. использования внутренних теплопоступлений 0.7..0.9.

Класс по удельному показателю:
    A+   : -60% от нормы
    A    : -50%
    B    : -30..-50
    C    : ±15% от нормы (норма СП 50 Табл. 9 для региона)
    D    : +15..+50
    E    : +50% и более

Для упрощения используем удельный qh_у (Вт·ч/(м²·год)) и сравнение с
нормативной таблицей.
"""

from __future__ import annotations
from dataclasses import dataclass
from typing import Dict, List, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from hvac.project import HVACProject


# ============================================================================
# Нормативные данные СП 50.13330 Табл. 14
# ============================================================================

# Удельная теплозащитная характеристика, Вт/(м²·К) — справочно
# (не используется напрямую, для проверки соответствия СП 50)

# Класс энергоэффективности по отклонению от базового q_h:
ENERGY_CLASS_THRESHOLDS = [
    # (lower_pct, upper_pct, class_letter, description)
    (-1000, -60, "A++", "Очень высокий, оптимальная экономия"),
    (-60,    -50, "A+",  "Высочайший"),
    (-50,    -30, "A",   "Очень высокий"),
    (-30,    -15, "B+",  "Высокий"),
    (-15,     -5, "B",   "Повышенный"),
    (-5,      +5, "C+",  "Нормальный"),
    (+5,     +15, "C",   "Соответствует нормам"),
    (+15,    +30, "C-",  "Допустимый"),
    (+30,    +50, "D",   "Пониженный (требуется доутепление)"),
    (+50,  +1000, "E",   "Очень низкий (несоответствие нормам)"),
]


# Базовые нормативные удельные показатели qh_у, кВт·ч/(м²·год)
# Примерные значения по СП 50 для жилых зданий разной этажности
# при ГСОП = 4000 (приведённые к 1 м² отапл. площади):
BASE_HEATING_NORMS_KWH_M2: Dict[str, float] = {
    # тип здания → норма при ГСОП 4000
    "жилое 1-3 этажа":   180,
    "жилое 4-5 этажей":  130,
    "жилое 6-9 этажей":  120,
    "жилое 10-12":       110,
    "жилое 12+":         105,
    "офис":              140,
    "гостиница":         160,
    "магазин":           130,
    "школа":             120,
    "общественное":      130,   # дефолт
}


# ============================================================================
# Структура результата
# ============================================================================

@dataclass
class EnergyPassport:
    """Энергопаспорт здания (упрощённый, по СП 50.13330 Приложение Г)."""

    # ===== Исходные =====
    project_name: str = ""
    city: str = ""
    gsop_18: float = 0.0                  # ГСОП база +18, °C·сут
    t_out_heating: float = 0.0            # расчётная зимняя
    total_area_m2: float = 0.0            # площадь всех помещений
    total_volume_m3: float = 0.0          # объём
    n_spaces: int = 0
    building_type: str = "общественное"

    # ===== Расчётные нагрузки =====
    q_peak_heating_w: float = 0.0         # пиковая мощность отопления, Вт
    q_peak_cooling_w: float = 0.0         # пиковая мощность охлаждения, Вт
    q_peak_ventilation_heating_w: float = 0.0  # пиковая от приточек зима
    q_peak_dhw_w: float = 0.0             # пиковая ГВС

    # ===== Годовое потребление =====
    z_heating_days: float = 0.0           # продолжительность отопит. сезона, сут
    t_avg_heating: float = 0.0            # средняя за период, °C
    e_heating_kwh_year: float = 0.0       # тепло на отопление за год
    e_ventilation_kwh_year: float = 0.0   # нагрев приточки за год
    e_cooling_kwh_year: float = 0.0       # электроэнергия на охлаждение, кВт·ч/год
    e_dhw_kwh_year: float = 0.0           # ГВС за год
    e_internal_gains_kwh_year: float = 0.0  # внутренние теплопоступления
    e_solar_gains_kwh_year: float = 0.0   # солнечные

    # ===== Удельные =====
    qh_specific_kwh_m2: float = 0.0       # удельный расход тепла, кВт·ч/(м²·год)
    qh_normative_kwh_m2: float = 0.0      # нормативный по СП 50
    deviation_percent: float = 0.0        # отклонение, %
    energy_class: str = ""
    energy_class_description: str = ""

    # ===== Параметры регулирования =====
    k_regulation: float = 1.0             # КПД регулирования (ИТП с авт. — 0.85)
    k_internal_use: float = 0.8           # доля использования внутр. теплопост.
    internal_gain_w_m2: float = 10.0      # ср. внутр. теплопост., Вт/м²

    # ===== ШНҚ 2.01.18-24 (Узбекистан) — нормативный q_ov =====
    n_floors: int = 1                     # этажность здания (по уровням)
    shnq_category: str = ""               # категория ШНҚ Табл.1-3
    q_design_specific_w_m2: float = 0.0   # удельная расч. мощность отопл.+вент., Вт/м²
    q_ov_normative_w_m2: float = 0.0      # норматив ШНҚ q_ov, Вт/м² (0 — нет данных)
    shnq_compliant: Optional[bool] = None  # q_design ≤ q_ov? None — нет норматива

    note: str = ""


# ============================================================================
# Расчёт
# ============================================================================

def heating_season_duration(t_out_avg_monthly: List[float],
                            t_threshold: float = 8.0) -> int:
    """Возвращает приблизительную длительность отопительного сезона, сут.

    Дефолт по СП 131.13330 п. 3.13 — начало/конец сезона при tн ≤ 8°C
    (для жилых +10°C). Использует месячные ср. температуры, если есть.
    Без данных по месяцам — оценка по ГСОП.
    """
    if not t_out_avg_monthly:
        return 0
    days_per_month = 30
    return sum(days_per_month for t in t_out_avg_monthly if t < t_threshold)


def estimate_heating_season_from_gsop(gsop: float, t_in: float = 20.0,
                                      t_threshold: float = 8.0) -> Dict:
    """Оценка z_от и t_от из ГСОП.

    ГСОП = z_от · (t_в − t_от_ср)
    где z_от — длительность сезона (сут), t_от_ср — ср. наружная за сезон.

    Эмпирическая формула, откалибрована на справочные данные СП 131.13330
    Приложение Б (Ташкент 132 сут / Москва 214 / Новосибирск 230 / Якутск 254):
    
        z_от ≈ 280 · (1 − exp(−ГСОП / 3500))
    
    Затем t_от_ср = t_в − ГСОП/z_от.
    Точность ±5% для городов СНГ с ГСОП 1500..10000.
    """
    import math
    if gsop <= 0:
        return {"z_days": 0, "t_avg": 0.0}
    z_days = 280.0 * (1.0 - math.exp(-gsop / 3500.0))
    # Ограничение здравым смыслом
    z_days = max(60.0, min(z_days, 300.0))
    t_avg = t_in - (gsop / z_days)
    return {"z_days": round(z_days), "t_avg": round(t_avg, 1)}


def annual_heating_energy_kwh(q_peak_w: float, t_in: float, t_out_design: float,
                              z_days: float, t_avg_season: float,
                              k_reg: float = 1.0) -> float:
    """Годовое потребление тепла на отопление, кВт·ч/год.

    Метод: бин-метод на основе средней наружной за сезон.

        Q_год = q_peak · ((t_в − t_от_ср) / (t_в − t_н_расч)) · z_от · 24 ч · k_reg

    Параметры
    ---------
    q_peak_w     : расчётная (пиковая) нагрузка на отопление, Вт
    t_in         : средняя расчётная внутренняя
    t_out_design : расчётная зимняя наружная (СП 131, обесп. 0.92)
    z_days       : длительность отопит. сезона, сут
    t_avg_season : средняя наружная за сезон, °C
    k_reg        : коэф. регулирования (1.0 без автоматики, 0.85 с ИТП)
    """
    if q_peak_w <= 0 or (t_in - t_out_design) <= 0:
        return 0.0
    load_factor = (t_in - t_avg_season) / (t_in - t_out_design)
    hours = z_days * 24.0
    return q_peak_w * load_factor * hours * k_reg / 1000.0  # Вт → кВт·ч


def annual_cooling_energy_kwh(q_peak_w: float, climate_t_cool: float,
                              t_in_cool: float, hours_per_year: float = 1000.0
                              ) -> float:
    """Годовое потребление электроэнергии на охлаждение, кВт·ч/год.

    Сильно упрощённая оценка: q_peak × часы работы в году × средний коэф.
    нагрузки 0.5 / EER. EER = 3.0 принят по умолчанию (типовой чиллер).

    hours_per_year — типичные часы работы кондиц. сезона:
       400  для холодного климата (Москва)
       800  для умеренного
      1200  для тёплого/жаркого (Ташкент)
    """
    if q_peak_w <= 0:
        return 0.0
    load_factor = 0.5  # средняя загрузка чиллеров в сезон
    eer = 3.0          # типовой EER
    # Электроэнергия на холодоснабжение
    return (q_peak_w * load_factor * hours_per_year) / eer / 1000.0


def hours_per_year_cooling(climate_t_cool: float) -> float:
    """Оценка длительности сезона охлаждения, ч/год."""
    # Эмпирика: тёплый климат (Ташкент 36°C) — ~1500 ч, умеренный — ~800
    if climate_t_cool >= 34:
        return 1500.0
    if climate_t_cool >= 30:
        return 1000.0
    if climate_t_cool >= 26:
        return 600.0
    return 300.0


def normative_qh(building_type: str, gsop: float,
                 base_norms: Optional[Dict[str, float]] = None) -> float:
    """Нормативный удельный qh_у по СП 50 Табл. 14.

    Базовая норма дана при ГСОП=4000. Корректировка линейная по ГСОП.
    Это упрощение — реальная таблица имеет ступенчатые границы.
    """
    if base_norms is None:
        base_norms = BASE_HEATING_NORMS_KWH_M2
    base = base_norms.get(building_type, base_norms["общественное"])
    if gsop <= 0:
        return base
    return base * (gsop / 4000.0)


def energy_class_for_deviation(deviation_percent: float) -> Dict[str, str]:
    """Класс энергоэффективности по отклонению от нормы."""
    for lo, hi, cls, desc in ENERGY_CLASS_THRESHOLDS:
        if lo <= deviation_percent < hi:
            return {"class": cls, "description": desc}
    return {"class": "?", "description": "Вне диапазона"}


def detect_building_type(project: "HVACProject") -> str:
    """Эвристика для определения типа здания по составу помещений."""
    total_area = sum(sp.area_m2 for sp in project.spaces)
    if total_area <= 0:
        return "общественное"

    # Площадь по типам
    by_type: Dict[str, float] = {}
    for sp in project.spaces:
        by_type[sp.room_type] = by_type.get(sp.room_type, 0) + sp.area_m2

    hotel_area = by_type.get("Гостиничный номер", 0)
    office_area = by_type.get("Офис", 0) + by_type.get("Конференц-зал", 0)
    res_area = by_type.get("Жилая комната", 0)
    shop_area = by_type.get("Магазин / торговля", 0)

    # Доминирующий тип
    shares = [(hotel_area, "гостиница"),
              (office_area, "офис"),
              (res_area, "жилое 4-5 этажей"),
              (shop_area, "магазин")]
    shares.sort(reverse=True)
    if shares[0][0] / total_area >= 0.30:
        return shares[0][1]
    return "общественное"


def calculate_passport(project: "HVACProject",
                       building_type: Optional[str] = None,
                       k_regulation: float = 1.0,
                       k_internal_use: float = 0.8,
                       internal_gain_w_m2: float = 10.0
                       ) -> EnergyPassport:
    """Строит энергетический паспорт здания.

    Параметры
    ---------
    building_type     : тип здания (см. BASE_HEATING_NORMS_KWH_M2). Если None,
                        определяется автоматически.
    k_regulation      : коэф. регулирования системы отопления (1.0 без авт.,
                        0.85 при ИТП с погодной автоматикой)
    k_internal_use    : коэф. использования внутренних теплопоступлений
                        (СП 50 — 0.8 для типичных режимов)
    internal_gain_w_m2 : усреднённые внутренние теплопоступления, Вт/м²
                        (СП 50: 17 для жилья, 10 для общественных)
    """
    params = project.params
    total_area = sum(sp.area_m2 for sp in project.spaces)
    total_volume = sum(sp.volume_m3 for sp in project.spaces)

    if building_type is None:
        building_type = detect_building_type(project)

    # Длительность сезона
    season = estimate_heating_season_from_gsop(
        params.gsop_18, t_in=20.0, t_threshold=8.0,
    )

    # Пиковые
    q_peak_heating = sum(sp.heat_loss_w for sp in project.spaces)
    q_peak_cooling = sum(sp.heat_gain_w for sp in project.spaces)

    # Нагрузка от вентиляции зимой (нагрев приточки) — если AHU посчитаны
    q_peak_vent = 0.0
    for sys in getattr(project, "ahu_loads", {}).values():
        q_peak_vent += sys.get("q_heater_w", 0.0)

    # Пиковая ГВС
    q_peak_dhw = sum(s.q_with_circulation_w
                     for s in getattr(project, "dhw_systems", {}).values())

    # ===== ШНҚ 2.01.18-24: норматив q_ov [Вт/м²] (основная норма УзР) =====
    # Сравниваем удельную расчётную мощность отопл.+вент. (Вт/м²) с
    # нормативом ШНҚ Табл.1-3 по типу здания, этажности и градус-суткам.
    from hvac.catalogs.shnq_energy import (
        normative_q_ov_shnq, building_type_to_shnq)
    n_floors = len({sp.level for sp in project.spaces if sp.level}) or 1
    shnq_cat = building_type_to_shnq(building_type)
    q_design_specific = ((q_peak_heating + q_peak_vent) / total_area
                         if total_area > 0 else 0.0)
    # ШНҚ Dd считается от tв (≈20°C), а проектный ГСОП — от +18°C.
    # Поправка базы: Dd_shnq = ГСОП_18 + z·(tв − 18). Период по ШНҚ —
    # tср.сут ≤ 10°C (порог сезона приближаем оценкой по ГСОП).
    t_in_shnq = 20.0
    dd_shnq = params.gsop_18 + season["z_days"] * (t_in_shnq - 18.0)
    q_ov_norm = normative_q_ov_shnq(shnq_cat, n_floors, dd_shnq) or 0.0
    shnq_compliant = (q_design_specific <= q_ov_norm) if q_ov_norm > 0 else None

    # ====== Годовые ======
    e_heating = annual_heating_energy_kwh(
        q_peak_heating, t_in=20.0, t_out_design=params.t_out_heating,
        z_days=season["z_days"], t_avg_season=season["t_avg"],
        k_reg=k_regulation,
    )
    e_vent = annual_heating_energy_kwh(
        q_peak_vent, t_in=20.0, t_out_design=params.t_out_heating,
        z_days=season["z_days"], t_avg_season=season["t_avg"],
        k_reg=k_regulation,
    )

    hours_cool = hours_per_year_cooling(params.t_out_cooling)
    e_cooling = annual_cooling_energy_kwh(
        q_peak_cooling, params.t_out_cooling, 24.0, hours_cool,
    )

    # ГВС работает круглый год: 24 × 365 × средн. загрузка 0.4
    e_dhw = 0.0
    for sys in getattr(project, "dhw_systems", {}).values():
        # Сред. суточная * 365
        if sys.v_daily_total_m3 > 0:
            # Используется зимний Δt — упрощение
            dt = sys.t_hot_c - sys.t_cold_winter_c
            # 1163 Вт·ч/(м³·К) × м³/сут × 365 сут = Вт·ч/год → кВт·ч
            e_dhw += (sys.v_daily_total_m3 * 1163.0 * dt * 365.0 / 1000.0
                      / max(sys.efficiency, 0.01))

    # Внутренние теплопоступления (Вт/м² × часы сезона × площадь)
    e_internal = (internal_gain_w_m2 * total_area
                  * season["z_days"] * 24.0 / 1000.0)

    # Скорректированное потребление
    e_heating_net = max(e_heating - k_internal_use * e_internal, 0.0)

    # Удельный показатель
    qh = e_heating_net / total_area if total_area > 0 else 0.0
    qh_norm = normative_qh(building_type, params.gsop_18)
    deviation = (qh - qh_norm) / qh_norm * 100.0 if qh_norm > 0 else 0.0
    cls_info = energy_class_for_deviation(deviation)

    return EnergyPassport(
        project_name=params.project_name,
        city=params.city,
        gsop_18=params.gsop_18,
        t_out_heating=params.t_out_heating,
        total_area_m2=total_area,
        total_volume_m3=total_volume,
        n_spaces=len(project.spaces),
        building_type=building_type,

        q_peak_heating_w=q_peak_heating,
        q_peak_cooling_w=q_peak_cooling,
        q_peak_ventilation_heating_w=q_peak_vent,
        q_peak_dhw_w=q_peak_dhw,

        z_heating_days=season["z_days"],
        t_avg_heating=season["t_avg"],
        e_heating_kwh_year=e_heating_net,
        e_ventilation_kwh_year=e_vent,
        e_cooling_kwh_year=e_cooling,
        e_dhw_kwh_year=e_dhw,
        e_internal_gains_kwh_year=e_internal,

        qh_specific_kwh_m2=qh,
        qh_normative_kwh_m2=qh_norm,
        deviation_percent=deviation,
        energy_class=cls_info["class"],
        energy_class_description=cls_info["description"],

        k_regulation=k_regulation,
        k_internal_use=k_internal_use,
        internal_gain_w_m2=internal_gain_w_m2,

        n_floors=n_floors,
        shnq_category=shnq_cat,
        q_design_specific_w_m2=q_design_specific,
        q_ov_normative_w_m2=q_ov_norm,
        shnq_compliant=shnq_compliant,
    )
