# -*- coding: utf-8 -*-
"""Живой мост с Revit через сокет-плагин Revit MCP (127.0.0.1:8080).

Заменяет ручной цикл «Dynamo → CSV → Dynamo»: импорт геометрии
(spaces.csv + thermal_all.csv) и запись результатов в параметры
Spaces/Rooms выполняются прямо из программы, пока модель открыта.

Протокол: JSON-RPC 2.0 поверх TCP. Команда `send_code_to_revit`
компилирует и исполняет C# (тело метода
``Execute(Document document, object[] parameters)``) внутри Revit.
Доступные usings: System, System.Linq, Autodesk.Revit.DB,
Autodesk.Revit.UI, System.Collections.Generic; остальное (System.IO,
Newtonsoft, Mechanical.Space) — через полные имена.

Требования к Revit:
  • Revit открыт в полном режиме с целевой моделью;
  • включён переключатель «Revit MCP Switch» (плагин слушает :8080).

C#-выгрузка — порт Dynamo-скрипта revit_dynamo_hvac_write_csv.py
(колонки CSV идентичны, включая orientation_deg и orphan-витражи).
C#-запись — порт hvac-mcp/revit_writeback.py (Фаза 2, обкатан).
"""

from __future__ import annotations

import json
import socket
from typing import List, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from hvac.project import HVACProject

REVIT_HOST = "127.0.0.1"
REVIT_PORT = 8080


class RevitNotConnected(RuntimeError):
    """Revit закрыт или переключатель Revit MCP Switch выключен."""


def call(method: str, params: Optional[dict] = None, timeout: float = 75.0):
    """Низкоуровневый JSON-RPC вызов к плагину Revit."""
    try:
        s = socket.create_connection((REVIT_HOST, REVIT_PORT), timeout=timeout)
    except OSError as e:
        raise RevitNotConnected(
            f"Не удалось подключиться к Revit на {REVIT_HOST}:{REVIT_PORT}. "
            f"Открыт ли Revit и включён ли переключатель 'Revit MCP Switch'? ({e})"
        )
    try:
        s.settimeout(timeout)
        req = {"jsonrpc": "2.0", "id": "1",
               "method": method, "params": params or {}}
        s.sendall(json.dumps(req, ensure_ascii=False).encode("utf-8"))
        # Плагин пишет ответ БЕЗ разделителя и не закрывает сокет —
        # читаем чанками и пытаемся распарсить накопленное (ответ —
        # ровно один JSON-объект).
        buf = b""
        resp = None
        while True:
            chunk = s.recv(65536)
            if not chunk:
                break
            buf += chunk
            try:
                resp = json.loads(buf.decode("utf-8"))
                break
            except json.JSONDecodeError:
                continue
    finally:
        s.close()
    if resp is None:
        resp = json.loads(buf.decode("utf-8", "replace").strip())
    if "error" in resp:
        raise RuntimeError(resp["error"].get("message", str(resp["error"])))
    return resp.get("result")


def send_code(code: str, parameters: Optional[List[str]] = None,
              transaction_mode: str = "auto", timeout: float = 120.0):
    """Исполнить C# внутри Revit и вернуть разобранный результат."""
    res = call("send_code_to_revit",
               {"code": code, "parameters": parameters or [],
                "transactionMode": transaction_mode},
               timeout=timeout)
    if isinstance(res, dict):
        if not res.get("success", False):
            raise RuntimeError(
                "Revit code error: " + str(res.get("errorMessage", "")))
        raw = res.get("result")
        if isinstance(raw, str):
            try:
                return json.loads(raw)
            except Exception:
                return raw
        return raw
    return res


def ping(timeout: float = 10.0) -> bool:
    """Быстрая проверка живости моста (read-only вызов)."""
    try:
        send_code("return document.Title;",
                  transaction_mode="none", timeout=timeout)
        return True
    except Exception:
        return False


# ============================================================================
# C#: выгрузка spaces.csv + thermal_all.csv (порт Dynamo-скрипта, Фаза 3)
# ============================================================================
# parameters[0] = папка вывода; parameters[1] = "1"/"0" — orphan-витражи.
# Возвращает { spaces_rows, thermal_rows, orphan_rows, source,
#              spaces_csv, thermal_csv }.

