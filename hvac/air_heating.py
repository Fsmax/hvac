# -*- coding: utf-8 -*-
"""Воздушное отопление / охлаждение: подбор расхода приточки по нагрузке.

Для помещений с флагом `air_heating` / `air_cooling` (см. models.Space) тепло
или холод подаётся самим приточным воздухом, без радиаторов/фанкойлов. Тогда
расход приточки должен перекрыть нагрузку помещения, а не только дать свежий
воздух:

    L = Q / (0.28 · ρ · c · Δt),   Δt = |t_подачи − t_помещения|   (м³/ч)

где Q — теплопотери (зимой) или теплопоступления (летом), а температура подачи
ограничена параметрами обслуживающей установки (СП 60.13330):

    - отопление: подача ≤ t_supply_air_heating (≈40°C) — против пересушивания
      и перегрева верхней зоны (стратификации);
    - охлаждение: подача ≥ t_supply_air_cooling (≈14-16°C) — против сквозняка
      и выпадения конденсата на решётках.

Итоговый расход помещения = max(вентиляционная норма, расход на отопление,
расход на охлаждение). `apply_air_heating` поднимает до него `Space.supply_m3h`,
после чего мощность калорифера/охладителя AHU (hvac.ahu_load) считается уже на
увеличенный расход и автоматически включает и вентиляцию, и нагрузку помещения.

Чистые функции над HVACProject — physics берётся из готовых полей расчёта
(`heat_loss_w` / `heat_gain_w` из recalculate, вентиляция из calculate_ventilation).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Tuple, TYPE_CHECKING

from hvac.ahu_load import C_AIR_KJ_KG_K
from hvac.engine.base import air_density

if TYPE_CHECKING:
    from hvac.project import HVACProject
    from hvac.models import Space
    from hvac.equipment import VentilationSystem

# Дефолты, если помещение не привязано к установке (нет system_ventilation).
DEFAULT_T_SUPPLY_AIR_HEATING = 40.0
DEFAULT_T_SUPPLY_AIR_COOLING = 16.0


@dataclass
class AirRoomLoad:
    """Подбор расхода приточки по нагрузке для одного помещения."""
    space_id: str
    number: str
    name: str
    ahu: str                       # имя обслуживающей VentilationSystem ("" если нет)
    air_heating: bool
    air_cooling: bool

    t_room_heat: float = 20.0      # tвн зимой
    t_room_cool: float = 24.0      # tвн летом
    t_supply_heat: float = 0.0     # эффективная подача AHU зимой
    t_supply_cool: float = 0.0     # эффективная подача AHU летом
    q_heat_w: float = 0.0          # теплопотери
    q_cool_w: float = 0.0          # теплопоступления

    vent_supply_m3h: float = 0.0   # вентиляционная норма (база)
    req_heat_m3h: float = 0.0      # расход для перекрытия теплопотерь воздухом
    req_cool_m3h: float = 0.0      # расход для перекрытия теплопоступлений
    design_supply_m3h: float = 0.0 # итоговый = max из трёх
    governed_by: str = "ventilation"  # "ventilation" | "heating" | "cooling"
    warnings: List[str] = field(default_factory=list)


def required_air_flow(q_w: float, dt_k: float, rho: float,
                      c_kj_kg_k: float = C_AIR_KJ_KG_K) -> float:
    """Расход воздуха (м³/ч), перекрывающий нагрузку Q (Вт) при перепаде Δt (К).

    Обратная формула к мощности нагрева потока: Q = 0.28·L·ρ·c·Δt.
    Возвращает 0, если нагрузки нет или перепад непригоден (Δt ≤ 0).
    """
    if q_w <= 0 or dt_k <= 0 or rho <= 0:
        return 0.0
    return q_w / (0.28 * rho * c_kj_kg_k * dt_k)


def _ahu_caps(ahu: "VentilationSystem | None") -> Tuple[float, float]:
    """Предельные температуры подачи установки (для подбора расхода)."""
    if ahu is None:
        return DEFAULT_T_SUPPLY_AIR_HEATING, DEFAULT_T_SUPPLY_AIR_COOLING
    return (getattr(ahu, "t_supply_air_heating", DEFAULT_T_SUPPLY_AIR_HEATING),
            getattr(ahu, "t_supply_air_cooling", DEFAULT_T_SUPPLY_AIR_COOLING))


def effective_ahu_supply_temps(ahu: "VentilationSystem | None",
                               spaces: List["Space"],
                               rho_winter: float,
                               rho_summer: float) -> Tuple[float, float]:
    """Расчётные температуры подачи установки (зима, лето) для расчёта
    мощности калорифера/охладителя.

    Если установка обслуживает воздушно-отапливаемые помещения, зимняя подача
    рассчитывается как МИНИМАЛЬНО необходимая, чтобы перекрыть их суммарную
    нагрузку при уже подобранном расходе:

        t_подачи = t_помещения + ΣQ / (0.28·ρ·c·L_возд),   ≤ t_supply_air_heating

    Так калорифер не завышается: его мощность = «нагрев приточки до t помещения»
    плюс фактическая нагрузка помещений (а не нагрев всего расхода до предела).
    Аналогично летняя подача опускается ровно настолько, насколько нужно для
    перекрытия теплопоступлений, но не ниже t_supply_air_cooling.

    Если воздушного режима нет — возвращаются нейтральные вентиляционные
    t_supply_winter / t_supply_summer. Плотности (rho_winter/rho_summer)
    передаются из расчёта AHU, чтобы совпадать с формулой мощности.
    """
    t_cap_h, t_cap_c = _ahu_caps(ahu)
    neutral_w = ahu.t_supply_winter if ahu is not None else 18.0
    neutral_s = ahu.t_supply_summer if ahu is not None else 18.0
    t_w, t_s = neutral_w, neutral_s

    # ----- зима: воздушное отопление -----
    heat_rooms = [sp for sp in spaces
                  if getattr(sp, "air_heating", False) and sp.heat_loss_w > 0]
    if heat_rooms:
        l_heat = sum(sp.supply_m3h for sp in heat_rooms)
        sum_q = sum(sp.heat_loss_w for sp in heat_rooms)
        t_room = sum(sp.t_in_heat for sp in heat_rooms) / len(heat_rooms)
        if l_heat > 0 and rho_winter > 0:
            rise = sum_q / (0.28 * l_heat * rho_winter * C_AIR_KJ_KG_K)
            t_w = min(t_cap_h, t_room + rise)
        else:
            t_w = t_cap_h

    # ----- лето: воздушное охлаждение -----
    cool_rooms = [sp for sp in spaces
                  if getattr(sp, "air_cooling", False) and sp.heat_gain_w > 0]
    if cool_rooms:
        l_cool = sum(sp.supply_m3h for sp in cool_rooms)
        sum_q = sum(sp.heat_gain_w for sp in cool_rooms)
        t_room = sum(sp.t_in_cool for sp in cool_rooms) / len(cool_rooms)
        if l_cool > 0 and rho_summer > 0:
            drop = sum_q / (0.28 * l_cool * rho_summer * C_AIR_KJ_KG_K)
            t_s = max(t_cap_c, t_room - drop)
        else:
            t_s = t_cap_c

    return t_w, t_s


def _vent_base(sp: "Space") -> float:
    """Вентиляционный расход помещения (без надбавки воздушного отопления).

    Берётся из ventilation_breakdown (сырой выход движка вентиляции), чтобы
    результат был идемпотентным при повторном вызове apply_air_heating —
    даже если supply_m3h уже был поднят. Для помещений с ручной правкой
    вентиляции уважаем текущее supply_m3h.
    """
    if getattr(sp, "vent_user_modified", False):
        return sp.supply_m3h
    br = getattr(sp, "ventilation_breakdown", None)
    if br and "supply_m3h" in br:
        return br.get("supply_m3h", 0.0)
    return sp.supply_m3h


def compute_air_heating(project: "HVACProject") -> Dict[str, AirRoomLoad]:
    """Подбирает расход приточки по нагрузке для всех помещений с флагами
    air_heating / air_cooling. Не мутирует проект — только считает.

    Возвращает {space_id: AirRoomLoad} ТОЛЬКО для помеченных помещений.
    """
    # Предельные температуры подачи кэшируем по установке (один воздуховод —
    # одна температура подачи на все её помещения).
    caps_cache: Dict[str, Tuple[float, float]] = {}

    def _caps(ahu_name: str) -> Tuple[float, float]:
        if ahu_name not in caps_cache:
            ahu = project.ventilation_systems.get(ahu_name) if ahu_name else None
            caps_cache[ahu_name] = _ahu_caps(ahu)
        return caps_cache[ahu_name]

    result: Dict[str, AirRoomLoad] = {}
    for sp in project.spaces:
        ah = bool(getattr(sp, "air_heating", False))
        ac = bool(getattr(sp, "air_cooling", False))
        if not (ah or ac):
            continue

        ahu_name = getattr(sp, "system_ventilation", "")
        # Подбор расхода — по предельному перепаду (подача ограничена
        # t_supply_air_heating/cooling), это даёт минимальный расход.
        t_sup_w, t_sup_s = _caps(ahu_name)

        row = AirRoomLoad(
            space_id=sp.space_id, number=sp.number, name=sp.name,
            ahu=ahu_name, air_heating=ah, air_cooling=ac,
            t_room_heat=sp.t_in_heat, t_room_cool=sp.t_in_cool,
            t_supply_heat=t_sup_w, t_supply_cool=t_sup_s,
            q_heat_w=sp.heat_loss_w, q_cool_w=sp.heat_gain_w,
            vent_supply_m3h=_vent_base(sp),
        )
        if not ahu_name:
            row.warnings.append("Не назначена приточная установка")

        # ----- расход на воздушное отопление -----
        if ah:
            dt_h = t_sup_w - sp.t_in_heat
            if dt_h <= 0:
                row.warnings.append(
                    f"Подача {t_sup_w:.0f}°C ≤ tвн {sp.t_in_heat:.0f}°C — "
                    f"воздушное отопление невозможно")
            else:
                rho_h = air_density(sp.t_in_heat)
                row.req_heat_m3h = required_air_flow(sp.heat_loss_w, dt_h, rho_h)

        # ----- расход на воздушное охлаждение -----
        if ac:
            dt_c = sp.t_in_cool - t_sup_s
            if dt_c <= 0:
                row.warnings.append(
                    f"Подача {t_sup_s:.0f}°C ≥ tвн {sp.t_in_cool:.0f}°C — "
                    f"воздушное охлаждение невозможно")
            else:
                rho_c = air_density(sp.t_in_cool)
                row.req_cool_m3h = required_air_flow(sp.heat_gain_w, dt_c, rho_c)

        # ----- итоговый расход = max -----
        candidates = [("ventilation", row.vent_supply_m3h),
                      ("heating", row.req_heat_m3h),
                      ("cooling", row.req_cool_m3h)]
        row.governed_by, row.design_supply_m3h = max(candidates, key=lambda t: t[1])
        result[sp.space_id] = row

    return result


def apply_air_heating(project: "HVACProject") -> int:
    """Синхронизирует Space.supply_m3h с воздушным режимом помещений.

    - помещения с air_heating/air_cooling: расход поднимается до перекрывающего
      нагрузку (= max(вентиляция, отопление, охлаждение));
    - помещения БЕЗ флагов: расход возвращается к вентиляционному (снимаем
      ранее наложенную надбавку, если режим выключили).

    Помещения с ручной правкой расхода (vent_user_modified) не трогаются.
    Идемпотентно: база берётся из ventilation_breakdown, а не из уже
    поднятого supply_m3h. Возвращает количество поднятых помещений.
    """
    loads = compute_air_heating(project)
    boosted = 0
    for sp in project.spaces:
        if getattr(sp, "vent_user_modified", False):
            continue
        row = loads.get(sp.space_id)
        new_supply = None
        if row is not None and row.design_supply_m3h > 0:
            # Воздушный режим включён — расход по нагрузке.
            new_supply = row.design_supply_m3h
            if new_supply > sp.supply_m3h + 1e-6:
                boosted += 1
        elif row is None:
            # Режим выключен — вернуть вентиляционный расход (если был поднят).
            base = _vent_base(sp)
            if base and abs(sp.supply_m3h - base) > 1e-6:
                new_supply = base
        if new_supply is not None:
            sp.supply_m3h = new_supply
            if sp.volume_m3 > 0:
                sp.ach_calculated = sp.supply_m3h / sp.volume_m3
    return boosted
