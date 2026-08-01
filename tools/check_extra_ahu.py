# -*- coding: utf-8 -*-
"""Поиск лишних приточных установок в project JSON.

Лишняя приточка = VentilationSystem приточного вида (kind ahu/supply_fan,
либо system_type содержит 'supply'), которая:
  - не обслуживает ни одного помещения (n_spaces == 0)  -> СИРОТА
  - обслуживает помещения, но суммарный приток == 0      -> НУЛЕВОЙ ПРИТОК
Плюс детектор дублей по нормализованному имени.
"""
import json
import sys
from collections import defaultdict

SUPPLY_KINDS = {"ahu", "supply_fan"}


def load(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def analyze(path):
    data = load(path)
    vsys = data.get("ventilation_systems", {}) or {}
    spaces = data.get("spaces", []) or []

    # агрегируем помещения по системе вентиляции
    by_sys_n = defaultdict(int)
    by_sys_supply = defaultdict(float)
    by_sys_exhaust = defaultdict(float)
    assigned_names = set()
    for sp in spaces:
        name = sp.get("system_ventilation") or ""
        if not name:
            continue
        assigned_names.add(name)
        by_sys_n[name] += 1
        by_sys_supply[name] += float(sp.get("supply_m3h", 0) or 0)
        by_sys_exhaust[name] += float(sp.get("exhaust_m3h", 0) or 0)

    print(f"\n===== {path} =====")
    print(f"Всего систем вентиляции в проекте : {len(vsys)}")
    print(f"Всего помещений                   : {len(spaces)}")
    print(f"Имён систем, реально назначенных   : {len(assigned_names)}")

    def is_supply(v):
        return (v.get("kind", "ahu") in SUPPLY_KINDS
                or "supply" in (v.get("system_type", "") or ""))

    supply_systems = {n: v for n, v in vsys.items() if is_supply(v)}
    print(f"Из них приточных (supply) систем   : {len(supply_systems)}")

    orphans = []          # 0 помещений
    zero_supply = []      # есть помещения, но приток 0
    ok = []
    for n, v in sorted(supply_systems.items()):
        nsp = by_sys_n.get(n, 0)
        sup = by_sys_supply.get(n, 0.0)
        if nsp == 0:
            orphans.append((n, v))
        elif sup <= 0.0:
            zero_supply.append((n, v, nsp, by_sys_exhaust.get(n, 0.0)))
        else:
            ok.append((n, v, nsp, sup))

    # дубли по нормализованному имени
    norm = defaultdict(list)
    for n in vsys:
        key = "".join(ch for ch in n.lower() if ch.isalnum())
        norm[key].append(n)
    dups = {k: names for k, names in norm.items() if len(names) > 1}

    print(f"\n--- РАБОЧИЕ приточки (приток > 0) : {len(ok)} ---")
    for n, v, nsp, sup in ok:
        print(f"  OK  {n!r:28} kind={v.get('kind','ahu'):11} "
              f"помещений={nsp:4}  Σприток={sup:10.0f} м³/ч")

    print(f"\n--- ЛИШНИЕ: СИРОТЫ (0 помещений) : {len(orphans)} ---")
    for n, v in orphans:
        print(f"  !!  {n!r:28} kind={v.get('kind','ahu'):11} "
              f"type={v.get('system_type','')}  has_heater={v.get('has_heater')}"
              f"  has_cooler={v.get('has_cooler')}")

    print(f"\n--- ЛИШНИЕ: НУЛЕВОЙ ПРИТОК (только вытяжка/NC) : {len(zero_supply)} ---")
    for n, v, nsp, exh in zero_supply:
        print(f"  ?   {n!r:28} kind={v.get('kind','ahu'):11} "
              f"помещений={nsp:4}  Σприток=0  Σвытяжка={exh:.0f} м³/ч")

    print(f"\n--- ВОЗМОЖНЫЕ ДУБЛИ ИМЁН : {len(dups)} ---")
    for k, names in dups.items():
        print(f"  ~   {names}")

    # системы, назначенные помещениям, но отсутствующие в реестре vsys
    missing = assigned_names - set(vsys.keys())
    print(f"\n--- Назначены помещениям, но НЕТ в реестре систем : {len(missing)} ---")
    for n in sorted(missing):
        print(f"  x   {n!r}  (помещений={by_sys_n[n]}, Σприток={by_sys_supply[n]:.0f})")

    return {
        "n_vsys": len(vsys), "n_supply": len(supply_systems),
        "orphans": [n for n, _ in orphans],
        "zero_supply": [n for n, *_ in zero_supply],
        "dups": dups, "missing": sorted(missing),
    }


if __name__ == "__main__":
    paths = sys.argv[1:] or ["ALL-BLOCKS.hvac.json"]
    for p in paths:
        analyze(p)