EXPORT_CS = r'''
string folder = (string)parameters[0];
bool collectOrphans = parameters.Length < 2 || ((string)parameters[1] != "0");
var CI = System.Globalization.CultureInfo.InvariantCulture;
const double FT_M = 0.3048;

// ---------- базовые помощники ----------
string Num(double v, int dec) {
    return Math.Round(v, dec).ToString("0.0###", CI);
}
Parameter BPm(Element e, BuiltInParameter bp) {
    try { return e.get_Parameter(bp); } catch { return null; }
}
string PVal(Parameter p) {
    if (p == null) return "";
    try {
        if (p.StorageType == StorageType.String) return p.AsString() ?? "";
        if (p.StorageType == StorageType.Double) {
            var vs = p.AsValueString();
            return vs ?? p.AsDouble().ToString(CI);
        }
        if (p.StorageType == StorageType.Integer) {
            var vs = p.AsValueString();
            return vs ?? p.AsInteger().ToString(CI);
        }
    } catch { }
    return "";
}
string BPS(Element e, BuiltInParameter bp) { return PVal(BPm(e, bp)); }
double BPD(Element e, BuiltInParameter bp) {
    var p = BPm(e, bp);
    if (p != null && p.StorageType == StorageType.Double) {
        try { return p.AsDouble(); } catch { }
    }
    return 0.0;
}
string Lookup(Element e, string[] names) {
    if (e == null) return "";
    foreach (var n in names) {
        Parameter p = null;
        try { p = e.LookupParameter(n); } catch { }
        var v = PVal(p);
        if (v != "") return v;
    }
    return "";
}
string LevelName(Element e) {
    try {
        var lv = e.Document.GetElement(e.LevelId);
        if (lv != null) return lv.Name ?? "";
    } catch { }
    return BPS(e, BuiltInParameter.LEVEL_PARAM);
}
string CatName(Element e) {
    try { return e.Category != null ? (e.Category.Name ?? "") : ""; }
    catch { return ""; }
}
bool IsCat(Element e, BuiltInCategory c) {
    try { return e.Category != null && e.Category.Id.Value == (long)(int)c; }
    catch { return false; }
}

// ---------- кэш характеристик типа ----------
// [0]=family [1]=type [2]=function [3]=u-value [4]=толщина,мм [5]=curtain
var typeCache = new Dictionary<string, string[]>();
string[] TInfo(Element el) {
    var blank = new[]{"","","","","",""};
    if (el == null) return blank;
    string key;
    Document d;
    ElementId tid;
    try {
        d = el.Document;
        tid = el.GetTypeId();
        key = (d.PathName ?? "") + "|" + tid.Value.ToString(CI);
    } catch { return blank; }
    string[] info;
    if (typeCache.TryGetValue(key, out info)) return info;
    info = new[]{"","","","","",""};
    try {
        var te = d.GetElement(tid) as ElementType;
        if (te != null) {
            try { info[0] = te.FamilyName ?? ""; } catch { }
            try { info[1] = te.Name ?? ""; } catch { }
            info[2] = BPS(te, BuiltInParameter.FUNCTION_PARAM);
            info[3] = Lookup(te, new[]{"Heat Transfer Coefficient",
                "Thermal Transmittance", "U-Value", "U Value", "U"});
            var wp = BPm(te, BuiltInParameter.WALL_ATTR_WIDTH_PARAM);
            if (wp != null && wp.StorageType == StorageType.Double)
                info[4] = Num(wp.AsDouble() * 304.8, 1);
            bool curtain = false;
            var wt = te as WallType;
            if (wt != null) { try { curtain = wt.Kind == WallKind.Curtain; } catch { } }
            if (!curtain) {
                var full = (info[0] + " " + info[1]).ToLowerInvariant();
                if (full.Contains("curtain") || full.Contains("витраж") ||
                    full.Contains("стекл") || full.Contains("glaz")) curtain = true;
            }
            info[5] = curtain ? "1" : "";
        }
    } catch { }
    typeCache[key] = info;
    return info;
}

// ---------- азимуты ----------
string Az(double x, double y) {
    if (Math.Abs(x) < 1e-9 && Math.Abs(y) < 1e-9) return "";
    double a = Math.Atan2(x, y) * 180.0 / Math.PI;
    if (a < 0) a += 360.0;
    return Math.Round(a, 1).ToString("0.0", CI);
}
string WallAz(Element el) {
    var w = el as Wall;
    if (w == null) return "";
    try { var n = w.Orientation; if (n != null) return Az(n.X, n.Y); } catch { }
    try {
        var lc = w.Location as LocationCurve;
        if (lc != null) {
            var c = lc.Curve;
            XYZ dvec = null;
            var ln = c as Line;
            if (ln != null) dvec = ln.Direction;
            else {
                double p0 = c.GetEndParameter(0), p1 = c.GetEndParameter(1);
                dvec = c.ComputeDerivatives((p0 + p1) * 0.5, true).BasisX;
            }
            if (dvec != null) {
                double nx = dvec.Y, ny = -dvec.X;
                if (w.Flipped) { nx = -nx; ny = -ny; }
                return Az(nx, ny);
            }
        }
    } catch { }
    return "";
}
string SegAz(BoundarySegment seg) {
    try {
        var ln = seg.GetCurve() as Line;
        if (ln == null) return "";
        var dvec = ln.Direction;
        return Az(dvec.Y, -dvec.X);
    } catch { return ""; }
}

// ---------- разрешение элемента границы (включая связанные модели) ----------
System.Tuple<Element, string> BElem(BoundarySegment seg) {
    Element host = null;
    try {
        if (seg.ElementId != ElementId.InvalidElementId)
            host = document.GetElement(seg.ElementId);
    } catch { }
    var li = host as RevitLinkInstance;
    if (li != null) {
        try {
            var ld = li.GetLinkDocument();
            var lid = seg.LinkElementId;
            if (ld != null && lid != ElementId.InvalidElementId) {
                var le = ld.GetElement(lid);
                if (le != null)
                    return System.Tuple.Create<Element, string>(le, li.Name ?? "");
            }
        } catch { }
    }
    return System.Tuple.Create<Element, string>(host, "");
}

// ---------- неотапливаемые пространства (балконы/террасы/шахты) ----------
var uncondCache = new Dictionary<long, bool>();
bool IsUncond(SpatialElement sp) {
    long sid;
    try { sid = sp.Id.Value; } catch { sid = -1; }
    bool r;
    if (sid >= 0 && uncondCache.TryGetValue(sid, out r)) return r;
    string number = (BPS(sp, BuiltInParameter.ROOM_NUMBER) ?? "").Trim();
    string name = (BPS(sp, BuiltInParameter.ROOM_NAME) ?? "").Trim();
    r = false;
    var nu = number.ToUpperInvariant();
    foreach (var pfx in new[]{"OFC-", "BAL-", "TER-", "SHAFT", "ШАХТ"})
        if (nu.StartsWith(pfx)) { r = true; break; }
    if (!r) {
        var full = (number + " " + name).ToLowerInvariant();
        foreach (var kw in new[]{"балкон", "терраса", "лоджия", "balcony",
                                  "terrace", "loggia", "shaft", "open air"})
            if (full.Contains(kw)) { r = true; break; }
    }
    if (sid >= 0) uncondCache[sid] = r;
    return r;
}

// ---------- сбор пространств ----------
var spatial = new List<SpatialElement>();
string source = "Spaces (MEP)";
foreach (Element e in new FilteredElementCollector(document)
        .OfCategory(BuiltInCategory.OST_MEPSpaces).WhereElementIsNotElementType()) {
    var se = e as SpatialElement;
    if (se != null && BPD(se, BuiltInParameter.ROOM_AREA) > 1e-9) spatial.Add(se);
}
if (spatial.Count == 0) {
    source = "Rooms (Architecture)";
    foreach (Element e in new FilteredElementCollector(document)
            .OfCategory(BuiltInCategory.OST_Rooms).WhereElementIsNotElementType()) {
        var se = e as SpatialElement;
        if (se != null && BPD(se, BuiltInParameter.ROOM_AREA) > 1e-9) spatial.Add(se);
    }
}

string HeightM(SpatialElement sp) {
    double h = BPD(sp, BuiltInParameter.ROOM_HEIGHT);
    if (h <= 0) {
        try {
            var s2 = sp as Autodesk.Revit.DB.Mechanical.Space;
            if (s2 != null) h = s2.UnboundedHeight;
        } catch { }
    }
    if (h <= 0) {
        try {
            var r2 = sp as Autodesk.Revit.DB.Architecture.Room;
            if (r2 != null) h = r2.UnboundedHeight;
        } catch { }
    }
    if (h <= 0) return "";
    return Num(h * FT_M, 3);
}

// ---------- bsc: сколько отапливаемых пространств видит каждую границу ----------
var bopt = new SpatialElementBoundaryOptions();
var bndCounts = new Dictionary<string, HashSet<long>>();
foreach (var sp in spatial) {
    if (IsUncond(sp)) continue;
    IList<IList<BoundarySegment>> loops = null;
    try { loops = sp.GetBoundarySegments(bopt); } catch { }
    if (loops == null) continue;
    var seen = new HashSet<string>();
    foreach (var loop in loops) foreach (var seg in loop) {
        var t = BElem(seg);
        if (t.Item1 == null) continue;
        seen.Add(t.Item2 + "|" + t.Item1.Id.Value.ToString(CI));
    }
    long spid = sp.Id.Value;
    foreach (var k in seen) {
        HashSet<long> hs;
        if (!bndCounts.TryGetValue(k, out hs)) { hs = new HashSet<long>(); bndCounts[k] = hs; }
        hs.Add(spid);
    }
}

// ---------- CSV ----------
string EscCsv(string s) {
    if (s == null) s = "";
    if (s.IndexOfAny(new[]{',', '"', '\n', '\r'}) >= 0)
        return "\"" + s.Replace("\"", "\"\"") + "\"";
    return s;
}
void WriteCsv(string path, List<string[]> rows) {
    var sb = new System.Text.StringBuilder();
    foreach (var r in rows) {
        for (int i = 0; i < r.Length; i++) {
            if (i > 0) sb.Append(',');
            sb.Append(EscCsv(r[i]));
        }
        sb.Append("\r\n");
    }
    System.IO.File.WriteAllText(path, sb.ToString(), new System.Text.UTF8Encoding(true));
}

// ---------- spaces.csv ----------
var spacesRows = new List<string[]>();
spacesRows.Add(new[]{"id", "category", "number", "name", "level", "area",
                     "volume", "height", "zone", "heating_load", "cooling_load"});
foreach (var sp in spatial) {
    spacesRows.Add(new[]{
        sp.Id.Value.ToString(CI),
        CatName(sp),
        BPS(sp, BuiltInParameter.ROOM_NUMBER),
        BPS(sp, BuiltInParameter.ROOM_NAME),
        LevelName(sp),
        Num(BPD(sp, BuiltInParameter.ROOM_AREA) * FT_M * FT_M, 3),
        Num(BPD(sp, BuiltInParameter.ROOM_VOLUME) * FT_M * FT_M * FT_M, 3),
        HeightM(sp),
        Lookup(sp, new[]{"Zone", "Space Type"}),
        Lookup(sp, new[]{"Heating Load", "Calculated Heating Load", "Design Heating Load"}),
        Lookup(sp, new[]{"Cooling Load", "Calculated Cooling Load", "Design Cooling Load"}),
    });
}

// ---------- thermal_all.csv ----------
var thermalRows = new List<string[]>();
thermalRows.Add(new[]{"space_id", "space_number", "space_name", "space_level",
    "row_type", "is_exterior_wall", "element_id", "link_model", "category",
    "family", "type", "element_level", "boundary_length_m", "space_height_m",
    "approx_area_m2", "element_area", "thickness", "function", "thermal_value",
    "host_element_id", "boundary_space_count", "orientation_deg"});

string ElemAreaM2(Element el) {
    double a = BPD(el, BuiltInParameter.HOST_AREA_COMPUTED);
    if (a > 0) return Num(a * FT_M * FT_M, 3);
    return Lookup(el, new[]{"Area", "Площадь"});
}

var seenKeys = new HashSet<string>();        // (link|eid) из стандартного обхода
var spacesWithGlazing = new HashSet<long>(); // у кого уже есть витражи

foreach (var sp in spatial) {
    IList<IList<BoundarySegment>> loops = null;
    try { loops = sp.GetBoundarySegments(bopt); } catch { }
    if (loops == null) continue;

    string sid = sp.Id.Value.ToString(CI);
    string sNum = BPS(sp, BuiltInParameter.ROOM_NUMBER);
    string sName = BPS(sp, BuiltInParameter.ROOM_NAME);
    string sLevel = LevelName(sp);
    string sHeight = HeightM(sp);
    double sHeightD = 0;
    double.TryParse(sHeight, System.Globalization.NumberStyles.Any, CI, out sHeightD);

    foreach (var loop in loops) foreach (var seg in loop) {
        var t = BElem(seg);
        var el = t.Item1;
        string linkName = t.Item2;
        if (el == null) continue;

        double segLenM = -1;
        try { segLenM = seg.GetCurve().Length * FT_M; } catch { }
        bool isWall = IsCat(el, BuiltInCategory.OST_Walls);
        // corner-артефакты: фрагменты стены короче 0.5 м
        if (isWall && segLenM >= 0 && segLenM < 0.5) continue;

        string key = linkName + "|" + el.Id.Value.ToString(CI);
        int sharedCount = 1;
        HashSet<long> hs;
        if (bndCounts.TryGetValue(key, out hs)) sharedCount = hs.Count;

        var ti = TInfo(el);
        bool isCurtain = isWall && ti[5] == "1";
        bool realExterior;
        if (isWall) {
            if (isCurtain) realExterior = true;
            else if (sharedCount >= 2) realExterior = false;
            else realExterior = true;
        } else realExterior = false;

        string approxArea = "";
        if (segLenM >= 0 && sHeightD > 0) approxArea = Num(segLenM * sHeightD, 3);
        string orient = isWall ? WallAz(el) : "";
        if (orient == "") orient = SegAz(seg);

        seenKeys.Add(key);
        if (isCurtain) {
            var glz = (ti[0] + " " + ti[1]).ToLowerInvariant();
            if (glz.Contains("витраж") || glz.Contains("curtain") ||
                glz.Contains("balcony") || glz.Contains("chr_balcony"))
                spacesWithGlazing.Add(sp.Id.Value);
        }

        thermalRows.Add(new[]{
            sid, sNum, sName, sLevel, "external_wall",
            realExterior ? "yes" : "no",
            el.Id.Value.ToString(CI), linkName, CatName(el), ti[0], ti[1],
            LevelName(el),
            segLenM >= 0 ? Num(segLenM, 3) : "",
            sHeight, approxArea, ElemAreaM2(el), ti[4], ti[2], ti[3],
            "", sharedCount.ToString(CI), orient,
        });

        // Проёмы (окна/двери), вставленные в стену
        var ho = el as HostObject;
        if (ho != null) {
            IList<ElementId> insertIds = null;
            try { insertIds = ho.FindInserts(true, false, false, false); } catch { }
            if (insertIds != null) {
                foreach (var iid in insertIds) {
                    Element ins = null;
                    try { ins = el.Document.GetElement(iid); } catch { }
                    if (ins == null) continue;
                    if (!IsCat(ins, BuiltInCategory.OST_Windows) &&
                        !IsCat(ins, BuiltInCategory.OST_Doors)) continue;
                    var tiIns = TInfo(ins);
                    thermalRows.Add(new[]{
                        sid, sNum, sName, sLevel, "opening",
                        realExterior ? "yes" : "no",
                        ins.Id.Value.ToString(CI), linkName, CatName(ins),
                        tiIns[0], tiIns[1], LevelName(ins),
                        "", "", "", ElemAreaM2(ins), "",
                        "hosted by exterior wall", tiIns[3],
                        el.Id.Value.ToString(CI), sharedCount.ToString(CI), orient,
                    });
                }
            }
        }
    }
}

// ---------- orphan-витражи (вне Room Bounding) ----------
int orphanCount = 0;
if (collectOrphans) {
    // bbox-кэш пространств
    var bboxCache = new Dictionary<long, double[]>();
    double[] SpBbox(SpatialElement sp) {
        long sid2 = sp.Id.Value;
        double[] bb;
        if (bboxCache.TryGetValue(sid2, out bb)) return bb;
        bb = null;
        try {
            var b = sp.get_BoundingBox(null);
            if (b != null) bb = new[]{b.Min.X, b.Min.Y, b.Min.Z, b.Max.X, b.Max.Y, b.Max.Z};
        } catch { }
        bboxCache[sid2] = bb;
        return bb;
    }
    bool InBbox(XYZ p, double[] bb, double tol) {
        if (bb == null || p == null) return true;
        return bb[0] - tol <= p.X && p.X <= bb[3] + tol &&
               bb[1] - tol <= p.Y && p.Y <= bb[4] + tol &&
               bb[2] - tol <= p.Z && p.Z <= bb[5] + tol;
    }
    bool PtInSpace(SpatialElement sp, XYZ p) {
        try {
            var s2 = sp as Autodesk.Revit.DB.Mechanical.Space;
            if (s2 != null) return s2.IsPointInSpace(p);
        } catch { }
        try {
            var r2 = sp as Autodesk.Revit.DB.Architecture.Room;
            if (r2 != null) return r2.IsPointInRoom(p);
        } catch { }
        return false;
    }

    // все витражи: основной документ + связанные (каждый документ один раз)
    var cwalls = new List<object[]>();   // [wall, transform|null, linkName]
    var seenDocs = new HashSet<string>();
    seenDocs.Add(document.PathName ?? "MAIN");
    foreach (Element e in new FilteredElementCollector(document)
            .OfCategory(BuiltInCategory.OST_Walls).WhereElementIsNotElementType()) {
        var w = e as Wall;
        if (w == null) continue;
        var wt = document.GetElement(w.GetTypeId()) as WallType;
        if (wt != null && wt.Kind == WallKind.Curtain)
            cwalls.Add(new object[]{w, null, ""});
    }
    foreach (Element e in new FilteredElementCollector(document).OfClass(typeof(RevitLinkInstance))) {
        var li = e as RevitLinkInstance;
        if (li == null) continue;
        Document ld = null;
        try { ld = li.GetLinkDocument(); } catch { }
        if (ld == null) continue;
        string lp = ld.PathName ?? (li.Name ?? "");
        if (seenDocs.Contains(lp)) continue;
        seenDocs.Add(lp);
        Transform tr = null;
        try { tr = li.GetTotalTransform(); } catch { }
        foreach (Element we in new FilteredElementCollector(ld)
                .OfCategory(BuiltInCategory.OST_Walls).WhereElementIsNotElementType()) {
            var w = we as Wall;
            if (w == null) continue;
            var wt = ld.GetElement(w.GetTypeId()) as WallType;
            if (wt != null && wt.Kind == WallKind.Curtain)
                cwalls.Add(new object[]{w, tr, li.Name ?? ""});
        }
    }

    XYZ MidGlobal(Wall w, Transform tr) {
        try {
            var lc = w.Location as LocationCurve;
            var c = lc.Curve;
            var p0 = c.GetEndPoint(0);
            var p1 = c.GetEndPoint(1);
            var mid = new XYZ((p0.X + p1.X) * 0.5, (p0.Y + p1.Y) * 0.5, (p0.Z + p1.Z) * 0.5);
            return tr == null ? mid : tr.OfPoint(mid);
        } catch { return null; }
    }
    bool Touches(Wall w, Transform tr, SpatialElement sp) {
        Curve c = null;
        try { c = (w.Location as LocationCurve).Curve; } catch { return false; }
        if (c == null) return false;
        try {
            var mid = c.Evaluate(0.5, true);
            if (tr != null) mid = tr.OfPoint(mid);
            if (!InBbox(mid, SpBbox(sp), 3.3)) return false;
        } catch { }
        XYZ nrm = null;
        try { nrm = w.Orientation; } catch { return false; }
        if (nrm == null) return false;
        if (tr != null) { try { nrm = tr.OfVector(nrm); } catch { } }
        foreach (var tpar in new[]{0.1, 0.3, 0.5, 0.7, 0.9}) {
            XYZ pg = null;
            try {
                double par = c.GetEndParameter(0) * (1 - tpar) + c.GetEndParameter(1) * tpar;
                pg = c.Evaluate(par, false);
                if (tr != null) pg = tr.OfPoint(pg);
            } catch { continue; }
            foreach (var sign in new[]{-1.0, 1.0}) {
                var op = new XYZ(pg.X + sign * 1.6 * nrm.X, pg.Y + sign * 1.6 * nrm.Y, pg.Z);
                if (PtInSpace(sp, op)) return true;
            }
        }
        return false;
    }
    SpatialElement CondNeighbor(SpatialElement uncond) {
        XYZ pt0 = null;
        try { pt0 = (uncond.Location as LocationPoint).Point; } catch { return null; }
        if (pt0 == null) return null;
        SpatialElement best = null;
        double bestD = 1e18;
        foreach (var sp in spatial) {
            if (sp.Id.Value == uncond.Id.Value || IsUncond(sp)) continue;
            XYZ pt = null;
            try { pt = (sp.Location as LocationPoint).Point; } catch { continue; }
            if (pt == null) continue;
            if (Math.Abs(pt.Z - pt0.Z) > 2.0 / FT_M) continue;
            double dx = pt.X - pt0.X, dy = pt.Y - pt0.Y;
            double dd = Math.Sqrt(dx * dx + dy * dy);
            if (dd < bestD) { bestD = dd; best = sp; }
        }
        return best;
    }

    var seenOrphan = new HashSet<string>();
    foreach (var cw in cwalls) {
        var w = (Wall)cw[0];
        var tr = (Transform)cw[1];
        var linkName = (string)cw[2];
        string key = linkName + "|" + w.Id.Value.ToString(CI);
        if (seenKeys.Contains(key) || seenOrphan.Contains(key)) continue;

        // мелкие фрагменты < 0.5 м²
        double aft = BPD(w, BuiltInParameter.HOST_AREA_COMPUTED);
        if (aft > 0 && aft * FT_M * FT_M < 0.5) continue;

        var mid = MidGlobal(w, tr);
        SpatialElement target = null;
        SpatialElement host = null;
        if (mid != null) {
            foreach (var sp in spatial) {
                if (!InBbox(mid, SpBbox(sp), 1.6)) continue;
                if (PtInSpace(sp, mid)) { host = sp; break; }
            }
        }
        if (host != null) {
            if (IsUncond(host)) {
                var cn = CondNeighbor(host);
                if (cn != null && Touches(w, tr, cn)) target = cn;
            } else target = host;
        } else if (mid != null) {
            foreach (var sp in spatial) {
                if (IsUncond(sp)) continue;
                if (!InBbox(mid, SpBbox(sp), 3.3)) continue;
                if (Touches(w, tr, sp)) { target = sp; break; }
            }
        }
        if (target == null) continue;
        if (spacesWithGlazing.Contains(target.Id.Value)) continue;

        seenOrphan.Add(key);
        orphanCount++;
        var ti = TInfo(w);
        string lenM = "";
        try { lenM = Num((w.Location as LocationCurve).Curve.Length * FT_M, 3); } catch { }
        thermalRows.Add(new[]{
            target.Id.Value.ToString(CI),
            BPS(target, BuiltInParameter.ROOM_NUMBER),
            BPS(target, BuiltInParameter.ROOM_NAME),
            LevelName(target), "external_wall", "yes",
            w.Id.Value.ToString(CI), linkName, CatName(w), ti[0], ti[1],
            LevelName(w), lenM, HeightM(target),
            ElemAreaM2(w), ElemAreaM2(w), ti[4],
            "curtain (orphan)", ti[3], "", "1", WallAz(w),
        });
    }
}

// ---------- запись ----------
string spacesPath = System.IO.Path.Combine(folder, "spaces.csv");
string thermalPath = System.IO.Path.Combine(folder, "thermal_all.csv");
if (!System.IO.Directory.Exists(folder)) System.IO.Directory.CreateDirectory(folder);
WriteCsv(spacesPath, spacesRows);
WriteCsv(thermalPath, thermalRows);

return new {
    spaces_rows = spacesRows.Count - 1,
    thermal_rows = thermalRows.Count - 1,
    orphan_rows = orphanCount,
    source = source,
    spaces_csv = spacesPath,
    thermal_csv = thermalPath,
};
'''


