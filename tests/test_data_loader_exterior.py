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


def _row2(space_id, space_number, eid, family, function, bsc):
    r = _row(eid, "yes", family, function, bsc=bsc)
    r["space_id"] = space_id
    r["space_number"] = space_number
    return r


def test_curtain_between_two_heated_rooms_is_internal():
    """Витраж, общий между двумя отапливаемыми комнатами (bsc=2), —
    стеклянная перегородка номера, а НЕ фасад → внутренняя.
    Реальный фасадный витраж выгружается с bsc=1 и остаётся наружным."""
    from hvac.models import Space
    spaces = [
        Space(space_id="A", number="HTL-1.a", name="LIVING ROOM",
              level="L02", area_m2=20.0, volume_m3=60.0),
        Space(space_id="B", number="HTL-1.b", name="ROOM",
              level="L02", area_m2=18.0, volume_m3=54.0),
    ]
    # Один и тот же витраж CURT присутствует у обоих помещений (bsc=2).
    rows = [
        _row2("A", "HTL-1.a", "CURT", "Витраж", "Наружные слои", bsc=2),
        _row2("B", "HTL-1.b", "CURT", "Витраж", "Наружные слои", bsc=2),
    ]
    path = _write_csv(rows)
    try:
        els = load_thermal(path, spaces)
    finally:
        os.remove(path)
    curt = [e for e in els if e.element_id == "CURT"]
    assert curt and all(e.is_exterior is False for e in curt)


def test_curtain_orphan_bsc1_stays_exterior():
    """Одиночный фасадный витраж (bsc=1) остаётся наружным."""
    els = _load([_row("CURT2", "yes", "Витраж", "curtain (orphan)", bsc=1)])
    assert els["CURT2"].is_exterior is True
