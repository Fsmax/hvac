# -*- coding: utf-8 -*-
"""Тесты климатической базы (climate.json) — целостность и узб. города ШНҚ."""

from hvac.catalogs.climate import CLIMATE_DB


REQUIRED = ("country", "t_heat_092", "t_heat_098", "t_cool_095",
            "daily_amp", "solar_vert", "gsop_18")
PERIOD = ("z_ht_8", "t_ht_8", "z_ht_12", "t_ht_12")


class TestClimateIntegrity:
    def test_all_cities_have_required_fields(self):
        for name, e in CLIMATE_DB.items():
            for f in REQUIRED:
                assert f in e, f"{name}: нет поля {f}"

    def test_design_temps_ordered(self):
        # t_098 (обеспеч. 0.98) холоднее или равно t_092
        for name, e in CLIMATE_DB.items():
            assert e["t_heat_098"] <= e["t_heat_092"], name

    def test_period_fields_paired(self):
        # если есть хоть одно поле периода ≤8/≤12 — должны быть все 4
        for name, e in CLIMATE_DB.items():
            present = [f for f in PERIOD if f in e]
            assert present == [] or len(present) == 4, f"{name}: {present}"

    def test_period_ordering(self):
        # период ≤12°C длиннее и теплее периода ≤8°C
        for name, e in CLIMATE_DB.items():
            if "z_ht_8" in e:
                assert e["z_ht_12"] >= e["z_ht_8"], name
                assert e["t_ht_12"] >= e["t_ht_8"], name


class TestUzbekCities:
    def test_uz_cities_have_period_data(self):
        # все узбекские города должны нести данные периодов ≤8/≤12 (ШНҚ 2.01.01-22)
        uz = {k: v for k, v in CLIMATE_DB.items() if v.get("country") == "UZ"}
        assert len(uz) >= 40, f"ожидалось ≥40 узб. городов, есть {len(uz)}"
        for name, e in uz.items():
            assert "z_ht_8" in e, f"{name}: нет периода ≤8°C"

    def test_spot_values(self):
        # выборочная сверка с ШНҚ 2.01.01-22 Табл.4
        jizzakh = CLIMATE_DB["Джизак"]
        assert jizzakh["t_heat_092"] == -16
        assert jizzakh["z_ht_8"] == 126 and jizzakh["t_ht_8"] == 2.7
        urgench = CLIMATE_DB["Ургенч"]
        assert urgench["t_heat_092"] == -18
        assert urgench["z_ht_12"] == 176
