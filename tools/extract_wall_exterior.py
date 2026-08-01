# -*- coding: utf-8 -*-
"""Геометрический тест внешней стороны глухих стен (как для витража).

Для каждой глухой (не Curtain) граничной стены ОТАПЛИВАЕМОГО помещения
сэмплирует ВНЕШНЮЮ сторону (за стеной) и проверяет, не лежит ли там
другое ОТАПЛИВАЕМОЕ помещение — MEP-пространство ИЛИ ARC-комната
(коридоры/ядра/лестницы, которых нет в MEP). Если да → это внутренняя
перегородка (verdict 'int'), даже если bsc/функция считают её наружной.
Иначе → 'ext' (улица / балкон / шахта без отапл. соседа — оставляем).

Вывод: вердикты (space_id, wall_id) -> int/ext + сколько СЕЙЧАС наружных
глухих стен перевернулось бы во внутренние.

Запуск (Revit открыт):
  C:\\Python314\\python.exe D:\\HVAC\\tools\\extract_wall_exterior.py [папка]
"""
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
sys.path.insert(0, _ROOT)
sys.path.insert(0, _HERE)

from hvac import revit_link as rl  # noqa: E402
from hvac import data_loader  # noqa: E402
import reconcile_glazing as rec  # noqa: E402

ARC_TOKENS = "ARC-00-HTL,ARC-00-OFF,ARC-00-RES,ARC-00-BMG"

CS = r'''
string lvl=(string)parameters[0];
string arcToks=(string)parameters[1];
var CI=System.Globalization.CultureInfo.InvariantCulture;
var sps=new List<Autodesk.Revit.DB.Mechanical.Space>();
var sbb=new List<BoundingBoxXYZ>();
var sH=new List<bool>();
var snum=new List<string>();
double zmin=1e9,zmax=-1e9;
foreach(Element e in new FilteredElementCollector(document).OfCategory(BuiltInCategory.OST_MEPSpaces).WhereElementIsNotElementType()){
var sp=e as Autodesk.Revit.DB.Mechanical.Space;if(sp==null)continue;
var ap=sp.get_Parameter(BuiltInParameter.ROOM_AREA);if(ap==null||ap.AsDouble()<=1e-6)continue;
string ln="";try{var l=document.GetElement(sp.LevelId);if(l!=null)ln=l.Name??"";}catch{}
if(lvl!=""&&!ln.Contains(lvl))continue;
var bb=sp.get_BoundingBox(null);if(bb==null)continue;
string nu="";try{var pn=sp.get_Parameter(BuiltInParameter.ROOM_NUMBER);if(pn!=null)nu=(pn.AsString()??"").ToUpperInvariant();}catch{}
bool uc=nu.StartsWith("OFC-")||nu.StartsWith("BAL-")||nu.StartsWith("TER-")||nu.StartsWith("SHAFT");
sps.Add(sp);sbb.Add(bb);sH.Add(!uc);snum.Add(nu);
if(bb.Min.Z<zmin)zmin=bb.Min.Z;if(bb.Max.Z>zmax)zmax=bb.Max.Z;}
var sb=new System.Text.StringBuilder();
if(sps.Count==0)return sb.ToString();
var rms=new List<Autodesk.Revit.DB.Architecture.Room>();
var rtf=new List<Transform>();
var rbx=new List<BoundingBoxXYZ>();
var rH=new List<bool>();
var rnum=new List<string>();
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
rms.Add(rm);rtf.Add(tf);rbx.Add(bb);rH.Add(!uc);rnum.Add(nu);}}
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
string verdict="ext";string nb="";
for(int j=0;j<sps.Count;j++){if(j==si||!sH[j])continue;var bb=sbb[j];
if(outer.X<bb.Min.X-IN||outer.X>bb.Max.X+IN||outer.Y<bb.Min.Y-IN||outer.Y>bb.Max.Y+IN||outer.Z<bb.Min.Z-IN||outer.Z>bb.Max.Z+IN)continue;
bool ins=false;try{ins=sps[j].IsPointInSpace(outer);}catch{}if(ins){verdict="int";nb="S:"+snum[j];break;}}
if(verdict=="ext"){
for(int j=0;j<rms.Count;j++){if(!rH[j])continue;
XYZ ol;try{ol=rtf[j].Inverse.OfPoint(outer);}catch{ol=outer;}
var bb=rbx[j];
if(ol.X<bb.Min.X-IN||ol.X>bb.Max.X+IN||ol.Y<bb.Min.Y-IN||ol.Y>bb.Max.Y+IN||ol.Z<bb.Min.Z-IN||ol.Z>bb.Max.Z+IN)continue;
bool ins=false;try{ins=rms[j].IsPointInRoom(ol);}catch{}if(ins){verdict="int";nb="R:"+rnum[j];break;}}}
done.Add(wid);
sb.Append(sid.ToString(CI));sb.Append('\t');sb.Append(wid.ToString(CI));sb.Append('\t');sb.Append(verdict);sb.Append('\t');sb.Append(nb);sb.Append('\n');
}}
return sb.ToString();
'''


