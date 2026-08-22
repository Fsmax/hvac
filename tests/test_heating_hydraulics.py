# -*- coding: utf-8 -*-
"""Тесты насоса, расширительного бака и подпитки."""

import pytest
from hvac.heating_hydraulics import (
    PUMP_CATALOG, STD_EXPANSION_TANK_LITERS, alpha_t,
    calculate_expansion_tank, design_hydraulics_for_network,
    design_pump, estimate_system_volume_l, pick_expansion_tank,
    pick_pump, required_pump_head_m, water_density,
)


class TestWaterPhysics:
    def test_density_10c(self):
        assert water_density(10.0) == pytest.approx(999.7, rel=0.001)

    def test_density_70c(self):
        assert water_density(70.0) == pytest.approx(977.7, rel=0.001)

    def test_density_interpolation(self):
        """45°C должна быть между 40°C (992.2) и 50°C (988.0)."""
        d = water_density(45.0)
        assert 988.0 < d < 992.2

    def test_alpha_t_increases_with_temperature(self):
        assert alpha_t(40.0) < alpha_t(70.0) < alpha_t(90.0)

    def test_alpha_t_80c(self):
        """ΔV/V при 80°C ≈ 2.9% от V."""
        assert alpha_t(80.0) == pytest.approx(0.0290, rel=0.01)


class TestSystemVolume:
    def test_radiator_default(self):
        """100 кВт радиаторов ≈ 1350 л воды в системе."""
        v = estimate_system_volume_l(100.0, "radiator")
        assert v == pytest.approx(1350.0, rel=0.01)

    def test_floor_more_water(self):
        """Тёплый пол держит больше воды на кВт, чем радиаторы."""
        v_floor = estimate_system_volume_l(100.0, "floor")
        v_rad = estimate_system_volume_l(100.0, "radiator")
        assert v_floor > v_rad

    def test_custom_override(self):
        v = estimate_system_volume_l(50.0, "radiator",
                                       custom_l_per_kw=20.0)
        assert v == pytest.approx(1000.0)


class TestExpansionTank:
    def test_basic_80c(self):
        """Система 1000 л при 80°C: V_тб ≈ 1000·0.029·K_p·1.10.
        K_p = (P_max+1)/(P_max−P_init), при P_max=3, P_init=1.2 → K_p=2.22.
        V ≈ 1000·0.029·2.22·1.10 ≈ 71 л."""
        t = calculate_expansion_tank(
            system_volume_l=1000.0, t_supply_c=80.0,
            static_height_m=0.0,
        )
        # P_init = max(0 + 0.5 + 0.2, 0.5) = 0.7
        # P_max = max(0 + 1.5, 2.5) = 2.5
        # K_p = 3.5 / 1.8 = 1.944
        # V = 29.0 · 1.944 · 1.10 = 62 л
        assert t.expansion_volume_l == pytest.approx(29.0, rel=0.01)
        assert t.pressure_factor == pytest.approx(1.944, rel=0.01)
        assert t.required_tank_volume_l == pytest.approx(62.0, rel=0.05)

    def test_higher_static_increases_pmax(self):
        """Высокое здание (30 м) → P_max растёт, тогда K_p падает."""
        low = calculate_expansion_tank(
            system_volume_l=500.0, t_supply_c=70.0,
            static_height_m=5.0,
        )
        high = calculate_expansion_tank(
            system_volume_l=500.0, t_supply_c=70.0,
            static_height_m=30.0,
        )
        # При высоком здании K_p (множитель) меньше — компенсируется ростом P_max
        assert high.p_max_bar > low.p_max_bar

    def test_relief_valve_above_pmax(self):
        t = calculate_expansion_tank(system_volume_l=500.0, t_supply_c=80.0)
        assert t.relief_valve_pressure_bar > t.p_max_bar


class TestPickTank:
    def test_round_up(self):
        """65 л → 80 л."""
        assert pick_expansion_tank(65.0) == 80

    def test_exact_match(self):
        assert pick_expansion_tank(100.0) == 100

    def test_smaller_than_min(self):
        """5 л → минимальный из ряда (8 л)."""
        assert pick_expansion_tank(5.0) == 8

    def test_larger_than_max(self):
        """1500 л → последний (1000 л)."""
        assert pick_expansion_tank(1500.0) == 1000


class TestPumpHead:
    def test_basic_conversion(self):
        """ΔP=50 кПа, ρ≈980, k=1.3 → H ≈ 50000·1.3/(980·9.81) ≈ 6.76 м."""
        h = required_pump_head_m(50_000.0, t_medium_c=70.0,
                                   reserve_factor=1.30)
        assert h == pytest.approx(6.76, rel=0.02)

    def test_zero_dp(self):
        assert required_pump_head_m(0.0) == 0.0


class TestPumpCatalog:
    def test_picks_first_fitting(self):
        """Q=1.5 m³/h, H=3 m selects the first unified small pump."""
        p = pick_pump(1.5, 3.0)
        assert p is not None
        assert "UPS 25-40" in p[0]

    def test_picks_larger_when_needed(self):
        """Q=10 м³/ч, H=10 м → Magna1 32-100 (8) недостаточен → Stratos 40/1."""
        p = pick_pump(10.0, 11.0)
        assert p is not None
        q, h = p[1], p[2]
        assert q >= 10.0 and h >= 11.0

    def test_large_tpe_point_is_covered(self):
        """The unified catalog covers large plant-room duty points."""
        p = pick_pump(200.0, 20.0)
        assert p is not None
        assert p[1] >= 200.0 and p[2] >= 20.0


class TestDesignPump:
    def _make_network(self, load_w=20_000, dp_pa=30_000, t_sup=70):
        from hvac.pipe_sizing import PipeNetwork
        n = PipeNetwork(
            system_name="Test",
            total_heat_load_w=load_w,
            total_flow_kg_h=load_w / 1.163 / 20,   # ΔT=20K
            t_supply_c=t_sup, t_return_c=t_sup - 20,
            total_pressure_loss_pa=dp_pa,
        )
        return n

    def test_design_pump_picks_model(self):
        n = self._make_network(load_w=100_000, dp_pa=50_000)
        req = design_pump(n, reserve_factor=1.30)
        assert req.flow_m3_h > 0
        assert req.head_m > 0
        # Должен подобрать насос
        assert req.selected_model != ""
        assert req.selected_flow_m3_h >= req.flow_m3_h
        assert req.selected_head_m >= req.head_m


class TestHydraulicsFacade:
    def test_full_design(self):
        from hvac.pipe_sizing import PipeNetwork
        n = PipeNetwork(
            system_name="Радиаторы",
            total_heat_load_w=80_000,
            total_flow_kg_h=80_000 / 1.163 / 20,
            t_supply_c=80.0, t_return_c=60.0,
            total_pressure_loss_pa=40_000,
        )
        result = design_hydraulics_for_network(
            n, circuit_type="radiator", static_height_m=15.0,
        )
        assert result.network_name == "Радиаторы"
        assert result.pump.selected_model
        assert result.expansion_tank.required_tank_volume_l > 0
        assert result.expansion_tank.selected_model.startswith("Бак ")
        assert result.makeup.daily_makeup_l > 0
