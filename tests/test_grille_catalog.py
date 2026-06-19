# -*- coding: utf-8 -*-
"""Тесты каталога решёток (ARKTIKA/Арктос) и подбора по расходу/шуму."""

import json

import pytest

from hvac.grille_catalog import (
    GRILLE_CATALOG,
    load_grille_catalog, select_grille, select_grilles,
    select_grilles_for_room, grille_families, grille_mounts,
)


def _find(code, a, b):
    for m in GRILLE_CATALOG:
        if m.family_code == code and m.a_mm == a and m.b_mm == b:
            return m
    raise AssertionError(f"нет {code} {a}×{b}")


class TestCatalog:
    def test_builtin_loaded(self):
        assert len(GRILLE_CATALOG) >= 300
        codes = {m.family_code for m in GRILLE_CATALOG}
        assert "АМ/АД" in codes          # АМН/АМР/АДН/АДР
        assert "АП" in codes              # переточные
        assert "КМУ" in codes             # для круглых воздуховодов

    def test_families_and_mounts(self):
        fams = dict(grille_families())
        assert "АМ/АД" in fams
        mounts = grille_mounts()
        for m in ("wall", "round_duct", "transfer", "floor", "slot"):
            assert m in mounts

    def test_sizes_positive_f0(self):
        for m in GRILLE_CATALOG:
            assert m.f0_m2 > 0, m.label()

    def test_amad_flagship_values(self):
        """Опорные значения АМ/АД 200×100 (стр.387 каталога)."""
        m = _find("АМ/АД", 200, 100)
        assert m.f0_m2 == pytest.approx(0.018)
        # анкеры шума (дубль LwA=20 схлопнут к max L0=60)
        assert m.max_l0_for_noise(25) == pytest.approx(180)
        assert m.max_l0_for_noise(35) == pytest.approx(280)
        assert m.max_l0_for_noise(45) == pytest.approx(350)
        # интерполяция между 25 и 35
        assert m.max_l0_for_noise(30) == pytest.approx(230)

    def test_noise_anchors_monotonic(self):
        for m in GRILLE_CATALOG:
            a = m._noise_anchors()
            qs = [q for _lw, q in a]
            assert qs == sorted(qs), m.label()


class TestModelMath:
    def test_velocity(self):
        m = _find("АМ/АД", 200, 100)         # F0=0.018
        # 200 м³/ч -> 200/(3600*0.018)=3.09 м/с
        assert m.velocity(200) == pytest.approx(3.086, abs=0.01)

    def test_dp_quadratic_outside(self):
        m = _find("АМ/АД", 200, 100)
        dp_low = m.dp_at(180)                 # анкер 25 дБ: ΔP=6
        assert dp_low == pytest.approx(6.0, abs=0.5)
        # ниже диапазона — квадратично, монотонно меньше
        assert m.dp_at(90) < dp_low

    def test_lwa_at_interpolates(self):
        m = _find("АМ/АД", 200, 100)
        assert m.lwa_at(180) == pytest.approx(25, abs=0.1)
        assert m.lwa_at(280) == pytest.approx(35, abs=0.1)
        assert 25 < m.lwa_at(230) < 35

    def test_allowable_l0_min_of_constraints(self):
        m = _find("АМ/АД", 200, 100)
        # только шум 35 -> 280
        assert m.allowable_l0(max_lwa=35) == pytest.approx(280)
        # добавим жёсткую скорость 2 м/с -> 2*0.018*3600=129.6 (меньше)
        assert m.allowable_l0(max_lwa=35, max_velocity=2.0) == pytest.approx(
            129.6, abs=0.1)


