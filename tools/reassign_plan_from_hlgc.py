# -*- coding: utf-8 -*-
"""DRY-RUN: карта перепривязки помещений 9 авто-зон по HLGC EQUIPMENT NUMBER.

Стыковка как в io_hlgc: HLGC col3 (1-idx) = номер помещения = Space.number,
HLGC col35 (1-idx) = EQUIPMENT NUMBER = целевая система вентиляции.
Ничего не пишет — только показывает план.
"""
import openpyxl
from collections import defaultdict, Counter
from hvac.project import HVACProject
from hvac.io_json import load_project

XLSX = r"D:\Chorsu HLGC Design Table_.xlsx"
JSON = "ALL-BLOCKS.hvac.json"
AUTO_ZONES = {
    "Блок HTL", "Блок RES", "Блок OFF", "Блок B01", "Блок OFC", "Блок B02",
    "Уровень L04 RES (FFL)", "Уровень L05 RES (FFL)", "Уровень L06 RES (FFL)",
}
COL_NUM = 2   # 0-idx -> col 3 (1-idx) номер
COL_EQ = 34   # 0-idx -> col 35 (1-idx) EQUIPMENT NUMBER
HEADER_TOKENS = {"room", "supply", "наименование системы", "выбор системы",
                 "центр-ный конд-нер", "equipment number", ""}


def read_hlgc_map():
    wb = openpyxl.load_workbook(XLSX, read_only=True, data_only=True)
    m = {}            # number_upper -> equipment (str or "")
    name_of = {}
    n_rows = 0
    for ws in wb.worksheets:
        for r in ws.iter_rows(values_only=True):
            num = r[COL_NUM] if len(r) > COL_NUM else None
            if num is None:
                continue
            num = str(num).strip()
            if not num or num.lower() in HEADER_TOKENS:
                continue
            eq = r[COL_EQ] if len(r) > COL_EQ else None
            eq = ("" if eq is None else str(eq).strip())
            if eq.lower() in ("supply", "наименование системы",
                              "центр-ный конд-нер"):
                eq = ""
            m[num.upper()] = eq
            nm = r[4] if len(r) > 4 else None
            name_of[num.upper()] = ("" if nm is None else str(nm).strip())
            n_rows += 1
    wb.close()
    return m, name_of, n_rows


def main():
    hlgc, name_of, n_rows = read_hlgc_map()
    n_eq = sum(1 for v in hlgc.values() if v)
    print(f"HLGC: строк с номером {n_rows}, из них с EQUIPMENT NUMBER {n_eq}, "
          f"пустых {n_rows - n_eq}")

    project = HVACProject()
    load_project(project, JSON)
    valid_systems = set(project.ventilation_systems.keys())

    targets = [sp for sp in project.spaces
               if (sp.system_ventilation or "") in AUTO_ZONES]
    print(f"Помещений в 9 авто-зонах: {len(targets)}")

    # Стыковка
    matched = notfound = 0
    to_reassign = defaultdict(list)   # target_system -> [spaces]
    to_unassign = []
    to_unknown_sys = defaultdict(list)  # eq которой нет среди систем проекта
    for sp in targets:
        key = (sp.number or "").strip().upper()
        if key not in hlgc:
            notfound += 1
            continue
        matched += 1
        eq = hlgc[key]
        if not eq:
            to_unassign.append(sp)
        elif eq in valid_systems:
            to_reassign[eq].append(sp)
        else:
            to_unknown_sys[eq].append(sp)

    print(f"\nСтыковка по номеру: совпало {matched}, нет в HLGC {notfound}")

    def sup(sps):
        return sum(float(getattr(s, "supply_m3h", 0) or 0) for s in sps)

    print(f"\n=== ПЛАН: перепривязать на существующие установки "
          f"({sum(len(v) for v in to_reassign.values())} помещ.) ===")
    for tgt in sorted(to_reassign):
        sps = to_reassign[tgt]
        src = Counter((s.system_ventilation or "") for s in sps)
        print(f"  → {tgt:18} +{len(sps):4} помещ, +{sup(sps):8.0f} м³/ч  "
              f"(из: {dict(src)})")

    if to_unknown_sys:
        print(f"\n=== ⚠ EQUIPMENT NUMBER, которой НЕТ среди систем проекта "
              f"(надо создать?) ===")
        for tgt in sorted(to_unknown_sys):
            sps = to_unknown_sys[tgt]
            print(f"  ? {tgt:18} {len(sps):4} помещ, {sup(sps):8.0f} м³/ч")

    print(f"\n=== ПЛАН: отвязать (в HLGC пусто) : {len(to_unassign)} помещ, "
          f"{sup(to_unassign):.0f} м³/ч ===")
    by_src = Counter((s.system_ventilation or "") for s in to_unassign)
    for src, c in by_src.most_common():
        print(f"     из {src:20} {c:4} помещ")

    if notfound:
        print(f"\n=== ⚠ Нет в HLGC по номеру : {notfound} помещ "
              f"(останутся как есть / решить отдельно) ===")
        ex = [sp for sp in targets
              if (sp.number or "").strip().upper() not in hlgc][:15]
        for sp in ex:
            print(f"     {sp.number:14} {sp.room_type:18} "
                  f"{sp.system_ventilation} (приток {getattr(sp,'supply_m3h',0):.0f})")


if __name__ == "__main__":
    main()
