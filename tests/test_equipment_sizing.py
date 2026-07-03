# -*- coding: utf-8 -*-
"""Тесты свёртки подбора источников (hvac.equipment_sizing) и pick_units."""

import pytest

from hvac.project import HVACProject
from hvac.models import Space
from hvac.equipment_sizing import select_equipment
from hvac.sizing_helpers import pick_units, BOILER_KW_LADDER, CHILLER_KW_LADDER
from hvac.ahu_load import aggregate_ahus, summary_by_circuit


def _add_space(p, sid, number, **kw):
    sp = Space(space_id=sid, number=number, name="Room", level="L1",
               area_m2=20.0, volume_m3=60.0, height_m=3.0, room_type="Офис")
    for k, v in kw.items():
        setattr(sp, k, v)
    p.spaces.append(sp)
    p._space_by_id[sid] = sp
    return sp


# --------------------------------------------------------------- pick_units
class TestPickUnits:
    def test_single_unit_next_size(self):
        assert pick_units(140, BOILER_KW_LADDER) == (150.0, 1)

    def test_exact_boundary(self):
        assert pick_units(100, BOILER_KW_LADDER) == (100.0, 1)

    def test_cascade_above_largest(self):
        # 2500 кВт > 2000 (макс) → 2 котла по 2000
        assert pick_units(2500, BOILER_KW_LADDER) == (2000.0, 2)

    def test_zero(self):
        assert pick_units(0, BOILER_KW_LADDER) == (0.0, 0)

    def test_chiller_ladder(self):
        assert pick_units(210, CHILLER_KW_LADDER) == (300.0, 1)


# ----------------------------------------------------------- свёртка тепла
class TestHeatingRollup:
    def test_circuit_rooms_rolled_to_source(self):
        p = HVACProject()
        p.add_zone_circuit("heating", "Рад-1", "Котёл A", circuit_type="radiator")
        _add_space(p, "1", "R-1", heat_loss_w=10_000)
        _add_space(p, "2", "R-2", heat_loss_w=20_000)
        p.assign_rooms_to_circuit("heating", ["1", "2"], "Рад-1")

        sel = select_equipment(p, margin_heating=1.10)
        src = {s.name: s for s in sel.heating}["Котёл A"]
        assert len(src.circuits) == 1
        c = src.circuits[0]
        assert c.n_rooms == 2
        assert c.q_rooms_w == 30_000
        assert c.q_ahu_w == 0.0
        assert src.q_total_w == 30_000
        # 30 кВт × 1.10 = 33 → котёл 50 кВт ×1
        assert round(src.required_kw, 1) == 33.0
        assert (src.unit_kw, src.units) == (50.0, 1)

    def test_direct_rooms_without_circuit(self):
        p = HVACProject()
        p.add_zone_system("heating", "Котёл A")
        _add_space(p, "1", "R-1", heat_loss_w=12_000)
        p.assign_rooms_to_system("heating", ["1"], "Котёл A")  # без контура
        sel = select_equipment(p)
        src = {s.name: s for s in sel.heating}["Котёл A"]
        assert src.n_direct_rooms == 1
        assert src.q_direct_w == 12_000
        assert not src.circuits
        assert src.q_total_w == 12_000

    def test_ahu_heater_attributed_to_circuit_no_double_count(self):
        p = HVACProject()
        p.params.t_out_heating = -16.0
        p.add_zone_circuit("heating", "Рад-1", "Котёл A")
        # помещение контура
        _add_space(p, "1", "R-1", heat_loss_w=10_000)
        p.assign_rooms_to_circuit("heating", ["1"], "Рад-1")
        # AHU с калорифером, привязанным к контуру Рад-1
        p.add_zone_system("ventilation", "ПВ-1", heating_circuit="Рад-1",
                          t_supply_winter=16.0)
        _add_space(p, "2", "R-2", system_ventilation="ПВ-1", supply_m3h=1000.0)

        # эталон нагрузки калорифера — из штатного движка
        by_circ = summary_by_circuit(aggregate_ahus(p))
        q_ahu_ref = by_circ["Рад-1"]["q_heating_w"]
        assert q_ahu_ref > 0

        sel = select_equipment(p)
        src = {s.name: s for s in sel.heating}["Котёл A"]
        c = src.circuits[0]
        assert c.q_ahu_w == pytest.approx(q_ahu_ref)
        # источник = помещения контура + калорифер AHU, без задвоения
        assert src.q_total_w == pytest.approx(10_000 + q_ahu_ref)
        assert src.q_ahu_w == pytest.approx(q_ahu_ref)


# ----------------------------------------------------------- свёртка холода
class TestCoolingRollup:
    def test_cooling_source_capacity(self):
        p = HVACProject()
        p.add_zone_circuit("cooling", "ФК-1", "Чиллер 1", circuit_type="fancoil")
        _add_space(p, "1", "R-1", heat_gain_w=80_000)
        _add_space(p, "2", "R-2", heat_gain_w=70_000)
        p.assign_rooms_to_circuit("cooling", ["1", "2"], "ФК-1")
        sel = select_equipment(p, margin_cooling=1.15)
        src = {s.name: s for s in sel.cooling}["Чиллер 1"]
        assert src.q_total_w == 150_000
        # 150 × 1.15 = 172.5 → чиллер 200 кВт
        assert round(src.required_kw, 1) == 172.5
        assert (src.unit_kw, src.units) == (200.0, 1)


