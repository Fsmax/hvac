# -*- coding: utf-8 -*-
# Dynamo CPython3 script for Revit 2026.
# Расширенная выгрузка: spaces.csv + thermal_all.csv с азимутом (orientation_deg).
#
# Использование в Dynamo:
#   IN[0] : путь к папке (например, "D:\HVAC")
#   IN[1] : режим — "all" (выгружает оба файла)

import clr
import math

clr.AddReference("RevitServices")
from RevitServices.Persistence import DocumentManager

clr.AddReference("RevitAPI")
from Autodesk.Revit.DB import (
    BuiltInCategory,
    BuiltInParameter,
    ElementId,
    FilteredElementCollector,
    RevitLinkInstance,
    SpatialElement,
    SpatialElementBoundaryOptions,
    StorageType,
    Transform,
    Wall,
    WallKind,
    XYZ,
    Line,
    Arc,
)

clr.AddReference("System")
from System.IO import Directory, Path, StreamWriter
from System.Text import UTF8Encoding

doc = DocumentManager.Instance.CurrentDBDocument


# ----------- утилиты -----------

def id_value(element_id):
    try:
        return element_id.IntegerValue
    except Exception:
        try:
            return element_id.Value
        except Exception:
            return None


def element_id(element):
    try:
        return id_value(element.Id)
    except Exception:
        return None


def element_document(element):
    try:
        return element.Document
    except Exception:
        return doc


def text(value):
    if value is None:
        return ""
    try:
        return str(value)
    except Exception:
        return ""


def clean_input(value):
    return text(value).strip().strip('"')


def safe_name(element):
    try:
        return element.Name
    except Exception:
        return ""


def parameter_value(parameter):
    if parameter is None:
        return ""
    try:
        if parameter.StorageType == StorageType.Double:
            return parameter.AsValueString() or text(parameter.AsDouble())
        if parameter.StorageType == StorageType.Integer:
            return parameter.AsValueString() or text(parameter.AsInteger())
        if parameter.StorageType == StorageType.String:
            return parameter.AsString() or ""
        if parameter.StorageType == StorageType.ElementId:
            value_id = parameter.AsElementId()
            if value_id and value_id != ElementId.InvalidElementId:
                value_element = doc.GetElement(value_id)
                return safe_name(value_element) or text(id_value(value_id))
    except Exception:
        return ""
    return ""


def parameter_double(element, builtin_parameter):
    try:
        parameter = element.get_Parameter(builtin_parameter)
        if parameter and parameter.StorageType == StorageType.Double:
            return parameter.AsDouble()
    except Exception:
        pass
    return None


def builtin(element, builtin_parameter):
    try:
        return parameter_value(element.get_Parameter(builtin_parameter))
    except Exception:
        return ""


def lookup(element, names):
    if element is None:
        return ""
    for name in names:
        try:
            value = parameter_value(element.LookupParameter(name))
            if value:
                return value
        except Exception:
            pass
    return ""


def category_id(element):
    try:
        return id_value(element.Category.Id)
    except Exception:
        return None


def category_name(element):
    try:
        return element.Category.Name
    except Exception:
        return ""


def is_category(element, built_in_category):
    try:
        return category_id(element) == id_value(ElementId(built_in_category))
    except Exception:
        return False


def level_name(element):
    try:
        level = element_document(element).GetElement(element.LevelId)
        return safe_name(level)
    except Exception:
        return builtin(element, BuiltInParameter.LEVEL_PARAM)


# Кэш типов элементов: (doc_hash, type_id_int) -> Type Element
# Огромный выигрыш: type_element() вызывается 6-8 раз на каждую строку.
_TYPE_ELEM_CACHE = {}

# Кэш характеристик типа: (doc_hash, type_id) -> dict с готовыми значениями
# family_name, type_name, function, kind, thermal_value, thickness
_TYPE_INFO_CACHE = {}


def _doc_key(d):
    """Стабильный ключ для документа (на случай связанных моделей)."""
    if d is None:
        return 0
    try:
        return d.PathName or id(d)
    except Exception:
        return id(d)


def type_element(element):
    if element is None:
        return None
    try:
        d = element_document(element)
        tid = element.GetTypeId()
        try:
            tid_val = tid.IntegerValue
        except Exception:
            try:
                tid_val = tid.Value
            except Exception:
                tid_val = -1
        cache_key = (_doc_key(d), tid_val)
        if cache_key in _TYPE_ELEM_CACHE:
            return _TYPE_ELEM_CACHE[cache_key]
        te = d.GetElement(tid)
        _TYPE_ELEM_CACHE[cache_key] = te
        return te
    except Exception:
        return None


def _type_info(element):
    """Возвращает кэшированный dict с характеристиками типа."""
    te = type_element(element)
    if te is None:
        return {}
    try:
        d = element_document(element)
        tid = element.GetTypeId()
        try:
            tid_val = tid.IntegerValue
        except Exception:
            try:
                tid_val = tid.Value
            except Exception:
                tid_val = -1
        cache_key = (_doc_key(d), tid_val)
    except Exception:
        cache_key = None

    if cache_key is not None and cache_key in _TYPE_INFO_CACHE:
        return _TYPE_INFO_CACHE[cache_key]

    info = {}
    try:
        info["family_name"] = te.FamilyName or ""
    except Exception:
        info["family_name"] = ""
    info["type_name"] = safe_name(te) or ""
    info["function"] = builtin(te, BuiltInParameter.FUNCTION_PARAM)
    try:
        info["kind"] = te.Kind if hasattr(te, "Kind") else None
    except Exception:
        info["kind"] = None
    info["thermal_value"] = lookup(
        te,
        [
            "Heat Transfer Coefficient",
            "Thermal Transmittance",
            "U-Value",
            "U Value",
            "U",
        ],
    )
    try:
        info["thickness"] = parameter_value(
            te.get_Parameter(BuiltInParameter.WALL_ATTR_WIDTH_PARAM))
    except Exception:
        info["thickness"] = ""

    if cache_key is not None:
        _TYPE_INFO_CACHE[cache_key] = info
    return info


