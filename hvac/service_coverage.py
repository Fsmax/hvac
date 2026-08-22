# -*- coding: utf-8 -*-
"""Final-design service coverage for HVAC spaces.

The thermal-balance flags describe whether a room is intended to be served;
the system fields describe how it is served.  This module reconciles the two
without changing the project and exposes compact blockers for final output.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from typing import TYPE_CHECKING, Iterable

if TYPE_CHECKING:
    from hvac.models import Space
    from hvac.project import HVACProject


NOT_REQUIRED = "not_required"
OK = "ok"
MISSING = "missing"
UNKNOWN = "unknown"

_FLOW_EPSILON_M3H = 0.5


@dataclass(frozen=True)
class ServiceCoverageRow:
    space_id: str
    number: str
    name: str
    level: str
    block: str
    room_type: str

    heating_required: bool
    heating_system: str
    heating_via_air: bool
    heating_state: str

    cooling_required: bool
    cooling_system: str
    cooling_via_air: bool
    cooling_state: str

    supply_required: bool
    supply_system: str
    supply_state: str
    exhaust_required: bool
    exhaust_system: str
    exhaust_state: str

    smoke_systems: tuple[str, ...]
    smoke_state: str
    blockers: tuple[str, ...]

    @property
    def has_blockers(self) -> bool:
        return bool(self.blockers)

    @property
    def ready(self) -> bool:
        return not self.blockers


def _assignment_state(required: bool, name: str, registry: dict) -> str:
    if not required:
        return NOT_REQUIRED
    if not name:
        return MISSING
    if name not in registry:
        return UNKNOWN
    return OK


def _issue_code(domain: str, state: str) -> str | None:
    if state == MISSING:
        return f"{domain}_missing"
    if state == UNKNOWN:
        return f"{domain}_unknown"
    return None


def _coverage_for_space(project: "HVACProject",
                        space: "Space") -> ServiceCoverageRow:
    heating_required = bool(space.is_heated)
    heating_via_air = bool(space.air_heating)
    if heating_via_air:
        heating_system = space.vent_system_supply
        heating_registry = project.ventilation_systems
    else:
        heating_system = space.system_heating
        heating_registry = project.heating_systems
    heating_state = _assignment_state(
        heating_required, heating_system, heating_registry)

    cooling_required = bool(space.is_cooled)
    cooling_via_air = bool(space.air_cooling)
    if cooling_via_air:
        cooling_system = space.vent_system_supply
        cooling_registry = project.ventilation_systems
    else:
        cooling_system = space.system_cooling
        cooling_registry = project.cooling_systems
    cooling_state = _assignment_state(
        cooling_required, cooling_system, cooling_registry)

    supply_required = float(space.supply_m3h or 0.0) > _FLOW_EPSILON_M3H
    supply_system = space.vent_system_supply
    supply_state = _assignment_state(
        supply_required, supply_system, project.ventilation_systems)

    exhaust_flow = float(space.exhaust_m3h or 0.0) + float(
        space.hood_m3h or 0.0)
    exhaust_required = exhaust_flow > _FLOW_EPSILON_M3H
    exhaust_system = space.vent_system_exhaust
    exhaust_state = _assignment_state(
        exhaust_required, exhaust_system, project.ventilation_systems)

    smoke_systems = tuple(dict.fromkeys(
        name for name in (space.smoke_system, space.pressurization_system)
        if name
    ))
    if not smoke_systems:
        smoke_state = NOT_REQUIRED
    elif all(name in project.smoke_systems for name in smoke_systems):
        smoke_state = OK
    else:
        smoke_state = UNKNOWN

    blockers = tuple(code for code in (
        _issue_code("heating", heating_state),
        _issue_code("cooling", cooling_state),
        _issue_code("vent_supply", supply_state),
        _issue_code("vent_exhaust", exhaust_state),
        _issue_code("smoke", smoke_state),
    ) if code is not None)

    return ServiceCoverageRow(
        space_id=space.space_id,
        number=space.number,
        name=space.name,
        level=space.level,
        block=space.block,
        room_type=space.room_type,
        heating_required=heating_required,
        heating_system=heating_system,
        heating_via_air=heating_via_air,
        heating_state=heating_state,
        cooling_required=cooling_required,
        cooling_system=cooling_system,
        cooling_via_air=cooling_via_air,
        cooling_state=cooling_state,
        supply_required=supply_required,
        supply_system=supply_system,
        supply_state=supply_state,
        exhaust_required=exhaust_required,
        exhaust_system=exhaust_system,
        exhaust_state=exhaust_state,
        smoke_systems=smoke_systems,
        smoke_state=smoke_state,
        blockers=blockers,
    )


def build_service_coverage(project: "HVACProject") -> list[ServiceCoverageRow]:
    """Return one non-mutating service-coverage record per project space."""
    return [_coverage_for_space(project, sp) for sp in project.spaces]


_ISSUE_MESSAGES = {
    "heating_missing":
        "{n} отапливаемых помещений не назначены системе отопления",
    "heating_unknown":
        "У {n} помещений система отопления отсутствует в каталоге систем",
    "cooling_missing":
        "{n} охлаждаемых помещений не назначены системе охлаждения",
    "cooling_unknown":
        "У {n} помещений система охлаждения отсутствует в каталоге систем",
    "vent_supply_missing":
        "{n} помещений с притоком не назначены приточной системе",
    "vent_supply_unknown":
        "У {n} помещений приточная система отсутствует в каталоге систем",
    "vent_exhaust_missing":
        "{n} помещений с вытяжкой не назначены вытяжной системе",
    "vent_exhaust_unknown":
        "У {n} помещений вытяжная система отсутствует в каталоге систем",
    "smoke_unknown":
        "У {n} помещений система дымоудаления/подпора отсутствует в каталоге",
}


def coverage_issue_records(project: "HVACProject",
                           rows: Iterable[ServiceCoverageRow] | None = None,
                           ) -> list[dict]:
    """Aggregate per-room coverage gaps into concise validation records."""
    coverage = list(rows) if rows is not None else build_service_coverage(project)
    counts = Counter(code for row in coverage for code in row.blockers)
    records = []
    for code, template in _ISSUE_MESSAGES.items():
        count = counts.get(code, 0)
        if not count:
            continue
        records.append({
            "severity": "error",
            "category": "Обслуживание",
            "msg": template.format(n=count) + " — см. матрицу обслуживания",
            "space_id": "",
            "code": code,
            "count": count,
        })
    return records


def export_blockers(project: "HVACProject") -> list[dict]:
    """Return critical geometry/parameter and service gaps for final output."""
    blockers = [
        dict(item) for item in project.validate_detailed()
        if item.get("severity") == "error"
    ]
    blockers.extend(coverage_issue_records(project))
    return blockers
