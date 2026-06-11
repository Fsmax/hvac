# -*- coding: utf-8 -*-
"""Тесты каталога вентиляторов и подбора по рабочей точке."""

import json

import pytest

from hvac.fan_catalog import (
    FAN_CATALOG, FanModel, load_fan_catalog, select_fan, select_fans)


class TestCatalog:
    def test_builtin_catalog_loaded(self):
        assert len(FAN_CATALOG) >= 20
        families = {m.family for m in FAN_CATALOG}
        assert "Канальный круглый" in families
        assert "Радиальный" in families

    def test_models_have_positive_curve_points(self):
        for m in FAN_CATALOG:
            assert m.flow_max_m3_h > 0, m.name
            assert m.pressure_max_pa > 0, m.name
            assert m.power_w > 0, m.name

    def test_user_catalog_merged(self, tmp_path):
        (tmp_path / "my_fans.json").write_text(json.dumps({
            "type": "fans",
            "models": [{"name": "Мой вентилятор", "family": "Радиальный",
                        "flow_max_m3_h": 99999, "pressure_max_pa": 5000,
                        "power_w": 1}],
        }), encoding="utf-8")
        cat = load_fan_catalog(user_dir=tmp_path)
        assert any(m.name == "Мой вентилятор" for m in cat)
        # Чужой тип не подмешивается
        assert len(cat) == len(FAN_CATALOG) + 1

    def test_pressure_curve_parabola(self):
        m = FanModel(name="t", flow_max_m3_h=1000, pressure_max_pa=400)
        assert m.pressure_at_flow(0.0) == pytest.approx(400.0)
        assert m.pressure_at_flow(500.0) == pytest.approx(300.0)   # 1−0,25
        assert m.pressure_at_flow(1000.0) == 0.0
        assert m.pressure_at_flow(2000.0) == 0.0


class TestSelectFan:
    def test_small_duct_point(self):
        """300 м³/ч / 200 Па — должен найтись малый канальный."""
        pick = select_fan(300.0, 200.0)
        assert pick is not None
        assert pick.pressure_available_pa >= 200.0
        assert pick.flow_m3_h == 300.0

    def test_economical_first(self):
        """Сортировка по мощности: первый вариант — наименее мощный."""
        picks = select_fans(1000.0, 150.0, n_best=3)
        assert len(picks) >= 2
        powers = [p.model.power_w for p in picks]
        assert powers == sorted(powers)

    def test_high_pressure_needs_radial(self):
        """1200 Па может дать только радиальный."""
        pick = select_fan(3000.0, 1200.0)
        assert pick is not None
        assert pick.model.family == "Радиальный"

    def test_impossible_point_empty(self):
        assert select_fans(500_000.0, 100.0) == []
        assert select_fan(100.0, 9000.0) is None

    def test_family_filter(self):
        picks = select_fans(1000.0, 150.0,
                            family_filter=["Канальный прямоугольный"])
        assert picks
        assert all(p.model.family == "Канальный прямоугольный"
                   for p in picks)

    def test_tail_of_curve_warns(self):
        """Точка на правом краю кривой даёт предупреждение."""
        cat = [FanModel(name="t", family="x", flow_max_m3_h=1000,
                        pressure_max_pa=1000, power_w=100)]
        picks = select_fans(900.0, 50.0, catalog=cat)
        assert picks
        assert picks[0].warnings

    def test_invalid_inputs_raise(self):
        with pytest.raises(ValueError):
            select_fans(0.0, 100.0)
        with pytest.raises(ValueError):
            select_fans(100.0, -5.0)