def type_name(element):
    return _type_info(element).get("type_name", "")


def family_name(element):
    return _type_info(element).get("family_name", "")


def wall_function(element):
    return _type_info(element).get("function", "")


def thermal_value(element):
    return _type_info(element).get("thermal_value", "")


def is_curtain_wall(element):
    """Витражная стена: либо WallKind.Curtain, либо имя содержит curtain/витраж.
    Использует кэш типа — быстро при многократных вызовах для одного типа."""
    if not is_category(element, BuiltInCategory.OST_Walls):
        return False
    info = _type_info(element)
    kind = info.get("kind")
    if kind is not None and kind == WallKind.Curtain:
        return True
    # Запасной вариант — по имени семейства/типа
    full = (info.get("family_name", "") + " " +
            info.get("type_name", "")).lower()
    for kw in ("curtain", "витраж", "стекл", "glaz"):
        if kw in full:
            return True
    return False


def is_exterior_by_function(element):
    """Стена помечена 'Наружная'/'Exterior' в параметре Function типа."""
    if not is_category(element, BuiltInCategory.OST_Walls):
        return False
    function = wall_function(element).lower()
    return "exterior" in function or "наруж" in function


def is_exterior_wall(element):
    """Базовая проверка по типу стены (без учёта геометрии).
    Не определяет, реально ли стена выходит наружу — для этого
    смотри ещё shared_count в boundary_counts."""
    if not is_category(element, BuiltInCategory.OST_Walls):
        return False
    # Витражные стены всегда считаются наружными (это фасадное остекление)
    if is_curtain_wall(element):
        return True
    return is_exterior_by_function(element)


def is_window_or_door(element):
    return is_category(element, BuiltInCategory.OST_Windows) or is_category(element, BuiltInCategory.OST_Doors)


def element_area(element):
    value = builtin(element, BuiltInParameter.HOST_AREA_COMPUTED)
    if value:
        return value
    return lookup(element, ["Area", "Площадь"])


def element_height_m(space):
    height = parameter_double(space, BuiltInParameter.ROOM_HEIGHT)
    if height is None:
        try:
            height = space.UnboundedHeight
        except Exception:
            height = None
    if height is None:
        return ""
    return round(height * 0.3048, 3)


# --------- НОВОЕ: получение азимута стены ---------

def vector_to_azimuth_deg(vec):
    """Конвертирует горизонтальный вектор в азимут (0..360°), 0=N, 90=E."""
    try:
        x = float(vec.X)
        y = float(vec.Y)
    except Exception:
        return ""
    if abs(x) < 1e-9 and abs(y) < 1e-9:
        return ""
    # atan2(X, Y): 0 = +Y (север), pi/2 = +X (восток)
    angle = math.degrees(math.atan2(x, y))
    if angle < 0:
        angle += 360.0
    return round(angle, 1)


def wall_orientation_deg(wall):
    """Возвращает азимут наружной стороны стены, или ''."""
    try:
        normal = wall.Orientation  # XYZ, наружу
    except Exception:
        normal = None

    if normal is None:
        # Fallback через геометрию LocationCurve
        try:
            loc = wall.Location
            curve = loc.Curve
            if isinstance(curve, Line):
                d = curve.Direction
            else:
                # Для дуги — касательная в середине
                p0 = curve.GetEndParameter(0)
                p1 = curve.GetEndParameter(1)
                t = curve.ComputeDerivatives((p0 + p1) * 0.5, True).BasisX
                d = t
            # Поворот на -90° даёт нормаль вправо от направления стены
            normal = XYZ(d.Y, -d.X, 0)
            if getattr(wall, "Flipped", False):
                normal = XYZ(-normal.X, -normal.Y, 0)
        except Exception:
            return ""
    return vector_to_azimuth_deg(normal)


def segment_direction_azimuth(segment):
    """Азимут наружу для сегмента границы помещения."""
    try:
        curve = segment.GetCurve()
        d = curve.Direction if isinstance(curve, Line) else None
        if d is None:
            return ""
        # Граничный сегмент идёт против часовой стрелки вокруг помещения,
        # значит нормаль наружу = (Dy, -Dx)
        normal = XYZ(d.Y, -d.X, 0)
        return vector_to_azimuth_deg(normal)
    except Exception:
        return ""


def element_inserts(element):
    inserts = []
    try:
        insert_ids = element.FindInserts(True, False, False, False)
    except Exception:
        insert_ids = []
    for insert_id in insert_ids:
        insert = element_document(element).GetElement(insert_id)
        if insert and is_window_or_door(insert):
            inserts.append(insert)
    return inserts


def boundary_element_from_segment(segment):
    host_element = doc.GetElement(segment.ElementId)
    link_name = ""

    try:
        link_id = segment.LinkElementId
    except Exception:
        link_id = ElementId.InvalidElementId

    if link_id and link_id != ElementId.InvalidElementId:
        try:
            link_doc = host_element.GetLinkDocument()
            linked_element = link_doc.GetElement(link_id)
            link_name = safe_name(host_element)
            if linked_element:
                return linked_element, link_name
        except Exception:
            pass

    return host_element, link_name


