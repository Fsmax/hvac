# -*- coding: utf-8 -*-
"""Раздел «Блоки»: определение блока, назначение, сводка нагрузок."""

import pytest

from hvac import blocks
from hvac.equipment import VentilationSystem
from hvac.models import Space
from hvac.project import HVACProject


def _sp(sid, number, level, **kw):
    defaults = dict(space_id=sid, number=number, name="X", level=level,
                    area_m2=10, volume_m3=30, height_m=3)
    defaults.update(kw)
    return Space(**defaults)


class TestDetectBlock:

    def test_number_prefix_wins_over_level(self):
        # Ресторан отеля на подиуме: номер HTL-*, уровень GFL -> HTL
        assert blocks.detect_block(_sp("1", "HTL-014", "GFL (FFL) +428")) == "HTL"
        # Трансформаторная жилой стороны в подвале: номер B01-* -> B1
        assert blocks.detect_block(_sp("2", "B01-093", "B1 (FFL) +424")) == "B1"

    def test_level_fallback(self):
        assert blocks.detect_block(_sp("3", "1001", "L10 RES (FFL)")) == "RES"
        assert blocks.detect_block(_sp("4", "017", "GFL (FFL) +428")) == "GFL"
        assert blocks.detect_block(_sp("5", "018", "MFL (FFL) +433")) == "MFL"

    def test_codes(self):
        assert blocks.detect_block(_sp("6", "OFF-046", "GFL")) == "OFF"
        assert blocks.detect_block(_sp("7", "OFC-100", "L02")) == "OFF"
        assert blocks.detect_block(_sp("8", "B02-032", "B2 (FFL)")) == "B2"
        assert blocks.detect_block(_sp("9", "X-1", "")) == ""


class TestAssignBlocks:

    def test_assign_and_keep_manual(self):
        project = HVACProject()
        a = _sp("1", "HTL-100", "L02 HTL")
        b = _sp("2", "RES-200", "L02 RES")
        b.block = "OFF"          # ручное назначение
        project.spaces = [a, b]
        project._space_by_id = {s.space_id: s for s in project.spaces}

        n = project.assign_blocks()
        assert n == 1
        assert a.block == "HTL"
        assert b.block == "OFF"  # не тронуто

        n = project.assign_blocks(overwrite=True)
        assert n == 1
        assert b.block == "RES"  # переопределено

    def test_blocks_in_project_order(self):
        project = HVACProject()
        project.spaces = [_sp("1", "B01-1", "B1"), _sp("2", "HTL-1", "L02 HTL"),
                          _sp("3", "RES-1", "L03 RES")]
        project._space_by_id = {s.space_id: s for s in project.spaces}
        assert blocks.blocks_in_project(project) == []   # до назначения — пусто
        project.assign_blocks()
        assert blocks.blocks_in_project(project) == ["HTL", "RES", "B1"]


