# -*- coding: utf-8 -*-
"""AUTO-system consolidation and safe geometry-repair tests."""

from hvac.models import Space
from hvac.project import HVACProject
from hvac.service_coverage import build_service_coverage
from hvac.system_assignment import (
    apply_system_assignment_plan, build_missing_system_assignment_plan,
)
from hvac.system_finalization import (
    apply_auto_merge_proposals,
    apply_geometry_repairs,
    build_system_finalization_plan,
)


def _add(project: HVACProject, sid: str, level: str, *,
         volume: float = 60.0) -> Space:
    space = Space(
        space_id=sid, number=sid, name=sid, level=level,
        block="RESIDENCE", area_m2=20.0, volume_m3=volume, height_m=3.0,
        room_type="Санузел", is_heated=False, is_cooled=False,
        exhaust_m3h=100.0,
    )
    project.spaces.append(space)
    project._space_by_id[sid] = space
    return space


def test_vertical_auto_exhaust_systems_get_merge_proposal():
    project = HVACProject()
    first = _add(project, "1", "L02 RES")
    second = _add(project, "2", "L03 RES")
    apply_system_assignment_plan(
        project, build_missing_system_assignment_plan(project))

    plan = build_system_finalization_plan(project)

    assert plan.auto_system_count == 2
    assert len(plan.merge_proposals) == 1
    proposal = plan.merge_proposals[0]
    assert proposal.target_name == "В-AUTO-RES-SAN"
    assert len(proposal.source_names) == 2
    assert proposal.rooms == 2
    assert proposal.exhaust_m3h == 200.0

    result = apply_auto_merge_proposals(project, plan.merge_proposals)

    assert result.systems_removed == 1
    assert set(project.ventilation_systems) == {"В-AUTO-RES-SAN"}
    assert first.system_exhaust == second.system_exhaust == "В-AUTO-RES-SAN"
    assert all(row.ready for row in build_service_coverage(project))


def test_ground_and_mezzanine_auto_systems_are_not_merged_as_vertical_riser():
    project = HVACProject()
    _add(project, "1", "GFL RES")
    _add(project, "2", "MFL RES")
    apply_system_assignment_plan(
        project, build_missing_system_assignment_plan(project))

    plan = build_system_finalization_plan(project)

    assert plan.auto_system_count == 2
    assert plan.merge_proposals == ()


def test_later_auto_level_joins_existing_consolidated_riser():
    project = HVACProject()
    _add(project, "1", "L02 RES")
    _add(project, "2", "L03 RES")
    apply_system_assignment_plan(
        project, build_missing_system_assignment_plan(project))
    first_plan = build_system_finalization_plan(project)
    apply_auto_merge_proposals(project, first_plan.merge_proposals)

    later = _add(project, "3", "L04 RES")
    apply_system_assignment_plan(
        project, build_missing_system_assignment_plan(project))
    later_plan = build_system_finalization_plan(project)

    assert len(later_plan.merge_proposals) == 1
    proposal = later_plan.merge_proposals[0]
    assert proposal.target_name == "В-AUTO-RES-SAN"
    assert set(proposal.source_names) == {
        "В-AUTO-RES-SAN", "В-AUTO-RES-L04-SAN",
    }
    assert later_plan.systems_removed == 1

    result = apply_auto_merge_proposals(project, later_plan.merge_proposals)

    assert result.systems_removed == 1
    assert set(project.ventilation_systems) == {"В-AUTO-RES-SAN"}
    assert later.system_exhaust == "В-AUTO-RES-SAN"


def test_zero_volume_is_repaired_from_area_and_height():
    project = HVACProject()
    space = _add(project, "1", "L02 RES", volume=0.0)

    plan = build_system_finalization_plan(project)
    result = apply_geometry_repairs(project, plan.geometry_repairs)

    assert len(plan.geometry_repairs) == 1
    assert result.repaired == 1
    assert space.volume_m3 == 60.0
    assert space.ach_calculated == 0.0
    assert not any(
        item.get("category") == "Геометрия"
        for item in project.validate_detailed()
    )


def test_merge_zone_systems_rewrites_room_references_and_removes_sources():
    project = HVACProject()
    first = _add(project, "1", "L02 RES")
    second = _add(project, "2", "L03 RES")
    apply_system_assignment_plan(
        project, build_missing_system_assignment_plan(project))
    sources = sorted(project.ventilation_systems)

    changed = project.merge_zone_systems(
        "ventilation", sources, "В-RES-SAN")

    assert changed == 2
    assert set(project.ventilation_systems) == {"В-RES-SAN"}
    assert first.system_exhaust == second.system_exhaust == "В-RES-SAN"
