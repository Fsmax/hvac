# -*- coding: utf-8 -*-
"""Safe planning and application of missing HVAC system assignments."""

from hvac.equipment import HeatingSystem, VentilationSystem
from hvac.models import Space
from hvac.project import HVACProject
from hvac.service_coverage import build_service_coverage
from hvac.system_assignment import (
    apply_system_assignment_plan,
    build_missing_system_assignment_plan,
)


def _add(project: HVACProject, sid: str, *, block: str = "HOTEL",
         level: str = "L04 HTL", room_type: str = "Офис", **kwargs) -> Space:
    values = dict(
        space_id=sid, number=sid, name=sid, level=level, block=block,
        area_m2=20.0, volume_m3=60.0, height_m=3.0,
        room_type=room_type,
    )
    values.update(kwargs)
    space = Space(**values)
    project.spaces.append(space)
    project._space_by_id[sid] = space
    return space


def test_plan_groups_thermal_systems_by_block_and_closes_coverage():
    project = HVACProject()
    first = _add(
        project, "1", supply_m3h=200.0, exhaust_m3h=180.0,
        is_heated=True, is_cooled=True,
    )
    second = _add(
        project, "2", room_type="Коридор", supply_m3h=100.0,
        exhaust_m3h=100.0, is_heated=True, is_cooled=True,
    )

    plan = build_missing_system_assignment_plan(project)
    result = apply_system_assignment_plan(project, plan)

    assert result.assignments_changed == 6
    assert first.system_heating == second.system_heating
    assert first.system_cooling == second.system_cooling
    assert first.system_ventilation
    assert second.system_ventilation
    assert project.heating_systems[first.system_heating].block == "HOTEL"
    assert project.cooling_systems[first.system_cooling].block == "HOTEL"
    assert project.ventilation_systems[first.system_ventilation].kind == "ahu"
    assert all(row.ready for row in build_service_coverage(project))


def test_exhaust_only_room_gets_split_exhaust_fan():
    project = HVACProject()
    space = _add(
        project, "1", block="RESIDENCE", level="L08 RES",
        room_type="Санузел", supply_m3h=0.0, exhaust_m3h=100.0,
        is_heated=False, is_cooled=False,
    )

    result = apply_system_assignment_plan(
        project, build_missing_system_assignment_plan(project))

    assert result.assignments_changed == 1
    assert not space.system_ventilation
    assert not space.system_supply
    assert space.system_exhaust.startswith("В-AUTO-RES-L08-SAN")
    system = project.ventilation_systems[space.system_exhaust]
    assert system.kind == "exhaust_fan"
    assert system.system_type == "exhaust"


def test_existing_assignments_are_preserved_and_unknown_system_is_registered():
    project = HVACProject()
    space = _add(
        project, "1", system_heating="РУЧНАЯ-ОТ",
        system_cooling="РУЧНАЯ-ХС", is_heated=True, is_cooled=True,
        supply_m3h=0.0, exhaust_m3h=0.0,
    )

    plan = build_missing_system_assignment_plan(project)
    apply_system_assignment_plan(project, plan)

    assert space.system_heating == "РУЧНАЯ-ОТ"
    assert space.system_cooling == "РУЧНАЯ-ХС"
    assert "РУЧНАЯ-ОТ" in project.heating_systems
    assert "РУЧНАЯ-ХС" in project.cooling_systems
    assert build_service_coverage(project)[0].ready


def test_unknown_combined_ventilation_system_is_registered_as_ahu():
    project = HVACProject()
    space = _add(
        project, "1", system_ventilation="РУЧНАЯ-ПВ",
        supply_m3h=100.0, exhaust_m3h=100.0,
        is_heated=False, is_cooled=False,
    )

    apply_system_assignment_plan(
        project, build_missing_system_assignment_plan(project))

    assert space.system_ventilation == "РУЧНАЯ-ПВ"
    assert project.ventilation_systems["РУЧНАЯ-ПВ"].kind == "ahu"
    assert build_service_coverage(project)[0].ready


def test_plan_does_not_overwrite_field_changed_after_preview():
    project = HVACProject()
    space = _add(project, "1", is_heated=True, is_cooled=False)
    plan = build_missing_system_assignment_plan(project)
    space.system_heating = "ПОСЛЕ-ПРЕДПРОСМОТРА"
    project.heating_systems[space.system_heating] = HeatingSystem(
        name=space.system_heating)

    result = apply_system_assignment_plan(project, plan)

    assert result.assignments_changed == 0
    assert space.system_heating == "ПОСЛЕ-ПРЕДПРОСМОТРА"


def test_air_heating_uses_supply_system_not_water_heating():
    project = HVACProject()
    space = _add(
        project, "1", air_heating=True, is_heated=True, is_cooled=False,
        supply_m3h=150.0,
    )

    apply_system_assignment_plan(
        project, build_missing_system_assignment_plan(project))

    assert not space.system_heating
    assert space.vent_system_supply
    assert isinstance(
        project.ventilation_systems[space.vent_system_supply],
        VentilationSystem,
    )
    assert build_service_coverage(project)[0].ready
