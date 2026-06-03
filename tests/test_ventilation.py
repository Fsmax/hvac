# -*- coding: utf-8 -*-
"""Тесты движка вентиляции."""

import pytest
from hvac.project import HVACProject
from hvac.models import Space
from hvac.engine.ventilation import SP60VentilationEngine


def _make_space(room_type, area_m2=20, volume_m3=60, people=2.0):
    return Space(
        space_id="1", number="101", name="Test", level="L1",
        area_m2=area_m2, volume_m3=volume_m3,
        room_type=room_type, occupancy_people=people,
        lighting_w_m2=12, equipment_w_m2=15,
    )


def _make_project(space):
    p = HVACProject()
    p.spaces = [space]
    p._space_by_id = {space.space_id: space}
    return p


class TestSP60Ventilation:

    def test_office_by_people(self):
        """Офис, 2 чел → 120 м³/ч (60 × 2, ШНҚ 2.08.02-23 табл.26)."""
        sp = _make_space("Офис", area_m2=20, volume_m3=60, people=2.0)
        engine = SP60VentilationEngine()
        result = engine.calculate(sp, _make_project(sp))
        assert result["supply_m3h"] == pytest.approx(120, rel=0.01)
        assert result["exhaust_m3h"] == pytest.approx(120, rel=0.01)  # balance=0
        assert "По людям" in result["method"]

    def test_office_min_ach_wins(self):
        """Офис большой, 1 чел → ACH=1 победит (V=200, 1ACH=200>40)."""
        sp = _make_space("Офис", area_m2=50, volume_m3=200, people=1.0)
        engine = SP60VentilationEngine()
        result = engine.calculate(sp, _make_project(sp))
        # max(40, 200) = 200 м³/ч по кратности
        assert result["supply_m3h"] == pytest.approx(200, rel=0.01)
        assert "По кратности" in result["method"]

    def test_residential_per_m2(self):
        """Жилая, 50 м² → 150 м³/ч (50 × 3) или 30·чел — что больше."""
        sp = _make_space("Жилая комната", area_m2=50, volume_m3=150, people=2)
        engine = SP60VentilationEngine()
        result = engine.calculate(sp, _make_project(sp))
        # m3/чел=30·2=60; m3/m2=50·3=150; ach=150·0.5=75 → max=150
        assert result["supply_m3h"] == pytest.approx(150, rel=0.01)
        assert "По площади" in result["method"]

    def test_wc_exhaust_only(self):
        """Туалет 5 м² → exhaust 100 м³/ч (ШНҚ 2.08.02-23: 100 на унитаз),
        приток = 0 (переток)."""
        sp = _make_space("Санузел", area_m2=5, volume_m3=15, people=0)
        engine = SP60VentilationEngine()
        result = engine.calculate(sp, _make_project(sp))
        assert result["supply_m3h"] == 0
        assert result["exhaust_m3h"] == pytest.approx(100, rel=0.01)
        assert "Только вытяжка" in result["method"]

    def test_wc_large_uses_area(self):
        """Большой санузел 10 м² → 200 м³/ч (10 × 20 м³/ч·м²)."""
        sp = _make_space("Санузел", area_m2=10, volume_m3=30, people=0)
        engine = SP60VentilationEngine()
        result = engine.calculate(sp, _make_project(sp))
        assert result["exhaust_m3h"] == pytest.approx(200, rel=0.01)

    def test_vestibule_ach_shnk(self):
        """Вестибюль (ШНҚ 2.08.02-23 табл.19): кратность ≥2 → V×2."""
        sp = _make_space("Вестибюль", area_m2=20, volume_m3=60, people=1.0)
        engine = SP60VentilationEngine()
        result = engine.calculate(sp, _make_project(sp))
        # max(40 м³/ч·чел, 60×2=120 по кратности) = 120
        assert result["supply_m3h"] == pytest.approx(120, rel=0.01)
        assert "По кратности" in result["method"]

    def test_shower_by_ach_shnk(self):
        """Душевая (ШНҚ 2.08.02-23 табл.19): кратность ≥5, вытяжка > притока."""
        sp = _make_space("Душевая", area_m2=10, volume_m3=30, people=0)
        engine = SP60VentilationEngine()
        result = engine.calculate(sp, _make_project(sp))
        # supply = 30×5 = 150; balance=-10 → exhaust = 150×1.10 = 165
        assert result["supply_m3h"] == pytest.approx(150, rel=0.01)
        assert result["exhaust_m3h"] == pytest.approx(165, rel=0.01)
        assert result["exhaust_m3h"] > result["supply_m3h"]

    def test_sports_hall_per_person_shnk(self):
        """Спортзал (ШНҚ 2.08.02-23 табл.23): 20 чел → 1600 м³/ч (80 × 20)."""
        sp = _make_space("Спортзал", area_m2=200, volume_m3=600, people=20)
        engine = SP60VentilationEngine()
        result = engine.calculate(sp, _make_project(sp))
        # max(20×80=1600, 600×1=600) = 1600 по людям
        assert result["supply_m3h"] == pytest.approx(1600, rel=0.01)
        assert "По людям" in result["method"]

    def test_engine_name_is_shnk(self):
        """Движок вентиляции теперь идентифицируется как ШНҚ 2.08.02-23."""
        assert SP60VentilationEngine().name == "ШНҚ 2.08.02-23"

    def test_parking_co_warning(self):
        """Парковка — предупреждение проверить расход по CO (ШНҚ/СП 113)."""
        sp = _make_space("Гараж / автостоянка", area_m2=1000, volume_m3=3000,
                         people=0)
        result = SP60VentilationEngine().calculate(sp, _make_project(sp))
        assert any("CO" in w for w in result["warnings"])

    def test_exhibition_per_person_shnk(self):
        """Выставочный зал (ШНҚ 2.08.02-23 табл.21): ≥20 м³/ч·чел."""
        sp = _make_space("Выставочный зал", area_m2=100, volume_m3=400,
                         people=30)
        result = SP60VentilationEngine().calculate(sp, _make_project(sp))
        # max(30×20=600, 400×1=400) = 600 по людям
        assert result["supply_m3h"] == pytest.approx(600, rel=0.01)

    def test_dishwash_by_ach_shnk(self):
        """Моечная (ШНҚ 2.08.02-23 табл.24): кратность ≥6, вытяжка > притока."""
        sp = _make_space("Моечная", area_m2=10, volume_m3=30, people=0)
        result = SP60VentilationEngine().calculate(sp, _make_project(sp))
        # supply = 30×6 = 180; balance=-10 → exhaust = 180×1.10 = 198
        assert result["supply_m3h"] == pytest.approx(180, rel=0.01)
        assert result["exhaust_m3h"] == pytest.approx(198, rel=0.01)

    def test_kitchen_has_hood(self):
        """Ресторан/кухня — должен быть зонт + вытяжка > притока."""
        sp = _make_space("Ресторан / кухня", area_m2=50, volume_m3=150, people=20)
        engine = SP60VentilationEngine()
        result = engine.calculate(sp, _make_project(sp))
        # supply: max(20·30=600, 50·4=200, 150·1=150) = 600
        # balance=-15: exhaust = 600·(1−(−0.15)) = 600·1.15 = 690
        assert result["supply_m3h"] == pytest.approx(600, rel=0.01)
        assert result["exhaust_m3h"] == pytest.approx(690, rel=0.01)
        assert result["exhaust_m3h"] > result["supply_m3h"]  # отриц. давление
        assert result["hood_m3h"] > 0
        # зонт — 40% от вытяжки = 276
        assert result["hood_m3h"] == pytest.approx(276, rel=0.01)

    def test_elevator_NC(self):
        """Лифт — без вентиляции."""
        sp = _make_space("Лифт / шахта", area_m2=5, volume_m3=15, people=0)
        engine = SP60VentilationEngine()
        result = engine.calculate(sp, _make_project(sp))
        assert result["supply_m3h"] == 0
        assert result["exhaust_m3h"] == 0
        assert "NC" in result["method"]

    def test_carpark_per_m2(self):
        """Парковка 7000 м² → 42000 м³/ч (6·7000) или ACH=1.5·V."""
        sp = _make_space("Гараж / автостоянка", area_m2=7000, volume_m3=21000)
        engine = SP60VentilationEngine()
        result = engine.calculate(sp, _make_project(sp))
        # m3/m2: 7000·6=42000; min_ach: 21000·1.5=31500 → max=42000
        assert result["supply_m3h"] == pytest.approx(42000, rel=0.01)

    def test_server_room_by_equipment(self):
        """Серверная: расход по тепловыделению оборудования."""
        sp = _make_space("Серверная", area_m2=20, volume_m3=60, people=0)
        sp.equipment_w_m2 = 500  # 10 кВт всего
        engine = SP60VentilationEngine()
        result = engine.calculate(sp, _make_project(sp))
        # equipment 500 W/m²·20m² = 10 kW; m3_per_kw=100; → 1000 м³/ч
        # vs min_ach 60·3=180 → max=1000
        assert result["supply_m3h"] == pytest.approx(1000, rel=0.01)
        assert "тепловыделению" in result["method"]

    def test_warning_too_high_ach(self):
        """Очень маленькое помещение с большим расчётом → предупреждение."""
        sp = _make_space("Серверная", area_m2=4, volume_m3=10, people=0)
        sp.equipment_w_m2 = 500  # 2 кВт → 200 м³/ч → 20 ACH
        engine = SP60VentilationEngine()
        result = engine.calculate(sp, _make_project(sp))
        assert any("высокая кратность" in w for w in result["warnings"])