def boundary_key(element, link_name):
    if element is None:
        return None
    return text(link_name) + "|" + text(element_id(element))


# Префиксы номеров/имён неотапливаемых пространств (балконы, террасы,
# открытые площадки, шахты). Стены, граничащие только с такими
# пространствами, считаются наружными.
UNCONDITIONED_PREFIXES = ("OFC-", "BAL-", "TER-", "SHAFT", "ШАХТ")
UNCONDITIONED_KEYWORDS = ("балкон", "терраса", "лоджия", "balcony",
                          "terrace", "loggia", "shaft", "open air")


# Кэш результата is_unconditioned_space по Id
_UNCONDITIONED_CACHE = {}


def is_unconditioned_space(space):
    """True если пространство — балкон/терраса/шахта/неотапл. помещение.
    Результат кэшируется по Id пространства."""
    try:
        sid = space.Id.IntegerValue
    except Exception:
        try:
            sid = space.Id.Value
        except Exception:
            sid = None
    if sid is not None and sid in _UNCONDITIONED_CACHE:
        return _UNCONDITIONED_CACHE[sid]

    try:
        number = (builtin(space, BuiltInParameter.ROOM_NUMBER) or "").strip()
        name = (builtin(space, BuiltInParameter.ROOM_NAME) or "").strip()
    except Exception:
        if sid is not None:
            _UNCONDITIONED_CACHE[sid] = False
        return False

    result = False
    if number or name:
        num_up = number.upper()
        for pfx in UNCONDITIONED_PREFIXES:
            if num_up.startswith(pfx):
                result = True
                break
        if not result:
            full = (number + " " + name).lower()
            for kw in UNCONDITIONED_KEYWORDS:
                if kw in full:
                    result = True
                    break

    if sid is not None:
        _UNCONDITIONED_CACHE[sid] = result
    return result


def shared_boundary_map(spatial_elements):
    by_boundary = {}
    options = SpatialElementBoundaryOptions()

    for space in spatial_elements:
        # Неотапливаемые пространства не вкладываются в подсчёт bsc —
        # тогда стена между жилой комнатой и балконом получит bsc=1
        # и будет правильно классифицирована как наружная.
        if is_unconditioned_space(space):
            continue
        space_key = text(element_id(space))
        try:
            loops = space.GetBoundarySegments(options)
        except Exception:
            loops = None
        if not loops:
            continue

        seen_in_space = set()
        for loop in loops:
            for segment in loop:
                element, link_name = boundary_element_from_segment(segment)
                key = boundary_key(element, link_name)
                if key:
                    seen_in_space.add(key)

        for key in seen_in_space:
            if key not in by_boundary:
                by_boundary[key] = set()
            by_boundary[key].add(space_key)

    result = {}
    for key in by_boundary:
        result[key] = len(by_boundary[key])
    return result


def has_area(element):
    value = builtin(element, BuiltInParameter.ROOM_AREA)
    try:
        return float(parameter_double(element, BuiltInParameter.ROOM_AREA) or 0) > 0
    except Exception:
        return True


def collect_spatial_elements():
    spaces = (FilteredElementCollector(doc)
              .OfCategory(BuiltInCategory.OST_MEPSpaces)
              .WhereElementIsNotElementType()
              .ToElements())
    spaces = [s for s in spaces if has_area(s)]
    if spaces:
        return spaces, "Spaces (MEP)"
    rooms = (FilteredElementCollector(doc)
             .OfCategory(BuiltInCategory.OST_Rooms)
             .WhereElementIsNotElementType()
             .ToElements())
    rooms = [r for r in rooms if has_area(r)]
    return rooms, "Rooms (Architecture)"


def write_csv(file_path, rows):
    folder = Path.GetDirectoryName(file_path)
    if folder and not Directory.Exists(folder):
        Directory.CreateDirectory(folder)
    encoding = UTF8Encoding(True)  # с BOM, удобно для Excel
    writer = StreamWriter(file_path, False, encoding)
    try:
        for row in rows:
            line = []
            for value in row:
                text_value = text(value)
                if any(ch in text_value for ch in (",", "\"", "\n", "\r")):
                    text_value = "\"" + text_value.replace("\"", "\"\"") + "\""
                line.append(text_value)
            writer.WriteLine(",".join(line))
    finally:
        writer.Close()


def combine_path(folder_path, file_name):
    try:
        if not Directory.Exists(folder_path):
            return folder_path
    except Exception:
        pass
    return Path.Combine(folder_path, file_name)


def space_row(space):
    return [
        element_id(space),
        category_name(space),
        builtin(space, BuiltInParameter.ROOM_NUMBER),
        builtin(space, BuiltInParameter.ROOM_NAME),
        level_name(space),
        builtin(space, BuiltInParameter.ROOM_AREA),
        builtin(space, BuiltInParameter.ROOM_VOLUME),
        builtin(space, BuiltInParameter.ROOM_HEIGHT),
        lookup(space, ["Zone", "Space Type"]),
        lookup(space, ["Heating Load", "Calculated Heating Load", "Design Heating Load"]),
        lookup(space, ["Cooling Load", "Calculated Cooling Load", "Design Cooling Load"]),
    ]