def export_verdicts(folder):
    spaces = data_loader.load_spaces(os.path.join(folder, "spaces.csv"))
    levels, seen = [], set()
    for s in spaces:
        if s.level and s.level not in seen:
            seen.add(s.level)
            levels.append(s.level)
    verdicts = {}
    for i, lvl in enumerate(levels, 1):
        try:
            res = rl.send_code(CS, parameters=[lvl, ARC_TOKENS],
                               transaction_mode="none", timeout=240)
        except Exception as e:
            print("  [%2d/%d] %-26s ОШИБКА: %s" % (i, len(levels), lvl[:26], e))
            continue
        text = res if isinstance(res, str) else (str(res) if res else "")
        n_int = 0
        for line in text.splitlines():
            p = line.split("\t")
            if len(p) < 3:
                continue
            nb = p[3] if len(p) > 3 else ""
            verdicts[(p[0], p[1])] = (p[2], nb)
            if p[2] == "int":
                n_int += 1
        print("  [%2d/%d] %-26s int=%d" % (i, len(levels), lvl[:26], n_int))
    return verdicts, spaces


def main():
    import collections
    import csv
    folder = sys.argv[1] if len(sys.argv) > 1 else _ROOT
    print("Геом-тест внешней стороны глухих стен по уровням...")
    verdicts, spaces = export_verdicts(folder)

    # сохраняем вердикты (для интеграции, без повторного прогона моста)
    out_dir = os.path.join(_HERE, "out")
    if not os.path.isdir(out_dir):
        os.makedirs(out_dir)
    vpath = os.path.join(out_dir, "wall_verdicts.csv")
    with open(vpath, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(["space_id", "element_id", "verdict", "neighbor"])
        for (sid, wid), (v, nb) in verdicts.items():
            w.writerow([sid, wid, v, nb])

    sp_by_id = {s.space_id: s for s in spaces}
    elems = data_loader.load_thermal(os.path.join(folder, "thermal_all.csv"),
                                     spaces)
    # старый Dynamo (rbc есть) для сверки решений загрузчика
    old_ext = {}
    old_path = os.path.join(folder, "thermal_all.pre-cleanglazing.csv")
    if os.path.exists(old_path):
        for o in data_loader.load_thermal(old_path, spaces):
            old_ext[(o.space_id, o.element_id)] = o.is_exterior

    flip = cur_ext = 0
    flip_area = 0.0
    func_dist = collections.Counter()
    nb_dist = collections.Counter()
    agree = disagree = unknown = 0
    samples = []
    for e in elems:
        if e.row_type != "external_wall" or not e.is_exterior:
            continue
        fam = (e.family or "").lower()
        if "витраж" in fam or "curtain" in fam:
            continue
        cur_ext += 1
        vv = verdicts.get((e.space_id, e.element_id))
        if vv and vv[0] == "int":
            flip += 1
            nb = vv[1]
            flip_area += (e.net_area_m2 or e.approx_area_m2
                          or e.element_area_m2 or 0.0)
            func_dist[(e.function or "(пусто)").strip() or "(пусто)"] += 1
            nb_dist["S" if nb.startswith("S:") else
                    ("R" if nb.startswith("R:") else "?")] += 1
            oe = old_ext.get((e.space_id, e.element_id))
            if oe is False:
                agree += 1       # Dynamo тоже считал внутренней
            elif oe is True:
                disagree += 1    # Dynamo считал наружной (geom строже)
            else:
                unknown += 1
            if len(samples) < 20:
                s = sp_by_id.get(e.space_id)
                samples.append("%-9s %-18s | %-22s сосед %s" % (
                    (s.number if s else "")[:9],
                    ((s.name if s else "") or "")[:18],
                    (e.type_name or "")[:22], nb[:24]))
    print("\nВердиктов получено:", len(verdicts), "-> сохранено:", vpath)
    print("Сейчас наружных глухих стен:", cur_ext)
    print("Геометрия -> ВНУТРЕННЯЯ:", flip,
          "(%.1f%%)" % (100.0 * flip / max(cur_ext, 1)),
          " площадь ~%.0f m2" % flip_area)
    if old_ext:
        print("  сверка со старым Dynamo+loader: согласен(внутр)=%d, "
              "Dynamo считал наружной=%d, нет данных=%d"
              % (agree, disagree, unknown))
    print("\nПеревёрнутые по функции стены:")
    for fn, c in func_dist.most_common():
        print("  %-22s %5d" % (fn[:22], c))
    print("Сосед с внешней стороны: MEP-простр.=%d, ARC-комната=%d, ?=%d"
          % (nb_dist.get("S", 0), nb_dist.get("R", 0), nb_dist.get("?", 0)))
    print("\nПримеры перевёрнутых (стена -> что с внешней стороны):")
    for s in samples:
        print("  ", s)


if __name__ == "__main__":
    main()
