# -*- coding: utf-8 -*-
"""Инвентаризация помещений общепита в рабочем проекте: что сейчас типа
'Ресторан / кухня' (и др. кухонные), их имена, площади, equipment_w_m2.
Нужно чтобы спроектировать разделение кухня↔зал и ключевые слова."""
import collections
import sys

sys.path.insert(0, r"D:\HVAC")
from hvac.project import HVACProject  # noqa: E402
from hvac import io_json  # noqa: E402

P = HVACProject()
io_json.load_project(P, r"D:\HVAC\ALL-BLOCKS_fixed.hvac.json")

FOOD = {"Ресторан / кухня", "Горячий цех", "Холодный цех", "Моечная",
        "Холодильная камера"}

by_type = collections.Counter(s.room_type for s in P.spaces)
print("=== ВСЕ ТИПЫ (топ по числу) ===")
for t, n in by_type.most_common():
    print("  %4d  %s" % (n, t))

print("\n=== ОБЩЕПИТ: имена помещений ===")
rows = [s for s in P.spaces if s.room_type in FOOD]
print("всего:", len(rows))
# группируем по типу
for t in sorted(FOOD):
    grp = [s for s in rows if s.room_type == t]
    if not grp:
        continue
    area = sum(s.area_m2 or 0 for s in grp)
    print("\n--- %s : %d шт, %.0f м², equip=%g Вт/м² ---" % (
        t, len(grp), area, grp[0].equipment_w_m2 if grp else 0))
    seen = collections.Counter((s.name or "").strip() for s in grp)
    for name, c in seen.most_common(60):
        print("   %3d  %s" % (c, name))
