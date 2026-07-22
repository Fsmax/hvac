# -*- coding: utf-8 -*-
"""Safe batch catalog selection for preliminary AUTO heat/cool sources."""
from __future__ import annotations

from dataclasses import dataclass

from hvac.equipment_sizing import select_equipment
from hvac.source_catalog import catalog_for_domain, select_source_units


@dataclass(frozen=True)
class PlannedSourceCatalogPick:
    domain: str
    system_name: str
    required_kw: float
    model_name: str
    unit_kw: float
    working_units: int
    reserve_units: int
    installed_units: int
    installed_kw: float
    working_margin_pct: float
    efficiency_or_eer: float


@dataclass(frozen=True)
class SkippedSourceCatalogPick:
    domain: str
    system_name: str
    reason: str


@dataclass(frozen=True)
class SourceCatalogAssignmentPlan:
    picks: tuple[PlannedSourceCatalogPick, ...]
    skipped: tuple[SkippedSourceCatalogPick, ...]

    def counts(self) -> dict[str, int]:
        return {
            domain: sum(item.domain == domain for item in self.picks)
            for domain in ("heating", "cooling")
        }


@dataclass(frozen=True)
class SourceCatalogAssignmentResult:
    systems_changed: int


def _is_manual(system) -> bool:
    return bool(
        float(getattr(system, "design_capacity_kw", 0.0) or 0.0) > 0.0
        or int(getattr(system, "unit_count", 0) or 0) > 0
        or (getattr(system, "selected_model", "") or "").strip()
    )


def _compatible_catalog(domain: str, system) -> list:
    catalog = list(catalog_for_domain(domain))
    if domain == "heating":
        fuel = (getattr(system, "fuel", "") or "").strip().lower()
        if fuel == "gas":
            catalog = [m for m in catalog if m.fuel in ("gas", "gas_diesel")]
        elif fuel == "diesel":
            catalog = [m for m in catalog if m.fuel in ("diesel", "gas_diesel")]
        elif fuel:
            catalog = [m for m in catalog if m.fuel == fuel]
        t_supply = float(getattr(system, "t_supply", 0.0) or 0.0)
        if t_supply > 0.0:
            catalog = [m for m in catalog if m.t_max_c >= t_supply]
    else:
        system_type = (getattr(system, "system_type", "") or "").lower()
        if system_type == "chiller_air":
            catalog = [m for m in catalog if m.cooling == "air"]
        elif system_type == "chiller_water":
            catalog = [m for m in catalog if m.cooling == "water"]
        elif system_type not in ("", "chiller"):
            return []
    return catalog


def build_auto_source_catalog_plan(project, *, reserve_units: int = 1
                                   ) -> SourceCatalogAssignmentPlan:
    """Plan best compatible catalog picks for unselected AUTO sources."""
    selection = select_equipment(project)
    picks: list[PlannedSourceCatalogPick] = []
    skipped: list[SkippedSourceCatalogPick] = []
    reserve_units = max(0, int(reserve_units))

    for domain in ("heating", "cooling"):
        for source in selection.sources(domain):
            if "-AUTO-" not in source.name:
                continue
            system = project.systems_of(domain).get(source.name)
            if system is None:
                continue
            if _is_manual(system):
                skipped.append(SkippedSourceCatalogPick(
                    domain=domain, system_name=source.name, reason="manual",
                ))
                continue
            catalog = _compatible_catalog(domain, system)
            variants = select_source_units(
                source.required_kw, catalog, max_units=8, n_best=1,
            )
            if not variants:
                skipped.append(SkippedSourceCatalogPick(
                    domain=domain, system_name=source.name,
                    reason="no_compatible_model",
                ))
                continue
            variant = variants[0]
            model = variant.model
            installed_units = variant.units + reserve_units
            picks.append(PlannedSourceCatalogPick(
                domain=domain,
                system_name=source.name,
                required_kw=source.required_kw,
                model_name=(f"{model.manufacturer} {model.name}").strip(),
                unit_kw=float(model.q_kw),
                working_units=variant.units,
                reserve_units=reserve_units,
                installed_units=installed_units,
                installed_kw=installed_units * float(model.q_kw),
                working_margin_pct=variant.margin_pct,
                efficiency_or_eer=float(
                    getattr(model, "efficiency", getattr(model, "eer", 0.0))),
            ))

    return SourceCatalogAssignmentPlan(
        picks=tuple(picks), skipped=tuple(skipped),
    )


def apply_auto_source_catalog_plan(project, plan: SourceCatalogAssignmentPlan
                                  ) -> SourceCatalogAssignmentResult:
    """Apply the previewed picks, rechecking that manual choices stay intact."""
    changed = 0
    for item in plan.picks:
        system = project.systems_of(item.domain).get(item.system_name)
        if system is None or _is_manual(system):
            continue
        values = {
            "design_capacity_kw": item.unit_kw,
            "unit_count": item.installed_units,
            "reserve_units": item.reserve_units,
            "selected_model": item.model_name,
        }
        if item.domain == "heating":
            values["efficiency"] = item.efficiency_or_eer
        else:
            values["cop"] = item.efficiency_or_eer
        project.update_zone_system(item.domain, item.system_name, **values)
        changed += 1
    return SourceCatalogAssignmentResult(systems_changed=changed)
