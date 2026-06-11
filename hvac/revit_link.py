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

ОГРАНИЧЕНИЕ ПЛАГИНА: запрос читается одним буфером 8192 байта
(проверено эмпирически: 6 КБ проходит, 8 КБ — «Invalid JSON»).
Поэтому выгрузка разбита на ТРИ прохода, каждый — компактный C#
(минифицируется перед отправкой, размер контролируется):

  1) spaces.csv + карта смежности границ (_bsc.tsv);
  2) thermal_all.csv по границам помещений (+ _seen.txt / _glz.txt);
  3) orphan-витражи вне Room Bounding (дописываются в thermal_all.csv).

Промежуточные файлы пишутся в ту же папку и удаляются после импорта.
Колонки CSV идентичны Dynamo-скрипту revit_dynamo_hvac_write_csv.py.
C#-запись результатов — порт hvac-mcp/revit_writeback.py (обкатан).

Требования к Revit: модель открыта в полном режиме, включён
переключатель «Revit MCP Switch» (плагин слушает :8080).
"""

from __future__ import annotations

import json
import os
import socket
import tempfile
from collections import Counter
from dataclasses import dataclass, field
from typing import Dict, List, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from hvac.project import HVACProject

REVIT_HOST = "127.0.0.1"
REVIT_PORT = 8080

# Буфер приёма плагина — 8192 байта на ВЕСЬ JSON-RPC запрос.
# Оставляем запас на обвязку (id/method/params/экранирование).
MAX_REQUEST_BYTES = 7600


class RevitNotConnected(RuntimeError):
    """Revit закрыт или переключатель Revit MCP Switch выключен."""


def minify_cs(code: str) -> str:
    """Сжимает C#: убирает пустые строки, отступы и строки-комментарии.

    Хвостовые комментарии не трогаем (могут быть внутри строковых
    литералов) — в шаблонах ниже их просто нет.
    """
    out = []
    for line in code.splitlines():
        s = line.strip()
        if not s or s.startswith("//"):
            continue
        out.append(s)
    return "\n".join(out)


def call(method: str, params: Optional[dict] = None, timeout: float = 75.0):
    """Низкоуровневый JSON-RPC вызов к плагину Revit."""
    req = {"jsonrpc": "2.0", "id": "1",
           "method": method, "params": params or {}}
    payload = json.dumps(req, ensure_ascii=False).encode("utf-8")
    if len(payload) > MAX_REQUEST_BYTES + 592:
        raise RuntimeError(
            f"Запрос {len(payload)} байт превышает буфер плагина Revit "
            f"(8192). Разбейте C#-код на несколько вызовов send_code.")
    try:
        s = socket.create_connection((REVIT_HOST, REVIT_PORT), timeout=timeout)
    except OSError as e:
        raise RevitNotConnected(
            f"Не удалось подключиться к Revit на {REVIT_HOST}:{REVIT_PORT}. "
            f"Открыт ли Revit и включён ли переключатель 'Revit MCP Switch'? ({e})"
        )
    try:
        s.settimeout(timeout)
        s.sendall(payload)
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
    """Исполнить C# внутри Revit и вернуть разобранный результат.

    Код минифицируется автоматически (лимит запроса — 8 КБ).
    """
    res = call("send_code_to_revit",
               {"code": minify_cs(code), "parameters": parameters or [],
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
# Проход 1: spaces.csv + карта смежности границ (_bsc.tsv)
# ============================================================================
# parameters[0] = папка вывода.
# _bsc.tsv: "<link>|<element_id>\t<число отапливаемых пространств>".

EXPORT_CS_SPACES = r'''
string folder = (string)parameters[0];
var CI = System.Globalization.CultureInfo.InvariantCulture;
string S(Element e, BuiltInParameter b){var p=e.get_Parameter(b);if(p==null)return "";if(p.StorageType==StorageType.String)return p.AsString()??"";return p.AsValueString()??"";}
double D(Element e, BuiltInParameter b){var p=e.get_Parameter(b);if(p!=null&&p.StorageType==StorageType.Double){try{return p.AsDouble();}catch{}}return 0.0;}
string Lk(Element e, string[] names){if(e==null)return "";foreach(var n in names){Parameter p=null;try{p=e.LookupParameter(n);}catch{}if(p==null)continue;string v=p.StorageType==StorageType.String?(p.AsString()??""):(p.AsValueString()??"");if(v!="")return v;}return "";}
string Lv(Element e){try{var l=e.Document.GetElement(e.LevelId);if(l!=null)return l.Name??"";}catch{}return S(e,BuiltInParameter.LEVEL_PARAM);}
string Nm(double v){return Math.Round(v,3).ToString("0.0###",CI);}
string Esc(string s){if(s==null)s="";if(s.IndexOfAny(new[]{',','"','\n','\r'})>=0)return "\""+s.Replace("\"","\"\"")+"\"";return s;}
bool Unc(SpatialElement sp){
string nu=(S(sp,BuiltInParameter.ROOM_NUMBER)??"").Trim().ToUpperInvariant();
foreach(var px in new[]{"OFC-","BAL-","TER-","SHAFT","ШАХТ"})if(nu.StartsWith(px))return true;
string full=(nu+" "+(S(sp,BuiltInParameter.ROOM_NAME)??"")).ToLowerInvariant();
foreach(var kw in new[]{"балкон","терраса","лоджия","balcony","terrace","loggia","shaft","open air"})if(full.Contains(kw))return true;
return false;}
var spatial=new List<SpatialElement>();
string source="Spaces (MEP)";
foreach(Element e in new FilteredElementCollector(document).OfCategory(BuiltInCategory.OST_MEPSpaces).WhereElementIsNotElementType()){var se=e as SpatialElement;if(se!=null&&D(se,BuiltInParameter.ROOM_AREA)>1e-9)spatial.Add(se);}
if(spatial.Count==0){source="Rooms (Architecture)";
foreach(Element e in new FilteredElementCollector(document).OfCategory(BuiltInCategory.OST_Rooms).WhereElementIsNotElementType()){var se=e as SpatialElement;if(se!=null&&D(se,BuiltInParameter.ROOM_AREA)>1e-9)spatial.Add(se);}}
string Hm(SpatialElement sp){
double h=D(sp,BuiltInParameter.ROOM_HEIGHT);
if(h<=0){try{var s2=sp as Autodesk.Revit.DB.Mechanical.Space;if(s2!=null)h=s2.UnboundedHeight;}catch{}}
if(h<=0){try{var r2=sp as Autodesk.Revit.DB.Architecture.Room;if(r2!=null)h=r2.UnboundedHeight;}catch{}}
return h>0?Nm(h*0.3048):"";}
var sb=new System.Text.StringBuilder();
sb.Append("id,category,number,name,level,area,volume,height,zone,heating_load,cooling_load\r\n");
foreach(var sp in spatial){
string cat="";try{cat=sp.Category!=null?(sp.Category.Name??""):"";}catch{}
var cells=new[]{sp.Id.Value.ToString(CI),cat,S(sp,BuiltInParameter.ROOM_NUMBER),S(sp,BuiltInParameter.ROOM_NAME),Lv(sp),
Nm(D(sp,BuiltInParameter.ROOM_AREA)*0.09290304),Nm(D(sp,BuiltInParameter.ROOM_VOLUME)*0.0283168466),Hm(sp),
Lk(sp,new[]{"Zone","Space Type"}),Lk(sp,new[]{"Heating Load","Calculated Heating Load","Design Heating Load"}),Lk(sp,new[]{"Cooling Load","Calculated Cooling Load","Design Cooling Load"})};
for(int i=0;i<cells.Length;i++){if(i>0)sb.Append(',');sb.Append(Esc(cells[i]));}
sb.Append("\r\n");}
if(!System.IO.Directory.Exists(folder))System.IO.Directory.CreateDirectory(folder);
System.IO.File.WriteAllText(System.IO.Path.Combine(folder,"spaces.csv"),sb.ToString(),new System.Text.UTF8Encoding(true));
var bopt=new SpatialElementBoundaryOptions();
var bnd=new Dictionary<string,HashSet<long>>();
foreach(var sp in spatial){
if(Unc(sp))continue;
IList<IList<BoundarySegment>> loops=null;try{loops=sp.GetBoundarySegments(bopt);}catch{}
if(loops==null)continue;
var seen=new HashSet<string>();
foreach(var loop in loops)foreach(var seg in loop){
Element host=null;try{if(seg.ElementId!=ElementId.InvalidElementId)host=document.GetElement(seg.ElementId);}catch{}
string ln="";Element el=host;
var li=host as RevitLinkInstance;
if(li!=null){try{var ld=li.GetLinkDocument();var lid=seg.LinkElementId;if(ld!=null&&lid!=ElementId.InvalidElementId){var le=ld.GetElement(lid);if(le!=null){el=le;ln=li.Name??"";}}}catch{}}
if(el==null)continue;
seen.Add(ln+"|"+el.Id.Value.ToString(CI));}
long sid=sp.Id.Value;
foreach(var k in seen){HashSet<long> hs;if(!bnd.TryGetValue(k,out hs)){hs=new HashSet<long>();bnd[k]=hs;}hs.Add(sid);}}
var tb=new System.Text.StringBuilder();
foreach(var kv in bnd){tb.Append(kv.Key);tb.Append('\t');tb.Append(kv.Value.Count.ToString(CI));tb.Append('\n');}
System.IO.File.WriteAllText(System.IO.Path.Combine(folder,"_bsc.tsv"),tb.ToString(),new System.Text.UTF8Encoding(false));
return new{spaces_rows=spatial.Count,bsc_keys=bnd.Count,source=source};
'''


# ============================================================================
# Проход 2: thermal_all.csv по границам (+ _seen.txt, _glz.txt для прохода 3)
# ============================================================================
# parameters[0] = папка (там же _bsc.tsv из прохода 1).

EXPORT_CS_THERMAL = r'''
string folder = (string)parameters[0];
var CI = System.Globalization.CultureInfo.InvariantCulture;
string S(Element e, BuiltInParameter b){var p=e.get_Parameter(b);if(p==null)return "";if(p.StorageType==StorageType.String)return p.AsString()??"";return p.AsValueString()??"";}
double D(Element e, BuiltInParameter b){var p=e.get_Parameter(b);if(p!=null&&p.StorageType==StorageType.Double){try{return p.AsDouble();}catch{}}return 0.0;}
string Lv(Element e){try{var l=e.Document.GetElement(e.LevelId);if(l!=null)return l.Name??"";}catch{}return S(e,BuiltInParameter.LEVEL_PARAM);}
string Nm(double v){return Math.Round(v,3).ToString("0.0###",CI);}
string Esc(string s){if(s==null)s="";if(s.IndexOfAny(new[]{',','"','\n','\r'})>=0)return "\""+s.Replace("\"","\"\"")+"\"";return s;}
string Az(double x,double y){if(Math.Abs(x)<1e-9&&Math.Abs(y)<1e-9)return "";double a=Math.Atan2(x,y)*180.0/Math.PI;if(a<0)a+=360.0;return Math.Round(a,1).ToString("0.0",CI);}
var tc=new Dictionary<string,string[]>();
string[] TI(Element el){
var bl=new[]{"","","","","",""};
if(el==null)return bl;
string key;Document d;ElementId tid;
try{d=el.Document;tid=el.GetTypeId();key=(d.PathName??"")+"|"+tid.Value.ToString(CI);}catch{return bl;}
string[] r;if(tc.TryGetValue(key,out r))return r;
r=new[]{"","","","","",""};
try{var te=d.GetElement(tid) as ElementType;
if(te!=null){
try{r[0]=te.FamilyName??"";}catch{}
try{r[1]=te.Name??"";}catch{}
r[2]=S(te,BuiltInParameter.FUNCTION_PARAM);
foreach(var n in new[]{"Heat Transfer Coefficient","Thermal Transmittance","U-Value","U Value","U"}){Parameter p=null;try{p=te.LookupParameter(n);}catch{}if(p==null)continue;string v=p.StorageType==StorageType.String?(p.AsString()??""):(p.AsValueString()??"");if(v!=""){r[3]=v;break;}}
var wp=te.get_Parameter(BuiltInParameter.WALL_ATTR_WIDTH_PARAM);
if(wp!=null&&wp.StorageType==StorageType.Double)r[4]=Nm(wp.AsDouble()*304.8);
bool cu=false;var wt=te as WallType;
if(wt!=null){try{cu=wt.Kind==WallKind.Curtain;}catch{}}
if(!cu){var f=(r[0]+" "+r[1]).ToLowerInvariant();if(f.Contains("curtain")||f.Contains("витраж")||f.Contains("стекл")||f.Contains("glaz"))cu=true;}
r[5]=cu?"1":"";}}catch{}
tc[key]=r;return r;}
string WAz(Element el){
var w=el as Wall;if(w==null)return "";
try{var n=w.Orientation;if(n!=null)return Az(n.X,n.Y);}catch{}
return "";}
string EA(Element el){double a=D(el,BuiltInParameter.HOST_AREA_COMPUTED);if(a>0)return Nm(a*0.09290304);
foreach(var n in new[]{"Area","Площадь"}){Parameter p=null;try{p=el.LookupParameter(n);}catch{}if(p!=null){var v=p.AsValueString();if(!string.IsNullOrEmpty(v))return v;}}
return "";}
var bsc=new Dictionary<string,int>();
foreach(var line in System.IO.File.ReadAllLines(System.IO.Path.Combine(folder,"_bsc.tsv"))){
int t=line.LastIndexOf('\t');if(t<0)continue;
int c;if(int.TryParse(line.Substring(t+1),System.Globalization.NumberStyles.Any,CI,out c))bsc[line.Substring(0,t)]=c;}
var spatial=new List<SpatialElement>();
foreach(Element e in new FilteredElementCollector(document).OfCategory(BuiltInCategory.OST_MEPSpaces).WhereElementIsNotElementType()){var se=e as SpatialElement;if(se!=null&&D(se,BuiltInParameter.ROOM_AREA)>1e-9)spatial.Add(se);}
if(spatial.Count==0)foreach(Element e in new FilteredElementCollector(document).OfCategory(BuiltInCategory.OST_Rooms).WhereElementIsNotElementType()){var se=e as SpatialElement;if(se!=null&&D(se,BuiltInParameter.ROOM_AREA)>1e-9)spatial.Add(se);}
string Hm(SpatialElement sp){
double h=D(sp,BuiltInParameter.ROOM_HEIGHT);
if(h<=0){try{var s2=sp as Autodesk.Revit.DB.Mechanical.Space;if(s2!=null)h=s2.UnboundedHeight;}catch{}}
return h>0?Nm(h*0.3048):"";}
var bopt=new SpatialElementBoundaryOptions();
var sb=new System.Text.StringBuilder();
sb.Append("space_id,space_number,space_name,space_level,row_type,is_exterior_wall,element_id,link_model,category,family,type,element_level,boundary_length_m,space_height_m,approx_area_m2,element_area,thickness,function,thermal_value,host_element_id,boundary_space_count,orientation_deg\r\n");
int rows=0;
var seenK=new HashSet<string>();
var glz=new HashSet<long>();
void Row(string[] cells){for(int i=0;i<cells.Length;i++){if(i>0)sb.Append(',');sb.Append(Esc(cells[i]));}sb.Append("\r\n");rows++;}
foreach(var sp in spatial){
IList<IList<BoundarySegment>> loops=null;try{loops=sp.GetBoundarySegments(bopt);}catch{}
if(loops==null)continue;
string sid=sp.Id.Value.ToString(CI),sn=S(sp,BuiltInParameter.ROOM_NUMBER),sm=S(sp,BuiltInParameter.ROOM_NAME),sl=Lv(sp),sh=Hm(sp);
double shd=0;double.TryParse(sh,System.Globalization.NumberStyles.Any,CI,out shd);
foreach(var loop in loops)foreach(var seg in loop){
Element host=null;try{if(seg.ElementId!=ElementId.InvalidElementId)host=document.GetElement(seg.ElementId);}catch{}
string ln="";Element el=host;
var li=host as RevitLinkInstance;
if(li!=null){try{var ld=li.GetLinkDocument();var lid=seg.LinkElementId;if(ld!=null&&lid!=ElementId.InvalidElementId){var le=ld.GetElement(lid);if(le!=null){el=le;ln=li.Name??"";}}}catch{}}
if(el==null)continue;
double len=-1;try{len=seg.GetCurve().Length*0.3048;}catch{}
bool isWall=false;try{isWall=el.Category!=null&&el.Category.Id.Value==(long)(int)BuiltInCategory.OST_Walls;}catch{}
if(isWall&&len>=0&&len<0.5)continue;
string key=ln+"|"+el.Id.Value.ToString(CI);
int bc;if(!bsc.TryGetValue(key,out bc))bc=1;
var ti=TI(el);
bool curt=isWall&&ti[5]=="1";
bool ext=isWall&&(curt||bc<2);
string orient=isWall?WAz(el):"";
if(orient==""){try{var lc=seg.GetCurve() as Line;if(lc!=null)orient=Az(lc.Direction.Y,-lc.Direction.X);}catch{}}
seenK.Add(key);
var gf=(ti[0]+" "+ti[1]).ToLowerInvariant();
if(gf.Contains("витраж")||gf.Contains("curtain")||gf.Contains("balcony"))glz.Add(sp.Id.Value);
string cat="";try{cat=el.Category!=null?(el.Category.Name??""):"";}catch{}
Row(new[]{sid,sn,sm,sl,"external_wall",ext?"yes":"no",el.Id.Value.ToString(CI),ln,cat,ti[0],ti[1],Lv(el),len>=0?Nm(len):"",sh,(len>=0&&shd>0)?Nm(len*shd):"",EA(el),ti[4],ti[2],ti[3],"",bc.ToString(CI),orient});
var ho=el as HostObject;
if(ho==null)continue;
IList<ElementId> ins=null;try{ins=ho.FindInserts(true,false,false,false);}catch{}
if(ins==null)continue;
foreach(var iid in ins){
Element ie=null;try{ie=el.Document.GetElement(iid);}catch{}
if(ie==null)continue;
bool wd=false;try{long cid=ie.Category.Id.Value;wd=cid==(long)(int)BuiltInCategory.OST_Windows||cid==(long)(int)BuiltInCategory.OST_Doors;}catch{}
if(!wd)continue;
var ti2=TI(ie);
string cat2="";try{cat2=ie.Category!=null?(ie.Category.Name??""):"";}catch{}
Row(new[]{sid,sn,sm,sl,"opening",ext?"yes":"no",ie.Id.Value.ToString(CI),ln,cat2,ti2[0],ti2[1],Lv(ie),"","","",EA(ie),"","hosted by exterior wall",ti2[3],el.Id.Value.ToString(CI),bc.ToString(CI),orient});}}}
System.IO.File.WriteAllText(System.IO.Path.Combine(folder,"thermal_all.csv"),sb.ToString(),new System.Text.UTF8Encoding(true));
System.IO.File.WriteAllLines(System.IO.Path.Combine(folder,"_seen.txt"),seenK.ToArray());
var gl=new List<string>();foreach(var g in glz)gl.Add(g.ToString(CI));
System.IO.File.WriteAllLines(System.IO.Path.Combine(folder,"_glz.txt"),gl.ToArray());
return new{thermal_rows=rows};
'''


# ============================================================================
# Проход 3: orphan-витражи вне Room Bounding → дозапись в thermal_all.csv
# ============================================================================
# parameters[0] = папка (там же _seen.txt и _glz.txt из прохода 2).

EXPORT_CS_ORPHANS = r'''
string folder = (string)parameters[0];
var CI = System.Globalization.CultureInfo.InvariantCulture;
string S(Element e, BuiltInParameter b){var p=e.get_Parameter(b);if(p==null)return "";if(p.StorageType==StorageType.String)return p.AsString()??"";return p.AsValueString()??"";}
double D(Element e, BuiltInParameter b){var p=e.get_Parameter(b);if(p!=null&&p.StorageType==StorageType.Double){try{return p.AsDouble();}catch{}}return 0.0;}
string Lv(Element e){try{var l=e.Document.GetElement(e.LevelId);if(l!=null)return l.Name??"";}catch{}return "";}
string Nm(double v){return Math.Round(v,3).ToString("0.0###",CI);}
string Esc(string s){if(s==null)s="";if(s.IndexOfAny(new[]{',','"','\n','\r'})>=0)return "\""+s.Replace("\"","\"\"")+"\"";return s;}
string Az(double x,double y){if(Math.Abs(x)<1e-9&&Math.Abs(y)<1e-9)return "";double a=Math.Atan2(x,y)*180.0/Math.PI;if(a<0)a+=360.0;return Math.Round(a,1).ToString("0.0",CI);}
var seenK=new HashSet<string>(System.IO.File.ReadAllLines(System.IO.Path.Combine(folder,"_seen.txt")));
var glz=new HashSet<string>(System.IO.File.ReadAllLines(System.IO.Path.Combine(folder,"_glz.txt")));
bool Unc(SpatialElement sp){
string nu=(S(sp,BuiltInParameter.ROOM_NUMBER)??"").Trim().ToUpperInvariant();
foreach(var px in new[]{"OFC-","BAL-","TER-","SHAFT","ШАХТ"})if(nu.StartsWith(px))return true;
string full=(nu+" "+(S(sp,BuiltInParameter.ROOM_NAME)??"")).ToLowerInvariant();
foreach(var kw in new[]{"балкон","терраса","лоджия","balcony","terrace","loggia","shaft","open air"})if(full.Contains(kw))return true;
return false;}
var spatial=new List<SpatialElement>();
foreach(Element e in new FilteredElementCollector(document).OfCategory(BuiltInCategory.OST_MEPSpaces).WhereElementIsNotElementType()){var se=e as SpatialElement;if(se!=null&&D(se,BuiltInParameter.ROOM_AREA)>1e-9)spatial.Add(se);}
if(spatial.Count==0)foreach(Element e in new FilteredElementCollector(document).OfCategory(BuiltInCategory.OST_Rooms).WhereElementIsNotElementType()){var se=e as SpatialElement;if(se!=null&&D(se,BuiltInParameter.ROOM_AREA)>1e-9)spatial.Add(se);}
var bb=new Dictionary<long,double[]>();
double[] BB(SpatialElement sp){
long id=sp.Id.Value;double[] r;
if(bb.TryGetValue(id,out r))return r;
r=null;try{var b=sp.get_BoundingBox(null);if(b!=null)r=new[]{b.Min.X,b.Min.Y,b.Min.Z,b.Max.X,b.Max.Y,b.Max.Z};}catch{}
bb[id]=r;return r;}
bool InB(XYZ p,double[] b,double t){if(b==null||p==null)return true;return b[0]-t<=p.X&&p.X<=b[3]+t&&b[1]-t<=p.Y&&p.Y<=b[4]+t&&b[2]-t<=p.Z&&p.Z<=b[5]+t;}
bool PIn(SpatialElement sp,XYZ p){
try{var s2=sp as Autodesk.Revit.DB.Mechanical.Space;if(s2!=null)return s2.IsPointInSpace(p);}catch{}
try{var r2=sp as Autodesk.Revit.DB.Architecture.Room;if(r2!=null)return r2.IsPointInRoom(p);}catch{}
return false;}
var cw=new List<object[]>();
var seenD=new HashSet<string>();
seenD.Add(document.PathName??"MAIN");
foreach(Element e in new FilteredElementCollector(document).OfCategory(BuiltInCategory.OST_Walls).WhereElementIsNotElementType()){var w=e as Wall;if(w==null)continue;var wt=document.GetElement(w.GetTypeId()) as WallType;if(wt!=null&&wt.Kind==WallKind.Curtain)cw.Add(new object[]{w,null,""});}
foreach(Element e in new FilteredElementCollector(document).OfClass(typeof(RevitLinkInstance))){
var li=e as RevitLinkInstance;if(li==null)continue;
Document ld=null;try{ld=li.GetLinkDocument();}catch{}
if(ld==null)continue;
string lp=ld.PathName??(li.Name??"");
if(seenD.Contains(lp))continue;
seenD.Add(lp);
Transform tr=null;try{tr=li.GetTotalTransform();}catch{}
foreach(Element we in new FilteredElementCollector(ld).OfCategory(BuiltInCategory.OST_Walls).WhereElementIsNotElementType()){var w=we as Wall;if(w==null)continue;var wt=ld.GetElement(w.GetTypeId()) as WallType;if(wt!=null&&wt.Kind==WallKind.Curtain)cw.Add(new object[]{w,tr,li.Name??""});}}
bool Tch(Wall w,Transform tr,SpatialElement sp){
Curve c=null;try{c=(w.Location as LocationCurve).Curve;}catch{return false;}
if(c==null)return false;
XYZ nrm=null;try{nrm=w.Orientation;}catch{return false;}
if(nrm==null)return false;
if(tr!=null){try{nrm=tr.OfVector(nrm);}catch{}}
foreach(var t in new[]{0.1,0.3,0.5,0.7,0.9}){
XYZ pg=null;
try{double par=c.GetEndParameter(0)*(1-t)+c.GetEndParameter(1)*t;pg=c.Evaluate(par,false);if(tr!=null)pg=tr.OfPoint(pg);}catch{continue;}
foreach(var sg in new[]{-1.0,1.0}){var op=new XYZ(pg.X+sg*1.6*nrm.X,pg.Y+sg*1.6*nrm.Y,pg.Z);if(PIn(sp,op))return true;}}
return false;}
var sb=new System.Text.StringBuilder();
int rows=0;
var seenO=new HashSet<string>();
foreach(var o in cw){
var w=(Wall)o[0];var tr=(Transform)o[1];var ln=(string)o[2];
string key=ln+"|"+w.Id.Value.ToString(CI);
if(seenK.Contains(key)||seenO.Contains(key))continue;
double aft=D(w,BuiltInParameter.HOST_AREA_COMPUTED);
if(aft>0&&aft*0.09290304<0.5)continue;
XYZ mid=null;
try{var c=(w.Location as LocationCurve).Curve;var p0=c.GetEndPoint(0);var p1=c.GetEndPoint(1);mid=new XYZ((p0.X+p1.X)*0.5,(p0.Y+p1.Y)*0.5,(p0.Z+p1.Z)*0.5);if(tr!=null)mid=tr.OfPoint(mid);}catch{}
if(mid==null)continue;
SpatialElement host=null,target=null;
foreach(var sp in spatial){if(!InB(mid,BB(sp),1.6))continue;if(PIn(sp,mid)){host=sp;break;}}
if(host!=null){
if(Unc(host)){
SpatialElement best=null;double bd=1e18;XYZ p0=null;
try{p0=(host.Location as LocationPoint).Point;}catch{}
if(p0!=null)foreach(var sp in spatial){
if(sp.Id.Value==host.Id.Value||Unc(sp))continue;
XYZ pt=null;try{pt=(sp.Location as LocationPoint).Point;}catch{continue;}
if(pt==null||Math.Abs(pt.Z-p0.Z)>6.56)continue;
double dx=pt.X-p0.X,dy=pt.Y-p0.Y,dd=Math.Sqrt(dx*dx+dy*dy);
if(dd<bd){bd=dd;best=sp;}}
if(best!=null&&Tch(w,tr,best))target=best;}
else target=host;}
else{foreach(var sp in spatial){if(Unc(sp))continue;if(!InB(mid,BB(sp),3.3))continue;if(Tch(w,tr,sp)){target=sp;break;}}}
if(target==null)continue;
if(glz.Contains(target.Id.Value.ToString(CI)))continue;
seenO.Add(key);
var wt2=w.Document.GetElement(w.GetTypeId()) as ElementType;
string fam="",tn="",uv="";
if(wt2!=null){try{fam=wt2.FamilyName??"";}catch{}try{tn=wt2.Name??"";}catch{}
foreach(var n in new[]{"Heat Transfer Coefficient","Thermal Transmittance","U-Value","U Value","U"}){Parameter p=null;try{p=wt2.LookupParameter(n);}catch{}if(p==null)continue;var v=p.AsValueString();if(!string.IsNullOrEmpty(v)){uv=v;break;}}}
string lenM="";try{lenM=Nm((w.Location as LocationCurve).Curve.Length*0.3048);}catch{}
double th=D(target,BuiltInParameter.ROOM_HEIGHT)*0.3048;
string area=aft>0?Nm(aft*0.09290304):"";
string cat="";try{cat=w.Category!=null?(w.Category.Name??""):"";}catch{}
string orient="";try{var n2=w.Orientation;if(n2!=null)orient=Az(n2.X,n2.Y);}catch{}
var cells=new[]{target.Id.Value.ToString(CI),S(target,BuiltInParameter.ROOM_NUMBER),S(target,BuiltInParameter.ROOM_NAME),Lv(target),"external_wall","yes",w.Id.Value.ToString(CI),ln,cat,fam,tn,Lv(w),lenM,th>0?Nm(th):"",area,area,"","curtain (orphan)",uv,"","1",orient};
for(int i=0;i<cells.Length;i++){if(i>0)sb.Append(',');sb.Append(Esc(cells[i]));}
sb.Append("\r\n");rows++;}
if(rows>0)System.IO.File.AppendAllText(System.IO.Path.Combine(folder,"thermal_all.csv"),sb.ToString(),new System.Text.UTF8Encoding(false));
return new{orphan_rows=rows};
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

#: Временные файлы обмена между проходами импорта
_IMPORT_TEMP_FILES = ("_bsc.tsv", "_seen.txt", "_glz.txt")


def import_from_revit(folder: str, collect_orphans: bool = True,
                      timeout: float = 600.0) -> dict:
    """Выгружает spaces.csv + thermal_all.csv из открытой модели Revit.

    Выполняется в три прохода (см. докстринг модуля) — каждый C#-вызов
    укладывается в 8-КБ буфер плагина. Колонки CSV идентичны
    Dynamo-скрипту revit_dynamo_hvac_write_csv.py.

    Возвращает сводку: {spaces_rows, thermal_rows, orphan_rows,
    source, spaces_csv, thermal_csv}.
    """
    folder = str(folder)
    try:
        r1 = send_code(EXPORT_CS_SPACES, parameters=[folder],
                       transaction_mode="none", timeout=timeout)
        if not isinstance(r1, dict):
            raise RuntimeError(f"Проход 1: неожиданный ответ Revit: {r1!r}")
        r2 = send_code(EXPORT_CS_THERMAL, parameters=[folder],
                       transaction_mode="none", timeout=timeout)
        if not isinstance(r2, dict):
            raise RuntimeError(f"Проход 2: неожиданный ответ Revit: {r2!r}")
        r3 = {"orphan_rows": 0}
        if collect_orphans:
            r3 = send_code(EXPORT_CS_ORPHANS, parameters=[folder],
                           transaction_mode="none", timeout=timeout)
            if not isinstance(r3, dict):
                raise RuntimeError(f"Проход 3: неожиданный ответ Revit: {r3!r}")
    finally:
        for name in _IMPORT_TEMP_FILES:
            try:
                os.remove(os.path.join(folder, name))
            except OSError:
                pass
    orphans = int(r3.get("orphan_rows", 0))
    return {
        "spaces_rows": int(r1.get("spaces_rows", 0)),
        "thermal_rows": int(r2.get("thermal_rows", 0)) + orphans,
        "orphan_rows": orphans,
        "source": r1.get("source", ""),
        "spaces_csv": os.path.join(folder, "spaces.csv"),
        "thermal_csv": os.path.join(folder, "thermal_all.csv"),
    }


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


# ============================================================================
# Снимок модели и дифф с проектом
# ============================================================================
# Лёгкий read-only проход: id/номер/имя/уровень/площадь/объём всех
# помещений. Ответ (даже на тысячи помещений) приходит одной строкой —
# лимит 8 КБ касается только запроса.

SNAPSHOT_CS = r'''
var CI = System.Globalization.CultureInfo.InvariantCulture;
string S(Element e, BuiltInParameter b){var p=e.get_Parameter(b);if(p==null)return "";if(p.StorageType==StorageType.String)return p.AsString()??"";return p.AsValueString()??"";}
double D(Element e, BuiltInParameter b){var p=e.get_Parameter(b);if(p!=null&&p.StorageType==StorageType.Double){try{return p.AsDouble();}catch{}}return 0.0;}
string Lv(Element e){try{var l=e.Document.GetElement(e.LevelId);if(l!=null)return l.Name??"";}catch{}return S(e,BuiltInParameter.LEVEL_PARAM);}
string Cl(string s){if(s==null)return "";return s.Replace('\t',' ').Replace('\n',' ').Replace('\r',' ');}
var spatial=new List<SpatialElement>();
string source="Spaces (MEP)";
foreach(Element e in new FilteredElementCollector(document).OfCategory(BuiltInCategory.OST_MEPSpaces).WhereElementIsNotElementType()){var se=e as SpatialElement;if(se!=null&&D(se,BuiltInParameter.ROOM_AREA)>1e-9)spatial.Add(se);}
if(spatial.Count==0){source="Rooms (Architecture)";
foreach(Element e in new FilteredElementCollector(document).OfCategory(BuiltInCategory.OST_Rooms).WhereElementIsNotElementType()){var se=e as SpatialElement;if(se!=null&&D(se,BuiltInParameter.ROOM_AREA)>1e-9)spatial.Add(se);}}
var sb=new System.Text.StringBuilder();
foreach(var sp in spatial){
sb.Append(sp.Id.Value.ToString(CI)).Append('\t');
sb.Append(Cl(S(sp,BuiltInParameter.ROOM_NUMBER))).Append('\t');
sb.Append(Cl(S(sp,BuiltInParameter.ROOM_NAME))).Append('\t');
sb.Append(Cl(Lv(sp))).Append('\t');
sb.Append(Math.Round(D(sp,BuiltInParameter.ROOM_AREA)*0.09290304,3).ToString("0.0##",CI)).Append('\t');
sb.Append(Math.Round(D(sp,BuiltInParameter.ROOM_VOLUME)*0.0283168466,3).ToString("0.0##",CI)).Append('\n');}
return new{count=spatial.Count,source=source,data=sb.ToString()};
'''


def _snapshot_raw(timeout: float = 300.0) -> tuple:
    """Снимок помещений открытой модели: ({id: данные}, источник)."""
    res = send_code(SNAPSHOT_CS, transaction_mode="none", timeout=timeout)
    if not isinstance(res, dict) or "data" not in res:
        raise RuntimeError(f"Неожиданный ответ Revit: {res!r}")
    out: Dict[str, dict] = {}
    for line in str(res["data"]).splitlines():
        parts = line.split("\t")
        if len(parts) < 6:
            continue
        try:
            area = float(parts[4])
            volume = float(parts[5])
        except ValueError:
            continue
        out[parts[0]] = {
            "number": parts[1], "name": parts[2], "level": parts[3],
            "area_m2": area, "volume_m3": volume,
        }
    return out, str(res.get("source", ""))


def snapshot_spaces(timeout: float = 300.0) -> Dict[str, dict]:
    """Лёгкий снимок помещений открытой модели: {id: данные}."""
    return _snapshot_raw(timeout)[0]


@dataclass
class RevitDiff:
    """Расхождения открытой модели Revit с загруженным проектом."""
    source: str = ""                       # Spaces (MEP) / Rooms
    added: List[dict] = field(default_factory=list)    # есть в Revit, нет в проекте
    removed: List[dict] = field(default_factory=list)  # есть в проекте, нет в Revit
    changed: List[dict] = field(default_factory=list)  # площадь/объём/атрибуты разошлись
    unchanged: int = 0

    @property
    def in_sync(self) -> bool:
        return not self.added and not self.removed and not self.changed


def diff_with_project(project: "HVACProject", *, rel_tol: float = 0.02,
                      abs_tol_m2: float = 0.5,
                      timeout: float = 300.0) -> RevitDiff:
    """Сравнивает помещения открытой модели Revit с проектом.

    Изменённым считается помещение, у которого площадь или объём ушли
    больше чем на rel_tol (2%) И abs_tol (0.5 м²/м³), либо изменились
    номер/имя/уровень.
    """
    snap, source = _snapshot_raw(timeout=timeout)
    diff = RevitDiff(source=source)

    proj = {sp.space_id: sp for sp in project.spaces}
    for sid, r in snap.items():
        sp = proj.get(sid)
        if sp is None:
            diff.added.append({"id": sid, **r})
            continue
        changes = []
        for attr, key in (("number", "number"), ("name", "name"),
                          ("level", "level")):
            old = getattr(sp, attr, "") or ""
            new = r[key] or ""
            if old.strip() != new.strip():
                changes.append(f"{key}: {old!r} → {new!r}")
        for attr, key, unit in (("area_m2", "area_m2", "м²"),
                                ("volume_m3", "volume_m3", "м³")):
            old = float(getattr(sp, attr, 0.0) or 0.0)
            new = float(r[key])
            if (abs(new - old) > abs_tol_m2
                    and abs(new - old) > rel_tol * max(old, 1e-9)):
                changes.append(f"{key}: {old:.1f} → {new:.1f} {unit}")
        if changes:
            diff.changed.append({"id": sid, "number": r["number"],
                                 "name": r["name"], "what": changes})
        else:
            diff.unchanged += 1
    for sid, sp in proj.items():
        if sid not in snap:
            diff.removed.append({"id": sid, "number": sp.number,
                                 "name": sp.name, "level": sp.level})
    return diff


# ============================================================================
# Раскраска результатов в Revit (override графики активного вида)
# ============================================================================
# Python считает цвет каждого помещения (градиент синий→жёлтый→красный
# по выбранной метрике), пишет CSV id,r,g,b; C# в транзакции ставит
# заливку Solid Fill через SetElementOverrides активного вида.

COLOR_CS = r'''
string csvPath = (string)parameters[0];
var lines = System.IO.File.ReadAllLines(csvPath);
var view = document.ActiveView;
FillPatternElement solid = null;
foreach(FillPatternElement f in new FilteredElementCollector(document).OfClass(typeof(FillPatternElement))){try{if(f.GetFillPattern().IsSolidFill){solid=f;break;}}catch{}}
var col = new FilteredElementCollector(document).OfCategory(BuiltInCategory.OST_MEPSpaces).WhereElementIsNotElementType().ToElements();
if(col.Count==0) col = new FilteredElementCollector(document).OfCategory(BuiltInCategory.OST_Rooms).WhereElementIsNotElementType().ToElements();
var byId = new Dictionary<string,Element>();
foreach(var e in col){var k=e.Id.Value.ToString();if(!byId.ContainsKey(k))byId[k]=e;}
int done=0,missing=0,failed=0;
for(int i=1;i<lines.Length;i++){
if(string.IsNullOrWhiteSpace(lines[i]))continue;
var c=lines[i].Split(',');
if(c.Length<4)continue;
Element e;
if(!byId.TryGetValue(c[0].Trim(),out e)){missing++;continue;}
byte r,g,b;
if(!byte.TryParse(c[1],out r)||!byte.TryParse(c[2],out g)||!byte.TryParse(c[3],out b))continue;
var ogs=new OverrideGraphicSettings();
var clr=new Color(r,g,b);
ogs.SetSurfaceForegroundPatternColor(clr);
ogs.SetCutForegroundPatternColor(clr);
if(solid!=null){ogs.SetSurfaceForegroundPatternId(solid.Id);ogs.SetCutForegroundPatternId(solid.Id);}
try{view.SetElementOverrides(e.Id,ogs);done++;}catch{failed++;}}
return new{colored=done,missing=missing,failed=failed,view=view.Name};
'''

CLEAR_COLOR_CS = r'''
var view = document.ActiveView;
var col = new FilteredElementCollector(document).OfCategory(BuiltInCategory.OST_MEPSpaces).WhereElementIsNotElementType().ToElements();
if(col.Count==0) col = new FilteredElementCollector(document).OfCategory(BuiltInCategory.OST_Rooms).WhereElementIsNotElementType().ToElements();
int done=0;
var ogs=new OverrideGraphicSettings();
foreach(var e in col){try{view.SetElementOverrides(e.Id,ogs);done++;}catch{}}
return new{cleared=done,view=view.Name};
'''

#: Метрики раскраски: {ключ: функция(Space) → значение}
COLOR_METRICS = {
    "heating_w_m2": lambda sp: (sp.heat_loss_w / sp.area_m2
                                if sp.area_m2 > 0 else 0.0),
    "cooling_w_m2": lambda sp: (sp.heat_gain_w / sp.area_m2
                                if sp.area_m2 > 0 else 0.0),
    "ach": lambda sp: sp.ach_calculated,
}


def _gradient_color(v: float) -> tuple:
    """Синий (0) → жёлтый (0.5) → красный (1) для нормированного v."""
    v = max(0.0, min(1.0, v))
    lo, mid, hi = (59, 130, 246), (250, 204, 21), (239, 68, 68)
    if v < 0.5:
        t = v * 2.0
        a, b = lo, mid
    else:
        t = (v - 0.5) * 2.0
        a, b = mid, hi
    return tuple(round(a[i] + (b[i] - a[i]) * t) for i in range(3))


def color_spaces_in_revit(project: "HVACProject",
                          metric: str = "heating_w_m2",
                          timeout: float = 600.0) -> dict:
    """Раскрашивает помещения активного вида Revit по метрике расчёта.

    Нормировка — перцентили 5/95 по проекту (устойчивость к выбросам).
    Возвращает сводку C# + диапазон значений {vmin, vmax, metric}.
    """
    fn = COLOR_METRICS.get(metric)
    if fn is None:
        raise ValueError(f"Неизвестная метрика {metric!r}; "
                         f"доступны {sorted(COLOR_METRICS)}")
    values = [(sp.space_id, fn(sp)) for sp in project.spaces
              if sp.area_m2 > 0]
    if not values:
        raise ValueError("В проекте нет помещений с площадью — "
                         "нечего раскрашивать")
    ordered = sorted(v for _sid, v in values)
    vmin = ordered[int(len(ordered) * 0.05)]
    vmax = ordered[min(int(len(ordered) * 0.95), len(ordered) - 1)]
    span = max(vmax - vmin, 1e-9)

    lines = ["space_id,r,g,b"]
    for sid, v in values:
        r, g, b = _gradient_color((v - vmin) / span)
        lines.append(f"{sid},{r},{g},{b}")

    fd, csv_path = tempfile.mkstemp(suffix=".csv", prefix="hvac_color_")
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as f:
            f.write("\n".join(lines))
        res = send_code(COLOR_CS, parameters=[csv_path],
                        transaction_mode="auto", timeout=timeout)
    finally:
        try:
            os.remove(csv_path)
        except OSError:
            pass
    if not isinstance(res, dict):
        raise RuntimeError(f"Неожиданный ответ Revit: {res!r}")
    res.update({"metric": metric, "vmin": round(vmin, 1),
                "vmax": round(vmax, 1)})
    return res


def clear_space_colors_in_revit(timeout: float = 600.0) -> dict:
    """Сбрасывает раскраску помещений активного вида Revit."""
    res = send_code(CLEAR_COLOR_CS, transaction_mode="auto",
                    timeout=timeout)
    if not isinstance(res, dict):
        raise RuntimeError(f"Неожиданный ответ Revit: {res!r}")
    return res


# ============================================================================
# Импорт оборудования помещений (решётки/диффузоры, фанкойлы, радиаторы)
# ============================================================================
# Read-only проход по расставленным FamilyInstance трёх категорий:
#   T = Воздухораспределители (OST_DuctTerminal),
#   M = Механическое оборудование (OST_MechanicalEquipment),
#   S = Прочее оборудование (OST_SpecialityEquipment).
# Помещение — через FamilyInstance.Space/.Room; расход — RBS_DUCT_FLOW_PARAM
# (м³/ч), мощности — типовые параметры тепло/холодопроизводительности (Вт).
# Ответ — TSV одной строкой (лимит 8 КБ касается только запроса).

EQUIPMENT_CS = r'''
var CI = System.Globalization.CultureInfo.InvariantCulture;
string Cl(string s){if(s==null)return "";return s.Replace('\t',' ').Replace('\n',' ').Replace('\r',' ');}
string Nm(double v){return Math.Round(v,1).ToString("0.#",CI);}
double Pw(Element e,Element te,string[] ns){
foreach(var el in new Element[]{e,te}){
if(el==null)continue;
foreach(var n in ns){
Parameter p=null;try{p=el.LookupParameter(n);}catch{}
if(p==null||p.StorageType!=StorageType.Double)continue;
double v=0;try{v=p.AsDouble();}catch{continue;}
if(v<=0)continue;
try{var dt=p.Definition.GetDataType();if(UnitUtils.IsMeasurableSpec(dt))return UnitUtils.ConvertFromInternalUnits(v,UnitTypeId.Watts);}catch{}
return v;}}
return 0;}
var cats=new[]{BuiltInCategory.OST_DuctTerminal,BuiltInCategory.OST_MechanicalEquipment,BuiltInCategory.OST_SpecialityEquipment};
var codes=new[]{"T","M","S"};
var hn=new[]{"Heating Capacity","Total Heating Capacity","Теплопроизводительность","Тепловая мощность","Номинальная тепловая мощность"};
var cn=new[]{"Total Cooling Capacity","Cooling Capacity","Холодопроизводительность","Холодильная мощность"};
var sb=new System.Text.StringBuilder();
int total=0,nospace=0;
for(int ci=0;ci<cats.Length;ci++){
foreach(Element e in new FilteredElementCollector(document).OfCategory(cats[ci]).WhereElementIsNotElementType()){
var fi=e as FamilyInstance;
if(fi==null||fi.SuperComponent!=null)continue;
string sid="";
try{var s2=fi.Space;if(s2!=null)sid=s2.Id.Value.ToString(CI);}catch{}
if(sid==""){try{var r2=fi.Room;if(r2!=null)sid=r2.Id.Value.ToString(CI);}catch{}}
Element te=null;try{te=document.GetElement(fi.GetTypeId());}catch{}
string fam="",tn="";
var ty=te as ElementType;
if(ty!=null){try{fam=ty.FamilyName??"";}catch{}try{tn=ty.Name??"";}catch{}}
string fl="";
try{var p=fi.get_Parameter(BuiltInParameter.RBS_DUCT_FLOW_PARAM);if(p!=null&&p.StorageType==StorageType.Double){double v=p.AsDouble();if(v>0)fl=Nm(UnitUtils.ConvertFromInternalUnits(v,UnitTypeId.CubicMetersPerHour));}}catch{}
string sc="";
try{var p=fi.get_Parameter(BuiltInParameter.RBS_SYSTEM_CLASSIFICATION_PARAM);if(p!=null){sc=p.AsString()??"";if(sc=="")sc=p.AsValueString()??"";}}catch{}
string sn="";
try{var p=fi.get_Parameter(BuiltInParameter.RBS_SYSTEM_NAME_PARAM);if(p!=null){sn=p.AsString()??"";if(sn=="")sn=p.AsValueString()??"";}}catch{}
double hw=Pw(fi,te,hn),cw=Pw(fi,te,cn);
if(sid=="")nospace++;
sb.Append(codes[ci]).Append('\t').Append(sid).Append('\t').Append(Cl(fam)).Append('\t').Append(Cl(tn)).Append('\t').Append(fl).Append('\t').Append(Cl(sc)).Append('\t').Append(Cl(sn)).Append('\t').Append(hw>0?Nm(hw):"").Append('\t').Append(cw>0?Nm(cw):"").Append('\n');
total++;}}
return new{count=total,no_space=nospace,data=sb.ToString()};
'''


def snapshot_equipment(timeout: float = 300.0) -> List[dict]:
    """Снимок расставленного оборудования открытой модели Revit.

    Каждая строка: {cat: T/M/S, space_id, family, type, flow_m3h,
    sys_class, sys_name, heat_w, cool_w}.
    """
    res = send_code(EQUIPMENT_CS, transaction_mode="none", timeout=timeout)
    if not isinstance(res, dict) or "data" not in res:
        raise RuntimeError(f"Неожиданный ответ Revit: {res!r}")

    def _f(s: str) -> float:
        try:
            return float(s)
        except ValueError:
            return 0.0

    rows: List[dict] = []
    for line in str(res["data"]).splitlines():
        parts = line.split("\t")
        if len(parts) < 9:
            continue
        rows.append({
            "cat": parts[0], "space_id": parts[1],
            "family": parts[2], "type": parts[3],
            "flow_m3h": _f(parts[4]),
            "sys_class": parts[5], "sys_name": parts[6],
            "heat_w": _f(parts[7]), "cool_w": _f(parts[8]),
        })
    return rows


# ---------------------------------------------------------------------------
# Классификация: семейство/тип Revit → слот и тип RoomEquipment
# ---------------------------------------------------------------------------

def _norm(s: str) -> str:
    return (s or "").lower().replace("ё", "е")


_EXHAUST_CLASS_KW = ("вытяж", "отработ", "exhaust", "return",
                     "возврат", "рецирк")
_SUPPLY_CLASS_KW = ("приточ", "supply")


def _terminal_slot(row: dict, text: str) -> str:
    """Приток или вытяжка: классификация системы → имя системы → имя."""
    sc = _norm(row.get("sys_class", ""))
    if any(k in sc for k in _EXHAUST_CLASS_KW):
        return "exhaust"
    if any(k in sc for k in _SUPPLY_CLASS_KW):
        return "supply"
    sn = (row.get("sys_name") or "").strip().upper()
    if sn[:1] in ("П", "P"):
        return "supply"
    if sn[:1] in ("В", "У", "V", "U", "E"):
        return "exhaust"
    if "вытяж" in text or "exhaust" in text:
        return "exhaust"
    return "supply"


def _air_terminal_type(text: str, slot: str) -> str:
    """Тип из SUPPLY/EXHAUST_TERMINAL_TYPES по ключевым словам имени."""
    if "анемостат" in text:
        return "Анемостат"
    is_ceiling = "потолоч" in text or "ceiling" in text
    if slot == "exhaust":
        if "зонт" in text:
            return "Зонт кухонный"
        if "клапан" in text:
            return ("Клапан вытяжной квадратный"
                    if "квадрат" in text or "прямоуг" in text
                    else "Клапан вытяжной круглый")
        if "дроссель" in text:
            return "Решётка с дроссель-клапаном"
        return "Решётка потолочная" if is_ceiling else "Решётка настенная"
    if "сопло" in text or "jet" in text:
        return "Сопло поворотное"
    if "перфор" in text:
        return "Перфорированная панель"
    if "вытесн" in text or "displacement" in text:
        return "Вытесняющий диффузор"
    if "решетк" in text or "grille" in text:
        return "Решётка потолочная" if is_ceiling else "Решётка настенная"
    if "вихр" in text or "swirl" in text:
        return "Диффузор вихревой"
    if "щелев" in text or "slot" in text or "линейн" in text:
        return "Диффузор щелевой"
    if "струйн" in text:
        return "Диффузор струйный"
    if "диффузор" in text or "diffuser" in text:
        return ("Диффузор круглый"
                if "кругл" in text or "round" in text or "dn" in text
                else "Диффузор квадратный")
    return "Решётка настенная"


def _cooling_type(text: str) -> Optional[str]:
    # «2/4 pipes» — типовое именование фанкойлов у производителей
    # (например Clint DWX 4 PIPES) без слова «фанкойл» в семействе.
    four_pipe = ("4-труб" in text or "четырехтруб" in text
                 or "4 труб" in text or "4 pipe" in text
                 or "4-pipe" in text)
    if ("фанкойл" in text or "fancoil" in text or "fan coil" in text
            or "fcu" in text or four_pipe or "2 pipe" in text
            or "2-pipe" in text):
        if four_pipe:
            return "Фанкойл (отопл.+охл.)"
        if "канал" in text or "duct" in text:
            return "Фанкойл канальный"
        if "настен" in text or "wall" in text:
            return "Фанкойл настенный"
        if "наполь" in text or "floor" in text:
            return "Фанкойл напольный"
        return "Фанкойл кассетный"
    if "vrf" in text or "vrv" in text or "врф" in text:
        if "канал" in text or "duct" in text:
            return "Внутр. блок VRF канальный"
        if "настен" in text or "wall" in text:
            return "Внутр. блок VRF настенный"
        return "Внутр. блок VRF кассетный"
    if "сплит" in text or "split" in text:
        return ("Сплит-система кассетная" if "кассет" in text
                else "Сплит-система настенная")
    if "chilled beam" in text or ("балк" in text and "охлажд" in text):
        return "Охлаждаемая балка"
    if "прецизион" in text or "precision" in text:
        return "Прецизионный кондиционер"
    return None


def _heating_type(text: str) -> Optional[str]:
    if "радиатор" in text or "radiator" in text:
        if "биметал" in text:
            return "Радиатор биметаллический"
        if "алюмин" in text or "alumin" in text:
            return "Радиатор алюминиевый"
        if "чугун" in text or "cast iron" in text:
            return "Радиатор чугунный"
        return "Радиатор стальной"
    if "конвектор" in text or "convector" in text:
        if ("внутрипольн" in text or "встраив" in text or "наполь" in text
                or "trench" in text or "floor" in text):
            return "Конвектор внутрипольный"
        return "Конвектор настенный"
    if "завес" in text or "air curtain" in text:
        return "Тепловая завеса"
    if "инфракрасн" in text or "infrared" in text:
        return "Инфракрасный обогреватель"
    return None


def classify_equipment_row(row: dict) -> Optional[tuple]:
    """Строка снимка → (слот, тип RoomEquipment) или None.

    Слоты: supply / exhaust / heating / cooling — четыре группы полей
    hvac.room_equipment.RoomEquipment.
    """
    text = _norm(row.get("family", "") + " " + row.get("type", ""))
    if row.get("cat") == "T":
        slot = _terminal_slot(row, text)
        return slot, _air_terminal_type(text, slot)
    cool = _cooling_type(text)
    if cool:
        return "cooling", cool
    heat = _heating_type(text)
    if heat:
        return "heating", heat
    # Кухонные зонты часто расставлены как механическое оборудование
    if "зонт" in text or "hood" in text:
        return "exhaust", "Зонт кухонный"
    return None


# ---------------------------------------------------------------------------
# План импорта (фоновый поток) и применение к проекту (главный поток)
# ---------------------------------------------------------------------------

#: слот → префикс полей RoomEquipment
_SLOT_PREFIX = {"heating": "heating_terminal", "cooling": "cooling_terminal",
                "supply": "supply_terminal", "exhaust": "exhaust_terminal"}


@dataclass
class EquipmentImportPlan:
    """Результат разбора снимка оборудования до записи в проект."""
    total: int = 0            # классифицированных экземпляров в модели
    no_space: int = 0         # вне помещений (не привязать)
    unmatched: int = 0        # помещение есть в Revit, но не в проекте
    skipped_other: int = 0    # прочее оборудование без ключевых слов
    by_slot: Dict[str, int] = field(default_factory=dict)
    updates: Dict[str, dict] = field(default_factory=dict)  # space_id → поля
    assigned: List[dict] = field(default_factory=list)      # для отчёта
    unrecognized: List[str] = field(default_factory=list)   # мех. без слота

    @property
    def has_updates(self) -> bool:
        return bool(self.updates)


def plan_equipment_import(project: "HVACProject", rows: Optional[List[dict]]
                          = None, timeout: float = 300.0
                          ) -> EquipmentImportPlan:
    """Снимок оборудования Revit → план заполнения RoomEquipment.

    Ничего не меняет ни в проекте, ни в модели — применение отдельно
    (apply_equipment_import), чтобы UI мог мутировать проект в главном
    потоке. На помещение и слот: количество = все экземпляры слота,
    модель/тип — преобладающие, расход/мощность — среднее по ненулевым.
    """
    if rows is None:
        rows = snapshot_equipment(timeout=timeout)
    plan = EquipmentImportPlan()
    proj = {sp.space_id: sp for sp in project.spaces}
    unrec: set = set()
    # (space_id, слот) → типы/модели Counter, ненулевые значения
    buckets: Dict[tuple, dict] = {}
    for row in rows:
        cls = classify_equipment_row(row)
        if cls is None:
            if row.get("cat") == "M":
                label = (row.get("family", "") + " "
                         + row.get("type", "")).strip()
                if label:
                    unrec.add(label)
            else:
                plan.skipped_other += 1
            continue
        plan.total += 1
        sid = row.get("space_id", "")
        if not sid:
            plan.no_space += 1
            continue
        if sid not in proj:
            plan.unmatched += 1
            continue
        slot, ttype = cls
        plan.by_slot[slot] = plan.by_slot.get(slot, 0) + 1
        b = buckets.setdefault((sid, slot), {
            "types": Counter(), "models": Counter(), "values": []})
        b["types"][ttype] += 1
        model = (row.get("family", "") + " " + row.get("type", "")).strip()
        if model:
            b["models"][model] += 1
        value = (row.get("flow_m3h", 0.0) if slot in ("supply", "exhaust")
                 else row.get("cool_w", 0.0) if slot == "cooling"
                 else row.get("heat_w", 0.0))
        if value > 0:
            b["values"].append(value)
    for (sid, slot), b in buckets.items():
        prefix = _SLOT_PREFIX[slot]
        qty = sum(b["types"].values())
        ttype = b["types"].most_common(1)[0][0]
        model = (b["models"].most_common(1)[0][0] if b["models"] else "")
        mean = (round(sum(b["values"]) / len(b["values"]), 1)
                if b["values"] else 0.0)
        fields = {f"{prefix}_type": ttype, f"{prefix}_model": model,
                  f"{prefix}_qty": qty}
        if slot in ("supply", "exhaust"):
            fields[f"{prefix}_flow_m3h"] = mean
        else:
            fields[f"{prefix}_power_w"] = mean
        plan.updates.setdefault(sid, {}).update(fields)
        sp = proj[sid]
        plan.assigned.append({
            "space_id": sid, "number": sp.number, "name": sp.name,
            "slot": slot, "type": ttype, "model": model, "qty": qty,
            "value": mean})
    plan.assigned.sort(key=lambda r: (r["number"], r["slot"]))
    plan.unrecognized = sorted(unrec)
    return plan


def apply_equipment_import(project: "HVACProject",
                           plan: EquipmentImportPlan) -> int:
    """Записывает план в Space.room_equipment. Возвращает число помещений.

    Затрагиваются только слоты, найденные в Revit; остальные поля
    оборудования помещения не трогаются. equipment_changed эмитится
    один раз.
    """
    by_id = {sp.space_id: sp for sp in project.spaces}
    n = 0
    for sid, fields in plan.updates.items():
        sp = by_id.get(sid)
        if sp is None:
            continue
        eq = sp.get_or_create_equipment()
        for k, v in fields.items():
            if hasattr(eq, k):
                setattr(eq, k, v)
        n += 1
    if n:
        project.emit("equipment_changed")
    return n


# ============================================================================
# Лучевая проверка фасадов по живой модели (read-only)
# ============================================================================
# Эвристики выгрузки (bsc/rbc/толщина/имя) не видят, ЧТО за стеной:
# стена к лифтовой шахте и настоящий фасад выглядят одинаково (bsc=1).
# Здесь — прямая геометрия: от середины стены лучом наружу до 8 м через
# Document.GetSpaceAtPoint. Нашлось отапливаемое пространство (балконы,
# шахты и террасы отфильтрованы) — стена внутренняя, за ней не улица.
# Список element_id передаётся ФАЙЛОМ (запрос ограничен 8 КБ), ответ —
# TSV без ограничений. Элемент ищется в хост-модели и во всех связях.

FACADE_PROBE_CS = r'''
string path=(string)parameters[0];
var CI=System.Globalization.CultureInfo.InvariantCulture;
string S(Element e,BuiltInParameter b){var p=e.get_Parameter(b);if(p==null)return "";if(p.StorageType==StorageType.String)return p.AsString()??"";return p.AsValueString()??"";}
bool Unc(Element sp){
string nu=(S(sp,BuiltInParameter.ROOM_NUMBER)??"").Trim().ToUpperInvariant();
foreach(var px in new[]{"OFC-","BAL-","TER-","SHAFT","ШАХТ"})if(nu.StartsWith(px))return true;
string full=(nu+" "+(S(sp,BuiltInParameter.ROOM_NAME)??"")).ToLowerInvariant();
foreach(var kw in new[]{"балкон","терраса","лоджия","balcony","terrace","loggia","shaft","open air"})if(full.Contains(kw))return true;
return false;}
Autodesk.Revit.DB.Mechanical.Space Cond(XYZ p){
Autodesk.Revit.DB.Mechanical.Space s=null;
try{s=document.GetSpaceAtPoint(p);}catch{}
if(s==null)return null;
return Unc(s)?null:s;}
var docs=new List<object[]>();
docs.Add(new object[]{document,null});
foreach(Element e in new FilteredElementCollector(document).OfClass(typeof(RevitLinkInstance))){
var li=e as RevitLinkInstance;Document ld=null;try{ld=li.GetLinkDocument();}catch{}
if(ld==null)continue;
Transform tr=null;try{tr=li.GetTotalTransform();}catch{}
docs.Add(new object[]{ld,tr});}
var sb=new System.Text.StringBuilder();
int nf=0,nw=0,fa=0,it=0,ns=0;
foreach(var line in System.IO.File.ReadAllLines(path)){
string ids=line.Trim();if(ids=="")continue;
long id;if(!long.TryParse(ids,System.Globalization.NumberStyles.Any,CI,out id))continue;
Wall w=null;Transform tr=null;bool found=false;
foreach(var o in docs){
Element el=null;try{el=((Document)o[0]).GetElement(new ElementId(id));}catch{}
if(el==null)continue;
found=true;
var ww=el as Wall;if(ww!=null){w=ww;tr=(Transform)o[1];break;}}
if(w==null){if(found){nw++;sb.Append(ids).Append("\tNOTWALL\t\t\n");}else{nf++;sb.Append(ids).Append("\tNOTFOUND\t\t\n");}continue;}
XYZ mid=null,n=null;
try{var c=(w.Location as LocationCurve).Curve;
var a=c.GetEndPoint(0);var b=c.GetEndPoint(1);
mid=new XYZ((a.X+b.X)*0.5,(a.Y+b.Y)*0.5,(a.Z+b.Z)*0.5+4.0);
n=w.Orientation;
if(tr!=null){mid=tr.OfPoint(mid);n=tr.OfVector(n);}}catch{}
if(mid==null||n==null){nw++;sb.Append(ids).Append("\tNOTWALL\t\t\n");continue;}
var sA=Cond(new XYZ(mid.X+n.X,mid.Y+n.Y,mid.Z));
var sB=Cond(new XYZ(mid.X-n.X,mid.Y-n.Y,mid.Z));
if(sA!=null&&sB!=null){it++;sb.Append(ids).Append("\tINTERIOR\t").Append(S(sB,BuiltInParameter.ROOM_NUMBER)).Append("\t0.3\n");continue;}
if(sA==null&&sB==null){ns++;sb.Append(ids).Append("\tNOSPACE\t\t\n");continue;}
double sg=sA!=null?-1.0:1.0;
string hit="",hd="";
foreach(var m in new[]{1.0,1.5,2.0,3.0,4.0,6.0,8.0}){
double ft=m*3.28084;
var s=Cond(new XYZ(mid.X+sg*ft*n.X,mid.Y+sg*ft*n.Y,mid.Z));
if(s!=null){hit=S(s,BuiltInParameter.ROOM_NUMBER);hd=m.ToString("0.0",CI);break;}}
if(hit==""){fa++;sb.Append(ids).Append("\tFACADE\t\t\n");}
else{it++;sb.Append(ids).Append("\tINTERIOR\t").Append(hit).Append('\t').Append(hd).Append('\n');}}
return new{walls=fa+it+ns,facade=fa,interior=it,nospace=ns,notfound=nf,notwall=nw,data=sb.ToString()};
'''


def probe_facades(element_ids, timeout: float = 600.0) -> Dict[str, dict]:
    """Лучевая проверка стен по id: {id: {verdict, hit, dist_m}}.

    verdict: FACADE (за стеной пусто до 8 м — улица), INTERIOR (нашлось
    отапливаемое пространство), NOSPACE (стена не у пространств),
    NOTFOUND / NOTWALL (нет в модели / не стена).
    """
    ids = [str(i).strip() for i in element_ids if str(i).strip()]
    fd, path = tempfile.mkstemp(suffix=".txt", prefix="hvac_probe_")
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as f:
            f.write("\n".join(ids))
        res = send_code(FACADE_PROBE_CS, parameters=[path],
                        transaction_mode="none", timeout=timeout)
    finally:
        try:
            os.remove(path)
        except OSError:
            pass
    if not isinstance(res, dict) or "data" not in res:
        raise RuntimeError(f"Неожиданный ответ Revit: {res!r}")
    out: Dict[str, dict] = {}
    for line in str(res["data"]).splitlines():
        parts = line.split("\t")
        if len(parts) < 4:
            continue
        try:
            dist = float(parts[3]) if parts[3] else 0.0
        except ValueError:
            dist = 0.0
        out[parts[0]] = {"verdict": parts[1], "hit": parts[2],
                         "dist_m": dist}
    return out


@dataclass
class FacadeCheckPlan:
    """Результат лучевой проверки до записи в проект."""
    checked: int = 0          # уникальных стен отправлено на проверку
    facades: int = 0          # подтверждены наружными
    no_geometry: int = 0      # NOSPACE / NOTFOUND / NOTWALL — не трогаем
    pairs: List[tuple] = field(default_factory=list)   # (space_id, element_id)
    to_interior: List[dict] = field(default_factory=list)  # для отчёта

    @property
    def has_updates(self) -> bool:
        return bool(self.pairs)


def plan_facade_check(project: "HVACProject",
                      verdicts: Optional[Dict[str, dict]] = None,
                      timeout: float = 600.0) -> FacadeCheckPlan:
    """Проверяет все «наружные» стены проекта лучом по живой модели.

    Ничего не меняет — применение отдельно (apply_facade_check, главный
    поток). Стена с вердиктом INTERIOR переводится во внутренние вместе
    со своими проёмами (host_element_id).
    """
    wall_ids: List[str] = []
    seen: set = set()
    for e in project.elements:
        if (e.row_type == "external_wall" and e.is_exterior
                and e.element_id and e.element_id not in seen):
            seen.add(e.element_id)
            wall_ids.append(e.element_id)
    plan = FacadeCheckPlan(checked=len(wall_ids))
    if not wall_ids:
        return plan
    if verdicts is None:
        verdicts = probe_facades(wall_ids, timeout=timeout)
    interior: Dict[str, dict] = {}
    for eid in wall_ids:
        v = verdicts.get(eid)
        if v is None:
            plan.no_geometry += 1
        elif v["verdict"] == "INTERIOR":
            interior[eid] = v
        elif v["verdict"] == "FACADE":
            plan.facades += 1
        else:
            plan.no_geometry += 1
    if not interior:
        return plan
    sid_to_sp = {sp.space_id: sp for sp in project.spaces}
    for e in project.elements:
        if not e.is_exterior or e.row_type not in ("external_wall",
                                                   "opening"):
            continue
        key = (e.element_id if e.row_type == "external_wall"
               else e.host_element_id)
        v = interior.get(key)
        if v is None:
            continue
        plan.pairs.append((e.space_id, e.element_id))
        sp = sid_to_sp.get(e.space_id)
        plan.to_interior.append({
            "number": sp.number if sp else "", "name": sp.name if sp else "",
            "family": e.family, "type": e.type_name,
            "area_m2": e.approx_area_m2 or e.element_area_m2 or 0.0,
            "hit": v["hit"], "dist_m": v["dist_m"]})
    plan.to_interior.sort(key=lambda r: r["number"])
    return plan


def apply_facade_check(project: "HVACProject", plan: FacadeCheckPlan) -> int:
    """Переводит ложные «фасады» во внутренние и пересчитывает проект.

    Использует set_elements_exterior — изменения сохраняются в проект
    как element_overrides и переживают сохранение/открытие.
    """
    n = project.set_elements_exterior(plan.pairs, False)
    if n:
        project.recalculate()
    return n


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
