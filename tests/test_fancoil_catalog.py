# -*- coding: utf-8 -*-
"""Тесты каталога и подбора фанкойлов."""

import pytest
from hvac.fancoil_catalog import (
    FANCOIL_CATALOG, correct_cool, correct_heat,
    select_fancoil, select_fancoils_for_spaces,
)


class TestCorrection:
    def test_cool_at_nominal(self):
        """При ΔT_actual = ΔT_nominal — мощность совпадает."""
        q = correct_cool(3000.0, 20.0, 20.0)
        assert q == pytest.approx(3000.0)

    def test_cool_at_higher_temp(self):
        """При большем ΔT мощность растёт."""
        q_low = correct_cool(3000.0, 15.0, 20.0)
        q_high = correct_cool(3000.0, 25.0, 20.0)
        assert q_high > q_low

    def test_heat_zero_dt(self):
        assert correct_heat(3000.0, 0.0) == 0.0


class TestCatalog:
    def test_catalog_has_models(self):
        assert len(FANCOIL_CATALOG) >= 10

    def test_all_have_cooling_capacity(self):
        for m in FANCOIL_CATALOG:
            assert m.q_cool_nom_w > 0

    def test_4pipe_outnumber_2pipe(self):
        n4 = sum(1 for m in FANCOIL_CATALOG if m.pipes == 4)
        n2 = sum(1 for m in FANCOIL_CATALOG if m.pipes == 2)
        # В типовом проекте 4-трубных больше
        assert n4 >= n2


class TestSelectFancoil:
    def test_picks_for_typical_office(self):
        """Помещение с холодом 3 кВт, теплом 2 кВт — должен подобраться."""
        pick = select_fancoil(
            required_cool_w=3000, required_heat_w=2000,
        )
        assert pick is not None
        assert pick.actual_cool_w >= 3000

    def test_too_high_load_no_solution(self):
        """50 кВт холода — каталог не имеет таких фанкойлов."""
        pick = select_fancoil(50_000, max_margin=1.0)
        # Должен либо вернуть None, либо самый большой не дотягивающий
        if pick is not None:
            assert pick.actual_cool_w >= 50_000 * 0.7

    def test_family_filter(self):
        pick = select_fancoil(2000, family_filter=["Кассетный 600×600"])
        if pick is not None:
            assert "Кассетный" in pick.model.family

    def test_pipes_filter(self):
        """Фильтр 2-трубных даёт только 2-трубные."""
        pick = select_fancoil(3000, pipes_filter=2)
        if pick is not None:
            assert pick.model.pipes == 2

    def test_max_margin_filter(self):
        """100 Вт нагрузка — фанкойлы слишком большие → должен быть None
        или с приемлемым запасом."""
        pick = select_fancoil(100, max_margin=0.20)
        if pick is not None:
            assert pick.cool_margin_pct <= 20.0


class TestSelectForSpaces:
    def _make_space(self, sid, q_cool, q_heat=0, t_in_cool=24, t_in_heat=20):
        from hvac.models import Space
        return Space(
            space_id=sid, number=sid, name="Room", level="L1",
            area_m2=25, volume_m3=75, height_m=3,
            t_in_cool=t_in_cool, t_in_heat=t_in_heat,
            heat_gain_w=q_cool, heat_loss_w=q_heat,
        )

    def test_assigns_to_spaces(self):
        spaces = [
            self._make_space("a", 2500, 1500),
            self._make_space("b", 5000, 2500),
            self._make_space("c", 0),     # нет нагрузки на холод
        ]
        result = select_fancoils_for_spaces(spaces)
        assert "a" in result
        assert "b" in result
        assert "c" not in result

    def test_filter_by_family(self):
        spaces = [self._make_space("a", 2500, 1500)]
        result = select_fancoils_for_spaces(
            spaces, family_filter=["Канальный низконапорный"])
        if "a" in result:
            assert "Канальный" in result["a"].model.family
