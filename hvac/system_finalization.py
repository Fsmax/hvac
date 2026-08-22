# -*- coding: utf-8 -*-
"""Review and finalize preliminary AUTO HVAC systems.

Only deterministic vertical-riser candidates are proposed automatically:
systems generated for regular ``Lxx`` floors with the same block, service
family and equipment kind.  Podium, ground, mezzanine and basement systems
remain separate because merging them needs an engineering decision.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
import re


@dataclass(frozen=True)
class AutoMergeProposal:
    domain: str
    target_name: str
    source_names: tuple[str, ...]
    kind: str
    block: str
    rooms: int
    supply_m3h: float
    exhaust_m3h: float


@dataclass(frozen=True)
class GeometryRepair:
    space_id: str
    number: str
    name: str
    old_volume_m3: float
    new_volume_m3: float


@dataclass(frozen=True)
class SystemFinalizationPlan:
    auto_system_count: int
    merge_proposals: tuple[AutoMergeProposal, ...]
    geometry_repairs: tuple[GeometryRepair, ...]

    @property
    def systems_removed(self) -> int:
        return sum(len(item.source_names) - 1
                   for item in self.merge_proposals)


@dataclass(frozen=True)
class AutoMergeResult:
    proposals_applied: int
    rooms_changed: int
    systems_removed: int


@dataclass(frozen=True)
class GeometryRepairResult:
    repaired: int


def _auto_vertical_group(name: str) -> tuple[str, str] | None:
    """Return (target_name, level) for our exact AUTO Lxx naming scheme."""
    parts = name.split("-")
    if (len(parts) != 5 or parts[1] != "AUTO"
            or re.fullmatch(r"L\d+", parts[3]) is None):
        return None
    target = "-".join((parts[0], parts[1], parts[2], parts[4]))
    return target, parts[3]


def _proposal_metrics(project, source_names: set[str]) -> tuple[int, float, float]:
    room_ids = set()
    supply = 0.0
    exhaust = 0.0
    for space in project.spaces:
        touched = False
        if space.vent_system_supply in source_names:
            supply += float(space.supply_m3h or 0.0)
            touched = True
        if space.vent_system_exhaust in source_names:
            exhaust += float(space.exhaust_m3h or 0.0)
            exhaust += float(space.hood_m3h or 0.0)
            touched = True
        if touched:
            room_ids.add(space.space_id)
    return len(room_ids), supply, exhaust


def _build_auto_merge_proposals(project) -> tuple[AutoMergeProposal, ...]:
    groups: dict[tuple[str, str, str], list[str]] = defaultdict(list)
    for name, system in project.ventilation_systems.items():
        parsed = _auto_vertical_group(name)
        if parsed is None:
            continue
        target, _level = parsed
        kind = getattr(system, "kind", "") or "ahu"
        groups[(target, kind, getattr(system, "block", "") or "")].append(name)

    proposals = []
    for (target, kind, block), names in sorted(groups.items()):
        existing = project.ventilation_systems.get(target)
        if existing is not None and getattr(existing, "kind", "") != kind:
            target = f"{target}-{kind.upper()}"
            existing = project.ventilation_systems.get(target)
        if (existing is not None
                and (getattr(existing, "block", "") or "") == block
                and target not in names):
            # A later geometry repair/recalculation can create one more Lxx
            # AUTO system after the main riser was already consolidated.
            names.append(target)
        if len(names) < 2:
            continue
        sources = tuple(sorted(names))
        rooms, supply, exhaust = _proposal_metrics(project, set(sources))
        proposals.append(AutoMergeProposal(
            domain="ventilation", target_name=target,
            source_names=sources, kind=kind, block=block,
            rooms=rooms, supply_m3h=supply, exhaust_m3h=exhaust,
        ))
    return tuple(proposals)


def _build_geometry_repairs(project) -> tuple[GeometryRepair, ...]:
    repairs = []
    for space in project.spaces:
        area = float(space.area_m2 or 0.0)
        height = float(space.height_m or 0.0)
        volume = float(space.volume_m3 or 0.0)
        if volume > 0.0 or area <= 0.0 or height <= 0.0:
            continue
        repairs.append(GeometryRepair(
            space_id=space.space_id, number=space.number, name=space.name,
            old_volume_m3=volume, new_volume_m3=round(area * height, 3),
        ))
    return tuple(repairs)


def build_system_finalization_plan(project) -> SystemFinalizationPlan:
    auto_count = sum(
        "-AUTO-" in name
        for domain in ("heating", "cooling", "ventilation")
        for name in project.systems_of(domain)
    )
    return SystemFinalizationPlan(
        auto_system_count=auto_count,
        merge_proposals=_build_auto_merge_proposals(project),
        geometry_repairs=_build_geometry_repairs(project),
    )


def apply_auto_merge_proposals(project, proposals
                               ) -> AutoMergeResult:
    proposals = tuple(proposals)
    affected = set()
    before = sum(len(project.systems_of(domain))
                 for domain in ("heating", "cooling", "ventilation"))
    applied = 0
    for proposal in proposals:
        source_set = set(proposal.source_names)
        for space in project.spaces:
            fields = ("system_ventilation", "system_supply", "system_exhaust")
            if any(getattr(space, field, "") in source_set for field in fields):
                affected.add(space.space_id)
        if project.merge_zone_systems(
                proposal.domain, proposal.source_names,
                proposal.target_name) or any(
                    name not in project.systems_of(proposal.domain)
                    for name in proposal.source_names):
            applied += 1
    after = sum(len(project.systems_of(domain))
                for domain in ("heating", "cooling", "ventilation"))
    return AutoMergeResult(
        proposals_applied=applied, rooms_changed=len(affected),
        systems_removed=max(0, before - after),
    )


def apply_geometry_repairs(project, repairs) -> GeometryRepairResult:
    repaired = 0
    for repair in repairs:
        space = project.get_space(repair.space_id)
        if space is None or float(space.volume_m3 or 0.0) > 0.0:
            continue
        if repair.new_volume_m3 <= 0.0:
            continue
        space.volume_m3 = repair.new_volume_m3
        space.ach_calculated = (
            float(space.supply_m3h or 0.0) / space.volume_m3)
        if space.ventilation_breakdown is not None:
            space.ventilation_breakdown["ach_calculated"] = space.ach_calculated
        repaired += 1
    if repaired:
        project.emit("spaces_changed")
    return GeometryRepairResult(repaired=repaired)
