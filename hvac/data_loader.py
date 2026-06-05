# -*- coding: utf-8 -*-
"""Загрузка данных Revit (выгруженных Dynamo-скриптом) из CSV."""

from __future__ import annotations
import csv
from typing import Dict, List, Set
from hvac.models import Space, BoundaryElement
from hvac.parsers import parse_number, parse_area, azimuth_to_sector

# Категории, которые исключаются из расчёта теплопередачи
# (учитываются как мостики холода в самой стене)
EXCLUDED_CATEGORIES = {
    "<Разделитель помещений>",
    "<Разделители помещений>",
    "<Разделители пространств>",
    "<Разделитель пространств>",
    "<Room Separation Lines>",
    "<Room Separation>",
    "<Space Separation Lines>",
    "<Space Separation>",
    "Несущие колонны",
    "Колонны",
    "Structural Columns",
    "Columns",
}


def is_excluded_category(category: str) -> bool:
    """True если категория — служебная (разделитель помещений или колонна).

    Срабатывает как на точное совпадение, так и на эвристику: любая
    строка вида «<…разделит…>» / «…separation…» в категории/семействе
    относится к линиям-разделителям Revit и теплопередачи не несёт.
    """
    if not category:
        return False
    if category in EXCLUDED_CATEGORIES:
        return True
    low = category.lower()
    if low.startswith("<") and ("раздел" in low or "separation" in low):
        return True
    return False

# Префиксы номеров неотапливаемых пространств (балконы, террасы и т.п.)
# Стена, граничащая только с такими пространствами, считается наружной.
UNCONDITIONED_PREFIXES = ("OFC-", "BAL-", "TER-", "SHAFT")
UNCONDITIONED_KEYWORDS = ("балкон", "терраса", "лоджия", "balcony",
                          "terrace", "loggia", "shaft", "open air")

# Имена «мокрых»/служебных помещений, которые в плане здания почти
# никогда не выходят на фасад. Если в выгрузке у них появляется
# фасадный витраж с bsc>=2 (общий с гостиной/спальней) — это почти
# всегда артефакт Room Bounding в Revit (Space «протекает» сквозь
# перегородку до настоящего витража соседней комнаты). Такие витражи
# отсекаем, чтобы санузел не «грел улицу». Если у санузла bsc=1
# (эксклюзивный витраж) — оставляем, мало ли реально такое.
WET_ROOM_KEYWORDS = (
    "bathroom", "bath", "wc", "toilet", "shower", "lavatory",
    "powder room", "water closet",
    "санузел", "ванн", "душ", "уборн", "туалет",
)


def is_wet_space(name: str) -> bool:
    if not name:
        return False
    low = name.lower()
    return any(kw in low for kw in WET_ROOM_KEYWORDS)


def is_unconditioned_number(number: str, name: str = "") -> bool:
    """True если номер/имя пространства указывает на неотапливаемое
    помещение (балкон, терраса, шахта)."""
    if not (number or name):
        return False
    num_up = (number or "").upper()
    for pfx in UNCONDITIONED_PREFIXES:
        if num_up.startswith(pfx):
            return True
    full = ((number or "") + " " + (name or "")).lower()
    for kw in UNCONDITIONED_KEYWORDS:
        if kw in full:
            return True
    return False


