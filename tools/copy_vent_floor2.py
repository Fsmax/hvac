# -*- coding: utf-8 -*-
"""Копирует ручную настройку вентиляции с этажа 2 (L02 HTL) на этажи 3-9 (HTL).

Шаблон  = помещения L02 HTL с vent_user_modified=True (45 шт).
Сопоставление = по номеру без цифры этажа: HTL-201.a -> ключ '01.a'.
Для каждого совпавшего помещения L03..L09 HTL копируем supply/exhaust/hood,
ставим vent_user_modified=True и пересчитываем ach = max(supply,exhaust)/volume
(как панель вентиляции, по объёму ЦЕЛЕВОГО помещения).
"""
import json, shutil, datetime, sys

PATH = "ALL-BLOCKS_fixed_2026-06-22.hvac.json"
TEMPLATE_LEVEL = "L02 HTL (FFL)"
# L03..L08 — типовые этажи, геометрически идентичны L02.
# L09 ИСКЛЮЧЁН: другая планировка (площади/типы комнат не совпадают с L02),
# перенос расходов по номеру даёт неверный ACH. Настраивается отдельно.
TARGET_LEVELS = [f"L0{n} HTL (FFL)" for n in range(3, 9)]  # L03..L08
COPY_FIELDS = ["supply_m3h", "exhaust_m3h", "hood_m3h"]
DRY = "--write" not in sys.argv


def room_key(num: str) -> str:
    # 'HTL-201.a' -> '201.a' -> '01.a' (снимаем первую цифру = этаж)
    body = num.split("-", 1)[1]
    return body[1:]


def main():
    d = json.load(open(PATH, encoding="utf-8"))
    spaces = d["spaces"]

    template = {}
    for s in spaces:
        if s["level"] == TEMPLATE_LEVEL and s.get("vent_user_modified"):
            template[room_key(s["number"])] = s
    print(f"Шаблон L02 HTL: {len(template)} изменённых помещений")

    per_floor = {L: {"matched": 0, "changed": 0, "missing": []} for L in TARGET_LEVELS}
    target_keys_by_floor = {L: set() for L in TARGET_LEVELS}

    for s in spaces:
        L = s["level"]
        if L not in TARGET_LEVELS:
            continue
        k = room_key(s["number"])
        target_keys_by_floor[L].add(k)
        t = template.get(k)
        if not t:
            continue
        per_floor[L]["matched"] += 1
        before = (s["supply_m3h"], s["exhaust_m3h"], s["hood_m3h"],
                  s.get("vent_user_modified", False), round(s["ach_calculated"], 4))
        for f in COPY_FIELDS:
            s[f] = t[f]
        s["vent_user_modified"] = True
        vol = s.get("volume_m3", 0.0)
        s["ach_calculated"] = (max(s["supply_m3h"], s["exhaust_m3h"]) / vol) if vol > 0 else 0.0
        after = (s["supply_m3h"], s["exhaust_m3h"], s["hood_m3h"],
                 s["vent_user_modified"], round(s["ach_calculated"], 4))
        if before != after:
            per_floor[L]["changed"] += 1

    # помещения-шаблоны, которым не нашлось пары на конкретном этаже
    for L in TARGET_LEVELS:
        for k, t in template.items():
            if k not in target_keys_by_floor[L]:
                per_floor[L]["missing"].append(t["number"])

    print(f"\n{'этаж':16} {'совпало':>8} {'изменено':>9}   нет аналога шаблонной комнаты")
    total_changed = 0
    for L in TARGET_LEVELS:
        p = per_floor[L]
        total_changed += p["changed"]
        miss = ", ".join(p["missing"]) if p["missing"] else "-"
        print(f"{L:16} {p['matched']:>8} {p['changed']:>9}   {miss}")
    print(f"\nВсего помещений изменено: {total_changed}")

    if DRY:
        print("\n[DRY-RUN] файл не записан. Запуск с --write для применения.")
        return

    stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    backup = f"{PATH}.bak-floorcopy-{stamp}"
    shutil.copy2(PATH, backup)
    print(f"\nБэкап: {backup}")
    with open(PATH, "w", encoding="utf-8") as f:
        json.dump(d, f, ensure_ascii=False, indent=2, default=str)
    print(f"Записано: {PATH}")


if __name__ == "__main__":
    main()
