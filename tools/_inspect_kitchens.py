# -*- coding: utf-8 -*-
"""Где находятся 227 'KITCHEN' — жилые (квартирные/номерные кухни) или
коммерческие (ресторанные цеха)? Группируем по блоку/системе/уровню."""
import collections
import sys

sys.path.insert(0, r"D:\HVAC")
from hvac.project import HVACProject  # noqa: E402
from hvac import io_json  # noqa: E402

P = HVACProject()
io_json.load_project(P, r"D:\HVAC\ALL-BLOCKS_fixed.hvac.json")

rk = [s for s in P.spaces if s.room_type == "Ресторан / кухня"]


def blk(s):
    # блок часто закодирован в системе охлаждения ("Блок HTL"), zone, или level
    for attr in ("system_cooling", "zone", "system_ventilation"):
        v = getattr(s, attr, None)
        if v:
            return str(v)
    return (s.level or "?")


print("=== 'Ресторан / кухня' по (имя, блок/система охл.) ===")
combo = collections.Counter((s.name.strip(), blk(s)) for s in rk)
for (name, b), c in combo.most_common(40):
    print("  %3d  %-22s | %s" % (c, name, b))

print("\n=== KITCHEN: распределение по уровню (первые символы) ===")
kit = [s for s in rk if s.name.strip().upper() == "KITCHEN"]
lvl = collections.Counter((s.level or "?") for s in kit)
for lv, c in lvl.most_common(40):
    print("  %3d  %s" % (c, lv))

print("\n=== KITCHEN: площади (гистограмма) ===")
ar = collections.Counter()
for s in kit:
    a = s.area_m2 or 0
    bucket = "<6" if a < 6 else "6-12" if a < 12 else "12-25" if a < 25 \
        else "25-60" if a < 60 else ">=60"
    ar[bucket] += 1
for b in ("<6", "6-12", "12-25", "25-60", ">=60"):
    print("  %-6s %d" % (b, ar.get(b, 0)))
print("  средняя площадь KITCHEN: %.1f м²" % (
    sum(s.area_m2 or 0 for s in kit) / max(1, len(kit))))

print("\n=== примеры KITCHEN (имя | уровень | площадь | сист.охл | вент) ===")
for s in kit[:25]:
    print("  %-8s | %-10s | %5.1f | %-14s | %s" % (
        s.space_id, (s.level or "?")[:10], s.area_m2 or 0,
        str(getattr(s, "system_cooling", ""))[:14],
        str(getattr(s, "system_ventilation", ""))[:18]))
