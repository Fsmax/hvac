# -*- coding: utf-8 -*-
"""Тесты JSON-каталогов оборудования и пользовательских дополнений."""

import json

from hvac.fancoil_catalog import FANCOIL_CATALOG, load_fancoil_catalog
from hvac.radiator_catalog import RADIATOR_CATALOG, load_radiator_catalog


class TestBuiltinCatalogs:
    def test_radiator_catalog_size(self):
        """450 панельных (2 бренда × 5 высот × 3 типа × 15 длин) + 24 явных."""
        assert len(RADIATOR_CATALOG) == 474

    def test_fancoil_catalog_size(self):
        assert len(FANCOIL_CATALOG) == 13

    def test_known_radiator_model_preserved(self):
        """Опорная модель из прежнего встроенного каталога не потерялась."""
        m = next(m for m in RADIATOR_CATALOG
                 if m.name == "Kermi FK0 22 500x1000")
        assert m.q_nominal_w == 1428.0
        assert m.family == "Стальной панельный 22"
        assert m.depth_mm == 100

    def test_known_sectional_preserved(self):
        m = next(m for m in RADIATOR_CATALOG
                 if m.name == "Rifar Base 500 (секция)")
        assert m.q_nominal_w == 204
        assert m.is_sectional and m.max_sections == 14

    def test_known_fancoil_preserved(self):
        m = next(m for m in FANCOIL_CATALOG if m.name == "Carrier 42GWC030")
        assert m.q_cool_nom_w == 3500
        assert m.pipes == 4


class TestUserCatalogs:
    def test_user_radiators_appended(self, tmp_path):
        (tmp_path / "my.json").write_text(json.dumps({
            "type": "radiators",
            "models": [{"name": "Тест-Радиатор 500", "family": "Тест",
                        "q_nominal_w": 999.0, "комментарий": "лишний ключ"}],
        }, ensure_ascii=False), encoding="utf-8")
        cat = load_radiator_catalog(user_dir=tmp_path)
        assert len(cat) == len(RADIATOR_CATALOG) + 1
        m = next(m for m in cat if m.name == "Тест-Радиатор 500")
        assert m.q_nominal_w == 999.0

    def test_user_panel_family_generated(self, tmp_path):
        (tmp_path / "fam.json").write_text(json.dumps({
            "type": "radiators",
            "panel_families": [{
                "brand": "Тест-Бренд",
                "q_per_m": {"500": {"22": 1000}},
                "v_per_m": {"500": {"22": 5.0}},
                "depth_mm": {"22": 100},
                "lengths_mm": [1000, 2000],
            }],
        }, ensure_ascii=False), encoding="utf-8")
        cat = load_radiator_catalog(user_dir=tmp_path)
        gen = [m for m in cat if m.name.startswith("Тест-Бренд")]
        assert len(gen) == 2
        assert gen[0].q_nominal_w == 1000.0          # 1000 Вт/м × 1.0 м

    def test_user_fancoils_appended(self, tmp_path):
        (tmp_path / "fc.json").write_text(json.dumps({
            "type": "fancoils",
            "models": [{"name": "Тест-ФК", "family": "Кассетный",
                        "q_cool_nom_w": 4000.0}],
        }, ensure_ascii=False), encoding="utf-8")
        cat = load_fancoil_catalog(user_dir=tmp_path)
        assert len(cat) == len(FANCOIL_CATALOG) + 1

    def test_wrong_type_skipped(self, tmp_path):
        (tmp_path / "fc.json").write_text(json.dumps({
            "type": "fancoils",
            "models": [{"name": "Не радиатор"}],
        }), encoding="utf-8")
        cat = load_radiator_catalog(user_dir=tmp_path)
        assert len(cat) == len(RADIATOR_CATALOG)

    def test_broken_json_skipped(self, tmp_path, caplog):
        (tmp_path / "bad.json").write_text("{не json", encoding="utf-8")
        cat = load_radiator_catalog(user_dir=tmp_path)   # не падает
        assert len(cat) == len(RADIATOR_CATALOG)

    def test_missing_dir_ok(self, tmp_path):
        cat = load_radiator_catalog(user_dir=tmp_path / "нет_такой_папки")
        assert len(cat) == len(RADIATOR_CATALOG)
