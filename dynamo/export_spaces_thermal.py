# -*- coding: utf-8 -*-
# Dynamo CPython3 script for Revit 2026.
# Р Р°СЃС€РёСЂРµРЅРЅР°СЏ РІС‹РіСЂСѓР·РєР°: spaces.csv + thermal_all.csv СЃ Р°Р·РёРјСѓС‚РѕРј (orientation_deg).
#
# РСЃРїРѕР»СЊР·РѕРІР°РЅРёРµ РІ Dynamo:
#   IN[0] : РїСѓС‚СЊ Рє РїР°РїРєРµ (РЅР°РїСЂРёРјРµСЂ, "D:\HVAC")
#   IN[1] : СЂРµР¶РёРј вЂ” "all" (РІС‹РіСЂСѓР¶Р°РµС‚ РѕР±Р° С„Р°Р№Р»Р°)

import clr
import math

clr.AddReference("RevitServices")
from RevitServices.Persistence import DocumentManager

clr.AddReference("RevitAPI")
from Autodesk.Revit.DB import (
    BuiltInCategory,
    BuiltInParameter,
    Element, ElementId,
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


# ----------- СѓС‚РёР»РёС‚С‹ -----------

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
    if element is None:
        return ""
    try:
        # CPython3 (Revit 2026): element.Name РЅР°РїСЂСЏРјСѓСЋ РЅРµ С‡РёС‚Р°РµС‚СЃСЏ
        # (РёР·РІРµСЃС‚РЅР°СЏ РѕСЃРѕР±РµРЅРЅРѕСЃС‚СЊ pythonnet) вЂ” Р±РµСЂС‘Рј С‡РµСЂРµР· РґРµСЃРєСЂРёРїС‚РѕСЂ.
        name = clr.GetClrType(Element).GetProperty("Name").GetValue(element, None)
        if name:
            return name
    except Exception:
        pass
    try:
        return element.Name or ""
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


# РљСЌС€ С‚РёРїРѕРІ СЌР»РµРјРµРЅС‚РѕРІ: (doc_hash, type_id_int) -> Type Element
# РћРіСЂРѕРјРЅС‹Р№ РІС‹РёРіСЂС‹С€: type_element() РІС‹Р·С‹РІР°РµС‚СЃСЏ 6-8 СЂР°Р· РЅР° РєР°Р¶РґСѓСЋ СЃС‚СЂРѕРєСѓ.
_TYPE_ELEM_CACHE = {}

# РљСЌС€ С…Р°СЂР°РєС‚РµСЂРёСЃС‚РёРє С‚РёРїР°: (doc_hash, type_id) -> dict СЃ РіРѕС‚РѕРІС‹РјРё Р·РЅР°С‡РµРЅРёСЏРјРё
# family_name, type_name, function, kind, thermal_value, thickness
_TYPE_INFO_CACHE = {}


def _doc_key(d):
    """РЎС‚Р°Р±РёР»СЊРЅС‹Р№ РєР»СЋС‡ РґР»СЏ РґРѕРєСѓРјРµРЅС‚Р° (РЅР° СЃР»СѓС‡Р°Р№ СЃРІСЏР·Р°РЅРЅС‹С… РјРѕРґРµР»РµР№)."""
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
    """Р’РѕР·РІСЂР°С‰Р°РµС‚ РєСЌС€РёСЂРѕРІР°РЅРЅС‹Р№ dict СЃ С…Р°СЂР°РєС‚РµСЂРёСЃС‚РёРєР°РјРё С‚РёРїР°."""
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
    """Р’РёС‚СЂР°Р¶РЅР°СЏ СЃС‚РµРЅР°: Р»РёР±Рѕ WallKind.Curtain, Р»РёР±Рѕ РёРјСЏ СЃРѕРґРµСЂР¶РёС‚ curtain/РІРёС‚СЂР°Р¶.
    РСЃРїРѕР»СЊР·СѓРµС‚ РєСЌС€ С‚РёРїР° вЂ” Р±С‹СЃС‚СЂРѕ РїСЂРё РјРЅРѕРіРѕРєСЂР°С‚РЅС‹С… РІС‹Р·РѕРІР°С… РґР»СЏ РѕРґРЅРѕРіРѕ С‚РёРїР°."""
    if not is_category(element, BuiltInCategory.OST_Walls):
        return False
    info = _type_info(element)
    kind = info.get("kind")
    if kind is not None and kind == WallKind.Curtain:
        return True
    # Р—Р°РїР°СЃРЅРѕР№ РІР°СЂРёР°РЅС‚ вЂ” РїРѕ РёРјРµРЅРё СЃРµРјРµР№СЃС‚РІР°/С‚РёРїР°
    full = (info.get("family_name", "") + " " +
            info.get("type_name", "")).lower()
    for kw in ("curtain", "РІРёС‚СЂР°Р¶", "СЃС‚РµРєР»", "glaz"):
        if kw in full:
            return True
    return False


def is_exterior_by_function(element):
    """РЎС‚РµРЅР° РїРѕРјРµС‡РµРЅР° 'РќР°СЂСѓР¶РЅР°СЏ'/'Exterior' РІ РїР°СЂР°РјРµС‚СЂРµ Function С‚РёРїР°."""
    if not is_category(element, BuiltInCategory.OST_Walls):
        return False
    function = wall_function(element).lower()
    return "exterior" in function or "РЅР°СЂСѓР¶" in function


def is_exterior_wall(element):
    """Р‘Р°Р·РѕРІР°СЏ РїСЂРѕРІРµСЂРєР° РїРѕ С‚РёРїСѓ СЃС‚РµРЅС‹ (Р±РµР· СѓС‡С‘С‚Р° РіРµРѕРјРµС‚СЂРёРё).
    РќРµ РѕРїСЂРµРґРµР»СЏРµС‚, СЂРµР°Р»СЊРЅРѕ Р»Рё СЃС‚РµРЅР° РІС‹С…РѕРґРёС‚ РЅР°СЂСѓР¶Сѓ вЂ” РґР»СЏ СЌС‚РѕРіРѕ
    СЃРјРѕС‚СЂРё РµС‰С‘ shared_count РІ boundary_counts."""
    if not is_category(element, BuiltInCategory.OST_Walls):
        return False
    # Р’РёС‚СЂР°Р¶РЅС‹Рµ СЃС‚РµРЅС‹ РІСЃРµРіРґР° СЃС‡РёС‚Р°СЋС‚СЃСЏ РЅР°СЂСѓР¶РЅС‹РјРё (СЌС‚Рѕ С„Р°СЃР°РґРЅРѕРµ РѕСЃС‚РµРєР»РµРЅРёРµ)
    if is_curtain_wall(element):
        return True
    return is_exterior_by_function(element)


def is_window_or_door(element):
    return is_category(element, BuiltInCategory.OST_Windows) or is_category(element, BuiltInCategory.OST_Doors)


def element_area(element):
    value = builtin(element, BuiltInParameter.HOST_AREA_COMPUTED)
    if value:
        return value
    return lookup(element, ["Area", "РџР»РѕС‰Р°РґСЊ"])


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


# --------- РќРћР’РћР•: РїРѕР»СѓС‡РµРЅРёРµ Р°Р·РёРјСѓС‚Р° СЃС‚РµРЅС‹ ---------

def vector_to_azimuth_deg(vec):
    """РљРѕРЅРІРµСЂС‚РёСЂСѓРµС‚ РіРѕСЂРёР·РѕРЅС‚Р°Р»СЊРЅС‹Р№ РІРµРєС‚РѕСЂ РІ Р°Р·РёРјСѓС‚ (0..360В°), 0=N, 90=E."""
    try:
        x = float(vec.X)
        y = float(vec.Y)
    except Exception:
        return ""
    if abs(x) < 1e-9 and abs(y) < 1e-9:
        return ""
    # atan2(X, Y): 0 = +Y (СЃРµРІРµСЂ), pi/2 = +X (РІРѕСЃС‚РѕРє)
    angle = math.degrees(math.atan2(x, y))
    if angle < 0:
        angle += 360.0
    return round(angle, 1)


def wall_orientation_deg(wall):
    """Р’РѕР·РІСЂР°С‰Р°РµС‚ Р°Р·РёРјСѓС‚ РЅР°СЂСѓР¶РЅРѕР№ СЃС‚РѕСЂРѕРЅС‹ СЃС‚РµРЅС‹, РёР»Рё ''."""
    try:
        normal = wall.Orientation  # XYZ, РЅР°СЂСѓР¶Сѓ
    except Exception:
        normal = None

    if normal is None:
        # Fallback С‡РµСЂРµР· РіРµРѕРјРµС‚СЂРёСЋ LocationCurve
        try:
            loc = wall.Location
            curve = loc.Curve
            if isinstance(curve, Line):
                d = curve.Direction
            else:
                # Р”Р»СЏ РґСѓРіРё вЂ” РєР°СЃР°С‚РµР»СЊРЅР°СЏ РІ СЃРµСЂРµРґРёРЅРµ
                p0 = curve.GetEndParameter(0)
                p1 = curve.GetEndParameter(1)
                t = curve.ComputeDerivatives((p0 + p1) * 0.5, True).BasisX
                d = t
            # РџРѕРІРѕСЂРѕС‚ РЅР° -90В° РґР°С‘С‚ РЅРѕСЂРјР°Р»СЊ РІРїСЂР°РІРѕ РѕС‚ РЅР°РїСЂР°РІР»РµРЅРёСЏ СЃС‚РµРЅС‹
            normal = XYZ(d.Y, -d.X, 0)
            if getattr(wall, "Flipped", False):
                normal = XYZ(-normal.X, -normal.Y, 0)
        except Exception:
            return ""
    return vector_to_azimuth_deg(normal)


def segment_direction_azimuth(segment):
    """РђР·РёРјСѓС‚ РЅР°СЂСѓР¶Сѓ РґР»СЏ СЃРµРіРјРµРЅС‚Р° РіСЂР°РЅРёС†С‹ РїРѕРјРµС‰РµРЅРёСЏ."""
    try:
        curve = segment.GetCurve()
        d = curve.Direction if isinstance(curve, Line) else None
        if d is None:
            return ""
        # Р“СЂР°РЅРёС‡РЅС‹Р№ СЃРµРіРјРµРЅС‚ РёРґС‘С‚ РїСЂРѕС‚РёРІ С‡Р°СЃРѕРІРѕР№ СЃС‚СЂРµР»РєРё РІРѕРєСЂСѓРі РїРѕРјРµС‰РµРЅРёСЏ,
        # Р·РЅР°С‡РёС‚ РЅРѕСЂРјР°Р»СЊ РЅР°СЂСѓР¶Сѓ = (Dy, -Dx)
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


# РџСЂРµС„РёРєСЃС‹ РЅРѕРјРµСЂРѕРІ/РёРјС‘РЅ РЅРµРѕС‚Р°РїР»РёРІР°РµРјС‹С… РїСЂРѕСЃС‚СЂР°РЅСЃС‚РІ (Р±Р°Р»РєРѕРЅС‹, С‚РµСЂСЂР°СЃС‹,
# РѕС‚РєСЂС‹С‚С‹Рµ РїР»РѕС‰Р°РґРєРё, С€Р°С…С‚С‹). РЎС‚РµРЅС‹, РіСЂР°РЅРёС‡Р°С‰РёРµ С‚РѕР»СЊРєРѕ СЃ С‚Р°РєРёРјРё
# РїСЂРѕСЃС‚СЂР°РЅСЃС‚РІР°РјРё, СЃС‡РёС‚Р°СЋС‚СЃСЏ РЅР°СЂСѓР¶РЅС‹РјРё.
UNCONDITIONED_PREFIXES = ("OFC-", "BAL-", "TER-", "SHAFT", "РЁРђРҐРў")
UNCONDITIONED_KEYWORDS = ("Р±Р°Р»РєРѕРЅ", "С‚РµСЂСЂР°СЃР°", "Р»РѕРґР¶РёСЏ", "balcony",
                          "terrace", "loggia", "shaft", "open air")


# РљСЌС€ СЂРµР·СѓР»СЊС‚Р°С‚Р° is_unconditioned_space РїРѕ Id
_UNCONDITIONED_CACHE = {}


def is_unconditioned_space(space):
    """True РµСЃР»Рё РїСЂРѕСЃС‚СЂР°РЅСЃС‚РІРѕ вЂ” Р±Р°Р»РєРѕРЅ/С‚РµСЂСЂР°СЃР°/С€Р°С…С‚Р°/РЅРµРѕС‚Р°РїР». РїРѕРјРµС‰РµРЅРёРµ.
    Р РµР·СѓР»СЊС‚Р°С‚ РєСЌС€РёСЂСѓРµС‚СЃСЏ РїРѕ Id РїСЂРѕСЃС‚СЂР°РЅСЃС‚РІР°."""
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
        # РќРµРѕС‚Р°РїР»РёРІР°РµРјС‹Рµ РїСЂРѕСЃС‚СЂР°РЅСЃС‚РІР° РЅРµ РІРєР»Р°РґС‹РІР°СЋС‚СЃСЏ РІ РїРѕРґСЃС‡С‘С‚ bsc вЂ”
        # С‚РѕРіРґР° СЃС‚РµРЅР° РјРµР¶РґСѓ Р¶РёР»РѕР№ РєРѕРјРЅР°С‚РѕР№ Рё Р±Р°Р»РєРѕРЅРѕРј РїРѕР»СѓС‡РёС‚ bsc=1
        # Рё Р±СѓРґРµС‚ РїСЂР°РІРёР»СЊРЅРѕ РєР»Р°СЃСЃРёС„РёС†РёСЂРѕРІР°РЅР° РєР°Рє РЅР°СЂСѓР¶РЅР°СЏ.
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
    encoding = UTF8Encoding(True)  # СЃ BOM, СѓРґРѕР±РЅРѕ РґР»СЏ Excel
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


def thermal_rows(space, exterior_only, boundary_counts):
    rows = []
    options = SpatialElementBoundaryOptions()
    try:
        loops = space.GetBoundarySegments(options)
    except Exception:
        loops = None

    if not loops:
        return rows

    # РџРѕСЂРѕРі РґР»СЏ РѕС‚СЃРµРІР° corner-Р°СЂС‚РµС„Р°РєС‚РѕРІ: С„СЂР°РіРјРµРЅС‚С‹ СЃС‚РµРЅС‹ РєРѕСЂРѕС‡Рµ 0.5 Рј
    # (РїР»РѕС‰Р°РґСЊСЋ < ~0.3..0.5 РјВІ РїСЂРё РІС‹СЃРѕС‚Рµ 3 Рј) РїРѕС‡С‚Рё РІСЃРµРіРґР° вЂ” РїРѕР±РѕС‡РЅС‹Р№
    # СЌС„С„РµРєС‚ СЂР°Р·Р±РёРµРЅРёСЏ РіСЂР°РЅРёС†С‹ РІ СѓРіР»Сѓ РїРѕРјРµС‰РµРЅРёСЏ.
    CORNER_ARTIFACT_LEN_M = 0.5

    space_height = element_height_m(space)
    for loop in loops:
        for segment in loop:
            element, link_name = boundary_element_from_segment(segment)
            if element is None:
                continue
            # Р”Р»РёРЅР° СЃРµРіРјРµРЅС‚Р° вЂ” РґР»СЏ РѕС‚СЃРµРІР° СѓРіР»РѕРІС‹С… Р°СЂС‚РµС„Р°РєС‚РѕРІ
            try:
                seg_len_m = segment.GetCurve().Length * 0.3048
            except Exception:
                seg_len_m = None
            if (seg_len_m is not None
                    and seg_len_m < CORNER_ARTIFACT_LEN_M
                    and is_category(element, BuiltInCategory.OST_Walls)):
                # corner-С„СЂР°РіРјРµРЅС‚ СЃС‚РµРЅС‹ вЂ” РїСЂРѕРїСѓСЃРєР°РµРј
                continue
            shared_count = 1
            key = boundary_key(element, link_name)
            if key in boundary_counts:
                shared_count = boundary_counts[key]
            # РЎС‚РµРЅР° СЃС‡РёС‚Р°РµС‚СЃСЏ СЂРµР°Р»СЊРЅРѕ РЅР°СЂСѓР¶РЅРѕР№, РµСЃР»Рё:
            # (1) РІРёС‚СЂР°Р¶РЅР°СЏ (РІСЃРµРіРґР° С„Р°СЃР°Рґ), РР›Р
            # (2) РµС‘ Function = Exterior/РќР°СЂСѓР¶РЅР°СЏ, РР›Р
            # (3) СЃ РїСЂРѕС‚РёРІРѕРїРѕР»РѕР¶РЅРѕР№ СЃС‚РѕСЂРѕРЅС‹ РЅРµС‚ РЅРё РѕРґРЅРѕРіРѕ РїРѕРјРµС‰РµРЅРёСЏ
            #     (shared_count == 1) вЂ” РіРµРѕРјРµС‚СЂРёС‡РµСЃРєРёР№ РїСЂРёР·РЅР°Рє, СЂР°Р±РѕС‚Р°РµС‚
            #     РґР»СЏ РЅРµСЃСѓС‰РёС… Р¶/Р± СЃС‚РµРЅ, Сѓ РєРѕС‚РѕСЂС‹С… Function РїСѓСЃС‚/Bearing.
            # Р’РЅСѓС‚СЂРµРЅРЅРёРµ СЃС‚РµРЅС‹ (shared_count >= 2) РёСЃРєР»СЋС‡РµРЅС‹ РґР°Р¶Рµ РµСЃР»Рё
            # РїРѕРјРµС‡РµРЅС‹ РєР°Рє Exterior вЂ” СЌС‚Рѕ РѕС€РёР±РєР° РІ РјРѕРґРµР»Рё.
            is_wall = is_category(element, BuiltInCategory.OST_Walls)
            if is_wall:
                if is_curtain_wall(element):
                    real_exterior = True
                elif shared_count >= 2:
                    real_exterior = False
                else:
                    # shared_count == 1: СЃС‚РµРЅР° РіСЂР°РЅРёС‡РёС‚ С‚РѕР»СЊРєРѕ СЃ РѕРґРЅРёРј
                    # РїРѕРјРµС‰РµРЅРёРµРј в†’ СЃ РґСЂСѓРіРѕР№ СЃС‚РѕСЂРѕРЅС‹ СѓР»РёС†Р°/РЅРµРѕС‚Р°РїР»РёРІР°РµРјРѕРµ
                    real_exterior = True
            else:
                real_exterior = False
            exterior = real_exterior  # РґР»СЏ РѕР±СЂР°С‚РЅРѕР№ СЃРѕРІРјРµСЃС‚РёРјРѕСЃС‚Рё РІ РІС‹РІРѕРґРµ
            if exterior_only and not real_exterior:
                continue

            # length_m СѓР¶Рµ РїРѕСЃС‡РёС‚Р°РЅ РІС‹С€Рµ (seg_len_m) вЂ” РїРµСЂРµРёСЃРїРѕР»СЊР·СѓРµРј
            length_m = seg_len_m

            approx_area = ""
            if length_m is not None and space_height != "":
                approx_area = round(length_m * space_height, 3)

            # РђР·РёРјСѓС‚: СЃРЅР°С‡Р°Р»Р° РёР· СЃС‚РµРЅС‹, РїРѕС‚РѕРј РёР· СЃРµРіРјРµРЅС‚Р°
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
                orient,    # РќРћР’РћР•: orientation_deg
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
                    orient,   # РїСЂРѕС‘РјС‹ РЅР°СЃР»РµРґСѓСЋС‚ Р°Р·РёРјСѓС‚ СЃС‚РµРЅС‹-С…РѕР·СЏРёРЅР°
                ])
    return rows


