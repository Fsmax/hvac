# -*- coding: utf-8 -*-
"""ПРИМЕНЕНИЕ (отель/офис по HLGC): перепривязать помещения с явным
EQUIPMENT NUMBER на существующие установки и отвязать те, где в HLGC пусто.
RES/OFC и не найденные в HLGC помещения НЕ трогаются.
Авто-зона удаляется только если после операции в ней 0 помещений.
"""
import shutil
from datetime import datetime
from collections import defaultdict, Counter

import openpyxl
from hvac.project import HVACProject
from hvac.io_json import load_project, save_project

XLSX = r"D:\Chorsu HLGC Design Table_.xlsx"
JSON = "ALL-BLOCKS.hvac.json"
AUTO_ZONES = {
    "Блок HTL", "Блок RES", "Блок OFF", "Блок B01", "Блок OFC", "Блок B02",
    "Уровень L04 RES (FFL)", "Уровень L05 RES (FFL)", "Уровень L06 RES (FFL)",
}
COL_NUM, COL_EQ = 2, 34
SKIP_EQ = {"", "supply", "наименование системы", "центр-ный конд-нер"}


def read_hlgc_map():
    wb = openpyxl.load_workbook(XLSX, read_only=True, data_only=True)
    m = {}
    for ws in wb.worksheets:
        for r in ws.iter_rows(values_only=True):
            num = r[COL_NUM] if len(r) > COL_NUM else None
            if num is None:
                continue
            num = str(num).strip()
            if not num or num.lower() in ("room", ""):
                continue
            eq = r[COL_EQ] if len(r) > COL_EQ else None
            eq = "" if eq is None else str(eq).strip()
            if eq.lower() in SKIP_EQ:
                eq = ""
            m[num.upper()] = eq
    wb.close()
    return m


def eng_supply(project):
    return sum(float(getattr(sp, "supply_m3h", 0) or 0)
               for sp in project.spaces
               if (sp.system_ventilation or "").startswith(("П-", "ПВ-")))


def main():
    hlgc = read_hlgc_map()
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    bak = f"{JSON}.bak_before_hlgc_reassign_{ts}"
    shutil.copy2(JSON, bak)
    print(f"Бэкап: {bak}")

    p = HVACProject()
    load_project(p, JSON)
    valid = set(p.ventilation_systems.keys())
    n_sys_before = len(p.ventilation_systems)
    eng_before = eng_supply(p)

    reassign = defaultdict(list)   # target -> [space_id]
    unassign = []                  # [space_id]
    notfound = 0
    for sp in p.spaces:
        if (sp.system_ventilation or "") not in AUTO_ZONES:
            continue
        key = (sp.number or "").strip().upper()
        if key not in hlgc:
            notfound += 1
            continue
        eq = hlgc[key]
        if not eq:
            unassign.append(sp.space_id)
        elif eq in valid:
            reassign[eq].append(sp.space_id)
        else:
            notfound += 1   # EQUIPMENT NUMBER не среди систем — не трогаем

    # Применяем
    moved = 0
    for tgt, ids in reassign.items():
        moved += p.assign_rooms_to_system("ventilation", ids, tgt)
    cleared = p.clear_rooms_assignment("ventilation", unassign, "system")
    print(f"Перепривязано: {moved} (целей {len(reassign)}); "
          f"отвязано: {cleared}; не тронуто (нет в HLGC/чужой eq): {notfound}")

    # Удаляем авто-зоны, которые опустели
    counts = Counter((sp.system_ventilation or "") for sp in p.spaces)
    deleted, kept = [], []
    for z in sorted(AUTO_ZONES):
        if counts.get(z, 0) == 0:
            if p.remove_zone_system("ventilation", z):
                deleted.append(z)
        else:
            kept.append((z, counts.get(z, 0)))
    # чистим производные кэши от удалённых
    for attr in ("ahu_loads", "ahu_processes", "duct_networks",
                 "duct_networks_detailed", "grille_picks"):
        d = getattr(p, attr, None)
        if isinstance(d, dict):
            for z in deleted:
                d.pop(z, None)

    save_project(p, JSON, force_self_contained=True)
    print(f"Сохранено: {JSON}")

    # Контроль
    p2 = HVACProject()
    load_project(p2, JSON)
    eng_after = eng_supply(p2)
    print("\n--- КОНТРОЛЬ ПОСЛЕ ---")
    print(f"Систем вентиляции: {n_sys_before} -> {len(p2.ventilation_systems)}")
    print(f"Σприток инженерных П-/ПВ-: {eng_before:.0f} -> {eng_after:.0f} "
          f"(+{eng_after-eng_before:.0f} м³/ч от перепривязки)")
    print(f"Удалено авто-зон (опустели): {deleted or '—'}")
    print("Остаются авто-зоны (не пустые, RES/OFC/хвосты):")
    c2 = Counter((sp.system_ventilation or "") for sp in p2.spaces)
    for z in sorted(AUTO_ZONES):
        if z in p2.ventilation_systems:
            sup = sum(float(getattr(sp, "supply_m3h", 0) or 0)
                      for sp in p2.spaces if sp.system_ventilation == z)
            print(f"   {z:24} помещений={c2.get(z,0):4}  Σприток={sup:8.0f}")
    # сводка landing по целям
    print("\nКуда легли перепривязанные:")
    for tgt in sorted(reassign):
        got = sum(1 for sp in p2.spaces if sp.system_ventilation == tgt
                  and sp.space_id in set(reassign[tgt]))
        print(f"   → {tgt:18} ожидалось {len(reassign[tgt]):4}, "
              f"факт на цели из набора {got}")


if __name__ == "__main__":
    main()
