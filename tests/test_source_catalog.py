# -*- coding: utf-8 -*-
"""Тесты каталога котлов/чиллеров и подбора каскада агрегатов."""

import json

import pytest

from hvac.source_catalog import (
    BOILER_CATALOG, CHILLER_CATALOG, BoilerModel, ChillerModel,
    cascade_for, catalog_for_domain, load_boiler_catalog,
    load_chiller_catalog, select_source_units)


class TestCatalogs:
    def test_builtin_boilers_loaded(self):
        assert len(BOILER_CATALOG) >= 15
        for m in BOILER_CATALOG:
            assert m.q_kw > 0, m.name
            assert 0.85 <= m.efficiency <= 1.12, m.name
            assert m.fuel in ("gas", "diesel", "gas_diesel", "electric"), m.name

    def test_builtin_chillers_loaded(self):
        assert len(CHILLER_CATALOG) >= 15
        for m in CHILLER_CATALOG:
            assert m.q_kw > 0, m.name
            assert 2.0 <= m.eer <= 7.0, m.name
            assert m.cooling in ("air", "water"), m.name

    def test_capacity_range_covers_blocks(self):
        """Ряды должны покрывать блоки CHORSU: 0.5–4 МВт тепло/холод."""
        assert max(m.q_kw for m in BOILER_CATALOG) >= 4000
        assert min(m.q_kw for m in BOILER_CATALOG) <= 150
        assert max(m.q_kw for m in CHILLER_CATALOG) >= 2000
        assert min(m.q_kw for m in CHILLER_CATALOG) <= 250

    def test_catalog_for_domain(self):
        assert catalog_for_domain("heating") is BOILER_CATALOG
        assert catalog_for_domain("cooling") is CHILLER_CATALOG

    def test_user_catalog_merged(self, tmp_path):
        (tmp_path / "my.json").write_text(json.dumps({
            "type": "boilers",
            "models": [{"name": "Мой котёл", "q_kw": 123.0,
                        "efficiency": 0.9}],
        }), encoding="utf-8")
        cat = load_boiler_catalog(user_dir=tmp_path)
        assert any(m.name == "Мой котёл" for m in cat)
        assert len(cat) == len(BOILER_CATALOG) + 1
        # тип "boilers" не подмешивается к чиллерам
        assert len(load_chiller_catalog(user_dir=tmp_path)) == \
            len(CHILLER_CATALOG)

    def test_chiller_power_el(self):
        m = ChillerModel(name="t", q_kw=300.0, eer=3.0)
        assert m.power_el_kw == pytest.approx(100.0)


class TestCascade:
    def test_exact_fit_no_rounding_up(self):
        # 2000/1000 = ровно 2 агрегата (не 3 из-за float-мусора)
        assert cascade_for(2000.0, 1000.0) == 2
        assert cascade_for(2000.0000001, 1000.0) == 2

    def test_partial_needs_extra_unit(self):
        assert cascade_for(2001.0, 1000.0) == 3

    def test_single_unit(self):
        assert cascade_for(800.0, 1000.0) == 1

    def test_max_units_limit(self):
        assert cascade_for(10_000.0, 100.0) == 0          # 100 шт — отказ
        assert cascade_for(10_000.0, 100.0, max_units=100) == 100

    def test_zero_inputs(self):
        assert cascade_for(0.0, 1000.0) == 0
        assert cascade_for(1000.0, 0.0) == 0


class TestSelect:
    def test_sorted_fewer_units_then_margin(self):
        cat = [BoilerModel(name="a", q_kw=1000.0),
               BoilerModel(name="b", q_kw=2000.0),
               BoilerModel(name="c", q_kw=4000.0)]
        picks = select_source_units(3800.0, cat, n_best=0)
        # 1×4000 (+5%) → 2×2000 (+5%) → 4×1000 (+5%)
        assert [(p.model.name, p.units) for p in picks] == \
            [("c", 1), ("b", 2), ("a", 4)]
        for p in picks:
            assert p.total_kw >= 3800.0
            assert p.margin_pct >= 0.0

    def test_margin_breaks_ties(self):
        cat = [BoilerModel(name="big", q_kw=3000.0),
               BoilerModel(name="fit", q_kw=2000.0)]
        picks = select_source_units(3800.0, cat, n_best=0)
        # оба по 2 агрегата: 2×2000=4000 (+5%) лучше 2×3000=6000 (+58%)
        assert picks[0].model.name == "fit"

    def test_n_best_and_empty(self):
        cat = [BoilerModel(name=str(i), q_kw=100.0 * (i + 1))
               for i in range(10)]
        assert len(select_source_units(500.0, cat, n_best=3)) == 3
        assert select_source_units(0.0, cat) == []
        assert select_source_units(-5.0, cat) == []

    def test_builtin_covers_chorsu_blocks(self):
        """Реальные нагрузки блоков: подбор не должен быть пустым."""
        for req in (3615 * 1.10, 537 * 1.10):        # HOTEL / RETAIL тепло
            assert select_source_units(req, BOILER_CATALOG), req
        for req in (2570 * 1.15, 891 * 1.15):        # HOTEL / RESIDENCE холод
            assert select_source_units(req, CHILLER_CATALOG), req
