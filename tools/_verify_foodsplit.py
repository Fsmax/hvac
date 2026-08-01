# -*- coding: utf-8 -*-
"""Проверка после реклассификации: перечитать сохранённый проект, убедиться
что новых типов нет старого 'Ресторан / кухня', системы целы, HTL-039 ок."""
import collections
import sys

sys.path.insert(0, r"D:\HVAC")
from hvac.project import HVACProject  # noqa: E402
from hvac import io_json  # noqa: E402

P = HVACProject()
io_json.load_project(P, r"D:\HVAC\ALL-BLOCKS_fixed.hvac.json")

types = collections.Counter(s.room_type for s in P.spaces)
print("Старый тип 'Ресторан / кухня' остался:",
      types.get("Ресторан / кухня", 0), "шт (должно 0)")
for t in ("Кухня", "Ресторан / зал", "Горячий цех"):
    print("  %-16s %d" % (t, types.get(t, 0)))

# системы целы?
heat = sum(1 for s in P.spaces if s.system_heating)
cool = sum(1 for s in P.spaces if s.system_cooling)
vent = sum(1 for s in P.spaces if s.system_ventilation)
print("\nС системами: отопл=%d охл=%d вент=%d (всего %d)" % (
    heat, cool, vent, len(P.spaces)))

h = P._space_by_id.get("750384")
print("\nHTL-039:", h.name, "| тип", h.room_type,
      "| equip", h.equipment_w_m2, "Вт/м²",
      "| охл-сист", h.system_cooling,
      "| вент-сист", h.system_ventilation,
      "| supply", round(h.supply_m3h or 0), "exhaust", round(h.exhaust_m3h or 0))

# Пример бытовой кухни
k = next((s for s in P.spaces if s.room_type == "Кухня"), None)
if k:
    print("Кухня-пример:", k.name, k.space_id, "| equip", k.equipment_w_m2,
          "| занятость", k.occupancy_people, "| t_in_heat", k.t_in_heat,
          "| охл-сист", k.system_cooling)
