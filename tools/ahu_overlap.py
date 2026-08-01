# -*- coding: utf-8 -*-
"""Кросс-таблица приточек: схемы именования, этажи, площади, дамп фантомов."""
import json, sys
from collections import defaultdict

SUPPLY_KINDS = {"ahu", "supply_fan"}


def scheme(name):
    n = name.strip()
    if n.startswith("Блок "):
        return "AUTO: Блок*"
    if n.startswith("Уровень "):
        return "AUTO: Уровень*(FFL)"
    if n.startswith("ПВ-"):
        return "ENG: ПВ-*"
    if n.startswith("П-"):
        return "ENG: П-*"
    return "прочее"


def main(path):
    data = json.load(open(path, encoding="utf-8"))
    vsys = data.get("ventilation_systems", {}) or {}
    spaces = data.get("spaces", []) or []

    rooms = defaultdict(list)
    for sp in spaces:
        nm = sp.get("system_ventilation") or ""
        if nm:
            rooms[nm].append(sp)

    def is_supply(v):
        return (v.get("kind", "ahu") in SUPPLY_KINDS
                or "supply" in (v.get("system_type", "") or ""))

    # сводка по схемам
    agg = defaultdict(lambda: {"n_sys": 0, "n_rooms": 0, "supply": 0.0, "area": 0.0})
    per_level_by_scheme = defaultdict(lambda: defaultdict(set))
    for nm, v in vsys.items():
        if not is_supply(v):
            continue
        sc = scheme(nm)
        rs = rooms.get(nm, [])
        agg[sc]["n_sys"] += 1
        agg[sc]["n_rooms"] += len(rs)
        agg[sc]["supply"] += sum(float(r.get("supply_m3h", 0) or 0) for r in rs)
        agg[sc]["area"] += sum(float(r.get("area_m2", 0) or 0) for r in rs)
        for r in rs:
            per_level_by_scheme[sc][r.get("level", "?")].add(nm)

    print(f"\n===== Схемы приточек: {path} =====")
    print(f"{'Схема':22} {'систем':>7} {'помещ':>7} {'Σприток,м³/ч':>14} {'Σплощадь,м²':>13}")
    for sc, d in sorted(agg.items()):
        print(f"{sc:22} {d['n_sys']:7} {d['n_rooms']:7} {d['supply']:14.0f} {d['area']:13.0f}")

    # Пересечение по этажам: AUTO-схемы vs ENG-схемы
    eng_levels = set()
    auto_levels = set()
    for sc, lv in per_level_by_scheme.items():
        if sc.startswith("ENG"):
            eng_levels |= set(lv.keys())
        if sc.startswith("AUTO"):
            auto_levels |= set(lv.keys())
    overlap = sorted(eng_levels & auto_levels)
    print(f"\nЭтажи, где ОДНОВРЕМЕННО и ENG (П/ПВ), и AUTO (Блок/Уровень) приточки:")
    print(f"  {len(overlap)} этажей: {overlap}")

    # Дамп фантомов / near-zero
    print("\n===== Дамп проблемных приточек =====")
    targets = []
    for nm, v in vsys.items():
        if not is_supply(v):
            continue
        rs = rooms.get(nm, [])
        sup = sum(float(r.get("supply_m3h", 0) or 0) for r in rs)
        if len(rs) == 0 or sup < 100:   # фантом или почти нулевой приток
            targets.append((nm, v, rs, sup))
    for nm, v, rs, sup in sorted(targets, key=lambda t: t[3]):
        types = defaultdict(int)
        levels = set()
        for r in rs:
            types[r.get("room_type", "?")] += 1
            levels.add(r.get("level", "?"))
        print(f"\n  ▶ {nm!r}  (помещений={len(rs)}, Σприток={sup:.0f} м³/ч, этажи={sorted(levels)})")
        for t, c in sorted(types.items(), key=lambda x: -x[1]):
            print(f"       {c:4} × {t}")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "ALL-BLOCKS.hvac.json")