def segment_other_side_conditioned(segment, space, spaces, offset_ft=2.5):
    """True, если с ПРОТИВОПОЛОЖНОЙ от space стороны границы есть
    ОТАПЛИВАЕМОЕ помещение → это межкомнатная перегородка, а не фасад.

    Зачем: boundary_counts даёт shared_count=1, когда сосед обходит ту же
    стену ДРУГИМ элементом (частый артефакт Revit), и перегородка ошибочно
    считается наружной. Геометрия (есть ли отапл. помещение с другой стороны)
    надёжнее, чем тип/Function стены и счётчик границ.
    """
    try:
        crv = segment.GetCurve()
        p0 = crv.GetEndPoint(0)
        p1 = crv.GetEndPoint(1)
        perp = XYZ(-(p1.Y - p0.Y), (p1.X - p0.X), 0.0).Normalize()
    except Exception:
        return False
    mx = (p0.X + p1.X) * 0.5
    my = (p0.Y + p1.Y) * 0.5
    mz = (p0.Z + p1.Z) * 0.5 + 4.0   # внутрь высоты этажа, от плоскости пола
    try:
        my_sid = element_id(space)
    except Exception:
        my_sid = None
    for sgn in (1.0, -1.0):
        probe = XYZ(mx + perp.X * offset_ft * sgn,
                    my + perp.Y * offset_ft * sgn, mz)
        sp = find_space_for_point(probe, spaces)
        if sp is None:
            continue
        try:
            if element_id(sp) == my_sid:
                continue   # это наша сторона — пропускаем
        except Exception:
            pass
        if not is_unconditioned_space(sp):
            return True    # отапл. сосед с другой стороны → перегородка
    return False


def thermal_rows(space, exterior_only, boundary_counts):
    rows = []
    options = SpatialElementBoundaryOptions()
    try:
        loops = space.GetBoundarySegments(options)
    except Exception:
        loops = None

    if not loops:
        return rows

    # Порог для отсева corner-артефактов: фрагменты стены короче 0.5 м
    # (площадью < ~0.3..0.5 м² при высоте 3 м) почти всегда — побочный
    # эффект разбиения границы в углу помещения.
    CORNER_ARTIFACT_LEN_M = 0.5

    space_height = element_height_m(space)
    for loop in loops:
        for segment in loop:
            element, link_name = boundary_element_from_segment(segment)
            if element is None:
                continue
            # Длина сегмента — для отсева угловых артефактов
            try:
                seg_len_m = segment.GetCurve().Length * 0.3048
            except Exception:
                seg_len_m = None
            if (seg_len_m is not None
                    and seg_len_m < CORNER_ARTIFACT_LEN_M
                    and is_category(element, BuiltInCategory.OST_Walls)):
                # corner-фрагмент стены — пропускаем
                continue
            shared_count = 1
            key = boundary_key(element, link_name)
            if key in boundary_counts:
                shared_count = boundary_counts[key]
            # Стена считается реально наружной, если:
            # (1) витражная (всегда фасад), ИЛИ
            # (2) её Function = Exterior/Наружная, ИЛИ
            # (3) с противоположной стороны нет ни одного помещения
            #     (shared_count == 1) — геометрический признак, работает
            #     для несущих ж/б стен, у которых Function пуст/Bearing.
            # Внутренние стены (shared_count >= 2) исключены даже если
            # помечены как Exterior — это ошибка в модели.
            is_wall = is_category(element, BuiltInCategory.OST_Walls)
            if is_wall:
                if is_curtain_wall(element):
                    real_exterior = True
                elif shared_count >= 2:
                    real_exterior = False
                else:
                    # shared_count == 1 НЕнадёжно: сосед часто обходит ту же
                    # стену другим элементом, и перегородка получает счётчик 1.
                    # Проверяем геометрией: если с другой стороны есть отапл.
                    # помещение → перегородка (внутренняя), иначе → фасад.
                    if segment_other_side_conditioned(segment, space,
                                                      spatial_elements):
                        real_exterior = False
                    else:
                        real_exterior = True
            else:
                real_exterior = False
            exterior = real_exterior  # для обратной совместимости в выводе
            if exterior_only and not real_exterior:
                continue

            # length_m уже посчитан выше (seg_len_m) — переиспользуем
            length_m = seg_len_m

            approx_area = ""
            if length_m is not None and space_height != "":
                approx_area = round(length_m * space_height, 3)

            # Азимут: сначала из стены, потом из сегмента
            orient = wall_orientation_deg(element) if is_category(element, BuiltInCategory.OST_Walls) else ""
            if orient == "":
                orient = segment_direction_azimuth(segment)

            rows.append([
                element_id(space),
                builtin(space, BuiltInParameter.ROOM_NUMBER),
                builtin(space, BuiltInParameter.ROOM_NAME),
                level_name(space),
                "external_wall",
                "yes" if real_exterior else "no",
                element_id(element),
                link_name,
                category_name(element),
                family_name(element),
                type_name(element),
                level_name(element),
                round(length_m, 3) if length_m is not None else "",
                space_height,
                approx_area,
                element_area(element),
                builtin(type_element(element), BuiltInParameter.WALL_ATTR_WIDTH_PARAM),
                wall_function(element),
                thermal_value(element),
                "",
                shared_count,
                orient,    # НОВОЕ: orientation_deg
            ])

            for insert in element_inserts(element):
                rows.append([
                    element_id(space),
                    builtin(space, BuiltInParameter.ROOM_NUMBER),
                    builtin(space, BuiltInParameter.ROOM_NAME),
                    level_name(space),
                    "opening",
                    "yes" if real_exterior else "no",
                    element_id(insert),
                    link_name,
                    category_name(insert),
                    family_name(insert),
                    type_name(insert),
                    level_name(insert),
                    "",
                    "",
                    "",
                    element_area(insert),
                    "",
                    "hosted by exterior wall",
                    thermal_value(insert),
                    element_id(element),
                    shared_count,
                    orient,   # проёмы наследуют азимут стены-хозяина
                ])
    return rows


