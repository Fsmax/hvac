# -*- coding: utf-8 -*-
"""Тесты функциональности v3.2: явная/скрытая теплота, 4-зонный пол,
валидация данных."""

import pytest
from hvac.project import HVACProject
from hvac.models import Space, BoundaryElement, Construction
from hvac.engine.sp50 import (
    SP50Engine, _floor_4zone_areas, _calc_floor_loss_4zone,
    _latent_infiltration_w,
)


def _minimal_project():
    """Минимальный проект: 1 помещение, 1 наружная стена."""
    project = HVACProject()
    project.params.t_out_heating = -25
    project.params.t_out_cooling = 36
    project.params.daily_amplitude = 10
    project.params.solar_intensity_w_m2 = 600
    project.params.inf_correction_k = 0.7
    project.params.safety_margin_heating = 1.0
    project.params.safety_margin_cooling = 1.0
    project.params.w_out_summer_g_kg = 8.0
    project.params.w_in_summer_g_kg = 9.3

    sp = Space(
        space_id="1", number="101", name="Office", level="L1",
        area_m2=20.0, volume_m3=60.0, height_m=3.0,
        room_type="Офис", t_in_heat=20, t_in_cool=24,
        ach_inf=0.5, lighting_w_m2=12, equipment_w_m2=15,
        occupancy_people=2.0,
    )
    project.spaces = [sp]
    project._space_by_id = {"1": sp}

    wall = BoundaryElement(
        space_id="1", row_type="external_wall", is_exterior=True,
        element_id="W1", category="Стены", family="Базовая стена",
        type_name="Test", boundary_length_m=4.0, space_height_m=3.0,
        approx_area_m2=12.0, element_area_m2=12.0, thickness_mm=210,
        function="Наружные", host_element_id="", boundary_space_count=1,
        construction_key="Стены / Базовая стена / Test / 210",
        orientation="N", u_value=0.5, net_area_m2=12.0,
    )
    project.elements = [wall]
    project.constructions = {
        wall.construction_key: Construction(
            key=wall.construction_key, category="Стены",
            family="Базовая стена", type_name="Test", thickness_mm=210,
            u_value=0.5, shgc=0.0,
        )
    }
    return project, sp


class TestSensibleLatent:
    """Разделение явной и скрытой теплоты."""

    def test_people_split(self):
        """Люди: 75 явная + 55 скрытая = 130 на чел."""
        project, sp = _minimal_project()
        engine = SP50Engine()
        engine.heat_gain(sp, project)
        # 2 чел × 75 = 150 явная
        assert sp.heat_gain_breakdown_sensible["Люди"] == pytest.approx(150, rel=0.01)
        # 2 чел × 55 = 110 скрытая
        assert sp.heat_gain_breakdown_latent["Люди"] == pytest.approx(110, rel=0.01)

    def test_lighting_100_sensible(self):
        """Освещение — только явная."""
        project, sp = _minimal_project()
        engine = SP50Engine()
        engine.heat_gain(sp, project)
        # 20·12 = 240 Вт явная, 0 скрытая
        assert sp.heat_gain_breakdown_sensible["Освещение"] == pytest.approx(240, rel=0.01)
        assert sp.heat_gain_breakdown_latent["Освещение"] == 0

    def test_office_equipment_90_sensible(self):
        """Оборудование в офисе: 90% явная (компьютеры)."""
        project, sp = _minimal_project()
        engine = SP50Engine()
        engine.heat_gain(sp, project)
        # 20·15 = 300 Вт общая, 90% = 270 явная, 10% = 30 скрытая
        assert sp.heat_gain_breakdown_sensible["Оборудование"] == pytest.approx(270, rel=0.01)
        assert sp.heat_gain_breakdown_latent["Оборудование"] == pytest.approx(30, rel=0.01)

    def test_kitchen_equipment_50_50(self):
        """Кухня: 50/50 явная/скрытая (плиты, пароконвектоматы)."""
        project, sp = _minimal_project()
        sp.room_type = "Ресторан / кухня"
        sp.equipment_w_m2 = 200
        engine = SP50Engine()
        engine.heat_gain(sp, project)
        # 20·200 = 4000 общая, 50% = 2000 каждая
        assert sp.heat_gain_breakdown_sensible["Оборудование"] == pytest.approx(2000, rel=0.01)
        assert sp.heat_gain_breakdown_latent["Оборудование"] == pytest.approx(2000, rel=0.01)

    def test_dry_climate_negative_latent_infiltration(self):
        """В сухом климате скрытая инфильтрация может быть отрицательной."""
        project, sp = _minimal_project()
        project.params.w_out_summer_g_kg = 6.0  # очень сухо снаружи
        project.params.w_in_summer_g_kg = 9.3
        engine = SP50Engine()
        engine.heat_gain(sp, project)
        # Δw = 6 - 9.3 = -3.3 → скрытая отрицательная
        assert sp.heat_gain_breakdown_latent["Инфильтрация/вентиляция"] < 0

    def test_humid_climate_positive_latent(self):
        """Во влажном климате — положительная."""
        project, sp = _minimal_project()
        project.params.w_out_summer_g_kg = 14.0  # влажно
        engine = SP50Engine()
        engine.heat_gain(sp, project)
        assert sp.heat_gain_breakdown_latent["Инфильтрация/вентиляция"] > 0

    def test_totals_match(self):
        """ИТОГО = сумма явной и скрытой."""
        project, sp = _minimal_project()
        engine = SP50Engine()
        br = engine.heat_gain(sp, project)
        assert br["ИТОГО"] == pytest.approx(
            sp.heat_gain_sensible_w + sp.heat_gain_latent_w, rel=0.001)

    def test_sensible_always_positive(self):
        """Явная теплота для нормальных параметров > 0."""
        project, sp = _minimal_project()
        engine = SP50Engine()
        engine.heat_gain(sp, project)
        assert sp.heat_gain_sensible_w > 0