# ============================================================================
# C#: запись результатов в параметры Spaces/Rooms (порт hvac-mcp, Фаза 2)
# ============================================================================
# parameters[0] = путь к CSV из io_revit.export_results_for_revit.

WRITEBACK_CS = r'''
string csvPath = (string)parameters[0];
var lines = System.IO.File.ReadAllLines(csvPath);
if (lines.Length < 2) return new { error = "empty_csv", rows = lines.Length };

string[] SplitCsv(string line) {
    var res = new List<string>();
    var sb = new System.Text.StringBuilder();
    bool q = false;
    for (int i = 0; i < line.Length; i++) {
        char c = line[i];
        if (q) {
            if (c == '"') { if (i + 1 < line.Length && line[i + 1] == '"') { sb.Append('"'); i++; } else q = false; }
            else sb.Append(c);
        } else {
            if (c == '"') q = true;
            else if (c == ',') { res.Add(sb.ToString()); sb.Clear(); }
            else sb.Append(c);
        }
    }
    res.Add(sb.ToString());
    return res.ToArray();
}

var header = SplitCsv(lines[0]);
var idx = new Dictionary<string, int>();
for (int i = 0; i < header.Length; i++) { var k = header[i].Trim(); if (!idx.ContainsKey(k)) idx[k] = i; }

Parameter FindParam(Element e, string[] names) {
    foreach (var n in names) { var p = e.LookupParameter(n); if (p != null && !p.IsReadOnly) return p; }
    return null;
}

bool SetNum(Element e, string[] cells, string col, string[] names, ForgeTypeId unit, HashSet<string> skipped) {
    if (!idx.ContainsKey(col)) return false;
    int ci = idx[col]; if (ci >= cells.Length) return false;
    double v;
    if (!double.TryParse(cells[ci].Trim().Replace(",", "."), System.Globalization.NumberStyles.Any,
            System.Globalization.CultureInfo.InvariantCulture, out v)) return false;
    var p = FindParam(e, names); if (p == null) { skipped.Add(col); return false; }
    try {
        double val = v;
        if (unit != null) { var spec = p.Definition.GetDataType(); if (UnitUtils.IsMeasurableSpec(spec)) val = UnitUtils.ConvertToInternalUnits(v, unit); }
        if (p.StorageType == StorageType.Double) { p.Set(val); return true; }
        if (p.StorageType == StorageType.Integer) { p.Set((int)System.Math.Round(v)); return true; }
        if (p.StorageType == StorageType.String) { p.Set(v.ToString("0.0", System.Globalization.CultureInfo.InvariantCulture)); return true; }
    } catch { }
    return false;
}

bool SetText(Element e, string[] cells, string col, string[] names, HashSet<string> skipped) {
    if (!idx.ContainsKey(col)) return false;
    int ci = idx[col]; if (ci >= cells.Length) return false;
    var sval = cells[ci].Trim(); if (sval.Length == 0) return false;
    var p = FindParam(e, names); if (p == null) { skipped.Add(col); return false; }
    try { if (p.StorageType == StorageType.String) { p.Set(sval); return true; } } catch { }
    return false;
}

var col2 = new FilteredElementCollector(document).OfCategory(BuiltInCategory.OST_MEPSpaces).WhereElementIsNotElementType().ToElements();
if (col2.Count == 0) col2 = new FilteredElementCollector(document).OfCategory(BuiltInCategory.OST_Rooms).WhereElementIsNotElementType().ToElements();
var byId = new Dictionary<string, Element>();
foreach (var e in col2) { var k = e.Id.Value.ToString(); if (!byId.ContainsKey(k)) byId[k] = e; }

int sidIdx = idx.ContainsKey("space_id") ? idx["space_id"] : 0;
int updated = 0, written = 0, missing = 0;
var skipped = new HashSet<string>();

for (int li = 1; li < lines.Length; li++) {
    if (string.IsNullOrWhiteSpace(lines[li])) continue;
    var cells = SplitCsv(lines[li]);
    if (sidIdx >= cells.Length) continue;
    var sid = cells[sidIdx].Trim(); if (sid.Length == 0) continue;
    Element e;
    if (!byId.TryGetValue(sid, out e)) { missing++; continue; }
    bool touched = false;
    if (SetNum(e, cells, "heating_load_w", new[]{"Heating Load","Calculated Heating Load","Design Heating Load"}, UnitTypeId.Watts, skipped)) { written++; touched = true; }
    if (SetNum(e, cells, "cooling_load_w", new[]{"Cooling Load","Calculated Cooling Load","Design Cooling Load"}, UnitTypeId.Watts, skipped)) { written++; touched = true; }
    if (SetNum(e, cells, "cooling_sensible_w", new[]{"Cooling Sensible Load","Sensible Cooling Load"}, UnitTypeId.Watts, skipped)) { written++; touched = true; }
    if (SetNum(e, cells, "cooling_latent_w", new[]{"Cooling Latent Load","Latent Cooling Load"}, UnitTypeId.Watts, skipped)) { written++; touched = true; }
    if (SetNum(e, cells, "supply_m3h", new[]{"Supply Airflow","Supply Air Flow"}, UnitTypeId.CubicMetersPerHour, skipped)) { written++; touched = true; }
    if (SetNum(e, cells, "exhaust_m3h", new[]{"Exhaust Airflow","Exhaust Air Flow"}, UnitTypeId.CubicMetersPerHour, skipped)) { written++; touched = true; }
    if (SetNum(e, cells, "ach", new[]{"Air Changes","Air Changes per Hour","ACH"}, null, skipped)) { written++; touched = true; }
    if (SetNum(e, cells, "t_in_heat", new[]{"Heating Setpoint","Heating Set Point"}, UnitTypeId.Celsius, skipped)) { written++; touched = true; }
    if (SetNum(e, cells, "t_in_cool", new[]{"Cooling Setpoint","Cooling Set Point"}, UnitTypeId.Celsius, skipped)) { written++; touched = true; }
    if (SetText(e, cells, "system_heating", new[]{"Heating System"}, skipped)) { written++; touched = true; }
    if (SetText(e, cells, "system_cooling", new[]{"Cooling System"}, skipped)) { written++; touched = true; }
    if (SetText(e, cells, "system_ventilation", new[]{"Ventilation System"}, skipped)) { written++; touched = true; }
    if (SetText(e, cells, "circuit_heating", new[]{"Heating Circuit"}, skipped)) { written++; touched = true; }
    if (SetText(e, cells, "circuit_cooling", new[]{"Cooling Circuit"}, skipped)) { written++; touched = true; }
    if (SetText(e, cells, "duct_zone", new[]{"Duct Zone"}, skipped)) { written++; touched = true; }
    if (touched) updated++;
}

return new { updated_spaces = updated, written_params = written, missing_spaces = missing,
              model_spaces = byId.Count, csv_rows = lines.Length - 1, skipped_columns = skipped.ToList() };
'''