class TestBlockSummary:

    def _project(self):
        project = HVACProject()
        # HTL: комната с нагрузками и приточкой; B1: техпомещение с парой
        a = _sp("1", "HTL-100", "L02 HTL", heat_loss_w=2000, heat_gain_w=3000,
                supply_m3h=500, exhaust_m3h=100, system_ventilation="П-1")
        b = _sp("2", "B01-135", "B1 (FFL)", heat_loss_w=1000,
                supply_m3h=1000, exhaust_m3h=1000,
                system_ventilation="В-1", system_supply="П-Б1")
        project.spaces = [a, b]
        project._space_by_id = {s.space_id: s for s in project.spaces}
        project.ventilation_systems["П-1"] = VentilationSystem(
            name="П-1", kind="ahu", system_type="supply")
        project.ventilation_systems["В-1"] = VentilationSystem(
            name="В-1", kind="exhaust_fan", system_type="exhaust",
            has_heater=False, has_cooler=False)
        project.ventilation_systems["П-Б1"] = VentilationSystem(
            name="П-Б1", kind="ahu", system_type="supply")
        project.assign_blocks()
        project.assign_system_blocks()   # шаг 2 — явно (фолбэка «на лету» нет)
        project.calculate_ahu_loads()
        return project

    def test_rooms_and_ahu_by_block(self):
        project = self._project()
        s = project.get_block_summary()
        assert list(s.keys()) == ["HTL", "B1"]

        htl, b1 = s["HTL"], s["B1"]
        assert htl["n_spaces"] == 1
        assert htl["q_heat_rooms_w"] == 2000
        assert htl["q_cool_rooms_w"] == 3000
        assert htl["supply_m3h"] == 500
        # приточка П-1 обслуживает только HTL -> её блок HTL (по расходу)
        assert [a["name"] for a in htl["ahus"]] == ["П-1"]
        assert htl["ahu_q_heater_w"] > 0
        assert htl["q_heat_total_w"] == pytest.approx(
            2000 + htl["ahu_q_heater_w"])

        # B1: комната на В-1 (вытяжка) + приток на П-Б1; калорифер на П-Б1
        names = [a["name"] for a in b1["ahus"]]
        assert set(names) == {"В-1", "П-Б1"}
        p_b1 = next(a for a in b1["ahus"] if a["name"] == "П-Б1")
        assert p_b1["supply_m3h"] == 1000
        assert p_b1["q_heater_w"] > 0
        v_1 = next(a for a in b1["ahus"] if a["name"] == "В-1")
        assert v_1["exhaust_m3h"] == 1000
        assert v_1["q_heater_w"] == 0

    def test_multi_block_ahu_belongs_to_one_block(self):
        """Установка ЦЕЛИКОМ в своём блоке (шаг 2), дробления нет;
        «serves» перечисляет блоки, куда она раздаёт воздух."""
        project = self._project()
        # П-1 обслуживает HTL (500) и RES (1500): преобладает RES
        c = _sp("3", "RES-300", "L03 RES", supply_m3h=1500,
                system_ventilation="П-1")
        project.spaces.append(c)
        project._space_by_id[c.space_id] = c
        project.assign_blocks()
        project.assign_system_blocks(overwrite=True)  # пересчёт доминанты
        project.calculate_ahu_loads()
        s = project.get_block_summary()
        q_total = project.ahu_loads["П-1"]["q_heater_w"]
        # вся нагрузка на RES, в HTL установки НЕТ
        assert all(a["name"] != "П-1" for a in s["HTL"]["ahus"])
        res_ahu = next(a for a in s["RES"]["ahus"] if a["name"] == "П-1")
        assert res_ahu["q_heater_w"] == pytest.approx(q_total)
        assert res_ahu["multi_block"]
        served = {b: sup for b, sup, _exh in res_ahu["serves"]}
        assert served == {"RES": 1500, "HTL": 500}

    def test_token_ignored_when_block_unknown(self):
        """Токен имени засчитывается только для СУЩЕСТВУЮЩЕГО блока: при
        пользовательской разбивке (HOTEL/…) «П-B1-05» не воскрешает B1,
        а идёт за помещениями."""
        flows = {"HOTEL": {"supply": 1000.0, "exhaust": 1000.0}}
        assert blocks.detect_system_block(
            "П-B1-05", flows, known_blocks={"HOTEL", "APARTMENT"}) == "HOTEL"
        # а при канонической разбивке токен работает
        assert blocks.detect_system_block(
            "П-B1-05", flows, known_blocks={"B1", "HOTEL"}) == "B1"

    def test_system_block_by_name_token(self):
        """Токен в имени главнее преобладающего расхода."""
        project = self._project()
        # П-1 переименовывать не будем — проверим detect напрямую
        assert blocks.detect_system_block("П-B1-05") == "B1"
        assert blocks.detect_system_block("В-08-HTL-28") == "HTL"
        assert blocks.detect_system_block("П-01-HTL-MFL") == "HTL"  # башня главнее
        assert blocks.detect_system_block("ПВ-02-OFF") == "OFF"
        assert blocks.detect_system_block("ПВ-В2-01") == "B2"  # кириллическая В2
        assert blocks.detect_system_block("В-01-WC") == ""     # токена нет
        # ручное назначение перекрывает всё
        vs = project.ventilation_systems["П-1"]
        vs.block = "OFF"
        s = project.get_block_summary()
        assert any(a["name"] == "П-1" for a in s["OFF"]["ahus"])

    def test_assign_system_blocks(self):
        project = self._project()
        for vs in project.ventilation_systems.values():
            vs.block = ""            # снять — фикстура уже назначила
        n = project.assign_system_blocks()
        assert n == 3
        assert project.ventilation_systems["П-1"].block == "HTL"
        assert project.ventilation_systems["В-1"].block == "B1"
        assert project.ventilation_systems["П-Б1"].block == "B1"
        # повторный вызов ничего не меняет; ручное сохраняется
        project.ventilation_systems["П-1"].block = "OFF"
        assert project.assign_system_blocks() == 0
        assert project.ventilation_systems["П-1"].block == "OFF"
        # overwrite возвращает на авто
        project.assign_system_blocks(overwrite=True)
        assert project.ventilation_systems["П-1"].block == "HTL"

    def test_is_heated_flag_respected(self):
        project = self._project()
        project.spaces[0].is_heated = False
        s = project.get_block_summary()
        assert s["HTL"]["q_heat_rooms_w"] == 0


