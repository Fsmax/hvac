# -*- coding: utf-8 -*-
"""Тесты ручного ввода: add/remove/update/duplicate/import/template."""

import csv
from dataclasses import dataclass
from typing import List

import pytest

from hvac.project import HVACProject
from hvac.io_json import save_project, load_project
from hvac.catalogs.construction_presets import apply_preset
from hvac.models import Construction


@dataclass
class _Room:
    name: str
    room_type: str
    area_m2: float


@dataclass
class _Template:
    n_floors: int
    first_floor_number: int
    apartments_per_floor: int
    rooms_per_apartment: List[_Room]
    height_m: float
    level_prefix: str


def _fresh_project() -> HVACProject:
    p = HVACProject()
    p.new_empty_project(project_name="Тест", city="Ташкент")
    return p


# ===== Space CRUD =====
class TestSpaceCRUD:
    def test_add_space_autoincrements_id(self):
        p = _fresh_project()
        s1 = p.add_space("101", "Гостиная", "1 этаж", 25.0)
        s2 = p.add_space("102", "Спальня",  "1 этаж", 18.0)
        assert s1.space_id != s2.space_id
        assert s1.manual_entry is True
        assert s1.volume_m3 == 25.0 * s1.height_m
        assert p.get_space(s1.space_id) is s1
        assert len(p.spaces) == 2

    def test_add_space_duplicate_id_raises(self):
        p = _fresh_project()
        p.add_space("101", "A", "1", 10.0, space_id="X1")
        with pytest.raises(ValueError):
            p.add_space("102", "B", "1", 10.0, space_id="X1")

    def test_remove_space_cleans_elements(self):
        p = _fresh_project()
        sp = p.add_space("101", "Жилая", "1", 20.0)
        p.add_element(sp.space_id, "external_wall", "Стены",
                       "F", "T", area_m2=15)
        p.add_element(sp.space_id, "opening", "Окна",
                       "Окно", "Т", area_m2=3)
        assert len([e for e in p.elements if e.space_id == sp.space_id]) == 2
        ok = p.remove_space(sp.space_id)
        assert ok
        assert p.get_space(sp.space_id) is None
        assert all(e.space_id != sp.space_id for e in p.elements)

    def test_update_space_recomputes_volume(self):
        p = _fresh_project()
        sp = p.add_space("1", "X", "1", 20.0, height_m=3.0)
        assert sp.volume_m3 == 60.0
        p.update_space(sp.space_id, area_m2=30.0)
        assert sp.volume_m3 == 30.0 * sp.height_m

    def test_duplicate_space_copies_elements(self):
        p = _fresh_project()
        sp = p.add_space("101", "Гостиная", "1", 20.0)
        p.add_element(sp.space_id, "external_wall", "Стены",
                       "F", "T", area_m2=12, orientation="N")
        p.add_element(sp.space_id, "opening", "Окна",
                       "Окно", "Т", area_m2=3, orientation="N")
        new_sp = p.duplicate_space(sp.space_id)
        assert new_sp is not None
        assert new_sp.space_id != sp.space_id
        assert "копия" in new_sp.number
        elems = [e for e in p.elements if e.space_id == new_sp.space_id]
        assert len(elems) == 2
        # У копии собственные element_id
        original_ids = {e.element_id for e in p.elements
                        if e.space_id == sp.space_id}
        copy_ids = {e.element_id for e in elems}
        assert not (original_ids & copy_ids)


# ===== Шаблон =====
class TestBuildingTemplate:
    def test_creates_n_floors_x_m_apts_x_k_rooms(self):
        p = _fresh_project()
        tpl = _Template(
            n_floors=3, first_floor_number=1, apartments_per_floor=2,
            rooms_per_apartment=[
                _Room("Гостиная", "Жилая комната", 20.0),
                _Room("Спальня", "Жилая комната", 12.0),
                _Room("Санузел", "Санузел", 4.0),
            ],
            height_m=3.0, level_prefix="Этаж ",
        )
        created = p.add_spaces_from_template(tpl)
        # 3 этажа × 2 кв × 3 комн = 18 помещений
        assert len(created) == 18
        assert len(p.spaces) == 18
        # Все промаркированы как ручные
        assert all(s.manual_entry for s in p.spaces)
        # Уровни сгенерированы
        levels = sorted({s.level for s in p.spaces})
        assert levels == ["Этаж 1", "Этаж 2", "Этаж 3"]
        # Площади
        floor_area = 2 * (20 + 12 + 4)  # на этаж: 2 кв × сумма
        assert sum(s.area_m2 for s in p.spaces if s.level == "Этаж 1") \
            == floor_area


