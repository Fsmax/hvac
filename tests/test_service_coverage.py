# -*- coding: utf-8 -*-
"""Service-coverage matrix and final-export quality-gate tests."""

from hvac.equipment import CoolingSystem, HeatingSystem, VentilationSystem
from hvac.models import Space
from hvac.project import HVACProject
from hvac.service_coverage import (
    build_service_coverage,
    coverage_issue_records,
    export_blockers,
)


def _space(**overrides) -> Space:
    data = dict(
        space_id="1",
        number="101",
        name="Office",
        level="L1",
        area_m2=20.0,
        volume_m3=60.0,
        height_m=3.0,
        room_type="Офис",
    )
    data.update(overrides)
    return Space(**data)


def _project(sp: Space) -> HVACProject:
    project = HVACProject()
    project.spaces.append(sp)
    project._space_by_id[sp.space_id] = sp
    return project


def test_required_heating_and_cooling_without_systems_are_blockers():
    project = _project(_space(is_heated=True, is_cooled=True))

    row = build_service_coverage(project)[0]

    assert row.has_blockers
    assert {"heating_missing", "cooling_missing"} <= set(row.blockers)
    assert {r["code"] for r in coverage_issue_records(project)} >= {
        "heating_missing", "cooling_missing",
    }


def test_non_served_room_needs_no_system_assignment():
    project = _project(_space(is_heated=False, is_cooled=False))

    row = build_service_coverage(project)[0]

    assert row.ready
    assert row.blockers == ()


def test_defined_systems_and_split_ventilation_cover_room():
    sp = _space(
        system_heating="H-1",
        system_cooling="C-1",
        system_supply="P-1",
        system_exhaust="V-1",
        supply_m3h=200.0,
        exhaust_m3h=180.0,
    )
    project = _project(sp)
    project.heating_systems["H-1"] = HeatingSystem(name="H-1")
    project.cooling_systems["C-1"] = CoolingSystem(name="C-1")
    project.ventilation_systems["P-1"] = VentilationSystem(name="P-1")
    project.ventilation_systems["V-1"] = VentilationSystem(name="V-1")

    row = build_service_coverage(project)[0]

    assert row.ready
    assert row.supply_system == "P-1"
    assert row.exhaust_system == "V-1"


def test_air_heating_uses_defined_supply_ventilation_system():
    sp = _space(
        is_heated=True,
        is_cooled=False,
        air_heating=True,
        system_ventilation="AHU-1",
        supply_m3h=250.0,
    )
    project = _project(sp)
    project.ventilation_systems["AHU-1"] = VentilationSystem(name="AHU-1")

    row = build_service_coverage(project)[0]

    assert row.ready
    assert row.heating_via_air
    assert row.heating_system == "AHU-1"


def test_assignment_to_undefined_system_is_blocking():
    project = _project(_space(
        is_heated=True,
        is_cooled=False,
        system_heating="MISSING-H",
    ))

    row = build_service_coverage(project)[0]

    assert "heating_unknown" in row.blockers


def test_zero_volume_and_service_gaps_reported():
    # Диагностика для панели «Проблемы»; экспорт записки она не блокирует.
    project = _project(_space(volume_m3=0.0))

    blockers = export_blockers(project)

    assert any(r["category"] == "Геометрия" for r in blockers)
    assert any(r["category"] == "Обслуживание" for r in blockers)
