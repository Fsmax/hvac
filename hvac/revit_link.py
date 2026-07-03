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

import csv
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
            except UnicodeDecodeError:
                # chunk оборвал многобайтовый UTF-8 символ (кириллица на
                # границе recv) — ответ ещё не дочитан, копим дальше
                continue
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
bool shortWall=isWall&&len>=0&&len<0.5;
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
if(!shortWall)Row(new[]{sid,sn,sm,sl,"external_wall",ext?"yes":"no",el.Id.Value.ToString(CI),ln,cat,ti[0],ti[1],Lv(el),len>=0?Nm(len):"",sh,(len>=0&&shd>0)?Nm(len*shd):"",EA(el),ti[4],ti[2],ti[3],"",bc.ToString(CI),orient});
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


# ============================================================================
# Чистая геометрическая привязка фасадного остекления (заменяет orphan-проход)
# ============================================================================
# Для каждой навесной стены (Curtain, без внутренних типов) из АВТОРИТЕТНОГО
# источника блока сэмплит фронт (11 точек × обе стороны, марш вглубь сквозь
# балкон до отапл. комнаты) и раскидывает реальную HOST_AREA по комнатам
# пропорционально доле попавших точек. Это убивает двойной учёт (один источник
# на физ. фасад), завышение (площадь по фронту, а не целиком в каждую комнату)
# и чинит подиум (storefront без Room Bounding достаёт залы за ним).
#
# Источник по блокам (подтверждено по модели Chorsu, 2026-06-21):
#   отель/подиум → FCD (CHR_Balcony / CHR_Storefront),
#   офис/резиденции → ARC (GLZ-O* / M_Exterior Glazing).
# parameters[0] = имя уровня (подстрока), parameters[1] = токены через запятую.
GLAZING_SOURCE_TOKENS = ["FCD-00-HTL", "FCD-00-BMG", "ARC-00-OFF", "ARC-00-RES"]

