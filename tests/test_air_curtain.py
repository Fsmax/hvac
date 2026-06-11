# -*- coding: utf-8 -*-
"""Тесты подбора воздушно-тепловых завес (hvac/air_curtain.py)."""

import pytest

from hvac.air_curtain import (
    AirCurtainInput, air_density, calc_air_curtain)


def _gate_input(**kw):
    base = dict(
        is_gate=True, width_m=3.0, height_m=3.0, building_height_m=12.0,
        t_outside_c=-15.0, t_inside_c=16.0, t_mix_c=12.0,
        wind_speed_ms=3.0, q_ratio=0.7, mu_flow=0.25)
    base.update(kw)
    return AirCurtainInput(**base)


class TestAirDensity:
    def test_standard_values(self):
        assert air_density(0.0) == pytest.approx(1.293, abs=0.01)
        assert air_density(20.0) == pytest.approx(1.205, abs=0.01)

    def test_colder_is_denser(self):
        assert air_density(-20.0) > air_density(20.0)


class TestCalcAirCurtain:
    def test_gate_sane_magnitudes(self):
        """Ворота 3×3 при −15 °C: расход десятки тысяч кг/ч,
        мощность — десятки кВт."""
        res = calc_air_curtain(_gate_input())
        assert res.opening_area_m2 == pytest.approx(9.0)
        assert res.dp_pa > 5.0
        assert 10_000 < res.g_kg_h < 100_000
        assert 20_000 < res.q_heat_w < 150_000
        assert res.warnings == []

    def test_mix_balance(self):
        """Баланс смеси: q̄·t_подачи + (1−q̄)·t_н = t_см."""
        inp = _gate_input()
        res = calc_air_curtain(inp)
        t_mix = (inp.q_ratio * res.t_supply_c
                 + (1 - inp.q_ratio) * inp.t_outside_c)
        assert t_mix == pytest.approx(inp.t_mix_c)

    def test_colder_outside_more_heat(self):
        warm = calc_air_curtain(_gate_input(t_outside_c=-5.0))
        cold = calc_air_curtain(_gate_input(t_outside_c=-30.0))
        assert cold.q_heat_w > warm.q_heat_w
        assert cold.dp_pa > warm.dp_pa

    def test_supply_temp_limit_warning(self):
        """Малый q̄ при сильном морозе требует перегретой подачи."""
        res = calc_air_curtain(
            _gate_input(is_gate=False, t_outside_c=-30.0,
                        t_mix_c=14.0, q_ratio=0.3))
        assert res.t_supply_c > 50.0
        assert any("50" in w for w in res.warnings)

    def test_slot_velocity_warning(self):
        """Маленькая щель → скорость выше нормы для дверей."""
        res = calc_air_curtain(
            _gate_input(is_gate=False, slot_area_m2=0.02))
        assert res.v_slot_ms > 8.0
        assert any("м/с" in w for w in res.warnings)

    def test_outside_intake_more_heat(self):
        """Забор снаружи требует большего подогрева, чем изнутри."""
        inside = calc_air_curtain(_gate_input(intake_inside=True))
        outside = calc_air_curtain(_gate_input(intake_inside=False))
        assert outside.q_heat_w > inside.q_heat_w

    def test_warm_outside_warns(self):
        res = calc_air_curtain(_gate_input(t_outside_c=20.0))
        assert any("гравитационный" in w for w in res.warnings)

    def test_invalid_inputs_raise(self):
        with pytest.raises(ValueError):
            calc_air_curtain(_gate_input(width_m=0.0))
        with pytest.raises(ValueError):
            calc_air_curtain(_gate_input(q_ratio=0.0))
        with pytest.raises(ValueError):
            calc_air_curtain(_gate_input(mu_flow=0.0))