# ===== Импорт из CSV =====
class TestImport:
    def _make_csv(self, tmp_path, rows, headers):
        path = tmp_path / "spaces.csv"
        with open(path, "w", encoding="utf-8", newline="") as f:
            w = csv.writer(f)
            w.writerow(headers)
            for r in rows:
                w.writerow(r)
        return str(path)

    def test_import_csv_russian_headers(self, tmp_path):
        path = self._make_csv(tmp_path,
            headers=["Номер", "Имя", "Этаж", "Тип", "Площадь", "Высота"],
            rows=[
                ["101", "Гостиная", "1 этаж", "Жилая комната", "22.5", "3.0"],
                ["102", "Кухня",    "1 этаж", "Ресторан / кухня", "10",  "3.0"],
                ["201", "Спальня",  "2 этаж", "Жилая комната", "14.0", "3.0"],
            ])
        p = _fresh_project()
        n = p.import_spaces_from_csv(path)
        assert n == 3
        nums = {s.number for s in p.spaces}
        assert nums == {"101", "102", "201"}

    def test_import_csv_english_headers(self, tmp_path):
        path = self._make_csv(tmp_path,
            headers=["number", "name", "level", "area", "height"],
            rows=[
                ["A-1", "Office",  "1 floor", "30", "3.2"],
                ["A-2", "Meeting", "1 floor", "18", "3.2"],
            ])
        p = _fresh_project()
        n = p.import_spaces_from_csv(path)
        assert n == 2
        sp = next(s for s in p.spaces if s.number == "A-1")
        assert sp.height_m == 3.2
        # Тип авто-детектирован (Office → Офис)
        assert sp.room_type == "Офис"

    def test_import_csv_skips_dup_and_empty(self, tmp_path):
        path = self._make_csv(tmp_path,
            headers=["№", "Имя", "Площадь"],
            rows=[
                ["X1", "A", "10"],
                ["X1", "B", "12"],   # дубль номера ОК (space_id разные)
                ["",   "C", "15"],   # без номера — пропускается
                ["X2", "D", ""],     # без площади — пропускается
            ])
        p = _fresh_project()
        n = p.import_spaces_from_csv(path)
        # X1 и X1 оба попадут (space_id автогенерируется), без номера/пл. — нет
        assert n == 2

    def test_import_csv_requires_number_and_area(self, tmp_path):
        path = self._make_csv(tmp_path,
            headers=["имя", "тип"],
            rows=[["A", "Офис"]])
        p = _fresh_project()
        with pytest.raises(ValueError):
            p.import_spaces_from_csv(path)


