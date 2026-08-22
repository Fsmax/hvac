# -*- coding: utf-8 -*-
"""Сохранение/загрузка проекта в JSON.

v3.8: проект может сохраняться ПОЛНОСТЬЮ (со всеми помещениями и
ограждениями) — для проектов, созданных вручную без Revit.
Если все помещения помечены manual_entry=True или CSV-пути пусты,
то save_project автоматически записывает полную геометрию в JSON,
и проект полностью самодостаточен.
"""

from __future__ import annotations
import json
import os
from dataclasses import asdict
from typing import Optional
from hvac.project import HVACProject
from hvac.models import Space, BoundaryElement, ProjectParameters
from hvac.room_equipment import (
    serialize_room_equipment, deserialize_room_equipment,
)


# Поля Space, которые сохраняются как пользовательские override
SAVED_SPACE_FIELDS = [
    "room_type", "t_in_heat", "t_in_cool", "occupancy_people",
    "lighting_w_m2", "equipment_w_m2", "ach_inf",
    "is_corner", "has_floor_to_ground", "has_roof", "is_top_floor",
    "floor_over_unheated_n",
    "user_modified",
    # Вентиляция (если пользователь правил)
    "supply_m3h", "exhaust_m3h", "hood_m3h", "vent_user_modified",
    # Санитарные приборы (расчёт вытяжки санузлов)
    "wc_count", "urinal_count",
    # Бассейны (влагоудаление)
    "water_surface_m2", "water_temp_c",
    # Зрители (спорт) / машино-места (парковки)
    "spectator_count", "car_count",
    # Блок здания (раздел «Блоки»)
    "block",
    # Зоны / системы
    "system_heating", "system_cooling", "system_ventilation",
    # Раздельная привязка притока/вытяжки (переопределения)
    "system_supply", "system_exhaust",
    # Контуры внутри систем
    "circuit_heating", "circuit_cooling", "duct_zone",
    # Воздушное отопление / охлаждение
    "air_heating", "air_cooling",
    # Тепловой баланс (ручная классификация отапл./охлажд.)
    "is_heated", "is_cooled",
    # Аварийные системы
    "smoke_system", "pressurization_system", "smoke_zone_index",
]

# v3.8: полный набор полей Space (для самодостаточного сохранения)
FULL_SPACE_FIELDS = [
    "space_id", "number", "name", "level", "area_m2", "volume_m3", "height_m",
    "room_type", "t_in_heat", "t_in_cool", "occupancy_people",
    "lighting_w_m2", "equipment_w_m2", "ach_inf", "rh_design",
    "is_corner", "has_floor_to_ground", "has_roof", "is_top_floor",
    "floor_over_unheated_n",
    "user_modified", "manual_entry",
    "supply_m3h", "exhaust_m3h", "hood_m3h", "ach_calculated",
    "vent_user_modified",
    "wc_count", "urinal_count",
    "water_surface_m2", "water_temp_c",
    "spectator_count", "car_count",
    "block",
    "system_heating", "system_cooling", "system_ventilation",
    "system_supply", "system_exhaust",
    "circuit_heating", "circuit_cooling", "duct_zone",
    "air_heating", "air_cooling",
    "is_heated", "is_cooled",
    "smoke_system", "pressurization_system", "smoke_zone_index",
    "heat_loss_w", "heat_gain_w",
    "heat_gain_sensible_w", "heat_gain_latent_w",
]

# v3.8: полный набор полей BoundaryElement
FULL_ELEMENT_FIELDS = [
    "space_id", "row_type", "is_exterior", "element_id", "category",
    "family", "type_name", "boundary_length_m", "space_height_m",
    "approx_area_m2", "element_area_m2", "thickness_mm", "function",
    "host_element_id", "boundary_space_count",
    "construction_key", "orientation_deg", "orientation",
    "u_value", "net_area_m2", "manual_entry", "user_modified",
]

# Поля ручных правок ограждения (панель «Ограждения»): сохраняются как
# element_overrides в CSV-режиме и накладываются поверх элементов из CSV.
# Покрывает «внутреннее/наружное», смену конструкции, ориентацию и площадь.
SAVED_ELEMENT_FIELDS = [
    "is_exterior", "orientation", "orientation_deg",
    "construction_key", "u_value", "family", "type_name", "category",
    "thickness_mm", "approx_area_m2", "element_area_m2", "net_area_m2",
]


def _serialize_space_full(sp: Space) -> dict:
    """Полное сохранение помещения (для self-contained проекта).
    Включает все поля + room_equipment."""
    out = {f: getattr(sp, f) for f in FULL_SPACE_FIELDS if hasattr(sp, f)}
    if sp.room_equipment is not None:
        out["room_equipment"] = serialize_room_equipment(sp.room_equipment)
    return out


def _serialize_element_full(el: BoundaryElement) -> dict:
    """Полное сохранение граничного элемента."""
    return {f: getattr(el, f) for f in FULL_ELEMENT_FIELDS if hasattr(el, f)}


def _is_self_contained(project: HVACProject) -> bool:
    """Проект «самодостаточный» если:
    - нет CSV-путей, или
    - хотя бы одно помещение manual_entry=True, или
    - CSV-файлы недоступны.
    В таком случае сохраняем ПОЛНУЮ геометрию.
    """
    if not project.spaces_csv_path or not project.thermal_csv_path:
        return True
    if any(getattr(sp, "manual_entry", False) for sp in project.spaces):
        return True
    if not os.path.exists(project.spaces_csv_path):
        return True
    if not os.path.exists(project.thermal_csv_path):
        return True
    return False