class TestIntegration:

    def test_project_calculate_ventilation(self):
        """calculate_ventilation() заполняет поля Space."""
        sp = _make_space("Офис", area_m2=20, volume_m3=60, people=2)
        project = _make_project(sp)
        project.calculate_ventilation()
        assert sp.supply_m3h > 0
        assert sp.ach_calculated > 0
        assert sp.ventilation_breakdown.get("method")

    def test_independent_from_heat_calc(self):
        """Расчёт вентиляции не зависит от теплового расчёта."""
        sp = _make_space("Офис")
        project = _make_project(sp)
        project.calculate_ventilation()
        assert sp.heat_loss_w == 0
        assert sp.heat_gain_w == 0
        assert sp.supply_m3h > 0


class TestUserOverrides:
    """Ручная правка значений вентиляции."""

    def test_modified_skipped_on_recalc(self):
        """Помещение с vent_user_modified=True не пересчитывается."""
        sp = _make_space("Офис", area_m2=20, volume_m3=60, people=2)
        project = _make_project(sp)
        project.calculate_ventilation()
        # Эталонное значение от автомата
        auto_supply = sp.supply_m3h

        # Пользователь правит вручную
        sp.supply_m3h = 999.0
        sp.exhaust_m3h = 999.0
        sp.vent_user_modified = True

        # Пересчёт не должен затронуть это помещение
        project.calculate_ventilation()
        assert sp.supply_m3h == 999.0
        assert sp.exhaust_m3h == 999.0
        # И при этом auto_supply != 999 — проверяем что иначе бы изменилось
        assert auto_supply != 999.0

    def test_modified_propagates_to_json(self):
        """vent_user_modified сохраняется в JSON-проект.

        Поддерживает оба режима save_project:
        - self-contained (новый, для проектов без CSV) — данные в spaces[]
        - старый режим (с CSV) — данные в space_overrides[].
        """
        import tempfile, json
        from hvac.io_json import save_project

        sp = _make_space("Офис")
        project = _make_project(sp)
        project.calculate_ventilation()
        sp.supply_m3h = 500
        sp.vent_user_modified = True

        with tempfile.NamedTemporaryFile(mode="w", suffix=".json",
                                          delete=False) as f:
            path = f.name
        try:
            save_project(project, path)
            with open(path) as f:
                data = json.load(f)

            if data.get("self_contained"):
                # Новый режим: ищем в spaces[]
                spaces = data.get("spaces", [])
                sp_data = next((s for s in spaces
                                if s.get("space_id") == sp.space_id), None)
                assert sp_data is not None, \
                    f"Помещение {sp.space_id} не найдено в spaces"
                assert sp_data["supply_m3h"] == 500
                assert sp_data["vent_user_modified"] is True
            else:
                # Старый режим: ищем в overrides
                assert sp.space_id in data["space_overrides"]
                ov = data["space_overrides"][sp.space_id]
                assert ov["supply_m3h"] == 500
                assert ov["vent_user_modified"] is True
        finally:
            import os
            os.unlink(path)

    def test_unmodified_pass_recalc(self):
        """Помещение без флага пересчитывается нормально."""
        sp = _make_space("Офис", area_m2=20, volume_m3=60, people=2)
        project = _make_project(sp)
        project.calculate_ventilation()
        first = sp.supply_m3h
        # Меняем кол-во людей
        sp.occupancy_people = 5.0
        project.calculate_ventilation()
        # Должно перерасcчитаться: 5×60 = 300 м³/ч (ШНҚ 2.08.02-23 табл.26)
        assert sp.supply_m3h == pytest.approx(300, rel=0.01)
        assert sp.supply_m3h != first
