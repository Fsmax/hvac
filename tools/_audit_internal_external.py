# -*- coding: utf-8 -*-
"""Аудит жалобы #3: глухая стена помечена наружной, но делит её другая
ОТАПЛИВАЕМАЯ комната того же уровня (значит это внутренняя перегородка)."""
import collections
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(_HERE))
sys.path.insert(0, _HERE)
from hvac import data_loader  # noqa: E402
import reconcile_glazing as rec  # noqa: E402

folder = sys.argv[1] if len(sys.argv) > 1 else os.path.join(_HERE, "out", "live_test")
spaces = data_loader.load_spaces(os.path.join(folder, "spaces.csv"))
elems = data_loader.load_thermal(os.path.join(folder, "thermal_all.csv"), spaces)
sp_by_id = {s.space_id: s for s in spaces}


def heated(sid):
    s = sp_by_id.get(sid)
    if not s:
        return False
    return not (s.number or "").upper().startswith(("OFC-", "BAL-", "TER-", "SHAFT"))


def level_of(sid):
    s = sp_by_id.get(sid)
    return s.level if s else ""


# element_id -> множество отапливаемых помещений
emap = collections.defaultdict(set)
for e in elems:
    if e.element_id and heated(e.space_id):
        emap[e.element_id].add(e.space_id)

n_opaque_ext = 0
n_suspect = 0
area_suspect = 0.0
samples = []
for e in elems:
    if e.row_type != "external_wall" or not e.is_exterior:
        continue
    if rec.classify(e.family, e.type_name) == "facade":
        continue  # это витраж, не глухая
    n_opaque_ext += 1
    others = [s for s in emap.get(e.element_id, set())
              if s != e.space_id and level_of(s) == level_of(e.space_id)]
    if others:
        n_suspect += 1
        area_suspect += e.net_area_m2 or e.approx_area_m2 or 0.0
        if len(samples) < 12:
            s = sp_by_id.get(e.space_id)
            samples.append("%-9s %-18s %-14s %s -> +%d отапл. сосед(а)" % (
                (s.number if s else ""), (s.name or "")[:18] if s else "",
                (e.type_name or "")[:14], e.element_id, len(others)))

print("Глухих наружных элементов:", n_opaque_ext)
print("Из них делит отапл. сосед того же уровня (подозрение #3):",
      n_suspect, "(%.1f%%)" % (100.0 * n_suspect / max(n_opaque_ext, 1)),
      " площадь ~%.0f м²" % area_suspect)
print("\nПримеры:")
for s in samples:
    print("  ", s)