def import_from_revit(folder: str, collect_orphans: bool = True,
                      timeout: float = 600.0) -> dict:
    """Выгружает spaces.csv + thermal_all.csv из открытой модели Revit.

    Колонки идентичны Dynamo-скрипту revit_dynamo_hvac_write_csv.py —
    файлы сразу пригодны для HVACProject.load().

    Возвращает сводку: {spaces_rows, thermal_rows, orphan_rows,
    source, spaces_csv, thermal_csv}.
    """
    res = send_code(
        EXPORT_CS,
        parameters=[str(folder), "1" if collect_orphans else "0"],
        transaction_mode="none", timeout=timeout,
    )
    if not isinstance(res, dict):
        raise RuntimeError(f"Неожиданный ответ Revit: {res!r}")
    return res


def write_results_to_revit(project: "HVACProject", csv_path: str,
                           timeout: float = 300.0) -> dict:
    """Записывает результаты расчёта в параметры Spaces открытой модели.

    Сначала сохраняет CSV (io_revit.export_results_for_revit) в csv_path —
    он остаётся как артефакт, — затем исполняет запись в Revit.
    В модели должны существовать Project Parameters (см. check_revit_params).
    """
    from hvac.io_revit import export_results_for_revit
    export_results_for_revit(project, csv_path)
    res = send_code(WRITEBACK_CS, parameters=[str(csv_path)],
                    transaction_mode="auto", timeout=timeout)
    if not isinstance(res, dict):
        raise RuntimeError(f"Неожиданный ответ Revit: {res!r}")
    return res


