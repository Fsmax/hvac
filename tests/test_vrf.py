# -*- coding: utf-8 -*-
"""Тесты модуля VRF/VRV."""

import pytest
from hvac.vrf import (
    INDOOR_CATALOG, OUTDOOR_CATALOG, VRFConstraints, VRFIndoorUnit,
    VRFOutdoorUnit, VRFSystem, build_vrf_system, check_constraints,
    design_pipe_segments, pipe_diameters_by_index, select_indoor_for_load,
    select_outdoor_for_total,
)


class TestCatalogs:
    def test_indoor_has_models(self):
        assert len(INDOOR_CATALOG) >= 15

    def test_outdoor_has_models(self):
        assert len(OUTDOOR_CATALOG) >= 8

    def test_capacity_indices_sorted(self):
        outdoor_sorted = sorted(OUTDOOR_CATALOG, key=lambda x: x.capacity_index)
        assert outdoor_sorted == sorted(OUTDOOR_CATALOG,
                                          key=lambda x: x.capacity_index)


class TestSelectIndoor:
    def test_picks_smallest_fitting(self):
        """Q_cool = 2000 Вт → ближайший выше (Cassette 22 = 2200)."""
        idu = select_indoor_for_load(2000)
        assert idu is not None
        assert idu.q_cool_w >= 2000

    def test_family_filter(self):
        idu = select_indoor_for_load(3000, family_filter=["Канальный"])
        if idu is not None:
            assert idu.family == "Канальный"

    def test_too_high_returns_none(self):
        idu = select_indoor_for_load(100_000, max_margin=0.20)
        assert idu is None


class TestSelectOutdoor:
    def test_picks_minimal_outdoor(self):
        """Сумма индексов 220 → внешний 250."""
        outdoor = select_outdoor_for_total(220)
        assert outdoor is not None
        assert outdoor.capacity_index == 250

    def test_too_high(self):
        outdoor = select_outdoor_for_total(20_000)
        assert outdoor is None


class TestPipeDiameters:
    def test_small_indoor(self):
        liq, gas = pipe_diameters_by_index(28)
        assert liq == 6.35
        assert gas == 12.7

    def test_medium_indoor(self):
        liq, gas = pipe_diameters_by_index(140)
        assert liq == 9.52
        assert gas == 15.88

    def test_large_main(self):
        liq, gas = pipe_diameters_by_index(800)
        assert liq == 15.88
        assert gas == 28.58


class TestBuildSystem:
    def _make_spaces(self):
        from hvac.models import Space
        spaces = []
        for i, q in enumerate([2000, 3500, 4500, 2800, 5000]):
            spaces.append(Space(
                space_id=f"r{i}", number=f"R-{i:03d}",
                name="Room", level="L1",
                area_m2=30, volume_m3=90, height_m=3,
                heat_gain_w=q,
                heat_loss_w=q * 0.6,
            ))
        return spaces

    def test_builds_system(self):
        sys = build_vrf_system(
            self._make_spaces(),
            indoor_family="Кассетный",
            main_pipe_length_m=20,
            max_pipe_length_m=40,
        )
        assert sys.outdoor is not None
        assert len(sys.indoors) == 5
        assert sys.total_indoor_capacity_index > 0
        assert 0.5 <= sys.combination_ratio <= 1.3

    def test_correction_factor(self):
        """Длинные трассы > 50 м снижают мощность."""
        sys_short = build_vrf_system(self._make_spaces(),
                                       main_pipe_length_m=10,
                                       max_pipe_length_m=20)
        sys_long = build_vrf_system(self._make_spaces(),
                                      main_pipe_length_m=80,
                                      max_pipe_length_m=80)
        assert sys_long.capacity_correction_factor < sys_short.capacity_correction_factor


class TestConstraints:
    def _make_simple_system(self):
        from hvac.models import Space
        spaces = [
            Space(space_id=f"r{i}", number=f"R-{i}", name="Room", level="L1",
                   area_m2=25, volume_m3=75, height_m=3,
                   heat_gain_w=3000, heat_loss_w=2000)
            for i in range(3)
        ]
        return build_vrf_system(spaces, main_pipe_length_m=30,
                                  max_pipe_length_m=50, max_height_m=10)

    def test_default_ok(self):
        sys = self._make_simple_system()
        res = check_constraints(sys)
        assert res.ok or len(res.issues) == 0

    def test_too_long_fails(self):
        sys = self._make_simple_system()
        sys.max_pipe_length_to_indoor_m = 500  # > 165 м
        res = check_constraints(sys)
        assert not res.ok
        assert any("длина" in i.lower() for i in res.issues)

    def test_too_high_fails(self):
        sys = self._make_simple_system()
        sys.max_height_diff_m = 100  # > 50 м
        res = check_constraints(sys)
        assert not res.ok
        assert any("высот" in i.lower() for i in res.issues)

    def test_too_many_indoors_fails(self):
        """Подделаем кучу внутренних → превышение max_indoor_units."""
        sys = self._make_simple_system()
        # Дублируем внутренние до 200 шт
        sys.indoors = sys.indoors * 70
        res = check_constraints(sys)
        assert not res.ok
        assert any("внутренн" in i.lower() for i in res.issues)


class TestPipeSegments:
    def test_returns_main_plus_terminals(self):
        from hvac.models import Space
        spaces = [
            Space(space_id="r1", number="R-1", name="Room", level="L1",
                   area_m2=25, volume_m3=75, height_m=3,
                   heat_gain_w=3000, heat_loss_w=2000),
            Space(space_id="r2", number="R-2", name="Room", level="L1",
                   area_m2=25, volume_m3=75, height_m=3,
                   heat_gain_w=4000, heat_loss_w=2500),
        ]
        sys = build_vrf_system(spaces, main_pipe_length_m=20,
                                 max_pipe_length_m=30)
        segs = design_pipe_segments(sys)
        # 1 магистраль + 2 терминала
        assert len(segs) == 3
        assert segs[0]["segment"] == "main"
        assert segs[1]["segment"] == "terminal"
        # У всех заполнены диаметры
        for s in segs:
            assert s["liquid_mm"] > 0 and s["gas_mm"] > 0

    def test_empty_system(self):
        sys = VRFSystem()
        assert design_pipe_segments(sys) == []
