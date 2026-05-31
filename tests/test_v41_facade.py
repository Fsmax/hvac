# -*- coding: utf-8 -*-
"""Интеграционные тесты для фасадных методов v4.1."""

import pytest
from hvac.project import HVACProject
from hvac.models import Space
from hvac.equipment import (
    HeatingSystem, HeatingCircuit, VentilationSystem,
)


def _setup_basic_project():
    p = HVACProject()
    p.params.apply_city("Ташкент")
    # Помещения
    for i in range(5):
        sp = Space(
            space_id=f"r{i}", number=f"R-{i:03d}",
            name="Офис", level="L1",
            area_m2=25, volume_m3=75, height_m=3,
            t_in_heat=20, t_in_cool=24,
            room_type="Офис",
            heat_loss_w=2000 + 200 * i,
            heat_gain_w=2500,
            supply_m3h=120, exhaust_m3h=120,
            system_heating="Котёл-1", system_cooling="Чиллер-1",
            system_ventilation="ПВ-1",
        )
        p.spaces.append(sp)
        p._space_by_id[sp.space_id] = sp
    # Системы
    p.heating_systems["Котёл-1"] = HeatingSystem(
        name="Котёл-1", t_supply=80, t_return=60)
    p.ventilation_systems["ПВ-1"] = VentilationSystem(
        name="ПВ-1", has_recovery=True,
        recovery_efficiency_winter=0.65,
        recovery_efficiency_summer=0.55,
        t_supply_winter=18, t_supply_summer=18,
    )
    return p


class TestComputeAHUProcesses:
    def test_basic_winter_summer_transitional(self):
        p = _setup_basic_project()
        result = p.compute_ahu_processes()
        assert "ПВ-1" in result
        assert set(result["ПВ-1"].keys()) == {
            "winter", "summer", "transitional"}
        # Зимой калорифер тратит мощность
        winter = result["ПВ-1"]["winter"]
        assert winter.q_heater_kw > 0

    def test_results_stored_on_project(self):
        p = _setup_basic_project()
        p.compute_ahu_processes()
        assert p.ahu_processes
        assert "ПВ-1" in p.ahu_processes

    def test_event_emitted(self):
        p = _setup_basic_project()
        events = []
        p.subscribe("ahu_processes_computed", lambda: events.append(1))
        p.compute_ahu_processes()
        assert events == [1]


class TestDesignHeatingHydraulics:
    def test_picks_pumps_for_all_circuits(self):
        from hvac.pipe_sizing import PipeNetwork
        p = _setup_basic_project()
        p.recalculate()
        # Имитируем результаты size_pipes
        p.pipe_networks["Котёл-1"] = PipeNetwork(
            system_name="Котёл-1",
            total_heat_load_w=50_000,
            total_flow_kg_h=2150,
            t_supply_c=80, t_return_c=60,
            total_pressure_loss_pa=35_000,
        )
        p.heating_circuits["Котёл-1"] = HeatingCircuit(
            name="Котёл-1", circuit_type="radiator", t_supply=80, t_return=60)
        result = p.design_heating_hydraulics(static_height_m=15)
        assert "Котёл-1" in result
        assert result["Котёл-1"].pump.selected_model
        assert result["Котёл-1"].expansion_tank.required_tank_volume_l > 0
        # Параметры записаны обратно в circuit
        assert p.heating_circuits["Котёл-1"].pump_model != ""


class TestSelectRadiators:
    def test_assigns_radiators_to_loaded_spaces(self):
        p = _setup_basic_project()
        picks = p.select_radiators_for_all_spaces()
        # Каждое помещение с нагрузкой получило радиатор
        assert len(picks) == 5
        for pick in picks.values():
            assert pick.actual_power_w > 0

    def test_temperature_graph_used_from_heating_system(self):
        """Если не передан t_supply, берётся из HeatingSystem."""
        p = _setup_basic_project()
        p.heating_systems["Котёл-1"].t_supply = 65
        p.heating_systems["Котёл-1"].t_return = 50
        picks = p.select_radiators_for_all_spaces()
        assert picks  # подбор сработал

    def test_filter_by_family(self):
        p = _setup_basic_project()
        picks = p.select_radiators_for_all_spaces(
            family_filter=["Биметалл"],
            prefer_sectional=True,
        )
        for pick in picks.values():
            assert pick.model.family.startswith("Биметалл")