def save_project(project: HVACProject, path: str,
                 force_self_contained: bool = False) -> None:
    """Сохраняет проект в JSON.

    Режимы:
    - Если проект полностью или частично создан вручную, либо CSV недоступны:
      сохраняется ПОЛНАЯ геометрия (помещения + ограждения + оборудование).
    - Иначе: сохраняются только настройки (геометрия в CSV).

    force_self_contained=True заставляет сохранить полную геометрию
    в любом случае (полезно для архивации проекта).
    """
    self_contained = force_self_contained or _is_self_contained(project)

    # Сохраняем оборудование для ВСЕХ помещений, у которых оно есть
    equipment_data = {}
    for sp in project.spaces:
        if sp.room_equipment is not None:
            equipment_data[sp.space_id] = serialize_room_equipment(sp.room_equipment)

    data = {
        "version": "3.8",
        "self_contained": self_contained,
        "params": asdict(project.params),
        "spaces_csv_path": project.spaces_csv_path if not self_contained else "",
        "thermal_csv_path": project.thermal_csv_path if not self_contained else "",
        "constructions": {k: asdict(c) for k, c in project.constructions.items()},
        # v3.8: оборудование помещений
        "room_equipment": equipment_data,
        # Реестр блоков здания (раздел «Блоки»)
        "blocks": list(getattr(project, "blocks", []) or []),
        # Системы оборудования
        "ventilation_systems": {k: asdict(v) for k, v in project.ventilation_systems.items()},
        "heating_systems": {k: asdict(v) for k, v in project.heating_systems.items()},
        "cooling_systems": {k: asdict(v) for k, v in project.cooling_systems.items()},
        # Контуры внутри систем + зоны воздуховодов
        "heating_circuits": {k: asdict(v) for k, v in project.heating_circuits.items()},
        "cooling_circuits": {k: asdict(v) for k, v in project.cooling_circuits.items()},
        "duct_zones": {k: asdict(v) for k, v in project.duct_zones.items()},
        "smoke_systems": {k: asdict(v) for k, v in project.smoke_systems.items()},
        "dhw_systems": {k: asdict(v) for k, v in project.dhw_systems.items()},
        "duct_networks": {
            k: _serialize_duct_network(v)
            for k, v in project.duct_networks.items()
        },
        "pipe_networks": {
            k: _serialize_pipe_network(v)
            for k, v in project.pipe_networks.items()
        },
        "cooling_pipe_networks": {
            k: _serialize_pipe_network(v)
            for k, v in project.cooling_pipe_networks.items()
        },
        "energy_passport": (asdict(project.energy_passport)
                            if project.energy_passport else None),
        "ahu_loads": project.ahu_loads,
        # ===== v4.1 — результаты подробной инженерии =====
        "ahu_processes": _serialize_ahu_processes(
            getattr(project, "ahu_processes", {})),
        "heating_hydraulics_results": _serialize_hydraulics(
            getattr(project, "heating_hydraulics_results", {})),
        "radiator_picks": _serialize_radiator_picks(
            getattr(project, "radiator_picks", {})),
        "acoustics_results": _serialize_acoustics(
            getattr(project, "acoustics_results", {})),
        "duct_networks_detailed": _serialize_detailed_ducts(
            getattr(project, "duct_networks_detailed", {})),
        # ===== v4.2 =====
        "underfloor_loops": _serialize_underfloor_loops(
            getattr(project, "underfloor_loops", {})),
        "fancoil_picks": _serialize_fancoil_picks(
            getattr(project, "fancoil_picks", {})),
        "vrf_systems": _serialize_vrf_systems(
            getattr(project, "vrf_systems", {})),
        # ===== v4.4 =====
        "grille_picks": _serialize_grille_picks(
            getattr(project, "grille_picks", {})),
    }

    if self_contained:
        # Полное сохранение геометрии
        data["spaces"] = [_serialize_space_full(sp) for sp in project.spaces]
        data["elements"] = [_serialize_element_full(el) for el in project.elements]
    else:
        # Старый режим: сохраняем только пользовательские правки
        data["space_overrides"] = {
            sp.space_id: {f: getattr(sp, f) for f in SAVED_SPACE_FIELDS}
            for sp in project.spaces
            if sp.user_modified or sp.vent_user_modified
            or sp.block
            or sp.system_heating or sp.system_cooling or sp.system_ventilation
            or sp.system_supply or sp.system_exhaust
            or sp.circuit_heating or sp.circuit_cooling or sp.duct_zone
            or sp.air_heating or sp.air_cooling
            or not sp.is_heated or not sp.is_cooled
            or sp.smoke_system or sp.pressurization_system
        }
        # Ручные правки ограждений (внутреннее/наружное, конструкция,
        # ориентация, площадь). Сохраняем списком записей с ключом
        # (space_id, element_id) — element_id может повторяться у общих стен.
        data["element_overrides"] = [
            {"space_id": e.space_id, "element_id": e.element_id,
             **{f: getattr(e, f) for f in SAVED_ELEMENT_FIELDS}}
            for e in project.elements
            if getattr(e, "user_modified", False) and e.element_id
        ]

    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2, default=str)


def _serialize_duct_network(net) -> dict:
    """Сериализация DuctNetwork с вложенными секциями."""
    return {
        "system_name": net.system_name,
        "role": net.role,
        "parent_ahu": getattr(net, "parent_ahu", ""),
        "zone_name": getattr(net, "zone_name", ""),
        "total_flow_m3h": net.total_flow_m3h,
        "n_terminals": net.n_terminals,
        "total_pressure_loss_pa": net.total_pressure_loss_pa,
        "has_zone_fan": getattr(net, "has_zone_fan", False),
        "zone_fan_flow_m3_h": getattr(net, "zone_fan_flow_m3_h", 0.0),
        "zone_fan_pressure_pa": getattr(net, "zone_fan_pressure_pa", 0.0),
        "building_type": net.building_type,
        "note": net.note,
        "sections": [asdict(s) for s in net.sections],
    }