CLEAN_GLAZING_CS = r'''
string lvl=(string)parameters[0];
string toks=(string)parameters[1];
var CI=System.Globalization.CultureInfo.InvariantCulture;
var sps=new List<Autodesk.Revit.DB.Mechanical.Space>();
var bbs=new List<BoundingBoxXYZ>();
var unc=new List<bool>();
foreach(Element e in new FilteredElementCollector(document).OfCategory(BuiltInCategory.OST_MEPSpaces).WhereElementIsNotElementType()){
var sp=e as Autodesk.Revit.DB.Mechanical.Space;if(sp==null)continue;
var ap=sp.get_Parameter(BuiltInParameter.ROOM_AREA);if(ap==null||ap.AsDouble()<=1e-6)continue;
string ln="";try{var l=document.GetElement(sp.LevelId);if(l!=null)ln=l.Name??"";}catch{}
if(lvl!=""&&!ln.Contains(lvl))continue;
var bb=sp.get_BoundingBox(null);if(bb==null)continue;
string nu="";try{var pn=sp.get_Parameter(BuiltInParameter.ROOM_NUMBER);if(pn!=null)nu=(pn.AsString()??"").ToUpperInvariant();}catch{}
bool uc=nu.StartsWith("OFC-")||nu.StartsWith("BAL-")||nu.StartsWith("TER-")||nu.StartsWith("SHAFT");
sps.Add(sp);bbs.Add(bb);unc.Add(uc);}
var sb=new System.Text.StringBuilder();
if(sps.Count==0)return sb.ToString();
double tn0=0;try{var pos=document.ActiveProjectLocation.GetProjectPosition(XYZ.Zero);if(pos!=null)tn0=pos.Angle;}catch{}
double ca=Math.Cos(tn0),sa=Math.Sin(tn0);
string[] intkw=new[]{"interior","partition","перегород","внутрен","separator","разделит","empty","not defined","shower","душ","кабин","cabin","core","balustrade","ограждени","перил"};
double FT=0.092903040;double OFF=1.6404;int N=11;
foreach(var tok in toks.Split(',')){
Document ld=null;Transform tf=Transform.Identity;
foreach(Element e in new FilteredElementCollector(document).OfClass(typeof(RevitLinkInstance))){
var li=e as RevitLinkInstance;if(li==null)continue;string nm=li.Name??"";if(!nm.Contains(tok))continue;
try{ld=li.GetLinkDocument();tf=li.GetTotalTransform();}catch{}if(ld!=null)break;}
if(ld==null)continue;
foreach(Element e in new FilteredElementCollector(ld).OfCategory(BuiltInCategory.OST_Walls).WhereElementIsNotElementType()){
var w=e as Wall;if(w==null)continue;
string tnm="";string kind="";
try{var t=ld.GetElement(w.GetTypeId());if(t!=null){tnm=t.Name??"";var wt=t as WallType;if(wt!=null)kind=wt.Kind.ToString();}}catch{}
if(kind!="Curtain")continue;
string low=tnm.ToLowerInvariant();bool bad=false;foreach(var k in intkw)if(low.Contains(k)){bad=true;break;}if(bad)continue;
double area=0;try{var p=w.get_Parameter(BuiltInParameter.HOST_AREA_COMPUTED);if(p!=null&&p.StorageType==StorageType.Double)area=p.AsDouble();}catch{}if(area<=0)continue;
Curve cv=null;try{var lc=w.Location as LocationCurve;if(lc!=null)cv=lc.Curve;}catch{}if(cv==null)continue;
XYZ nrm=null;try{nrm=w.Orientation;}catch{}if(nrm==null)continue;
XYZ ng=tf.OfVector(nrm);double nl=Math.Sqrt(ng.X*ng.X+ng.Y*ng.Y+ng.Z*ng.Z);if(nl<1e-9)continue;ng=new XYZ(ng.X/nl,ng.Y/nl,ng.Z/nl);
var tally=new Dictionary<int,int>();
for(int i=0;i<N;i++){
double t=(double)i/(N-1);
XYZ pl;try{pl=cv.Evaluate(t,true);}catch{continue;}
XYZ pg=tf.OfPoint(pl);
int hit=-1;double hd=1e9;
double[] steps=new[]{1.6404,4.9213,8.2021};
for(int s=0;s<2;s++){
double sign=s==0?1.0:-1.0;
for(int si=0;si<steps.Length;si++){
double st=steps[si];
XYZ q=new XYZ(pg.X+sign*st*ng.X,pg.Y+sign*st*ng.Y,pg.Z);
int found=-1;
for(int j=0;j<sps.Count;j++){
var bb=bbs[j];
if(q.X<bb.Min.X-OFF||q.X>bb.Max.X+OFF||q.Y<bb.Min.Y-OFF||q.Y>bb.Max.Y+OFF||q.Z<bb.Min.Z-OFF||q.Z>bb.Max.Z+OFF)continue;
bool ins=false;try{ins=sps[j].IsPointInSpace(q);}catch{}
if(ins){found=j;break;}}
if(found<0)continue;
if(unc[found])continue;
if(st<hd){hd=st;hit=found;}
break;}}
if(hit>=0){int c;tally.TryGetValue(hit,out c);tally[hit]=c+1;}}
if(tally.Count==0)continue;
double am2=area*FT;
double rx=ng.X*ca+ng.Y*sa,ry=-ng.X*sa+ng.Y*ca;
double az=Math.Atan2(rx,ry)*180.0/Math.PI;if(az<0)az+=360.0;
foreach(var kv in tally){
double a=am2*((double)kv.Value/N);
var sp=sps[kv.Key];
sb.Append(sp.Id.Value.ToString(CI));sb.Append('\t');sb.Append(w.Id.Value.ToString(CI));sb.Append('\t');
sb.Append(tok);sb.Append('\t');sb.Append(tnm.Replace('\t',' '));sb.Append('\t');
sb.Append(a.ToString("0.00",CI));sb.Append('\t');sb.Append(az.ToString("0.0",CI));sb.Append('\n');}}}
return sb.ToString();
'''


