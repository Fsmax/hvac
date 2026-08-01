# -*- coding: utf-8 -*-
"""Эффект инфильтрации-по-балансу на здании. Грузит мигрированный проект
(там есть приток/вытяжка по помещениям), пересчитывает с фоном 0 и 0.3,
сравнивает с прежним (плоский ACH). Сохраняет проект с выбранным фоном."""
import collections
import sys

sys.path.insert(0, r"D:\HVAC")
sys.path.insert(0, r"D:\HVAC\tools")
from hvac.project import HVACProject  # noqa: E402
from hvac import io_json  # noqa: E402
import reconcile_glazing as rec  # noqa: E402

SRC = r"D:\HVAC\ALL-BLOCKS_fixed.hvac.json"

P = HVACProject()
io_json.load_project(P, SRC)

# Прежнее (плоский ACH) — сохранённые значения из миграции
loss_old = sum(s.heat_loss_w for s in P.spaces) / 1000.0
gain_old = sum(s.heat_gain_w for s in P.spaces) / 1000.0


def recalc(floor):
    P.params.infiltration_min_ach = floor
    P.recalculate()
    loss = sum(s.heat_loss_w for s in P.spaces) / 1000.0
    gain = sum(s.heat_gain_w for s in P.spaces) / 1000.0
    inf = sum((s.heat_loss_breakdown or {}).get("Инфильтрация", 0.0)
              for s in P.spaces) / 1000.0
    h = P._space_by_id.get("750384")
    h_inf = (h.heat_loss_breakdown or {}).get("Инфильтрация", 0.0) if h else 0
    return loss, gain, inf, h_inf


l0, g0, i0, h0 = recalc(0.0)
l3, g3, i3, h3 = recalc(0.3)

print("=== ТЕПЛОПОТЕРИ ЗДАНИЯ, кВт ===")
print("  плоский ACH (было):           %.0f" % loss_old)
print("  по балансу, фон 0.0 (строго): %.0f  (инфильтр. %.0f)" % (l0, i0))
print("  по балансу, фон 0.3 (запас):  %.0f  (инфильтр. %.0f)" % (l3, i3))
print("\n=== ТЕПЛОПОСТУПЛЕНИЯ ЗДАНИЯ, кВт ===")
print("  было: %.0f | фон0: %.0f | фон0.3: %.0f" % (gain_old, g0, g3))
print("\nHTL-039 инфильтрация (Вт): фон0=%.0f  фон0.3=%.0f" % (h0, h3))

# сохраняем с фоном 0.3 (запас на отопление — рекомендуется)
P.params.infiltration_min_ach = 0.3
P.recalculate()
io_json.save_project(P, SRC, force_self_contained=True)
print("\nСохранено с фоном 0.3:", SRC)
print("(сменить: params.infiltration_min_ach — 0 строго / 0.3 запас)")
