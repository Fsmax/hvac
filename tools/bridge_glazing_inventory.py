# -*- coding: utf-8 -*-
"""Инвентаризация остекления по всем связанным моделям через живой мост.

Читает (read-only) основной документ + все RevitLinkInstance, собирает
стены, тип которых похож на остекление/фасад (по WallKind.Curtain или
ключевым словам в имени типа/семейства), группирует по
link||kind||family||type и считает количество + площадь (м²).

Также печатает по каждой связи общее число стен и окон — чтобы видеть,
достижима ли модель LND вообще.

Запуск: C:\\Python314\\python.exe D:\\HVAC\\tools\\bridge_glazing_inventory.py
"""
import sys

sys.path.insert(0, r"D:\HVAC")
from hvac import revit_link as rl  # noqa: E402

CS = r'''
var CI=System.Globalization.CultureInfo.InvariantCulture;
var docs=new List<Document>();
docs.Add(document);
var nm=new Dictionary<Document,string>();
nm[document]="MAIN";
foreach(Element e in new FilteredElementCollector(document).OfClass(typeof(RevitLinkInstance))){
var li=e as RevitLinkInstance;if(li==null)continue;
Document ld=null;try{ld=li.GetLinkDocument();}catch{}
if(ld==null||docs.Contains(ld))continue;
docs.Add(ld);nm[ld]=li.Name??"";}
var sb=new System.Text.StringBuilder();
string[] kws=new[]{"glass","mullion","стекл","витраж","glaz","curtain","storefront","facade","фасад","spandrel","alumin","навесн"};
var rows=new Dictionary<string,double[]>();
foreach(var d in docs){
int wc=new FilteredElementCollector(d).OfCategory(BuiltInCategory.OST_Walls).WhereElementIsNotElementType().GetElementCount();
int wn=new FilteredElementCollector(d).OfCategory(BuiltInCategory.OST_Windows).WhereElementIsNotElementType().GetElementCount();
sb.Append("#LINK||"+nm[d]+"||"+wc.ToString(CI)+"||"+wn.ToString(CI)+"\n");
foreach(Element e in new FilteredElementCollector(d).OfCategory(BuiltInCategory.OST_Walls).WhereElementIsNotElementType()){
var w=e as Wall;if(w==null)continue;
string tn="";string fam="";string kind="";
try{var t=d.GetElement(w.GetTypeId());if(t!=null){tn=t.Name??"";var wt=t as WallType;if(wt!=null){fam=wt.FamilyName??"";kind=wt.Kind.ToString();}}}catch{}
string full=(fam+" "+tn).ToLowerInvariant();
bool hit=(kind=="Curtain");
if(!hit)foreach(var k in kws)if(full.Contains(k)){hit=true;break;}
if(!hit)continue;
double a=0;try{var p=w.get_Parameter(BuiltInParameter.HOST_AREA_COMPUTED);if(p!=null&&p.StorageType==StorageType.Double)a=p.AsDouble()*0.09290304;}catch{}
string key=nm[d]+"||"+kind+"||"+fam+"||"+tn;
double[] v;if(!rows.TryGetValue(key,out v)){v=new double[2];rows[key]=v;}
v[0]+=1;v[1]+=a;}}
foreach(var kv in rows){sb.Append("G||"+kv.Key+"||"+kv.Value[0].ToString("0",CI)+"||"+kv.Value[1].ToString("0.0",CI)+"\n");}
return sb.ToString();
'''


def main():
    print("ping:", rl.ping())
    res = rl.send_code(CS, transaction_mode="none", timeout=180)
    text = res if isinstance(res, str) else str(res)
    links = [ln for ln in text.splitlines() if ln.startswith("#LINK")]
    glz = [ln for ln in text.splitlines() if ln.startswith("G||")]
    print("\n=== СВЯЗИ (link || walls || windows) ===")
    for ln in links:
        print(ln)
    print("\n=== ОСТЕКЛЕНИЕ (link || kind || family || type || count || area_m2) ===")
    # сортируем по площади убыв.
    def area_of(ln):
        try:
            return float(ln.rsplit("||", 1)[1])
        except Exception:
            return 0.0
    for ln in sorted(glz, key=area_of, reverse=True):
        print(ln)
    print("\nИтого групп остекления:", len(glz))


if __name__ == "__main__":
    main()
