# -*- coding: utf-8 -*-
"""Сверка эталонной ведомости 'Установки A-B (данные).xlsx' с установками,
которые сейчас есть в программе (ALL-BLOCKS.hvac.json).

Эталон = реальные установки, которые инженер утвердил.
Всё, что в программе есть, а в эталоне нет, — кандидат в лишние.
"""
import openpyxl
from collections import defaultdict
from hvac.project import HVACProject
from hvac.io_json import load_project

XLSX = r"D:\Установки A-B (данные).xlsx"
JSON = "ALL-BLOCKS.hvac.json"
SKIP = {"установка", "(не назначено)", "итого", ""}


def read_schedule():
    wb = openpyxl.load_workbook(XLSX, read_only=True, data_only=True)
    rows = {}          # name -> {sheet, type, floors, n, supply, exhaust}
    collisions = defaultdict(list)
    for ws in wb.worksheets:
        for r in ws.iter_rows(values_only=True):
            name = (str(r[0]).strip() if r[0] is not None else "")
            if name.lower() in SKIP:
                continue
            rec = {"sheet": ws.title, "type": r[1], "floors": r[2],
                   "n": r[3], "supply": r[5], "exhaust": r[6]}
            if name in rows:
                collisions[name].append(rec)
                collisions[name].append(rows[name])
            rows[name] = rec
    wb.close()
    return rows, collisions


def main():
    sched, collisions = read_schedule()
    sched_supply = {n for n, v in sched.items()
                    if str(v["type"]).strip() in ("П", "ПВ")}
    sched_exhaust = {n for n, v in sched.items()
                     if str(v["type"]).strip() == "В"}
    print(f"Эталон 'Установки A-B': всего {len(sched)} установок "
          f"(приточных П/ПВ={len(sched_supply)}, вытяжных В={len(sched_exhaust)})")

    if collisions:
        print(f"\n⚠ КОЛЛИЗИИ ИМЁН в самой ведомости (одно имя в обоих блоках):")
        for n, recs in collisions.items():
            uniq = {(x["sheet"], x["supply"]) for x in recs}
            print(f"   {n!r}: " + " ; ".join(
                f"{x['sheet']}/приток={x['supply']}" for x in dict(
                    (id(x), x) for x in recs).values()))

    project = HVACProject()
    load_project(project, JSON)
    SUP_KINDS = {"ahu", "supply_fan"}
    prog = {}
    for nm, v in project.ventilation_systems.items():
        is_sup = (v.kind in SUP_KINDS or "supply" in (v.system_type or ""))
        prog[nm] = is_sup
    prog_supply = {n for n, s in prog.items() if s}
    print(f"\nПрограмма ALL-BLOCKS: всего {len(prog)} систем "
          f"(приточных={len(prog_supply)})")

    # supply-системы в программе, которых НЕТ в эталоне
    extra = sorted(prog_supply - sched_supply)
    missing = sorted(sched_supply - prog_supply)
    matched = sorted(prog_supply & sched_supply)

    # расход по системам в программе
    psupply = defaultdict(float)
    for sp in project.spaces:
        nm = sp.system_ventilation or ""
        if nm:
            psupply[nm] += float(getattr(sp, "supply_m3h", 0) or 0)

    print(f"\n================ ЛИШНИЕ: приточки в программе, которых НЕТ "
          f"в эталоне ({len(extra)}) ================")
    for n in extra:
        print(f"  ✗ {n!r:26} Σприток={psupply.get(n,0):9.0f} м³/ч  "
              f"(помещений={sum(1 for sp in project.spaces if sp.system_ventilation==n)})")

    print(f"\n---------------- В эталоне есть, в программе НЕТ "
          f"({len(missing)}) ----------------")
    for n in missing:
        print(f"  ? {n!r:26} (эталон: приток={sched[n]['supply']}, "
              f"этажи={sched[n]['floors']})")

    print(f"\n---------------- Совпали приточки ({len(matched)}) "
          f"----------------")
    for n in matched:
        sp_s = psupply.get(n, 0)
        sc_s = sched[n]["supply"] or 0
        flag = "" if abs(sp_s - sc_s) < 1 else f"  ⚠ расход прог={sp_s:.0f} vs эталон={sc_s}"
        print(f"  ✓ {n!r:26} {sp_s:9.0f} м³/ч{flag}")


if __name__ == "__main__":
    main()
