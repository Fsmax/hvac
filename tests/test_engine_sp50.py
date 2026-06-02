# -*- coding: utf-8 -*-
"""Тесты движка СП 50.13330 на известных примерах."""

import pytest
from hvac.project import HVACProject
from hvac.models import Space, BoundaryElement, Construction
from hvac.engine.sp50 import SP50Engine


def make_minimal_project():
    """Создаёт минимальный проект для тестов: одно помещение,
    одна наружная стена, заданная конструкция."""
    project = HVACProject()
    project.params.t_out_heating = -25
    project.params.t_out_cooling = 28
    project.params.daily_amplitude = 10
    project.params.solar_intensity_w_m2 = 600
    project.params.inf_correction_k = 0.7
    project.params.safety_margin_heating = 1.0   # без запаса — для проверки чистой формулы
    project.params.safety_margin_cooling = 1.0

    sp = Space(
        space_id="1",
        number="101",
        name="Office",
        level="L1",
        area_m2=20.0,
        volume_m3=60.0,
        height_m=3.0,
        room_type="Офис",
        t_in_heat=20,
        t_in_cool=24,
        ach_inf=0.5,
        lighting_w_m2=12,
        equipment_w_m2=15,
        occupancy_people=2,
        is_corner=False,
    )
    project.spaces = [sp]
    project._space_by_id = {"1": sp}

    # Одна наружная стена: 3×4 = 12 м², U=0.5, на север (β=0.10)
    wall = BoundaryElement(
        space_id="1",
        row_type="external_wall",
        is_exterior=True,
        element_id="W1",
        category="Стены",
        family="Базовая стена",
        type_name="Test",
        boundary_length_m=4.0,
        space_height_m=3.0,
        approx_area_m2=12.0,
        element_area_m2=12.0,
        thickness_mm=210,
        function="Наружные",
        host_element_id="",
        boundary_space_count=1,
        construction_key="Стены / Базовая стена / Test / 210",
        orientation_deg=0,
        orientation="N",
        u_value=0.5,
        net_area_m2=12.0,
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


class TestHeatLoss:

    def test_simple_wall(self):
        """Q = U·F·ΔT·(1+β) для одной стены на север."""
        project, sp = make_minimal_project()
        engine = SP50Engine()
        result = engine.heat_loss(sp, project)

        # ΔT = 20 - (-25) = 45 K
        # Q_стена = 0.5 · 12 · 45 · (1 + 0.10) = 297 Вт
        q_wall = 0.5 * 12 * 45 * 1.10
        assert pytest.approx(result["Стены"], rel=0.01) == q_wall
        assert pytest.approx(result["Через ограждения"], rel=0.01) == q_wall

    def test_infiltration_component(self):
        """Инфильтрация: Q = 0.28 · L · ρ · c · ΔT · k."""
        project, sp = make_minimal_project()
        engine = SP50Engine()
        result = engine.heat_loss(sp, project)
        # L = 0.5 · 60 = 30 м³/ч
        # ρ(-25) = 353/(273-25) = 1.4234
        # Q_инф = 0.28 · 30 · 1.4234 · 1.005 · 45 · 0.7 = 378.4 Вт
        assert result["Инфильтрация"] > 0
        assert result["Инфильтрация"] < 500

    def test_corner_no_supplement(self):
        """В СП 50.13330 (актуальном) надбавки на угловое помещение нет —
        правило +0.05 из отменённого СНиП 2.04.05-91 не применяется.
        Флаг is_corner остаётся информационным (используется в валидаторе)."""
        project, sp = make_minimal_project()
        engine = SP50Engine()
        normal = engine.heat_loss(sp, project)["Через ограждения"]
        sp.is_corner = True
        cornered = engine.heat_loss(sp, project)["Через ограждения"]
        assert pytest.approx(cornered, rel=1e-9) == normal

    def test_orientation_south_zero_supplement(self):
        """Юг = β 0, должно быть меньше чем север."""
        project, sp = make_minimal_project()
        engine = SP50Engine()
        north = engine.heat_loss(sp, project)["Стены"]
        project.elements[0].orientation = "S"
        south = engine.heat_loss(sp, project)["Стены"]
        # Север (1+0.10) vs Юг (1+0.0): отношение 1.0/1.10
        assert pytest.approx(south / north, rel=0.01) == 1.0 / 1.10

    def test_no_dt_no_loss(self):
        """Если tв = tн, теплопотерь нет."""
        project, sp = make_minimal_project()
        project.params.t_out_heating = sp.t_in_heat
        engine = SP50Engine()
        result = engine.heat_loss(sp, project)
        assert result["ИТОГО"] == 0.0

    def test_safety_margin_applied(self):
        """Запас на отопление умножает итог."""
        project, sp = make_minimal_project()
        engine = SP50Engine()
        no_margin = engine.heat_loss(sp, project)["ИТОГО"]
        project.params.safety_margin_heating = 1.20
        with_margin = engine.heat_loss(sp, project)["ИТОГО"]
        assert pytest.approx(with_margin / no_margin, rel=0.001) == 1.20

    def test_floor_over_unheated_applies_n(self):
        """Перекрытие над неотап. подвалом (КМК Табл.3): Q=U·A·Δt·n, n<1.

        area=20 м², Δt=45, U_пол=0.35, n=0.6 → 0.35·20·45·0.6 = 189 Вт."""
        from hvac.catalogs.constructions import DEFAULT_U_BY_CATEGORY
        project, sp = make_minimal_project()
        engine = SP50Engine()
        base = engine.heat_loss(sp, project)
        assert "Пол над неотап." not in base  # по умолчанию выключено

        sp.floor_over_unheated_n = 0.6
        res = engine.heat_loss(sp, project)
        dt = sp.t_in_heat - project.params.t_out_heating
        expected = DEFAULT_U_BY_CATEGORY["Пол"] * sp.area_m2 * dt * 0.6
        assert pytest.approx(res["Пол над неотап."], rel=1e-6) == expected
        assert res["Через ограждения"] > base["Через ограждения"]

    def test_floor_over_unheated_zero_no_effect(self):
        """n=0 (по умолчанию) — статья отсутствует, теплопотери не меняются."""
        project, sp = make_minimal_project()
        engine = SP50Engine()
        a = engine.heat_loss(sp, project)["Через ограждения"]
        sp.floor_over_unheated_n = 0.0
        b = engine.heat_loss(sp, project)["Через ограждения"]
        assert pytest.approx(a, rel=1e-9) == b


class TestHeatGain:

    def test_internal_gains(self):
        """Люди + освещение + оборудование."""
        project, sp = make_minimal_project()
        engine = SP50Engine()
        result = engine.heat_gain(sp, project)

        # Люди: 2 · 130 = 260 Вт
        assert pytest.approx(result["Люди"], rel=0.01) == 260
        # Освещение: 20 · 12 = 240 Вт
        assert pytest.approx(result["Освещение"], rel=0.01) == 240
        # Оборудование: 20 · 15 = 300 Вт
        assert pytest.approx(result["Оборудование"], rel=0.01) == 300

    def test_solar_only_with_shgc(self):
        """Солнечная нагрузка идёт только через окна с SHGC>0."""
        project, sp = make_minimal_project()
        engine = SP50Engine()
        # У стены SHGC=0 → солнца нет
        result = engine.heat_gain(sp, project)
        assert result["Солнечная радиация"] == 0

        # Меняем на окно с SHGC=0.6
        project.constructions[project.elements[0].construction_key].shgc = 0.6
        result = engine.heat_gain(sp, project)
        # SHGC · F · I · пик(N=0.20) · CLF(0.75) = 0.6 · 12 · 600 · 0.20 · 0.75 = 648 Вт
        assert pytest.approx(result["Солнечная радиация"], rel=0.01) == 648


class TestProjectIntegration:

    def test_recalculate_runs(self):
        """recalculate() должен заполнить heat_loss_w и heat_gain_w."""
        project, sp = make_minimal_project()
        project.recalculate()
        assert sp.heat_loss_w > 0
        assert sp.heat_gain_w > 0
        assert "ИТОГО" in sp.heat_loss_breakdown

    def test_validation_no_u(self):
        """validate() должен предупредить о пустых U."""
        project, sp = make_minimal_project()
        project.constructions[project.elements[0].construction_key].u_value = 0
        warnings = project.validate()
        assert any("не задано U" in w for w in warnings)

    def test_validation_clean(self):
        """Без проблем — нет предупреждений."""
        project, sp = make_minimal_project()
        warnings = project.validate()
        assert warnings == []
