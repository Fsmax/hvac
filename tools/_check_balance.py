# -*- coding: utf-8 -*-
"""Баланс приток/вытяжка: HTL-039 и здание целиком + сколько помещений
приточно-доминантны (подпор) vs вытяжно-доминантны (подсос)."""
import sys

sys.path.insert(0, r"D:\HVAC")
from hvac.project import HVACProject  # noqa: E402
from hvac import io_json  # noqa: E402

P = HVACProject()
io_json.load_project(P, r"D:\HVAC\ALL-BLOCKS_fixed.hvac.json")

tot_sup = sum(s.supply_m3h or 0 for s in P.spaces)
tot_exh = sum((s.exhaust_m3h or 0) + (s.hood_m3h or 0) for s in P.spaces)
press = sum(1 for s in P.spaces
            if (s.supply_m3h or 0) >= (s.exhaust_m3h or 0) + (s.hood_m3h or 0)
            and ((s.supply_m3h or 0) > 0 or (s.exhaust_m3h or 0) > 0))
exhd = sum(1 for s in P.spaces
           if (s.supply_m3h or 0) < (s.exhaust_m3h or 0) + (s.hood_m3h or 0))
nomech = sum(1 for s in P.spaces
             if (s.supply_m3h or 0) == 0 and (s.exhaust_m3h or 0) == 0
             and (s.hood_m3h or 0) == 0)

print("=== БАЛАНС ЗДАНИЯ ===")
print("  суммарный приток:  %.0f м³/ч" % tot_sup)
print("  суммарная вытяжка+зонт: %.0f м³/ч" % tot_exh)
print("  нетто (вытяжка-приток): %.0f м³/ч" % (tot_exh - tot_sup))
print("  помещений с подпором (приток>=вытяжки):", press)
print("  помещений вытяжно-домин. (подсос):", exhd)
print("  без мех. вентиляции:", nomech)

h = P._space_by_id.get("750384")
if h:
    print("\n=== HTL-039 ALL DAY DINING ===")
    print("  приток:  %.0f м³/ч" % (h.supply_m3h or 0))
    print("  вытяжка: %.0f м³/ч" % (h.exhaust_m3h or 0))
    print("  зонт:    %.0f м³/ч" % (h.hood_m3h or 0))
    print("  объём:   %.0f м³ (1 ACH = %.0f м³/ч)" % (
        h.volume_m3, h.volume_m3))
    bal = (h.exhaust_m3h or 0) + (h.hood_m3h or 0) - (h.supply_m3h or 0)
    print("  дефицит (подсос): %.0f м³/ч" % bal)