class TestBlockRegistry:

    def _project(self):
        project = HVACProject()
        a = _sp("1", "HTL-100", "L02 HTL", block="HTL")
        b = _sp("2", "HTL-200", "L03 HTL", block="HTL")
        project.spaces = [a, b]
        project._space_by_id = {s.space_id: s for s in project.spaces}
        project.ventilation_systems["П-1"] = VentilationSystem(
            name="П-1", block="HTL")
        return project

    def test_create_block_registers_empty(self):
        project = self._project()
        assert project.create_block("Подиум") is True
        assert project.create_block("Подиум") is False   # дубль
        assert project.create_block("HTL") is False      # уже есть по данным
        assert "Подиум" in blocks.blocks_in_project(project)
        # пустой блок виден в сводке нулевой строкой
        s = project.get_block_summary()
        assert s["Подиум"]["n_spaces"] == 0

    def test_rename_block_everywhere(self):
        project = self._project()
        project.create_block("Подиум")
        stats = project.rename_block("HTL", "Башня А")
        assert stats == {"rooms": 2, "systems": 1}
        assert all(sp.block == "Башня А" for sp in project.spaces)
        assert project.ventilation_systems["П-1"].block == "Башня А"
        assert "HTL" not in blocks.blocks_in_project(project)

    def test_delete_block_clears_refs(self):
        project = self._project()
        project.create_block("HTL")  # False, но не важно
        stats = project.delete_block("HTL")
        assert stats == {"rooms": 2, "systems": 1}
        assert all(sp.block == "" for sp in project.spaces)
        assert project.ventilation_systems["П-1"].block == ""
        assert "HTL" not in (project.blocks or [])

    def test_delete_block_stays_deleted(self):
        """Регрессия: удалённый блок НЕ возвращается автоопределением —
        имена помещений/систем детектируемые (HTL-*, П-…), но block_of/
        system_block_of фолбэка не имеют."""
        project = self._project()
        project.delete_block("HTL")
        assert blocks.blocks_in_project(project) == []
        s = project.get_block_summary()
        assert list(s.keys()) == [""]           # только «(без блока)»
        assert s[""]["n_spaces"] == 2
        # автопомощник вернёт по явному действию — это ок
        project.assign_blocks()
        assert blocks.blocks_in_project(project) == ["HTL"]

    def test_registry_roundtrip(self, tmp_path):
        project = self._project()
        project.spaces[0].manual_entry = True
        project.create_block("Подиум")
        from hvac.io_json import save_project, load_project
        path = str(tmp_path / "t.hvac.json")
        save_project(project, path)
        fresh = HVACProject()
        load_project(fresh, path)
        assert "Подиум" in fresh.blocks
        assert "Подиум" in blocks.blocks_in_project(fresh)