# ------------------------------------------------------------------- ГВС
class TestDHW:
    def test_dhw_total_collected(self):
        from hvac.dhw import DHWSystem
        p = HVACProject()
        p.dhw_systems["ГВС-1"] = DHWSystem(name="ГВС-1", q_with_circulation_w=40_000)
        sel = select_equipment(p)
        assert sel.q_dhw_w == 40_000


class TestManualOverride:
    def test_manual_capacity_overrides_auto(self):
        p = HVACProject()
        p.add_zone_circuit("heating", "Рад-1", "Котёл A")
        _add_space(p, "1", "R-1", heat_loss_w=30_000)
        p.assign_rooms_to_circuit("heating", ["1"], "Рад-1")
        # вручную: 2 котла по 100 кВт, модель
        p.update_zone_system("heating", "Котёл A", design_capacity_kw=100.0,
                             unit_count=2, selected_model="Vitodens 200")
        sel = select_equipment(p)
        src = {s.name: s for s in sel.heating}["Котёл A"]
        assert src.manual is True
        assert (src.unit_kw, src.units) == (100.0, 2)
        assert src.selected_model == "Vitodens 200"
        # авто-нагрузка по-прежнему считается (для справки)
        assert src.q_total_w == 30_000

    def test_no_override_falls_back_to_auto(self):
        p = HVACProject()
        p.add_zone_circuit("heating", "Рад-1", "Котёл A")
        _add_space(p, "1", "R-1", heat_loss_w=30_000)
        p.assign_rooms_to_circuit("heating", ["1"], "Рад-1")
        sel = select_equipment(p)
        src = {s.name: s for s in sel.heating}["Котёл A"]
        assert src.manual is False
        assert (src.unit_kw, src.units) == (50.0, 1)


# ------------------------------------------- тепловой баланс блока
class TestBlockBalance:
    def test_required_from_block_balance(self):
        """Без контуров required берётся из баланса блока (+ГВС котлам)."""
        from hvac.dhw import DHWSystem
        p = HVACProject()
        _add_space(p, "1", "R-1", heat_loss_w=30_000, heat_gain_w=20_000,
                   block="HTL")
        _add_space(p, "2", "R-2", heat_loss_w=10_000, block="HTL")
        p.dhw_systems["ГВС-HTL"] = DHWSystem(
            name="ГВС-HTL", block="HTL", q_with_circulation_w=5_000.0)
        p.add_zone_system("heating", "Котлы HTL", block="HTL")
        p.add_zone_system("cooling", "Чиллеры HTL", block="HTL")

        sel = select_equipment(p, margin_heating=1.10, margin_cooling=1.15)
        h = {s.name: s for s in sel.heating}["Котлы HTL"]
        assert h.block == "HTL"
        assert h.q_total_w == 0                       # контуров нет
        assert h.q_block_rooms_w == 40_000
        assert h.q_block_dhw_w == 5_000
        assert h.q_base_w == 45_000
        assert h.required_kw == pytest.approx(45.0 * 1.10)
        c = {s.name: s for s in sel.cooling}["Чиллеры HTL"]
        assert c.q_block_rooms_w == 20_000
        assert c.q_block_dhw_w == 0                   # ГВС только котлам
        assert c.required_kw == pytest.approx(20.0 * 1.15)

    def test_circuits_take_precedence_over_block(self):
        """Есть контуры — required от них, баланс блока лишь справочно."""
        p = HVACProject()
        _add_space(p, "1", "R-1", heat_loss_w=30_000, block="HTL")
        _add_space(p, "2", "R-2", heat_loss_w=10_000, block="HTL")
        p.add_zone_circuit("heating", "Рад-1", "Котлы HTL",
                           circuit_type="radiator")
        p.assign_rooms_to_circuit("heating", ["1"], "Рад-1")
        p.update_zone_system("heating", "Котлы HTL", block="HTL")

        sel = select_equipment(p, margin_heating=1.10)
        h = {s.name: s for s in sel.heating}["Котлы HTL"]
        assert h.q_total_w == 30_000                  # контур
        assert h.q_block_rooms_w == 40_000            # баланс справочно
        assert h.q_base_w == 30_000                   # контуры главнее
        assert h.required_kw == pytest.approx(30.0 * 1.10)

    def test_no_block_keeps_zero(self):
        p = HVACProject()
        _add_space(p, "1", "R-1", heat_loss_w=30_000, block="HTL")
        p.add_zone_system("heating", "Котёл X")       # без блока
        sel = select_equipment(p)
        h = {s.name: s for s in sel.heating}["Котёл X"]
        assert h.block == "" and h.q_base_w == 0
        assert h.required_kw == 0
