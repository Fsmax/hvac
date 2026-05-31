"""
Аудит остекления по уровням — РАСПРЕДЕЛЕНИЕ ПО Z-КООРДИНАТЕ.
Узел Python Script (CPython3) в Dynamo.

Зачем: навесные стены в Revit моделируются многоэтажными сегментами,
и LevelId хоста показывает только базу. Поэтому панели «прилипают» к
нижнему этажу. Здесь каждая панель/окно относится к уровню по Z центра
геометрии, а стены прорезаются по высотам уровней.

ВХОДЫ:
    IN[0] : str — папка для CSV ("D:/HVAC")
    IN[1] : str — режим: "window" | "panel" | "wall" | "all"
    IN[2] : str — (опц.) подстрока имени линка для фильтра

ВЫХОД:
    OUT   : [csv_path, status_text, rows]
"""

import os, csv, traceback

import clr
clr.AddReference("RevitServices")
clr.AddReference("RevitAPI")

from RevitServices.Persistence import DocumentManager
from Autodesk.Revit.DB import (
    FilteredElementCollector, BuiltInCategory, BuiltInParameter,
    ElementId, Wall, UnitUtils, RevitLinkInstance, Options, XYZ
)

try:
    from Autodesk.Revit.DB import SpecTypeId
    _USE_SPEC = True
except Exception:
    from Autodesk.Revit.DB import DisplayUnitType
    _USE_SPEC = False

host_doc = DocumentManager.Instance.CurrentDBDocument

log_lines = []
def log(msg): log_lines.append(str(msg))

# --- inputs ---
def safe_in(i, default=""):
    try:
        if len(IN) > i and IN[i] is not None:
            return IN[i]
    except Exception:
        pass
    return default

out_folder  = safe_in(0, "")
mode        = (str(safe_in(1, "all")) or "all").strip().lower()
link_filter = (str(safe_in(2, "")) or "").strip().lower()
if mode not in {"window", "panel", "wall", "all"}:
    mode = "all"

log("host doc      = {0}".format(getattr(host_doc, "Title", "?")))
log("IN[0] folder  = {0!r}".format(out_folder))
log("IN[1] mode    = {0}".format(mode))
log("IN[2] linkflt = {0!r}".format(link_filter))

# --- helpers ---
def eid(element_id):
    try:    return element_id.Value
    except: return element_id.IntegerValue

def to_m2(v):
    try:
        if _USE_SPEC:
            return UnitUtils.ConvertFromInternalUnits(v, SpecTypeId.Area)
        return UnitUtils.ConvertFromInternalUnits(v, DisplayUnitType.DUT_SQUARE_METERS)
    except Exception:
        return v * 0.092903

def to_m(v):
    try:
        if _USE_SPEC:
            return UnitUtils.ConvertFromInternalUnits(v, SpecTypeId.Length)
        return UnitUtils.ConvertFromInternalUnits(v, DisplayUnitType.DUT_METERS)
    except Exception:
        return v * 0.3048

def get_param_double(el, bip):
    try:
        p = el.get_Parameter(bip)
        if p and p.HasValue:
            return p.AsDouble()
    except Exception:
        pass
    return 0.0

def type_name(d, el):
    try:
        sym = d.GetElement(el.GetTypeId())
        if sym is None: return ""
        n = sym.get_Parameter(BuiltInParameter.SYMBOL_NAME_PARAM)
        if n and n.HasValue:
            v = n.AsString()
            if v: return v
        return getattr(sym, "Name", "") or ""
    except Exception:
        return ""

GEOM_OPTS = Options()
GEOM_OPTS.ComputeReferences = False
GEOM_OPTS.IncludeNonVisibleObjects = False

def bbox_z_range(el):
    """(z_min, z_max) bbox элемента в координатах его документа. None при неудаче."""
    try:
        bb = el.get_BoundingBox(None)
        if bb is None:
            return None
        return (bb.Min.Z, bb.Max.Z)
    except Exception:
        return None

def bbox_center_z(el):
    r = bbox_z_range(el)
    if r is None:
        # fallback: точка размещения
        try:
            loc = el.Location
            if loc is not None and hasattr(loc, "Point") and loc.Point is not None:
                return loc.Point.Z
        except Exception:
            pass
        return None
    return 0.5 * (r[0] + r[1])

# --- собрать линки ---
target_docs = []
link_instances = list(FilteredElementCollector(host_doc).OfClass(RevitLinkInstance))
log("RevitLinkInstance в host: {0}".format(len(link_instances)))

seen = set()
for li in link_instances:
    try:
        ld = li.GetLinkDocument()
        if ld is None:
            log("  • '{0}' — НЕ ЗАГРУЖЕН".format(li.Name)); continue
        key = ld.PathName or ld.Title
        if key in seen: continue
        seen.add(key)
        if link_filter and (link_filter not in (ld.Title or "").lower()
                            and link_filter not in (li.Name or "").lower()):
            log("  • skip '{0}'".format(ld.Title)); continue
        target_docs.append((ld.Title or li.Name, ld))
        log("  • '{0}' добавлен".format(ld.Title))
    except Exception as ex:
        log("  • ошибка линка: {0}".format(ex))

