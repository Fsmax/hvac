# -*- coding: utf-8 -*-
"""Делит фасад-витраж CHR_Storefront на стекло + глухой спандрел.

Зачем: ARC-плейсхолдер `CHR_Storefront` моделирует ВСЮ плоскость фасада как
стекло (U=2.2, SHGC=0.4). По сверке с фасадной моделью FCD-BMG реальная доля
прозрачного стекла: GFL ≈ 81%, MFL ≈ 66% (остальное — спандрел/алюминий).
Учёт всей плоскости стеклом завышает теплопотери и теплопоступления.

Что делает: для каждого НАРУЖНОГО элемента CHR_Storefront* на GFL/MFL
  - оставляет стеклянную долю (gf) как «Витраж» (U=2.2, SHGC=0.4),
    уменьшая его GROSS-площадь до gf (net пересчитается из gross);
  - создаёт парный НЕПРОЗРАЧНЫЙ элемент-спандрел на долю (1-gf):
    category «Стены», U=SPANDREL_U, SHGC=0.
Площадь сохраняется (gf + (1-gf) = 1). CHR_Balcony НЕ трогаем (полное стекло).

Идемпотентность: повторный запуск пропускает уже разделённые (по наличию
парного спандрел-элемента с тем же element_id) — см. _already_split.

Запуск:
    C:\\Python314\\python.exe tools\\split_storefront_spandrel.py          # dry-run
    C:\\Python314\\python.exe tools\\split_storefront_spandrel.py --apply  # запись (с .bak)
"""
import sys, copy, shutil, datetime, collections

sys.path.insert(0, r"D:\HVAC")
from hvac.project import HVACProject
from hvac import io_json

PATH = r"D:\HVAC\ALL-BLOCKS.hvac.json"

GLASS_FRACTION = {"GFL": 0.81, "MFL": 0.66}   # измерено по FCD-BMG
SPANDREL_U = 0.6                               # непрозрачный спандрел, Вт/м²·К
SPANDREL_FAMILY = "Спандрель"
SPANDREL_TYPE = "Спандрель глухой непрозрачный"   # БЕЗ curtain-keywords → категория «Стены»
SPD_SUFFIX = "_spd"


def band_of(level: str):
    if level.startswith("GFL"):
        return "GFL"
    if level.startswith("MFL"):
        return "MFL"
    return None


def is_storefront(el) -> bool:
    return (el.is_exterior
            and "storefront" in (el.type_name or "").lower())


