# -*- coding: utf-8 -*-
"""Проверочный прогон чистой геом-привязки остекления + покрытие по блокам.

Тонкая обёртка над канонической hvac.revit_link.export_clean_glazing
(вся C#-логика живёт там, единый источник истины). Здесь — только запись
glazing_clean.csv (для apply_glazing_fix.py) и сводка покрытия live↔clean.

Запуск (Revit открыт, мост 8080):
  C:\\Python314\\python.exe D:\\HVAC\\tools\\extract_glazing_clean.py [папка_csv]
"""
import csv
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
sys.path.insert(0, _ROOT)
sys.path.insert(0, _HERE)

from hvac import revit_link as rl  # noqa: E402
import reconcile_glazing as rec  # noqa: E402


def main():
    folder = sys.argv[1] if len(sys.argv) > 1 else _ROOT
    spaces = rec.data_loader.load_spaces(os.path.join(folder, "spaces.csv"))
    sp_by_id = {s.space_id: s for s in spaces}
    print("Помещений:", len(spaces), "— тяну чистое остекление через мост...")

    rows = rl.export_clean_glazing(folder)   # канонический источник

    # запись glazing_clean.csv (формат для apply_glazing_fix.py)
    out_dir = os.path.join(_HERE, "out")
    if not os.path.isdir(out_dir):
        os.makedirs(out_dir)
    clean_path = os.path.join(out_dir, "glazing_clean.csv")
    with open(clean_path, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(["space_id", "element_id", "source", "type",
                    "area_m2", "orientation_deg", "level"])
        for r in rows:
            w.writerow([r["space_id"], r["element_id"], r["link_model"],
                        r["type"], r["element_area"], r["orientation_deg"],
                        r["element_level"]])

    # покрытие по блокам: clean (по помещению) vs live (по связи)
    clean_blk = {}
    for r in rows:
        sp = sp_by_id.get(r["space_id"])
        blk = rec.block_of_space(sp.level if sp else r["element_level"],
                                 sp.number if sp else "")
        try:
            area = float(r["element_area"])
        except Exception:
            area = 0.0
        clean_blk[blk] = clean_blk.get(blk, 0.0) + area

    print("Живая инвентаризация (эталон)...")
    live, _ = rec.live_inventory_by_block()

    print("\n=============== ЧИСТАЯ ПРИВЯЗКА vs ЖИВАЯ МОДЕЛЬ ===============")
    print("%-5s %12s %12s %9s" % ("block", "live_fac", "clean_fac", "cov%"))
    total_live = total_clean = 0.0
    for b in sorted(set(list(clean_blk.keys()) + list(live.keys()))):
        lf = live.get(b, {}).get("facade", 0.0)
        cf = clean_blk.get(b, 0.0)
        total_live += lf
        total_clean += cf
        cov = (100.0 * cf / lf) if lf > 0 else 0
        print("%-5s %12.0f %12.0f %8.0f%%" % (b, lf, cf, cov))
    print("-" * 42)
    print("%-5s %12.0f %12.0f %8.0f%%" % (
        "ИТОГО", total_live, total_clean,
        100.0 * total_clean / total_live if total_live else 0))
    print("\nВсего строк остекления:", len(rows))
    print("Файл:", clean_path)


if __name__ == "__main__":
    main()
