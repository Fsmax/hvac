"""Движок КМК/ШНҚ (Узбекистан).

Отличия от СП вынесены сюда: надбавка на угловое помещение и возмещение
вытяжки в жилых зданиях по ШНҚ 2.04.05-22 п. 191.
"""
from __future__ import annotations

from hvac.engine.base import register_engine
from hvac.engine.sp50 import SP50Engine


def _is_dwelling(space) -> bool:
    """Квартира — по номеру, как в data_loader.py и sp50.heat_loss."""
    return (getattr(space, "number", "") or "").upper().startswith("RES")


def _neighbor_spaces(space, project):
    """Смежные помещения по общим стенам (как в _has_supplied_neighbor)."""
    seen: set = set()
    for el in project.elements_for(space.space_id):
        if el.row_type != "external_wall":
            continue
        for nid in project.wall_neighbor_space_ids(el.element_id, space.space_id):
            if nid in seen:
                continue
            seen.add(nid)
            nb = project._space_by_id.get(nid)
            if nb is not None:
                yield nb


def _has_exterior(space, project) -> bool:
    """Есть ли у помещения наружная оболочка — критерий как в heat_loss."""
    all_elems = project.elements_for(space.space_id)
    if not all_elems:
        return True
    return any(e.net_area_m2 > 0 for e in all_elems
               if getattr(e, "is_exterior", False))


def _is_exhaust_only(space) -> bool:
    """Чисто вытяжное: вытяжка есть, притока и зонта нет (санузел, ванная)."""
    return ((getattr(space, "exhaust_m3h", 0.0) or 0.0) > 0.0
            and not (getattr(space, "supply_m3h", 0.0) or 0.0)
            and not (getattr(space, "hood_m3h", 0.0) or 0.0))


def _admits_inflow(space, project) -> bool:
    """Через это помещение заходит естественный приток: жилая комната с
    наружным ограждением (форточка окна или балконной двери), без своей
    механической вентиляции и без вытяжки."""
    return (_is_dwelling(space)
            and not (getattr(space, "supply_m3h", 0.0) or 0.0)
            and not (getattr(space, "exhaust_m3h", 0.0) or 0.0)
            and not (getattr(space, "hood_m3h", 0.0) or 0.0)
            and _has_exterior(space, project))


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

    # ---------- возмещение вытяжки: ШНҚ 2.04.05-22 п. 191 ----------
    def _has_transfer_donor(self, space, project) -> bool:
        """ШНҚ 2.04.05-22 п. 191: в жилых зданиях воздух, удаляемый из кухонь,
        уборных, ванных и душевых, возмещается ЕСТЕСТВЕННЫМ притоком наружного
        воздуха через форточки окон и балконных дверей.

        Поэтому критерий СП «сосед с механическим притоком» для квартир не
        работает никогда: приточных установок в жилье нет. Донором служит
        смежная жилая комната с наружным ограждением — через её форточку и
        заходит воздух, который потом перетекает в санузел под дверью.

        Без этого санузел с любым куском фасада получает весь расход вытяжки
        при наружной температуре, а точно такой же санузел без окна — ноль.
        """
        if super()._has_transfer_donor(space, project):
            return True
        if not (_is_dwelling(space) and _is_exhaust_only(space)):
            return False
        return any(_admits_inflow(nb, project)
                   for nb in _neighbor_spaces(space, project))

    def _makeup_air_flow(self, space, project, params) -> float:
        """Расход, который жилая комната принимает за смежные вытяжные, м³/ч.

        Обратная сторона `_has_transfer_donor`: сняв вытяжку с санузла, её
        нельзя потерять — воздух физически заходит через форточку комнаты и
        греется её приборами (п. 191). Расход соседа делится поровну между
        всеми комнатами, через которые он может зайти.
        """
        if not _admits_inflow(space, project):
            return 0.0
        total = 0.0
        for nb in _neighbor_spaces(space, project):
            if not (_is_dwelling(nb) and _is_exhaust_only(nb)):
                continue
            if not self._has_transfer_donor(nb, project):
                continue
            admitting = sum(1 for x in _neighbor_spaces(nb, project)
                            if _admits_inflow(x, project))
            if admitting:
                total += (nb.exhaust_m3h or 0.0) / admitting
        return total
