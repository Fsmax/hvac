# -*- coding: utf-8 -*-
"""Чинит фасадное остекление, ошибочно помеченное внутренним.

Проблема: длинный фасад-витраж (Storefront / Balcony) в Revit — это ОДИН
элемент, граничащий сразу с несколькими отапливаемыми комнатами (bsc>=2).
Геометрическое правило data_loader («общий с отапл. помещением → перегородка»)
ошибочно метит такой фасад is_exterior=False, и он выпадает из расчёта
теплопотерь (U=0, нет construction_key).

Storefront/Balcony по определению — наружный фасад, не межкомнатная
перегородка. Скрипт переводит такие элементы в is_exterior=True; дальше
project.recalculate()->apply_constructions() сам проставит «Витраж» U=2.2,
SHGC=0.4 из каталога.

Запуск:
    C:\\Python314\\python.exe tools\\fix_facade_glazing.py            # dry-run
    C:\\Python314\\python.exe tools\\fix_facade_glazing.py --apply    # запись (с .bak)
"""
import sys, os, shutil, datetime, collections

sys.path.insert(0, r"D:\HVAC")
from hvac.project import HVACProject
from hvac import io_json
from hvac.catalogs.constructions import normalize_category, construction_key

PATH = r"D:\HVAC\ALL-BLOCKS.hvac.json"

# Ключевые слова ФАСАДНОГО (наружного) остекления — однозначно улица.
FACADE_KW = ("storefront", "витрин", "facade", "фасад",
             "balcony", "балкон", "loggia", "лоджия")
# Явно ВНУТРЕННИЕ — на всякий случай исключаем, даже если совпал фасадный kw.
INTERIOR_KW = ("interior", "partition", "перегород", "внутрен",
               "separator", "разделит", "empty",
               "shower", "душ", "кабин", "cabin", "core")


def is_curtain(el) -> bool:
    b = (el.family + " " + el.type_name).lower()
    return any(w in b for w in ("витраж", "curtain", "storefront", "glaz"))


def is_facade_glazing(el) -> bool:
    b = (el.family + " " + el.type_name).lower()
    if not is_curtain(el):
        return False
    if any(w in b for w in INTERIOR_KW):
        return False
    return any(w in b for w in FACADE_KW)


def main(apply: bool) -> None:
    proj = HVACProject()
    io_json.load_project(proj, PATH)
    sp_by_id = {s.space_id: s for s in proj.spaces}

    targets = [el for el in proj.elements
               if (not el.is_exterior) and is_facade_glazing(el)]

    if not targets:
        print("Нечего чинить: фасадных is_exterior=False не найдено.")
        return

    # --- отчёт ДО ---
    by_type = collections.defaultdict(lambda: [0, 0.0])
    by_level = collections.defaultdict(lambda: [0, 0.0])
    aff_space_ids = set()
    for el in targets:
        a = el.net_area_m2 or el.element_area_m2 or 0.0
        by_type[el.type_name][0] += 1
        by_type[el.type_name][1] += a
        lvl = sp_by_id.get(el.space_id).level if el.space_id in sp_by_id else "?"
        by_level[lvl][0] += 1
        by_level[lvl][1] += a
        aff_space_ids.add(el.space_id)

    print(f"Найдено фасадных элементов для перевода в наружные: {len(targets)}")
    print("\n=== по типу ===")
    for t, (n, a) in sorted(by_type.items(), key=lambda x: -x[1][1]):
        print(f"   {a:8.1f} м²  N={n:4}  {t}")
    print("\n=== по уровню ===")
    for lvl, (n, a) in sorted(by_level.items(), key=lambda x: -x[1][1]):
        print(f"   {a:8.1f} м²  N={n:4}  {lvl}")

    loss_before = sum((sp_by_id[s].heat_loss_w or 0.0)
                      for s in aff_space_ids if s in sp_by_id)
    gain_before = sum((sp_by_id[s].heat_gain_w or 0.0)
                      for s in aff_space_ids if s in sp_by_id)

    # --- применяем флаг ---
    for el in targets:
        el.is_exterior = True
        el.user_modified = True

    proj.recalculate()

    # проверка: какие construction_key/U проставились
    keys = collections.Counter((el.construction_key, el.u_value) for el in targets)
    print("\n=== проставленные конструкции (после apply_constructions) ===")
    for (k, u), n in keys.most_common():
        print(f"   N={n:4}  U={u}  key={k!r}")

    loss_after = sum((sp_by_id[s].heat_loss_w or 0.0)
                     for s in aff_space_ids if s in sp_by_id)
    gain_after = sum((sp_by_id[s].heat_gain_w or 0.0)
                     for s in aff_space_ids if s in sp_by_id)
    print(f"\n=== загрузки затронутых {len(aff_space_ids)} помещений ===")
    print(f"   Теплопотери:    {loss_before/1000:8.1f} → {loss_after/1000:8.1f} кВт "
          f"(Δ {(loss_after-loss_before)/1000:+.1f})")
    print(f"   Теплопоступл.:  {gain_before/1000:8.1f} → {gain_after/1000:8.1f} кВт "
          f"(Δ {(gain_after-gain_before)/1000:+.1f})")

    if not apply:
        print("\n[DRY-RUN] Файл НЕ изменён. Запусти с --apply для записи.")
        return

    ts = datetime.datetime.now().strftime("%Y%m%d%H%M%S")
    bak = f"{PATH}.bak-{ts}"
    shutil.copy2(PATH, bak)
    io_json.save_project(proj, PATH)
    print(f"\n[ЗАПИСАНО] backup: {bak}")
    print(f"[ЗАПИСАНО] обновлён: {PATH}")


if __name__ == "__main__":
    main(apply="--apply" in sys.argv)
