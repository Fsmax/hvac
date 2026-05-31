# -*- coding: utf-8 -*-
"""Расчёт горячего водоснабжения (ГВС) по СП 30.13330.2020.

Считает для каждого помещения (на основе типа и количества людей) суточный
и часовой расход горячей воды, а также мощность нагрева. Затем агрегирует
в систему ГВС с возможностью задать тип нагревателя, рекуперацию,
циркуляцию и расчётный суточный график.

Норма расхода — по Приложению А СП 30.13330.2020 (Табл. А.2):

    Тип потребителя              q_сут (л/потребитель·сут, при t=60°C)
    ───────────────────────────────────────────────────────────────
    Жилая квартира с ваннами              105
    Жилая квартира без ванн               60
    Гостиница 3*–4* с ваннами             140
    Гостиница 5* (люкс)                   200
    Общежитие                             80
    Офис (адм.-быт.)                      7
    Школа                                 3
    Больница                              90
    Поликлиника                           5
    Магазин (продовольственный)           65 / на 1 рабочее место
    Ресторан / кафе                       12 / на 1 блюдо
    Спортзал                              30 / на 1 спортсм.
    Бассейн                               110 / на 1 спортсм.
    Парикмахерская                        56 / на 1 раб. место
    Прачечная                             40 / на 1 кг белья

Формулы:

    Q_сут (Вт·ч/сут) = V_сут · c · ρ · Δt
    где:
      V_сут   — суточный объём, м³/сут (= q_сут · N_людей / 1000)
      c       — теплоёмкость воды = 1.163 Вт·ч/(кг·К) = 4186 Дж/(кг·К)
      ρ       — плотность воды ≈ 1000 кг/м³
      Δt      — нагрев (t_гор − t_хол), обычно 60 − 5 = 55 К зимой, 60 − 15 = 45 К летом

    Q_час_max (Вт) = K_ч · Q_сут / (24 ч)
    где:
      K_ч     — коэффициент часовой неравномерности
                Жильё: 2.5, гостиницы: 2.0, офисы: 4.0, рестораны: 2.5

    Q_цирк (Вт) = 0.10 ÷ 0.30 · Q_час_max  — потери на циркуляцию

Источники: СП 30.13330.2020 (Приложения А, Б), СП 60.13330.2020.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Dict, List, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from hvac.project import HVACProject
    from hvac.models import Space


# ============================================================================
# Константы воды
# ============================================================================

WATER_SPECIFIC_HEAT_WH_KG_K = 1.163       # Вт·ч/(кг·К)
WATER_DENSITY_KG_M3 = 1000.0              # кг/м³
T_HOT_DEFAULT_C = 60.0                    # температура ГВС, °C (СП 30 п. 5.1.1)
T_COLD_WINTER_C = 5.0                     # холодная зимой, °C
T_COLD_SUMMER_C = 15.0                    # холодная летом, °C

# Удельная теплоёмкость воды на единицу объёма (Вт·ч / (м³·К))
WATER_SPECIFIC_HEAT_PER_M3_WH_K = WATER_SPECIFIC_HEAT_WH_KG_K * WATER_DENSITY_KG_M3
# = 1163 Вт·ч/(м³·К)


# ============================================================================
# Нормы расхода по типам помещений (СП 30.13330.2020 Прил. А, Табл. А.2)
# ============================================================================

@dataclass
class DHWNorm:
    """Норма расхода ГВС для одного типа потребителя."""
    norm_unit: str               # "person" — на человека, "m2" — на м², "fixed" — фикс.
    q_daily_l: float             # суточный расход, л в день на единицу
    q_hourly_l: float            # максимальный часовой, л/час на единицу
    k_hour: float = 2.5          # коэф. часовой неравномерности (если не задан q_hourly)
    note: str = ""


# Маппинг room_type → DHWNorm. На "потребителя" = на человека по СП 30.
DHW_NORMS: Dict[str, DHWNorm] = {
    "Жилая комната": DHWNorm(
        "person", q_daily_l=105.0, q_hourly_l=10.0, k_hour=2.5,
        note="СП 30.13330.2020 Табл. А.2: квартиры с ваннами 1500-1700 мм",
    ),
    "Гостиничный номер": DHWNorm(
        "person", q_daily_l=140.0, q_hourly_l=12.0, k_hour=2.0,
        note="СП 30.13330.2020 Табл. А.2: гостиницы 3*–4* с ваннами",
    ),
    "Офис": DHWNorm(
        "person", q_daily_l=7.0, q_hourly_l=2.0, k_hour=4.0,
        note="СП 30.13330.2020 Табл. А.2: административные здания",
    ),
    "Конференц-зал": DHWNorm(
        "person", q_daily_l=2.0, q_hourly_l=0.5, k_hour=4.0,
        note="СП 30.13330.2020: посетители общественных зданий",
    ),
    "Ресторан / кухня": DHWNorm(
        "m2", q_daily_l=15.0, q_hourly_l=3.0, k_hour=2.5,
        note="СП 30.13330.2020: рестораны/кафе, по площади залов",
    ),
    "Магазин / торговля": DHWNorm(
        "m2", q_daily_l=0.5, q_hourly_l=0.15, k_hour=4.0,
        note="СП 30.13330.2020: торговые залы (учитывается персонал)",
    ),
    "Санузел": DHWNorm(
        "fixed", q_daily_l=0.0, q_hourly_l=0.0,
        note="ГВС считается на помещения-источники потребления, "
             "санузел — точка водоразбора, в норме не считается отдельно",
    ),
    # Помещения без существенного ГВС:
    "Коридор":           DHWNorm("fixed", 0, 0, note="Без ГВС"),
    "Вестибюль":         DHWNorm("fixed", 0, 0, note="Без ГВС"),
    "Лестница":          DHWNorm("fixed", 0, 0, note="Без ГВС"),
    "Лифт / шахта":      DHWNorm("fixed", 0, 0, note="Без ГВС"),
    "Склад":             DHWNorm("fixed", 0, 0, note="Без ГВС"),
    "Технич. помещение": DHWNorm("fixed", 0, 0, note="Без ГВС"),
    "Гараж / автостоянка": DHWNorm("fixed", 0, 0, note="Без ГВС"),
    "Серверная":         DHWNorm("fixed", 0, 0, note="Без ГВС"),
    "Прочее":            DHWNorm("fixed", 0, 0, note="Уточнить норму вручную"),
}


# ============================================================================
# Структуры данных
# ============================================================================

@dataclass
class DHWDemand:
    """Расчёт ГВС для одного помещения."""
    space_id: str
    space_number: str
    space_name: str
    room_type: str
    base_unit: str              # "person" / "m2" / "fixed"
    base_qty: float             # сколько единиц (человек/м²)

    v_daily_m3: float = 0.0     # суточный объём ГВС, м³/сут
    v_hourly_m3: float = 0.0    # максимальный часовой, м³/час
    q_avg_w: float = 0.0        # средняя мощность нагрева, Вт
    q_peak_w: float = 0.0       # пиковая часовая мощность, Вт
    note: str = ""


@dataclass
class DHWSystem:
    """Система горячего водоснабжения (центральная или индивидуальная)."""
    name: str = "ГВС-1"                     # "ГВС-Гост", "ГВС-Офис"

    # Параметры нагревателя
    heater_type: str = "boiler_gas"         # boiler_gas / boiler_electric /
                                             # heat_pump / central / solar
    t_hot_c: float = 60.0                   # температура ГВС, °C
    t_cold_winter_c: float = 5.0            # холодная зимой
    t_cold_summer_c: float = 15.0           # холодная летом
    efficiency: float = 0.92                # КПД нагревателя

    # Циркуляция
    has_circulation: bool = True
    circulation_loss_fraction: float = 0.15  # доля от q_peak (10..30%)

    # Аккумуляция
    has_storage: bool = True
    storage_volume_m3: float = 0.0          # 0 = автоподбор
    storage_factor: float = 0.5             # часовой запас от суточного

    # Результаты (заполняются при расчёте)
    n_consumers: int = 0                    # сколько помещений обслуживает
    v_daily_total_m3: float = 0.0           # суммарный суточный
    v_hourly_max_m3: float = 0.0            # суммарный часовой пиковый
    q_avg_w: float = 0.0                    # средняя мощность ГВС
    q_peak_w: float = 0.0                   # пиковая мощность нагревателя
    q_with_circulation_w: float = 0.0       # с учётом циркуляции
    q_heater_size_w: float = 0.0            # подбор мощности нагревателя
    storage_recommended_m3: float = 0.0     # рекомендованный объём бака

    note: str = ""


# ============================================================================
# Расчёт
# ============================================================================

def calculate_space_demand(space: "Space",
                           norms: Optional[Dict[str, DHWNorm]] = None
                           ) -> DHWDemand:
    """Расчёт ГВС для одного помещения по нормам СП 30.13330.

    Если для типа помещения нет нормы, возвращает нулевую DHWDemand с note.
    """
    if norms is None:
        norms = DHW_NORMS
    norm = norms.get(space.room_type, norms["Прочее"])

    # Определяем базовую единицу
    if norm.norm_unit == "person":
        qty = float(space.occupancy_people)
    elif norm.norm_unit == "m2":
        qty = float(space.area_m2)
    else:  # fixed / без ГВС
        qty = 0.0

    v_daily_l = qty * norm.q_daily_l           # литры в сутки
    v_daily = v_daily_l / 1000.0               # м³/сут
    v_hourly_l = qty * norm.q_hourly_l          # литры в час (макс)
    v_hourly = v_hourly_l / 1000.0             # м³/час

    return DHWDemand(
        space_id=space.space_id,
        space_number=space.number,
        space_name=space.name,
        room_type=space.room_type,
        base_unit=norm.norm_unit,
        base_qty=qty,
        v_daily_m3=v_daily,
        v_hourly_m3=v_hourly,
        # Мощности заполнит calculate_dhw_system, т.к. нужен Δt
        q_avg_w=0.0, q_peak_w=0.0,
        note=norm.note,
    )


def power_for_volume(v_per_hour_m3: float, dt_k: float = 55.0) -> float:
    """Мощность нагрева воды, Вт, для заданного часового расхода и нагрева Δt."""
    return v_per_hour_m3 * WATER_SPECIFIC_HEAT_PER_M3_WH_K * dt_k


def calculate_demands(project: "HVACProject") -> List[DHWDemand]:
    """Расчёт ГВС для всех помещений проекта (без привязки к системе)."""
    demands: List[DHWDemand] = []
    for sp in project.spaces:
        d = calculate_space_demand(sp)
        # Считаем мощности по зимнему Δt (60 − 5 = 55)
        dt = T_HOT_DEFAULT_C - T_COLD_WINTER_C
        if d.v_daily_m3 > 0:
            # Средняя за сутки
            d.q_avg_w = (d.v_daily_m3 / 24.0) * WATER_SPECIFIC_HEAT_PER_M3_WH_K * dt
            # Пиковая часовая
            d.q_peak_w = d.v_hourly_m3 * WATER_SPECIFIC_HEAT_PER_M3_WH_K * dt
        demands.append(d)
    return demands


def aggregate_to_system(demands: List[DHWDemand],
                        system: DHWSystem) -> DHWSystem:
    """Агрегирует список потребностей в систему ГВС и рассчитывает её."""
    # Суммирование
    sys_v_daily = sum(d.v_daily_m3 for d in demands)
    sys_v_hourly = sum(d.v_hourly_m3 for d in demands)
    system.n_consumers = sum(1 for d in demands if d.v_daily_m3 > 0)
    system.v_daily_total_m3 = sys_v_daily
    system.v_hourly_max_m3 = sys_v_hourly

    # Мощности (по зимнему Δt — это даёт максимум)
    dt = system.t_hot_c - system.t_cold_winter_c
    # Средняя за сутки — на основе суммарного объёма
    system.q_avg_w = (sys_v_daily / 24.0) * WATER_SPECIFIC_HEAT_PER_M3_WH_K * dt
    # Пиковая часовая
    system.q_peak_w = sys_v_hourly * WATER_SPECIFIC_HEAT_PER_M3_WH_K * dt
    # С учётом циркуляции
    cirq = system.q_peak_w * system.circulation_loss_fraction \
        if system.has_circulation else 0.0
    system.q_with_circulation_w = system.q_peak_w + cirq
    # Мощность нагревателя с учётом КПД
    system.q_heater_size_w = system.q_with_circulation_w / max(system.efficiency, 0.01)

    # Рекомендованный объём аккумулятора (50% от часового пика + 25% сутки/24)
    # Это упрощённая формула; точный подбор по графику ГВС
    if system.has_storage:
        system.storage_recommended_m3 = max(
            0.5 * sys_v_hourly,
            sys_v_daily / 24.0,
        )
    else:
        system.storage_recommended_m3 = 0.0

    return system


def calculate_project_dhw(project: "HVACProject",
                          system_strategy: str = "single") -> Dict[str, DHWSystem]:
    """Полный расчёт ГВС для проекта.

    Параметры
    ---------
    system_strategy : "single" — одна система на весь проект,
                      "by_zone"  — отдельная система на каждую отопит. зону,
                      "by_type"  — отдельные системы для жилья/гостиниц/офиса.

    Возвращает
    ----------
    {name: DHWSystem} — словарь рассчитанных систем ГВС.
    """
    all_demands = calculate_demands(project)

    if system_strategy == "single":
        sys = DHWSystem(name="ГВС-Общая")
        # Используем уже существующую систему, если есть
        if "ГВС-Общая" in getattr(project, "dhw_systems", {}):
            sys = project.dhw_systems["ГВС-Общая"]
        active = [d for d in all_demands if d.v_daily_m3 > 0]
        aggregate_to_system(active, sys)
        return {sys.name: sys}

    if system_strategy == "by_type":
        # Группировка типов
        groups = {
            "ГВС-Жильё":     ["Жилая комната"],
            "ГВС-Гостиница": ["Гостиничный номер"],
            "ГВС-Офис":      ["Офис", "Конференц-зал"],
            "ГВС-Питание":   ["Ресторан / кухня"],
            "ГВС-Торговля":  ["Магазин / торговля"],
        }
        result: Dict[str, DHWSystem] = {}
        for sys_name, room_types in groups.items():
            sp_ids = {sp.space_id for sp in project.spaces
                      if sp.room_type in room_types}
            sub = [d for d in all_demands
                   if d.space_id in sp_ids and d.v_daily_m3 > 0]
            if not sub:
                continue
            existing = getattr(project, "dhw_systems", {}).get(sys_name)
            sys = existing if existing else DHWSystem(name=sys_name)
            aggregate_to_system(sub, sys)
            result[sys_name] = sys
        return result

    if system_strategy == "by_zone":
        # По полю system_heating (или зоне)
        by_zone: Dict[str, List[DHWDemand]] = {}
        sp_by_id = {sp.space_id: sp for sp in project.spaces}
        for d in all_demands:
            if d.v_daily_m3 <= 0:
                continue
            sp = sp_by_id.get(d.space_id)
            zone = (sp.system_heating if sp and sp.system_heating
                    else "Общая")
            by_zone.setdefault(zone, []).append(d)

        result = {}
        for zone, sub in by_zone.items():
            sys_name = f"ГВС-{zone}"
            existing = getattr(project, "dhw_systems", {}).get(sys_name)
            sys = existing if existing else DHWSystem(name=sys_name)
            aggregate_to_system(sub, sys)
            result[sys_name] = sys
        return result

    raise ValueError(f"Неизвестная стратегия: {system_strategy}")


def total_dhw_summary(systems: Dict[str, DHWSystem]) -> Dict:
    """Сводка по всем системам ГВС."""
    return {
        "n_systems": len(systems),
        "v_daily_total_m3": sum(s.v_daily_total_m3 for s in systems.values()),
        "v_hourly_max_m3": sum(s.v_hourly_max_m3 for s in systems.values()),
        "q_peak_total_w": sum(s.q_peak_w for s in systems.values()),
        "q_with_circulation_total_w": sum(s.q_with_circulation_w
                                          for s in systems.values()),
        "q_heater_total_w": sum(s.q_heater_size_w for s in systems.values()),
        "storage_total_m3": sum(s.storage_recommended_m3
                                for s in systems.values()),
    }