# ----------- СЃР±РѕСЂ В«Р±РµСЃС…РѕР·РЅС‹С…В» РІРёС‚СЂР°Р¶РµР№ (РІРЅРµ Room Bounding) -----------
#
# Curtain Walls c РІС‹РєР»СЋС‡РµРЅРЅС‹Рј С„Р»Р°РіРѕРј В«Room BoundingВ» (С‡Р°СЃС‚Рѕ РІСЃС‚СЂРµС‡Р°РµС‚СЃСЏ Сѓ
# С„Р°СЃР°РґРЅС‹С… РІРёС‚СЂР°Р¶РµР№ РЅР° Р±Р°Р»РєРѕРЅР°С…) РќР• РїРѕРїР°РґР°СЋС‚ РІ GetBoundarySegments(),
# РїРѕСЌС‚РѕРјСѓ Q_СЃРѕР»РЅС†Р° Сѓ Р±РµРґСЂСѓРјРѕРІ РїРѕР»СѓС‡Р°РµС‚СЃСЏ = 0. Р­С‚РѕС‚ Р±Р»РѕРє СЃРѕР±РёСЂР°РµС‚ РІСЃРµ
# Curtain Walls (РІРєР»СЋС‡Р°СЏ СЃРІСЏР·Р°РЅРЅС‹Рµ Р°СЂС…-РјРѕРґРµР»Рё) Рё РїСЂРёРїРёСЃС‹РІР°РµС‚ РєР°Р¶РґС‹Р№ Рє
# Р±Р»РёР¶Р°Р№С€РµРјСѓ РћРўРђРџР›РР’РђР•РњРћРњРЈ РїРѕРјРµС‰РµРЅРёСЋ РїРѕ РіРµРѕРјРµС‚СЂРёРё.


