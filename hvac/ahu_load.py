# -*- coding: utf-8 -*-
"""Расчёт нагрузок приточных установок (AHU) — структурированная агрегация.

Каждая VentilationSystem обслуживает группу помещений (по sp.system_ventilation).
Этот модуль:

  1. Группирует помещения по AHU и суммирует Σ supply_m3h / Σ exhaust_m3h.
  2. Считает требуемую мощность калорифера зимой с учётом рекуператора:
        t' = t_нар + η_з · (t_возд_из_помещения − t_нар)   (после рекуператора)
        Q_калор = 0.28 · L · ρ · c · (t_подачи − t')       (Вт)
  3. Считает мощность охладителя летом (явная + скрытая) с учётом рекуператора.
  4. Возвращает структурированные AHULoad с разбивкой.

Полученные нагрузки далее используются в pipe_sizing для добавления
AHU как виртуальных потребителей соответствующих контуров ИТП.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Dict, List, TYPE_CHECKING

from hvac.engine.base import air_density

if TYPE_CHECKING:
    from hvac.project import HVACProject
    from hvac.equipment import VentilationSystem


# Удельная теплоёмкость воздуха, кДж/(кг·К)
C_AIR_KJ_KG_K = 1.005

# Скрытая теплота парообразования воды, кДж/кг (при ~20°C)
H_FG_KJ_KG = 2500.0


@dataclass
class AHULoad:
    """Расчётные нагрузки одной приточной установки."""
    system_name: str                       # имя AHU ("ПВ-1", "П1")

    # Помещения и расходы
    n_spaces: int = 0
    supply_m3_h: float = 0.0
    exhaust_m3_h: float = 0.0

    # Температуры расчётные (из ProjectParameters и VentilationSystem)
    t_outdoor_winter: float = 0.0
    t_outdoor_summer: float = 0.0
    t_supply_winter: float = 0.0
    t_supply_summer: float = 0.0
    t_indoor_avg_winter: float = 20.0      # средняя tвн зимой (для рекуператора)
    t_indoor_avg_summer: float = 24.0      # средняя tвн летом

    # Рекуператор
    has_recovery: bool = False
    recovery_eff_winter: float = 0.0
    recovery_eff_summer: float = 0.0
    t_after_recovery_winter: float = 0.0   # t после рекуператора зимой
    t_after_recovery_summer: float = 0.0   # летом

    # Нагрузки
    q_heater_w: float = 0.0                # калорифер зимой, Вт
    q_cooler_sens_w: float = 0.0           # охладитель — явная, Вт
    q_cooler_lat_w: float = 0.0            # охладитель — скрытая (осушение), Вт
    q_cooler_total_w: float = 0.0          # полная нагрузка охладителя, Вт

    # Привязка к контурам ИТП (для гидравлического расчёта)
    heating_circuit: str = ""              # имя HeatingCircuit
    cooling_circuit: str = ""              # имя CoolingCircuit

    # Помещения, обслуживаемые установкой (для контроля)
    served_space_ids: List[str] = field(default_factory=list)

    @property
    def q_heater_kw(self) -> float:
        return self.q_heater_w / 1000.0

    @property
    def q_cooler_total_kw(self) -> float:
        return self.q_cooler_total_w / 1000.0


def _avg_indoor_temperature(spaces: List, mode: str = "heat") -> float:
    """Средняя расчётная температура внутреннего воздуха по обслуж. помещениям.
    Нужна для оценки температуры на выходе рекуператора.

    mode: 'heat' — зимой (t_in_heat), 'cool' — летом (t_in_cool).
    """
    if not spaces:
        return 20.0 if mode == "heat" else 24.0
    attr = "t_in_heat" if mode == "heat" else "t_in_cool"
    vals = [getattr(sp, attr, 20.0) for sp in spaces]
    return sum(vals) / len(vals)


def calculate_ahu_load(ahu: "VentilationSystem",
                       spaces: List,
                       params) -> AHULoad:
    """Считает нагрузку одной установки.

    params : ProjectParameters (для t_out_heating/cooling, w_out_summer_g_kg)
    spaces : список Space, обслуживаемых этой AHU
    """
    L_supply = sum(getattr(sp, "supply_m3h", 0.0) for sp in spaces)
    L_exhaust = sum(getattr(sp, "exhaust_m3h", 0.0) for sp in spaces)

    # Воздушное отопление/охлаждение: если установка обслуживает помещения с
    # флагом air_heating/air_cooling, температура подачи рассчитывается как
    # минимально необходимая для перекрытия их нагрузки при подобранном расходе
    # (огранич. t_supply_air_heating/cooling). Иначе — нейтральная вентиляц.
    # Плотности считаем заранее и переиспользуем в формулах мощности ниже.
    from hvac.air_heating import effective_ahu_supply_temps
    rho_w = air_density(params.t_out_heating)
    rho_s = air_density(params.t_out_cooling)
    t_supply_winter, t_supply_summer = effective_ahu_supply_temps(
        ahu, spaces, rho_w, rho_s)

    load = AHULoad(
        system_name=ahu.name,
        n_spaces=len(spaces),
        supply_m3_h=L_supply,
        exhaust_m3_h=L_exhaust,
        t_outdoor_winter=params.t_out_heating,
        t_outdoor_summer=params.t_out_cooling,
        t_supply_winter=t_supply_winter,
        t_supply_summer=t_supply_summer,
        t_indoor_avg_winter=_avg_indoor_temperature(spaces, "heat"),
        t_indoor_avg_summer=_avg_indoor_temperature(spaces, "cool"),
        has_recovery=ahu.has_recovery,
        recovery_eff_winter=ahu.recovery_efficiency_winter,
        recovery_eff_summer=ahu.recovery_efficiency_summer,
        heating_circuit=getattr(ahu, "heating_circuit", ""),
        cooling_circuit=getattr(ahu, "cooling_circuit", ""),
        served_space_ids=[getattr(sp, "space_id", "") for sp in spaces],
    )

    if L_supply <= 0:
        return load

    # ===== Калорифер (зимой) =====
    # t после рекуператора: t' = t_нар + η·(t_возд − t_нар)
    eta_w = ahu.recovery_efficiency_winter if ahu.has_recovery else 0.0
    t_after = (params.t_out_heating
               + eta_w * (load.t_indoor_avg_winter - params.t_out_heating))
    load.t_after_recovery_winter = t_after

    dt_h = t_supply_winter - t_after
    if dt_h > 0 and getattr(ahu, "has_heater", True):
        load.q_heater_w = 0.28 * L_supply * rho_w * C_AIR_KJ_KG_K * dt_h

    # ===== Охладитель (летом) =====
    eta_s = ahu.recovery_efficiency_summer if ahu.has_recovery else 0.0
    t_after_s = (params.t_out_cooling
                 + eta_s * (load.t_indoor_avg_summer - params.t_out_cooling))
    load.t_after_recovery_summer = t_after_s

    has_cooler = getattr(ahu, "has_cooler", True)
    dt_c = t_after_s - t_supply_summer
    if dt_c > 0 and has_cooler:
        load.q_cooler_sens_w = 0.28 * L_supply * rho_s * C_AIR_KJ_KG_K * dt_c

    # Скрытая нагрузка (осушение): по разнице влагосодержаний на ВХОДЕ в
    # охладитель (после рекуператора) и на выходе.
    # Упрощённо: считаем, что роторный рекуператор частично снимает влагу,
    # пластинчатый — нет. Для оценки берём то же η.
    w_after_recovery = (params.w_out_summer_g_kg
                        - eta_s * (params.w_out_summer_g_kg
                                   - params.w_in_summer_g_kg))
    dw = w_after_recovery - ahu.w_supply_summer
    if dw > 0 and has_cooler:
        load.q_cooler_lat_w = 0.83 * L_supply * dw

    load.q_cooler_total_w = load.q_cooler_sens_w + load.q_cooler_lat_w
    return load


def aggregate_ahus(project: "HVACProject") -> Dict[str, AHULoad]:
    """Считает нагрузки для всех приточных установок проекта.

    Возвращает {system_name: AHULoad}.
    Также записывает в project.ahu_loads dict-форму (для обратной
    совместимости с UI/JSON, где раньше использовался плоский dict).
    """
    from collections import defaultdict
    result: Dict[str, AHULoad] = {}

    by_system: Dict[str, List] = defaultdict(list)
    for sp in project.spaces:
        if sp.system_ventilation:
            by_system[sp.system_ventilation].append(sp)

    for ahu_name, ahu in project.ventilation_systems.items():
        spaces = by_system.get(ahu_name, [])
        load = calculate_ahu_load(ahu, spaces, project.params)
        result[ahu_name] = load

    # Совместимость: project.ahu_loads — dict-форма (как было).
    project.ahu_loads = {
        name: {
            "n_spaces": load.n_spaces,
            "supply_m3h": load.supply_m3_h,
            "exhaust_m3h": load.exhaust_m3_h,
            "t_supply_winter": load.t_supply_winter,
            "t_supply_summer": load.t_supply_summer,
            "has_recovery": load.has_recovery,
            "recovery_w": load.recovery_eff_winter,
            "recovery_s": load.recovery_eff_summer,
            "t_after_recovery_winter": load.t_after_recovery_winter,
            "t_after_recovery_summer": load.t_after_recovery_summer,
            "q_heater_w": load.q_heater_w,
            "q_cooler_sens_w": load.q_cooler_sens_w,
            "q_cooler_lat_w": load.q_cooler_lat_w,
            "q_cooler_total_w": load.q_cooler_total_w,
            "heating_circuit": load.heating_circuit,
            "cooling_circuit": load.cooling_circuit,
        }
        for name, load in result.items()
    }

    return result


def summary_by_circuit(loads: Dict[str, AHULoad]
                       ) -> Dict[str, Dict[str, float]]:
    """Группирует нагрузки AHU по контурам ИТП.

    Возвращает {circuit_name: {q_heating_w, q_cooling_w, ahus: [...]}}.
    Используется для проверки, что суммарная нагрузка калориферов всех
    AHU не превышает мощность котла, питающего контур.
    """
    from collections import defaultdict
    out: Dict[str, Dict] = defaultdict(
        lambda: {"q_heating_w": 0.0, "q_cooling_w": 0.0, "ahus": []})

    for name, load in loads.items():
        if load.heating_circuit and load.q_heater_w > 0:
            out[load.heating_circuit]["q_heating_w"] += load.q_heater_w
            out[load.heating_circuit]["ahus"].append(name)
        if load.cooling_circuit and load.q_cooler_total_w > 0:
            out[load.cooling_circuit]["q_cooling_w"] += load.q_cooler_total_w
            if name not in out[load.cooling_circuit]["ahus"]:
                out[load.cooling_circuit]["ahus"].append(name)

    return dict(out)