def _serialize_pipe_network(net) -> dict:
    """Сериализация PipeNetwork с вложенными секциями."""
    return {
        "system_name": net.system_name,
        "parent_system": getattr(net, "parent_system", ""),
        "circuit_type": getattr(net, "circuit_type", ""),
        "medium": getattr(net, "medium", "heating"),
        "total_heat_load_w": net.total_heat_load_w,
        "total_flow_kg_h": net.total_flow_kg_h,
        "delta_t_k": net.delta_t_k,
        "t_supply_c": getattr(net, "t_supply_c", 80.0),
        "t_return_c": getattr(net, "t_return_c", 60.0),
        "n_terminals": net.n_terminals,
        "total_pressure_loss_pa": net.total_pressure_loss_pa,
        "pump_head_m": getattr(net, "pump_head_m", 0.0),
        "pump_flow_m3_h": getattr(net, "pump_flow_m3_h", 0.0),
        "pump_model": getattr(net, "pump_model", ""),
        "pump_working_units": getattr(net, "pump_working_units", 0),
        "pump_reserve_units": getattr(net, "pump_reserve_units", 0),
        "pump_catalog_covered": getattr(net, "pump_catalog_covered", True),
        "pipe_material": net.pipe_material,
        "insulated": getattr(net, "insulated", False),
        "note": net.note,
        "sections": [asdict(s) for s in net.sections],
    }


# ============================================================================
# v4.1 — сериализация результатов подробной инженерии
# ============================================================================

def _serialize_ahu_processes(processes: dict) -> dict:
    """{ahu: {mode: AHUProcess}} → JSON-совместимая структура."""
    out: dict = {}
    for ahu, by_mode in processes.items():
        out[ahu] = {}
        for mode, proc in by_mode.items():
            out[ahu][mode] = {
                "ahu_name": proc.ahu_name,
                "mode": proc.mode,
                "mass_flow_kg_s": proc.mass_flow_kg_s,
                "volume_flow_m3_h": proc.volume_flow_m3_h,
                "recirculation_ratio": proc.recirculation_ratio,
                "q_recovery_kw": proc.q_recovery_kw,
                "q_heater_kw": proc.q_heater_kw,
                "q_cooler_total_kw": proc.q_cooler_total_kw,
                "q_cooler_sensible_kw": proc.q_cooler_sensible_kw,
                "q_cooler_latent_kw": proc.q_cooler_latent_kw,
                "q_humidifier_kw": proc.q_humidifier_kw,
                "humidifier_water_kg_h": proc.humidifier_water_kg_h,
                "condensate_kg_h": proc.condensate_kg_h,
                "points": {
                    name: {"t_c": s.t_c, "W": s.W, "p": s.p}
                    for name, s in proc.points.items()
                },
            }
    return out


def _deserialize_ahu_processes(data: dict) -> dict:
    from hvac.ahu_process import AHUProcess
    from hvac.psychro import AirState
    out: dict = {}
    for ahu, by_mode in data.items():
        out[ahu] = {}
        for mode, d in by_mode.items():
            proc = AHUProcess(ahu_name=d.get("ahu_name", ahu),
                                mode=d.get("mode", mode))
            proc.mass_flow_kg_s = d.get("mass_flow_kg_s", 0.0)
            proc.volume_flow_m3_h = d.get("volume_flow_m3_h", 0.0)
            proc.recirculation_ratio = d.get("recirculation_ratio", 0.0)
            proc.q_recovery_kw = d.get("q_recovery_kw", 0.0)
            proc.q_heater_kw = d.get("q_heater_kw", 0.0)
            proc.q_cooler_total_kw = d.get("q_cooler_total_kw", 0.0)
            proc.q_cooler_sensible_kw = d.get("q_cooler_sensible_kw", 0.0)
            proc.q_cooler_latent_kw = d.get("q_cooler_latent_kw", 0.0)
            proc.q_humidifier_kw = d.get("q_humidifier_kw", 0.0)
            proc.humidifier_water_kg_h = d.get("humidifier_water_kg_h", 0.0)
            proc.condensate_kg_h = d.get("condensate_kg_h", 0.0)
            proc.points = {
                name: AirState(t_c=p["t_c"], W=p["W"],
                                 p=p.get("p", 101325.0))
                for name, p in (d.get("points") or {}).items()
            }
            out[ahu][mode] = proc
    return out


def _serialize_hydraulics(results: dict) -> dict:
    out = {}
    for name, r in results.items():
        out[name] = {
            "network_name": r.network_name,
            "pump": asdict(r.pump),
            "expansion_tank": asdict(r.expansion_tank),
            "makeup": asdict(r.makeup),
        }
    return out


def _deserialize_hydraulics(data: dict) -> dict:
    from hvac.heating_hydraulics import (
        ExpansionTank, HeatingHydraulicsResult, MakeupValveSpec,
        PumpRequirement,
    )
    out = {}

    def _build(cls, info):
        valid = {k: v for k, v in (info or {}).items()
                 if k in cls.__dataclass_fields__}
        return cls(**valid)

    for name, d in data.items():
        out[name] = HeatingHydraulicsResult(
            network_name=d.get("network_name", name),
            pump=_build(PumpRequirement, d.get("pump")),
            expansion_tank=_build(ExpansionTank, d.get("expansion_tank")),
            makeup=_build(MakeupValveSpec, d.get("makeup")),
        )
    return out


def _serialize_radiator_picks(picks: dict) -> dict:
    """{space_id: RadiatorPick} → сериализованное представление."""
    out = {}
    for sid, p in picks.items():
        out[sid] = {
            "model_name": p.model.name,
            "model_family": p.model.family,
            "model_q_nominal_w": p.model.q_nominal_w,
            "model_n_exponent": p.model.n_exponent,
            "model_is_sectional": p.model.is_sectional,
            "model_height_mm": p.model.height_mm,
            "model_length_mm": p.model.length_mm,
            "sections": p.sections,
            "actual_power_w": p.actual_power_w,
            "margin_pct": p.margin_pct,
            "note": p.note,
        }
    return out


