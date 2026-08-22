# -*- coding: utf-8 -*-
"""Unified preliminary pump catalog and parallel N+1 selection."""
from __future__ import annotations

from dataclasses import dataclass
import math


@dataclass(frozen=True)
class PumpModel:
    name: str
    q_max_m3_h: float
    h_max_m: float
    pump_type: str = ""
    power_w: float = 0.0


@dataclass(frozen=True)
class PumpPick:
    model: PumpModel
    required_flow_m3_h: float
    required_head_m: float
    working_units: int
    reserve_units: int

    @property
    def installed_units(self) -> int:
        return self.working_units + self.reserve_units


PUMP_MODELS: tuple[PumpModel, ...] = (
    PumpModel("Grundfos UPS 25-40 180", 2.5, 4.0, "wet_rotor", 45),
    PumpModel("Grundfos UPS 25-60 180", 3.5, 6.0, "wet_rotor", 65),
    PumpModel("Grundfos UPS 25-80 180", 4.5, 8.0, "wet_rotor", 0),
    PumpModel("Grundfos UPS 32-80 180", 6.0, 8.0, "wet_rotor", 0),
    PumpModel("Grundfos Magna1 25-60", 4.0, 6.0, "ec_wet_rotor", 0),
    PumpModel("Grundfos Magna1 32-100", 9.0, 10.0, "ec_wet_rotor", 180),
    PumpModel("Grundfos Magna1 40-120 F", 16.0, 12.0, "ec_wet_rotor", 0),
    PumpModel("Grundfos Magna1 50-100 F", 25.0, 10.0, "ec_wet_rotor", 0),
    PumpModel("Grundfos Magna1 65-120 F", 45.0, 12.0, "ec_wet_rotor", 0),
    PumpModel("Grundfos Magna3 80-100 F", 70.0, 10.0, "ec_wet_rotor", 0),
    PumpModel("Grundfos Magna3 100-120 F", 120.0, 12.0, "ec_wet_rotor", 0),
    PumpModel("Grundfos TPE 80-120", 150.0, 12.0, "inline_dry", 0),
    PumpModel("Grundfos TPE 100-200", 300.0, 20.0, "inline_dry", 0),
)


def select_pump_units(
    flow_m3_h: float,
    head_m: float,
    *,
    flow_reserve: float = 1.10,
    head_reserve: float = 1.30,
    reserve_units: int = 1,
    max_working_units: int = 4,
    catalog_tolerance: float = 0.01,
) -> PumpPick | None:
    """Select equal pumps in parallel and add explicit N+1 reserve.

    The one-percent tolerance prevents rounded envelope points such as
    300.0 m³/h from failing a 300.5 m³/h preliminary requirement.
    """
    if flow_m3_h <= 0.0 or head_m <= 0.0:
        return None
    q_required = flow_m3_h * max(flow_reserve, 0.0)
    h_required = head_m * max(head_reserve, 0.0)
    tolerance = max(0.0, catalog_tolerance)
    variants: list[tuple[int, float, PumpModel]] = []
    for model in PUMP_MODELS:
        if model.h_max_m * (1.0 + tolerance) < h_required:
            continue
        effective_q = model.q_max_m3_h * (1.0 + tolerance)
        working = int(math.ceil(q_required / effective_q - 1e-9))
        if not 0 < working <= max_working_units:
            continue
        flow_margin = abs(working * model.q_max_m3_h - q_required)
        variants.append((working, flow_margin, model))
    if not variants:
        return None
    working, _margin, model = min(
        variants, key=lambda item: (item[0], item[1], item[2].q_max_m3_h),
    )
    return PumpPick(
        model=model,
        required_flow_m3_h=q_required,
        required_head_m=h_required,
        working_units=working,
        reserve_units=max(0, int(reserve_units)),
    )
