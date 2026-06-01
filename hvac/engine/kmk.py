# -*- coding: utf-8 -*-
"""Расчётный движок по КМК 2.04.05-91 «Отопление, вентиляция и
кондиционирование» (Узбекистан) + КМК 2.01.04-18 «Строительная теплотехника».

Формула теплопотерь и теплопоступлений совпадает со структурой СП 50.13330 /
СП 60.13330, поэтому движок наследуется от SP50Engine. Отличие действующей
узбекской нормы — СОХРАНЁННАЯ надбавка СНиП 2.04.05-91 на угловое помещение
(+0.05 на каждую наружную стену/окно), которую СП 50.13330 отменил.

Нормируемые сопротивления R₀^тр и Δt_н в этой методике берутся по КМК
(project.params.thermal_norm="KMK_UZ" — значение по умолчанию), см.
hvac/catalogs/kmk_thermal.py и hvac/dew_point.py.
"""

from __future__ import annotations

from hvac.engine.base import register_engine
from hvac.engine.sp50 import SP50Engine


@register_engine
class KMKEngine(SP50Engine):
    """КМК 2.04.05-91 + КМК 2.01.04-18 (Узбекистан)."""

    @property
    def name(self) -> str:
        return "КМК 2.04.05-91 + КМК 2.01.04-18"

    def _corner_room_addition(self, space, ext_elems) -> float:
        """+0.05 для угловых помещений (СНиП/КМК 2.04.05-91 прил.).

        Использует канонический флаг space.is_corner — автоопределяется по ≥2
        ориентациям наружных стен (project._mark_corner_rooms) и редактируется
        вручную в панели «Свойства». Надбавка добавляется к β каждой
        вертикальной наружной конструкции (стены и окна) — см.
        SP50Engine.heat_loss.
        """
        return 0.05 if getattr(space, "is_corner", False) else 0.0
