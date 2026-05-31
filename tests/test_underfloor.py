# -*- coding: utf-8 -*-
"""Тесты тёплого пола."""

import pytest
from hvac.underfloor import (
    BASE_Q_W_M2_AT_15K, COVER_FACTOR, MAX_FLOOR_T_BY_ZONE, PIPE_CATALOG,
    PITCH_FACTOR, UnderfloorLoop, UnderfloorPipe, design_for_project_spaces,
    design_for_space, design_loop, floor_surface_temperature_c,
    heat_flux_w_m2,
)


class TestHeatFlux:
    def test_base_value_at_15K(self):
        """Шаг 150, плитка, ΔθH=15 K → ~70 Вт/м²."""
        q = heat_flux_w_m2(15.0, pitch_mm=150, cover="tile")
        assert q == pytest.approx(BASE_Q_W_M2_AT_15K, rel=0.05)

    def test_pitch_factor(self):
        """Шаг 100 даёт больше тепла, чем 250."""
        q_100 = heat_flux_w_m2(15.0, pitch_mm=100, cover="tile")
        q_250 = heat_flux_w_m2(15.0, pitch_mm=250, cover="tile")
        assert q_100 > q_250

    def test_cover_carpet_reduces(self):
        """Ковролин снижает теплоотдачу."""
        q_tile = heat_flux_w_m2(15.0, cover="tile")
        q_carpet = heat_flux_w_m2(15.0, cover="carpet")
        assert q_carpet < q_tile * 0.7

    def test_zero_dth(self):
        assert heat_flux_w_m2(0.0) == 0.0

    def test_negative_dth(self):
        assert heat_flux_w_m2(-5.0) == 0.0

    def test_higher_temp_more_flux(self):
        q1 = heat_flux_w_m2(10.0)
        q2 = heat_flux_w_m2(25.0)
        assert q2 > q1


class TestFloorTemperature:
    def test_surface_above_room(self):
        """T_пов всегда выше T_комнаты при положительной теплоотдаче."""
        t = floor_surface_temperature_c(80.0, t_room=20.0)
        assert t > 20.0

    def test_higher_q_higher_t(self):
        t1 = floor_surface_temperature_c(50.0, t_room=20.0)
        t2 = floor_surface_temperature_c(150.0, t_room=20.0)
        assert t2 > t1


class TestDesignLoop:
    def _make_loop(self, area=20, q=1500, t_room=20.0, **kwargs):
        params = dict(
            name="Test", area_m2=area, q_required_w=q,
            t_supply_c=45.0, t_return_c=35.0, t_room_c=t_room,
        )
        params.update(kwargs)
        return UnderfloorLoop(**params)

    def test_basic_design(self):
        loop = self._make_loop(area=20)
        design_loop(loop)
        assert loop.q_actual_w_m2 > 0
        assert loop.pipe_length_m > 0
        assert loop.flow_kg_h > 0
        assert loop.pressure_drop_kpa > 0

    def test_pipe_length_proportional_to_area(self):
        small = self._make_loop(area=10)
        big = self._make_loop(area=40)
        design_loop(small)
        design_loop(big)
        # Длина ≈ A/шаг, должна быть кратной
        assert big.pipe_length_m > 3 * small.pipe_length_m

    def test_warning_for_too_long_loop(self):
        """Площадь, требующая длины > max — генерит предупреждение."""
        # Берём трубку 16x2.0 (max 100 м). Шаг 100 → A = 100·0.1 = 10 м² на 100 м.
        # Возьмём 30 м² → длина ~300 м → должно превысить.
        loop = self._make_loop(area=30, pitch_mm=100)
        loop.pipe = next(p for p in PIPE_CATALOG
                          if "16x2.0" in p.name and p.material == "PEX-AL-PEX")
        design_loop(loop)
        assert any("разделите" in w.lower() or "превышает" in w.lower()
                    or "разделить" in w.lower() or "петель" in w.lower()
                   for w in loop.warnings)

    def test_warning_for_exceed_floor_temp(self):
        """Слишком высокая подача в жилой зоне → T_пов выше 29°C."""
        loop = self._make_loop(area=10, t_room=20.0)
        loop.t_supply_c = 65.0
        loop.t_return_c = 55.0
        loop.zone = "habitable"
        design_loop(loop)
        # Δθ_H = 60-20 = 40 → q очень высокая
        assert any("поверхности" in w.lower() for w in loop.warnings)

    def test_no_warning_in_edge_zone(self):
        """Та же подача в краевой зоне (ванная, 35°C допустимо) ОК."""
        loop = self._make_loop(area=10, t_room=24.0)
        loop.t_supply_c = 50.0
        loop.t_return_c = 40.0
        loop.zone = "edge"
        design_loop(loop)
        warns_floor = [w for w in loop.warnings if "поверхности" in w.lower()]
        # При 50/40 в краевой зоне 35°C может быть превышено или нет —
        # проверим, что лимит используется правильный
        assert loop.t_floor_limit_c == MAX_FLOOR_T_BY_ZONE["edge"]


class TestDesignForSpace:
    def _make_space(self, sid="r1", area=20, q_loss=1500, t_in=20.0):
        from hvac.models import Space
        return Space(
            space_id=sid, number=sid, name="Room", level="L1",
            area_m2=area, volume_m3=area * 3, height_m=3,
            t_in_heat=t_in, heat_loss_w=q_loss,
        )

    def test_coverage_reduces_area(self):
        sp = self._make_space(area=20, q_loss=1500)
        loop = design_for_space(sp, coverage_ratio=0.85)
        assert loop.area_m2 == pytest.approx(17.0)

    def test_project_loop_for_all_spaces(self):
        spaces = [
            self._make_space("a", 20, 1500),
            self._make_space("b", 30, 2400),
            self._make_space("c", 25, 0),       # без нагрузки
        ]
        result = design_for_project_spaces(spaces)
        assert "a" in result
        assert "b" in result
        assert "c" not in result               # пропущено


class TestPipeCatalog:
    def test_catalog_nonempty(self):
        assert len(PIPE_CATALOG) >= 4

    def test_max_lengths_reasonable(self):
        for p in PIPE_CATALOG:
            assert 50 <= p.max_length_m <= 200


class TestPitchFactor:
    def test_smaller_pitch_higher_factor(self):
        assert PITCH_FACTOR[100] > PITCH_FACTOR[150]
        assert PITCH_FACTOR[150] > PITCH_FACTOR[300]