def collect_all_curtain_walls():
    """Р’РѕР·РІСЂР°С‰Р°РµС‚ СЃРїРёСЃРѕРє (wall, transform, link_doc, link_name).

    РЎРѕР±РёСЂР°РµС‚ РІРёС‚СЂР°Р¶Рё РёР· РѕСЃРЅРѕРІРЅРѕРіРѕ РґРѕРєСѓРјРµРЅС‚Р° Рё РІСЃРµС… СЃРІСЏР·Р°РЅРЅС‹С… РјРѕРґРµР»РµР№.
    transform вЂ” РїСЂРµРѕР±СЂР°Р·РѕРІР°РЅРёРµ РєРѕРѕСЂРґРёРЅР°С‚ РёР· РјРѕРґРµР»Рё СЃС‚РµРЅС‹ РІ РєРѕРѕСЂРґРёРЅР°С‚С‹
    РѕСЃРЅРѕРІРЅРѕРіРѕ РґРѕРєСѓРјРµРЅС‚Р° (РґР»СЏ СЃРІСЏР·Р°РЅРЅС‹С… РјРѕРґРµР»РµР№).

    Р’РђР–РќРћ: РµСЃР»Рё Р°СЂС…-РјРѕРґРµР»СЊ РїСЂРёР»РёРЅРєРѕРІР°РЅР° РЅРµСЃРєРѕР»СЊРєРёРјРё RevitLinkInstance,
    РєР°Р¶РґС‹Р№ РІРёС‚СЂР°Р¶ Р±РµСЂС‘С‚СЃСЏ РўРћР›Р¬РљРћ РћР”РРќ Р РђР— (РїРѕ РїРµСЂРІРѕРјСѓ СЌРєР·РµРјРїР»СЏСЂСѓ),
    С‡С‚РѕР±С‹ РёР·Р±РµР¶Р°С‚СЊ РґСѓР±Р»РёСЂРѕРІР°РЅРёСЏ СЃС‚СЂРѕРє РІ CSV.
    """
    results = []
    seen_docs = set()  # PathName СѓР¶Рµ РѕР±СЂР°Р±РѕС‚Р°РЅРЅС‹С… РґРѕРєСѓРјРµРЅС‚РѕРІ

    # РћСЃРЅРѕРІРЅРѕР№ РґРѕРєСѓРјРµРЅС‚
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

    # РЎРІСЏР·Р°РЅРЅС‹Рµ РјРѕРґРµР»Рё вЂ” РєР°Р¶РґС‹Р№ РРЎРҐРћР”РќР«Р™ РґРѕРєСѓРјРµРЅС‚ РѕР±СЂР°Р±Р°С‚С‹РІР°РµРј РѕРґРёРЅ СЂР°Р·
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
                continue  # СЌС‚РѕС‚ РґРѕРєСѓРјРµРЅС‚ СѓР¶Рµ РѕР±СЂР°Р±РѕС‚Р°РЅ РґСЂСѓРіРёРј СЌРєР·РµРјРїР»СЏСЂРѕРј
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
    """Р’РѕР·РІСЂР°С‰Р°РµС‚ СЃРµСЂРµРґРёРЅСѓ С†РµРЅС‚СЂР°Р»СЊРЅРѕР№ Р»РёРЅРёРё СЃС‚РµРЅС‹ РІ РіР»РѕР±Р°Р»СЊРЅС‹С… РєРѕРѕСЂРґРёРЅР°С‚Р°С…
    РѕСЃРЅРѕРІРЅРѕРіРѕ РґРѕРєСѓРјРµРЅС‚Р°. None РµСЃР»Рё РЅРµ СѓРґР°Р»РѕСЃСЊ РїРѕР»СѓС‡РёС‚СЊ."""
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


