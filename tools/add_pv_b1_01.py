#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Добавление недостающей системы ПВ-B1-01 (есть в Excel-дизайне, нет в проекте).

Создаётся ЕДИНООБРАЗНО с сёстрами: копия определения ПВ-B1-02 (тип
supply_exhaust, дефолтные температуры/без рекуперации — как все 38 систем
проекта) + пустой ahu_loads. Помещение (HLGC №2408) сейчас не сматчено по
номеру, поэтому система создаётся без привязок — комната подвяжется позже.

Идемпотентно. Запуск: python add_pv_b1_01.py [--dry]
"""
import json, os, sys, shutil

# скрипт лежит в tools/, данные — в корне проекта
HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DST = os.path.join(HERE, "ALL-BLOCKS_fixed_2026-06-22.hvac.json")
NEW = "ПВ-B1-01"
TMPL = "ПВ-B1-02"
DRY = "--dry" in sys.argv


def insert_before(dct, anchor, key, value):
    """Возвращает новый dict со вставкой key->value перед anchor (или в конец)."""
    out = {}
    placed = False
    for k, v in dct.items():
        if k == anchor:
            out[key] = value
            placed = True
        out[k] = v
    if not placed:
        out[key] = value
    return out


def main():
    d = json.load(open(DST, encoding="utf-8"))
    vs = d["ventilation_systems"]
    al = d.get("ahu_loads", {})
    if NEW in vs:
        print(f"{NEW} уже существует — ничего не делаю.")
        return
    if TMPL not in vs:
        print(f"ОШИБКА: шаблон {TMPL} не найден."); return

    new_sys = dict(vs[TMPL]); new_sys["name"] = NEW
    new_load = dict(al.get(TMPL, {}))
    for k in new_load:
        if isinstance(new_load[k], (int, float)):
            new_load[k] = 0 if isinstance(new_load[k], int) else 0.0

    print("=== DRY-RUN ===" if DRY else "=== APPLY ===")
    print(f"добавляю систему {NEW} (шаблон {TMPL}):")
    print(json.dumps(new_sys, ensure_ascii=False, indent=2))
    print(f"ventilation_systems: {len(vs)} -> {len(vs)+1} | ahu_loads: {len(al)} -> {len(al)+1}")

    if DRY:
        print("\n(dry run — файл не тронут)")
        return

    d["ventilation_systems"] = insert_before(vs, TMPL, NEW, new_sys)
    d["ahu_loads"] = insert_before(al, TMPL, NEW, new_load)

    bak = DST + ".bak_before_add_pvb101"
    if not os.path.exists(bak):
        shutil.copy2(DST, bak)
        print(f"\nBackup -> {bak}")
    text = json.dumps(d, ensure_ascii=False, indent=2).replace("\n", "\r\n")
    with open(DST, "w", encoding="utf-8", newline="") as f:
        f.write(text)
    print(f"Written -> {DST}")


if __name__ == "__main__":
    main()