if not link_filter:
    target_docs.insert(0, ("[HOST] " + (host_doc.Title or ""), host_doc))

log("документов для аудита: {0}".format(len(target_docs)))

# --- утилита: распределение Z по уровням документа ---
def level_z(l):
    """ProjectElevation совпадает с системой координат геометрии (internal),
    в отличие от Elevation, которое может быть в shared coords."""
    try:
        return l.ProjectElevation
    except Exception:
        return l.Elevation

def build_level_index(d):
    """
    Возвращает (sorted_levels, finder), где
      sorted_levels = [(elev_internal, Level), ...] по возрастанию,
      finder(z) → Level, чей elev <= z < следующий уровень
                   (если z ниже всех — самый нижний, выше всех — самый верхний)
    """
    levels = list(FilteredElementCollector(d)
                  .OfCategory(BuiltInCategory.OST_Levels)
                  .WhereElementIsNotElementType())
    pairs = sorted([(level_z(l), l) for l in levels], key=lambda x: x[0])
    if not pairs:
        return [], (lambda z: None)

    def finder(z):
        if z is None:
            return pairs[0][1]
        if z < pairs[0][0]:
            return pairs[0][1]
        for i in range(len(pairs) - 1):
            if pairs[i][0] <= z < pairs[i + 1][0]:
                return pairs[i][1]
        return pairs[-1][1]
    return pairs, finder

# --- aggregate ---
want_win   = mode in ("window", "all")
want_panel = mode in ("panel",  "all")
want_wall  = mode in ("wall",   "all")

per_key = {}     # (doc_label, level_id) -> bucket
level_lookup = {}  # (doc_label, level_id) -> Level

def bucket(key):
    if key not in per_key:
        per_key[key] = {"win_cnt": 0, "win_area": 0.0,
                        "panel_cnt": 0, "panel_area": 0.0,
                        "wall_cnt": 0, "wall_area": 0.0, "types": {}}
    return per_key[key]

total_err = 0

for label, d in target_docs:
    pairs, find_level = build_level_index(d)
    for _, l in pairs:
        level_lookup[(label, eid(l.Id))] = l

    windows = list(FilteredElementCollector(d)
                   .OfCategory(BuiltInCategory.OST_Windows)
                   .WhereElementIsNotElementType()) if want_win else []
    panels = list(FilteredElementCollector(d)
                  .OfCategory(BuiltInCategory.OST_CurtainWallPanels)
                  .WhereElementIsNotElementType()) if want_panel else []
    walls = list(FilteredElementCollector(d)
                 .OfClass(Wall)
                 .WhereElementIsNotElementType()) if want_wall else []

    log("[{0}] levels={1} (Zrange {2:.1f}..{3:.1f} m), windows={4}, panels={5}, walls={6}".format(
        label, len(pairs),
        to_m(pairs[0][0]) if pairs else 0.0,
        to_m(pairs[-1][0]) if pairs else 0.0,
        len(windows), len(panels), len(walls)))

    # --- окна: по Z центра ---
    for w in windows:
        try:
            zc = bbox_center_z(w)
            lvl = find_level(zc) if pairs else None
            if lvl is None: continue
            key = (label, eid(lvl.Id))
            b = bucket(key)
            b["win_cnt"] += 1
            a = get_param_double(w, BuiltInParameter.HOST_AREA_COMPUTED)
            if a == 0.0:
                sym = d.GetElement(w.GetTypeId())
                if sym is not None:
                    wd = sym.get_Parameter(BuiltInParameter.WINDOW_WIDTH) \
                      or sym.get_Parameter(BuiltInParameter.FAMILY_WIDTH_PARAM)
                    ht = sym.get_Parameter(BuiltInParameter.WINDOW_HEIGHT) \
                      or sym.get_Parameter(BuiltInParameter.FAMILY_HEIGHT_PARAM)
                    if wd and ht and wd.HasValue and ht.HasValue:
                        a = wd.AsDouble() * ht.AsDouble()
            b["win_area"] += to_m2(a)
            tn = type_name(d, w) or "?"
            b["types"][tn] = b["types"].get(tn, 0) + 1
        except Exception:
            total_err += 1

    # --- панели: по Z центра ---
    for p in panels:
        try:
            a = get_param_double(p, BuiltInParameter.HOST_AREA_COMPUTED)
            if a <= 0: continue
            tn = (type_name(d, p) or "").lower()
            is_glazed = any(k in tn for k in ("glaz", "glass", "стек"))
            if not (is_glazed or "panel" in tn):
                continue
            zc = bbox_center_z(p)
            lvl = find_level(zc) if pairs else None
            if lvl is None: continue
            key = (label, eid(lvl.Id))
            b = bucket(key)
            b["panel_cnt"] += 1
            b["panel_area"] += to_m2(a)
        except Exception:
            total_err += 1

    # --- стены: прорезаем по уровням ---
    # площадь стены распределяется пропорционально перекрытию [z_min..z_max] стены с
    # интервалом [elev_i..elev_{i+1}). Длина (а значит и площадь) считается прямой пропорцией.
    if pairs:
        for wall in walls:
            try:
                wt = d.GetElement(wall.GetTypeId())
                fn = wt.get_Parameter(BuiltInParameter.FUNCTION_PARAM)
                if fn and fn.AsInteger() != 1:  # только Exterior
                    continue
                r = bbox_z_range(wall)
                if r is None: continue
                z0, z1 = r
                if z1 <= z0: continue
                area = to_m2(get_param_double(wall, BuiltInParameter.HOST_AREA_COMPUTED))
                if area <= 0: continue
                total_h = z1 - z0

                # пройти по парам уровней
                for i in range(len(pairs)):
                    e_i = pairs[i][0]
                    e_next = pairs[i + 1][0] if i + 1 < len(pairs) else float("inf")
                    overlap = max(0.0, min(z1, e_next) - max(z0, e_i))
                    if overlap <= 0: continue
                    frac = overlap / total_h
                    key = (label, eid(pairs[i][1].Id))
                    b = bucket(key)
                    b["wall_area"] += area * frac
                    # счётчик стен — только тому уровню, где находится низ стены
                    if e_i <= z0 < e_next:
                        b["wall_cnt"] += 1
            except Exception:
                total_err += 1