# РљСЌС€ bounding box Рё Z-РґРёР°РїР°Р·РѕРЅР° РїСЂРѕСЃС‚СЂР°РЅСЃС‚РІ РґР»СЏ Р±С‹СЃС‚СЂРѕРіРѕ РїСЂРµС„РёР»СЊС‚СЂР°.
# {space.Id.IntegerValue: (xmin, ymin, zmin, xmax, ymax, zmax)} вЂ” РІСЃРµ РІ С„СѓС‚Р°С….
_SPACE_BBOX_CACHE = {}


def _space_bbox(space):
    """Р’РѕР·РІСЂР°С‰Р°РµС‚ (xmin, ymin, zmin, xmax, ymax, zmax) РїСЂРѕСЃС‚СЂР°РЅСЃС‚РІР° РІ С„СѓС‚Р°С….
    РљСЌС€РёСЂСѓРµС‚СЃСЏ РїРѕ Id."""
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
    """Р‘С‹СЃС‚СЂР°СЏ РїСЂРѕРІРµСЂРєР°: С‚РѕС‡РєР° РІ bbox СЃ РґРѕРїСѓСЃРєРѕРј (РїРѕ СѓРјРѕР»С‡Р°РЅРёСЋ 0.5 Рј)."""
    if bbox is None or point is None:
        return True   # Р±РµР· bbox вЂ” РїСЂРѕРїСѓСЃРєР°РµРј РґР°Р»СЊС€Рµ, РЅРµ РѕС‚СЃРµРёРІР°РµРј
    try:
        x, y, z = float(point.X), float(point.Y), float(point.Z)
    except Exception:
        return True
    xmin, ymin, zmin, xmax, ymax, zmax = bbox
    return (xmin - tol_ft <= x <= xmax + tol_ft and
            ymin - tol_ft <= y <= ymax + tol_ft and
            zmin - tol_ft <= z <= zmax + tol_ft)


