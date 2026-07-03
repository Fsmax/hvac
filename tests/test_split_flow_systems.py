# -*- coding: utf-8 -*-
"""Раздельная привязка притока и вытяжки помещения к двум системам.

Space.system_supply / system_exhaust переопределяют, какой системе принадлежит
каждый расход (пусто = system_ventilation). Случай: техпомещение обслуживают
две независимые установки — отдельная приточная + отдельный вытяжной
вентилятор (трансформаторные, котельные).
"""

import os
import tempfile

import pytest

from hvac.equipment import VentilationSystem
from hvac.models import Space
from hvac.project import HVACProject


def _project_with_pair():
    """Комната 1000/1000 на вытяжной В-1, приток отдан приточной П-1."""
    project = HVACProject()
    project.params.t_out_heating = -15
    project.params.t_out_cooling = 36
    project.params.w_out_summer_g_kg = 8.0
    sp = Space(space_id="1", number="B01-135", name="BOILER PUMP", level="B1",
               area_m2=50, volume_m3=150, height_m=3, room_type="Технич. помещение",
               supply_m3h=1000, exhaust_m3h=1000,
               system_ventilation="В-1", system_supply="П-1")
    project.spaces.append(sp)
    project._space_by_id[sp.space_id] = sp
    project.ventilation_systems["В-1"] = VentilationSystem(
        name="В-1", kind="exhaust_fan", system_type="exhaust",
        has_heater=False, has_cooler=False)
    project.ventilation_systems["П-1"] = VentilationSystem(
        name="П-1", kind="ahu", system_type="supply",
        has_heater=True, has_cooler=True)
    return project, sp


class TestEffectiveAttribution:

    def test_space_properties(self):
        sp = Space(space_id="1", number="X", name="X", level="L1",
                   area_m2=10, volume_m3=30,
                   system_ventilation="ПВ-1")
        assert sp.vent_system_supply == "ПВ-1"
        assert sp.vent_system_exhaust == "ПВ-1"
        sp.system_supply = "П-1"
        assert sp.vent_system_supply == "П-1"
        assert sp.vent_system_exhaust == "ПВ-1"
        sp.system_exhaust = "В-1"
        assert sp.vent_system_exhaust == "В-1"


class TestSplitAHULoads:

    def test_flows_split_between_pair(self):
        project, _ = _project_with_pair()
        loads = project.calculate_ahu_loads()
        assert loads["П-1"]["supply_m3h"] == 1000
        assert loads["П-1"]["exhaust_m3h"] == 0
        assert loads["В-1"]["supply_m3h"] == 0
        assert loads["В-1"]["exhaust_m3h"] == 1000
        # комната числится за обеими установками
        assert loads["П-1"]["n_spaces"] == 1
        assert loads["В-1"]["n_spaces"] == 1

    def test_heater_counted_on_supply_system(self):
        """Калорифер притока считается на приточной, а не теряется на вытяжной.
        Q = 0.28 × 1000 × ρ(-15) × 1.005 × (16-(-15)) ≈ 12390 Вт."""
        project, _ = _project_with_pair()
        loads = project.calculate_ahu_loads()
        assert loads["П-1"]["q_heater_w"] == pytest.approx(12390, rel=0.05)
        assert loads["В-1"]["q_heater_w"] == 0.0

    def test_single_system_unchanged(self):
        """Без переопределений поведение прежнее: оба расхода на одной системе."""
        project, sp = _project_with_pair()
        sp.system_supply = ""
        loads = project.calculate_ahu_loads()
        assert loads["В-1"]["supply_m3h"] == 1000
        assert loads["В-1"]["exhaust_m3h"] == 1000
        assert loads["П-1"]["supply_m3h"] == 0
        assert loads["П-1"]["n_spaces"] == 0


class TestZoneSummarySplit:

    def test_summary_attributes_flows(self):
        project, sp = _project_with_pair()
        sp.hood_m3h = 200
        s = project.get_zone_summary("ventilation")
        assert s["П-1"]["supply_m3h"] == 1000
        assert s["П-1"]["exhaust_m3h"] == 0
        assert s["В-1"]["exhaust_m3h"] == 1000
        assert s["В-1"]["hood_m3h"] == 200
        assert s["В-1"]["supply_m3h"] == 0
        # комната учтена в обеих зонах
        assert s["П-1"]["n_spaces"] == 1
        assert s["В-1"]["n_spaces"] == 1

    def test_summary_without_split(self):
        project, sp = _project_with_pair()
        sp.system_supply = ""
        s = project.get_zone_summary("ventilation")
        assert s["В-1"]["supply_m3h"] == 1000
        assert s["В-1"]["n_spaces"] == 1
        assert "П-1" not in s  # пустая система в сводку по зонам не попадает


class TestZoningAPI:

    def test_assign_rooms_flow_system(self):
        project, sp = _project_with_pair()
        sp.system_supply = ""
        n = project.assign_rooms_flow_system("supply", ["1"], "П-1")
        assert n == 1
        assert sp.system_supply == "П-1"
        # снятие переопределения пустым именем
        n = project.assign_rooms_flow_system("supply", ["1"], "")
        assert n == 1
        assert sp.system_supply == ""
        with pytest.raises(ValueError):
            project.assign_rooms_flow_system("both", ["1"], "П-1")

    def test_assign_creates_system(self):
        project, _ = _project_with_pair()
        project.assign_rooms_flow_system("exhaust", ["1"], "В-НОВАЯ")
        assert "В-НОВАЯ" in project.ventilation_systems

    def test_clear_assignment_clears_split(self):
        project, sp = _project_with_pair()
        project.clear_rooms_assignment("ventilation", ["1"], what="system")
        assert sp.system_ventilation == ""
        assert sp.system_supply == ""


class TestJSONRoundtrip:

    def test_split_fields_survive_save_load(self):
        project, sp = _project_with_pair()
        sp.manual_entry = True          # self-contained сохранение
        sp.system_exhaust = "В-1"
        from hvac.io_json import save_project, load_project
        fd, path = tempfile.mkstemp(suffix=".hvac.json")
        os.close(fd)
        try:
            save_project(project, path)
            fresh = HVACProject()
            load_project(fresh, path)
            re_sp = fresh.get_space("1")
            assert re_sp.system_ventilation == "В-1"
            assert re_sp.system_supply == "П-1"
            assert re_sp.system_exhaust == "В-1"
            loads = fresh.calculate_ahu_loads()
            assert loads["П-1"]["supply_m3h"] == 1000
        finally:
            os.remove(path)
