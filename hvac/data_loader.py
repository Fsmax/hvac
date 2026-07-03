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

# Наружных стен тоньше 100 мм не бывает: всё, что тоньше, — каркасные
# перегородки (санузлы, обшивки шахт, экраны). Такие стены часто граничат
# с шахтой/нишей без Space (bsc=1) и без правила массово становились
# ложно-наружными. Нижняя граница 5 мм страхует от CSV, где толщина
# случайно выгружена в метрах.
MIN_EXTERIOR_WALL_THICKNESS_MM = 100.0
_MIN_PLAUSIBLE_THICKNESS_MM = 5.0


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
                # under_roof=1 из revit_link.tag_roof_spaces (геом. детект:
                # над помещением нет отапл. пространства). Заменяет ломкий
                # _auto_detect_floors_roofs по уровням.
                has_roof=(row.get("under_roof", "") or "").strip() == "1",
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
    # Карта: space_id → уровень, для отсечения вертикальных соседей
    # (фасад навесной стены делит этажи, это не межкомнатная перегородка)
    sid_to_level: Dict[str, str] = {}
    if spaces:
        for sp in spaces:
            sid_to_name[sp.space_id] = sp.name or ""
            sid_to_level[sp.space_id] = sp.level or ""
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

    # Толщина стен по element_id, мм — проёмы наследуют толщину
    # стены-хозяина (у самих проёмов колонка thickness пустая).
    wall_thickness_mm: Dict[str, float] = {}
    for row in raw_rows:
        if row.get("row_type", "").strip() != "external_wall":
            continue
        eid = row.get("element_id", "").strip()
        thk = parse_area(row.get("thickness")) or 0.0
        if eid and thk > 0:
            wall_thickness_mm[eid] = thk

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

    def same_level_conditioned_neighbors(elem_id: str,
                                         current_space_id: str) -> int:
        """Сколько ОТАПЛИВАЕМЫХ соседей на ТОМ ЖЕ уровне делят элемент.
        Межкомнатная перегородка имеет соседа на своём этаже; навесной
        фасад, идущий вертикально через этажи, — нет (его делят одинаковые
        помещения на соседних этажах). Если карта уровней пуста (нет spaces)
        — возвращаем общий счётчик, чтобы не ослаблять старое правило."""
        if not sid_to_level:
            return conditioned_neighbors(elem_id, current_space_id)
        cur = sid_to_level.get(current_space_id, "")
        all_spaces = elem_space_map.get(elem_id, set())
        return sum(1 for s in all_spaces - {current_space_id}
                   if s not in truly_unconditioned_ids
                   and sid_to_level.get(s, "") == cur)

    elems: List[BoundaryElement] = []
    for row in raw_rows:
        cat = row.get("category", "").strip()
        try:
            bsc = int(parse_number(row.get("boundary_space_count")) or 1)
        except Exception:
            bsc = 1
        orient_deg = parse_number(row.get("orientation_deg"))
        # room_boundary_count — авторитетный двусторонний счётчик отапл.
        # комнат у стены (из ARC-линков, Dynamo). None для старых CSV.
        rbc = None
        _rbc_raw = row.get("room_boundary_count")
        if _rbc_raw is not None and str(_rbc_raw).strip() != "":
            try:
                rbc = int(parse_number(_rbc_raw) or 0)
            except Exception:
                rbc = None
        row_type = row.get("row_type", "").strip()
        eid = row.get("element_id", "").strip()
        sid = row.get("space_id", "").strip()
        # Геометрический вердикт внешней стороны (revit_link.export_wall_
        # verdicts): "int" — за стеной отапл. помещение/коридор-ARC →
        # внутренняя. Колонки может не быть в старых CSV → "".
        geom_ext = (row.get("geom_exterior") or "").strip()

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
        type_lower = row.get("type", "").strip().lower()
        func_lower = row.get("function", "").strip().lower()
        is_curtain = "витраж" in fam_lower or "curtain" in fam_lower
        # Окно (категория «Окна»/«Windows») — это всегда фасадное остекление.
        # В модели Chorsu окна сидят в тонкой фасадной панели CHR-FCD (~40 мм) и
        # выгружаются Dynamo с is_exterior_wall=no, из-за чего правило
        # thin_partition и ветка bsc<=1 ошибочно переводили их во внутренние
        # (см. ниже). Межкомнатных «окон» в проекте нет — все семейства
        # (CHR-WND-*/CWW) фасадные, поэтому окно всегда наружное.
        is_window = cat in ("Окна", "Windows") or cat.lower() == "windows"
        # Витраж, тип которого ЯВНО внутренний/не-фасадный (по имени типа из
        # Revit): стеклянная перегородка (Interior Partition), разделитель
        # (Separator) или пустой curtain wall. Такой витраж НЕ считается
        # фасадным остеклением — он внутренний, даже если общий с отапл.
        # помещением. Фасад/балкон (Exterior Glazing, Balcony, Storefront)
        # под это правило НЕ попадает и остаётся наружным.
        _glz = fam_lower + " " + type_lower
        # «shower»/«душ»/«кабин» — стеклянные душевые кабины: моделируются
        # витражом ВНУТРИ санузла, обе стороны в одном помещении (bsc=1),
        # поэтому без правила по имени неотличимы от фасадной панели.
        # «core» — остекление ядра здания (Core Curtain Wall): перегородки
        # лифтовых холлов/пожарных зон, не фасад.
        interior_glazing = is_curtain and any(
            kw in _glz for kw in (
                "interior", "partition", "перегород", "внутрен",
                "separator", "разделит", "empty",
                "shower", "душ", "кабин", "cabin", "core",
            ))
        # Витраж с ЯВНО фасадным типом (Storefront / Balcony / фасадное
        # остекление). Длинный фасад в Revit — это ОДИН элемент, граничащий
        # сразу с несколькими отапл. комнатами (bsc>=2..6), из-за чего
        # геометрическое правило «общий с отапл. помещением → перегородка»
        # (ветка bsc>=2 ниже) ошибочно метило его внутренним и он выпадал
        # из теплопотерь. Storefront/Balcony по определению — улица, не
        # межкомнатная перегородка, поэтому форсим наружный, перекрывая
        # геометрию. interior_glazing проверяется РАНЬШЕ, так что стеклянная
        # перегородка/душевая/ядро под это правило не попадут.
        facade_glazing = is_curtain and any(
            kw in _glz for kw in (
                "storefront", "витрин", "facade", "фасад",
                "balcony", "балкон", "loggia", "лоджия",
            ))
        # Непрозрачный спандрел навесного фасада (алюминий/гипс между
        # стёклами). Семейство «Базовая стена» (is_curtain=False), но это
        # фасад: делит этажи вертикально так же, как витраж. По имени типа
        # из проекта Chorsu: «CHR-MZN-Wall_Aluminium + Drywall» и т.п.
        facade_spandrel = (not interior_glazing) and any(
            kw in _glz for kw in ("alumin", "spandrel", "спандрел"))
        # Orphan-витраж из экспорта (function="curtain (orphan)"): фасадная
        # панель, добавленная отдельным проходом (не попала в
        # GetBoundarySegments) и УЖЕ поделённая по фронту между залами этажа.
        # Это всегда наружный фасад → наружный независимо от bsc/соседей
        # (после деления он общий с залами того же этажа, и геометрическое
        # правило bsc>=2 иначе ошибочно пометило бы его внутренним).
        is_orphan_facade = is_curtain and "orphan" in func_lower
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

        # Толщина стены (проём наследует от стены-хозяина): тоньше 100 мм —
        # каркасная перегородка, фасадом быть не может. Перекрывает
        # bsc/rbc/function: другая сторона часто шахта или ниша без Space
        # (bsc=1, rbc=1), из-за чего внутренние санузлы получали «фасад».
        thk_mm = parse_area(row.get("thickness")) or 0.0
        if row_type == "opening" and thk_mm <= 0:
            thk_mm = wall_thickness_mm.get(
                row.get("host_element_id", "").strip(), 0.0)
        thin_partition = (not is_curtain
                          and _MIN_PLAUSIBLE_THICKNESS_MM <= thk_mm
                          < MIN_EXTERIOR_WALL_THICKNESS_MM)

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
            if geom_ext == "int" and row_type == "external_wall" \
                    and not is_curtain:
                # Геометрия: внешняя сторона глухой стены упирается в отапл.
                # помещение/коридор-ARC → ВНУТРЕННЯЯ. Высший приоритет: ловит
                # толстые стены ядра/лестниц/коридоров, типизированные как
                # «Наружные», которые bsc/функция/rbc пропускают (другой face —
                # иной element_id). Витража и проёмов не касается.
                is_exterior_flag = False
            elif (row_type == "external_wall" and flag_yes
                  and (row.get("space_number", "") or "").strip()
                  .upper().startswith("RES")
                  and "living" in (row.get("space_name", "") or "").lower()):
                # RES-квартиры Chorsu выходят на ОТКРЫТЫЙ балкон: стена/панель,
                # помеченная экспортом наружной (is_exterior_wall=yes → bc<2 =
                # балкон/улица), остаётся НАРУЖНОЙ. Иначе func «Внутренние слои»
                # (STR-бетон 200) и thin_partition (панели PA01 10 мм) ошибочно
                # переводят её внутрь, и у жилой комнаты остаётся 0 наружной
                # оболочки → зимняя Q = −17·S·1.10 (одна бытовая, физ. неверно).
                # geom_ext=="int" (выше) сохраняет приоритет: если внешняя
                # сторона реально упирается в тёплую комнату — остаётся внутр.
                is_exterior_flag = True
            elif is_window:
                # Фасадное остекление — наружное всегда, независимо от толщины
                # стены-хозяина и флага Dynamo (см. определение is_window).
                is_exterior_flag = True
            elif wet_curtain_artifact:
                # Артефакт Room Bounding — игнорируем витраж у санузла.
                is_exterior_flag = False
            elif thin_partition:
                # Стена тоньше 100 мм (или проём в ней) — перегородка,
                # независимо от bsc/rbc/флага Dynamo (см. thin_partition).
                is_exterior_flag = False
            elif not eid:
                # Нет id элемента — пересчитать геометрию не можем.
                # Доверяем Dynamo + сигналам типа конструкции.
                is_exterior_flag = (flag_yes or is_curtain
                                    or is_exterior_function)
            elif interior_glazing:
                # Витраж с явно внутренним типом (Interior Partition /
                # Separator / Empty / Core / Shower) — не фасад. ВЫШЕ orphan,
                # чтобы внутренние curtain-панели не считались фасадом.
                is_exterior_flag = False
            elif is_orphan_facade:
                # Orphan-витраж: фасад, уже поделённый по фронту экспортом
                # между залами этажа. Наружный независимо от bsc/соседей
                # (см. определение is_orphan_facade).
                is_exterior_flag = True
            elif facade_glazing:
                # Storefront / Balcony / фасадное остекление — всегда улица,
                # даже если один элемент общий с несколькими отапл. комнатами
                # (длинный фасад вдоль ряда помещений, bsc>=2). Перекрывает
                # геометрическое правило bsc>=2 ниже, которое иначе метило
                # такой фасад внутренним.
                is_exterior_flag = True
            elif ((is_curtain or facade_spandrel)
                  and bsc_effective >= 2
                  and conditioned_neighbors(eid, sid) > 0
                  and same_level_conditioned_neighbors(eid, sid) == 0):
                # Навесной фасад (витраж GLZ или алюм-спандрел), идущий
                # ВЕРТИКАЛЬНО через этажи: один элемент делят ОДИНАКОВЫЕ
                # помещения на соседних этажах (bsc>=2), но на ЭТОМ этаже
                # соседа нет (same_level=0). Это фасад (улица), а не
                # межкомнатная перегородка — старое правило bsc>=2 метило
                # его внутренним (офисная башня OFF). Ограничено facade-
                # типами, чтобы НЕ задеть глухие стены многоэтажных атриумов.
                is_exterior_flag = True
            elif (not is_curtain) and (rbc is not None) and (rbc >= 1):
                # Авторитетный счётчик ARC-комнат (room_boundary_count): >=2
                # отапл. комнат у стены → ВНУТРЕННЯЯ (обе стороны тёплые).
                # Подстраховка bsc_effective>=2. Иначе (одна зона/улица/
                # балкон) → наружная. Перекрывает ненадёжные bsc/Function.
                is_exterior_flag = not (rbc >= 2 or bsc_effective >= 2)
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
                if (not is_curtain and not facade_spandrel
                        and (not flag_yes or interior_type)):
                    is_exterior_flag = False
                else:
                    # Витраж и алюм-спандрел навесного фасада (bsc=1) реально
                    # смотрят на улицу → наружные.
                    is_exterior_flag = True
            elif spaces and sid:
                # bsc>=2: элемент общий с другим пространством. Если хотя бы
                # один сосед — ОТАПЛИВАЕМОЕ помещение, это межкомнатная
                # перегородка (обе стороны тёплые) → ВНУТРЕННЯЯ. Касается и
                # витража: имя типа НЕнадёжно (в модели «M_Exterior Glazing»
                # используется и для фасада, и для стеклянных перегородок
                # между комнатами, напр. 6763672 между HTL-602.a и 602.b).
                # Геометрия (общий с отапл. помещением) — надёжный признак
                # перегородки. Если ВСЕ соседи неотапливаемые (балкон/шахта),
                # элемент граничит с улицей → наружный. Настоящее фасадное
                # остекление выгружается отдельным элементом с bsc=1 (ветка
                # выше) и остаётся наружным.
                is_exterior_flag = conditioned_neighbors(eid, sid) == 0
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