# ----------- сбор «бесхозных» витражей (вне Room Bounding) -----------
#
# Curtain Walls c выключенным флагом «Room Bounding» (часто встречается у
# фасадных витражей на балконах) НЕ попадают в GetBoundarySegments(),
# поэтому Q_солнца у бедрумов получается = 0. Этот блок собирает все
# Curtain Walls (включая связанные арх-модели) и приписывает каждый к
# ближайшему ОТАПЛИВАЕМОМУ помещению по геометрии.


def collect_all_curtain_walls():
    """Возвращает список (wall, transform, link_doc, link_name).

    Собирает витражи из основного документа и всех связанных моделей.
    transform — преобразование координат из модели стены в координаты
    основного документа (для связанных моделей).

    ВАЖНО: если арх-модель прилинкована несколькими RevitLinkInstance,
    каждый витраж берётся ТОЛЬКО ОДИН РАЗ (по первому экземпляру),
    чтобы избежать дублирования строк в CSV.
    """
    results = []
    seen_docs = set()  # PathName уже обработанных документов

    # Основной документ
    main_path = ""
    try:
        main_path = doc.PathName or "MAIN"
    except Exception:
        main_path = "MAIN"
    seen_docs.add(main_path)
    walls = (FilteredElementCollector(doc)
             .OfCategory(BuiltInCategory.OST_Walls)
             .WhereElementIsNotElementType()
             .ToElements())
    for w in walls:
        try:
            wt = doc.GetElement(w.GetTypeId())
            if wt and hasattr(wt, "Kind") and wt.Kind == WallKind.Curtain:
                results.append((w, Transform.Identity, doc, ""))
        except Exception:
            pass

    # Связанные модели — каждый ИСХОДНЫЙ документ обрабатываем один раз
    try:
        link_instances = (FilteredElementCollector(doc)
                          .OfClass(RevitLinkInstance)
                          .ToElements())
    except Exception:
        link_instances = []

    for link_inst in link_instances:
        try:
            link_doc = link_inst.GetLinkDocument()
            if link_doc is None:
                continue
            link_path = ""
            try:
                link_path = link_doc.PathName or safe_name(link_inst)
            except Exception:
                link_path = safe_name(link_inst)
            if link_path in seen_docs:
                continue  # этот документ уже обработан другим экземпляром
            seen_docs.add(link_path)

            link_transform = link_inst.GetTotalTransform()
            link_inst_name = safe_name(link_inst)
            link_walls = (FilteredElementCollector(link_doc)
                          .OfCategory(BuiltInCategory.OST_Walls)
                          .WhereElementIsNotElementType()
                          .ToElements())
            for w in link_walls:
                try:
                    wt = link_doc.GetElement(w.GetTypeId())
                    if wt and hasattr(wt, "Kind") and wt.Kind == WallKind.Curtain:
                        results.append((w, link_transform, link_doc, link_inst_name))
                except Exception:
                    pass
        except Exception:
            pass

    return results


def wall_midpoint_global(wall, transform):
    """Возвращает середину центральной линии стены в глобальных координатах
    основного документа. None если не удалось получить."""
    try:
        loc = wall.Location
        curve = loc.Curve
    except Exception:
        return None
    try:
        p0 = curve.GetEndPoint(0)
        p1 = curve.GetEndPoint(1)
        mid_local = XYZ((p0.X + p1.X) * 0.5,
                        (p0.Y + p1.Y) * 0.5,
                        (p0.Z + p1.Z) * 0.5)
        if transform is None or transform == Transform.Identity:
            return mid_local
        return transform.OfPoint(mid_local)
    except Exception:
        return None


# Кэш bounding box и Z-диапазона пространств для быстрого префильтра.
# {space.Id.IntegerValue: (xmin, ymin, zmin, xmax, ymax, zmax)} — все в футах.
_SPACE_BBOX_CACHE = {}


def _space_bbox(space):
    """Возвращает (xmin, ymin, zmin, xmax, ymax, zmax) пространства в футах.
    Кэшируется по Id."""
    try:
        sid = space.Id.IntegerValue
    except Exception:
        try:
            sid = space.Id.Value
        except Exception:
            sid = None
    if sid is not None and sid in _SPACE_BBOX_CACHE:
        return _SPACE_BBOX_CACHE[sid]
    bbox = None
    try:
        bb = space.get_BoundingBox(None)
        if bb is not None:
            bbox = (float(bb.Min.X), float(bb.Min.Y), float(bb.Min.Z),
                    float(bb.Max.X), float(bb.Max.Y), float(bb.Max.Z))
    except Exception:
        bbox = None
    if sid is not None:
        _SPACE_BBOX_CACHE[sid] = bbox
    return bbox


def _point_in_bbox(point, bbox, tol_ft=1.6):
    """Быстрая проверка: точка в bbox с допуском (по умолчанию 0.5 м)."""
    if bbox is None or point is None:
        return True   # без bbox — пропускаем дальше, не отсеиваем
    try:
        x, y, z = float(point.X), float(point.Y), float(point.Z)
    except Exception:
        return True
    xmin, ymin, zmin, xmax, ymax, zmax = bbox
    return (xmin - tol_ft <= x <= xmax + tol_ft and
            ymin - tol_ft <= y <= ymax + tol_ft and
            zmin - tol_ft <= z <= zmax + tol_ft)


