"""Strict, deterministic pressure analysis for an explicitly described duct tree.

This module deliberately has no dependency on the legacy duct sizing or network
catalogs.  It performs no sizing, balancing-device selection, fan selection,
normative lookup, or model mutation.  Every engineering input is supplied by the
caller and validated before any result is produced.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from numbers import Real
from typing import Sequence


ANALYSIS_PROFILE_VERSION = "coordera.hvac.duct-tree.explicit-input/1.0"
ANALYSIS_METHOD = "darcy-weisbach-explicit-factor/1.0"

MAXIMUM_EDGES = 5_000
MAXIMUM_DEPTH = 1_000
MAXIMUM_PATH_MEMBERSHIPS = 100_000

MAXIMUM_ID_LENGTH = 256
MINIMUM_AIR_DENSITY_KG_M3 = 0.1
MAXIMUM_AIR_DENSITY_KG_M3 = 5.0
MAXIMUM_DARCY_FRICTION_FACTOR = 1.0
MINIMUM_DESIGN_MARGIN_FACTOR = 1.0
MAXIMUM_DESIGN_MARGIN_FACTOR = 5.0
MAXIMUM_TERMINAL_FLOW_M3_H = 100_000_000.0
MAXIMUM_LENGTH_M = 100_000.0
MAXIMUM_DIMENSION_MM = 100_000.0
MAXIMUM_LOCAL_LOSS_COEFFICIENT = 1_000_000.0
MAXIMUM_PRESSURE_LOSS_PA = 1_000_000_000.0


class DuctNetworkAnalysisError(ValueError):
    """Raised when an explicit duct-tree input violates the analysis contract."""


@dataclass(frozen=True, slots=True)
class DuctNetworkAnalysisSettings:
    """Explicit global inputs used by every edge in an analysis."""

    rho_kg_m3: float
    darcy_friction_factor: float
    design_margin_factor: float


@dataclass(frozen=True, slots=True)
class DuctNetworkEdgeInput:
    """One edge of a rooted tree.

    ``terminal_flow_m3_h`` is positive only on leaves.  Internal-edge flow is
    derived as the sum of all descendant terminal flows.
    """

    edge_id: str
    parent_id: str
    terminal_flow_m3_h: float
    length_m: float
    shape: str
    diameter_mm: float
    width_mm: float
    height_mm: float
    local_loss_coefficient: float
    fixed_pressure_loss_pa: float
    terminal_required_pressure_pa: float


@dataclass(frozen=True, slots=True)
class DuctNetworkEdgeResult:
    """Validated input and calculated pressure evidence for one edge."""

    edge_id: str
    parent_id: str
    terminal_flow_m3_h: float
    derived_flow_m3_h: float
    length_m: float
    shape: str
    diameter_mm: float
    width_mm: float
    height_mm: float
    cross_section_area_m2: float
    hydraulic_diameter_m: float
    velocity_m_s: float
    dynamic_pressure_pa: float
    friction_pressure_loss_pa: float
    local_pressure_loss_pa: float
    fixed_pressure_loss_pa: float
    terminal_required_pressure_pa: float
    total_pressure_loss_pa: float


@dataclass(frozen=True, slots=True)
class DuctNetworkPathResult:
    """Pressure result for a root-to-terminal path."""

    terminal_edge_id: str
    terminal_flow_m3_h: float
    edge_ids: tuple[str, ...]
    net_pressure_pa: float
    equalization_pressure_difference_pa: float


@dataclass(frozen=True, slots=True)
class DuctNetworkAnalysisResult:
    """Immutable deterministic result of a strict duct-tree analysis."""

    profile_version: str
    method: str
    settings: DuctNetworkAnalysisSettings
    root_edge_id: str
    root_flow_m3_h: float
    edge_count: int
    terminal_count: int
    edges: tuple[DuctNetworkEdgeResult, ...]
    paths: tuple[DuctNetworkPathResult, ...]
    critical_terminal_edge_id: str
    critical_path_edge_ids: tuple[str, ...]
    critical_path_net_pressure_pa: float
    design_pressure_pa: float
    flow_continuity_residual_m3_h: float
    uncertainty_propagation: str = "not-performed"
    sizing_performed: bool = False
    balancing_performed: bool = False
    fan_selected: bool = False
    normative_compliance_claimed: bool = False
    model_mutated: bool = False


def analyze_duct_tree(
    edges: Sequence[DuctNetworkEdgeInput],
    *,
    settings: DuctNetworkAnalysisSettings,
) -> DuctNetworkAnalysisResult:
    """Validate and analyze one rooted, connected, acyclic duct tree.

    Indexing, topology validation, and flow aggregation are O(N).  Path
    materialization is bounded by ``MAXIMUM_PATH_MEMBERSHIPS`` because paths are
    part of the returned evidence.
    """

    _validate_settings(settings)
    settings = DuctNetworkAnalysisSettings(
        rho_kg_m3=float(settings.rho_kg_m3),
        darcy_friction_factor=float(settings.darcy_friction_factor),
        design_margin_factor=float(settings.design_margin_factor),
    )
    if isinstance(edges, (str, bytes)) or not isinstance(edges, Sequence):
        raise DuctNetworkAnalysisError("edges must be a sequence of edge inputs")
    if not edges:
        raise DuctNetworkAnalysisError("duct tree must contain at least one edge")
    if len(edges) > MAXIMUM_EDGES:
        raise DuctNetworkAnalysisError(
            f"duct tree exceeds the {MAXIMUM_EDGES} edge limit"
        )

    by_id: dict[str, DuctNetworkEdgeInput] = {}
    for index, edge in enumerate(edges):
        if not isinstance(edge, DuctNetworkEdgeInput):
            raise DuctNetworkAnalysisError(
                f"edges[{index}] must be DuctNetworkEdgeInput"
            )
        _validate_edge_values(edge, index)
        if edge.edge_id in by_id:
            raise DuctNetworkAnalysisError(f"duplicate edge_id {edge.edge_id!r}")
        by_id[edge.edge_id] = edge

    children: dict[str, list[str]] = {edge_id: [] for edge_id in by_id}
    roots: list[str] = []
    for edge in by_id.values():
        if edge.parent_id == "":
            roots.append(edge.edge_id)
        else:
            if edge.parent_id not in by_id:
                raise DuctNetworkAnalysisError(
                    f"edge {edge.edge_id!r} has unknown parent {edge.parent_id!r}"
                )
            if edge.parent_id == edge.edge_id:
                raise DuctNetworkAnalysisError(
                    f"edge {edge.edge_id!r} cannot be its own parent"
                )
            children[edge.parent_id].append(edge.edge_id)

    if len(roots) != 1:
        raise DuctNetworkAnalysisError(
            f"duct tree must have exactly one root; observed {len(roots)}"
        )
    root_id = roots[0]
    for child_ids in children.values():
        child_ids.sort()

    _validate_no_cycles(by_id)
    traversal, _ = _rooted_traversal(root_id, children)
    if len(traversal) != len(by_id):
        unreachable = sorted(set(by_id) - set(traversal))
        raise DuctNetworkAnalysisError(
            f"duct tree is disconnected; unreachable edges: {unreachable[:5]}"
        )

    terminal_ids: list[str] = []
    for edge_id in sorted(by_id):
        edge = by_id[edge_id]
        if children[edge_id]:
            if edge.terminal_flow_m3_h != 0.0:
                raise DuctNetworkAnalysisError(
                    f"non-leaf edge {edge_id!r} must have terminal_flow_m3_h = 0"
                )
            if edge.terminal_required_pressure_pa != 0.0:
                raise DuctNetworkAnalysisError(
                    f"non-leaf edge {edge_id!r} must have "
                    "terminal_required_pressure_pa = 0"
                )
        else:
            if edge.terminal_flow_m3_h <= 0.0:
                raise DuctNetworkAnalysisError(
                    f"leaf edge {edge_id!r} must have positive terminal flow"
                )
            terminal_ids.append(edge_id)

    derived_flows: dict[str, float] = {}
    for edge_id in reversed(traversal):
        edge = by_id[edge_id]
        flow = (
            edge.terminal_flow_m3_h
            if not children[edge_id]
            else math.fsum(derived_flows[child_id] for child_id in children[edge_id])
        )
        derived_flows[edge_id] = _require_finite_result(
            flow, f"derived flow for edge {edge_id!r}"
        )

    calculated_by_id: dict[str, DuctNetworkEdgeResult] = {}
    for edge_id in sorted(by_id):
        calculated_by_id[edge_id] = _calculate_edge(
            by_id[edge_id], derived_flows[edge_id], settings
        )

    path_memberships = 0
    preliminary_paths: list[tuple[str, tuple[str, ...], float]] = []
    for terminal_id in terminal_ids:
        reversed_path: list[str] = []
        current = terminal_id
        while current:
            reversed_path.append(current)
            current = by_id[current].parent_id
        edge_ids = tuple(reversed(reversed_path))
        path_memberships += len(edge_ids)
        if path_memberships > MAXIMUM_PATH_MEMBERSHIPS:
            raise DuctNetworkAnalysisError(
                "root-to-terminal paths exceed the "
                f"{MAXIMUM_PATH_MEMBERSHIPS} membership limit"
            )
        net_pressure = _require_finite_result(
            math.fsum(calculated_by_id[edge_id].total_pressure_loss_pa for edge_id in edge_ids),
            f"net pressure for terminal {terminal_id!r}",
        )
        preliminary_paths.append((terminal_id, edge_ids, net_pressure))

    # terminal_ids is lexical, and max returns the first equal item.  Therefore a
    # pressure tie deterministically chooses the lexically smallest terminal id.
    critical_terminal_id, critical_edge_ids, critical_pressure = max(
        preliminary_paths, key=lambda item: item[2]
    )
    paths = tuple(
        DuctNetworkPathResult(
            terminal_edge_id=terminal_id,
            terminal_flow_m3_h=float(by_id[terminal_id].terminal_flow_m3_h),
            edge_ids=edge_ids,
            net_pressure_pa=net_pressure,
            equalization_pressure_difference_pa=_require_finite_result(
                max(critical_pressure - net_pressure, 0.0),
                f"equalization pressure for terminal {terminal_id!r}",
            ),
        )
        for terminal_id, edge_ids, net_pressure in preliminary_paths
    )
    design_pressure = _require_finite_result(
        critical_pressure * settings.design_margin_factor,
        "design pressure",
    )
    terminal_flow_sum = math.fsum(
        by_id[terminal_id].terminal_flow_m3_h for terminal_id in terminal_ids
    )
    flow_continuity_residual = _require_signed_finite_result(
        derived_flows[root_id] - terminal_flow_sum,
        "flow continuity residual",
    )

    return DuctNetworkAnalysisResult(
        profile_version=ANALYSIS_PROFILE_VERSION,
        method=ANALYSIS_METHOD,
        settings=settings,
        root_edge_id=root_id,
        root_flow_m3_h=derived_flows[root_id],
        edge_count=len(by_id),
        terminal_count=len(terminal_ids),
        edges=tuple(calculated_by_id[edge_id] for edge_id in sorted(calculated_by_id)),
        paths=paths,
        critical_terminal_edge_id=critical_terminal_id,
        critical_path_edge_ids=critical_edge_ids,
        critical_path_net_pressure_pa=critical_pressure,
        design_pressure_pa=design_pressure,
        flow_continuity_residual_m3_h=flow_continuity_residual,
    )


def _validate_settings(settings: DuctNetworkAnalysisSettings) -> None:
    if not isinstance(settings, DuctNetworkAnalysisSettings):
        raise DuctNetworkAnalysisError("settings must be DuctNetworkAnalysisSettings")
    _require_number(
        settings.rho_kg_m3,
        "settings.rho_kg_m3",
        minimum=MINIMUM_AIR_DENSITY_KG_M3,
        maximum=MAXIMUM_AIR_DENSITY_KG_M3,
    )
    _require_number(
        settings.darcy_friction_factor,
        "settings.darcy_friction_factor",
        exclusive_minimum=0.0,
        maximum=MAXIMUM_DARCY_FRICTION_FACTOR,
    )
    _require_number(
        settings.design_margin_factor,
        "settings.design_margin_factor",
        minimum=MINIMUM_DESIGN_MARGIN_FACTOR,
        maximum=MAXIMUM_DESIGN_MARGIN_FACTOR,
    )


def _validate_edge_values(edge: DuctNetworkEdgeInput, index: int) -> None:
    location = f"edges[{index}]"
    _require_identifier(edge.edge_id, f"{location}.edge_id", allow_empty=False)
    _require_identifier(edge.parent_id, f"{location}.parent_id", allow_empty=True)
    _require_number(
        edge.terminal_flow_m3_h,
        f"{location}.terminal_flow_m3_h",
        minimum=0.0,
        maximum=MAXIMUM_TERMINAL_FLOW_M3_H,
    )
    _require_number(
        edge.length_m,
        f"{location}.length_m",
        exclusive_minimum=0.0,
        maximum=MAXIMUM_LENGTH_M,
    )
    _require_number(
        edge.local_loss_coefficient,
        f"{location}.local_loss_coefficient",
        minimum=0.0,
        maximum=MAXIMUM_LOCAL_LOSS_COEFFICIENT,
    )
    _require_number(
        edge.fixed_pressure_loss_pa,
        f"{location}.fixed_pressure_loss_pa",
        minimum=0.0,
        maximum=MAXIMUM_PRESSURE_LOSS_PA,
    )
    _require_number(
        edge.terminal_required_pressure_pa,
        f"{location}.terminal_required_pressure_pa",
        minimum=0.0,
        maximum=MAXIMUM_PRESSURE_LOSS_PA,
    )

    if edge.shape == "round":
        _require_number(
            edge.diameter_mm,
            f"{location}.diameter_mm",
            exclusive_minimum=0.0,
            maximum=MAXIMUM_DIMENSION_MM,
        )
        _require_exact_zero(edge.width_mm, f"{location}.width_mm")
        _require_exact_zero(edge.height_mm, f"{location}.height_mm")
    elif edge.shape == "rect":
        _require_exact_zero(edge.diameter_mm, f"{location}.diameter_mm")
        _require_number(
            edge.width_mm,
            f"{location}.width_mm",
            exclusive_minimum=0.0,
            maximum=MAXIMUM_DIMENSION_MM,
        )
        _require_number(
            edge.height_mm,
            f"{location}.height_mm",
            exclusive_minimum=0.0,
            maximum=MAXIMUM_DIMENSION_MM,
        )
    else:
        raise DuctNetworkAnalysisError(
            f"{location}.shape must be exactly 'round' or 'rect'"
        )


def _validate_no_cycles(by_id: dict[str, DuctNetworkEdgeInput]) -> None:
    # Each edge has at most one parent, so parent-chain coloring detects cycles in
    # linear time without recursion.
    state: dict[str, int] = {}
    for start in sorted(by_id):
        if state.get(start) == 2:
            continue
        trail: list[str] = []
        current = start
        while current and state.get(current, 0) == 0:
            state[current] = 1
            trail.append(current)
            current = by_id[current].parent_id
        if current and state.get(current) == 1:
            raise DuctNetworkAnalysisError(f"duct tree contains a cycle at {current!r}")
        for edge_id in trail:
            state[edge_id] = 2


def _rooted_traversal(
    root_id: str,
    children: dict[str, list[str]],
) -> tuple[list[str], dict[str, int]]:
    traversal: list[str] = []
    depths = {root_id: 1}
    stack = [root_id]
    while stack:
        edge_id = stack.pop()
        traversal.append(edge_id)
        depth = depths[edge_id]
        if depth > MAXIMUM_DEPTH:
            raise DuctNetworkAnalysisError(
                f"duct tree exceeds the {MAXIMUM_DEPTH} edge depth limit"
            )
        for child_id in reversed(children[edge_id]):
            depths[child_id] = depth + 1
            stack.append(child_id)
    return traversal, depths


def _calculate_edge(
    edge: DuctNetworkEdgeInput,
    derived_flow_m3_h: float,
    settings: DuctNetworkAnalysisSettings,
) -> DuctNetworkEdgeResult:
    if edge.shape == "round":
        diameter_m = edge.diameter_mm / 1_000.0
        area_m2 = math.pi * diameter_m * diameter_m / 4.0
        hydraulic_diameter_m = diameter_m
    else:
        width_m = edge.width_mm / 1_000.0
        height_m = edge.height_mm / 1_000.0
        area_m2 = width_m * height_m
        hydraulic_diameter_m = 2.0 * width_m * height_m / (width_m + height_m)

    area_m2 = _require_positive_finite_result(area_m2, f"area for edge {edge.edge_id!r}")
    hydraulic_diameter_m = _require_positive_finite_result(
        hydraulic_diameter_m, f"hydraulic diameter for edge {edge.edge_id!r}"
    )
    velocity_m_s = _require_finite_result(
        (derived_flow_m3_h / 3_600.0) / area_m2,
        f"velocity for edge {edge.edge_id!r}",
    )
    dynamic_pressure_pa = _require_finite_result(
        0.5 * settings.rho_kg_m3 * velocity_m_s * velocity_m_s,
        f"dynamic pressure for edge {edge.edge_id!r}",
    )
    friction_pressure_loss_pa = _require_finite_result(
        settings.darcy_friction_factor
        * edge.length_m
        / hydraulic_diameter_m
        * dynamic_pressure_pa,
        f"friction pressure for edge {edge.edge_id!r}",
    )
    local_pressure_loss_pa = _require_finite_result(
        edge.local_loss_coefficient * dynamic_pressure_pa,
        f"local pressure for edge {edge.edge_id!r}",
    )
    total_pressure_loss_pa = _require_finite_result(
        math.fsum(
            (
                friction_pressure_loss_pa,
                local_pressure_loss_pa,
                edge.fixed_pressure_loss_pa,
                edge.terminal_required_pressure_pa,
            )
        ),
        f"total pressure for edge {edge.edge_id!r}",
    )
    return DuctNetworkEdgeResult(
        edge_id=edge.edge_id,
        parent_id=edge.parent_id,
        terminal_flow_m3_h=float(edge.terminal_flow_m3_h),
        derived_flow_m3_h=derived_flow_m3_h,
        length_m=float(edge.length_m),
        shape=edge.shape,
        diameter_mm=float(edge.diameter_mm),
        width_mm=float(edge.width_mm),
        height_mm=float(edge.height_mm),
        cross_section_area_m2=area_m2,
        hydraulic_diameter_m=hydraulic_diameter_m,
        velocity_m_s=velocity_m_s,
        dynamic_pressure_pa=dynamic_pressure_pa,
        friction_pressure_loss_pa=friction_pressure_loss_pa,
        local_pressure_loss_pa=local_pressure_loss_pa,
        fixed_pressure_loss_pa=float(edge.fixed_pressure_loss_pa),
        terminal_required_pressure_pa=float(edge.terminal_required_pressure_pa),
        total_pressure_loss_pa=total_pressure_loss_pa,
    )


def _require_identifier(value: object, location: str, *, allow_empty: bool) -> str:
    if not isinstance(value, str):
        raise DuctNetworkAnalysisError(f"{location} must be a string")
    if value == "" and allow_empty:
        return value
    if not value or value != value.strip():
        raise DuctNetworkAnalysisError(f"{location} must be nonempty and trimmed")
    if len(value) > MAXIMUM_ID_LENGTH:
        raise DuctNetworkAnalysisError(
            f"{location} exceeds the {MAXIMUM_ID_LENGTH} character limit"
        )
    if any(character.isspace() and character != " " for character in value):
        raise DuctNetworkAnalysisError(f"{location} contains unsupported whitespace")
    if any(not character.isprintable() for character in value):
        raise DuctNetworkAnalysisError(f"{location} contains a control character")
    return value


def _require_exact_zero(value: object, location: str) -> float:
    number = _require_number(value, location, minimum=0.0, maximum=0.0)
    if number != 0.0:
        raise DuctNetworkAnalysisError(f"{location} must be exactly zero")
    return number


def _require_number(
    value: object,
    location: str,
    *,
    minimum: float | None = None,
    exclusive_minimum: float | None = None,
    maximum: float | None = None,
) -> float:
    if isinstance(value, bool) or not isinstance(value, Real):
        raise DuctNetworkAnalysisError(f"{location} must be a real number")
    number = float(value)
    if not math.isfinite(number):
        raise DuctNetworkAnalysisError(f"{location} must be finite")
    if minimum is not None and number < minimum:
        raise DuctNetworkAnalysisError(f"{location} must be at least {minimum}")
    if exclusive_minimum is not None and number <= exclusive_minimum:
        raise DuctNetworkAnalysisError(
            f"{location} must be greater than {exclusive_minimum}"
        )
    if maximum is not None and number > maximum:
        raise DuctNetworkAnalysisError(f"{location} must not exceed {maximum}")
    return number


def _require_finite_result(value: float, location: str) -> float:
    if not math.isfinite(value) or value < 0.0:
        raise DuctNetworkAnalysisError(f"{location} is outside the finite nonnegative range")
    return float(value)


def _require_positive_finite_result(value: float, location: str) -> float:
    if not math.isfinite(value) or value <= 0.0:
        raise DuctNetworkAnalysisError(f"{location} is outside the finite positive range")
    return float(value)


def _require_signed_finite_result(value: float, location: str) -> float:
    if not math.isfinite(value):
        raise DuctNetworkAnalysisError(f"{location} is outside the finite range")
    return 0.0 if value == 0.0 else float(value)


__all__ = [
    "ANALYSIS_METHOD",
    "ANALYSIS_PROFILE_VERSION",
    "DuctNetworkAnalysisError",
    "DuctNetworkAnalysisResult",
    "DuctNetworkAnalysisSettings",
    "DuctNetworkEdgeInput",
    "DuctNetworkEdgeResult",
    "DuctNetworkPathResult",
    "MAXIMUM_DEPTH",
    "MAXIMUM_EDGES",
    "MAXIMUM_PATH_MEMBERSHIPS",
    "analyze_duct_tree",
]
