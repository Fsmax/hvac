# -*- coding: utf-8 -*-
"""Тесты каталога климатических зон (ШНҚ 2.08.02-23 табл.18)."""
import os
import tempfile

import pytest

from hvac.catalogs.climate_zones import (
    CLIMATE_ZONE_PARAMS, list_climate_zones, zone_params,
    zone_indoor_cooling_temp,
)
from hvac.project import HVACProject
from hvac.io_json import save_project, load_project


def test_zones_listed_in_order():
    assert list_climate_zones() == ["I", "II", "III"]


def test_cooling_temp_decreases_by_zone():
    """Зона I (жаркая) — выше расчётная tв тёплого периода, чем III."""
    t1 = zone_indoor_cooling_temp("I")
    t2 = zone_indoor_cooling_temp("II")
    t3 = zone_indoor_cooling_temp("III")
    assert t1 > t2 > t3
    assert t1 == 26.0 and t2 == 25.0 and t3 == 24.0


def test_each_zone_has_required_keys():
    for zone, p in CLIMATE_ZONE_PARAMS.items():
        for key in ("t_cool", "rh_max", "v_max", "t_permissible_max", "note"):
            assert key in p, f"Зона {zone} без ключа {key}"


def test_unknown_zone_falls_back():
    assert zone_params("XYZ") == zone_params("II")


def test_climate_zone_persists_in_json():
    """params.climate_zone сохраняется и читается из JSON-проекта."""
    project = HVACProject()
    project.params.climate_zone = "III"
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json",
                                      delete=False) as f:
        path = f.name
    try:
        save_project(project, path)
        p2 = HVACProject()
        load_project(p2, path)
        assert p2.params.climate_zone == "III"
    finally:
        os.unlink(path)