class TestSelect:
    def test_basic_wall(self):
        picks = select_grilles(200, mount="wall", max_lwa=35)
        assert picks
        p = picks[0]
        assert p.n_units == 1
        assert p.lwa is not None and p.lwa <= 35 + 1e-6
        assert p.velocity > 0

    def test_quieter_picks_larger(self):
        """Жёстче по шуму -> крупнее решётка (ниже скорость)."""
        loud = select_grille(800, mount="wall", max_lwa=45, families=["АМ/АД"])
        quiet = select_grille(800, mount="wall", max_lwa=25, families=["АМ/АД"])
        assert loud and quiet
        assert quiet.model.face_area_m2 >= loud.model.face_area_m2
        assert quiet.velocity <= loud.velocity + 1e-6

    def test_family_filter(self):
        picks = select_grilles(300, families=["АМ/АД"])
        assert picks
        assert all(p.model.family_code == "АМ/АД" for p in picks)

    def test_max_velocity_caps_result(self):
        """Ограничение по скорости в живом сечении соблюдается."""
        picks = select_grilles(800, mount="wall", max_lwa=45,
                               max_velocity=2.0, families=["АМ/АД"])
        assert picks
        assert all(p.velocity <= 2.0 + 1e-6 for p in picks)

    def test_velocity_tighter_than_noise(self):
        """Жёсткая скорость даёт крупнее решётку, чем только шум."""
        by_noise = select_grille(800, mount="wall", max_lwa=45,
                                 families=["АМ/АД"])
        by_vel = select_grille(800, mount="wall", max_lwa=45,
                               max_velocity=2.0, families=["АМ/АД"])
        assert by_noise and by_vel
        assert by_vel.model.face_area_m2 >= by_noise.model.face_area_m2

    def test_max_size_limits(self):
        """Ограничение габарита A/B по каталогу соблюдается."""
        picks = select_grilles(800, mount="wall", max_lwa=45,
                               max_a_mm=600, max_b_mm=150)
        assert picks
        for p in picks:
            assert p.model.a_mm is None or p.model.a_mm <= 600
            assert p.model.b_mm is None or p.model.b_mm <= 150

    def test_fix_height_via_max_b(self):
        """Ограничение высоты B при свободной A фиксирует высоту."""
        p = select_grille(800, mount="wall", max_lwa=45,
                          max_b_mm=150, families=["АМ/АД"])
        assert p is not None and p.model.b_mm is not None
        assert p.model.b_mm <= 150

    def test_size_too_small_empty(self):
        """Слишком малый габарит под большой расход -> пусто."""
        assert select_grilles(5000, mount="wall", max_lwa=25,
                              max_a_mm=150, max_b_mm=100,
                              allow_multiple=False) == []

    def test_multiple_units_for_large_flow(self):
        """Очень большой расход -> несколько решёток."""
        p = select_grille(8000, mount="wall", max_lwa=30, families=["АМ/АД"])
        assert p is not None
        assert p.n_units >= 2
        assert p.l0_per_unit * p.n_units == pytest.approx(8000)

    def test_transfer_by_velocity(self):
        """Переточные — без шума, критерий по скорости."""
        picks = select_grilles(300, mount="transfer")
        assert picks
        assert all(p.model.mount == "transfer" for p in picks)
        assert all(p.lwa is None for p in picks)
        # скорость в живом сечении не выше дефолтного предела 1 м/с
        assert picks[0].velocity <= 1.0 + 1e-6

    def test_floor_dp_warning(self):
        picks = select_grilles(500, mount="floor")
        assert picks
        assert picks[0].dp is None
        assert any("номограмм" in w for w in picks[0].warnings)

    def test_round_duct(self):
        picks = select_grilles(400, mount="round_duct", max_lwa=35)
        assert picks
        assert all(p.model.mount == "round_duct" for p in picks)

    def test_impossible_empty(self):
        # абсурдно большой расход при max_units -> пусто
        assert select_grilles(10_000_000, mount="wall", max_lwa=25) == []

    def test_invalid_raises(self):
        with pytest.raises(ValueError):
            select_grilles(0)
        with pytest.raises(ValueError):
            select_grilles(-100)


class TestRoom:
    def test_room_supply_and_exhaust(self):
        rp = select_grilles_for_room(300, 200, max_lwa=35, families=["АМ/АД"])
        assert rp.supply is not None
        assert rp.exhaust is not None
        assert rp.supply.l0_total == 300
        assert rp.exhaust.l0_total == 200

    def test_room_zero_direction(self):
        rp = select_grilles_for_room(0, 150, max_lwa=35)
        assert rp.supply is None
        assert rp.exhaust is not None


class TestUserCatalog:
    def test_user_catalog_merged(self, tmp_path):
        (tmp_path / "my_grilles.json").write_text(json.dumps({
            "type": "grilles",
            "families": [{
                "code": "TEST", "variants": ["ТЕСТ"], "name": "Тестовая",
                "mount": "wall", "kind": "universal", "layout": "noise",
                "sizes": [{"a": 100, "b": 100, "f0": 0.01, "points": [
                    {"lwa": 30, "l0": 100, "dp": 5},
                    {"lwa": 40, "l0": 160, "dp": 12},
                ]}],
            }],
        }), encoding="utf-8")
        cat = load_grille_catalog(user_dir=tmp_path)
        assert any(m.family_code == "TEST" for m in cat)
        assert len(cat) == len(GRILLE_CATALOG) + 1


class TestProjectIntegration:
    def test_select_for_all_spaces(self):
        from hvac.project import HVACProject
        from hvac.models import Space

        pr = HVACProject()
        pr.spaces = [
            Space("S1", "101", "Офис", "1эт", 20.0, 60.0,
                  supply_m3h=300, exhaust_m3h=0),
            Space("S2", "102", "Санузел", "1эт", 4.0, 12.0,
                  supply_m3h=0, exhaust_m3h=75),
            Space("S3", "103", "Склад", "1эт", 10.0, 30.0),  # без расхода
        ]
        picks = pr.select_grilles_for_all_spaces(max_lwa=35)
        assert set(picks.keys()) == {"S1", "S2"}
        assert picks["S1"].supply is not None
        assert picks["S1"].exhaust is None
        assert picks["S2"].exhaust is not None

    def test_json_roundtrip(self, tmp_path):
        from hvac.project import HVACProject
        from hvac.models import Space
        from hvac import io_json

        pr = HVACProject()
        pr.spaces = [Space("S1", "101", "Офис", "1эт", 20.0, 60.0,
                           supply_m3h=300, exhaust_m3h=200)]
        pr.select_grilles_for_all_spaces(max_lwa=35)
        path = str(tmp_path / "p.hvac.json")
        io_json.save_project(pr, path, force_self_contained=True)

        pr2 = HVACProject()
        io_json.load_project(pr2, path)
        assert "S1" in pr2.grille_picks
        a = pr.grille_picks["S1"].supply
        b = pr2.grille_picks["S1"].supply
        assert b is not None
        assert a.model.label() == b.model.label()
        assert a.n_units == b.n_units
        assert a.lwa == pytest.approx(b.lwa)