def load_spaces(path: str) -> List[Space]:
    """Загружает список помещений из spaces.csv."""
    spaces: List[Space] = []
    with open(path, encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            sp = Space(
                space_id=row.get("id", "").strip(),
                number=row.get("number", "").strip(),
                name=row.get("name", "").strip(),
                level=row.get("level", "").strip(),
                area_m2=parse_area(row.get("area")),
                volume_m3=parse_area(row.get("volume")),
                height_m=parse_number(row.get("height")) or 0.0,
            )
            # Конвертация высоты из мм в м, если выгрузилось в мм
            if sp.height_m > 100:
                sp.height_m /= 1000.0
            elif sp.height_m == 0 and sp.area_m2 > 0 and sp.volume_m3 > 0:
                sp.height_m = sp.volume_m3 / sp.area_m2
            spaces.append(sp)
    return spaces


def load_thermal(path: str, spaces: List[Space] = None
                 ) -> List[BoundaryElement]:
    """Загружает границы помещений из thermal_all.csv.

    Если переданы `spaces`, то выполняется доп. проверка: для стен с
    bsc>=2 проверяется, не граничат ли они только с неотапливаемыми
    пространствами (балконы OFC-/BAL-/TER-). Такие стены помечаются
    как наружные — НО ТОЛЬКО если сам OFC- является «настоящим
    балконом» (т.е. имеет хотя бы одну стену с bsc=1, выходящую
    на улицу). OFC-* полностью окружённые отапливаемыми помещениями
    (внутренние ниши/шахты) НЕ запускают это правило.
    """
    # Множество space_id, которые мы считаем неотапливаемыми по имени.
    # definite_balcony_ids — заведомо балкон/терраса/шахта (по префиксу
    # BAL-/TER-/SHAFT или ключевому слову): такие пространства ВСЕГДА
    # считаются неотапливаемыми, даже если у них нет «эксклюзивной»
    # стены наружу (у типового балкона его единственная наружная сторона —
    # это витраж, общий со спальней).
    # ofc_ambiguous_ids — пространства с префиксом OFC-: имя само по себе
    # не доказывает, что это балкон (может быть и внутренним коридором),
    # поэтому проверяется отдельно через «эксклюзивную» стену.
    unconditioned_ids: Set[str] = set()
    definite_balcony_ids: Set[str] = set()
    ofc_ambiguous_ids: Set[str] = set()
    # Карта: space_id → имя помещения, для проверки на «мокрое»
    sid_to_name: Dict[str, str] = {}
    if spaces:
        for sp in spaces:
            sid_to_name[sp.space_id] = sp.name or ""
            if not is_unconditioned_number(sp.number, sp.name):
                continue
            unconditioned_ids.add(sp.space_id)
            num_up = (sp.number or "").upper()
            full_lower = ((sp.number or "") + " " + (sp.name or "")).lower()
            is_kw = any(kw in full_lower for kw in UNCONDITIONED_KEYWORDS)
            non_ofc_pfx = num_up.startswith(("BAL-", "TER-", "SHAFT"))
            if non_ofc_pfx or is_kw:
                definite_balcony_ids.add(sp.space_id)
            elif num_up.startswith("OFC-"):
                ofc_ambiguous_ids.add(sp.space_id)

    # Первый проход: считаем все строки с метаданными
    raw_rows = []
    with open(path, encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            cat = row.get("category", "").strip()
            if is_excluded_category(cat):
                continue
            raw_rows.append(row)

    # Карта: какие space_id содержат каждый element_id
    elem_space_map: Dict[str, Set[str]] = {}
    for row in raw_rows:
        eid = row.get("element_id", "").strip()
        sid = row.get("space_id", "").strip()
        if eid and sid:
            elem_space_map.setdefault(eid, set()).add(sid)

    # Подмножество ИСТИННЫХ балконов:
    # (а) заведомые балконы по префиксу/ключевым словам (BAL-/TER-/SHAFT/
    #     «балкон»/«terrace») — включаются СРАЗУ, потому что у типового
    #     балкона его единственная наружная сторона — это витраж, общий
    #     со спальней, и «эксклюзивных» стен у него вообще нет;
    # (б) пространства OFC-* — проверяем строго: только если у них есть
    #     хотя бы одна стена, эксклюзивная для них (elem_space_map = {O}).
    #     OFC- без таких стен — это внутренние ниши/коридоры/шахты, и
    #     стены к ним должны оставаться внутренними.
    truly_unconditioned_ids: Set[str] = set(definite_balcony_ids)
    if ofc_ambiguous_ids:
        rows_by_space: Dict[str, list] = {}
        for row in raw_rows:
            sid = row.get("space_id", "").strip()
            rows_by_space.setdefault(sid, []).append(row)
        for sid in ofc_ambiguous_ids:
            has_facade = False
            for r in rows_by_space.get(sid, []):
                row_type_r = r.get("row_type", "").strip()
                if row_type_r not in ("external_wall", "opening"):
                    continue
                eid_r = r.get("element_id", "").strip()
                if not eid_r:
                    continue
                # «Эксклюзивная» стена — кроме OFC её никто не знает.
                neighbors = elem_space_map.get(eid_r, set()) - {sid}
                if len(neighbors) == 0:
                    has_facade = True
                    break
            if has_facade:
                truly_unconditioned_ids.add(sid)

    def conditioned_neighbors(elem_id: str, current_space_id: str) -> int:
        """Сколько ОТАПЛИВАЕМЫХ соседних пространств кроме текущего
        содержат данный элемент. Здесь «неотапливаемые» = только истинные
        балконы (truly_unconditioned_ids), а не любые OFC-*."""
        all_spaces = elem_space_map.get(elem_id, set())
        others = all_spaces - {current_space_id}
        return sum(1 for s in others if s not in truly_unconditioned_ids)

    elems: List[BoundaryElement] = []
    for row in raw_rows:
        cat = row.get("category", "").strip()
        try:
            bsc = int(parse_number(row.get("boundary_space_count")) or 1)
        except Exception:
            bsc = 1
        orient_deg = parse_number(row.get("orientation_deg"))
        row_type = row.get("row_type", "").strip()
        eid = row.get("element_id", "").strip()
        sid = row.get("space_id", "").strip()

        # Эффективный bsc: если CSV говорит 1, но elem_space_map знает
        # больше соседей — берём реальное число. Это страхует от старых
        # CSV, где Dynamo занижал bsc для стен к OFC-* (балконам), и от
        # ошибок в подсчёте.
        bsc_effective = bsc
        if eid and eid in elem_space_map:
            bsc_effective = max(bsc, len(elem_space_map[eid]))

        # Признак «наружной» — комбинируем три источника:
        # 1) Категория/семейство Витраж (Curtain Wall) — всегда фасад.
        #    Может стоять между ЛИВИНГ + СПАЛЬНЯ одного гост. номера
        #    (bsc=2), и всё равно это наружное остекление, не «внутренняя
        #    стена между двумя комнатами».
        # 2) Функция конструкции = «Наружные»/«Exterior», или проём
        #    «hosted by exterior wall» — стена/окно по сути наружное.
        # 3) Иначе — геометрия elem_space_map: если этот же element_id
        #    встречается у >=2 пространств, и среди них есть отапливаемое
        #    помещение кроме текущего → стена внутренняя. Это спасает
        #    санузел от ложно-наружных стен в коридор-OFC.
        flag_yes = row.get("is_exterior_wall", "").strip().lower() == "yes"
        fam_lower = row.get("family", "").strip().lower()
        func_lower = row.get("function", "").strip().lower()
        is_curtain = "витраж" in fam_lower or "curtain" in fam_lower
        # ВНИМАНИЕ: is_exterior_function — это сигнал ТИПА конструкции
        # (из какого материала собрана стена), а НЕ геометрический факт
        # того, что эта конкретная стена реально граничит с улицей.
        # В русском Revit поле `function` часто выгружается как
        # "Наружные слои" / "Внутренние слои" — это название слоёв в
        # типе стены. Одна и та же стена типа "Наружные слои" может
        # стоять и на фасаде (bsc=1), и как межкомнатная перегородка
        # (bsc>=2 — если архитектор сэкономил типы). Поэтому ниже эта
        # переменная используется ТОЛЬКО как fallback, когда eid пустой
        # и геометрический анализ невозможен.
        is_exterior_function = (
            "exterior" in func_lower
            or "наруж" in func_lower
            or "hosted by exterior wall" in func_lower
        )
        # Защита от артефактов Room Bounding: если витраж разделён между
        # >=2 помещениями и текущее — «мокрое» (санузел/ванная/WC), это
        # почти гарантированно ошибка модели Revit (Space санузла «дотянулся»
        # до фасада через перегородку без Room Bounding). Санузел в этом
        # случае витраж как наружный НЕ получает. Если у санузла bsc=1
        # (эксклюзивный витраж), правило не срабатывает — оставляем как есть.
        sp_name = sid_to_name.get(sid, "")
        wet_curtain_artifact = (is_curtain
                                and bsc_effective >= 2
                                and is_wet_space(sp_name))

        # Приоритет признаков «наружной»:
        #   1) row_type должен быть external_wall / opening — иначе нет.
        #   2) wet_curtain_artifact → внутренняя (артефакт Revit).
        #   3) ГЕОМЕТРИЯ (bsc + соседи): если стена общая с другим
        #      ОТАПЛИВАЕМЫМ пространством, это внутренняя перегородка —
        #      независимо от того, что написано в function/family.
        #      Это главное правило: «помещение, окружённое другим
        #      помещением, не теряет тепло наружу».
        #   4) Витраж между двумя комнатами одного гост. номера — особый
        #      случай: стекло физически смотрит на улицу, оставляем
        #      наружным.
        #   5) Если eid пустой (нет геометрических данных) — fallback на
        #      сигналы Dynamo + типа конструкции.
        is_exterior_flag = False
        if row_type in ("external_wall", "opening"):
            if wet_curtain_artifact:
                # Артефакт Room Bounding — игнорируем витраж у санузла.
                is_exterior_flag = False
            elif not eid:
                # Нет id элемента — пересчитать геометрию не можем.
                # Доверяем Dynamo + сигналам типа конструкции.
                is_exterior_flag = (flag_yes or is_curtain
                                    or is_exterior_function)
            elif bsc_effective <= 1:
                # Геометрия: элемент касается лишь ОДНОГО помещения → кандидат
                # в «наружные». Но часто это перегородка, выходящая в шахту,
                # нишу или коридор без Room Bounding (другая сторона — не Space,
                # поэтому bsc=1). Без переопределения такие стены массово
                # становятся «наружными» (типичная ошибка выгрузки из Revit).
                # Переопределяем на ВНУТРЕННЮЮ при явном сигнале, что это не
                # фасад:
                #   - Dynamo пометил is_exterior_wall=no (flag_yes=False), ИЛИ
                #   - тип стены внутренний (function = «Внутренние слои»).
                # Витраж — исключение: его панели (bsc=1) реально смотрят на
                # улицу, поэтому остаются наружными.
                interior_type = "внутренн" in func_lower
                if not is_curtain and (not flag_yes or interior_type):
                    is_exterior_flag = False
                else:
                    is_exterior_flag = True
            elif spaces and sid:
                # bsc>=2: элемент общий с другим пространством.
                if conditioned_neighbors(eid, sid) == 0:
                    # Все остальные соседи — балконы/шахты (неотапливаемые) →
                    # стена граничит с «улицей», наружная.
                    is_exterior_flag = True
                elif is_curtain:
                    # ВИТРАЖ, общий с отапливаемым помещением. Различить
                    # «фасадное остекление, проходящее через две комнаты»
                    # (напр. HTL-602.a/602.b — реальный фасад) и «стеклянную
                    # перегородку между комнатами номера» (HTL-223.a/223.c)
                    # по выгрузке Revit НЕВОЗМОЖНО: оба варианта дают
                    # family=Витраж, function=Наружные слои, is_exterior_wall=yes,
                    # bsc=2, и витраж совпадает по ориентации с общей сплошной
                    # стеной. Считаем НАРУЖНЫМ (консервативно для отопления —
                    # лучше пере-, чем недосчитать). Реальные перегородки
                    # пользователь помечает внутренними вручную (панель
                    # «Ограждения» / «Ограждения проекта…»).
                    is_exterior_flag = True
                else:
                    # Обычная стена между отапливаемыми помещениями → внутренняя,
                    # даже если function="Наружные слои".
                    is_exterior_flag = False
            else:
                # Список spaces не передан — соседей проверить нельзя.
                # Доверяем флагу Dynamo, но не «улучшаем» его наверх.
                is_exterior_flag = flag_yes

        # Если текущее пространство само неотапливаемое — оно вообще
        # не должно учитываться в расчёте теплопотерь/теплопоступлений,
        # но мы оставляем элемент в списке (UI его покажет с пометкой).
        elem = BoundaryElement(
            space_id=sid,
            row_type=row_type,
            is_exterior=is_exterior_flag,
            element_id=eid,
            category=cat,
            family=row.get("family", "").strip(),
            type_name=row.get("type", "").strip(),
            boundary_length_m=parse_area(row.get("boundary_length_m")),
            space_height_m=parse_area(row.get("space_height_m")),
            approx_area_m2=parse_area(row.get("approx_area_m2")),
            element_area_m2=parse_area(row.get("element_area")),
            thickness_mm=parse_area(row.get("thickness")),
            function=row.get("function", "").strip(),
            host_element_id=row.get("host_element_id", "").strip(),
            boundary_space_count=bsc,
            orientation_deg=orient_deg,
            orientation=azimuth_to_sector(orient_deg),
        )
        elems.append(elem)
    return elems
