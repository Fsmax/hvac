# -*- coding: utf-8 -*-
"""Тесты фиксов нормативного контроля q ≤ q_ov (ШНҚ 2.01.18-24) и
теплопотерь ручных проектов (кейс «Гузар офисное здание BESS», q=88>80):

1. Донор перетока в ручном проекте — по балансу притока уровня
   (в ручных проектах нет общих стен, точная смежность недоступна).
2. Пол по грунту не считается дважды (элемент «Пол» + 4-зонный метод);
   «стены в грунте» — только у помещений без наружных стен (подвал);
   периметр 4-зонного метода — без плит пола/покрытия.
3. q_design_specific в паспорте — без монтажного запаса (запас — проектное
   решение, не свойство здания).
"""

import pytest

from hvac.project import HVACProject
from hvac.models import Space, BoundaryElement
from hvac.engine.sp50 import (SP50Engine, _has_supplied_neighbor,
                              _calc_floor_loss_4zone)


def _space(sid, name, level="L1", area=15.0, **kw):
    defaults = dict(
        space_id=sid, number=sid, name=name, level=level,
        area_m2=area, volume_m3=area * 3.0, height_m=3.0,
        room_type="Офис", t_in_heat=20, t_in_cool=24,
        ach_inf=0.5, lighting_w_m2=10, equipment_w_m2=10,
        occupancy_people=1, is_corner=False,
    )
    defaults.update(kw)
    return Space(**defaults)


def _wall(space_id, element_id, category="Стены", u=0.5, area=12.0,
          boundary_len=4.0, orientation="N", is_exterior=True):
    return BoundaryElement(
        space_id=space_id, row_type="external_wall", is_exterior=is_exterior,
        element_id=element_id, category=category, family="Тест",
        type_name="Тест", boundary_length_m=boundary_len, space_height_m=3.0,
        approx_area_m2=area, element_area_m2=area, thickness_mm=200,
        function="Наружные", host_element_id="", boundary_space_count=1,
        construction_key=f"{category} / Тест / Тест / 200",
        orientation_deg=0, orientation=orientation,
        u_value=u, net_area_m2=area,
    )


def _project(spaces, elements):
    project = HVACProject()
    project.params.t_out_heating = -11
    project.params.inf_correction_k = 0.7
    project.params.safety_margin_heating = 1.0
    project.params.safety_margin_cooling = 1.0
    project.params.infiltration_min_ach = 0.0
    project.spaces = list(spaces)
    project._space_by_id = {sp.space_id: sp for sp in spaces}
    project.elements = list(elements)
    project.constructions = {}
    project._invalidate_elements_index()
    return project


class TestManualProjectDonor:
    """Донор перетока в ручном проекте — по балансу притока уровня."""

    def _toilet_and_corridor(self, corridor_supply):
        toilet = _space("T1", "Санузел", room_type="Санузел",
                        supply_m3h=0.0, exhaust_m3h=300.0)
        corridor = _space("C1", "Коридор", room_type="Коридор",
                          supply_m3h=corridor_supply, exhaust_m3h=50.0)
        # У каждого помещения СВОИ элементы — общих стен нет (ручной ввод)
        els = [_wall("T1", "E-T1-001"), _wall("C1", "E-C1-001")]
        return _project([toilet, corridor], els), toilet

    def test_donor_found_when_level_surplus_covers_exhaust(self):
        """Профицит притока уровня ≥ вытяжки санузла → донор есть,
        радиаторы санузла не греют вытяжной расход от наружной t."""
        project, toilet = self._toilet_and_corridor(corridor_supply=350.0)
        assert not project.has_wall_adjacency()
        assert _has_supplied_neighbor(toilet, project)
        br = SP50Engine().heat_loss(toilet, project)
        assert br["Инфильтрация"] == pytest.approx(0.0)

    def test_no_donor_when_surplus_insufficient(self):
        """Профицит уровня (100−50=50) < вытяжки 300 → донора нет,
        вытяжка греется как наружный подсос."""
        project, toilet = self._toilet_and_corridor(corridor_supply=100.0)
        assert not _has_supplied_neighbor(toilet, project)
        br = SP50Engine().heat_loss(toilet, project)
        assert br["Инфильтрация"] > 1000  # ~300 м³/ч × Δt 31 K

    def test_donor_only_within_same_level(self):
        """Профицит на другом этаже не считается донором."""
        toilet = _space("T1", "Санузел", level="L1", room_type="Санузел",
                        supply_m3h=0.0, exhaust_m3h=300.0)
        corridor = _space("C1", "Коридор", level="L2", room_type="Коридор",
                          supply_m3h=500.0, exhaust_m3h=0.0)
        project = _project([toilet, corridor],
                           [_wall("T1", "E-T1-001"), _wall("C1", "E-C1-001")])
        assert not _has_supplied_neighbor(toilet, project)

    def test_revit_adjacency_path_unchanged(self):
        """В проекте с общими стенами (Revit) фолбэк не применяется:
        донор — только реальный сосед по стене с притоком."""
        toilet = _space("T1", "Санузел", room_type="Санузел",
                        supply_m3h=0.0, exhaust_m3h=100.0)
        room = _space("R1", "Номер", supply_m3h=400.0, exhaust_m3h=0.0)
        far = _space("F1", "Дальний санузел", room_type="Санузел",
                     supply_m3h=0.0, exhaust_m3h=100.0)
        shared = "W_SHARED"
        els = [
            _wall("T1", shared, is_exterior=False),   # общая стена T1|R1
            _wall("R1", shared, is_exterior=False),
            _wall("F1", "E-F1-001"),                  # без общих стен
        ]
        project = _project([toilet, room, far], els)
        assert project.has_wall_adjacency()
        assert _has_supplied_neighbor(toilet, project)   # сосед по стене
        assert not _has_supplied_neighbor(far, project)  # балансовый фолбэк
        #                                     не должен сработать в Revit-проекте