def main(apply: bool) -> None:
    proj = HVACProject()
    io_json.load_project(proj, PATH)
    sp_by_id = {s.space_id: s for s in proj.spaces}

    existing_spd = {e.element_id for e in proj.elements
                    if e.element_id.endswith(SPD_SUFFIX)}

    targets = []
    for el in proj.elements:
        if not is_storefront(el):
            continue
        b = band_of(sp_by_id.get(el.space_id).level
                    if el.space_id in sp_by_id else "")
        if b is None:
            continue
        if (el.element_id + SPD_SUFFIX) in existing_spd:
            continue  # уже разделён
        targets.append((el, b))

    if not targets:
        print("Нечего делить (всё уже разделено или нет storefront на GFL/MFL).")
        return

    aff_space_ids = {el.space_id for el, _ in targets}
    loss_before = sum((sp_by_id[s].heat_loss_w or 0.0) for s in aff_space_ids)
    gain_before = sum((sp_by_id[s].heat_gain_w or 0.0) for s in aff_space_ids)

    new_spandrels = []
    rep = collections.defaultdict(lambda: [0, 0.0, 0.0])  # band -> n, glass, spd
    for el, b in targets:
        gf = GLASS_FRACTION[b]
        gross = max(el.approx_area_m2 or 0.0, el.element_area_m2 or 0.0)
        # спандрел-копия на долю (1-gf)
        spd = copy.deepcopy(el)
        spd.element_id = el.element_id + SPD_SUFFIX
        spd.category = "Стены"
        spd.family = SPANDREL_FAMILY
        spd.type_name = SPANDREL_TYPE
        spd.host_element_id = ""        # проёмы не вычитаем из спандрела
        spd.construction_key = ""       # проставит apply_constructions
        spd.approx_area_m2 = (el.approx_area_m2 or 0.0) * (1 - gf)
        spd.element_area_m2 = (el.element_area_m2 or 0.0) * (1 - gf)
        spd.net_area_m2 = gross * (1 - gf)
        spd.user_modified = True
        new_spandrels.append(spd)
        # стеклянную часть ужимаем до gf (gross → net пересчитается)
        el.approx_area_m2 = (el.approx_area_m2 or 0.0) * gf
        el.element_area_m2 = (el.element_area_m2 or 0.0) * gf
        el.user_modified = True
        rep[b][0] += 1
        rep[b][1] += gross * gf
        rep[b][2] += gross * (1 - gf)

    proj.elements.extend(new_spandrels)
    proj._invalidate_elements_index()

    # гарантируем конструкцию спандрела с нужным U (иначе apply создаст с дефолтом)
    from hvac.models import Construction
    from hvac.catalogs.constructions import construction_key
    spd_key = construction_key("Стены", SPANDREL_FAMILY, SPANDREL_TYPE, 0.0)
    if spd_key not in proj.constructions:
        proj.constructions[spd_key] = Construction(
            key=spd_key, category="Стены", family=SPANDREL_FAMILY,
            type_name=SPANDREL_TYPE, thickness_mm=0.0,
            u_value=SPANDREL_U, shgc=0.0,
            note="Глухой спандрел навесного фасада (стекло-спандрел/алюминий)")
    else:
        proj.constructions[spd_key].u_value = SPANDREL_U
        proj.constructions[spd_key].shgc = 0.0

    proj.recalculate()

    # фактические NET-площади после пересчёта (их и считает движок)
    glass_els = [el for el, _ in targets]
    net = collections.defaultdict(lambda: [0.0, 0.0])  # band -> glass_net, spd_net
    for el, b in targets:
        net[b][0] += el.net_area_m2 or 0.0
    for spd in new_spandrels:
        b = band_of(sp_by_id.get(spd.space_id).level
                    if spd.space_id in sp_by_id else "")
        if b:
            net[b][1] += spd.net_area_m2 or 0.0

    print(f"Разделено элементов CHR_Storefront: {len(targets)}")
    print(f"{'полоса':<6}{'N':>5}{'стекло м²':>12}{'спандрел м²':>13}{'%стекла':>9}{'сумма м²':>11}")
    for b in ("GFL", "MFL"):
        if b in net:
            g, s = net[b]
            print(f"{b:<6}{rep[b][0]:>5}{g:>12.0f}{s:>13.0f}"
                  f"{100*g/(g+s) if g+s else 0:>8.0f}%{g+s:>11.0f}")

    # проверка проставленной конструкции спандрела (должна быть «Стены», U=0.6, shgc=0)
    spd_u = {(e.construction_key, e.u_value) for e in new_spandrels}
    print("спандрел-конструкции:", spd_u)

    loss_after = sum((sp_by_id[s].heat_loss_w or 0.0) for s in aff_space_ids)
    gain_after = sum((sp_by_id[s].heat_gain_w or 0.0) for s in aff_space_ids)
    print(f"\nЗатронуто помещений: {len(aff_space_ids)}")
    print(f"  Теплопотери:   {loss_before/1000:8.1f} → {loss_after/1000:8.1f} кВт "
          f"(Δ {(loss_after-loss_before)/1000:+.1f})")
    print(f"  Теплопоступл.: {gain_before/1000:8.1f} → {gain_after/1000:8.1f} кВт "
          f"(Δ {(gain_after-gain_before)/1000:+.1f})")

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
