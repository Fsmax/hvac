# -*- coding: utf-8 -*-
"""Unified pump catalog and N+1 tests."""

import os
import tempfile

from hvac.pump_catalog import select_pump_units


def test_rounded_300_m3h_catalog_point_covers_apt_duty():
    pick = select_pump_units(273.23, 7.7)

    assert pick is not None
    assert pick.model.name == "Grundfos TPE 100-200"
    assert pick.working_units == 1
    assert pick.reserve_units == 1
    assert pick.installed_units == 2


def test_head_outside_catalog_is_reported_as_uncovered():
    assert select_pump_units(1000.0, 50.0) is None


def test_pump_n_plus_one_fields_round_trip():
    from hvac.io_json import load_project, save_project
    from hvac.pipe_sizing import PipeNetwork
    from hvac.project import HVACProject

    project = HVACProject()
    project.pipe_networks["H-1"] = PipeNetwork(
        system_name="H-1", pump_model="Grundfos TPE 100-200",
        pump_working_units=1, pump_reserve_units=1,
        pump_catalog_covered=True,
    )
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json",
                                     delete=False) as stream:
        path = stream.name
    try:
        save_project(project, path)
        loaded = HVACProject()
        load_project(loaded, path)
        network = loaded.pipe_networks["H-1"]
        assert network.pump_working_units == 1
        assert network.pump_reserve_units == 1
        assert network.pump_catalog_covered
    finally:
        os.unlink(path)