log("buckets: {0}, element errors: {1}".format(len(per_key), total_err))

# --- build rows ---
header = ["Doc", "Level", "Elev_m", "Windows", "Panels_glazed",
          "Glass_m2", "Ext_Walls_cnt", "Wall_m2", "WWR_%", "Window_Types"]

items = []
for (label, lid), b in per_key.items():
    lvl = level_lookup.get((label, lid))
    name = lvl.Name if lvl else "<no level id={0}>".format(lid)
    elev = to_m(lvl.Elevation) if lvl else 0.0
    items.append((label, elev, name, b))
items.sort(key=lambda x: (x[0], x[1]))

rows = [header]
for label, elev, name, b in items:
    glass = b["win_area"] + b["panel_area"]
    wwr = (glass / b["wall_area"] * 100.0) if b["wall_area"] > 0 else 0.0
    types_str = "; ".join("{0}x{1}".format(v, k) for k, v in
                          sorted(b["types"].items(), key=lambda x: -x[1]))
    rows.append([label, name, round(elev, 2),
                 b["win_cnt"], b["panel_cnt"], round(glass, 1),
                 b["wall_cnt"], round(b["wall_area"], 1),
                 round(wwr, 1), types_str])

# diff vs L11
ref = next((r for r in rows[1:] if str(r[1]).startswith("L11")), None)
if ref:
    rows[0].append("dGlass_vs_L11_%")
    rg = ref[5] or 1e-9
    for r in rows[1:]:
        r.append(round((r[5] - rg) / rg * 100.0, 1))

# --- сводка по всем линкам на уровень (по имени уровня) ---
# чтобы напрямую сопоставлять с теплотехнической таблицей
combined = {}
for label, elev, name, b in items:
    if name not in combined:
        combined[name] = {"elev": elev, "win": 0, "pan": 0, "glass": 0.0,
                          "wall": 0.0, "docs": []}
    c = combined[name]
    c["win"] += b["win_cnt"]
    c["pan"] += b["panel_cnt"]
    c["glass"] += b["win_area"] + b["panel_area"]
    c["wall"] += b["wall_area"]
    c["docs"].append(label)

combined_rows = [["[SUMMARY] Level", "Elev_m", "Σ Windows", "Σ Panels",
                  "Σ Glass_m2", "Σ Wall_m2", "WWR_%", "Docs"]]
for name, c in sorted(combined.items(), key=lambda x: x[1]["elev"]):
    wwr = (c["glass"] / c["wall"] * 100.0) if c["wall"] > 0 else 0.0
    combined_rows.append([name, round(c["elev"], 2),
                          c["win"], c["pan"],
                          round(c["glass"], 1), round(c["wall"], 1),
                          round(wwr, 1), "; ".join(sorted(set(c["docs"])))])

# --- write csv ---
csv_path = ""
write_err = ""
try:
    folder = out_folder or os.path.expanduser("~")
    if not os.path.isdir(folder):
        os.makedirs(folder)
    csv_path = os.path.join(folder, "glazing_audit_{0}.csv".format(mode))
    with open(csv_path, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f, delimiter=";")
        w.writerow(["# DIAGNOSTIC"])
        for line in log_lines:
            w.writerow([line])
        w.writerow([])
        w.writerow(["# SUMMARY (агрегат по всем линкам)"])
        w.writerows(combined_rows)
        w.writerow([])
        w.writerow(["# DATA (по каждому линку)"])
        w.writerows(rows)
except Exception:
    write_err = traceback.format_exc()

status = "\n".join(log_lines)
if write_err:
    status += "\n\nWRITE ERROR:\n" + write_err

OUT = [csv_path or "(no path)", status, rows]
