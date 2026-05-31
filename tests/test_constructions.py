# -*- coding: utf-8 -*-
"""Тесты для каталога конструкций v4.x: слои, R_норм, пресеты, JSON."""

import json
from pathlib import Path

import pytest

from hvac.models import Construction, Layer
from hvac.catalogs.constructions import r_norm_for, u_norm_for
from hvac.catalogs.construction_presets import (
    PRESETS, apply_preset, presets_for_category,
)
from hvac.catalogs.materials import MATERIALS, AIR_GAPS
from hvac.project import HVACProject


# ===== Слои → U =====
class TestLayers:
    def test_empty_layers_gives_zero_r(self):
        c = Construction(key="x", category="Стены", family="", type_name="",
                         thickness_mm=0)
        assert c.total_r_m2k_w() == 0.0
        assert c.compute_u() == 0.0

    def test_single_layer_brick_380(self):
        # 380 мм керамического кирпича (λ = 0.81) + Rsi/Rse
        c = Construction(key="x", category="Стены", family="", type_name="",
                         thickness_mm=380)
        c.layers = [Layer(material="Кирпич", thickness_mm=380, lambda_w_mk=0.81)]
        # R = 0.115 + 0.380/0.81 + 0.043 ≈ 0.628
        assert c.total_r_m2k_w() == pytest.approx(0.627, abs=0.005)
        assert c.compute_u() == pytest.approx(1.594, abs=0.01)

    def test_multilayer_wall(self):
        c = Construction(key="x", category="Стены", family="", type_name="",
                         thickness_mm=600)
        c.layers = [
            Layer(material="Штукатурка", thickness_mm=15, lambda_w_mk=0.35),
            Layer(material="Кирпич",     thickness_mm=380, lambda_w_mk=0.81),
            Layer(material="Минвата",    thickness_mm=100, lambda_w_mk=0.045),
            Layer(material="Облицовка",  thickness_mm=120, lambda_w_mk=0.70),
        ]
        # 0.115 + 0.0428 + 0.4691 + 2.2222 + 0.1714 + 0.043 ≈ 3.064
        r = c.total_r_m2k_w()
        assert r == pytest.approx(3.064, abs=0.01)
        assert c.compute_u() == pytest.approx(0.326, abs=0.005)

    def test_air_gap_uses_direct_r(self):
        c = Construction(key="x", category="Стены", family="", type_name="",
                         thickness_mm=200)
        c.layers = [
            Layer(material="Стена", thickness_mm=200, lambda_w_mk=0.81),
            Layer(material="Воздух 50 мм", r_m2k_w=0.17),
        ]
        # 0.115 + 0.247 + 0.17 + 0.043 ≈ 0.575
        assert c.total_r_m2k_w() == pytest.approx(0.575, abs=0.01)

    def test_floor_uses_different_rsi(self):
        c = Construction(key="x", category="Пол", family="", type_name="",
                         thickness_mm=200)
        c.layers = [Layer(material="Бетон", thickness_mm=200, lambda_w_mk=1.86)]
        # Пол: Rsi = 0.172, Rse = 0.043
        # R = 0.172 + 0.108 + 0.043 ≈ 0.322
        assert c.total_r_m2k_w() == pytest.approx(0.322, abs=0.005)

    def test_recompute_u_from_layers(self):
        c = Construction(key="x", category="Стены", family="", type_name="",
                         thickness_mm=380, u_value=999.0)
        c.layers = [Layer(material="Кирпич", thickness_mm=380, lambda_w_mk=0.81)]
        changed = c.recompute_u_from_layers()
        assert changed
        assert c.u_value == pytest.approx(1.594, abs=0.01)