class TestFloorNotDoubleCounted:
    """Пол по грунту: одна статья, а не элемент + 4-зонный метод."""

    def _room_with_floor_slab(self, ftg):
        sp = _space("S1", "Офис", area=20.0, has_floor_to_ground=ftg)
        els = [
            _wall("S1", "E-S1-W", category="Стены", u=0.5, area=12.0,
                  boundary_len=4.0),
            # Плита пола хранится как external_wall категории «Пол»
            # (ручной ввод) — с собственной boundary_length.
            _wall("S1", "E-S1-F", category="Пол", u=0.3, area=20.0,
                  boundary_len=10.0),
        ]
        return _project([sp], els), sp

    def test_floor_element_skipped_when_floor_to_ground(self):
        project, sp = self._room_with_floor_slab(ftg=True)
        br = SP50Engine().heat_loss(sp, project)
        assert "Пол по грунту" in br
        assert "Пол" not in br           # элементный дубль исключён

    def test_floor_element_counts_without_floor_to_ground(self):
        project, sp = self._room_with_floor_slab(ftg=False)
        br = SP50Engine().heat_loss(sp, project)
        assert "Пол по грунту" not in br
        assert br["Пол"] > 0             # обычное ограждение

    def test_4zone_perimeter_excludes_slab_boundary(self):
        """Периметр 4-зонного метода — только наружные СТЕНЫ (4 м),
        boundary_length плиты пола (10 м) не участвует."""
        project, sp = self._room_with_floor_slab(ftg=True)
        br = SP50Engine().heat_loss(sp, project)
        dt = sp.t_in_heat - project.params.t_out_heating
        assert br["Пол по грунту"] == pytest.approx(
            _calc_floor_loss_4zone(sp.area_m2, 4.0, dt), rel=1e-6)

    def test_no_underground_walls_for_room_with_exterior_walls(self):
        """Наземное помещение с наружной стеной: разница периметр×h −
        площадь стен — проёмы/погрешность, а не стены в грунте."""
        sp = _space("S1", "Офис", area=20.0, has_floor_to_ground=True)
        els = [_wall("S1", "E-S1-W", category="Стены", area=6.0,
                     boundary_len=4.0)]   # 6 < 4×3 → раньше было бы 6 м² «грунта»
        project = _project([sp], els)
        br = SP50Engine().heat_loss(sp, project)
        assert "Стены в грунте" not in br

    def test_underground_walls_for_basement_room(self):
        """Помещение без наружных стен (подвал в грунте) — стены в грунте
        по всему периметру, как и раньше."""
        sp = _space("S1", "Кладовая подвала", area=20.0,
                    has_floor_to_ground=True)
        project = _project([sp], [_wall("S1", "E-S1-F", category="Пол",
                                        u=0.3, area=20.0, boundary_len=10.0)])
        br = SP50Engine().heat_loss(sp, project)
        assert br.get("Стены в грунте", 0.0) > 0


class TestPassportQDesignWithoutMargin:
    """q_design_specific для сравнения с q_ov — без монтажного запаса."""

    def test_margin_removed_from_q_design(self):
        from hvac.energy import calculate_passport
        sp = _space("S1", "Офис", area=20.0)
        project = _project([sp], [_wall("S1", "E-S1-W")])
        project.params.safety_margin_heating = 1.1
        sp.heat_loss_w = 1100.0          # хранится уже С запасом 1.1
        sp.heat_gain_w = 0.0
        ep = calculate_passport(project)
        # 1100 / 1.1 / 20 м² = 50.0 Вт/м² (а не 55.0)
        assert ep.q_design_specific_w_m2 == pytest.approx(50.0)
        # Пиковая мощность для подбора оборудования — по-прежнему с запасом
        assert ep.q_peak_heating_w == pytest.approx(1100.0)