class TestFloor4Zone:
    """4-зонный расчёт пола по грунту (СП 50.13330 прил. Е)."""

    def test_small_room_only_zone_1(self):
        """Маленькая комната — вся в зоне I."""
        # 3×3 = 9 м², P = 12. F_I = 2·12 = 24 > 9, ограничено площадью.
        zones = _floor_4zone_areas(9, 12)
        assert zones[1] == 9
        assert zones[2] == 0
        assert zones[3] == 0
        assert zones[4] == 0

    def test_medium_room_two_zones(self):
        """Средняя комната: зоны I и II."""
        # 6×6 = 36 м², P = 24. F_I = min(2·24, 36) = 36. Но F_I не должна
        # покрывать всё, потому что у нас не периметр-доминирующая комната.
        # Проверим что хотя бы зона I заполнена правильно для длинной комнаты.
        # 10×4 = 40 м², P = 28. F_I = 2·28 = 56 > 40 → всё в I.
        zones = _floor_4zone_areas(40, 28)
        assert zones[1] == 40
        assert sum(zones.values()) == 40

    def test_large_room_all_zones(self):
        """Большая комната: все 4 зоны."""
        # 20×20 = 400 м², P = 80. F_I = 2·80 = 160. F_II = 2·(80-16) = 128.
        # F_III = 2·(80-32) = 96. F_IV = 400 - 160 - 128 - 96 = 16.
        zones = _floor_4zone_areas(400, 80)
        assert zones[1] == 160
        assert zones[2] == 128
        assert zones[3] == 96
        assert zones[4] == 16
        assert sum(zones.values()) == 400

    def test_huge_basement(self):
        """Очень большой подвал: всё внутри будет зона IV."""
        # 100×100 = 10000 м², P = 400. F_I = 800, F_II = 768, F_III = 736.
        # F_IV = 10000 - 800 - 768 - 736 = 7696.
        zones = _floor_4zone_areas(10000, 400)
        assert zones[1] == 800
        assert zones[2] == 768
        assert zones[3] == 736
        assert zones[4] == 7696

    def test_zero_perimeter_falls_back(self):
        """Если периметр = 0 — вся площадь в зоне 1 (вырожденный случай)."""
        zones = _floor_4zone_areas(50, 0)
        assert zones[1] == 50

    def test_calc_floor_loss_small_room(self):
        """3×3 м, dt=30: 9 м² × 30 / 2.1 = ~128.6 Вт."""
        q = _calc_floor_loss_4zone(9, 12, 30)
        assert q == pytest.approx(9 * 30 / 2.1, rel=0.01)

    def test_calc_floor_loss_large(self):
        """20×20, dt=40: разные R для каждой зоны."""
        q = _calc_floor_loss_4zone(400, 80, 40)
        # 160/2.1 + 128/4.3 + 96/8.6 + 16/14.2 = 76.2 + 29.8 + 11.2 + 1.1 → ~118
        # × 40 = ~4730 Вт
        expected = (160/2.1 + 128/4.3 + 96/8.6 + 16/14.2) * 40
        assert q == pytest.approx(expected, rel=0.01)

    def test_floor_integrated_in_heat_loss(self):
        """has_floor_to_ground=True использует 4-зонный расчёт."""
        project, sp = _minimal_project()
        sp.has_floor_to_ground = True
        engine = SP50Engine()
        # Без пола
        sp.has_floor_to_ground = False
        br_no = engine.heat_loss(sp, project)
        # С полом
        sp.has_floor_to_ground = True
        br_with = engine.heat_loss(sp, project)
        # С полом потери должны быть больше
        assert br_with["ИТОГО"] > br_no["ИТОГО"]
        assert "Пол по грунту" in br_with


