# -*- coding: utf-8 -*-
"""Тесты детального расчёта оборудования (hvac.equipment_detail):
калорифер/охладитель (воздух+вода) и вентилятор (расход/давление/мощность/SFP)."""

import pytest

from hvac.project import HVACProject
from hvac.models import Space
from hvac.equipment import VentilationSystem, make_ventilation_defaults
from hvac.equipment_detail import (
    fan_power_kw, specific_fan_power, compute_equipment_detail,
)
from hvac.pipe_sizing import mass_flow_kg_h


def _add_space(p, sid, number, **kw):
    sp = Space(space_id=sid, number=number, name="Room", level="L1",
               area_m2=20.0, volume_m3=60.0, height_m=3.0, room_type="Офис")
    for k, v in kw.items():
        setattr(sp, k, v)
    p.spaces.append(sp)
    p._space_by_id[sid] = sp
    return sp


# --------------------------------------------------------------- вентилятор
class TestFanFormulas:
    def test_fan_power(self):
        # 3600 м³/ч = 1 м³/с, Δp=700 Па, η=0.7 → 1 кВт
        assert fan_power_kw(3600, 700, 0.7) == pytest.approx(1.0)

    def test_fan_power_zero(self):
        assert fan_power_kw(0, 700, 0.7) == 0.0
        assert fan_power_kw(3600, 0, 0.7) == 0.0
        assert fan_power_kw(3600, 700, 0) == 0.0

    def test_sfp(self):
        # SFP = Δp/η
        assert specific_fan_power(700, 0.7) == pytest.approx(1000.0)


# ------------------------------------------------------------- дефолты вида
class TestKindDefaults:
    def test_exhaust_defaults(self):
        d = make_ventilation_defaults("exhaust_fan")
        assert d["system_type"] == "exhaust"
        assert d["has_heater"] is False and d["has_cooler"] is False

    def test_ahu_defaults(self):
        d = make_ventilation_defaults("ahu")
        assert d["has_heater"] and d["has_cooler"]


# ----------------------------------------------------------------- AHU full
def _ahu_project():
    p = HVACProject()
    p.params.t_out_heating = -16.0
    p.params.t_out_cooling = 36.0
    p.ventilation_systems["PV-1"] = VentilationSystem(
        name="PV-1", kind="ahu", system_type="supply",
        has_recovery=True, recovery_efficiency_winter=0.6,
        recovery_efficiency_summer=0.5,
        t_supply_winter=20.0, t_supply_summer=16.0,
        fan_pressure_pa=700.0, fan_efficiency=0.7)
    for i in range(3):
        _add_space(p, str(i), f"R-{i}", system_ventilation="PV-1",
                   supply_m3h=1000.0, exhaust_m3h=900.0)
    return p


class TestAHUDetail:
    def test_heater_air_and_water(self):
        p = _ahu_project()
        det = compute_equipment_detail(p, "PV-1")
        assert det.kind == "ahu"
        assert det.supply_m3_h == 3000.0
        h = det.heater
        assert h is not None
        assert h.q_air_w > 0
        # вода: график по умолчанию 80/60 → Δt 20K
        assert h.water_supply_c == 80.0 and h.water_return_c == 60.0
        assert h.dt_water == 20.0
        assert h.water_flow_kg_h == pytest.approx(mass_flow_kg_h(h.q_air_w, 20.0))
        assert h.dn_mm > 0

    def test_cooler_present_in_summer(self):
        p = _ahu_project()
        det = compute_equipment_detail(p, "PV-1")
        c = det.cooler
        assert c is not None
        assert c.q_air_w > 0
        assert c.water_supply_c == 7.0 and c.water_return_c == 12.0

    def test_fan_supply(self):
        p = _ahu_project()
        det = compute_equipment_detail(p, "PV-1")
        f = det.fan_supply
        assert f is not None
        assert f.flow_m3_h == 3000.0
        assert f.pressure_pa == 700.0
        assert f.power_kw == pytest.approx(fan_power_kw(3000, 700, 0.7))
        assert f.pressure_source == "manual"

    def test_water_graph_from_circuit(self):
        p = _ahu_project()
        # привяжем калорифер к контуру 60/40
        p.add_zone_circuit("heating", "AHU-1", "Котёл", circuit_type="ahu_heater")
        p.heating_circuits["AHU-1"].t_supply = 60.0
        p.heating_circuits["AHU-1"].t_return = 40.0
        p.ventilation_systems["PV-1"].heating_circuit = "AHU-1"
        det = compute_equipment_detail(p, "PV-1")
        assert det.heater.dt_water == 20.0
        assert det.heater.graph_source == "circuit:AHU-1"
        assert det.heater.water_supply_c == 60.0


# --------------------------------------------------------------- exhaust fan
class TestExhaustFan:
    def test_fan_only_no_coils(self):
        p = HVACProject()
        p.ventilation_systems["V-1"] = VentilationSystem(
            **{"name": "V-1", **make_ventilation_defaults("exhaust_fan"),
               "fan_pressure_pa": 350.0, "fan_efficiency": 0.6})
        for i in range(2):
            _add_space(p, str(i), f"WC-{i}", system_ventilation="V-1",
                       supply_m3h=0.0, exhaust_m3h=150.0)
        det = compute_equipment_detail(p, "V-1")
        assert det.kind == "exhaust_fan"
        assert det.heater is None and det.cooler is None
        assert det.fan_exhaust is not None
        assert det.fan_exhaust.flow_m3_h == 300.0
        assert det.fan_supply is None

    def test_warns_no_flow(self):
        p = HVACProject()
        p.ventilation_systems["V-1"] = VentilationSystem(
            name="V-1", **make_ventilation_defaults("exhaust_fan"))
        det = compute_equipment_detail(p, "V-1")
        assert any("вытяж" in w.lower() for w in det.warnings)


# --------------------------------------------------------- supply fan no AHU
class TestSupplyFan:
    def test_no_cooler_when_disabled(self):
        p = HVACProject()
        p.params.t_out_heating = -16.0
        p.ventilation_systems["P-1"] = VentilationSystem(
            name="P-1", **{**make_ventilation_defaults("supply_fan"),
                           "has_heater": True, "t_supply_winter": 18.0})
        _add_space(p, "1", "R-1", system_ventilation="P-1",
                   supply_m3h=500.0, exhaust_m3h=0.0)
        det = compute_equipment_detail(p, "P-1")
        assert det.cooler is None          # has_cooler=False
        assert det.fan_supply is not None
        assert det.fan_supply.flow_m3_h == 500.0


def test_unknown_system_returns_none():
    p = HVACProject()
    assert compute_equipment_detail(p, "нет") is None
