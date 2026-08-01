# -*- coding: utf-8 -*-
"""Чинит фасад офисной башни OFF, ошибочно помеченный внутренним.

Причина (подтверждено по живому Revit): навесной фасад офисов — сплошной
curtain-wall, идущий ВЕРТИКАЛЬНО через этажи. Один и тот же элемент граничит
с одним офисом на этаже N и тем же офисом на этаже N+1 (OFC-328 ↔ OFC-228 =
OFFICE T1 на 3 и 2 этаже). Правило data_loader «общий с 2 отапл. помещениями
= перегородка» из-за этого пометило весь фасад is_exterior=False, U=0 → фасад
выпал из теплопотерь.

Офисный фасад УЖЕ разнесён на отдельные элементы:
  - остекление  GLZ-O0x          (family «Витраж») → «Витраж» U=2.2, SHGC=0.4
  - спандрел    CHR-MZN-Wall_Aluminium + Drywall (family «Базовая стена»)
                                  → «Стены» U=0.45 (есть в каталоге), SHGC=0
поэтому достаточно перевести их в is_exterior=True; apply_constructions сам
проставит правильные U/SHGC. Глухие блочные стены (CHR-ARC-WA-BL*) НЕ трогаем
(неоднозначны: периметр или перегородка — нужна отдельная проверка).

Запуск:
    C:\\Python314\\python.exe tools\\fix_office_facade.py           # dry-run
    C:\\Python314\\python.exe tools\\fix_office_facade.py --apply   # запись (с .bak)
"""
import sys, shutil, datetime, collections

sys.path.insert(0, r"D:\HVAC")
from hvac.project import HVACProject
from hvac import io_json

PATH = r"D:\HVAC\ALL-BLOCKS.hvac.json"


def is_office_facade(el) -> bool:
    """Фасадный элемент офисной навесной стены: витраж GLZ или алюм-спандрел."""
    t = (el.type_name or "").lower()
    return t.startswith("glz") or "aluminium" in t or "aluminum" in t


def main(apply: bool) -> None:
    proj = HVACProject()
    io_json.load_project(proj, PATH)
    sp_by_id = {s.space_id: s for s in proj.spaces}

    targets = []
    for el in proj.elements:
        if el.is_exterior:
            continue
        s = sp_by_id.get(el.space_id)
        if s is None or "OFF" not in (s.level or ""):
            continue
        if is_office_facade(el):
            targets.append(el)

    if not targets:
        print("Нечего чинить: фасадных OFF is_exterior=False не найдено.")
        return

    aff = {el.space_id for el in targets}
    loss_b = sum((sp_by_id[s].heat_loss_w or 0.0) for s in aff)
    gain_b = sum((sp_by_id[s].heat_gain_w or 0.0) for s in aff)

    by_type = collections.defaultdict(lambda: [0, 0.0])
    by_level = collections.defaultdict(lambda: [0, 0.0])
    for el in targets:
        a = el.net_area_m2 or 0.0
        by_type[el.type_name][0] += 1
        by_type[el.type_name][1] += a
        lvl = sp_by_id[el.space_id].level
        by_level[lvl][0] += 1
        by_level[lvl][1] += a

    print(f"Фасадных элементов OFF к переводу в наружные: {len(targets)}")
    print("\n=== по типу ===")
    for t, (n, a) in sorted(by_type.items(), key=lambda x: -x[1][1]):
        print(f"   {a:7.0f} м²  N={n:4}  {t}")
    print("\n=== по уровню ===")
    for lvl, (n, a) in sorted(by_level.items()):
        print(f"   {a:7.0f} м²  N={n:4}  {lvl}")

    for el in targets:
        el.is_exterior = True
        el.user_modified = True
    proj.recalculate()

    cls = collections.Counter(
        (el.construction_key.split(" / ")[0], el.u_value) for el in targets)
    print("\n=== проставленные конструкции ===")
    for (cat, u), n in cls.most_common():
        print(f"   N={n:4}  {cat:8}  U={u}")

    loss_a = sum((sp_by_id[s].heat_loss_w or 0.0) for s in aff)
    gain_a = sum((sp_by_id[s].heat_gain_w or 0.0) for s in aff)
    print(f"\nЗатронуто помещений: {len(aff)}")
    print(f"  Теплопотери:   {loss_b/1000:8.1f} → {loss_a/1000:8.1f} кВт "
          f"(Δ {(loss_a-loss_b)/1000:+.1f})")
    print(f"  Теплопоступл.: {gain_b/1000:8.1f} → {gain_a/1000:8.1f} кВт "
          f"(Δ {(gain_a-gain_b)/1000:+.1f})")

    if not apply:
        print("\n[DRY-RUN] Файл НЕ изменён. Запусти с --apply для записи.")
        return
    ts = datetime.datetime.now().strftime("%Y%m%d%H%M%S")
    bak = f"{PATH}.bak-{ts}"
    shutil.copy2(PATH, bak)
    io_json.save_project(proj, PATH)
    print(f"\n[ЗАПИСАНО] backup: {bak}\n[ЗАПИСАНО] обновлён: {PATH}")


if __name__ == "__main__":
    main(apply="--apply" in sys.argv)