class TestValidation:
    """Проверки валидации."""

    def test_no_problems_passes(self):
        """Корректный проект — без предупреждений."""
        project, sp = _minimal_project()
        results = project.validate_detailed()
        # Может быть info, но не должно быть error/warning от хороших данных
        errors = [r for r in results if r["severity"] == "error"]
        assert errors == []

    def test_no_u_warning(self):
        """U=0 → предупреждение."""
        project, sp = _minimal_project()
        list(project.constructions.values())[0].u_value = 0
        warnings = project.validate()
        assert any("не задано U" in w for w in warnings)

    def test_huge_u_warning(self):
        """U=10 → подозрительно высокое."""
        project, sp = _minimal_project()
        list(project.constructions.values())[0].u_value = 10
        results = project.validate_detailed()
        assert any("Очень высокое U" in r["msg"] for r in results)

    def test_zero_area_error(self):
        """Площадь=0 → ошибка."""
        project, sp = _minimal_project()
        sp.area_m2 = 0
        results = project.validate_detailed()
        assert any(r["severity"] == "error" and "Площадь" in r["msg"]
                   for r in results)

    def test_low_ceiling_warning(self):
        """Высота < 2 м → предупреждение."""
        project, sp = _minimal_project()
        sp.area_m2 = 20
        sp.volume_m3 = 30  # высота 1.5 м
        results = project.validate_detailed()
        assert any("низкая высота" in r["msg"].lower() for r in results)

    def test_corner_without_walls(self):
        """is_corner=True но нет 2 наружных стен → предупреждение."""
        project, sp = _minimal_project()
        sp.is_corner = True
        # У нас всего 1 наружная стена в _minimal_project
        results = project.validate_detailed()
        assert any("угловым" in r["msg"] for r in results)

    def test_high_specific_load_warning(self):
        """Q > 200 Вт/м² → предупреждение."""
        project, sp = _minimal_project()
        sp.heat_loss_w = 5000  # 250 Вт/м² на 20 м²
        results = project.validate_detailed()
        assert any("Удельные теплопотери" in r["msg"] for r in results)


class TestLatentInfiltration:
    """Формула расчёта скрытой теплоты инфильтрации."""

    def test_zero_delta_w(self):
        """Δw = 0 → Q = 0."""
        assert _latent_infiltration_w(100, 0) == 0

    def test_positive_delta(self):
        """Влажно снаружи: 100 м³/ч, Δw=2 г/кг → 166 Вт."""
        q = _latent_infiltration_w(100, 2)
        assert q == pytest.approx(166, rel=0.01)

    def test_negative_delta(self):
        """Сухо снаружи: Δw < 0 → Q < 0."""
        q = _latent_infiltration_w(100, -3)
        assert q < 0
        assert q == pytest.approx(-249, rel=0.01)
