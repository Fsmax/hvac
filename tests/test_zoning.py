# -*- coding: utf-8 -*-
"""Тесты ручного зонирования: CRUD систем/контуров + массовое назначение
помещений (ZoningMixin)."""

import pytest

from hvac.project import HVACProject
from hvac.models import Space


def _add_space(project, sp_id, number, name="Office", level="L1",
               area=20.0, room_type="Офис"):
    sp = Space(space_id=sp_id, number=number, name=name, level=level,
               area_m2=area, volume_m3=area * 3, height_m=3.0,
               room_type=room_type)
    project.spaces.append(sp)
    project._space_by_id[sp_id] = sp
    return sp


def _project(n=3):
    p = HVACProject()
    for i in range(1, n + 1):
        _add_space(p, str(i), f"R-{i:03d}")
    return p


# ---------------------------------------------------------------- системы
class TestSystemCrud:

    def test_add_system_creates_object(self):
        p = _project()
        name = p.add_zone_system("heating", "Котёл A")
        assert name == "Котёл A"
        assert "Котёл A" in p.heating_systems
        # повторный вызов не дублирует
        p.add_zone_system("heating", "Котёл A")
        assert len(p.heating_systems) == 1

    def test_add_system_filters_unknown_kwargs(self):
        p = _project()
        p.add_zone_system("heating", "Котёл A", fuel="diesel", bogus="x")
        assert p.heating_systems["Котёл A"].fuel == "diesel"

    def test_add_system_blank_name_ignored(self):
        p = _project()
        assert p.add_zone_system("heating", "  ") == ""
        assert not p.heating_systems

    def test_rename_system_fixes_room_and_circuit_refs(self):
        p = _project()
        p.add_zone_circuit("heating", "Рад-1", "Котёл A")
        p.assign_rooms_to_circuit("heating", ["1", "2"], "Рад-1")
        assert p.rename_zone_system("heating", "Котёл A", "Котёл B")
        assert "Котёл B" in p.heating_systems
        assert "Котёл A" not in p.heating_systems
        assert p.spaces[0].system_heating == "Котёл B"
        # контур переключил родителя
        assert p.heating_circuits["Рад-1"].parent_system == "Котёл B"

    def test_rename_system_rejects_collision(self):
        p = _project()
        p.add_zone_system("heating", "A")
        p.add_zone_system("heating", "B")
        assert p.rename_zone_system("heating", "A", "B") is False

    def test_remove_system_clears_rooms_and_circuits(self):
        p = _project()
        p.add_zone_circuit("heating", "Рад-1", "Котёл A")
        p.assign_rooms_to_circuit("heating", ["1", "2"], "Рад-1")
        assert p.remove_zone_system("heating", "Котёл A")
        assert "Котёл A" not in p.heating_systems
        assert "Рад-1" not in p.heating_circuits
        assert p.spaces[0].system_heating == ""
        assert p.spaces[0].circuit_heating == ""


# --------------------------------------------------------------- контуры
class TestCircuitCrud:

    def test_add_circuit_autocreates_parent_and_defaults(self):
        p = _project()
        p.add_zone_circuit("heating", "ТП-1", "Котёл A", circuit_type="floor")
        assert "Котёл A" in p.heating_systems          # авто-создан
        c = p.heating_circuits["ТП-1"]
        assert c.parent_system == "Котёл A"
        assert c.circuit_type == "floor"
        # температурный график по умолчанию для тёплого пола 45/35
        assert (c.t_supply, c.t_return) == (45.0, 35.0)

    def test_ventilation_circuit_is_duct_zone(self):
        p = _project()
        p.add_zone_circuit("ventilation", "Зона А", "AHU-1")
        c = p.duct_zones["Зона А"]
        assert c.parent_ahu == "AHU-1"          # вент. родитель — parent_ahu

    def test_rename_circuit_fixes_rooms(self):
        p = _project()
        p.add_zone_circuit("cooling", "ФК-1", "Чиллер 1")
        p.assign_rooms_to_circuit("cooling", ["1"], "ФК-1")
        assert p.rename_zone_circuit("cooling", "ФК-1", "ФК-2")
        assert p.spaces[0].circuit_cooling == "ФК-2"

    def test_remove_circuit_keeps_system(self):
        p = _project()
        p.add_zone_circuit("heating", "Рад-1", "Котёл A")
        p.assign_rooms_to_circuit("heating", ["1"], "Рад-1")
        assert p.remove_zone_circuit("heating", "Рад-1")
        assert "Котёл A" in p.heating_systems            # система осталась
        assert p.spaces[0].circuit_heating == ""
        assert p.spaces[0].system_heating == "Котёл A"   # система осталась у комнаты

    def test_circuits_of_system(self):
        p = _project()
        p.add_zone_circuit("heating", "Рад-1", "Котёл A")
        p.add_zone_circuit("heating", "ТП-1", "Котёл A")
        p.add_zone_circuit("heating", "Рад-2", "Котёл B")
        assert p.circuits_of_system("heating", "Котёл A") == ["Рад-1", "ТП-1"]


