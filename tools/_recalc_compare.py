# -*- coding: utf-8 -*-
"""Полный пересчёт теплопотерь/теплопоступлений по зданию: старые данные
(Dynamo) vs новые (мост + чистый витраж + геом внутр.стены). Один и тот же
код — изолирует эффект фиксов выгрузки. Климат Ташкента, движок КМК."""
import collections
import os
import sys

sys.path.insert(0, r"D:\HVAC")
sys.path.insert(0, r"D:\HVAC\tools")
from hvac.project import HVACProject  # noqa: E402
import reconcile_glazing as rec  # noqa: E402

SP = r"D:\HVAC\spaces.csv"


def run(thermal, label):
    p = HVACProject()
    p.params.apply_city("Ташкент")
    p.load(SP, thermal)
    p.recalculate()
    loss = sum(s.heat_loss_w for s in p.spaces) / 1000.0
    gain = sum(s.heat_gain_w for s in p.spaces) / 1000.0
    bd = collections.Counter()
    for s in p.spaces:
        for k, v in (s.heat_loss_breakdown or {}).items():
            if k != "ИТОГО":
                bd[k] += v / 1000.0
    # площадь наружного остекления и глухих стен (для контекста)
    glaz = wall = 0.0
    for e in p.elements:
        if not e.is_exterior or e.row_type != "external_wall":
            continue
        fam = (e.family or "").lower()
        if "витраж" in fam or "curtain" in fam:
            glaz += e.net_area_m2 or 0.0
        else:
            wall += e.net_area_m2 or 0.0
    # по блокам: теплопотери и теплопоступления
    blk = collections.defaultdict(lambda: [0.0, 0.0])
    for s in p.spaces:
        b = rec.block_of_space(s.level, s.number)
        blk[b][0] += s.heat_loss_w / 1000.0
        blk[b][1] += s.heat_gain_w / 1000.0
    return loss, gain, bd, glaz, wall, blk


def main():
    rows = []
    rows.append(("Старые (Dynamo)",
                 run(r"D:\HVAC\thermal_all.pre-cleanglazing.csv",
                     "old")))
    rows.append(("Новые (мост+фиксы)",
                 run(r"D:\HVAC\thermal_all.csv", "new")))

    print("\n%-22s %12s %12s %12s %12s" % (
        "вариант", "Qпот,кВт", "Qпоступ,кВт", "витраж,м²", "глух.ст,м²"))
    for label, (loss, gain, bd, glaz, wall, blk) in rows:
        print("%-22s %12.0f %12.0f %12.0f %12.0f" % (
            label, loss, gain, glaz, wall))

    (lo, go, bo, _, _, blo) = rows[0][1]
    (ln, gn, bn, _, _, bln) = rows[1][1]
    print("\nИзменение теплопотерь:    %.0f → %.0f кВт (%.0f%%)"
          % (lo, ln, 100.0 * (ln - lo) / lo if lo else 0))
    print("Изменение теплопоступлений: %.0f → %.0f кВт (%.0f%%)"
          % (go, gn, 100.0 * (gn - go) / go if go else 0))

    print("\nТеплопотери по категориям (кВт): старое -> новое")
    keys = sorted(set(list(bo.keys()) + list(bn.keys())),
                  key=lambda k: -max(bo.get(k, 0), bn.get(k, 0)))
    for k in keys:
        print("  %-28s %8.0f -> %8.0f" % (k[:28], bo.get(k, 0), bn.get(k, 0)))

    print("\nПо блокам (Qпот / Qпоступ, кВт): старое -> новое")
    print("  %-5s %20s %20s" % ("блок", "Qпотери", "Qпоступления"))
    for b in sorted(set(list(blo.keys()) + list(bln.keys()))):
        lo2, go2 = blo.get(b, [0, 0])
        ln2, gn2 = bln.get(b, [0, 0])
        print("  %-5s %9.0f -> %-8.0f %9.0f -> %-8.0f"
              % (b, lo2, ln2, go2, gn2))


if __name__ == "__main__":
    main()