def _deserialize_radiator_picks(data: dict) -> dict:
    from hvac.radiator_catalog import RADIATOR_CATALOG, RadiatorModel, RadiatorPick
    by_name = {m.name: m for m in RADIATOR_CATALOG}
    out = {}
    for sid, d in data.items():
        m = by_name.get(d.get("model_name", ""))
        if m is None:
            # Каталог изменился — восстанавливаем минимальную копию
            m = RadiatorModel(
                name=d.get("model_name", ""),
                family=d.get("model_family", ""),
                height_mm=d.get("model_height_mm", 0),
                length_mm=d.get("model_length_mm", 0),
                q_nominal_w=d.get("model_q_nominal_w", 0.0),
                n_exponent=d.get("model_n_exponent", 1.30),
                is_sectional=d.get("model_is_sectional", False),
            )
        out[sid] = RadiatorPick(
            model=m,
            sections=d.get("sections", 1),
            actual_power_w=d.get("actual_power_w", 0.0),
            margin_pct=d.get("margin_pct", 0.0),
            note=d.get("note", ""),
        )
    return out


def _serialize_grille_pick(p) -> Optional[dict]:
    """GrillePick → dict (или None)."""
    if p is None:
        return None
    return {
        "family_code": p.model.family_code,
        "size_label": p.model.size_label(),
        "label": p.model.label(),
        "mount": p.model.mount,
        "n_units": p.n_units,
        "l0_per_unit": p.l0_per_unit,
        "l0_total": p.l0_total,
        "velocity": p.velocity,
        "lwa": p.lwa,
        "dp": p.dp,
        "throw_05": p.throw_05,
        "warnings": list(p.warnings),
    }


def _serialize_grille_picks(picks: dict) -> dict:
    """{space_id: GrilleRoomPick} → сериализованное представление.

    Хранится «снимок» подбора (модель восстанавливается по каталогу при
    загрузке через _deserialize_grille_picks).
    """
    out = {}
    for sid, rp in picks.items():
        out[sid] = {
            "supply": _serialize_grille_pick(getattr(rp, "supply", None)),
            "exhaust": _serialize_grille_pick(getattr(rp, "exhaust", None)),
        }
    return out


def _deserialize_grille_pick(d: Optional[dict]):
    if not d:
        return None
    from hvac.grille_catalog import GRILLE_CATALOG, GrillePick
    by_key = {(m.family_code, m.size_label()): m for m in GRILLE_CATALOG}
    model = by_key.get((d.get("family_code", ""), d.get("size_label", "")))
    if model is None:
        return None        # каталог изменился — снимок не восстановим
    return GrillePick(
        model=model,
        n_units=d.get("n_units", 1),
        l0_per_unit=d.get("l0_per_unit", 0.0),
        l0_total=d.get("l0_total", 0.0),
        velocity=d.get("velocity", 0.0),
        lwa=d.get("lwa"),
        dp=d.get("dp"),
        throw_05=d.get("throw_05"),
        warnings=list(d.get("warnings", [])),
    )


def _deserialize_grille_picks(data: dict) -> dict:
    from hvac.grille_catalog import GrilleRoomPick
    out = {}
    for sid, d in (data or {}).items():
        out[sid] = GrilleRoomPick(
            supply=_deserialize_grille_pick(d.get("supply")),
            exhaust=_deserialize_grille_pick(d.get("exhaust")),
        )
    return out


def _serialize_acoustics(results: dict) -> dict:
    out = {}
    for name, a in results.items():
        out[name] = {
            "lp_at_terminal": dict(a.lp_at_terminal),
            "lpa_at_terminal": a.lpa_at_terminal,
            "lpa_required_dba": a.lpa_required_dba,
            "margin_dba": a.margin_dba,
            "silencer_required": a.silencer_required,
            "silencer_name": (a.silencer_selected.name
                                if a.silencer_selected else ""),
            "silencer_length_mm": (a.silencer_selected.length_mm
                                     if a.silencer_selected else 0),
            "silencer_pressure_drop_pa": (
                a.silencer_selected.pressure_drop_pa
                if a.silencer_selected else 0.0),
            "silencer_insertion_loss": (
                dict(a.silencer_selected.insertion_loss)
                if a.silencer_selected else {}),
        }
    return out


def _deserialize_acoustics(data: dict) -> dict:
    from hvac.acoustics import AcousticAnalysis, Silencer, zero_spectrum
    out = {}
    for name, d in data.items():
        sp = {int(k): v for k, v in (d.get("lp_at_terminal") or {}).items()}
        silencer = None
        if d.get("silencer_name"):
            il = {int(k): v for k, v in
                  (d.get("silencer_insertion_loss") or {}).items()}
            silencer = Silencer(
                name=d["silencer_name"],
                length_mm=d.get("silencer_length_mm", 0),
                insertion_loss=il or zero_spectrum(),
                pressure_drop_pa=d.get("silencer_pressure_drop_pa", 0.0),
            )
        out[name] = AcousticAnalysis(
            lp_at_terminal=sp or zero_spectrum(),
            lpa_at_terminal=d.get("lpa_at_terminal", 0.0),
            lpa_required_dba=d.get("lpa_required_dba", 0.0),
            margin_dba=d.get("margin_dba", 0.0),
            silencer_selected=silencer,
            silencer_required=d.get("silencer_required", False),
        )
    return out


def _serialize_detailed_ducts(networks: dict) -> dict:
    """Топология DuctNetworkDetailed (без расчётных полей — пересчитаются)."""
    out = {}
    for name, n in networks.items():
        out[name] = {
            "system_name": n.system_name,
            "role": n.role,
            "rho_kg_m3": n.rho_kg_m3,
            "friction_factor": n.friction_factor,
            "fan_safety_factor": n.fan_safety_factor,
            "note": n.note,
            "edges": [
                {
                    "edge_id": e.edge_id,
                    "parent_id": e.parent_id,
                    "flow_m3_h": e.flow_m3_h,
                    "length_m": e.length_m,
                    "shape": e.shape,
                    "diameter_mm": e.diameter_mm,
                    "width_mm": e.width_mm,
                    "height_mm": e.height_mm,
                    "terminal_name": e.terminal_name,
                    "is_terminal": e.is_terminal,
                    "note": e.note,
                    "fittings": [
                        {"kind": f.kind, "zeta": f.zeta,
                         "extra_pressure_pa": f.extra_pressure_pa,
                         "quantity": f.quantity, "note": f.note}
                        for f in e.fittings
                    ],
                }
                for e in n.edges.values()
            ],
        }
    return out


