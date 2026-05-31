# -*- coding: utf-8 -*-
"""HVAC Calculator — пакет для расчёта теплопотерь, теплопоступлений,
вентиляции, дымоудаления, ГВС, энергопаспорта и гидравлики ОВ."""

__version__ = "4.0"

from hvac.project import HVACProject
from hvac.models import Space, BoundaryElement, Construction, ProjectParameters

# Расширения v3.7
from hvac.dew_point import (
    CondensationCheck, dew_point_c, surface_temperature,
    saturation_pressure_pa, ROOM_TYPE_RH_DESIGN,
)
from hvac.dhw import (
    DHWSystem, DHWDemand, DHWNorm, DHW_NORMS,
)
from hvac.energy import (
    EnergyPassport, energy_class_for_deviation, normative_qh,
    BASE_HEATING_NORMS_KWH_M2,
)
from hvac.duct_sizing import (
    DuctSection, DuctNetwork, pick_round_diameter, pick_rect_section,
    RECOMMENDED_VELOCITIES,
)
from hvac.pipe_sizing import (
    PipeSection, PipeNetwork, pick_dn, mass_flow_kg_h, volume_flow_m3_h,
)

__all__ = [
    "HVACProject", "Space", "BoundaryElement",
    "Construction", "ProjectParameters", "__version__",
    # v3.7
    "CondensationCheck", "dew_point_c", "surface_temperature",
    "saturation_pressure_pa", "ROOM_TYPE_RH_DESIGN",
    "DHWSystem", "DHWDemand", "DHWNorm", "DHW_NORMS",
    "EnergyPassport", "energy_class_for_deviation", "normative_qh",
    "BASE_HEATING_NORMS_KWH_M2",
    "DuctSection", "DuctNetwork", "pick_round_diameter", "pick_rect_section",
    "RECOMMENDED_VELOCITIES",
    "PipeSection", "PipeNetwork", "pick_dn", "mass_flow_kg_h",
    "volume_flow_m3_h",
]
