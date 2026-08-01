# -*- coding: utf-8 -*-
"""Проверка фикса площади: approx vs net по проблемным помещениям."""
import collections
import os
import sys

sys.path.insert(0, r"D:\HVAC")
from hvac.project import HVACProject
from hvac import data_loader

folder = sys.argv[1] if len(sys.argv) > 1 else r"D:\HVAC\tools\out\live_test"
spaces = data_loader.load_spaces(os.path.join(folder, "spaces.csv"))
elems = data_loader.load_thermal(os.path.join(folder, "thermal_all.csv"), spaces)
p = HVACProject()
p.spaces = spaces
p.elements = elems
p._recompute_net_areas()

by_space = collections.defaultdict(list)
for e in elems:
    by_space[e.space_id].append(e)

targets = {"HTL-2901", "RES-016", "HTL-064", "OFF-001", "OFC-R01", "OFF-033"}
print("%-9s %-20s %10s %10s" % ("номер", "имя", "approx_ext", "net_ext"))
for s in spaces:
    if s.number in targets:
        els = [e for e in by_space[s.space_id] if e.is_exterior]
        approx = sum(e.approx_area_m2 or 0 for e in els)
        net = sum(e.net_area_m2 or 0 for e in els)
        print("%-9s %-20s %10.1f %10.1f" % (
            s.number, (s.name or "")[:20], approx, net))
