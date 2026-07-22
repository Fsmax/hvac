# -*- coding: utf-8 -*-
"""Batch catalog selection and N+1 tests."""

import os
import tempfile

from hvac.models import Space
from hvac.project import HVACProject
from hvac.source_catalog import CHILLER_CATALOG
from hvac.source_catalog_assignment import (
    apply_auto_source_catalog_plan,
    build_auto_source_catalog_plan,
)


def _add_space(project, *, heat=1_000_000.0, cool=2_200_000.0):
    space = Space(
        space_id="1", number="1", name="Room", level="L02",
        block="HOTEL", area_m2=20, volume_m3=60, height_m=3,
        room_type="Офис", is_heated=True, is_cooled=True,
        heat_loss_w=heat, heat_gain_w=cool,
        system_heating="H-AUTO-HTL", system_cooling="C-AUTO-HTL",
    )
    project.spaces.append(space)
    project._space_by_id[space.space_id] = space
    return space


def _project():
    project = HVACProject()
    project.add_zone_system(
        "heating", "H-AUTO-HTL", block="HOTEL", fuel="gas",
    )
    project.add_zone_system(
        "cooling", "C-AUTO-HTL", block="HOTEL",
        system_type="chiller_air",
    )
    _add_space(project)
    return project


def test_batch_plan_selects_compatible_sources_with_n_plus_one():
    project = _project()

    plan = build_auto_source_catalog_plan(project, reserve_units=1)

    assert len(plan.picks) == 2
    assert plan.counts() == {"heating": 1, "cooling": 1}
    for item in plan.picks:
        assert item.installed_units == item.working_units + 1
        assert item.working_units * item.unit_kw >= item.required_kw
    cooling = next(item for item in plan.picks if item.domain == "cooling")
    model = next(m for m in CHILLER_CATALOG
                 if f"{m.manufacturer} {m.name}" == cooling.model_name)
    assert model.cooling == "air"


def test_apply_stores_working_and_reserve_units_in_selection():
    from hvac.equipment_sizing import select_equipment

    project = _project()
    plan = build_auto_source_catalog_plan(project)
    result = apply_auto_source_catalog_plan(project, plan)

    assert result.systems_changed == 2
    selection = select_equipment(project)
    for source in selection.heating + selection.cooling:
        assert source.manual
        assert source.reserve_units == 1
        assert source.units == source.working_units + 1
        assert source.n_plus_one_ok
        assert source.installed_kw == source.units * source.unit_kw


def test_existing_manual_selection_is_not_replaced():
    project = _project()
    project.update_zone_system(
        "heating", "H-AUTO-HTL", design_capacity_kw=777,
        unit_count=2, reserve_units=1, selected_model="Manual 777",
    )

    plan = build_auto_source_catalog_plan(project)
    apply_auto_source_catalog_plan(project, plan)

    assert all(item.system_name != "H-AUTO-HTL" for item in plan.picks)
    assert any(item.system_name == "H-AUTO-HTL" and item.reason == "manual"
               for item in plan.skipped)
    system = project.heating_systems["H-AUTO-HTL"]
    assert system.selected_model == "Manual 777"
    assert system.design_capacity_kw == 777


def test_non_chiller_cooling_source_is_safely_skipped():
    project = _project()
    project.cooling_systems["C-AUTO-HTL"].system_type = "vrf"

    plan = build_auto_source_catalog_plan(project)

    assert all(item.domain != "cooling" for item in plan.picks)
    assert any(item.domain == "cooling" and item.reason == "no_compatible_model"
               for item in plan.skipped)


def test_catalog_selection_round_trip_preserves_reserve_units():
    from hvac.io_json import load_project, save_project

    project = _project()
    apply_auto_source_catalog_plan(
        project, build_auto_source_catalog_plan(project))
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json",
                                     delete=False) as stream:
        path = stream.name
    try:
        save_project(project, path)
        loaded = HVACProject()
        load_project(loaded, path)
        for registry in (loaded.heating_systems, loaded.cooling_systems):
            system = next(iter(registry.values()))
            assert system.selected_model
            assert system.unit_count >= 2
            assert system.reserve_units == 1
    finally:
        os.unlink(path)