def _deserialize_detailed_ducts(data: dict) -> dict:
    from hvac.duct_network import DuctEdge, DuctFitting, DuctNetworkDetailed
    out = {}
    for name, d in data.items():
        net = DuctNetworkDetailed(
            system_name=d.get("system_name", name),
            role=d.get("role", "supply"),
            rho_kg_m3=d.get("rho_kg_m3", 1.20),
            friction_factor=d.get("friction_factor", 0.022),
            fan_safety_factor=d.get("fan_safety_factor", 1.10),
            note=d.get("note", ""),
        )
        for ed in d.get("edges", []):
            edge = DuctEdge(
                edge_id=ed.get("edge_id", ""),
                parent_id=ed.get("parent_id", ""),
                flow_m3_h=ed.get("flow_m3_h", 0.0),
                length_m=ed.get("length_m", 0.0),
                shape=ed.get("shape", "round"),
                diameter_mm=ed.get("diameter_mm", 0.0),
                width_mm=ed.get("width_mm", 0.0),
                height_mm=ed.get("height_mm", 0.0),
                terminal_name=ed.get("terminal_name", ""),
                is_terminal=ed.get("is_terminal", False),
                note=ed.get("note", ""),
            )
            for fd in ed.get("fittings", []):
                edge.fittings.append(DuctFitting(
                    kind=fd.get("kind", ""),
                    zeta=fd.get("zeta"),
                    extra_pressure_pa=fd.get("extra_pressure_pa", 0.0),
                    quantity=fd.get("quantity", 1),
                    note=fd.get("note", ""),
                ))
            net.add_edge(edge)
        net.compute()
        out[name] = net
    return out


# ============================================================================
# v4.2 — сериализация underfloor / fancoils / VRF
# ============================================================================

def _serialize_underfloor_loops(loops: dict) -> dict:
    out = {}
    for sid, loop in loops.items():
        out[sid] = {
            "name": loop.name,
            "room_id": loop.room_id,
            "area_m2": loop.area_m2,
            "q_required_w": loop.q_required_w,
            "pipe_name": loop.pipe.name if loop.pipe else "",
            "pitch_mm": loop.pitch_mm,
            "cover": loop.cover,
            "zone": loop.zone,
            "t_supply_c": loop.t_supply_c,
            "t_return_c": loop.t_return_c,
            "t_room_c": loop.t_room_c,
            "q_actual_w_m2": loop.q_actual_w_m2,
            "q_actual_w": loop.q_actual_w,
            "t_floor_surface_c": loop.t_floor_surface_c,
            "t_floor_limit_c": loop.t_floor_limit_c,
            "pipe_length_m": loop.pipe_length_m,
            "flow_kg_h": loop.flow_kg_h,
            "pressure_drop_kpa": loop.pressure_drop_kpa,
            "warnings": list(loop.warnings),
        }
    return out


def _deserialize_underfloor_loops(data: dict) -> dict:
    from hvac.underfloor import PIPE_CATALOG, UnderfloorLoop
    by_name = {p.name: p for p in PIPE_CATALOG}
    out = {}
    for sid, d in data.items():
        loop = UnderfloorLoop(
            name=d.get("name", ""),
            room_id=d.get("room_id", ""),
            area_m2=d.get("area_m2", 0.0),
            q_required_w=d.get("q_required_w", 0.0),
            pipe=by_name.get(d.get("pipe_name", "")),
            pitch_mm=d.get("pitch_mm", 150),
            cover=d.get("cover", "tile"),
            zone=d.get("zone", "habitable"),
            t_supply_c=d.get("t_supply_c", 45.0),
            t_return_c=d.get("t_return_c", 35.0),
            t_room_c=d.get("t_room_c", 20.0),
            q_actual_w_m2=d.get("q_actual_w_m2", 0.0),
            q_actual_w=d.get("q_actual_w", 0.0),
            t_floor_surface_c=d.get("t_floor_surface_c", 0.0),
            t_floor_limit_c=d.get("t_floor_limit_c", 0.0),
            pipe_length_m=d.get("pipe_length_m", 0.0),
            flow_kg_h=d.get("flow_kg_h", 0.0),
            pressure_drop_kpa=d.get("pressure_drop_kpa", 0.0),
            warnings=list(d.get("warnings", [])),
        )
        out[sid] = loop
    return out


def _serialize_fancoil_picks(picks: dict) -> dict:
    out = {}
    for sid, p in picks.items():
        out[sid] = {
            "model_name": p.model.name,
            "model_family": p.model.family,
            "model_pipes": p.model.pipes,
            "model_q_cool_nom_w": p.model.q_cool_nom_w,
            "model_q_heat_nom_w": p.model.q_heat_nom_w,
            "model_air_flow_m3_h": p.model.air_flow_m3_h,
            "model_noise_db_a": p.model.noise_db_a,
            "actual_cool_w": p.actual_cool_w,
            "actual_heat_w": p.actual_heat_w,
            "cool_margin_pct": p.cool_margin_pct,
            "heat_margin_pct": p.heat_margin_pct,
            "note": p.note,
        }
    return out


def _deserialize_fancoil_picks(data: dict) -> dict:
    from hvac.fancoil_catalog import FANCOIL_CATALOG, FancoilModel, FancoilPick
    by_name = {m.name: m for m in FANCOIL_CATALOG}
    out = {}
    for sid, d in data.items():
        m = by_name.get(d.get("model_name", ""))
        if m is None:
            m = FancoilModel(
                name=d.get("model_name", ""),
                family=d.get("model_family", ""),
                pipes=d.get("model_pipes", 4),
                q_cool_nom_w=d.get("model_q_cool_nom_w", 0.0),
                q_heat_nom_w=d.get("model_q_heat_nom_w", 0.0),
                air_flow_m3_h=d.get("model_air_flow_m3_h", 0.0),
                noise_db_a=d.get("model_noise_db_a", 0.0),
            )
        out[sid] = FancoilPick(
            model=m,
            actual_cool_w=d.get("actual_cool_w", 0.0),
            actual_heat_w=d.get("actual_heat_w", 0.0),
            cool_margin_pct=d.get("cool_margin_pct", 0.0),
            heat_margin_pct=d.get("heat_margin_pct", 0.0),
            note=d.get("note", ""),
        )
    return out


