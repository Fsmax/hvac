# -*- coding: utf-8 -*-
"""Дописывает geom_exterior в thermal_all.csv из сохранённых вердиктов
(out/wall_verdicts.csv) — без повторного прогона моста. Для будущих
импортов это делает revit_link.tag_wall_exterior автоматически."""
import csv
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
folder = sys.argv[1] if len(sys.argv) > 1 else os.path.dirname(_HERE)
vpath = os.path.join(_HERE, "out", "wall_verdicts.csv")
thermal = os.path.join(folder, "thermal_all.csv")

verdicts = {}
with open(vpath, encoding="utf-8-sig", newline="") as f:
    for r in csv.DictReader(f):
        verdicts[(r["space_id"].strip(), r["element_id"].strip())] = \
            r["verdict"].strip()

with open(thermal, encoding="utf-8-sig", newline="") as f:
    reader = csv.DictReader(f)
    fieldnames = list(reader.fieldnames or [])
    rows = list(reader)
if "geom_exterior" not in fieldnames:
    fieldnames.append("geom_exterior")

n_int = 0
for row in rows:
    if row.get("row_type", "").strip() != "external_wall":
        continue
    fam = (row.get("family", "") or "").lower()
    if "витраж" in fam or "curtain" in fam:
        continue
    v = verdicts.get((row.get("space_id", "").strip(),
                      row.get("element_id", "").strip()))
    if v:
        row["geom_exterior"] = v
        if v == "int":
            n_int += 1

with open(thermal, "w", encoding="utf-8-sig", newline="") as f:
    w = csv.DictWriter(f, fieldnames=fieldnames)
    w.writeheader()
    for row in rows:
        w.writerow({k: row.get(k, "") for k in fieldnames})

print("Вердиктов:", len(verdicts), " помечено внутренними (int):", n_int)
print("Файл:", thermal)
