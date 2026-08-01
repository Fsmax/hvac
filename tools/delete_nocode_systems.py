#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Удаление систем БЕЗ инженерного кода (Блок*/Уровень*) во ВСЕХ доменах
(вентиляция, отопление, охлаждение).

Зеркалит project.remove_zone_system (_project_zoning.py):
  - удаляет систему из словаря домена,
  - снимает её назначение у помещений (space.system_* -> ""),
  - удаляет дочерние контуры и снимает их у помещений,
  - для вентиляции дополнительно удаляет парный ahu_loads[name].

«Есть код» = имя начинается с П/В/ПВ (или лат. P/V) + разделитель/символ.
Всё прочее (Блок*, Уровень*) = без кода = удаляется.

Запуск:  python delete_nocode_systems.py [--dry]
"""
import json, os, sys, shutil, re
from collections import Counter

# скрипт лежит в tools/, данные — в корне проекта
HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DST = os.path.join(HERE, "ALL-BLOCKS_fixed_2026-06-22.hvac.json")
DRY = "--dry" in sys.argv

DOMAINS = [
    ("ventilation_systems", "system_ventilation", "ahu_loads"),
    ("heating_systems", "system_heating", None),
    ("cooling_systems", "system_cooling", None),
]


def has_code(name):
    return bool(re.match(r"^(ПВ|П|В|PV|P|V)\s*-?\s*\w", (name or "").strip()))


def main():
    d = json.load(open(DST, encoding="utf-8"))
    spaces = d["spaces"]

    print("=== DRY-RUN ===" if DRY else "=== APPLY ===")
    summary = []
    for cat, fld, paired in DOMAINS:
        systems = d.get(cat, {}) or {}
        used = Counter(s.get(fld, "") for s in spaces if s.get(fld))
        to_del = [n for n in systems if not has_code(n)]
        keep = [n for n in systems if has_code(n)]
        rooms_cleared = sum(used.get(n, 0) for n in to_del)

        if not DRY:
            for n in to_del:
                systems.pop(n, None)
                if paired and isinstance(d.get(paired), dict):
                    d[paired].pop(n, None)
            del_set = set(to_del)
            for sp in spaces:
                if sp.get(fld, "") in del_set:
                    sp[fld] = ""

        cov_before = sum(used.values())
        cov_after = sum(used.get(n, 0) for n in keep)
        summary.append((cat, fld, len(systems) if DRY else len(d.get(cat, {})),
                        len(to_del), len(keep), cov_before, cov_after, rooms_cleared))
        print(f"\n{cat}:")
        print(f"   delete {len(to_del)} no-code, keep {len(keep)} coded")
        print(f"   coverage {fld}: {cov_before} -> {cov_after}  (cleared {rooms_cleared} room refs)")
        if keep:
            print(f"   KEPT: {keep[:6]}{'...' if len(keep)>6 else ''}")

    print("\n--- summary ---")
    print(f"{'domain':22} del keep  cov_before -> cov_after")
    for cat, fld, _, nd, nk, cb, ca, rc in summary:
        print(f"  {cat:22} {nd:3} {nk:4}   {cb:6} -> {ca}")

    if DRY:
        print("\n(dry run — файл не тронут)")
        return

    bak = DST + ".bak_before_nocode_delete"
    if not os.path.exists(bak):
        shutil.copy2(DST, bak)
        print(f"\nBackup -> {bak}")
    else:
        print(f"\nBackup уже существует: {bak}")

    text = json.dumps(d, ensure_ascii=False, indent=2).replace("\n", "\r\n")
    with open(DST, "w", encoding="utf-8", newline="") as f:
        f.write(text)
    print(f"Written -> {DST}")


if __name__ == "__main__":
    main()
