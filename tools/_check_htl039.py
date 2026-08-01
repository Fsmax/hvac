# -*- coding: utf-8 -*-
"""Что загрузчик даёт по HTL-039 из ТЕКУЩЕГО thermal_all.csv (как покажет
приложение после переимпорта)."""
import os
import sys

sys.path.insert(0, r"D:\HVAC")
from hvac import data_loader  # noqa: E402

spaces = data_loader.load_spaces(r"D:\HVAC\spaces.csv")
elems = data_loader.load_thermal(r"D:\HVAC\thermal_all.csv", spaces)
sid = "750384"  # HTL-039 ALL DAY DINING

ext = [e for e in elems if e.space_id == sid and e.is_exterior]
glaz = sum(e.element_area_m2 or e.approx_area_m2 or 0
           for e in ext if "витраж" in (e.family or "").lower())
opaque = sum(e.element_area_m2 or e.approx_area_m2 or 0
             for e in ext if "витраж" not in (e.family or "").lower())
print("HTL-039 наружных элементов:", len(ext))
print("  витраж (фасад), м²:  %.1f" % glaz)
print("  глухие/прочее, м²:   %.1f" % opaque)
print("  Σ наружных, м²:      %.1f" % (glaz + opaque))
print("\nНаружные элементы:")
for e in ext:
    print("  %-8s %-30s %7.1f м²  %s" % (
        e.category, (e.type_name or "")[:30],
        e.element_area_m2 or e.approx_area_m2 or 0,
        "ВИТРАЖ" if "витраж" in (e.family or "").lower() else ""))