def find_space_for_point(point, spaces, level_z=None):
    """Р’РѕР·РІСЂР°С‰Р°РµС‚ РїСЂРѕСЃС‚СЂР°РЅСЃС‚РІРѕ, Р’РќРЈРўР Р РєРѕС‚РѕСЂРѕРіРѕ РЅР°С…РѕРґРёС‚СЃСЏ С‚РѕС‡РєР°.
    РўРѕР»СЊРєРѕ СЃС‚СЂРѕРіРѕРµ РїРѕРїР°РґР°РЅРёРµ вЂ” Р±РµР· fallback РЅР° В«Р±Р»РёР¶Р°Р№С€РёР№ С†РµРЅС‚СЂВ»
    (СЃС‚Р°СЂС‹Р№ fallback РґР°РІР°Р» Р»РѕР¶РЅС‹Рµ РїСЂРёРІСЏР·РєРё РІРёС‚СЂР°Р¶РµР№).

    РџСЂРµС„РёР»СЊС‚СЂ РїРѕ bounding box РґР°С‘С‚ РѕРіСЂРѕРјРЅС‹Р№ РІС‹РёРіСЂС‹С€ РЅР° РїСЂРѕРµРєС‚Р°С… СЃ
    СЃРѕС‚РЅСЏРјРё РїСЂРѕСЃС‚СЂР°РЅСЃС‚РІ вЂ” IsPointInSpace РґРѕСЂРѕРіРѕР№, Р° bbox-РїСЂРѕРІРµСЂРєР°
    С‚СЂРёРІРёР°Р»СЊРЅР°СЏ.
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
    """РџСЂРѕРІРµСЂРєР°: РІРёС‚СЂР°Р¶ РіРµРѕРјРµС‚СЂРёС‡РµСЃРєРё РєР°СЃР°РµС‚СЃСЏ РіСЂР°РЅРёС†С‹ РїСЂРѕСЃС‚СЂР°РЅСЃС‚РІР°.

    tolerance_ft в‰€ 0.5 Рј. РЎСЌРјРїР»РёСЂСѓРµРј 5 С‚РѕС‡РµРє РІРґРѕР»СЊ С†РµРЅС‚СЂР°Р»СЊРЅРѕР№ Р»РёРЅРёРё
    РІРёС‚СЂР°Р¶Р° Рё РїСЂРѕРІРµСЂСЏРµРј, РµСЃС‚СЊ Р»Рё С…РѕС‚СЏ Р±С‹ РѕРґРЅР°, РєРѕС‚РѕСЂР°СЏ Р»РµР¶РёС‚
    РІ РѕРєСЂРµСЃС‚РЅРѕСЃС‚Рё РіСЂР°РЅРёС†С‹ space (С‡РµСЂРµР· IsPointInSpace СЃ РЅРµР±РѕР»СЊС€РёРј
    СЃРјРµС‰РµРЅРёРµРј Рє С†РµРЅС‚СЂСѓ РїРѕРјРµС‰РµРЅРёСЏ).

    Р‘С‹СЃС‚СЂР°СЏ РѕС‚СЃРµС‡РєР°: РµСЃР»Рё bbox РїСЂРѕСЃС‚СЂР°РЅСЃС‚РІР° РЅРµ РїРµСЂРµСЃРµРєР°РµС‚СЃСЏ СЃ
    СЃРµСЂРµРґРёРЅРѕР№ РІРёС‚СЂР°Р¶Р° РґР°Р¶Рµ СЃ РґРѕРїСѓСЃРєРѕРј вЂ” РїСЂРѕРїСѓСЃРєР°РµРј Р±РµР· РґРѕСЂРѕРіРѕСЃС‚РѕСЏС‰РёС…
    IsPointInSpace.
    """
    try:
        curve = wall.Location.Curve
    except Exception:
        return False
    # Р‘С‹СЃС‚СЂР°СЏ bbox-РѕС‚СЃРµС‡РєР° РїРѕ СЃРµСЂРµРґРёРЅРµ РІРёС‚СЂР°Р¶Р°
    try:
        mid_local = curve.Evaluate(0.5, True)
        if transform is not None and transform != Transform.Identity:
            mid_global = transform.OfPoint(mid_local)
        else:
            mid_global = mid_local
        bbox = _space_bbox(space)
        if not _point_in_bbox(mid_global, bbox, tol_ft=3.3):  # ~1 Рј
            return False
    except Exception:
        pass
    try:
        # РќРѕСЂРјР°Р»СЊ РІРёС‚СЂР°Р¶Р°
        normal = wall.Orientation
    except Exception:
        return False
    # РџСЂРµРѕР±СЂР°Р·СѓРµРј РЅРѕСЂРјР°Р»СЊ РІ РіР»РѕР±Р°Р»СЊРЅС‹Рµ РєРѕРѕСЂРґРёРЅР°С‚С‹
    try:
        if transform is not None and transform != Transform.Identity:
            normal_global = transform.OfVector(normal)
        else:
            normal_global = normal
    except Exception:
        normal_global = normal

    # 5 С‚РѕС‡РµРє РІРґРѕР»СЊ РєСЂРёРІРѕР№
    test_dirs = (-1.0, 1.0)  # СЃ РѕР±РµРёС… СЃС‚РѕСЂРѕРЅ СЃС‚РµРЅС‹
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
        # РџСЂРѕР±СѓРµРј РїРѕ РѕР±Рµ СЃС‚РѕСЂРѕРЅС‹ СЃС‚РµРЅС‹
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
    """Р”Р»СЏ РЅРµРѕС‚Р°РїР»РёРІР°РµРјРѕРіРѕ РїРѕРјРµС‰РµРЅРёСЏ (Р±Р°Р»РєРѕРЅР°) РЅР°С…РѕРґРёС‚ Р±Р»РёР¶Р°Р№С€РµРµ
    РѕС‚Р°РїР»РёРІР°РµРјРѕРµ вЂ” РїРѕ РіРѕСЂРёР·РѕРЅС‚Р°Р»СЊРЅРѕРјСѓ СЂР°СЃСЃС‚РѕСЏРЅРёСЋ РјРµР¶РґСѓ Location.Point."""
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


def collect_orphan_curtain_rows(spatial_elements, already_seen_element_ids,
                                 spaces_with_glazing=None):
    """Р’РѕР·РІСЂР°С‰Р°РµС‚ РґРѕРїРѕР»РЅРёС‚РµР»СЊРЅС‹Рµ СЃС‚СЂРѕРєРё РґР»СЏ thermal_all.csv: РІРёС‚СЂР°Р¶Рё,
    РєРѕС‚РѕСЂС‹Рµ РЅРµ РІРѕС€Р»Рё РІ СЃС‚Р°РЅРґР°СЂС‚РЅС‹Рµ boundary loops.

    РљР›Р®Р§Р•Р’РћР• РћР“Р РђРќРР§Р•РќРР•:
    Р•СЃР»Рё Сѓ РїРѕРјРµС‰РµРЅРёСЏ РЈР–Р• РµСЃС‚СЊ СЃРІРѕР№ РІРёС‚СЂР°Р¶ РІ СЃС‚Р°РЅРґР°СЂС‚РЅРѕР№ РІС‹РіСЂСѓР·РєРµ
    (spaces_with_glazing), РЅРѕРІС‹Рµ РІРёС‚СЂР°Р¶Рё Рє РЅРµРјСѓ РќР• РґРѕР±Р°РІР»СЏСЋС‚СЃСЏ.
    Р­С‚Рѕ СЃС‚СЂР°С…СѓРµС‚ РѕС‚ Р»РѕР¶РЅС‹С… РїСЂРёРІСЏР·РѕРє: РЅР°РїСЂРёРјРµСЂ, РјР°Р»РµРЅСЊРєР°СЏ РІР°РЅРЅР°СЏ,
    Сѓ РєРѕС‚РѕСЂРѕР№ С‡РµСЂРµР· СЃС‚Р°РЅРґР°СЂС‚РЅС‹Р№ РѕР±С…РѕРґ СѓР¶Рµ РЅР°Р№РґРµРЅ РµС‘ РІРёС‚СЂР°Р¶ РІ СЃС‚РѕСЂРѕРЅСѓ
    Р±Р°Р»РєРѕРЅР°, РЅРµ РґРѕР»Р¶РЅР° РїРѕР»СѓС‡Р°С‚СЊ РµС‰С‘ 3-4 РІРёС‚СЂР°Р¶Р° РёР· СЃРѕСЃРµРґРЅРёС… Р±РµРґСЂСѓРјРѕРІ.

    РџСЂРёРІСЏР·РєР° СЃС‚СЂРѕРіР°СЏ:
    (1) РµСЃР»Рё СЃРµСЂРµРґРёРЅР° РІРёС‚СЂР°Р¶Р° РїРѕРїР°РґР°РµС‚ Р’РќРЈРўР Р¬ space РїРѕ IsPointInSpace вЂ”
        СЌС‚РѕС‚ space Р±РµСЂС‘С‚СЃСЏ (Р° РµСЃР»Рё РѕРЅ Р±Р°Р»РєРѕРЅ, С‚Рѕ РµРіРѕ РѕС‚Р°РїР». СЃРѕСЃРµРґ);
    (2) РёРЅР°С‡Рµ вЂ” РїСЂРѕР±СѓРµРј РіРµРѕРјРµС‚СЂРёС‡РµСЃРєРё: РІРёС‚СЂР°Р¶ РєР°СЃР°РµС‚СЃСЏ РіСЂР°РЅРёС†С‹ space
        (curtain_wall_touches_space); РµСЃР»Рё РєР°СЃР°РµС‚СЃСЏ РѕС‚Р°РїР»РёРІР°РµРјРѕРіРѕ
        space вЂ” Р±РµСЂС‘Рј РµРіРѕ, РµСЃР»Рё РєР°СЃР°РµС‚СЃСЏ Р±Р°Р»РєРѕРЅР° вЂ” Р±РµСЂС‘Рј СЃРѕСЃРµРґР°.
    Р•СЃР»Рё РЅРёС‡РµРіРѕ РЅРµ РЅР°С€Р»РѕСЃСЊ вЂ” РІРёС‚СЂР°Р¶ РїСЂРѕРїСѓСЃРєР°РµС‚СЃСЏ.

    РўР°РєР¶Рµ С„РёР»СЊС‚СЂСѓРµРј РІРёС‚СЂР°Р¶Рё РїР»РѕС‰Р°РґСЊСЋ < 0.5 РјВІ (РјРµР»РєРёРµ С„СЂР°РіРјРµРЅС‚С‹ вЂ”
    РґРµРєРѕСЂР°С‚РёРІРЅС‹Рµ РїР°РЅРµР»Рё/СѓРіР»РѕРІС‹Рµ РєСѓСЃРєРё, РЅРµ Р·РЅР°С‡РёРјС‹Рµ РґР»СЏ СЂР°СЃС‡С‘С‚Р°).

    already_seen_element_ids вЂ” РјРЅРѕР¶РµСЃС‚РІРѕ (link_name, element_id) СѓР¶Рµ
    РІС‹РІРµРґРµРЅРЅС‹С… СЌР»РµРјРµРЅС‚РѕРІ, С‡С‚РѕР±С‹ РёР·Р±РµР¶Р°С‚СЊ РґСѓР±Р»РёРєР°С‚РѕРІ.
    spaces_with_glazing вЂ” РјРЅРѕР¶РµСЃС‚РІРѕ space_id, Сѓ РєРѕС‚РѕСЂС‹С… СѓР¶Рµ РµСЃС‚СЊ СЃРІРѕРё
    РІРёС‚СЂР°Р¶Рё. РџРѕ СѓРјРѕР»С‡Р°РЅРёСЋ РїСѓСЃС‚Рѕ.
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

        # Р¤РёР»СЊС‚СЂ РјРµР»РєРёС… С„СЂР°РіРјРµРЅС‚РѕРІ
        try:
            area_str = element_area(wall)
            area_val = float(parameter_double(wall, BuiltInParameter.HOST_AREA_COMPUTED) or 0)
            if area_val and area_val * 0.3048 * 0.3048 < MIN_AREA_M2:
                continue
        except Exception:
            pass

        # РЎС‚СЂР°С‚РµРіРёСЏ 1: СЃРµСЂРµРґРёРЅР° РІРёС‚СЂР°Р¶Р° РїРѕРїР°Р»Р° РІРЅСѓС‚СЂСЊ РєР°РєРѕРіРѕ-С‚Рѕ РїСЂРѕСЃС‚СЂР°РЅСЃС‚РІР°
        mid = wall_midpoint_global(wall, transform)
        host_space = find_space_for_point(mid, spatial_elements)

        target_space = None
        if host_space is not None:
            if is_unconditioned_space(host_space):
                cn = find_conditioned_neighbor(host_space, spatial_elements)
                if cn is not None and curtain_wall_touches_space(wall, transform, cn):
                    target_space = cn
                else:
                    continue
            else:
                target_space = host_space
        else:
            # РЎС‚СЂР°С‚РµРіРёСЏ 2: С‚РѕС‡РєР° РЅРµ РїРѕРїР°Р»Р° РЅРё РІ РѕРґРЅРѕ РїСЂРѕСЃС‚СЂР°РЅСЃС‚РІРѕ вЂ”
            # РёС‰РµРј space, С‡СЊРµР№ РіСЂР°РЅРёС†С‹ РІРёС‚СЂР°Р¶ СЂРµР°Р»СЊРЅРѕ РєР°СЃР°РµС‚СЃСЏ.
            # РџСЂРµС„РёР»СЊС‚СЂ РїРѕ bbox: РїСЂРѕРІРµСЂСЏРµРј С‚РѕР»СЊРєРѕ РїСЂРѕСЃС‚СЂР°РЅСЃС‚РІР°, Сѓ РєРѕС‚РѕСЂС‹С…
            # bbox СЃРѕРґРµСЂР¶РёС‚ СЃРµСЂРµРґРёРЅСѓ РІРёС‚СЂР°Р¶Р° (СЃ РґРѕРїСѓСЃРєРѕРј). Р­С‚Рѕ СЂРµР¶РµС‚
            # РїРµСЂРµР±РѕСЂ СЃ С‚С‹СЃСЏС‡ РґРѕ РґРµСЃСЏС‚РєРѕРІ.
            for sp in spatial_elements:
                if is_unconditioned_space(sp):
                    continue
                bbox = _space_bbox(sp)
                if not _point_in_bbox(mid, bbox, tol_ft=3.3):
                    continue
                if curtain_wall_touches_space(wall, transform, sp):
                    target_space = sp
                    break
            if target_space is None:
                continue

        # РљР›Р®Р§Р•Р’РђРЇ РџР РћР’Р•Р РљРђ: РµСЃР»Рё Сѓ РїРѕРјРµС‰РµРЅРёСЏ СѓР¶Рµ РµСЃС‚СЊ СЃРІРѕРё РІРёС‚СЂР°Р¶Рё,
        # Р·РЅР°С‡РёС‚ СЃС‚Р°РЅРґР°СЂС‚РЅС‹Р№ РѕР±С…РѕРґ СЃРїСЂР°РІРёР»СЃСЏ СЃР°Рј вЂ” orphan РЅРµ Р»РµР·РµС‚.
        target_sid = text(element_id(target_space))
        if target_sid in spaces_with_glazing:
            continue

        seen_in_this_pass.add(key)
        # РџР»РѕС‰Р°РґСЊ Рё РїР°СЂР°РјРµС‚СЂС‹
        area_str = element_area(wall)
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
        # РўРѕР»С‰РёРЅР° Сѓ РІРёС‚СЂР°Р¶Р° РѕР±С‹С‡РЅРѕ 0, РѕСЃС‚Р°РІР»СЏРµРј РїСѓСЃС‚Рѕ
        try:
            thickness = wall.get_Parameter(BuiltInParameter.WALL_ATTR_WIDTH_PARAM)
            thickness_val = parameter_value(thickness) if thickness else ""
        except Exception:
            thickness_val = ""
        # Р”Р»РёРЅР° Рё РѕСЂРёРµРЅС‚Р°С†РёСЏ
        try:
            length_m = wall.Location.Curve.Length * 0.3048
        except Exception:
            length_m = ""
        orient = wall_orientation_deg(wall)

        rows.append([
            element_id(target_space),
            builtin(target_space, BuiltInParameter.ROOM_NUMBER),
            builtin(target_space, BuiltInParameter.ROOM_NAME),
            level_name(target_space),
            "external_wall",
            "yes",                 # РІРёС‚СЂР°Р¶ вЂ” РІСЃРµРіРґР° РЅР°СЂСѓР¶РЅС‹Р№
            eid,
            link_name,
            category_name(wall),
            family,
            type_n,
            level_name(wall),
            round(length_m, 3) if isinstance(length_m, float) else "",
            element_height_m(target_space),
            area_str,
            area_str,
            thickness_val,
            "curtain (orphan)",   # РїРѕРјРµС‡Р°РµРј РёСЃС‚РѕС‡РЅРёРє РґР»СЏ РѕС‚Р»Р°РґРєРё
            u_val,
            "",
            1,                     # bsc=1 (С‚СЂР°РєС‚СѓРµРј РєР°Рє В«СЂРµР°Р»СЊРЅРѕ РЅР°СЂСѓР¶РЅС‹Р№В»)
            orient,
        ])
    return rows