# ===== R_норм: СП 50.13330 Табл.3 (линейно, thermal_norm="SP_RU") =====
class TestRNormSP:
    def test_walls_residential_zero_gsop(self):
        assert r_norm_for("Стены", 0, thermal_norm="SP_RU") == 1.4  # R_min

    def test_walls_at_typical_gsop(self):
        # ГСОП = 5000: R = 0.00035*5000 + 1.4 = 3.15
        assert r_norm_for("Стены", 5000, thermal_norm="SP_RU") == pytest.approx(
            3.15, abs=0.01)

    def test_walls_public_softer(self):
        rn_res = r_norm_for("Стены", 5000, "residential", thermal_norm="SP_RU")
        rn_pub = r_norm_for("Стены", 5000, "public", thermal_norm="SP_RU")
        assert rn_pub < rn_res

    def test_roof_higher_than_walls(self):
        rn_wall = r_norm_for("Стены", 5000, thermal_norm="SP_RU")
        rn_roof = r_norm_for("Покрытие", 5000, thermal_norm="SP_RU")
        assert rn_roof > rn_wall

    def test_unknown_category(self):
        assert r_norm_for("Неизвестно", 5000, thermal_norm="SP_RU") == 0.0

    def test_u_norm_reciprocal(self):
        rn = r_norm_for("Стены", 5000, thermal_norm="SP_RU")
        un = u_norm_for("Стены", 5000, thermal_norm="SP_RU")
        assert un == pytest.approx(1.0 / rn, rel=1e-6)


# ===== R_норм: КМК 2.01.04-18 Табл.2а/2б/2в (ступенчато по полосам Dd) =====
class TestRNormKMK:
    def test_default_norm_is_kmk(self):
        # Дефолт нормы — КМК. Общественное, стены, Dd≤2000, уровень 1 = 1.2
        assert r_norm_for("Стены", 1500, "public", n_floors=2) == pytest.approx(1.2)

    def test_dd_bands_step(self):
        # public стены по полосам: ≤2000=1.2, 2000–3000=1.5, >3000=1.5
        assert r_norm_for("Стены", 1500, "public") == pytest.approx(1.2)
        assert r_norm_for("Стены", 2500, "public") == pytest.approx(1.5)
        assert r_norm_for("Стены", 3500, "public") == pytest.approx(1.5)

    def test_residential_low_vs_high(self):
        # res_low (≤3 эт.) стены ≤2000 = 1.12; res_high (>3 эт.) = 1.5
        low = r_norm_for("Стены", 1500, "residential", n_floors=3)
        high = r_norm_for("Стены", 1500, "residential", n_floors=9)
        assert low == pytest.approx(1.12)
        assert high == pytest.approx(1.5)

    def test_levels_increase(self):
        # res_low стены ≤2000: уровни 2а/2б/2в = 1.12 / 1.6 / 1.8
        l1 = r_norm_for("Стены", 1500, "residential", n_floors=3, level=1)
        l2 = r_norm_for("Стены", 1500, "residential", n_floors=3, level=2)
        l3 = r_norm_for("Стены", 1500, "residential", n_floors=3, level=3)
        assert l1 < l2 < l3
        assert (l1, l2, l3) == pytest.approx((1.12, 1.6, 1.8))

    def test_roof_floor_scaled_by_n(self):
        # Покрытие res_low ≤2000 база = 2.6; с n=0.6 над неотапл. = 2.6·0.6
        full = r_norm_for("Покрытие", 1500, "residential", n_floors=3, n=1.0)
        reduced = r_norm_for("Покрытие", 1500, "residential", n_floors=3, n=0.6)
        assert full == pytest.approx(2.6)
        assert reduced == pytest.approx(2.6 * 0.6)
        # Стены коэффициентом n НЕ масштабируются
        w1 = r_norm_for("Стены", 1500, "residential", n_floors=3, n=1.0)
        w2 = r_norm_for("Стены", 1500, "residential", n_floors=3, n=0.6)
        assert w1 == w2

    def test_doors_not_normalized(self):
        assert r_norm_for("Двери", 2500, "public") == 0.0

    def test_explicit_dd_overrides_gsop(self):
        # gsop_18 в полосе ≤2000, но явный dd в полосе >3000
        assert r_norm_for("Стены", 1500, "public", dd=3500) == pytest.approx(1.5)


