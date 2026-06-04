# -*- coding: utf-8 -*-
"""Тесты экспорта результатов в CSV для обратной записи в Revit."""

import csv

from hvac.project import HVACProject
from hvac.io_revit import export_results_for_revit, csv_header, REVIT_FIELDS, ID_COLUMNS


def _project_with_space() -> HVACProject:
    p = HVACProject()
    p.new_empty_project(project_name="Тест", city="Ташкент")
    sp = p.add_space("101", "Гостиная", "1 этаж", 25.0)
    # Результаты расчёта
    sp.heat_loss_w = 1234.56
    sp.heat_gain_w = 2345.67
    sp.heat_gain_sensible_w = 2000.0
    sp.heat_gain_latent_w = 345.67
    # Вентиляция
    sp.supply_m3h = 180.0
    sp.exhaust_m3h = 150.0
    sp.ach_calculated = 2.4
    # Температуры
    sp.t_in_heat = 21.0
    sp.t_in_cool = 25.0
    # Системы и контуры
    sp.system_heating = "Котёл A"
    sp.system_cooling = "Чиллер 1"
    sp.system_ventilation = "AHU-A"
    sp.circuit_heating = "Рад-1"
    sp.circuit_cooling = "ФК-1"
    sp.duct_zone = "Зона А"
    return p, sp


def _read_csv(path):
    with open(path, "r", encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def test_header_matches_contract(tmp_path):
    """Заголовок CSV = идентификаторы + все колонки REVIT_FIELDS."""
    p, _sp = _project_with_space()
    path = str(tmp_path / "results.csv")
    export_results_for_revit(p, path)
    with open(path, "r", encoding="utf-8-sig", newline="") as f:
        header = next(csv.reader(f))
    assert header == csv_header()
    assert header[:3] == ID_COLUMNS
    assert header == ID_COLUMNS + [col for col, *_ in REVIT_FIELDS]


def test_full_engineering_set_values(tmp_path):
    """Все инженерные поля попадают в CSV с верными значениями."""
    p, sp = _project_with_space()
    path = str(tmp_path / "results.csv")
    export_results_for_revit(p, path)
    rows = _read_csv(path)
    assert len(rows) == 1
    r = rows[0]

    assert r["space_id"] == sp.space_id
    assert r["space_number"] == "101"
    assert r["space_name"] == "Гостиная"

    assert float(r["heating_load_w"]) == 1234.6
    assert float(r["cooling_load_w"]) == 2345.7
    assert float(r["cooling_sensible_w"]) == 2000.0
    assert float(r["cooling_latent_w"]) == 345.7
    assert float(r["supply_m3h"]) == 180.0
    assert float(r["exhaust_m3h"]) == 150.0
    assert float(r["ach"]) == 2.4
    assert float(r["t_in_heat"]) == 21.0
    assert float(r["t_in_cool"]) == 25.0

    assert r["system_heating"] == "Котёл A"
    assert r["system_cooling"] == "Чиллер 1"
    assert r["system_ventilation"] == "AHU-A"
    assert r["circuit_heating"] == "Рад-1"
    assert r["circuit_cooling"] == "ФК-1"
    assert r["duct_zone"] == "Зона А"


def test_empty_optional_fields(tmp_path):
    """Незаполненные имена систем/контуров уходят пустыми строками."""
    p = HVACProject()
    p.new_empty_project(project_name="Тест", city="Ташкент")
    p.add_space("102", "Спальня", "1 этаж", 18.0)
    path = str(tmp_path / "results.csv")
    export_results_for_revit(p, path)
    r = _read_csv(path)[0]
    assert r["system_heating"] == ""
    assert r["duct_zone"] == ""
    # Числовые поля по умолчанию — 0 (нагрузки) либо дефолт модели (t)
    assert float(r["heating_load_w"]) == 0.0
    assert float(r["supply_m3h"]) == 0.0


def test_multiple_spaces_rows(tmp_path):
    """Одна строка на помещение, порядок сохраняется."""
    p = HVACProject()
    p.new_empty_project(project_name="Тест", city="Ташкент")
    p.add_space("101", "A", "1", 10.0)
    p.add_space("102", "B", "1", 12.0)
    p.add_space("103", "C", "1", 14.0)
    path = str(tmp_path / "results.csv")
    export_results_for_revit(p, path)
    rows = _read_csv(path)
    assert [r["space_number"] for r in rows] == ["101", "102", "103"]