# ----------- РѕСЃРЅРѕРІРЅРѕР№ Р·Р°РїСѓСЃРє -----------

output_path = r"D:\HVAC\spaces.csv"
output_table = "all"
collect_orphans = True   # IN[2] вЂ” "fast"/"false"/"no" С‡С‚РѕР±С‹ РІС‹РєР»СЋС‡РёС‚СЊ

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
# РџСЂРѕРіСЂРµРІР°РµРј bbox-РєСЌС€ РѕРґРЅРёРј РїСЂРѕС…РѕРґРѕРј вЂ” РїРѕС‚РѕРј IsPointInSpace
# РѕС‚СЃРµРєР°РµС‚СЃСЏ Р±РµР· РґРѕСЂРѕРіРёС… РіРµРѕРјРµС‚СЂРёС‡РµСЃРєРёС… РІС‹Р·РѕРІРѕРІ.
for _sp in spatial_elements:
    _space_bbox(_sp)
boundary_counts = shared_boundary_map(spatial_elements)

# Р Р°СЃС€РёСЂРµРЅРЅС‹Р№ Р·Р°РіРѕР»РѕРІРѕРє thermal_all.csv СЃ РЅРѕРІРѕР№ РєРѕР»РѕРЅРєРѕР№ orientation_deg
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
    "orientation_deg",   # РќРћР’РђРЇ РљРћР›РћРќРљРђ
]