# ===== Целостность данных КМК =====
class TestKMKThermalData:
    def test_all_levels_categories_complete(self):
        from hvac.catalogs.kmk_thermal import _LEVELS
        for lvl, data in _LEVELS.items():
            for cat, rows in data["categories"].items():
                assert len(rows) == 3, f"{lvl}/{cat}: ожидалось 3 полосы Dd"
                for row in rows:
                    assert len(row) == 5, f"{lvl}/{cat}: ожидалось 5 значений"
                    assert all(v > 0 for v in row), f"{lvl}/{cat}: значение ≤0"

    def test_category_mapping(self):
        from hvac.catalogs.kmk_thermal import kmk_category_for
        assert kmk_category_for("жилое 4-5 этажей", 5) == "res_high"
        assert kmk_category_for("жилое 1-3 этажа", 3) == "res_low"
        assert kmk_category_for("офис", 4) == "public"
        assert kmk_category_for("общественное", 10) == "public"


# ===== Пресеты =====
class TestPresets:
    def test_presets_have_unique_names(self):
        names = list(PRESETS.keys())
        assert len(names) == len(set(names))

    def test_presets_categories_known(self):
        known = {"Стены", "Окна", "Витраж", "Двери", "Покрытие", "Пол"}
        for p in PRESETS.values():
            assert p.category in known, f"{p.name}: {p.category}"

    def test_apply_preset_brick_wall(self):
        c = Construction(key="x", category="Стены", family="", type_name="",
                         thickness_mm=420)
        ok = apply_preset(c, "Кирпич 380 + минвата 100 мм")
        assert ok
        assert len(c.layers) == 4
        assert c.u_value > 0
        # Утеплённая стена — U должно быть в пределах 0.25-0.55
        assert 0.25 <= c.u_value <= 0.55
        assert "Пресет" in c.note

    def test_apply_preset_window_uses_u_override(self):
        c = Construction(key="w", category="Окна", family="", type_name="",
                         thickness_mm=0)
        apply_preset(c, "Двухкамерный СП с Low-E + Ar")
        assert c.u_value == 1.20
        assert c.shgc == 0.40
        # Светопрозрачные не несут слоёв
        assert c.layers == []

    def test_apply_preset_unknown_returns_false(self):
        c = Construction(key="x", category="Стены", family="", type_name="",
                         thickness_mm=0)
        assert apply_preset(c, "Нет такого пресета") is False

    def test_presets_for_category_filter(self):
        walls = presets_for_category("Стены")
        windows = presets_for_category("Окна")
        assert len(walls) >= 3
        assert len(windows) >= 2
        assert all(p.category == "Стены" for p in walls)


# ===== Каталог материалов =====
class TestMaterials:
    def test_materials_have_positive_lambda(self):
        for m in MATERIALS.values():
            assert m.lambda_w_mk > 0, m.name

    def test_air_gaps_have_positive_r(self):
        for r in AIR_GAPS.values():
            assert r > 0


# ===== Использование и удаление неиспользуемых =====
class TestUsage:
    def test_remove_unused_drops_only_unused(self):
        proj = HVACProject()
        used_key = "Стены / X / 250"
        unused_key = "Стены / Y / 100"
        proj.constructions[used_key] = Construction(
            key=used_key, category="Стены", family="X", type_name="X",
            thickness_mm=250, u_value=0.5)
        proj.constructions[unused_key] = Construction(
            key=unused_key, category="Стены", family="Y", type_name="Y",
            thickness_mm=100, u_value=0.5)

        # Имитируем элемент, ссылающийся на used_key
        from hvac.models import BoundaryElement
        proj.elements.append(BoundaryElement(
            space_id="S1", row_type="external_wall", is_exterior=True,
            element_id="E1", category="Стены", family="X", type_name="X",
            boundary_length_m=5, space_height_m=3, approx_area_m2=15,
            element_area_m2=15, thickness_mm=250, function="",
            host_element_id="", boundary_space_count=1,
            construction_key=used_key, net_area_m2=15))

        n = proj.remove_unused_constructions()
        assert n == 1
        assert used_key in proj.constructions
        assert unused_key not in proj.constructions


