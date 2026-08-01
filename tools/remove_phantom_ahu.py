# -*- coding: utf-8 -*-
"""Удаление 10 фантомных приточек (автозоны с нулевым/копеечным притоком).

Работает через родной API программы (remove_zone_system), поэтому корректно
снимает привязку помещений и удаляет дочерние зоны воздуховодов.
Делает бэкап, страховочно отказывается удалять систему с притоком >= 100 м³/ч,
сверяет, что инженерные П-/ПВ- установки не затронуты.
"""
import sys, shutil
from datetime import datetime
from collections import defaultdict

from hvac.project import HVACProject
from hvac.io_json import load_project, save_project

PATH = "ALL-BLOCKS.hvac.json"
PHANTOMS = [
    "Блок MZN", "Блок GFL",
    "Уровень L04 OFF (FFL)", "Уровень L05 OFF (FFL)",
    "Уровень L06 OFF (FFL)", "Уровень L07 OFF (FFL)",
    "Уровень L08 OFF (FFL)", "Уровень L09 OFF (FFL)",
    "Уровень L10 OFF (FFL)", "Уровень L11 OFF (FFL)",
]
SAFETY_SUPPLY_LIMIT = 100.0   # м³/ч — выше этого систему НЕ удаляем


def supply_by_system(project):
    agg = defaultdict(float)
    rooms = defaultdict(list)
    for sp in project.spaces:
        nm = sp.system_ventilation or ""
        if nm:
            agg[nm] += float(getattr(sp, "supply_m3h", 0) or 0)
            rooms[nm].append(sp)
    return agg, rooms


def eng_checksum(project):
    return sum(float(getattr(sp, "supply_m3h", 0) or 0)
               for sp in project.spaces
               if (sp.system_ventilation or "").startswith(("П-", "ПВ-")))


def main():
    # 1. Бэкап
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    bak = f"{PATH}.bak_before_phantom_cleanup_{ts}"
    shutil.copy2(PATH, bak)
    print(f"Бэкап: {bak}")

    # 2. Загрузка
    project = HVACProject()
    load_project(project, PATH)
    n_before = len(project.ventilation_systems)
    chk_before = eng_checksum(project)
    agg, rooms = supply_by_system(project)
    print(f"Систем вентиляции ДО: {n_before}")
    print(f"Контрольная Σприток инженерных П-/ПВ- ДО: {chk_before:.0f} м³/ч")

    # 3. Страховочная проверка + дамп того, что отвяжется
    print("\n--- Проверка целей и помещения, которые станут без приточки ---")
    unassigned_nonNC = []
    for nm in PHANTOMS:
        if nm not in project.ventilation_systems:
            print(f"  ПРОПУСК (нет в проекте): {nm!r}")
            continue
        sup = agg.get(nm, 0.0)
        rs = rooms.get(nm, [])
        if sup >= SAFETY_SUPPLY_LIMIT:
            print(f"  !!! ОТКАЗ: {nm!r} имеет приток {sup:.0f} ≥ {SAFETY_SUPPLY_LIMIT} — НЕ удаляю")
            continue
        for sp in rs:
            rt = sp.room_type
            if rt not in ("Лестница", "Лифт / шахта"):
                unassigned_nonNC.append((nm, sp.number, rt,
                                         float(getattr(sp, "supply_m3h", 0) or 0)))
        ok = project.remove_zone_system("ventilation", nm)
        print(f"  удалено: {nm!r:26} (помещений отвязано={len(rs)}, "
              f"Σприток было={sup:.0f}) -> {ok}")

    # 4. Чистим производные кэши, где имена могли остаться ключами
    for attr in ("ahu_loads", "ahu_processes", "duct_networks",
                 "duct_networks_detailed", "grille_picks"):
        d = getattr(project, attr, None)
        if isinstance(d, dict):
            for nm in PHANTOMS:
                d.pop(nm, None)

    # 5. Сохранение (принудительно self-contained, чтобы не потерять геометрию)
    save_project(project, PATH, force_self_contained=True)
    print(f"\nСохранено: {PATH}")

    # 6. Контроль: перезагружаем и проверяем
    p2 = HVACProject()
    load_project(p2, PATH)
    n_after = len(p2.ventilation_systems)
    chk_after = eng_checksum(p2)
    still = [nm for nm in PHANTOMS if nm in p2.ventilation_systems]
    print(f"\n--- КОНТРОЛЬ ПОСЛЕ ---")
    print(f"Систем вентиляции: {n_before} -> {n_after}  (ожидалось -{len(PHANTOMS)})")
    print(f"Σприток инженерных П-/ПВ-: {chk_before:.0f} -> {chk_after:.0f}  "
          f"(дельта {chk_after - chk_before:+.0f}, должно быть 0)")
    print(f"Фантомов осталось в проекте: {len(still)} {still}")

    if unassigned_nonNC:
        print(f"\n⚠ Помещения НЕ-NC, оставшиеся без приточки ({len(unassigned_nonNC)}) "
              f"— проверьте, нужно ли переназначить:")
        for nm, num, rt, sup in unassigned_nonNC:
            print(f"     {num:14} {rt:20} (было {sup:.0f} м³/ч)  из {nm!r}")


if __name__ == "__main__":
    main()
