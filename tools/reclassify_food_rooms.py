# -*- coding: utf-8 -*-
"""Реклассификация общепита в рабочем проекте после разделения типа
'Ресторан / кухня' → 'Ресторан / зал' (зал, 20 Вт/м²) / 'Кухня' (бытовая,
50 Вт/м²) / 'Горячий цех' (коммерческая, 250 Вт/м²).

Трогает ТОЛЬКО помещения с текущим типом 'Ресторан / кухня' (253 шт):
для каждого re-детект по имени → новый тип → применяем тепловые дефолты
(t_in, оборудование, освещение, занятость, ach_inf). Системы отопл/охл/вент
и заданные расходы supply/exhaust НЕ трогаем (инфильтрация по балансу как
была). Пересчёт нагрузок, бэкап, сохранение.
"""
import collections
import shutil
import sys

sys.path.insert(0, r"D:\HVAC")
from hvac.project import HVACProject  # noqa: E402
from hvac import io_json  # noqa: E402
from hvac.catalogs.room_types import (  # noqa: E402
    auto_detect_room_type, apply_room_type_defaults)

SRC = r"D:\HVAC\ALL-BLOCKS_fixed.hvac.json"
OLD = "Ресторан / кухня"

P = HVACProject()
io_json.load_project(P, SRC)

targets = [s for s in P.spaces if s.room_type == OLD]
print("Помещений типа '%s': %d" % (OLD, len(targets)))

loss0 = sum(s.heat_loss_w for s in P.spaces) / 1000.0
gain0 = sum(s.heat_gain_w for s in P.spaces) / 1000.0
food_gain0 = sum(s.heat_gain_w for s in targets) / 1000.0

# Реклассификация
moves = collections.Counter()
by_name = collections.Counter()
for s in targets:
    new_type = auto_detect_room_type(s.name or "")
    if new_type == "Прочее":
        # имя не распозналось — по умолчанию бытовая кухня (самый частый кейс)
        new_type = "Кухня"
    s.room_type = new_type
    apply_room_type_defaults(s)        # t_in, equip, light, occ, ach_inf
    moves[new_type] += 1
    by_name[(s.name.strip(), new_type)] += 1

print("\n=== РЕКЛАССИФИКАЦИЯ ===")
for t, n in moves.most_common():
    eq = next((x.equipment_w_m2 for x in targets if x.room_type == t), "?")
    print("  %3d → %-16s (equip=%s Вт/м²)" % (n, t, eq))

print("\n=== по именам ===")
for (name, t), n in by_name.most_common(40):
    print("  %3d  %-24s → %s" % (n, name, t))

P.recalculate()
loss1 = sum(s.heat_loss_w for s in P.spaces) / 1000.0
gain1 = sum(s.heat_gain_w for s in P.spaces) / 1000.0
food_gain1 = sum(s.heat_gain_w for s in targets) / 1000.0

print("\n=== НАГРУЗКИ ЗДАНИЯ, кВт ===")
print("  Теплопотери:    %.0f → %.0f  (%+.0f)" % (loss0, loss1, loss1 - loss0))
print("  Теплопоступл.:  %.0f → %.0f  (%+.0f)" % (gain0, gain1, gain1 - gain0))
print("  в т.ч. общепит: %.0f → %.0f  (%+.0f)" % (
    food_gain0, food_gain1, food_gain1 - food_gain0))

# HTL-039 (пример юзера)
h = P._space_by_id.get("750384")
if h:
    print("\nHTL-039 '%s': тип=%s equip=%g Вт/м² Qпоступл=%.0f Вт" % (
        h.name, h.room_type, h.equipment_w_m2, h.heat_gain_w))

shutil.copyfile(SRC, SRC + ".pre-foodsplit")
io_json.save_project(P, SRC, force_self_contained=True)
print("\nБэкап:", SRC + ".pre-foodsplit")
print("Сохранено:", SRC)