# ===== JSON import/export =====
class TestImportExport:
    def test_export_then_import_roundtrip(self, tmp_path):
        proj = HVACProject()
        c = Construction(key="K1", category="Стены", family="F", type_name="T",
                         thickness_mm=380, u_value=0.4, shgc=0.0,
                         note="Тестовая")
        c.layers = [
            Layer(material="Кирпич", thickness_mm=380, lambda_w_mk=0.81,
                  density_kg_m3=1800),
            Layer(material="Минвата", thickness_mm=100, lambda_w_mk=0.045,
                  density_kg_m3=100),
        ]
        proj.constructions[c.key] = c

        path = tmp_path / "cat.json"
        n = proj.export_constructions_json(str(path))
        assert n == 1
        assert path.exists()

        proj2 = HVACProject()
        stats = proj2.import_constructions_json(str(path), strategy="merge")
        assert stats["added"] == 1
        loaded = proj2.constructions["K1"]
        assert loaded.u_value == pytest.approx(0.4)
        assert loaded.note == "Тестовая"
        assert len(loaded.layers) == 2
        assert loaded.layers[0].lambda_w_mk == pytest.approx(0.81)

    def test_import_merge_does_not_overwrite(self, tmp_path):
        proj = HVACProject()
        c_old = Construction(key="K", category="Стены", family="F",
                              type_name="T", thickness_mm=380, u_value=0.99)
        proj.constructions["K"] = c_old

        # Подготовим файл с тем же ключом но другим U
        data = {"version": "1", "constructions": {
            "K": {"key": "K", "category": "Стены", "family": "F",
                  "type_name": "T", "thickness_mm": 380, "u_value": 0.1,
                  "shgc": 0.0, "note": "", "layers": []}
        }}
        path = tmp_path / "cat.json"
        path.write_text(json.dumps(data), encoding="utf-8")

        stats = proj.import_constructions_json(str(path), strategy="merge")
        assert stats["skipped"] == 1
        assert proj.constructions["K"].u_value == 0.99  # не изменилось

    def test_import_update_u_overwrites(self, tmp_path):
        proj = HVACProject()
        proj.constructions["K"] = Construction(
            key="K", category="Стены", family="F", type_name="T",
            thickness_mm=380, u_value=0.99)
        data = {"version": "1", "constructions": {
            "K": {"key": "K", "category": "Стены", "family": "F",
                  "type_name": "T", "thickness_mm": 380, "u_value": 0.1,
                  "shgc": 0.55, "note": "обновлено", "layers": []}
        }}
        path = tmp_path / "cat.json"
        path.write_text(json.dumps(data), encoding="utf-8")

        stats = proj.import_constructions_json(str(path), strategy="update_u")
        assert stats["updated"] == 1
        assert proj.constructions["K"].u_value == 0.1
        assert proj.constructions["K"].note == "обновлено"

    def test_save_load_empty_project_preserves_settings(self, tmp_path):
        """Регрессионный тест: новый проект без помещений должен
        сохраняться и загружаться, в т.ч. с правками каталога конструкций."""
        from hvac.io_json import save_project, load_project
        p = HVACProject()
        p.new_empty_project(project_name="Пустой", city="Ташкент")
        p.params.wwr_estimate = 0.45
        c = Construction(key="K", category="Стены", family="F", type_name="T",
                          thickness_mm=200, u_value=0.4, note="custom")
        c.layers = [Layer(material="Кирпич", thickness_mm=200,
                          lambda_w_mk=0.81)]
        p.constructions["K"] = c

        path = tmp_path / "empty.hvac.json"
        save_project(p, str(path))  # не должно падать

        p2 = HVACProject()
        load_project(p2, str(path))
        assert p2.params.project_name == "Пустой"
        assert p2.params.city == "Ташкент"
        assert p2.params.wwr_estimate == 0.45
        assert p2.spaces == []
        assert "K" in p2.constructions
        assert p2.constructions["K"].note == "custom"
        assert len(p2.constructions["K"].layers) == 1

    def test_import_replace_clears_catalog(self, tmp_path):
        proj = HVACProject()
        proj.constructions["OLD"] = Construction(
            key="OLD", category="Стены", family="", type_name="",
            thickness_mm=100)
        data = {"version": "1", "constructions": {
            "NEW": {"key": "NEW", "category": "Стены", "family": "",
                    "type_name": "", "thickness_mm": 100, "u_value": 0.5,
                    "shgc": 0.0, "note": "", "layers": []}
        }}
        path = tmp_path / "cat.json"
        path.write_text(json.dumps(data), encoding="utf-8")

        proj.import_constructions_json(str(path), strategy="replace")
        assert "OLD" not in proj.constructions
        assert "NEW" in proj.constructions