class TestAcousticsForAHU:
    def test_returns_analysis_per_ahu(self):
        p = _setup_basic_project()
        result = p.analyze_acoustics_for_ahus()
        assert "ПВ-1" in result
        assert result["ПВ-1"].lpa_at_terminal > 0

    def test_stored_on_project(self):
        p = _setup_basic_project()
        p.analyze_acoustics_for_ahus()
        assert p.acoustics_results

    def test_uses_strictest_norm(self):
        """Если среди обслуживаемых помещений есть жилое (40 дБА) и
        технич. (70 дБА), берётся более строгая норма (40)."""
        p = _setup_basic_project()
        # Изменим тип одного помещения на жилое
        p.spaces[0].room_type = "Жилая комната"
        result = p.analyze_acoustics_for_ahus()
        # Норма должна быть 40 дБА, а не 50 (офис) и не 70 (техн.)
        assert result["ПВ-1"].lpa_required_dba == 40.0


class TestJsonRoundtrip:
    def test_save_load_preserves_v41(self, tmp_path):
        from hvac.io_json import save_project, load_project
        from hvac.pipe_sizing import PipeNetwork
        from hvac.duct_network import DuctEdge, DuctFitting, DuctNetworkDetailed

        p = _setup_basic_project()
        p.recalculate()
        p.compute_ahu_processes()
        p.pipe_networks["Котёл-1"] = PipeNetwork(
            system_name="Котёл-1",
            total_heat_load_w=50_000,
            total_flow_kg_h=2150,
            t_supply_c=80, t_return_c=60,
            total_pressure_loss_pa=35_000,
        )
        p.heating_circuits["Котёл-1"] = HeatingCircuit(
            name="Котёл-1", circuit_type="radiator", t_supply=80, t_return=60)
        p.design_heating_hydraulics()
        p.select_radiators_for_all_spaces()
        p.analyze_acoustics_for_ahus()

        # Добавим детальную сеть
        net = DuctNetworkDetailed(system_name="ПВ-1", role="supply")
        net.add_edge(DuctEdge(
            edge_id="trunk", flow_m3_h=600, length_m=10,
            shape="round", diameter_mm=315,
            fittings=[DuctFitting(kind="grille_supply")],
            terminal_name="T1", is_terminal=True,
        ))
        net.compute()
        p.duct_networks_detailed["ПВ-1"] = net

        path = tmp_path / "test_v41.hvac.json"
        save_project(p, str(path), force_self_contained=True)

        p2 = HVACProject()
        load_project(p2, str(path))

        # AHU processes
        assert "ПВ-1" in p2.ahu_processes
        assert "winter" in p2.ahu_processes["ПВ-1"]
        winter = p2.ahu_processes["ПВ-1"]["winter"]
        assert winter.q_heater_kw > 0
        assert "outdoor" in winter.points

        # Hydraulics
        assert "Котёл-1" in p2.heating_hydraulics_results
        assert p2.heating_hydraulics_results["Котёл-1"].pump.selected_model

        # Radiators
        assert p2.radiator_picks
        for sid, pick in p2.radiator_picks.items():
            assert pick.model.name

        # Acoustics
        assert "ПВ-1" in p2.acoustics_results
        assert p2.acoustics_results["ПВ-1"].lpa_at_terminal > 0

        # Detailed ducts
        assert "ПВ-1" in p2.duct_networks_detailed
        assert p2.duct_networks_detailed["ПВ-1"].fan_flow_m3_h > 0