def check_revit_params(timeout: float = 60.0) -> dict:
    """Какие целевые параметры уже созданы на Spaces/Rooms модели."""
    code = r'''
var col = new FilteredElementCollector(document).OfCategory(BuiltInCategory.OST_MEPSpaces).WhereElementIsNotElementType().ToElements();
string cat = "MEPSpaces";
if (col.Count == 0) { col = new FilteredElementCollector(document).OfCategory(BuiltInCategory.OST_Rooms).WhereElementIsNotElementType().ToElements(); cat = "Rooms"; }
if (col.Count == 0) return new { category = "none", spaces = 0, present = new List<string>(), missing = new List<string>() };
var sample = col.First();
var targets = new[]{"Heating Load","Cooling Load","Cooling Sensible Load","Cooling Latent Load",
    "Supply Airflow","Exhaust Airflow","Air Changes","Heating Setpoint","Cooling Setpoint",
    "Heating System","Cooling System","Ventilation System","Heating Circuit","Cooling Circuit","Duct Zone"};
var present = new List<string>(); var missing = new List<string>();
foreach (var t in targets) { var p = sample.LookupParameter(t); if (p != null) present.Add(t); else missing.Add(t); }
return new { category = cat, spaces = col.Count, present = present, missing = missing };
'''
    return send_code(code, transaction_mode="none", timeout=timeout)
