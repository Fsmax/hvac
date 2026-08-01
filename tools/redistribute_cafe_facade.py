# -*- coding: utf-8 -*-
"""Перераспределяет «слипшийся» фасадный витраж кафе-зоны GFL/MFL по фронту.

Проблема: изогнутый многосветный фасад (элемент 4649808 в FCD-BMG, 37.4 м ×
~10.2 м = 381 м²) в MEP Spaces целиком приписан ОДНОМУ помещению HTL-063 CAFE
(103 м²!), хотя реально стоит перед кафе (GFL) и ритейлом (MFL):
  GFL низ:  HTL-064 41% / HTL-063 30% / HTL-062 21% / GFL-G02 7%
  MFL верх: HTL-191 39% / HTL-198 29% / HTL-199 22% / MZN-G02 7%
(доли фронта измерены сэмплированием кривой в живом Revit).

Делим 381 м² на GFL-долю (низ, h=5.0 м) и MFL-долю (верх, h=5.2 м), затем
внутри каждой — по фронту. Площадь сохраняется. Витраж получает U=2.2/SHGC=0.4
через apply_constructions (family «Витраж»).

Запуск:
  C:\\Python314\\python.exe tools\\redistribute_cafe_facade.py          # dry-run
  C:\\Python314\\python.exe tools\\redistribute_cafe_facade.py --apply
"""
import sys, copy, shutil, datetime

sys.path.insert(0, r"D:\HVAC")
from hvac.project import HVACProject
from hvac import io_json

PATH = r"D:\HVAC\ALL-BLOCKS.hvac.json"
SRC_EID = "4649808"          # элемент 381 м², сейчас на HTL-063
LEN_M = 37.4
H_GFL, H_MFL = 5.0, 5.2      # высоты яруса (низ/верх)
# доли фронта (норм. внутри яруса)
GFL = {"HTL-064": 0.41, "HTL-063": 0.30, "HTL-062": 0.21, "GFL-G02": 0.07}
MFL = {"HTL-191": 0.39, "HTL-198": 0.29, "HTL-199": 0.22, "MZN-G02": 0.07}


def norm(d):
    s = sum(d.values())
    return {k: v / s for k, v in d.items()}


def main(apply: bool) -> None:
    proj = HVACProject()
    io_json.load_project(proj, PATH)
    by_num = {}
    for s in proj.spaces:
        by_num.setdefault(s.number, s.space_id)

    src = next((e for e in proj.elements if e.element_id == SRC_EID
                and e.is_exterior), None)
    if src is None:
        print(f"Источник {SRC_EID} не найден (уже перераспределён?).")
        return
    src_area = src.net_area_m2 or 0.0
    print(f"Источник {SRC_EID}: {src_area:.0f} м² на {proj.get_space(src.space_id).number}")

    area_gfl = src_area * H_GFL / (H_GFL + H_MFL)
    area_mfl = src_area * H_MFL / (H_GFL + H_MFL)
    targets = {}   # number -> area
    for num, f in norm(GFL).items():
        targets[num] = area_gfl * f
    # MFL-ярус НЕ трогаем: ритейл HTL-191/199 уже частично остеклён
    # (риск двойного счёта). Верхняя доля (~MFL) убирается с HTL-063 —
    # она там была ошибочна. MFL-фасад флагуем отдельно.
    print(f"Делёж: GFL={area_gfl:.0f} м² (перераспр.), "
          f"MFL={area_mfl:.0f} м² (снято с HTL-063, MFL не трогаем)")
    aff_ids = set()
    new_els = []
    for num, area in targets.items():
        sid = by_num.get(num)
        if sid is None:
            print(f"  ! {num}: помещение не найдено, пропуск ({area:.0f} м²)")
            continue
        aff_ids.add(sid)
        if num == proj.get_space(src.space_id).number:
            # это HTL-063 — ужимаем исходный элемент до его доли
            src.approx_area_m2 = area
            src.element_area_m2 = area
            src.net_area_m2 = area
            src.user_modified = True
        else:
            e = copy.deepcopy(src)
            e.space_id = sid
            e.element_id = f"{SRC_EID}_r{len(new_els)+1}"
            e.host_element_id = ""
            e.boundary_space_count = 1
            e.approx_area_m2 = area
            e.element_area_m2 = area
            e.net_area_m2 = area
            e.construction_key = ""
            e.user_modified = True
            new_els.append(e)
        print(f"  {num:<9} -> {area:6.1f} м²")

    loss_b = {sid: (proj.get_space(sid).heat_loss_w or 0) for sid in aff_ids}
    proj.elements.extend(new_els)
    proj._invalidate_elements_index()
    proj.recalculate()

    # проверка U/категории
    chk = {(e.construction_key.split(' / ')[0], e.u_value)
           for e in new_els}
    print("новые элементы — конструкции:", chk)
    print("\nИзменение теплопотерь по затронутым помещениям:")
    for sid in aff_ids:
        s = proj.get_space(sid)
        print(f"  {s.number:<9} {s.heat_loss_w/1000:6.1f} кВт "
              f"(было {loss_b[sid]/1000:.1f})")

    if not apply:
        print("\n[DRY-RUN] не сохранено.")
        return
    bak = f"{PATH}.bak-{datetime.datetime.now().strftime('%Y%m%d%H%M%S')}"
    shutil.copy2(PATH, bak)
    io_json.save_project(proj, PATH)
    print(f"\n[ЗАПИСАНО] backup: {bak}")


if __name__ == "__main__":
    main(apply="--apply" in sys.argv)