def _serialize_vrf_systems(systems: dict) -> dict:
    out = {}
    for name, sys in systems.items():
        out[name] = {
            "name": sys.name,
            "outdoor_name": sys.outdoor.name if sys.outdoor else "",
            "indoors": [
                {
                    "indoor_name": a.indoor.name,
                    "indoor_capacity_index": a.indoor.capacity_index,
                    "indoor_family": a.indoor.family,
                    "space_id": a.space_id,
                    "pipe_length_m": a.pipe_length_m,
                    "height_diff_m": a.height_diff_m,
                }
                for a in sys.indoors
            ],
            "main_pipe_length_m": sys.main_pipe_length_m,
            "max_pipe_length_to_indoor_m": sys.max_pipe_length_to_indoor_m,
            "max_height_diff_m": sys.max_height_diff_m,
            "combination_ratio": sys.combination_ratio,
            "total_indoor_capacity_index": sys.total_indoor_capacity_index,
            "capacity_correction_factor": sys.capacity_correction_factor,
            "corrected_cool_w": sys.corrected_cool_w,
            "corrected_heat_w": sys.corrected_heat_w,
        }
    return out


def _deserialize_vrf_systems(data: dict) -> dict:
    from hvac.vrf import (
        INDOOR_CATALOG, OUTDOOR_CATALOG, VRFIndoorAssignment, VRFIndoorUnit,
        VRFSystem,
    )
    indoor_by_name = {m.name: m for m in INDOOR_CATALOG}
    outdoor_by_name = {m.name: m for m in OUTDOOR_CATALOG}
    out = {}
    for name, d in data.items():
        outdoor = outdoor_by_name.get(d.get("outdoor_name", ""))
        indoors = []
        for i_data in d.get("indoors", []):
            idu = indoor_by_name.get(i_data.get("indoor_name", ""))
            if idu is None:
                idu = VRFIndoorUnit(
                    name=i_data.get("indoor_name", ""),
                    family=i_data.get("indoor_family", ""),
                    capacity_index=i_data.get("indoor_capacity_index", 0),
                )
            indoors.append(VRFIndoorAssignment(
                indoor=idu,
                space_id=i_data.get("space_id", ""),
                pipe_length_m=i_data.get("pipe_length_m", 0.0),
                height_diff_m=i_data.get("height_diff_m", 0.0),
            ))
        sys = VRFSystem(
            name=d.get("name", name),
            outdoor=outdoor,
            indoors=indoors,
            main_pipe_length_m=d.get("main_pipe_length_m", 0.0),
            max_pipe_length_to_indoor_m=d.get("max_pipe_length_to_indoor_m", 0.0),
            max_height_diff_m=d.get("max_height_diff_m", 0.0),
            combination_ratio=d.get("combination_ratio", 0.0),
            total_indoor_capacity_index=d.get("total_indoor_capacity_index", 0),
            capacity_correction_factor=d.get("capacity_correction_factor", 1.0),
            corrected_cool_w=d.get("corrected_cool_w", 0.0),
            corrected_heat_w=d.get("corrected_heat_w", 0.0),
        )
        out[name] = sys
    return out


