#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Привязка «есть в проекте, но без привязки» помещений к их системам по HLGC.

Правило (опция A сверки): для каждого помещения проекта с ПУСТЫМ
`system_ventilation`, если его номер есть в HLGC Design Table и назначенная
там система (Supply, col 34) уже существует в проекте — проставляем эту
систему. Помещения без пары в HLGC или с несуществующей системой не трогаем.

В HLGC приток==вытяжка у всех помещений, поэтому берём col 34.

Запуск:  python assign_from_hlgc.py [--dry]
"""
import openpyxl, re, json, os, sys, shutil
from collections import defaultdict, Counter

HLGC = r"D:\Chorsu HLGC Design Table_.xlsx"
# скрипт лежит в tools/, данные — в корне проекта
HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DST = os.path.join(HERE, "ALL-BLOCKS_fixed_2026-06-22.hvac.json")
DRY = "--dry" in sys.argv
SYS = re.compile(r"^\s*(ПВ|П|В)\s*-", re.I)


def s0(s):
    return str(s).strip() if s is not None else ""


def is_sys(s):
    return bool(SYS.match(s0(s)))


def main():
    # --- HLGC: номер -> система (col 34) ---
    wb = openpyxl.load_workbook(HLGC, read_only=True, data_only=True)
    num2sys = {}
    conflicts = []
    for sn in ["TOWER A", "TOWER B"]:
        for r in wb[sn].iter_rows(min_row=2, values_only=True):
            num = s0(r[2]) if len(r) > 2 else ""
            sysn = s0(r[34]) if len(r) > 34 else ""
            if num and is_sys(sysn):
                if num in num2sys and num2sys[num] != sysn:
                    conflicts.append((num, num2sys[num], sysn))
                num2sys[num] = sysn
    wb.close()
    print(f"HLGC: {len(num2sys)} помещений с системой | конфликтов номеров: {len(conflicts)}")
    if conflicts:
        for c in conflicts[:10]:
            print("   CONFLICT", c)

    # --- проект ---
    d = json.load(open(DST, encoding="utf-8"))
    vsys = set(d.get("ventilation_systems", {}) or {})
    by_num = defaultdict(list)
    for sp in d["spaces"]:
        by_num[s0(sp["number"])].append(sp)

    assigned = Counter()
    skip_no_sys_in_proj = Counter()
    skip_already_linked = 0          # хоть одна копия номера уже имеет систему
    multi_empty = 0                  # номер задвоен, все копии пусты — назначаем одной
    for num, sysn in num2sys.items():
        sps = by_num.get(num, [])
        if not sps:
            continue                       # номера нет в проекте (мусорные/отсутствуют)
        if sysn not in vsys:
            skip_no_sys_in_proj[sysn] += 1
            continue                       # системы нет в проекте (напр. ПВ-B1-01)
        states = [s0(sp.get("system_ventilation", "")) for sp in sps]
        if any(states):
            # хотя бы одна копия уже привязана (к этой или другой системе) —
            # не трогаем, иначе двойной счёт по дублям номеров.
            skip_already_linked += 1
            continue
        # все копии номера пусты → помещение реально без системы: назначаем ОДНОЙ
        if len(sps) > 1:
            multi_empty += 1
        if not DRY:
            sps[0]["system_ventilation"] = sysn
        assigned[sysn] += 1

    print(f"\n{'='*46}\n{'DRY-RUN' if DRY else 'APPLY'} — назначено по системам:")
    for k, v in assigned.most_common():
        print(f"   {k:16} +{v}")
    print(f"ИТОГО назначено: {sum(assigned.values())} "
          f"| пропущено (уже привязан хотя бы один двойник): {skip_already_linked} "
          f"| задвоенных-пустых (взял 1 копию): {multi_empty}")
    if skip_no_sys_in_proj:
        print("Пропущено (система отсутствует в проекте):", dict(skip_no_sys_in_proj))

    if DRY:
        print("\n(dry run — файл не тронут)")
        return

    bak = DST + ".bak_before_hlgc_assign"
    if not os.path.exists(bak):
        shutil.copy2(DST, bak)
        print(f"\nBackup -> {bak}")
    text = json.dumps(d, ensure_ascii=False, indent=2).replace("\n", "\r\n")
    with open(DST, "w", encoding="utf-8", newline="") as f:
        f.write(text)
    print(f"Written -> {DST}")


if __name__ == "__main__":
    main()
