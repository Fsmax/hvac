#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Анализ: помещения, где ЕСТЬ вентиляция (приток/вытяжка/зонт), но НЕТ
привязки к системе (system_ventilation пуст). Только чтение."""
import json, os, re
from collections import defaultdict, Counter

# скрипт лежит в tools/, данные — в корне проекта
HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(HERE, "ALL-BLOCKS_fixed_2026-06-22.hvac.json")


def s0(x):
    return str(x).strip() if x is not None else ""


def num(x):
    try:
        return float(x or 0)
    except (TypeError, ValueError):
        return 0.0


def block_of(level, number):
    # блок по префиксу уровня "L11 HTL" / "B1 RES" и т.п.
    lv = s0(level)
    m = re.search(r"\b(HTL|RES|OFF|OFC|GFL|B1|B2|PEN|TWR|RET|MAL)\b", lv, re.I)
    if m:
        return m.group(1).upper()
    pre = s0(number).split("-")[0].upper()
    return pre or "?"


def main():
    d = json.load(open(SRC, encoding="utf-8"))
    spaces = d["spaces"]
    vsys = d.get("ventilation_systems", {}) or {}

    total = len(spaces)
    has_vent = 0
    vent_no_sys = []          # есть вентиляция, нет системы
    vent_with_sys = 0
    no_vent_no_sys = 0        # ни вентиляции, ни системы (не интересует, но посчитаем)

    for sp in spaces:
        sup = num(sp.get("supply_m3h"))
        exh = num(sp.get("exhaust_m3h"))
        hood = num(sp.get("hood_m3h"))
        has_v = (sup > 0) or (exh > 0) or (hood > 0)
        sys = s0(sp.get("system_ventilation"))
        if has_v:
            has_vent += 1
            if sys:
                vent_with_sys += 1
            else:
                vent_no_sys.append(sp)
        else:
            if not sys:
                no_vent_no_sys += 1

    # агрегаты по «есть вентиляция, нет системы»
    by_block = defaultdict(lambda: [0, 0.0, 0.0, 0.0])  # cnt, sup, exh, hood
    by_level = defaultdict(lambda: [0, 0.0, 0.0, 0.0])
    by_name = Counter()
    sup_tot = exh_tot = hood_tot = 0.0
    for sp in vent_no_sys:
        b = block_of(sp.get("level"), sp.get("number"))
        sup = num(sp.get("supply_m3h")); exh = num(sp.get("exhaust_m3h")); hood = num(sp.get("hood_m3h"))
        for agg, key in ((by_block, b), (by_level, s0(sp.get("level")))):
            agg[key][0] += 1; agg[key][1] += sup; agg[key][2] += exh; agg[key][3] += hood
        by_name[s0(sp.get("name"))] += 1
        sup_tot += sup; exh_tot += exh; hood_tot += hood

    print("=" * 72)
    print("ИТОГ: помещения с вентиляцией, но без системы (system_ventilation пуст)")
    print("=" * 72)
    print(f"Всего помещений в проекте:          {total}")
    print(f"Систем вентиляции в словаре:        {len(vsys)}")
    print(f"С вентиляцией (sup|exh|hood > 0):    {has_vent}")
    print(f"   из них с привязкой к системе:    {vent_with_sys}")
    print(f"   из них БЕЗ системы:              {len(vent_no_sys)}   <== цель")
    print(f"Без вентиляции и без системы:        {no_vent_no_sys}")
    print()
    print(f"Суммарный расход «без системы»: приток={sup_tot:,.0f}  вытяжка={exh_tot:,.0f}  зонт={hood_tot:,.0f}  м3/ч")
    print(f"  приток+вытяжка(+зонт) общий объём ~ {sup_tot+exh_tot+hood_tot:,.0f} м3/ч")

    print("\n--- по блокам (помещ | приток | вытяжка | зонт, м3/ч) ---")
    for b, (c, su, ex, ho) in sorted(by_block.items(), key=lambda kv: -kv[1][0]):
        print(f"  {b:6} | {c:5} | {su:10,.0f} | {ex:10,.0f} | {ho:9,.0f}")

    print("\n--- по уровням (топ-25 по числу помещений) ---")
    rows = sorted(by_level.items(), key=lambda kv: -kv[1][0])[:25]
    for lv, (c, su, ex, ho) in rows:
        print(f"  {lv:14} | {c:5} | {su:10,.0f} | {ex:10,.0f} | {ho:9,.0f}")

    print("\n--- по именам помещений (топ-25) ---")
    for nm, c in by_name.most_common(25):
        print(f"  {c:5}  {nm}")

    # разбивка по типу вентиляции (что именно не привязано)
    pat = Counter()          # 'supply_only' / 'exhaust_only' / 'both'
    pat_block = defaultdict(Counter)
    for sp in vent_no_sys:
        sup = num(sp.get("supply_m3h")); exh = num(sp.get("exhaust_m3h")); hood = num(sp.get("hood_m3h"))
        ex_any = (exh > 0) or (hood > 0)
        if sup > 0 and ex_any:
            p = "приток+вытяжка"
        elif sup > 0:
            p = "только приток (П-)"
        else:
            p = "только вытяжка (В-)"
        pat[p] += 1
        pat_block[block_of(sp.get("level"), sp.get("number"))][p] += 1
    print("\n--- по типу вентиляции (каких систем не хватает) ---")
    for p, c in pat.most_common():
        print(f"  {c:5}  {p}")
    print("\n--- блок × тип ---")
    cols = ["только вытяжка (В-)", "приток+вытяжка", "только приток (П-)"]
    print(f"  {'блок':6} | " + " | ".join(f"{c:>20}" for c in cols))
    for b in sorted(pat_block, key=lambda x: -sum(pat_block[x].values())):
        print(f"  {b:6} | " + " | ".join(f"{pat_block[b].get(c,0):>20}" for c in cols))

    # выгрузка полного списка в CSV рядом
    out = os.path.join(HERE, "vent_no_system.csv")
    with open(out, "w", encoding="utf-8-sig", newline="") as f:
        f.write("space_id;number;name;level;block;supply_m3h;exhaust_m3h;hood_m3h;area_m2\n")
        for sp in sorted(vent_no_sys, key=lambda s: (s0(s.get("level")), s0(s.get("number")))):
            f.write(";".join(s0(x) for x in (
                sp.get("space_id"), sp.get("number"), sp.get("name"), sp.get("level"),
                block_of(sp.get("level"), sp.get("number")),
                sp.get("supply_m3h"), sp.get("exhaust_m3h"), sp.get("hood_m3h"),
                sp.get("area_m2"))) + "\n")
    print(f"\nПолный список -> {out}  ({len(vent_no_sys)} строк)")


if __name__ == "__main__":
    main()