SPACES_HEADER = [
    "id", "category", "number", "name", "level", "area", "volume",
    "height", "zone", "heating_load", "cooling_load",
]

def _seen_set(rows):
    """РњРЅРѕР¶РµСЃС‚РІРѕ (link_name, element_id) РґР»СЏ СЃС‚СЂРѕРє, СѓР¶Рµ РІС‹РІРµРґРµРЅРЅС‹С…
    С‡РµСЂРµР· СЃС‚Р°РЅРґР°СЂС‚РЅС‹Рµ РіСЂР°РЅРёС†С‹ РїРѕРјРµС‰РµРЅРёР№."""
    seen = set()
    for r in rows[1:]:  # Р±РµР· Р·Р°РіРѕР»РѕРІРєР°
        try:
            link = text(r[7])   # link_model
            eid = text(r[6])    # element_id
            seen.add((link, eid))
        except Exception:
            pass
    return seen


def _spaces_with_existing_glazing(rows):
    """РњРЅРѕР¶РµСЃС‚РІРѕ space_id, Сѓ РєРѕС‚РѕСЂС‹С… РЈР–Р• РµСЃС‚СЊ РІРёС‚СЂР°Р¶Рё (Curtain Walls)
    РІ СЃС‚Р°РЅРґР°СЂС‚РЅРѕР№ РІС‹РіСЂСѓР·РєРµ. Orphan-СЃР±РѕСЂС‰РёРє РЅРµ РґРѕР»Р¶РµРЅ РґРѕР±Р°РІР»СЏС‚СЊ РёРј
    РґРѕРїРѕР»РЅРёС‚РµР»СЊРЅС‹Рµ РІРёС‚СЂР°Р¶Рё вЂ” Сѓ РЅРёС… СЃРІРѕС‘ РѕСЃС‚РµРєР»РµРЅРёРµ СѓР¶Рµ СѓС‡С‚РµРЅРѕ.
    РћРїСЂРµРґРµР»СЏРµРј В«РІРёС‚СЂР°Р¶В» РїРѕ СЃРµРјРµР№СЃС‚РІСѓ: СЃРѕРґРµСЂР¶РёС‚ 'РІРёС‚СЂР°Р¶'/'curtain'/'balcony'.
    """
    result = set()
    for r in rows[1:]:
        try:
            sid = text(r[0])               # space_id
            family = text(r[9]).lower()    # family
            type_n = text(r[10]).lower()   # type
            combined = family + " " + type_n
            for kw in ("РІРёС‚СЂР°Р¶", "curtain", "balcony", "chr_balcony"):
                # РўРћР›Р¬РљРћ С„Р°СЃР°РґРЅС‹Р№ РІРёС‚СЂР°Р¶ (bsc=1) СЃС‡РёС‚Р°РµС‚СЃСЏ В«РѕСЃС‚РµРєР»РµРЅРёРµРј СѓР¶Рµ
                # РµСЃС‚СЊВ». Р’РёС‚СЂР°Р¶ СЃ bsc>=2 вЂ” РїРµСЂРµРіРѕСЂРѕРґРєР° РјРµР¶РґСѓ РєРѕРјРЅР°С‚Р°РјРё
                # (РЅР°РїСЂ. 602.a/602.b): РѕРЅ РќР• РґРѕР»Р¶РµРЅ Р±Р»РѕРєРёСЂРѕРІР°С‚СЊ РїСЂРёРІСЏР·РєСѓ
                # РЅР°СЃС‚РѕСЏС‰РµРіРѕ С„Р°СЃР°РґР° orphan-СЃР±РѕСЂС‰РёРєРѕРј.
                if kw in combined and text(r[20]).strip() == "1":
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

    # Р”РѕРїРѕР»РЅРёС‚РµР»СЊРЅС‹Р№ РїСЂРѕС…РѕРґ: РІРёС‚СЂР°Р¶Рё Р±РµР· Room Bounding (РѕРїС†РёРѕРЅР°Р»СЊРЅРѕ).
    # РџРѕРјРµС‰РµРЅРёСЏ, Сѓ РєРѕС‚РѕСЂС‹С… СѓР¶Рµ РµСЃС‚СЊ СЃРІРѕРё РІРёС‚СЂР°Р¶Рё РІ СЃС‚Р°РЅРґР°СЂС‚РЅРѕР№ РІС‹РіСЂСѓР·РєРµ,
    # РґРѕРїРѕР»РЅРёС‚РµР»СЊРЅС‹С… РЅРµ РїРѕР»СѓС‡Р°СЋС‚.
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
    # Р”РѕР±Р°РІР»СЏРµРј В«orphanВ» РІРёС‚СЂР°Р¶Рё С‚РѕР»СЊРєРѕ РґР»СЏ РїРѕР»РЅРѕР№ РІС‹РіСЂСѓР·РєРё Рё РµСЃР»Рё РЅРµ fast
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
