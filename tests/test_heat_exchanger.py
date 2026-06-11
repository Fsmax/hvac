# -*- coding: utf-8 -*-
"""Тесты подбора пластинчатого ТО (hvac/heat_exchanger.py)."""

import math

import pytest

from hvac.heat_exchanger import HX_PRESETS, PlateHXInput, calc_plate_hx


class TestCalcPlateHX:
    def test_reference_case_95_70(self):
        """100 кВт, 95/70 → 60/80: LMTD = 5/ln(1,5) ≈ 12,33 K."""
        res = calc_plate_hx(PlateHXInput(
            q_kw=100.0, t_hot_in=95, t_hot_out=70,
            t_cold_in=60, t_cold_out=80, k_w_m2k=4500, margin=0.10))
        expected_lmtd = (15.0 - 10.0) / math.log(15.0 / 10.0)
        assert res.lmtd_k == pytest.approx(expected_lmtd, rel=1e-6)
        assert res.area_m2 == pytest.approx(
            100_000 * 1.1 / (4500 * expected_lmtd), rel=1e-6)
        # G = 0,86·Q/Δt
        assert res.g_hot_m3h == pytest.approx(0.86 * 100 / 25, rel=1e-6)
        assert res.g_cold_m3h == pytest.approx(0.86 * 100 / 20, rel=1e-6)
        assert res.warnings == []

    def test_equal_end_dt(self):
        """Равные концевые напоры: LMTD равен им (предел формулы)."""
        res = calc_plate_hx(PlateHXInput(
            q_kw=50.0, t_hot_in=90, t_hot_out=70,
            t_cold_in=50, t_cold_out=70))
        assert res.lmtd_k == pytest.approx(20.0)

    def test_counterflow_cross_allowed(self):
        """Противоток: выход нагреваемой выше выхода греющей — допустимо."""
        res = calc_plate_hx(PlateHXInput(
            q_kw=100.0, t_hot_in=70, t_hot_out=30,
            t_cold_in=5, t_cold_out=60))
        assert res.area_m2 > 0

    def test_impossible_cross_raises(self):
        """Выход нагреваемой выше входа греющей — недостижимо."""
        with pytest.raises(ValueError, match="крест"):
            calc_plate_hx(PlateHXInput(
                q_kw=100.0, t_hot_in=70, t_hot_out=50,
                t_cold_in=30, t_cold_out=75))

    def test_more_load_more_area(self):
        small = calc_plate_hx(PlateHXInput(q_kw=50.0))
        big = calc_plate_hx(PlateHXInput(q_kw=500.0))
        assert big.area_m2 == pytest.approx(small.area_m2 * 10, rel=1e-6)

    def test_small_lmtd_warns(self):
        res = calc_plate_hx(PlateHXInput(
            q_kw=100.0, t_hot_in=62, t_hot_out=52,
            t_cold_in=50, t_cold_out=60))
        assert any("LMTD" in w for w in res.warnings)

    def test_unusual_k_warns(self):
        res = calc_plate_hx(PlateHXInput(q_kw=100.0, k_w_m2k=1000.0))
        assert any("диапазона" in w for w in res.warnings)

    def test_invalid_inputs_raise(self):
        with pytest.raises(ValueError):
            calc_plate_hx(PlateHXInput(q_kw=0.0))
        with pytest.raises(ValueError):
            calc_plate_hx(PlateHXInput(t_hot_in=70, t_hot_out=70))
        with pytest.raises(ValueError):
            calc_plate_hx(PlateHXInput(t_cold_in=60, t_cold_out=60))

    def test_presets_are_consistent(self):
        """Все пресеты считаются без ошибок."""
        for name, (t1i, t1o, t2i, t2o) in HX_PRESETS.items():
            res = calc_plate_hx(PlateHXInput(
                q_kw=100.0, t_hot_in=t1i, t_hot_out=t1o,
                t_cold_in=t2i, t_cold_out=t2o))
            assert res.area_m2 > 0, name
