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


def _load_with_spaces(rows, spaces):
    path = _write_csv(rows)
    try:
        els = load_thermal(path, spaces)
    finally:
        os.remove(path)
    return {e.element_id: e for e in els}


def test_curtain_shared_with_heated_room_is_internal():
    """Витраж, общий между двумя ОТАПЛИВАЕМЫМИ комнатами (bsc=2), —
    стеклянная перегородка между ними → ВНУТРЕННЯЯ. Имя типа («M_Exterior
    Glazing») ненадёжно: в модели его используют и для фасада, и для
    перегородок (напр. 6763672 между HTL-602.a и 602.b). Надёжный признак —
    геометрия (общий с отапл. соседом). Реальный фасад выгружается отдельным
    элементом с bsc=1 и остаётся наружным (см. тест ниже)."""
    from hvac.models import Space
    spaces = [
        Space(space_id="A", number="HTL-1.a", name="LIVING ROOM",
              level="L02", area_m2=20.0, volume_m3=60.0),
        Space(space_id="B", number="HTL-1.b", name="ROOM",
              level="L02", area_m2=18.0, volume_m3=54.0),
    ]
    rows = [
        _row2("A", "HTL-1.a", "CURT", "Витраж", "Наружные слои", bsc=2),
        _row2("B", "HTL-1.b", "CURT", "Витраж", "Наружные слои", bsc=2),
    ]
    els = _load_with_spaces(rows, spaces)
    assert els["CURT"].is_exterior is False


def test_curtain_facade_bsc1_stays_exterior():
    """Настоящий фасадный витраж выгружается с bsc=1 (касается одного
    помещения) и остаётся НАРУЖНЫМ."""
    from hvac.models import Space
    spaces = [Space(space_id="A", number="HTL-1.a", name="ROOM",
                    level="L02", area_m2=20.0, volume_m3=60.0)]
    rows = [_row2("A", "HTL-1.a", "FAC", "Витраж", "Наружные слои", bsc=1)]
    els = _load_with_spaces(rows, spaces)
    assert els["FAC"].is_exterior is True


def test_curtain_orphan_bsc1_stays_exterior():
    """Одиночный фасадный витраж (bsc=1) остаётся наружным."""
    els = _load([_row("CURT2", "yes", "Витраж", "curtain (orphan)", bsc=1)])
    assert els["CURT2"].is_exterior is True


def test_interior_partition_type_is_internal():
    """Витраж с явно внутренним типом («CHR_Interior Partition») —
    внутренний даже при bsc=1 (имя типа в interior-направлении надёжно)."""
    r = _row("PART", "yes", "Витраж", "Наружные слои", bsc=1)
    r["type"] = "CHR_Interior Partition"
    els = _load([r])
    assert els["PART"].is_exterior is False
