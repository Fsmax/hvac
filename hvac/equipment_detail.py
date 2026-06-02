# -*- coding: utf-8 -*-
"""Детальный расчёт вентиляционного оборудования: калорифер/охладитель и вентилятор.

Собирает в одну подробную картину готовые расчёты:
- расходы и мощности секций — `hvac.ahu_load` (учитывает воздушное отопление);
- психрометрию по точкам и конденсат — `hvac.ahu_process`;
- водяную сторону теплообменников (G, DN, v) — `hvac.pipe_sizing`;
- мощность и SFP вентилятора — здесь (по расходу и давлению).

Для каждого оборудования (`VentilationSystem`) даёт:
  • калорифер (зима): воздух (t вход/выход, Δt, Q) + вода (график, Δt, G, DN);
  • охладитель (лето): то же + конденсат, явная/скрытая;
  • вентилятор: расход, давление, мощность мотора, удельная мощность (SFP).

Вид оборудования (`kind`) определяет, что считать: AHU — теплообменники +
приточный вентилятор; вытяжной/местный — только вытяжной вентилятор; приточный
вентилятор без AHU — вентилятор (+ калорифер, если включён).

Чистые функции над HVACProject — ядро без GUI. Панель «Системы» отображает.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple, TYPE_CHECKING

from hvac.equipment import VENT_KIND_SIDE, DEFAULT_FAN_PRESSURE_PA
from hvac.pipe_sizing import mass_flow_kg_h, volume_flow_m3_h, pick_dn

if TYPE_CHECKING:
    from hvac.project import HVACProject
    from hvac.ahu_load import AHULoad

# Плотность воды для пересчёта массового расхода в объёмный, кг/м³.
RHO_WATER_HOT = 977.0      # ~80°C (отопление)
RHO_WATER_COLD = 1000.0    # ~7°C (холод)

# Температурные графики по умолчанию, если теплообменник не привязан к контуру.
DEFAULT_HEATER_GRAPH = (80.0, 60.0)   # подача / обратка, °C
DEFAULT_COOLER_GRAPH = (7.0, 12.0)


@dataclass
class CoilDetail:
    """Детальный расчёт одного теплообменника (калорифер / охладитель)."""
    role: str                       # "heater" | "cooler"
    # Воздух
    q_air_w: float = 0.0            # полная мощность по воздуху, Вт
    q_sensible_w: float = 0.0      # явная (для охладителя)
    q_latent_w: float = 0.0        # скрытая (для охладителя)
    t_air_in: float = 0.0          # t воздуха на входе (после рекуператора)
    t_air_out: float = 0.0         # t воздуха на выходе (подача)
    dt_air: float = 0.0
    air_flow_m3_h: float = 0.0
    condensate_kg_h: float = 0.0   # конденсат (охладитель)
    # Вода
    water_supply_c: float = 0.0
    water_return_c: float = 0.0
    dt_water: float = 0.0
    water_flow_kg_h: float = 0.0
    water_flow_m3_h: float = 0.0
    dn_mm: int = 0
    water_velocity_m_s: float = 0.0
    graph_source: str = ""         # "circuit:<имя>" | "default"

    @property
    def q_air_kw(self) -> float:
        return self.q_air_w / 1000.0


@dataclass
class FanDetail:
    """Подбор вентилятора по расходу и давлению."""
    side: str                       # "supply" | "exhaust"
    flow_m3_h: float = 0.0
    pressure_pa: float = 0.0
    efficiency: float = 0.0
    power_kw: float = 0.0           # мощность на валу/моторе (с учётом КПД)
    sfp_w_m3_s: float = 0.0         # удельная мощность, Вт/(м³/с)
    pressure_source: str = ""       # "manual" | "network" | "default"


@dataclass
class EquipmentDetail:
    """Полный детальный расчёт одного вентиляционного оборудования."""
    name: str
    kind: str
    system_type: str
    n_spaces: int = 0
    supply_m3_h: float = 0.0
    exhaust_m3_h: float = 0.0
    heater: Optional[CoilDetail] = None
    cooler: Optional[CoilDetail] = None
    fan_supply: Optional[FanDetail] = None
    fan_exhaust: Optional[FanDetail] = None
    warnings: List[str] = field(default_factory=list)


# --------------------------------------------------------------------------- fan
def fan_power_kw(flow_m3_h: float, pressure_pa: float, efficiency: float) -> float:
    """Мощность вентилятора, кВт: P = Q·Δp / (1000·η), Q в м³/с."""
    if flow_m3_h <= 0 or pressure_pa <= 0 or efficiency <= 0:
        return 0.0
    return (flow_m3_h / 3600.0) * pressure_pa / (1000.0 * efficiency)


def specific_fan_power(pressure_pa: float, efficiency: float) -> float:
    """Удельная мощность SFP = Δp/η, Вт/(м³/с) (= Дж/м³)."""
    return pressure_pa / efficiency if efficiency > 0 else 0.0


def _fan_pressure(project, sysobj, kind: str) -> Tuple[float, str]:
    """Расчётное давление вентилятора и его источник.

    Приоритет: ручное (fan_pressure_pa>0) → аэродинамический расчёт сети
    (duct_networks_detailed) → дефолт по виду оборудования.
    """
    manual = getattr(sysobj, "fan_pressure_pa", 0.0) or 0.0
    if manual > 0:
        return manual, "manual"
    net = (getattr(project, "duct_networks_detailed", {}) or {}).get(sysobj.name)
    if net is not None and getattr(net, "fan_pressure_required_pa", 0.0) > 0:
        return net.fan_pressure_required_pa, "network"
    return DEFAULT_FAN_PRESSURE_PA.get(kind, 400.0), "default"


def _compute_fan(project, sysobj, side: str, flow_m3_h: float) -> FanDetail:
    kind = getattr(sysobj, "kind", "ahu")
    pressure, src = _fan_pressure(project, sysobj, kind)
    eff = getattr(sysobj, "fan_efficiency", 0.65) or 0.65
    return FanDetail(
        side=side, flow_m3_h=flow_m3_h, pressure_pa=pressure, efficiency=eff,
        power_kw=fan_power_kw(flow_m3_h, pressure, eff),
        sfp_w_m3_s=specific_fan_power(pressure, eff),
        pressure_source=src,
    )


# -------------------------------------------------------------------------- coil
def _water_graph(project, circuit_name: str, domain: str) -> Tuple[float, float, str]:
    """Температурный график теплоносителя/хладоносителя теплообменника.

    Из привязанного контура (если есть), иначе — дефолт по роли.
    Возвращает (t_подачи, t_обратки, источник).
    """
    if circuit_name:
        c = project.circuits_of(domain).get(circuit_name)
        if c is not None:
            return c.t_supply, c.t_return, f"circuit:{circuit_name}"
    ts, tr = (DEFAULT_HEATER_GRAPH if domain == "heating" else DEFAULT_COOLER_GRAPH)
    return ts, tr, "default"


def _heater_detail(project, sysobj, load: "AHULoad") -> Optional[CoilDetail]:
    if load.q_heater_w <= 0:
        return None
    ts, tr, src = _water_graph(project, getattr(sysobj, "heating_circuit", ""),
                               "heating")
    dt_w = abs(ts - tr)
    g_kg_h = mass_flow_kg_h(load.q_heater_w, dt_w)
    g_m3_h = volume_flow_m3_h(load.q_heater_w, dt_w, RHO_WATER_HOT)
    dn, _inner, v = pick_dn(g_m3_h, "steel")
    return CoilDetail(
        role="heater",
        q_air_w=load.q_heater_w,
        t_air_in=load.t_after_recovery_winter,
        t_air_out=load.t_supply_winter,
        dt_air=load.t_supply_winter - load.t_after_recovery_winter,
        air_flow_m3_h=load.supply_m3_h,
        water_supply_c=ts, water_return_c=tr, dt_water=dt_w,
        water_flow_kg_h=g_kg_h, water_flow_m3_h=g_m3_h,
        dn_mm=dn, water_velocity_m_s=v, graph_source=src,
    )


def _cooler_detail(project, sysobj, load: "AHULoad") -> Optional[CoilDetail]:
    if load.q_cooler_total_w <= 0:
        return None
    ts, tr, src = _water_graph(project, getattr(sysobj, "cooling_circuit", ""),
                               "cooling")
    dt_w = abs(ts - tr)
    g_kg_h = mass_flow_kg_h(load.q_cooler_total_w, dt_w)
    g_m3_h = volume_flow_m3_h(load.q_cooler_total_w, dt_w, RHO_WATER_COLD)
    dn, _inner, v = pick_dn(g_m3_h, "steel")
    # Конденсат: детальная психрометрия летнего режима.
    condensate = 0.0
    try:
        from hvac.ahu_process import compute_ahu_process
        proc = compute_ahu_process(load, project.params, mode="summer")
        condensate = proc.condensate_kg_h
    except Exception:
        condensate = 0.0
    return CoilDetail(
        role="cooler",
        q_air_w=load.q_cooler_total_w,
        q_sensible_w=load.q_cooler_sens_w,
        q_latent_w=load.q_cooler_lat_w,
        t_air_in=load.t_after_recovery_summer,
        t_air_out=load.t_supply_summer,
        dt_air=load.t_after_recovery_summer - load.t_supply_summer,
        air_flow_m3_h=load.supply_m3_h,
        condensate_kg_h=condensate,
        water_supply_c=ts, water_return_c=tr, dt_water=dt_w,
        water_flow_kg_h=g_kg_h, water_flow_m3_h=g_m3_h,
        dn_mm=dn, water_velocity_m_s=v, graph_source=src,
    )


def compute_equipment_detail(project: "HVACProject",
                             system_name: str) -> Optional[EquipmentDetail]:
    """Детальный расчёт одного вентиляционного оборудования по имени.

    Возвращает None, если системы нет. Для AHU/приточного вентилятора считает
    теплообменники (если включены) и приточный вентилятор; для вытяжного/местного
    — только вытяжной вентилятор.
    """
    from hvac.ahu_load import aggregate_ahus

    sysobj = project.ventilation_systems.get(system_name)
    if sysobj is None:
        return None
    kind = getattr(sysobj, "kind", "ahu")
    side = VENT_KIND_SIDE.get(kind, "supply")

    load = aggregate_ahus(project).get(system_name)
    supply = load.supply_m3_h if load else 0.0
    exhaust = load.exhaust_m3_h if load else 0.0
    n_spaces = load.n_spaces if load else 0

    det = EquipmentDetail(
        name=system_name, kind=kind,
        system_type=getattr(sysobj, "system_type", ""),
        n_spaces=n_spaces, supply_m3_h=supply, exhaust_m3_h=exhaust,
    )

    # Теплообменники — только для приточной стороны и если есть расход притока.
    if side == "supply" and load is not None and supply > 0:
        if getattr(sysobj, "has_heater", True):
            det.heater = _heater_detail(project, sysobj, load)
        if getattr(sysobj, "has_cooler", True):
            det.cooler = _cooler_detail(project, sysobj, load)

    # Вентилятор: со стороны потока этого оборудования.
    if side == "supply":
        if supply > 0:
            det.fan_supply = _compute_fan(project, sysobj, "supply", supply)
        else:
            det.warnings.append("Нет приточного расхода (назначьте помещения)")
        # Приточно-вытяжная AHU имеет и вытяжной вентилятор.
        if getattr(sysobj, "system_type", "") == "supply_exhaust" and exhaust > 0:
            det.fan_exhaust = _compute_fan(project, sysobj, "exhaust", exhaust)
    else:  # exhaust / local_exhaust
        if exhaust > 0:
            det.fan_exhaust = _compute_fan(project, sysobj, "exhaust", exhaust)
        else:
            det.warnings.append("Нет вытяжного расхода (назначьте помещения)")

    return det


def compute_all_equipment_detail(project: "HVACProject"
                                 ) -> Dict[str, EquipmentDetail]:
    """Детальный расчёт всех вентиляционных систем проекта."""
    out: Dict[str, EquipmentDetail] = {}
    for name in project.ventilation_systems:
        det = compute_equipment_detail(project, name)
        if det is not None:
            out[name] = det
    return out
