# -*- coding: utf-8 -*-
"""Safe, previewable assignment of missing HVAC service systems.

The legacy zoning assistant is useful for a blank model, but its broad
grouping is too destructive for a developed project.  This module builds a
non-mutating plan that fills only missing assignments, registers referenced
unknown systems, and gives every generated system an explicit ``AUTO`` name
so an engineer can review or merge the draft later.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
import re

from hvac.equipment import (
    CoolingSystem, HeatingSystem, VentilationSystem,
    make_ventilation_defaults,
)
from hvac.service_coverage import (
    MISSING, UNKNOWN, build_service_coverage,
)


_BLOCK_CODES = {
    "APARTMENT": "APT",
    "RESIDENCE": "RES",
    "HOTEL": "HTL",
    "OFFICE": "OFF",
    "RETAIL": "RTL",
}
_SYSTEM_CLASSES = {
    "heating": HeatingSystem,
    "cooling": CoolingSystem,
    "ventilation": VentilationSystem,
}


@dataclass(frozen=True)
class PlannedSystem:
    domain: str
    name: str
    block: str = ""
    kind: str = ""
    note: str = "Автоматический черновик — проверить границы обслуживания"


@dataclass(frozen=True)
class PlannedAssignment:
    space_id: str
    domain: str
    field: str
    system_name: str


@dataclass(frozen=True)
class SystemAssignmentPlan:
    systems: tuple[PlannedSystem, ...]
    assignments: tuple[PlannedAssignment, ...]

    @property
    def affected_space_ids(self) -> tuple[str, ...]:
        return tuple(dict.fromkeys(a.space_id for a in self.assignments))

    def assignment_counts(self) -> dict[str, int]:
        by_domain: dict[str, set[str]] = {
            "heating": set(), "cooling": set(), "ventilation": set(),
        }
        for action in self.assignments:
            by_domain[action.domain].add(action.space_id)
        return {domain: len(ids) for domain, ids in by_domain.items()}

    def system_counts(self) -> dict[str, int]:
        counts = Counter(spec.domain for spec in self.systems)
        return {domain: counts.get(domain, 0)
                for domain in ("heating", "cooling", "ventilation")}


@dataclass(frozen=True)
class AssignmentApplyResult:
    assignments_changed: int
    rooms_changed: int
    created_systems: tuple[tuple[str, str], ...]


def _safe_code(value: str, fallback: str) -> str:
    text = re.sub(r"[^0-9A-Za-zА-Яа-я]+", "-", value or "").strip("-")
    return text.upper() or fallback


def _block_code(space) -> str:
    block = (getattr(space, "block", "") or "").strip()
    return _BLOCK_CODES.get(block.upper(), _safe_code(block, "NO-BLOCK"))


def _level_code(space) -> str:
    level = (getattr(space, "level", "") or "").upper()
    match = re.search(r"(?<![A-Z0-9])(B\d+|L\d+|GFL|MFL)(?![A-Z0-9])", level)
    return match.group(1) if match else _safe_code(level, "NO-LEVEL")


def _family_code(space) -> str:
    room_type = (getattr(space, "room_type", "") or "").casefold()
    if any(word in room_type for word in (
            "сануз", "душ", "убороч", "мусор", "ванн")):
        return "SAN"
    if "кух" in room_type:
        return "KIT"
    if any(word in room_type for word in (
            "корид", "вестиб", "лифт", "лестниц", "пожаробез")):
        return "COM"
    if any(word in room_type for word in (
            "технич", "склад", "сервер")):
        return "TEC"
    if any(word in room_type for word in (
            "магаз", "торгов", "ресторан", "конференц")):
        return "PUB"
    return "GEN"


def _thermal_name(domain: str, space) -> str:
    prefix = "ОТ" if domain == "heating" else "ХС"
    return f"{prefix}-AUTO-{_block_code(space)}"


def _ventilation_name(prefix: str, space) -> str:
    return (f"{prefix}-AUTO-{_block_code(space)}-"
            f"{_level_code(space)}-{_family_code(space)}")


def _kind_priority(kind: str) -> int:
    return {"": 0, "exhaust_fan": 1, "supply_fan": 1, "ahu": 2}.get(kind, 1)


def build_missing_system_assignment_plan(project) -> SystemAssignmentPlan:
    """Build a plan without changing the project.

    Heating and cooling drafts are grouped by assigned building block.
    Ventilation drafts are grouped more narrowly by block, level and service
    family.  Existing assignments are never replaced.  A name referenced by
    a room but absent from the system registry is planned for registration.
    """
    coverage = build_service_coverage(project)
    spaces = {space.space_id: space for space in project.spaces}
    specs: dict[tuple[str, str], PlannedSystem] = {}
    actions: list[PlannedAssignment] = []

    def ensure_spec(domain: str, name: str, space, kind: str = "") -> None:
        if not name or name in project.systems_of(domain):
            return
        key = (domain, name)
        current = specs.get(key)
        if current is not None:
            if {current.kind, kind} == {"supply_fan", "exhaust_fan"}:
                kind = "ahu"
            elif _kind_priority(current.kind) >= _kind_priority(kind):
                return
        specs[key] = PlannedSystem(
            domain=domain, name=name,
            block=(getattr(space, "block", "") or "").strip(),
            kind=kind,
        )

    def add_action(space, domain: str, field: str, name: str,
                   kind: str = "") -> None:
        actions.append(PlannedAssignment(
            space_id=space.space_id, domain=domain,
            field=field, system_name=name,
        ))
        ensure_spec(domain, name, space, kind)

    for row in coverage:
        space = spaces[row.space_id]

        if row.heating_state == UNKNOWN:
            domain = "ventilation" if row.heating_via_air else "heating"
            kind = "supply_fan" if row.heating_via_air else ""
            ensure_spec(domain, row.heating_system, space, kind)
        elif row.heating_state == MISSING and not row.heating_via_air:
            add_action(
                space, "heating", "system_heating",
                _thermal_name("heating", space),
            )

        if row.cooling_state == UNKNOWN:
            domain = "ventilation" if row.cooling_via_air else "cooling"
            kind = "supply_fan" if row.cooling_via_air else ""
            ensure_spec(domain, row.cooling_system, space, kind)
        elif row.cooling_state == MISSING and not row.cooling_via_air:
            add_action(
                space, "cooling", "system_cooling",
                _thermal_name("cooling", space),
            )

        supply_missing = (
            row.supply_state == MISSING
            or (row.heating_via_air and row.heating_state == MISSING)
            or (row.cooling_via_air and row.cooling_state == MISSING)
        )
        exhaust_missing = row.exhaust_state == MISSING

        if row.supply_state == UNKNOWN:
            ensure_spec("ventilation", row.supply_system, space, "supply_fan")
        if row.exhaust_state == UNKNOWN:
            ensure_spec("ventilation", row.exhaust_system, space, "exhaust_fan")

        if supply_missing and exhaust_missing:
            add_action(
                space, "ventilation", "system_ventilation",
                _ventilation_name("ПВ", space), "ahu",
            )
        elif supply_missing:
            add_action(
                space, "ventilation", "system_supply",
                _ventilation_name("П", space), "supply_fan",
            )
        elif exhaust_missing:
            add_action(
                space, "ventilation", "system_exhaust",
                _ventilation_name("В", space), "exhaust_fan",
            )

    return SystemAssignmentPlan(
        systems=tuple(sorted(specs.values(), key=lambda s: (s.domain, s.name))),
        assignments=tuple(actions),
    )


def _system_is_referenced(project, domain: str, name: str) -> bool:
    if domain == "heating":
        fields = ("system_heating",)
    elif domain == "cooling":
        fields = ("system_cooling",)
    else:
        fields = ("system_ventilation", "system_supply", "system_exhaust")
    return any(any(getattr(space, field, "") == name for field in fields)
               for space in project.spaces)


def apply_system_assignment_plan(project, plan: SystemAssignmentPlan
                                 ) -> AssignmentApplyResult:
    """Apply a previewed plan, still refusing to overwrite non-empty fields."""
    changed = 0
    changed_spaces: set[str] = set()
    for action in plan.assignments:
        space = project.get_space(action.space_id)
        if space is None:
            continue
        if action.field == "system_ventilation":
            if any(getattr(space, field, "") for field in (
                    "system_ventilation", "system_supply", "system_exhaust")):
                continue
        elif action.field in ("system_supply", "system_exhaust"):
            if (getattr(space, action.field, "")
                    or getattr(space, "system_ventilation", "")):
                continue
        elif getattr(space, action.field, ""):
            continue
        setattr(space, action.field, action.system_name)
        changed += 1
        changed_spaces.add(space.space_id)

    created: list[tuple[str, str]] = []
    for spec in plan.systems:
        systems = project.systems_of(spec.domain)
        if spec.name in systems or not _system_is_referenced(
                project, spec.domain, spec.name):
            continue
        cls = _SYSTEM_CLASSES[spec.domain]
        kwargs = {"block": spec.block, "note": spec.note}
        if spec.domain == "ventilation":
            kwargs.update(make_ventilation_defaults(spec.kind or "ahu"))
        valid = {key: value for key, value in kwargs.items()
                 if key in cls.__dataclass_fields__}
        systems[spec.name] = cls(name=spec.name, **valid)
        created.append((spec.domain, spec.name))

    if changed or created:
        project.emit("zones_changed")
    return AssignmentApplyResult(
        assignments_changed=changed,
        rooms_changed=len(changed_spaces),
        created_systems=tuple(created),
    )
