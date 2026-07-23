# -*- coding: utf-8 -*-
"""load_project — ЗАМЕНА состояния проекта, а не слияние.

GUI открывает файлы в один долгоживущий HVACProject; до фикса всё, чего
не было в открываемом файле, переживало загрузку. Реальный случай: СДУ
«Кабельный этаж» и ГВС-системы, созданные в одном проекте, печатались в
записках всех проектов, открытых после него.
"""
import json
import os
import tempfile
import unittest

from hvac.project import HVACProject
from hvac.io_json import save_project, load_project
from hvac.smoke import SmokeSystem
from hvac.dhw import DHWSystem


def _project_with_systems() -> HVACProject:
    p = HVACProject()
    p.new_empty_project(project_name="Проект А", city="Ташкент")
    p.smoke_systems["СДУ Кабельный этаж"] = SmokeSystem(name="Кабельный этаж")
    p.dhw_systems["ГВС-Гостиница"] = DHWSystem(name="ГВС-Гостиница")
    p.ahu_loads["П1/В1"] = {"q_heater_w": 75000.0}
    p.blocks = ["Блок А"]
    return p


class TestLoadProjectReplacesState(unittest.TestCase):

    def test_load_clears_previous_project_systems(self):
        prev = _project_with_systems()

        fresh = HVACProject()
        fresh.new_empty_project(project_name="Проект Б", city="Гузар")
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "b.hvac.json")
            save_project(fresh, path)
            load_project(prev, path)

        self.assertEqual(prev.params.project_name, "Проект Б")
        self.assertEqual(prev.smoke_systems, {})
        self.assertEqual(prev.dhw_systems, {})
        self.assertEqual(prev.ahu_loads, {})
        self.assertEqual(prev.blocks, [])

    def test_load_keeps_systems_of_opened_file(self):
        prev = _project_with_systems()

        other = HVACProject()
        other.new_empty_project(project_name="Проект В", city="Гузар")
        other.smoke_systems["СДУ-B1"] = SmokeSystem(name="СДУ-B1")
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "v.hvac.json")
            save_project(other, path)
            load_project(prev, path)

        self.assertEqual(set(prev.smoke_systems), {"СДУ-B1"})
        self.assertEqual(prev.dhw_systems, {})

    def test_params_missing_keys_fall_back_to_defaults(self):
        prev = HVACProject()
        prev.new_empty_project(project_name="Проект А", city="Ташкент")
        prev.params.smoke_norm = "SP7_RU"

        minimal = {"self_contained": True,
                   "params": {"city": "Гузар"},
                   "spaces": []}
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "min.hvac.json")
            with open(path, "w", encoding="utf-8") as f:
                json.dump(minimal, f, ensure_ascii=False)
            load_project(prev, path)

        defaults = type(prev.params)()
        self.assertEqual(prev.params.city, "Гузар")
        self.assertEqual(prev.params.project_name, defaults.project_name)
        self.assertEqual(prev.params.smoke_norm, defaults.smoke_norm)


if __name__ == "__main__":
    unittest.main()