# ===== Фильтр служебных категорий Revit =====
class TestExcludedCategories:
    def test_is_excluded_category_known_names(self):
        from hvac.data_loader import is_excluded_category
        assert is_excluded_category("<Разделитель помещений>")
        assert is_excluded_category("<Разделители пространств>")
        assert is_excluded_category("<Room Separation Lines>")
        assert is_excluded_category("Несущие колонны")
        assert is_excluded_category("Structural Columns")

    def test_is_excluded_category_heuristic(self):
        from hvac.data_loader import is_excluded_category
        # Не из списка, но имя похоже на разделитель — ловится эвристикой
        assert is_excluded_category("<Разделение_проектное>")
        assert is_excluded_category("<New Separation Element>")

    def test_is_excluded_category_real_walls_pass(self):
        from hvac.data_loader import is_excluded_category
        assert not is_excluded_category("Стены")
        assert not is_excluded_category("Окна")
        assert not is_excluded_category("Walls")
        assert not is_excluded_category("")

    def test_json_load_drops_room_separators(self, tmp_path):
        """Старый проект с разделителями помещений — после загрузки они
        отфильтрованы."""
        import json
        from hvac.project import HVACProject
        from hvac.io_json import load_project
        data = {
            "version": "3.8",
            "self_contained": True,
            "params": {"city": "Москва"},
            "spaces": [{
                "space_id": "S1", "number": "1", "name": "X", "level": "1",
                "area_m2": 20.0, "volume_m3": 60.0,
            }],
            "elements": [
                {"space_id": "S1", "row_type": "external_wall",
                 "is_exterior": True, "element_id": "W1",
                 "category": "Стены", "family": "F", "type_name": "T",
                 "boundary_length_m": 5, "space_height_m": 3,
                 "approx_area_m2": 15, "element_area_m2": 15,
                 "thickness_mm": 200, "function": "", "host_element_id": "",
                 "boundary_space_count": 1, "net_area_m2": 15},
                {"space_id": "S1", "row_type": "external_wall",
                 "is_exterior": False, "element_id": "RS1",
                 "category": "<Разделитель помещений>",
                 "family": "", "type_name": "",
                 "boundary_length_m": 5, "space_height_m": 3,
                 "approx_area_m2": 0, "element_area_m2": 0,
                 "thickness_mm": 0, "function": "", "host_element_id": "",
                 "boundary_space_count": 1, "net_area_m2": 0},
            ],
            "constructions": {
                "Стены / F / 200": {"key": "Стены / F / 200",
                    "category": "Стены", "family": "F", "type_name": "T",
                    "thickness_mm": 200, "u_value": 0.5, "shgc": 0.0,
                    "note": "", "layers": []},
                "Раздел / / 0": {"key": "Раздел / / 0",
                    "category": "<Разделитель помещений>", "family": "",
                    "type_name": "", "thickness_mm": 0, "u_value": 0.0,
                    "shgc": 0.0, "note": "", "layers": []},
            },
        }
        path = tmp_path / "old.hvac.json"
        path.write_text(json.dumps(data), encoding="utf-8")
        p = HVACProject()
        load_project(p, str(path))
        # Реальная стена осталась, разделитель отфильтрован
        cats = [e.category for e in p.elements]
        assert "Стены" in cats
        assert "<Разделитель помещений>" not in cats
        # И из каталога тоже
        assert "Стены / F / 200" in p.constructions
        assert "Раздел / / 0" not in p.constructions


# ===== End-to-end: пустой → полный → save/load =====
class TestE2E:
    def test_full_no_revit_workflow(self, tmp_path):
        # Сценарий: пользователь создал пустой проект, добавил каталог
        # конструкций со слоями, накидал помещения и ограждения,
        # сохранил, перезагрузил, перерасчёт.
        p = _fresh_project()
        p.params.gsop_18 = 4500

        # Конструкции
        wall = Construction(key="Стены / Внеш / 380",
                             category="Стены", family="Внеш",
                             type_name="Стандарт", thickness_mm=380)
        apply_preset(wall, "Кирпич 380 + минвата 100 мм")
        p.constructions[wall.key] = wall

        window = Construction(key="Окна / Окно / 60",
                               category="Окна", family="Окно",
                               type_name="2-камерный", thickness_mm=60)
        apply_preset(window, "Двухкамерный СП с Low-E + Ar")
        p.constructions[window.key] = window

        # 5 этажей × 4 квартиры × 3 комнаты
        tpl = _Template(
            n_floors=5, first_floor_number=1, apartments_per_floor=4,
            rooms_per_apartment=[
                _Room("Гост", "Жилая комната", 22),
                _Room("Спал", "Жилая комната", 14),
                _Room("С/у",  "Санузел", 4),
            ],
            height_m=3.0, level_prefix="Этаж ",
        )
        p.add_spaces_from_template(tpl)
        assert len(p.spaces) == 60

        # Добавим стену и окно к первому помещению
        sp = p.spaces[0]
        p.add_element(sp.space_id, "external_wall", "Стены",
                       wall.family, wall.type_name, area_m2=12,
                       orientation="S", thickness_mm=380, u_value=wall.u_value)
        p.add_element(sp.space_id, "opening", "Окна",
                       window.family, window.type_name, area_m2=2.4,
                       orientation="S", u_value=window.u_value,
                       shgc=window.shgc)

        # Расчёт работает без CSV
        p.recalculate()
        assert sp.heat_loss_w > 0

        # Сохранение / загрузка
        path = tmp_path / "manual.hvac.json"
        save_project(p, str(path))
        p2 = HVACProject()
        load_project(p2, str(path))
        assert len(p2.spaces) == 60
        assert "Стены / Внеш / 380" in p2.constructions
        assert len(p2.constructions["Стены / Внеш / 380"].layers) == 4
        sp2 = p2.get_space(sp.space_id)
        assert sp2 is not None
        assert sp2.heat_loss_w > 0
        # Ограждения восстановились
        elems2 = [e for e in p2.elements if e.space_id == sp2.space_id]
        assert len(elems2) == 2
