# -*- coding: utf-8 -*-
"""Read-only инспекция проекта: что в нём есть (системы/оборудование/правки)
и текущее состояние HTL-039. Ничего не меняет."""
import sys

sys.path.insert(0, r"D:\HVAC")
from hvac.project import HVACProject  # noqa: E402
from hvac import io_json  # noqa: E402

path = sys.argv[1] if len(sys.argv) > 1 else r"D:\HVAC\ALL-BLOCKS.hvac.json"
P = HVACProject()
io_json.load_project(P, path)
print("Файл:", path)

sp_um = sum(1 for s in P.spaces if s.user_modified)
el_um = sum(1 for e in P.elements if getattr(e, "user_modified", False))
sys_h = sum(1 for s in P.spaces if s.system_heating)
sys_c = sum(1 for s in P.spaces if s.system_cooling)
sys_v = sum(1 for s in P.spaces if s.system_ventilation)
circ = sum(1 for s in P.spaces if s.circuit_heating or s.circuit_cooling
           or s.duct_zone)
smoke = sum(1 for s in P.spaces if s.smoke_system or s.pressurization_system)
equip = sum(1 for s in P.spaces if s.room_equipment is not None)

print("Помещений:", len(P.spaces), " ограждений:", len(P.elements))
print("Помещений user_modified:", sp_um)
print("Ограждений user_modified (ручная правка геометрии):", el_um)
print("--- системы (на это НЕ влияет миграция, сохраняется) ---")
print("  отопление назначено:", sys_h)
print("  охлаждение назначено:", sys_c)
print("  вентиляция назначена:", sys_v)
print("  контуры/зоны:", circ)
print("  дымоудаление/подпор:", smoke)
print("  оборудование в комнатах:", equip)
print("  систем: вент=%d отоп=%d охл=%d" % (
    len(P.ventilation_systems), len(P.heating_systems),
    len(P.cooling_systems)))

# HTL-039
sp = P._space_by_id.get("750384")
if sp:
    els = P.elements_for("750384")
    ext = [e for e in els if e.is_exterior]
    glaz = sum(e.net_area_m2 or 0 for e in ext
               if "витраж" in (e.family or "").lower())
    print("\nHTL-039 в ТЕКУЩЕМ проекте (старая геометрия):")
    print("  наружных элементов:", len(ext), " витраж м²: %.1f" % glaz)
    print("  система вент:", repr(sp.system_ventilation),
          " охл:", repr(sp.system_cooling),
          " зона:", repr(sp.duct_zone))
