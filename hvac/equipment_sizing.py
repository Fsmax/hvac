# -*- coding: utf-8 -*-
"""Подбор источников оборудования: свёртка нагрузок к котлам/чиллерам.

Связывает уже существующую цепочку расчётов в единую картину «подбора»:

    Помещение → Контур → Источник (котёл / чиллер)
                  ↑                     ↓
            калорифер AHU         Σ нагрузок × запас
                                  → мощность + кол-во агрегатов

Для каждого источника (`HeatingSystem` / `CoolingSystem`) собирает его
контуры, нагрузку каждого контура (помещения + калориферы/охладители AHU,
привязанные к контуру), при наличии — гидравлику контура (DN, Δp, насос),
и подбирает суммарную мощность источника и количество агрегатов.

Чистая функция над `HVACProject` — physics берётся из готовых движков:
- `hvac.ahu_load.aggregate_ahus` / `summary_by_circuit` — нагрузки AHU по контурам;
- `project.pipe_networks` / `cooling_pipe_networks` — DN и Δp по контурам (если посчитаны);
- `HeatingCircuit.pump_*` — насос (заполняется `design_heating_hydraulics`);
- `hvac.sizing_helpers.pick_units` — количество агрегатов по типоряду.

UI (панель «Оборудование») только отображает результат.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from typing import Dict, List

from hvac.sizing_helpers import (
    BOILER_KW_LADDER, CHILLER_KW_LADDER, pick_units,
)


@dataclass
class CircuitSelection:
    """Подбор по одному контуру источника."""
    name: str
    circuit_type: str
    n_rooms: int
    q_rooms_w: float                # нагрузка помещений контура
    q_ahu_w: float                  # калориферы/охладители AHU этого контура
    q_total_w: float                # q_rooms + q_ahu
    # Гидравлика (если посчитана size_pipes / design_heating_hydraulics)
    dn_mm: float = 0.0
    dp_pa: float = 0.0
    pump_model: str = ""
    pump_flow_m3_h: float = 0.0
    pump_head_m: float = 0.0
    pump_working_units: int = 0
    pump_reserve_units: int = 0
    pump_catalog_covered: bool = True

    @property
    def pump_display(self) -> str:
        if not self.pump_model:
            return "—"
        if self.pump_working_units or self.pump_reserve_units:
            return (f"{self.pump_model} "
                    f"({self.pump_working_units}+{self.pump_reserve_units})")
        return self.pump_model


@dataclass
class SourceSelection:
    """Подбор по одному источнику (котёл / чиллер)."""
    domain: str                     # "heating" | "cooling"
    name: str
    system_type: str
    circuits: List[CircuitSelection] = field(default_factory=list)
    n_direct_rooms: int = 0         # помещения на системе без контура
    q_direct_w: float = 0.0
    q_total_w: float = 0.0          # Σ контуров + прямые (до запаса)
    # Тепловой баланс блока источника (если задан block): помещения
    # (is_heated/is_cooled) + приточные установки блока + ГВС (котлы).
    block: str = ""
    q_block_rooms_w: float = 0.0
    q_block_ahu_w: float = 0.0
    q_block_dhw_w: float = 0.0      # ГВС блока (только heating)
    q_base_w: float = 0.0           # база required: контуры, иначе баланс блока
    margin: float = 1.0
    required_kw: float = 0.0        # q_base × margin
    unit_kw: float = 0.0            # типоразмер единичного агрегата
    units: int = 0                  # количество агрегатов
    working_units: int = 0          # рабочих агрегатов
    reserve_units: int = 0          # резервных агрегатов
    installed_kw: float = 0.0       # установленная мощность, включая резерв
    n_plus_one_ok: bool = False      # рабочие агрегаты покрывают required
    manual: bool = False            # подбор задан вручную (override авто)
    selected_model: str = ""        # выбранная модель (ручной подбор)

    @property
    def q_ahu_w(self) -> float:
        return sum(c.q_ahu_w for c in self.circuits)


@dataclass
class EquipmentSelection:
    """Результат подбора по всему проекту."""
    heating: List[SourceSelection] = field(default_factory=list)
    cooling: List[SourceSelection] = field(default_factory=list)
    q_dhw_w: float = 0.0            # суммарная нагрузка ГВС (справочно, к отоплению)

    def sources(self, domain: str) -> List[SourceSelection]:
        return self.heating if domain == "heating" else self.cooling


def _room_load_w(domain: str, sp) -> float:
    return sp.heat_loss_w if domain == "heating" else sp.heat_gain_w


def _select_domain(project, domain: str, margin: float) -> List[SourceSelection]:
    from hvac.ahu_load import aggregate_ahus, summary_by_circuit
    from hvac.blocks import block_summary

    sys_field, circ_field = project.zoning_space_fields(domain)
    systems = project.systems_of(domain)
    circuits_store = project.circuits_of(domain)
    nets = (project.pipe_networks if domain == "heating"
            else project.cooling_pipe_networks)

    # Нагрузка AHU по контурам (через привязку heating_circuit/cooling_circuit).
    ahu_by_circuit = summary_by_circuit(aggregate_ahus(project))
    q_key = "q_heating_w" if domain == "heating" else "q_cooling_w"

    # Помещения: по контуру и «прямые» (на системе без контура).
    rooms_by_circuit: Dict[str, list] = defaultdict(list)
    direct_by_system: Dict[str, list] = defaultdict(list)
    for sp in project.spaces:
        c = getattr(sp, circ_field, "")
        s = getattr(sp, sys_field, "")
        if c:
            rooms_by_circuit[c].append(sp)
        elif s:
            direct_by_system[s].append(sp)

    ladder = BOILER_KW_LADDER if domain == "heating" else CHILLER_KW_LADDER
    blocks_sum = block_summary(project)
    out: List[SourceSelection] = []
    for sname in sorted(systems.keys()):
        sysobj = systems[sname]
        src = SourceSelection(domain=domain, name=sname,
                              system_type=getattr(sysobj, "system_type", ""),
                              margin=margin)
        for cname in project.circuits_of_system(domain, sname):
            cobj = circuits_store.get(cname)
            rooms = rooms_by_circuit.get(cname, [])
            q_rooms = sum(_room_load_w(domain, sp) for sp in rooms)
            q_ahu = ahu_by_circuit.get(cname, {}).get(q_key, 0.0)
            net = nets.get(cname)
            dn = max((s.dn_mm for s in net.sections), default=0.0) if net else 0.0
            dp = net.total_pressure_loss_pa if net else 0.0
            src.circuits.append(CircuitSelection(
                name=cname,
                circuit_type=getattr(cobj, "circuit_type", "") if cobj else "",
                n_rooms=len(rooms),
                q_rooms_w=q_rooms,
                q_ahu_w=q_ahu,
                q_total_w=q_rooms + q_ahu,
                dn_mm=dn,
                dp_pa=dp,
                pump_model=getattr(cobj, "pump_model", "") if cobj else "",
                pump_flow_m3_h=getattr(cobj, "pump_flow_m3_h", 0.0) if cobj else 0.0,
                pump_head_m=getattr(cobj, "pump_head_m", 0.0) if cobj else 0.0,
                pump_working_units=(getattr(cobj, "pump_working_units", 0)
                                    if cobj else getattr(net, "pump_working_units", 0)),
                pump_reserve_units=(getattr(cobj, "pump_reserve_units", 0)
                                    if cobj else getattr(net, "pump_reserve_units", 0)),
                pump_catalog_covered=(getattr(cobj, "pump_catalog_covered", True)
                                      if cobj else getattr(net, "pump_catalog_covered", True)),
            ))
        direct = direct_by_system.get(sname, [])
        src.n_direct_rooms = len(direct)
        src.q_direct_w = sum(_room_load_w(domain, sp) for sp in direct)
        src.q_total_w = sum(c.q_total_w for c in src.circuits) + src.q_direct_w
        # Тепловой баланс блока: когда зонирование к источнику не привязано
        # (контуров/помещений нет), требуемая мощность берётся из баланса
        # блока — помещения + установки (+ ГВС для котлов).
        blk = getattr(sysobj, "block", "") or ""
        row = blocks_sum.get(blk) if blk else None
        if row:
            src.block = blk
            if domain == "heating":
                src.q_block_rooms_w = row.get("q_heat_rooms_w", 0.0)
                src.q_block_ahu_w = row.get("ahu_q_heater_w", 0.0)
                src.q_block_dhw_w = row.get("q_dhw_w", 0.0)
            else:
                src.q_block_rooms_w = row.get("q_cool_rooms_w", 0.0)
                src.q_block_ahu_w = row.get("ahu_q_cooler_w", 0.0)
        q_block = (src.q_block_rooms_w + src.q_block_ahu_w
                   + src.q_block_dhw_w)
        if src.circuits:
            # Explicit circuits are authoritative; the block balance remains
            # informational because it can include rooms owned by other sources.
            src.q_base_w = src.q_total_w
        elif q_block > 0:
            # Direct AUTO assignments cover the block rooms, but the source must
            # also carry block-level AHU and DHW loads that are not room fields.
            src.q_base_w = max(src.q_total_w, q_block)
        else:
            src.q_base_w = src.q_total_w
        src.required_kw = src.q_base_w * margin / 1000.0
        # Ручной подбор (если задан) имеет приоритет над авто-расчётом.
        manual_kw = getattr(sysobj, "design_capacity_kw", 0.0) or 0.0
        if manual_kw > 0:
            src.manual = True
            src.unit_kw = manual_kw
            src.units = getattr(sysobj, "unit_count", 0) or 1
            src.reserve_units = min(
                max(int(getattr(sysobj, "reserve_units", 0) or 0), 0),
                src.units,
            )
            src.working_units = src.units - src.reserve_units
            src.selected_model = getattr(sysobj, "selected_model", "") or ""
        else:
            src.unit_kw, src.units = pick_units(src.required_kw, ladder)
            src.working_units = src.units
        src.installed_kw = src.unit_kw * src.units
        src.n_plus_one_ok = bool(
            src.reserve_units > 0
            and src.working_units * src.unit_kw >= src.required_kw
        )
        out.append(src)
    return out


def select_equipment(project, *, margin_heating: float = 1.10,
                     margin_cooling: float = 1.15) -> EquipmentSelection:
    """Подбирает источники отопления и холода по их контурам и AHU.

    margin_* — запас на подбор мощности (по умолчанию 10 % тепло / 15 % холод).
    Гидравлика (DN/Δp/насос) подхватывается, если ранее выполнены
    `size_pipes()` и `design_heating_hydraulics()`.
    """
    sel = EquipmentSelection(
        heating=_select_domain(project, "heating", margin_heating),
        cooling=_select_domain(project, "cooling", margin_cooling),
    )
    sel.q_dhw_w = sum(
        getattr(d, "q_with_circulation_w", 0.0) or getattr(d, "q_peak_w", 0.0)
        for d in project.dhw_systems.values()
    )
    return sel