def find_space_for_point(point, spaces, level_z=None):
    """Возвращает пространство, ВНУТРИ которого находится точка.
    Только строгое попадание — без fallback на «ближайший центр»
    (старый fallback давал ложные привязки витражей).

    Префильтр по bounding box даёт огромный выигрыш на проектах с
    сотнями пространств — IsPointInSpace дорогой, а bbox-проверка
    тривиальная.
    """
    if point is None:
        return None
    for sp in spaces:
        bbox = _space_bbox(sp)
        if not _point_in_bbox(point, bbox):
            continue
        try:
            if hasattr(sp, "IsPointInSpace") and sp.IsPointInSpace(point):
                return sp
        except Exception:
            try:
                if hasattr(sp, "IsPointInRoom") and sp.IsPointInRoom(point):
                    return sp
            except Exception:
                pass
    return None


def curtain_wall_touches_space(wall, transform, space, tolerance_ft=1.6):
    """Проверка: витраж геометрически касается границы пространства.

    tolerance_ft ≈ 0.5 м. Сэмплируем 5 точек вдоль центральной линии
    витража и проверяем, есть ли хотя бы одна, которая лежит
    в окрестности границы space (через IsPointInSpace с небольшим
    смещением к центру помещения).

    Быстрая отсечка: если bbox пространства не пересекается с
    серединой витража даже с допуском — пропускаем без дорогостоящих
    IsPointInSpace.
    """
    try:
        curve = wall.Location.Curve
    except Exception:
        return False
    # Быстрая bbox-отсечка по середине витража
    try:
        mid_local = curve.Evaluate(0.5, True)
        if transform is not None and transform != Transform.Identity:
            mid_global = transform.OfPoint(mid_local)
        else:
            mid_global = mid_local
        bbox = _space_bbox(space)
        if not _point_in_bbox(mid_global, bbox, tol_ft=3.3):  # ~1 м
            return False
    except Exception:
        pass
    try:
        # Нормаль витража
        normal = wall.Orientation
    except Exception:
        return False
    # Преобразуем нормаль в глобальные координаты
    try:
        if transform is not None and transform != Transform.Identity:
            normal_global = transform.OfVector(normal)
        else:
            normal_global = normal
    except Exception:
        normal_global = normal

    # 5 точек вдоль кривой
    test_dirs = (-1.0, 1.0)  # с обеих сторон стены
    for t in (0.1, 0.3, 0.5, 0.7, 0.9):
        try:
            param = curve.GetEndParameter(0) * (1 - t) + curve.GetEndParameter(1) * t
            p_local = curve.Evaluate(param, False)
        except Exception:
            continue
        try:
            if transform is not None and transform != Transform.Identity:
                p_global = transform.OfPoint(p_local)
            else:
                p_global = p_local
        except Exception:
            p_global = p_local
        # Пробуем по обе стороны стены
        for sign in test_dirs:
            try:
                offset_pt = XYZ(
                    p_global.X + sign * tolerance_ft * normal_global.X,
                    p_global.Y + sign * tolerance_ft * normal_global.Y,
                    p_global.Z,
                )
                if hasattr(space, "IsPointInSpace") and space.IsPointInSpace(offset_pt):
                    return True
                if hasattr(space, "IsPointInRoom") and space.IsPointInRoom(offset_pt):
                    return True
            except Exception:
                continue
    return False


def find_conditioned_neighbor(unconditioned_space, all_spaces):
    """Для неотапливаемого помещения (балкона) находит ближайшее
    отапливаемое — по горизонтальному расстоянию между Location.Point."""
    try:
        pt0 = unconditioned_space.Location.Point
    except Exception:
        return None
    best_sp = None
    best_dist = 1e18
    z0 = float(pt0.Z)
    for sp in all_spaces:
        if sp.Id == unconditioned_space.Id:
            continue
        if is_unconditioned_space(sp):
            continue
        try:
            pt = sp.Location.Point
            dz = abs(float(pt.Z) - z0)
            if dz > 2.0 / 0.3048:
                continue
            dx = float(pt.X) - float(pt0.X)
            dy = float(pt.Y) - float(pt0.Y)
            d = (dx * dx + dy * dy) ** 0.5
            if d < best_dist:
                best_dist = d
                best_sp = sp
        except Exception:
            continue
    return best_sp


def split_curtain_wall_by_frontage(wall, transform, spatial_elements,
                                   spaces_with_glazing):
    """Делит площадь витража по сетке фронт×высота между ВСЕМИ помещениями,
    которые он реально закрывает.

    Старое поведение orphan-блока: вся стена целиком приписывалась ОДНОМУ
    помещению (по её середине). Для длинного/двусветного фасада это завышало
    остекление одной комнаты в разы (напр. HTL-063 CAFE получал 381 м² при
    площади пола 103 м²), а соседние залы и верхний этаж оставались без стекла.

    Теперь сэмплируем стену сеткой: по длине (~1.5 м) и по высоте (~2.5 м,
    т.е. по этажам). Для каждой ячейки определяем помещение с внутренней
    стороны (find_space_for_point с обеих сторон). Площадь ячейки идёт тому
    помещению. Итог: низ стены → залы нижнего этажа, верх → помещения
    верхнего; по длине — каждому залу его фронт.

    Возвращает список dict: {"space", "area_m2", "frontage_m"}.
    """
    try:
        curve = wall.Location.Curve
        bb = wall.get_BoundingBox(None)
        base_z = bb.Min.Z
        top_z = bb.Max.Z
    except Exception:
        return []
    L_m = curve.Length * 0.3048
    H_m = (top_z - base_z) * 0.3048
    if L_m <= 0.1 or H_m <= 0.1:
        return []
    n_pos = max(2, int(round(L_m / 1.5)))
    n_z = max(1, int(round(H_m / 2.5)))
    cell_area = (L_m / n_pos) * (H_m / n_z)
    seg_len_m = L_m / n_pos
    off = 1.6  # фт (~0.5 м) — смещение внутрь от плоскости стены
    agg = {}   # sid -> [space, area_m2, set(pos_index)]
    for i in range(n_pos):
        t = (i + 0.5) / n_pos
        try:
            p = curve.Evaluate(t, True)
            tg = curve.ComputeDerivatives(t, True).BasisX.Normalize()
            perp = XYZ(-tg.Y, tg.X, 0.0).Normalize()
        except Exception:
            continue
        for j in range(n_z):
            z = base_z + (j + 0.5) * (top_z - base_z) / n_z
            found = None
            for sgn in (1.0, -1.0):
                probe = XYZ(p.X + perp.X * off * sgn,
                            p.Y + perp.Y * off * sgn, z)
                gp = transform.OfPoint(probe) if transform is not None else probe
                sp = find_space_for_point(gp, spatial_elements)
                if sp is None:
                    continue
                if is_unconditioned_space(sp):
                    sp = find_conditioned_neighbor(sp, spatial_elements)
                if sp is not None and not is_unconditioned_space(sp):
                    found = sp
                    break
            if found is None:
                continue
            sid = text(element_id(found))
            if sid in spaces_with_glazing:
                continue   # у помещения уже есть свой витраж — не дублируем
            if sid not in agg:
                agg[sid] = [found, 0.0, set()]
            agg[sid][1] += cell_area
            agg[sid][2].add(i)
    out = []
    for sid in agg:
        sp, area, positions = agg[sid]
        if area < 0.5:
            continue
        out.append({"space": sp, "area_m2": round(area, 3),
                    "frontage_m": round(len(positions) * seg_len_m, 3)})
    return out


