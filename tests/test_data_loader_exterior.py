# -*- coding: utf-8 -*-
"""Тесты эвристики «наружное/внутреннее» при импорте ограждений из Revit/Dynamo.

Ключевой случай: стена касается лишь одного помещения (boundary_space_count=1).
Раньше такая стена всегда помечалась наружной → в реальных выгрузках почти все
перегородки, выходящие в шахты/ниши/коридоры без Room Bounding, ошибочно
становились наружными. Теперь при bsc<=1 переопределяем на внутреннюю, если
Dynamo пометил is_exterior_wall=no ИЛИ тип стены внутренний («Внутренние слои»).
Витраж остаётся наружным.
"""
import csv
import os
import tempfile

from hvac.data_loader import load_thermal


_HEADER = [
    "space_id", "space_number", "space_name", "space_level", "row_type",
    "is_exterior_wall", "element_id", "link_model", "category", "family",
    "type", "element_level", "boundary_length_m", "space_height_m",
    "approx_area_m2", "element_area", "thickness", "function", "thermal_value",
    "host_element_id", "boundary_space_count", "orientation_deg",
]


def _row(eid, flag, family, function, bsc=1, cat="Стены",
         row_type="external_wall"):
    return {
        "space_id": "R1", "space_number": "101", "space_name": "ROOM",
        "space_level": "L02", "row_type": row_type, "is_exterior_wall": flag,
        "element_id": eid, "link_model": "ARC.rvt", "category": cat,
        "family": family, "type": "", "element_level": "L02",
        "boundary_length_m": "3.0", "space_height_m": "3.0",
        "approx_area_m2": "9.0", "element_area": "9.0 м²", "thickness": "125",
        "function": function, "thermal_value": "", "host_element_id": "",
        "boundary_space_count": str(bsc), "orientation_deg": "180",
    }


def _write_csv(rows):
    fd, path = tempfile.mkstemp(suffix=".csv")
    os.close(fd)
    with open(path, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=_HEADER)
        w.writeheader()
        for r in rows:
            w.writerow(r)
    return path


def _load(rows):
    path = _write_csv(rows)
    try:
        els = load_thermal(path)
    finally:
        os.remove(path)
    return {e.element_id: e for e in els}


def test_bsc1_exterior_type_stays_exterior():
    """yes + «Наружные слои» + bsc=1 → реальный фасад, наружная."""
    els = _load([_row("EW1", "yes", "Базовая стена", "Наружные слои")])
    assert els["EW1"].is_exterior is True


def test_bsc1_interior_type_becomes_internal():
    """yes + «Внутренние слои» + bsc=1 → перегородка в шахту, внутренняя."""
    els = _load([_row("EW2", "yes", "Базовая стена", "Внутренние слои")])
    assert els["EW2"].is_exterior is False


def test_bsc1_dynamo_no_becomes_internal():
    """is_exterior_wall=no + bsc=1 → доверяем Dynamo, внутренняя."""
    els = _load([_row("EW3", "no", "Базовая стена", "")])
    assert els["EW3"].is_exterior is False


def test_bsc1_curtain_stays_exterior():
    """Витраж + bsc=1 → панели смотрят на улицу, наружная."""
    els = _load([_row("V1", "yes", "Витраж", "curtain (orphan)")])
    assert els["V1"].is_exterior is True


def test_bsc1_exterior_yes_no_function_stays_exterior():
    """yes + пустая function + bsc=1 → нет сигнала «внутренняя», наружная."""
    els = _load([_row("EW4", "yes", "Базовая стена", "")])
    assert els["EW4"].is_exterior is True