def export_clean_glazing(folder: str, timeout: float = 180.0) -> List[dict]:
    """Чистые строки остекления (по одному уровню за вызов моста).

    Читает spaces.csv в folder (уровни + номер/имя помещения), гоняет
    CLEAN_GLAZING_CS по каждому уровню и возвращает список dict-строк в
    схеме thermal_all. function='curtain (orphan)' → загрузчик доверяет им
    как фасаду, минуя bsc-эвристики (иначе поделённый по комнатам фасад
    с bsc>=2 был бы помечен внутренним).
    """
    folder = str(folder)
    sp_by_id: Dict[str, tuple] = {}
    levels: List[str] = []
    seen_lvl = set()
    with open(os.path.join(folder, "spaces.csv"),
              encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            sid = (row.get("id") or "").strip()
            lvl = (row.get("level") or "").strip()
            sp_by_id[sid] = (row.get("number", ""), row.get("name", ""), lvl)
            if lvl and lvl not in seen_lvl:
                seen_lvl.add(lvl)
                levels.append(lvl)
    toks = ",".join(GLAZING_SOURCE_TOKENS)
    rows: List[dict] = []
    for lvl in levels:
        res = send_code(CLEAN_GLAZING_CS, parameters=[lvl, toks],
                        transaction_mode="none", timeout=timeout)
        text = res if isinstance(res, str) else (str(res) if res else "")
        for line in text.splitlines():
            p = line.split("\t")
            if len(p) < 6:
                continue
            num, name, splvl = sp_by_id.get(p[0].strip(), ("", "", lvl))
            rows.append({
                "space_id": p[0].strip(), "space_number": num,
                "space_name": name, "space_level": splvl or lvl,
                "row_type": "external_wall", "is_exterior_wall": "yes",
                "element_id": p[1], "link_model": p[2], "category": "Стены",
                "family": "Витраж", "type": p[3], "element_level": lvl,
                "boundary_length_m": "", "space_height_m": "",
                "approx_area_m2": p[4], "element_area": p[4], "thickness": "",
                "function": "curtain (orphan)", "thermal_value": "",
                "host_element_id": "", "boundary_space_count": "1",
                "orientation_deg": p[5], "room_boundary_count": "0",
            })
    return rows


def rebuild_thermal_clean(folder: str, timeout: float = 180.0) -> dict:
    """Пересобирает thermal_all.csv с чистым остеклением.

    Выбрасывает ВСЕ строки навесных стен (family содержит «Витраж»/curtain:
    фасад, перегородки, душевые, ядро, старые orphan/boundary-привязки) и
    дописывает чистые строки из export_clean_glazing. Глухие стены, спандрел
    (Базовая стена), окна, двери, проёмы — сохраняются без изменений.
    """
    folder = str(folder)
    thermal_csv = os.path.join(folder, "thermal_all.csv")
    with open(thermal_csv, encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        fieldnames = list(reader.fieldnames or [])
        kept: List[dict] = []
        dropped = 0
        for row in reader:
            fam = (row.get("family", "") or "").lower()
            if "витраж" in fam or "curtain" in fam:
                dropped += 1
                continue
            kept.append(row)
    clean = export_clean_glazing(folder, timeout=timeout)
    for c in clean:
        for k in c:
            if k not in fieldnames:
                fieldnames.append(k)
    with open(thermal_csv, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        for row in kept:
            w.writerow({k: row.get(k, "") for k in fieldnames})
        for c in clean:
            w.writerow({k: c.get(k, "") for k in fieldnames})
    return {"clean_glazing_rows": len(clean), "dropped_curtain_rows": dropped,
            "total_rows": len(kept) + len(clean)}


# ============================================================================
# Геометрический тест внешней стороны глухих стен (внутр. как наружная)
# ============================================================================
# Для каждой глухой (не Curtain) граничной стены ОТАПЛИВАЕМОГО помещения
# сэмплит ВНЕШНЮЮ сторону и проверяет, не лежит ли там другое ОТАПЛИВАЕМОЕ
# помещение — MEP-пространство ИЛИ ARC-комната (коридоры/ядра/лестницы без
# MEP). Если да → verdict "int" (внутренняя перегородка), даже если bsc/
# функция/rbc считают её наружной (другой face стены — иной element_id, и
# счётчики по element_id промахиваются). Ловит толстые стены ядра/лестниц,
# типизированные как «Наружные». parameters[0]=уровень, [1]=ARC-токены.
ARC_ROOM_TOKENS = "ARC-00-HTL,ARC-00-OFF,ARC-00-RES,ARC-00-BMG"

WALL_VERDICT_CS = r'''
string lvl=(string)parameters[0];
string arcToks=(string)parameters[1];
var CI=System.Globalization.CultureInfo.InvariantCulture;
var sps=new List<Autodesk.Revit.DB.Mechanical.Space>();
var sbb=new List<BoundingBoxXYZ>();
var sH=new List<bool>();
double zmin=1e9,zmax=-1e9;
foreach(Element e in new FilteredElementCollector(document).OfCategory(BuiltInCategory.OST_MEPSpaces).WhereElementIsNotElementType()){
var sp=e as Autodesk.Revit.DB.Mechanical.Space;if(sp==null)continue;
var ap=sp.get_Parameter(BuiltInParameter.ROOM_AREA);if(ap==null||ap.AsDouble()<=1e-6)continue;
string ln="";try{var l=document.GetElement(sp.LevelId);if(l!=null)ln=l.Name??"";}catch{}
if(lvl!=""&&!ln.Contains(lvl))continue;
var bb=sp.get_BoundingBox(null);if(bb==null)continue;
string nu="";try{var pn=sp.get_Parameter(BuiltInParameter.ROOM_NUMBER);if(pn!=null)nu=(pn.AsString()??"").ToUpperInvariant();}catch{}
bool uc=nu.StartsWith("OFC-")||nu.StartsWith("BAL-")||nu.StartsWith("TER-")||nu.StartsWith("SHAFT");
sps.Add(sp);sbb.Add(bb);sH.Add(!uc);
if(bb.Min.Z<zmin)zmin=bb.Min.Z;if(bb.Max.Z>zmax)zmax=bb.Max.Z;}
var sb=new System.Text.StringBuilder();
if(sps.Count==0)return sb.ToString();
var rms=new List<Autodesk.Revit.DB.Architecture.Room>();
var rtf=new List<Transform>();
var rbx=new List<BoundingBoxXYZ>();
var rH=new List<bool>();
foreach(var tok in arcToks.Split(',')){
Document ld=null;Transform tf=Transform.Identity;
foreach(Element e in new FilteredElementCollector(document).OfClass(typeof(RevitLinkInstance))){
var li=e as RevitLinkInstance;if(li==null)continue;string nm=li.Name??"";if(!nm.Contains(tok))continue;
try{ld=li.GetLinkDocument();tf=li.GetTotalTransform();}catch{}if(ld!=null)break;}
if(ld==null)continue;
double dz=tf.Origin.Z;
foreach(Element e in new FilteredElementCollector(ld).OfCategory(BuiltInCategory.OST_Rooms).WhereElementIsNotElementType()){
var rm=e as Autodesk.Revit.DB.Architecture.Room;if(rm==null)continue;
if(rm.Area<=1e-6)continue;
var bb=rm.get_BoundingBox(null);if(bb==null)continue;
if(bb.Max.Z+dz<zmin-3.0||bb.Min.Z+dz>zmax+3.0)continue;
string nu="";try{var pn=rm.get_Parameter(BuiltInParameter.ROOM_NUMBER);if(pn!=null)nu=(pn.AsString()??"").ToUpperInvariant();}catch{}
bool uc=nu.StartsWith("OFC-")||nu.StartsWith("BAL-")||nu.StartsWith("TER-")||nu.StartsWith("SHAFT");
rms.Add(rm);rtf.Add(tf);rbx.Add(bb);rH.Add(!uc);}}
var bopt=new SpatialElementBoundaryOptions();
double IN=1.64,OUT=2.62;
for(int si=0;si<sps.Count;si++){
if(!sH[si])continue;
var sp=sps[si];long sid=sp.Id.Value;
IList<IList<BoundarySegment>> loops=null;try{loops=sp.GetBoundarySegments(bopt);}catch{}
if(loops==null)continue;
var done=new HashSet<long>();
foreach(var loop in loops)foreach(var seg in loop){
Element host=null;try{var hid=seg.ElementId;if(hid!=ElementId.InvalidElementId)host=document.GetElement(hid);}catch{}
Element wel=host;var li=host as RevitLinkInstance;
if(li!=null){try{var ld=li.GetLinkDocument();var lid=seg.LinkElementId;if(ld!=null&&lid!=ElementId.InvalidElementId){var le=ld.GetElement(lid);if(le!=null)wel=le;}}catch{}}
var w=wel as Wall;if(w==null)continue;
try{var t=wel.Document.GetElement(wel.GetTypeId());var wt=t as WallType;if(wt!=null&&wt.Kind==WallKind.Curtain)continue;}catch{}
long wid=wel.Id.Value;if(done.Contains(wid))continue;
Curve cv=null;try{cv=seg.GetCurve();}catch{}if(cv==null)continue;
XYZ mp;try{mp=cv.Evaluate(0.5,true);}catch{continue;}
XYZ d;try{d=cv.ComputeDerivatives(0.5,true).BasisX.Normalize();}catch{continue;}
XYZ nrm=new XYZ(d.Y,-d.X,0.0);
double nl=Math.Sqrt(nrm.X*nrm.X+nrm.Y*nrm.Y);if(nl<1e-9)continue;nrm=new XYZ(nrm.X/nl,nrm.Y/nl,0.0);
XYZ a=new XYZ(mp.X+nrm.X*IN,mp.Y+nrm.Y*IN,mp.Z);
XYZ b=new XYZ(mp.X-nrm.X*IN,mp.Y-nrm.Y*IN,mp.Z);
bool aIn=false,bIn=false;try{aIn=sp.IsPointInSpace(a);}catch{}try{bIn=sp.IsPointInSpace(b);}catch{}
XYZ od=nrm;if(aIn&&!bIn)od=new XYZ(-nrm.X,-nrm.Y,0.0);
XYZ outer=new XYZ(mp.X+od.X*OUT,mp.Y+od.Y*OUT,mp.Z);
string verdict="ext";
for(int j=0;j<sps.Count;j++){if(j==si||!sH[j])continue;var bb=sbb[j];
if(outer.X<bb.Min.X-IN||outer.X>bb.Max.X+IN||outer.Y<bb.Min.Y-IN||outer.Y>bb.Max.Y+IN||outer.Z<bb.Min.Z-IN||outer.Z>bb.Max.Z+IN)continue;
bool ins=false;try{ins=sps[j].IsPointInSpace(outer);}catch{}if(ins){verdict="int";break;}}
if(verdict=="ext"){
for(int j=0;j<rms.Count;j++){if(!rH[j])continue;
XYZ ol;try{ol=rtf[j].Inverse.OfPoint(outer);}catch{ol=outer;}
var bb=rbx[j];
if(ol.X<bb.Min.X-IN||ol.X>bb.Max.X+IN||ol.Y<bb.Min.Y-IN||ol.Y>bb.Max.Y+IN||ol.Z<bb.Min.Z-IN||ol.Z>bb.Max.Z+IN)continue;
bool ins=false;try{ins=rms[j].IsPointInRoom(ol);}catch{}if(ins){verdict="int";break;}}}
done.Add(wid);
sb.Append(sid.ToString(CI));sb.Append('\t');sb.Append(wid.ToString(CI));sb.Append('\t');sb.Append(verdict);sb.Append('\n');
}}
return sb.ToString();
'''


def export_wall_verdicts(folder: str, timeout: float = 240.0) -> Dict[tuple, str]:
    """Геом-вердикты внешней стороны глухих стен по уровням.

    Возвращает {(space_id, element_id): "int"|"ext"}. "int" = внешняя
    сторона упирается в отапл. помещение/ARC-комнату (внутренняя стена).
    """
    folder = str(folder)
    levels: List[str] = []
    seen = set()
    with open(os.path.join(folder, "spaces.csv"),
              encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            lvl = (row.get("level") or "").strip()
            if lvl and lvl not in seen:
                seen.add(lvl)
                levels.append(lvl)
    verdicts: Dict[tuple, str] = {}
    for lvl in levels:
        res = send_code(WALL_VERDICT_CS, parameters=[lvl, ARC_ROOM_TOKENS],
                        transaction_mode="none", timeout=timeout)
        text = res if isinstance(res, str) else (str(res) if res else "")
        for line in text.splitlines():
            p = line.split("\t")
            if len(p) >= 3:
                verdicts[(p[0], p[1])] = p[2]
    return verdicts


def tag_wall_exterior(folder: str, timeout: float = 240.0) -> dict:
    """Дописывает в thermal_all.csv колонку geom_exterior для глухих стен
    по геом-вердиктам (export_wall_verdicts). Загрузчик переводит
    geom_exterior=="int" во внутренние (высший приоритет)."""
    folder = str(folder)
    verdicts = export_wall_verdicts(folder, timeout=timeout)
    thermal_csv = os.path.join(folder, "thermal_all.csv")
    with open(thermal_csv, encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        fieldnames = list(reader.fieldnames or [])
        rows = list(reader)
    if "geom_exterior" not in fieldnames:
        fieldnames.append("geom_exterior")
    n_int = 0
    for row in rows:
        fam = (row.get("family", "") or "").lower()
        if row.get("row_type", "").strip() != "external_wall":
            continue
        if "витраж" in fam or "curtain" in fam:
            continue
        v = verdicts.get((row.get("space_id", "").strip(),
                          row.get("element_id", "").strip()))
        if v:
            row["geom_exterior"] = v
            if v == "int":
                n_int += 1
    with open(thermal_csv, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        for row in rows:
            w.writerow({k: row.get(k, "") for k in fieldnames})
    return {"verdicts": len(verdicts), "tagged_internal": n_int}


# ============================================================================
# Кровля: помещения под наружным покрытием (нет ОТАПЛИВАЕМОГО пространства
# сверху → потолок выходит под кровлю/небо). Заменяет ломкий по уровням
# _auto_detect_floors_roofs (брал алфавитно верхний уровень — мимо подиума и
# верхушек башни). Луч вверх от LocationPoint на +2..6 м, IsPointInSpace по
# всем пространствам; неотапл. сверху (OFC-/BAL-/TER-/SHAFT) не блокируют.
# ============================================================================

ROOF_DETECT_CS = r'''
var CI=System.Globalization.CultureInfo.InvariantCulture;
var sps=new List<Autodesk.Revit.DB.Mechanical.Space>();
var bbs=new List<BoundingBoxXYZ>();
var heated=new List<bool>();
foreach(Element e in new FilteredElementCollector(document).OfCategory(BuiltInCategory.OST_MEPSpaces).WhereElementIsNotElementType()){
var sp=e as Autodesk.Revit.DB.Mechanical.Space;if(sp==null)continue;
var ap=sp.get_Parameter(BuiltInParameter.ROOM_AREA);if(ap==null||ap.AsDouble()<=1e-6)continue;
var bb=sp.get_BoundingBox(null);if(bb==null)continue;
string nu="";try{var pn=sp.get_Parameter(BuiltInParameter.ROOM_NUMBER);if(pn!=null)nu=(pn.AsString()??"").ToUpperInvariant();}catch{}
bool uc=nu.StartsWith("OFC-")||nu.StartsWith("BAL-")||nu.StartsWith("TER-")||nu.StartsWith("SHAFT");
sps.Add(sp);bbs.Add(bb);heated.Add(!uc);}
var sb=new System.Text.StringBuilder();
double[] offs=new[]{6.56,9.84,13.12,16.40,19.69};
for(int i=0;i<sps.Count;i++){
if(!heated[i])continue;
var bb=bbs[i];var sp=sps[i];
double px,py;try{var lp=(sp.Location as LocationPoint).Point;px=lp.X;py=lp.Y;}catch{px=(bb.Min.X+bb.Max.X)*0.5;py=(bb.Min.Y+bb.Max.Y)*0.5;}
bool above=false;
foreach(var off in offs){
double qz=bb.Min.Z+off;
for(int j=0;j<sps.Count;j++){
if(j==i||!heated[j])continue;var b2=bbs[j];
if(qz<b2.Min.Z-0.5||qz>b2.Max.Z+0.5)continue;
if(px<b2.Min.X-0.5||px>b2.Max.X+0.5||py<b2.Min.Y-0.5||py>b2.Max.Y+0.5)continue;
bool ins=false;try{ins=sps[j].IsPointInSpace(new XYZ(px,py,qz));}catch{}
if(ins){above=true;break;}}
if(above)break;}
if(!above)sb.Append(sp.Id.Value.ToString(CI)).Append('\n');}
return sb.ToString();
'''


def detect_roof_spaces(timeout: float = 400.0) -> set:
    """Множество space_id (str) помещений, над которыми НЕТ отапливаемого
    пространства (потолок под кровлю/небо). Требует открытой модели Revit."""
    res = send_code(ROOF_DETECT_CS, transaction_mode="none", timeout=timeout)
    text = res if isinstance(res, str) else (str(res) if res else "")
    return {ln.strip() for ln in text.splitlines() if ln.strip()}


def tag_roof_spaces(folder: str, timeout: float = 400.0) -> dict:
    """Дописывает в spaces.csv колонку under_roof (1 — под кровлей) по
    геометрии открытой модели. Загрузчик переводит under_roof=1 → has_roof.
    Шаг импорта (вызывается из import_from_revit)."""
    folder = str(folder)
    roof_ids = detect_roof_spaces(timeout=timeout)
    spaces_csv = os.path.join(folder, "spaces.csv")
    with open(spaces_csv, encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        fieldnames = list(reader.fieldnames or [])
        rows = list(reader)
    if "under_roof" not in fieldnames:
        fieldnames.append("under_roof")
    n = 0
    for row in rows:
        if (row.get("id", "") or "").strip() in roof_ids:
            row["under_roof"] = "1"
            n += 1
        else:
            row.setdefault("under_roof", "")
    with open(spaces_csv, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        for row in rows:
            w.writerow({k: row.get(k, "") for k in fieldnames})
    return {"under_roof_tagged": n}


def apply_roof_flags(project: "HVACProject", timeout: float = 400.0) -> dict:
    """Проставляет has_roof по геометрии открытой модели для уже загруженного
    проекта (существующий JSON, без ре-импорта). Не трогает user_modified.
    Возвращает {detected, applied}."""
    roof_ids = detect_roof_spaces(timeout=timeout)
    applied = 0
    for sp in project.spaces:
        # has_roof — геометрический факт (есть ли покрытие над помещением),
        # а не пользовательская правка: применяем и к user_modified (флаг
        # стоит на ~четверти помещений из-за прежних правок окон/температур).
        if str(getattr(sp, "space_id", "")) in roof_ids and not sp.has_roof:
            sp.has_roof = True
            applied += 1
    return {"detected": len(roof_ids), "applied": applied}


def import_from_revit(folder: str, clean_glazing: bool = True,
                      wall_geom: bool = True,
                      roof_detect: bool = True,
                      collect_orphans: bool = False,
                      timeout: float = 600.0) -> dict:
    """Выгружает spaces.csv + thermal_all.csv из открытой модели Revit.

    Проходы 1-2 (помещения + границы) + чистая геом-привязка остекления
    (clean_glazing=True, по умолчанию): см. rebuild_thermal_clean. Старый
    orphan-проход доступен через clean_glazing=False, collect_orphans=True
    (обратная совместимость).

    Возвращает сводку: {spaces_rows, thermal_rows, orphan_rows,
    clean_glazing_rows, source, spaces_csv, thermal_csv}.
    """
    folder = str(folder)
    rg = {"clean_glazing_rows": 0, "total_rows": 0}
    wg = {"tagged_internal": 0}
    rf = {"under_roof_tagged": 0}
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
        if clean_glazing:
            rg = rebuild_thermal_clean(folder, timeout=timeout)
        elif collect_orphans:
            r3 = send_code(EXPORT_CS_ORPHANS, parameters=[folder],
                           transaction_mode="none", timeout=timeout)
            if not isinstance(r3, dict):
                raise RuntimeError(f"Проход 3: неожиданный ответ Revit: {r3!r}")
        if wall_geom:
            wg = tag_wall_exterior(folder, timeout=timeout)
        if roof_detect:
            rf = tag_roof_spaces(folder, timeout=timeout)
    finally:
        for name in _IMPORT_TEMP_FILES:
            try:
                os.remove(os.path.join(folder, name))
            except OSError:
                pass
    orphans = int(r3.get("orphan_rows", 0))
    if clean_glazing:
        thermal_rows = int(rg.get("total_rows", 0))
    else:
        thermal_rows = int(r2.get("thermal_rows", 0)) + orphans
    return {
        "spaces_rows": int(r1.get("spaces_rows", 0)),
        "thermal_rows": thermal_rows,
        "orphan_rows": orphans,
        "clean_glazing_rows": int(rg.get("clean_glazing_rows", 0)),
        "wall_internal_tagged": int(wg.get("tagged_internal", 0)),
        "under_roof_tagged": int(rf.get("under_roof_tagged", 0)),
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
    как element_overrides и переживают сохранение/открытие. У затронутых
    помещений заново выводится признак «угловое»: ложные фасады давали
    ≥2 ориентации наружных стен почти каждому помещению. Флаг только
    снимается (снятие стен не может сделать помещение угловым).
    """
    n = project.set_elements_exterior(plan.pairs, False)
    if not n:
        return 0
    affected = {sid for sid, _eid in plan.pairs}
    # Критерии зеркалят project._mark_corner_rooms()
    ext_by_space: Dict[str, list] = {}
    for e in project.elements:
        if (e.space_id in affected and e.row_type == "external_wall"
                and e.is_exterior and e.net_area_m2 > 1.0):
            ext_by_space.setdefault(e.space_id, []).append(e)
    for sp in project.spaces:
        if sp.space_id not in affected or not sp.is_corner:
            continue
        ext = ext_by_space.get(sp.space_id, [])
        oris = {e.orientation for e in ext if e.orientation}
        still_corner = (len(oris) >= 2
                        or (len(ext) >= 2 and not oris))
        if not still_corner:
            sp.is_corner = False
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
