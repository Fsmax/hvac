# -*- coding: utf-8 -*-
"""Сравнение классификации глухих стен: мост (rbc пустой) vs Dynamo (rbc есть).
Показывает, сколько лишних 'наружных' глухих стен даёт потеря room_boundary_count."""
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(_HERE))
sys.path.insert(0, _HERE)
from hvac import data_loader  # noqa: E402
import reconcile_glazing as rec  # noqa: E402

spaces = data_loader.load_spaces(r"D:\HVAC\spaces.csv")

for label, path in [("МОСТ (rbc пустой)", r"D:\HVAC\thermal_all.csv"),
                    ("DYNAMO (rbc есть)",
                     r"D:\HVAC\thermal_all.pre-cleanglazing.csv")]:
    elems = data_loader.load_thermal(path, spaces)
    n = area = 0
    rbc_filled = 0
    for e in elems:
        if e.row_type != "external_wall" or not e.is_exterior:
            continue
        fam = (e.family or "").lower()
        if "витраж" in fam or "curtain" in fam:
            continue  # только глухие стены, без остекления
        n += 1
        area += e.approx_area_m2 or e.element_area_m2 or 0.0
    # сколько строк вообще имеют rbc (диагностика)
    import csv
    with open(path, encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            v = (row.get("room_boundary_count") or "").strip()
            if v != "":
                rbc_filled += 1
    print("%-22s глухих наружных: %5d  площадь ~%8.0f м²  | строк с rbc: %d"
          % (label, n, area, rbc_filled))
