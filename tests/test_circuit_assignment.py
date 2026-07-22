# -*- coding: utf-8 -*-
"""Safe AUTO hydronic-circuit assignment tests."""

from hvac.circuit_assignment import (
    apply_auto_circuit_assignment_plan,
    build_auto_circuit_assignment_plan,
)
from hvac.equipment_sizing import select_equipment
from hvac.models import Space
from hvac.project import HVACProject


def _space(project, sid="1"):
    space = Space(
        space_id=sid, number=sid, name="Room", level="L02 HTL",
        block="HOTEL", area_m2=20.0, volume_m3=60.0, height_m=3.0,
        room_type="Офис", is_heated=True, is_cooled=True,
        heat_loss_w=10_000.0, heat_gain_w=8_000.0,
        supply_m3h=1_000.0, exhaust_m3h=800.0,
        system_heating="H-AUTO-HTL", system_cooling="C-AUTO-HTL",
        system_ventilation="AHU-1",
    )
    project.spaces.append(space)
    project._space_by_id[space.space_id] = space
    return space


def _project():
    project = HVACProject()
    project.add_zone_system("heating", "H-AUTO-HTL", block="HOTEL")
    project.add_zone_system("cooling", "C-AUTO-HTL", block="HOTEL")
    project.add_zone_system(
        "ventilation", "AHU-1", block="HOTEL", kind="ahu",
        system_type="supply_exhaust", has_heater=True, has_cooler=True,
    )
    return project


def test_auto_plan_creates_separate_room_and_ahu_circuits():
    project = _project()
    space = _space(project)

    plan = build_auto_circuit_assignment_plan(project)

    assert len(plan.circuits) == 4
    assert len(plan.room_assignments) == 2
    assert len(plan.ahu_links) == 2
    assert not plan.conflicts
    assert not plan.skipped_ahu_links

    result = apply_auto_circuit_assignment_plan(project, plan)

    assert len(result.created_circuits) == 4
    assert result.rooms_changed == 1
    assert result.ahu_links_changed == 2
    assert space.circuit_heating == "К-H-AUTO-HTL-RAD"
    assert space.circuit_cooling == "К-C-AUTO-HTL-FC"
    ahu = project.ventilation_systems["AHU-1"]
    assert ahu.heating_circuit == "К-H-AUTO-HTL-AHU"
    assert ahu.cooling_circuit == "К-C-AUTO-HTL-AHU"
    assert project.heating_circuits[ahu.heating_circuit].circuit_type == "ahu_heater"
    assert project.cooling_circuits[ahu.cooling_circuit].circuit_type == "ahu_cooler"

    project.calculate_ahu_loads()
    selection = select_equipment(project)
    heating = {item.name: item for item in selection.heating}["H-AUTO-HTL"]
    cooling = {item.name: item for item in selection.cooling}["C-AUTO-HTL"]
    assert len(heating.circuits) == 2
    assert len(cooling.circuits) == 2
    assert heating.q_total_w > space.heat_loss_w
    assert cooling.q_total_w > space.heat_gain_w

    repeated = build_auto_circuit_assignment_plan(project)
    assert not repeated.circuits
    assert not repeated.room_assignments
    assert not repeated.ahu_links


def test_manual_room_circuit_and_ahu_link_are_preserved():
    project = _project()
    space = _space(project)
    project.ventilation_systems["AHU-1"].has_cooler = False
    project.add_zone_circuit(
        "heating", "Manual rooms", "H-AUTO-HTL", circuit_type="floor",
    )
    project.add_zone_circuit(
        "heating", "Manual AHU", "H-AUTO-HTL", circuit_type="ahu_heater",
    )
    project.assign_rooms_to_circuit("heating", [space.space_id], "Manual rooms")
    project.ventilation_systems["AHU-1"].heating_circuit = "Manual AHU"

    plan = build_auto_circuit_assignment_plan(project)

    assert all(item.domain != "heating" for item in plan.circuits)
    assert all(item.domain != "heating" for item in plan.room_assignments)
    assert all(item.domain != "heating" for item in plan.ahu_links)
    assert space.circuit_heating == "Manual rooms"
    assert project.ventilation_systems["AHU-1"].heating_circuit == "Manual AHU"


def test_ambiguous_auto_sources_do_not_receive_ahu_link():
    project = _project()
    project.add_zone_system("heating", "H2-AUTO-HTL", block="HOTEL")
    _space(project)

    plan = build_auto_circuit_assignment_plan(project)

    heating_links = [item for item in plan.ahu_links if item.domain == "heating"]
    skipped = [item for item in plan.skipped_ahu_links if item.domain == "heating"]
    assert heating_links == []
    assert len(skipped) == 1
    assert skipped[0].reason == "ambiguous_source"


def test_conflicting_deterministic_circuit_is_not_reused():
    project = _project()
    space = _space(project)
    project.add_zone_system("heating", "Other source", block="OTHER")
    project.add_zone_circuit(
        "heating", "К-H-AUTO-HTL-RAD", "Other source",
        circuit_type="radiator",
    )

    plan = build_auto_circuit_assignment_plan(project)

    assert len(plan.conflicts) == 1
    assert plan.conflicts[0].reason == "parent_system"
    assert all(item.domain != "heating" for item in plan.room_assignments)
    assert not space.circuit_heating