def load_project(project: HVACProject, path: str) -> None:
    """Загружает проект из JSON в существующий объект.

    v3.8: поддерживает два режима:
    - "self_contained=True" — вся геометрия в JSON, CSV не нужны.
    - "self_contained=False" (старый) — геометрия из CSV + правки из JSON.
    """
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    # Открытие файла — это ЗАМЕНА состояния, а не слияние: GUI грузит в один
    # долгоживущий объект (main_window._load_project_path, data_panel).
    # Всё, чего нет в открываемом файле, не должно переживать загрузку —
    # иначе системы предыдущего проекта (СДУ, ГВС, вентустановки, ahu_loads)
    # «переезжают» в следующий и печатаются в его записке.
    project._reset_runtime_state()
    project.params = ProjectParameters()

    # Параметры
    for k, v in data.get("params", {}).items():
        if hasattr(project.params, k):
            setattr(project.params, k, v)

    self_contained = data.get("self_contained", False)

    # ===== Режим self-contained: полностью читаем из JSON =====
    if self_contained or "spaces" in data:
        # Сбрасываем геометрию
        project.spaces = []
        project.elements = []
        project.constructions = {}
        project._space_by_id = {}
        project.spaces_csv_path = ""
        project.thermal_csv_path = ""

        # Восстанавливаем помещения
        for sp_data in data.get("spaces", []):
            # Защита от лишних/неизвестных полей
            valid = {k: v for k, v in sp_data.items()
                     if k in Space.__dataclass_fields__ and k != "room_equipment"}
            sp = Space(**{
                "space_id": valid.pop("space_id", ""),
                "number": valid.pop("number", ""),
                "name": valid.pop("name", ""),
                "level": valid.pop("level", ""),
                "area_m2": valid.pop("area_m2", 0.0),
                "volume_m3": valid.pop("volume_m3", 0.0),
                **valid,
            })
            # Восстанавливаем оборудование если есть
            if "room_equipment" in sp_data:
                sp.room_equipment = deserialize_room_equipment(
                    sp_data["room_equipment"])
            project.spaces.append(sp)
            project._space_by_id[sp.space_id] = sp

        # Восстанавливаем граничные элементы (отфильтровывая служебные,
        # которые могли попасть в старые проекты до фикса фильтра)
        from hvac.data_loader import is_excluded_category
        for el_data in data.get("elements", []):
            if is_excluded_category(el_data.get("category", "")):
                continue
            valid = {k: v for k, v in el_data.items()
                     if k in BoundaryElement.__dataclass_fields__}
            # Обеспечиваем обязательные поля
            required_defaults = {
                "space_id": "", "row_type": "external_wall", "is_exterior": True,
                "element_id": "", "category": "", "family": "", "type_name": "",
                "boundary_length_m": 0.0, "space_height_m": 0.0,
                "approx_area_m2": 0.0, "element_area_m2": 0.0,
                "thickness_mm": 0.0, "function": "", "host_element_id": "",
                "boundary_space_count": 1,
            }
            for k, default in required_defaults.items():
                if k not in valid:
                    valid[k] = default
            el = BoundaryElement(**valid)
            project.elements.append(el)

        # Восстанавливаем конструкции (отфильтровывая служебные категории)
        from hvac.models import Construction, Layer
        for key, info in data.get("constructions", {}).items():
            if is_excluded_category(info.get("category", "")):
                continue
            layers_raw = info.get("layers", []) or []
            valid = {k: v for k, v in info.items()
                     if k in Construction.__dataclass_fields__ and k != "layers"}
            con = Construction(**valid)
            con.layers = [
                Layer(**{kk: vv for kk, vv in (l or {}).items()
                         if kk in Layer.__dataclass_fields__})
                for l in layers_raw
            ]
            project.constructions[key] = con

    else:
        # Старый режим: читаем CSV + применяем правки
        spaces_csv = data.get("spaces_csv_path", "")
        thermal_csv = data.get("thermal_csv_path", "")
        if spaces_csv and thermal_csv \
                and os.path.exists(spaces_csv) and os.path.exists(thermal_csv):
            project.load(spaces_csv, thermal_csv)

        # U-значения, слои и note конструкций. Каталог только что пересобран
        # из CSV, поэтому известные ключи обновляем, а отсутствующие
        # восстанавливаем из сохранённого словаря целиком: это конструкции,
        # переименованные через update_construction() или созданные вручную
        # через create_construction() — их ключей в CSV нет, и без
        # восстановления они молча терялись (первый же apply_constructions()
        # пересоздавал запись с дефолтным U вместо пользовательского).
        # Побочный эффект: ключи из сохранённого файла, которых больше нет
        # в CSV (например, после ре-экспорта с переименованными типами),
        # воскресают неиспользуемыми строками каталога — это приемлемо,
        # их убирает «Удалить неиспользуемые».
        from hvac.data_loader import is_excluded_category
        from hvac.models import Construction, Layer
        for key, info in data.get("constructions", {}).items():
            layers = [
                Layer(**{kk: vv for kk, vv in (l or {}).items()
                         if kk in Layer.__dataclass_fields__})
                for l in (info.get("layers", []) or [])
            ]
            if key in project.constructions:
                con = project.constructions[key]
                con.u_value = info.get("u_value", 0)
                con.shgc = info.get("shgc", 0)
                if info.get("note"):
                    con.note = info["note"]
                if layers:
                    con.layers = layers
            else:
                if is_excluded_category(info.get("category", "")):
                    continue
                valid = {k: v for k, v in info.items()
                         if k in Construction.__dataclass_fields__
                         and k != "layers"}
                con = Construction(**valid)
                con.layers = layers
                project.constructions[key] = con

        # Пользовательские настройки помещений
        overrides = data.get("space_overrides", {})
        for sid, ov in overrides.items():
            osp = project.get_space(sid)
            if osp:
                for k, v in ov.items():
                    if hasattr(osp, k):
                        setattr(osp, k, v)

        # Ручные правки ограждений (внутреннее/наружное и пр.) поверх CSV.
        # Ключ — пара (space_id, element_id), т.к. element_id может
        # повторяться у общих стен. Поддерживаем и старый dict-формат.
        elem_overrides = data.get("element_overrides", [])
        if isinstance(elem_overrides, dict):
            elem_overrides = list(elem_overrides.values())
        if elem_overrides:
            by_key = {(o.get("space_id"), o.get("element_id")): o
                      for o in elem_overrides}
            for e in project.elements:
                o = by_key.get((e.space_id, e.element_id))
                if not o:
                    continue
                for k, v in o.items():
                    if k in ("space_id", "element_id"):
                        continue
                    if hasattr(e, k):
                        setattr(e, k, v)
                e.user_modified = True
            project._invalidate_elements_index()

    # ===== Восстанавливаем оборудование помещений (для ОБОИХ режимов) =====
    for sid, eq_data in data.get("room_equipment", {}).items():
        esp = project.get_space(sid)
        if esp:
            esp.room_equipment = deserialize_room_equipment(eq_data)

    # Системы оборудования
    from hvac.equipment import (VentilationSystem, HeatingSystem,
                                 CoolingSystem, HeatingCircuit,
                                 CoolingCircuit, DuctZone)

    def _filter_kwargs(cls, info):
        """Защита от лишних полей в JSON (старые версии файла)."""
        return {k_: v for k_, v in info.items()
                if k_ in cls.__dataclass_fields__}

    # Реестр блоков здания (раздел «Блоки»)
    project.blocks = [str(b) for b in data.get("blocks", []) or [] if str(b).strip()]

    for k, info in data.get("ventilation_systems", {}).items():
        project.ventilation_systems[k] = VentilationSystem(
            **_filter_kwargs(VentilationSystem, info))
    for k, info in data.get("heating_systems", {}).items():
        project.heating_systems[k] = HeatingSystem(
            **_filter_kwargs(HeatingSystem, info))
    for k, info in data.get("cooling_systems", {}).items():
        project.cooling_systems[k] = CoolingSystem(
            **_filter_kwargs(CoolingSystem, info))

    # Контуры и зоны
    for k, info in data.get("heating_circuits", {}).items():
        project.heating_circuits[k] = HeatingCircuit(
            **_filter_kwargs(HeatingCircuit, info))
    for k, info in data.get("cooling_circuits", {}).items():
        project.cooling_circuits[k] = CoolingCircuit(
            **_filter_kwargs(CoolingCircuit, info))
    for k, info in data.get("duct_zones", {}).items():
        project.duct_zones[k] = DuctZone(
            **_filter_kwargs(DuctZone, info))

    # Аварийные системы
    from hvac.smoke import SmokeSystem
    for k, info in data.get("smoke_systems", {}).items():
        project.smoke_systems[k] = SmokeSystem(
            **_filter_kwargs(SmokeSystem, info))

    # ===== Расширения v3.7 =====
    from hvac.dhw import DHWSystem
    for k, info in data.get("dhw_systems", {}).items():
        # Защита от лишних полей в старых файлах
        valid = {k_: v for k_, v in info.items()
                 if k_ in DHWSystem.__dataclass_fields__}
        project.dhw_systems[k] = DHWSystem(**valid)

    # Сети воздуховодов
    from hvac.duct_sizing import DuctSection, DuctNetwork
    for k, info in data.get("duct_networks", {}).items():
        sections = []
        for s in info.get("sections", []):
            valid = {k_: v for k_, v in s.items()
                     if k_ in DuctSection.__dataclass_fields__}
            sections.append(DuctSection(**valid))
        net = DuctNetwork(
            system_name=info.get("system_name", k),
            role=info.get("role", "supply"),
            parent_ahu=info.get("parent_ahu", ""),
            zone_name=info.get("zone_name", ""),
            total_flow_m3h=info.get("total_flow_m3h", 0.0),
            n_terminals=info.get("n_terminals", 0),
            sections=sections,
            total_pressure_loss_pa=info.get("total_pressure_loss_pa", 0.0),
            has_zone_fan=info.get("has_zone_fan", False),
            zone_fan_flow_m3_h=info.get("zone_fan_flow_m3_h", 0.0),
            zone_fan_pressure_pa=info.get("zone_fan_pressure_pa", 0.0),
            building_type=info.get("building_type", "public"),
            note=info.get("note", ""),
        )
        project.duct_networks[k] = net

    # Сети труб
    from hvac.pipe_sizing import PipeSection, PipeNetwork

    def _build_pipe_network(info_dict, key):
        sections = []
        for s in info_dict.get("sections", []):
            valid = {k_: v for k_, v in s.items()
                     if k_ in PipeSection.__dataclass_fields__}
            sections.append(PipeSection(**valid))
        return PipeNetwork(
            system_name=info_dict.get("system_name", key),
            parent_system=info_dict.get("parent_system", ""),
            circuit_type=info_dict.get("circuit_type", ""),
            medium=info_dict.get("medium", "heating"),
            total_heat_load_w=info_dict.get("total_heat_load_w", 0.0),
            total_flow_kg_h=info_dict.get("total_flow_kg_h", 0.0),
            delta_t_k=info_dict.get("delta_t_k", 20.0),
            t_supply_c=info_dict.get("t_supply_c", 80.0),
            t_return_c=info_dict.get("t_return_c", 60.0),
            n_terminals=info_dict.get("n_terminals", 0),
            sections=sections,
            total_pressure_loss_pa=info_dict.get("total_pressure_loss_pa", 0.0),
            pump_head_m=info_dict.get("pump_head_m", 0.0),
            pump_flow_m3_h=info_dict.get("pump_flow_m3_h", 0.0),
            pump_model=info_dict.get("pump_model", ""),
            pump_working_units=info_dict.get("pump_working_units", 0),
            pump_reserve_units=info_dict.get("pump_reserve_units", 0),
            pump_catalog_covered=info_dict.get("pump_catalog_covered", True),
            pipe_material=info_dict.get("pipe_material", "steel"),
            insulated=info_dict.get("insulated", False),
            note=info_dict.get("note", ""),
        )

    for k, info in data.get("pipe_networks", {}).items():
        project.pipe_networks[k] = _build_pipe_network(info, k)
    for k, info in data.get("cooling_pipe_networks", {}).items():
        project.cooling_pipe_networks[k] = _build_pipe_network(info, k)

    # Энергопаспорт
    ep_data = data.get("energy_passport")
    if ep_data:
        from hvac.energy import EnergyPassport
        valid = {k_: v for k_, v in ep_data.items()
                 if k_ in EnergyPassport.__dataclass_fields__}
        project.energy_passport = EnergyPassport(**valid)

    # ahu_loads
    project.ahu_loads = data.get("ahu_loads", {}) or {}

    # ===== v4.1: подробная инженерия =====
    project.ahu_processes = _deserialize_ahu_processes(
        data.get("ahu_processes", {}) or {})
    project.heating_hydraulics_results = _deserialize_hydraulics(
        data.get("heating_hydraulics_results", {}) or {})
    project.radiator_picks = _deserialize_radiator_picks(
        data.get("radiator_picks", {}) or {})
    project.acoustics_results = _deserialize_acoustics(
        data.get("acoustics_results", {}) or {})
    project.duct_networks_detailed = _deserialize_detailed_ducts(
        data.get("duct_networks_detailed", {}) or {})

    # ===== v4.2 =====
    project.underfloor_loops = _deserialize_underfloor_loops(
        data.get("underfloor_loops", {}) or {})
    project.fancoil_picks = _deserialize_fancoil_picks(
        data.get("fancoil_picks", {}) or {})
    project.vrf_systems = _deserialize_vrf_systems(
        data.get("vrf_systems", {}) or {})
    project.grille_picks = _deserialize_grille_picks(
        data.get("grille_picks", {}) or {})

    # Self-contained ветка перезаписывает project.elements списком из JSON —
    # индекс elements_by_space становится устаревшим. В ветке load(CSV)
    # инвалидация уже сделана внутри project.load(). На всякий случай
    # инвалидируем безусловно — стоит один битовый флаг.
    project._invalidate_elements_index()
    project.emit("project_loaded")