class TestUpdateParams:

    def test_update_system_params(self):
        p = _project()
        p.add_zone_system("heating", "Котёл A")
        assert p.update_zone_system("heating", "Котёл A", t_supply=90.0,
                                    efficiency=0.95, fuel="diesel",
                                    design_capacity_kw=120.0)
        s = p.heating_systems["Котёл A"]
        assert (s.t_supply, s.efficiency, s.fuel) == (90.0, 0.95, "diesel")
        assert s.design_capacity_kw == 120.0

    def test_update_system_ignores_unknown_and_name(self):
        p = _project()
        p.add_zone_system("cooling", "Чиллер 1")
        p.update_zone_system("cooling", "Чиллер 1", name="ZZZ", bogus=1, cop=4.2)
        assert "Чиллер 1" in p.cooling_systems        # имя не сменилось
        assert p.cooling_systems["Чиллер 1"].cop == 4.2

    def test_update_missing_system_returns_false(self):
        p = _project()
        assert p.update_zone_system("heating", "нет", t_supply=50) is False

    def test_update_circuit_params(self):
        p = _project()
        p.add_zone_circuit("heating", "ТП-1", "Котёл A", circuit_type="floor")
        assert p.update_zone_circuit("heating", "ТП-1", t_supply=40.0,
                                     pipe_material="pex")
        c = p.heating_circuits["ТП-1"]
        assert (c.t_supply, c.pipe_material) == (40.0, "pex")

    def test_attach_ahu_to_circuit_via_update(self):
        p = _project()
        p.add_zone_system("ventilation", "ПВ-1")
        p.update_zone_system("ventilation", "ПВ-1", heating_circuit="Рад-1",
                             recovery_efficiency_winter=0.7, has_recovery=True)
        v = p.ventilation_systems["ПВ-1"]
        assert v.heating_circuit == "Рад-1"
        assert v.has_recovery and v.recovery_efficiency_winter == 0.7


# ------------------------------------------------------------ назначение
class TestAssignment:

    def test_assign_system_creates_and_counts(self):
        p = _project()
        n = p.assign_rooms_to_system("heating", ["1", "2"], "Котёл A")
        assert n == 2
        assert "Котёл A" in p.heating_systems
        assert p.spaces[0].system_heating == "Котёл A"
        # повторное назначение того же — 0 изменений
        assert p.assign_rooms_to_system("heating", ["1", "2"], "Котёл A") == 0

    def test_assign_system_drops_foreign_circuit(self):
        p = _project()
        p.add_zone_circuit("heating", "Рад-1", "Котёл A")
        p.assign_rooms_to_circuit("heating", ["1"], "Рад-1")
        # переназначаем комнату в другую систему — чужой контур снимается
        p.assign_rooms_to_system("heating", ["1"], "Котёл B")
        assert p.spaces[0].system_heating == "Котёл B"
        assert p.spaces[0].circuit_heating == ""

    def test_assign_circuit_syncs_system(self):
        p = _project()
        p.add_zone_circuit("heating", "Рад-1", "Котёл A")
        p.assign_rooms_to_circuit("heating", ["1"], "Рад-1")
        assert p.spaces[0].circuit_heating == "Рад-1"
        assert p.spaces[0].system_heating == "Котёл A"   # система подтянулась

    def test_clear_all(self):
        p = _project()
        p.add_zone_circuit("heating", "Рад-1", "Котёл A")
        p.assign_rooms_to_circuit("heating", ["1", "2"], "Рад-1")
        n = p.clear_rooms_assignment("heating", ["1", "2"], what="all")
        assert n == 2
        assert p.spaces[0].system_heating == ""
        assert p.spaces[0].circuit_heating == ""

    def test_clear_circuit_only(self):
        p = _project()
        p.add_zone_circuit("heating", "Рад-1", "Котёл A")
        p.assign_rooms_to_circuit("heating", ["1"], "Рад-1")
        p.clear_rooms_assignment("heating", ["1"], what="circuit")
        assert p.spaces[0].circuit_heating == ""
        assert p.spaces[0].system_heating == "Котёл A"   # система осталась


# ------------------------------------------------------------------- undo
class TestSnapshot:

    def test_snapshot_restore_roundtrip(self):
        p = _project()
        p.assign_rooms_to_system("cooling", ["1", "2"], "Чиллер 1")
        snap = p.snapshot_zoning(["1", "2"])
        p.clear_rooms_assignment("cooling", ["1", "2"], what="all")
        assert p.spaces[0].system_cooling == ""
        n = p.restore_zoning(snap)
        assert n == 2
        assert p.spaces[0].system_cooling == "Чиллер 1"


# --------------------------------------------------------- валидация домена
class TestDomain:

    def test_unknown_domain_raises(self):
        p = _project()
        with pytest.raises(ValueError):
            p.assign_rooms_to_system("plumbing", ["1"], "X")

    def test_domains_listed(self):
        assert set(HVACProject.zoning_domains()) == {
            "heating", "cooling", "ventilation"}
