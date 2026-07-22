# -*- coding: utf-8 -*-
"""Safe creation of preliminary hydronic circuits and AHU links.

The assistant only works with sources whose names contain ``-AUTO-``.
For every such source it can create one room circuit and one shared AHU-coil
circuit.  Existing room circuit assignments and AHU links are never replaced.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass

from hvac.ahu_load import calculate_ahu_load


@dataclass(frozen=True)
class PlannedCircuit:
    domain: str
    name: str
    parent_system: str
    circuit_type: str
    purpose: str
    block: str


@dataclass(frozen=True)
class PlannedRoomCircuitAssignment:
    space_id: str
    domain: str
    parent_system: str
    circuit_name: str


@dataclass(frozen=True)
class PlannedAHUCircuitLink:
    system_name: str
    domain: str
    parent_system: str
    circuit_name: str

    @property
    def field(self) -> str:
        return "heating_circuit" if self.domain == "heating" else "cooling_circuit"


@dataclass(frozen=True)
class CircuitConflict:
    domain: str
    circuit_name: str
    reason: str


@dataclass(frozen=True)
class SkippedAHULink:
    system_name: str
    domain: str
    block: str
    reason: str


@dataclass(frozen=True)
class CircuitAssignmentPlan:
    circuits: tuple[PlannedCircuit, ...]
    room_assignments: tuple[PlannedRoomCircuitAssignment, ...]
    ahu_links: tuple[PlannedAHUCircuitLink, ...]
    conflicts: tuple[CircuitConflict, ...]
    skipped_ahu_links: tuple[SkippedAHULink, ...]

    @property
    def affected_space_ids(self) -> tuple[str, ...]:
        return tuple(sorted({item.space_id for item in self.room_assignments}))

    def circuit_counts(self) -> dict[str, int]:
        return {
            domain: sum(item.domain == domain for item in self.circuits)
            for domain in ("heating", "cooling")
        }

    def room_counts(self) -> dict[str, int]:
        return {
            domain: sum(item.domain == domain for item in self.room_assignments)
            for domain in ("heating", "cooling")
        }

    def ahu_counts(self) -> dict[str, int]:
        return {
            domain: sum(item.domain == domain for item in self.ahu_links)
            for domain in ("heating", "cooling")
        }


@dataclass(frozen=True)
class CircuitAssignmentResult:
    created_circuits: tuple[tuple[str, str], ...]
    rooms_changed: int
    ahu_links_changed: int


_ROOM_TYPES = {"heating": "radiator", "cooling": "fancoil"}
_AHU_TYPES = {"heating": "ahu_heater", "cooling": "ahu_cooler"}
_ROOM_SUFFIXES = {"heating": "RAD", "cooling": "FC"}


def _is_auto_source(name: str) -> bool:
    return "-AUTO-" in (name or "")


def _circuit_name(parent_system: str, domain: str, purpose: str) -> str:
    suffix = "AHU" if purpose == "ahu" else _ROOM_SUFFIXES[domain]
    return f"К-{parent_system}-{suffix}"


def _pure_ahu_loads(project) -> dict:
    """Calculate AHU loads without updating ``project.ahu_loads``."""
    by_supply = defaultdict(list)
    by_exhaust = defaultdict(list)
    for space in project.spaces:
        supply = (getattr(space, "vent_system_supply", "")
                  or getattr(space, "system_ventilation", ""))
        exhaust = (getattr(space, "vent_system_exhaust", "")
                   or getattr(space, "system_ventilation", ""))
        if supply:
            by_supply[supply].append(space)
        if exhaust:
            by_exhaust[exhaust].append(space)
    return {
        name: calculate_ahu_load(
            system, by_supply.get(name, []), project.params,
            exhaust_spaces=by_exhaust.get(name, []),
        )
        for name, system in project.ventilation_systems.items()
    }


def _circuit_matches(project, spec: PlannedCircuit) -> tuple[bool, str]:
    existing = project.circuits_of(spec.domain).get(spec.name)
    if existing is None:
        return True, ""
    if getattr(existing, "parent_system", "") != spec.parent_system:
        return False, "parent_system"
    if getattr(existing, "circuit_type", "") != spec.circuit_type:
        return False, "circuit_type"
    return True, ""


def build_auto_circuit_assignment_plan(project) -> CircuitAssignmentPlan:
    """Build a non-mutating plan for AUTO sources, rooms and AHU coils."""
    specs: dict[tuple[str, str], PlannedCircuit] = {}
    rooms: list[PlannedRoomCircuitAssignment] = []
    ahu_links: list[PlannedAHUCircuitLink] = []
    conflicts: dict[tuple[str, str], CircuitConflict] = {}
    skipped: list[SkippedAHULink] = []

    auto_sources_by_block: dict[str, dict[str, list[str]]] = {
        "heating": defaultdict(list), "cooling": defaultdict(list),
    }
    for domain in ("heating", "cooling"):
        for name, system in project.systems_of(domain).items():
            if not _is_auto_source(name):
                continue
            block = (getattr(system, "block", "") or "").strip().upper()
            if block:
                auto_sources_by_block[domain][block].append(name)

    def ensure_spec(domain: str, parent: str, purpose: str,
                    block: str) -> PlannedCircuit | None:
        circuit_type = (_ROOM_TYPES[domain] if purpose == "room"
                        else _AHU_TYPES[domain])
        spec = PlannedCircuit(
            domain=domain,
            name=_circuit_name(parent, domain, purpose),
            parent_system=parent,
            circuit_type=circuit_type,
            purpose=purpose,
            block=block,
        )
        valid, reason = _circuit_matches(project, spec)
        if not valid:
            conflicts[(domain, spec.name)] = CircuitConflict(
                domain=domain, circuit_name=spec.name, reason=reason,
            )
            return None
        if spec.name not in project.circuits_of(domain):
            specs[(domain, spec.name)] = spec
        return spec

    for domain in ("heating", "cooling"):
        system_field, circuit_field = project.zoning_space_fields(domain)
        for parent, system in project.systems_of(domain).items():
            if not _is_auto_source(parent):
                continue
            candidates = [
                space for space in project.spaces
                if getattr(space, system_field, "") == parent
                and not getattr(space, circuit_field, "")
            ]
            if not candidates:
                continue
            block = (getattr(system, "block", "") or "").strip()
            spec = ensure_spec(domain, parent, "room", block)
            if spec is None:
                continue
            rooms.extend(PlannedRoomCircuitAssignment(
                space_id=space.space_id, domain=domain,
                parent_system=parent, circuit_name=spec.name,
            ) for space in candidates)

    loads = _pure_ahu_loads(project)
    for system_name, ventilation in project.ventilation_systems.items():
        load = loads[system_name]
        block = (getattr(ventilation, "block", "") or "").strip()
        block_key = block.upper()
        for domain, q_w, field in (
            ("heating", load.q_heater_w, "heating_circuit"),
            ("cooling", load.q_cooler_total_w, "cooling_circuit"),
        ):
            if q_w <= 0.0 or getattr(ventilation, field, ""):
                continue
            parents = sorted(auto_sources_by_block[domain].get(block_key, []))
            if len(parents) != 1:
                reason = "no_source" if not parents else "ambiguous_source"
                skipped.append(SkippedAHULink(
                    system_name=system_name, domain=domain,
                    block=block, reason=reason,
                ))
                continue
            parent = parents[0]
            spec = ensure_spec(domain, parent, "ahu", block)
            if spec is None:
                continue
            ahu_links.append(PlannedAHUCircuitLink(
                system_name=system_name, domain=domain,
                parent_system=parent, circuit_name=spec.name,
            ))

    return CircuitAssignmentPlan(
        circuits=tuple(sorted(specs.values(), key=lambda x: (x.domain, x.name))),
        room_assignments=tuple(rooms),
        ahu_links=tuple(ahu_links),
        conflicts=tuple(sorted(conflicts.values(), key=lambda x: (x.domain, x.circuit_name))),
        skipped_ahu_links=tuple(skipped),
    )


def apply_auto_circuit_assignment_plan(project, plan: CircuitAssignmentPlan
                                       ) -> CircuitAssignmentResult:
    """Apply a previewed plan while rechecking all no-overwrite guards."""
    created: list[tuple[str, str]] = []
    for spec in plan.circuits:
        valid, _reason = _circuit_matches(project, spec)
        if not valid:
            continue
        if spec.name not in project.circuits_of(spec.domain):
            project.add_zone_circuit(
                spec.domain, spec.name, spec.parent_system,
                circuit_type=spec.circuit_type,
                note=f"AUTO: {spec.purpose} circuit for {spec.block}",
            )
            created.append((spec.domain, spec.name))

    changed_spaces: set[str] = set()
    for item in plan.room_assignments:
        space = project.get_space(item.space_id)
        if space is None:
            continue
        system_field, circuit_field = project.zoning_space_fields(item.domain)
        if (getattr(space, system_field, "") != item.parent_system
                or getattr(space, circuit_field, "")):
            continue
        if project.circuit_parent(item.domain, item.circuit_name) != item.parent_system:
            continue
        setattr(space, circuit_field, item.circuit_name)
        changed_spaces.add(space.space_id)

    links_changed = 0
    for item in plan.ahu_links:
        system = project.ventilation_systems.get(item.system_name)
        if system is None or getattr(system, item.field, ""):
            continue
        if project.circuit_parent(item.domain, item.circuit_name) != item.parent_system:
            continue
        setattr(system, item.field, item.circuit_name)
        links_changed += 1

    if changed_spaces or links_changed:
        project.emit("zones_changed")
    return CircuitAssignmentResult(
        created_circuits=tuple(created),
        rooms_changed=len(changed_spaces),
        ahu_links_changed=links_changed,
    )