def collect_orphan_curtain_rows(spatial_elements, already_seen_element_ids,
                                 spaces_with_glazing=None):
    """Возвращает дополнительные строки для thermal_all.csv: витражи,
    которые не вошли в стандартные boundary loops.

    КЛЮЧЕВОЕ ОГРАНИЧЕНИЕ:
    Если у помещения УЖЕ есть свой витраж в стандартной выгрузке
    (spaces_with_glazing), новые витражи к нему НЕ добавляются.
    Это страхует от ложных привязок: например, маленькая ванная,
    у которой через стандартный обход уже найден её витраж в сторону
    балкона, не должна получать ещё 3-4 витража из соседних бедрумов.

    Привязка строгая:
    (1) если середина витража попадает ВНУТРЬ space по IsPointInSpace —
        этот space берётся (а если он балкон, то его отапл. сосед);
    (2) иначе — пробуем геометрически: витраж касается границы space
        (curtain_wall_touches_space); если касается отапливаемого
        space — берём его, если касается балкона — берём соседа.
    Если ничего не нашлось — витраж пропускается.

    Также фильтруем витражи площадью < 0.5 м² (мелкие фрагменты —
    декоративные панели/угловые куски, не значимые для расчёта).

    already_seen_element_ids — множество (link_name, element_id) уже
    выведенных элементов, чтобы избежать дубликатов.
    spaces_with_glazing — множество space_id, у которых уже есть свои
    витражи. По умолчанию пусто.
    """
    rows = []
    seen_in_this_pass = set()
    if spaces_with_glazing is None:
        spaces_with_glazing = set()

    MIN_AREA_M2 = 0.5

    try:
        curtain_walls = collect_all_curtain_walls()
    except Exception:
        return rows

    for wall, transform, src_doc, link_name in curtain_walls:
        try:
            eid = id_value(wall.Id)
        except Exception:
            continue
        key = (text(link_name), text(eid))
        if key in already_seen_element_ids or key in seen_in_this_pass:
            continue

        # Фильтр мелких фрагментов
        try:
            area_str = element_area(wall)
            area_val = float(parameter_double(wall, BuiltInParameter.HOST_AREA_COMPUTED) or 0)
            if area_val and area_val * 0.3048 * 0.3048 < MIN_AREA_M2:
                continue
        except Exception:
            pass

        # Параметры стены (общие для всех долей)
        u_val = thermal_value(wall)
        family = ""
        type_n = ""
        try:
            wt = src_doc.GetElement(wall.GetTypeId())
            if wt:
                family = wt.FamilyName or ""
                type_n = safe_name(wt) or ""
        except Exception:
            pass
        try:
            thickness = wall.get_Parameter(BuiltInParameter.WALL_ATTR_WIDTH_PARAM)
            thickness_val = parameter_value(thickness) if thickness else ""
        except Exception:
            thickness_val = ""
        orient = wall_orientation_deg(wall)

        # Делим витраж по фронту×высоте между ВСЕМИ залами, которые он
        # закрывает (низ→нижний этаж, верх→верхний; по длине — каждому его
        # фронт). Старое поведение (вся стена → одно помещение по середине)
        # завышало остекление одной комнаты в разы и обделяло соседей.
        parts = split_curtain_wall_by_frontage(
            wall, transform, spatial_elements, spaces_with_glazing)
        if not parts:
            continue
        seen_in_this_pass.add(key)
        n_parts = len(parts)
        for part in parts:
            target_space = part["space"]
            area_m2 = part["area_m2"]
            frontage = part["frontage_m"]
            rows.append([
                element_id(target_space),
                builtin(target_space, BuiltInParameter.ROOM_NUMBER),
                builtin(target_space, BuiltInParameter.ROOM_NAME),
                level_name(target_space),
                "external_wall",
                "yes",                 # витраж — всегда наружный
                eid,
                link_name,
                category_name(wall),
                family,
                type_n,
                level_name(wall),
                round(frontage, 3),    # boundary_length_m = фронт этой доли
                element_height_m(target_space),
                area_m2,               # approx_area_m2 = доля (фронт×высота)
                area_m2,               # element_area = та же доля
                thickness_val,
                "curtain (orphan)",   # маркер фасадного витража (для загрузчика)
                u_val,
                "",
                n_parts,               # bsc = число залов, делящих витраж
                orient,
            ])
    return rows