class TestLevelSortKey:

    def test_building_order(self):
        levels = ["L09 HTL (FFL)", "B1 (FFL) +424", "GFL (FFL) +428",
                  "MFL (FFL) +433", "B2 (FFL) +420", "L02 RES (FFL)",
                  "MZN (FFL)", "L28 HTL (FFL)"]
        ordered = sorted(levels, key=blocks.level_sort_key)
        assert ordered == ["B2 (FFL) +420", "B1 (FFL) +424",
                           "GFL (FFL) +428", "MZN (FFL)", "MFL (FFL) +433",
                           "L02 RES (FFL)", "L09 HTL (FFL)", "L28 HTL (FFL)"]

    def test_l_number_wins_over_tokens(self):
        # «L09 HTL» — этаж 9, а не токен HTL
        assert blocks.level_sort_key("L09 HTL (FFL)") == 9


class TestBlockRoundtrip:

    def test_block_saved_and_loaded(self, tmp_path):
        project = HVACProject()
        a = _sp("1", "HTL-100", "L02 HTL", manual_entry=True)
        project.spaces = [a]
        project._space_by_id = {"1": a}
        project.assign_blocks()
        assert a.block == "HTL"

        from hvac.io_json import save_project, load_project
        path = str(tmp_path / "t.hvac.json")
        save_project(project, path)
        fresh = HVACProject()
        load_project(fresh, path)
        assert fresh.get_space("1").block == "HTL"


class TestBlockSummarySourcesDhw:
    """Сводка: подобранные котлы/чиллеры и ГВС блока."""

    def test_dhw_and_sources_in_summary(self):
        from hvac.dhw import DHWSystem
        from hvac.equipment import CoolingSystem, HeatingSystem
        project = HVACProject()
        project.spaces = [_sp("1", "HTL-100", "L02 HTL", block="HTL")]
        project.heating_systems["Котлы HTL"] = HeatingSystem(
            name="Котлы HTL", block="HTL", design_capacity_kw=2000.0,
            unit_count=2, selected_model="Test 2000")
        project.cooling_systems["Чиллеры HTL"] = CoolingSystem(
            name="Чиллеры HTL", block="HTL", design_capacity_kw=1500.0,
            unit_count=2)
        project.dhw_systems["ГВС-HTL"] = DHWSystem(
            name="ГВС-HTL", block="HTL",
            q_with_circulation_w=50_000.0, v_daily_total_m3=4.2)

        r = project.get_block_summary()["HTL"]
        assert r["q_dhw_w"] == 50_000.0
        assert [d["name"] for d in r["dhw"]] == ["ГВС-HTL"]
        assert r["dhw"][0]["v_daily_m3"] == 4.2
        src = {s["name"]: s for s in r["sources"]}
        assert src["Котлы HTL"]["domain"] == "heating"
        assert src["Котлы HTL"]["total_kw"] == 4000.0
        assert src["Котлы HTL"]["model"] == "Test 2000"
        assert src["Чиллеры HTL"]["domain"] == "cooling"
        # ГВС не подмешивается в ИТОГО отопления
        assert r["q_heat_total_w"] == r["q_heat_rooms_w"] + r["ahu_q_heater_w"]

    def test_source_without_block_goes_to_no_block(self):
        from hvac.equipment import HeatingSystem
        project = HVACProject()
        project.spaces = [_sp("1", "HTL-100", "L02 HTL", block="HTL")]
        project.heating_systems["Котёл X"] = HeatingSystem(name="Котёл X")
        s = project.get_block_summary()
        assert [x["name"] for x in s[""]["sources"]] == ["Котёл X"]
        assert s["HTL"]["sources"] == []