# ----------- основной запуск -----------

output_path = r"D:\HVAC\spaces.csv"
output_table = "all"
collect_orphans = True   # IN[2] — "fast"/"false"/"no" чтобы выключить

try:
    if len(IN) > 0 and IN[0]:
        output_path = clean_input(IN[0])
    if len(IN) > 1 and IN[1]:
        output_table = clean_input(IN[1]).lower()
    if len(IN) > 2 and IN[2] is not None:
        flag = clean_input(IN[2]).lower()
        if flag in ("fast", "no", "false", "0", "off", "skip"):
            collect_orphans = False
except Exception:
    pass

spatial_elements, source_name = collect_spatial_elements()
# Прогреваем bbox-кэш одним проходом — потом IsPointInSpace
# отсекается без дорогих геометрических вызовов.
for _sp in spatial_elements:
    _space_bbox(_sp)
boundary_counts = shared_boundary_map(spatial_elements)

# Расширенный заголовок thermal_all.csv с новой колонкой orientation_deg
THERMAL_HEADER = [
    "space_id",
    "space_number",
    "space_name",
    "space_level",
    "row_type",
    "is_exterior_wall",
    "element_id",
    "link_model",
    "category",
    "family",
    "type",
    "element_level",
    "boundary_length_m",
    "space_height_m",
    "approx_area_m2",
    "element_area",
    "thickness",
    "function",
    "thermal_value",
    "host_element_id",
    "boundary_space_count",
    "orientation_deg",   # НОВАЯ КОЛОНКА
]

SPACES_HEADER = [
    "id", "category", "number", "name", "level", "area", "volume",
    "height", "zone", "heating_load", "cooling_load",
]

def _seen_set(rows):
    """Множество (link_name, element_id) для строк, уже выведенных
    через стандартные границы помещений."""
    seen = set()
    for r in rows[1:]:  # без заголовка
        try:
            link = text(r[7])   # link_model
            eid = text(r[6])    # element_id
            seen.add((link, eid))
        except Exception:
            pass
    return seen


def _spaces_with_existing_glazing(rows):
    """Множество space_id, у которых УЖЕ есть витражи (Curtain Walls)
    в стандартной выгрузке. Orphan-сборщик не должен добавлять им
    дополнительные витражи — у них своё остекление уже учтено.
    Определяем «витраж» по семейству: содержит 'витраж'/'curtain'/'balcony'.
    """
    result = set()
    for r in rows[1:]:
        try:
            sid = text(r[0])               # space_id
            family = text(r[9]).lower()    # family
            type_n = text(r[10]).lower()   # type
            combined = family + " " + type_n
            for kw in ("витраж", "curtain", "balcony", "chr_balcony"):
                if kw in combined:
                    result.add(sid)
                    break
        except Exception:
            pass
    return result


if output_table == "all":
    spaces_rows = [SPACES_HEADER]
    for spatial_element in spatial_elements:
        spaces_rows.append(space_row(spatial_element))

    thermal_rows_all = [THERMAL_HEADER]
    for spatial_element in spatial_elements:
        thermal_rows_all.extend(thermal_rows(spatial_element, False, boundary_counts))

    # Дополнительный проход: витражи без Room Bounding (опционально).
    # Помещения, у которых уже есть свои витражи в стандартной выгрузке,
    # дополнительных не получают.
    if collect_orphans:
        orphan_rows = collect_orphan_curtain_rows(
            spatial_elements,
            _seen_set(thermal_rows_all),
            _spaces_with_existing_glazing(thermal_rows_all),
        )
        thermal_rows_all.extend(orphan_rows)
    else:
        orphan_rows = []

    spaces_path = combine_path(output_path, "spaces.csv")
    thermal_path = combine_path(output_path, "thermal_all.csv")
    write_csv(spaces_path, spaces_rows)
    write_csv(thermal_path, thermal_rows_all)
    OUT = [
        "CSV files written",
        spaces_path,
        "Spaces rows: " + str(len(spaces_rows) - 1),
        thermal_path,
        "Thermal rows: " + str(len(thermal_rows_all) - 1),
        "Orphan curtain walls added: " + str(len(orphan_rows)),
        "Source: " + source_name,
    ]
elif output_table == "thermal" or output_table == "thermal_all":
    result_rows = [THERMAL_HEADER]
    exterior_only = output_table == "thermal"
    for spatial_element in spatial_elements:
        result_rows.extend(thermal_rows(spatial_element, exterior_only, boundary_counts))
    # Добавляем «orphan» витражи только для полной выгрузки и если не fast
    if output_table == "thermal_all" and collect_orphans:
        orphan_rows = collect_orphan_curtain_rows(
            spatial_elements,
            _seen_set(result_rows),
            _spaces_with_existing_glazing(result_rows),
        )
        result_rows.extend(orphan_rows)
    write_csv(output_path, result_rows)
    OUT = ["CSV written", output_path,
           "Rows: " + str(len(result_rows) - 1),
           "Source: " + source_name]
else:
    result_rows = [SPACES_HEADER]
    for spatial_element in spatial_elements:
        result_rows.append(space_row(spatial_element))
    write_csv(output_path, result_rows)
    OUT = ["CSV written", output_path,
           "Rows: " + str(len(result_rows) - 1),
           "Source: " + source_name]
