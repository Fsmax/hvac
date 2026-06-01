# -*- coding: utf-8 -*-
"""Тесты систем оборудования и расчёта нагрузок от AHU."""

import pytest
import tempfile, os
from hvac.project import HVACProject
from hvac.models import Space
from hvac.equipment import VentilationSystem, HeatingSystem, CoolingSystem


def _add_space(project, sid, num, level, area, supply=0, t_in_heat=20):
    sp = Space(space_id=sid, number=num, name="X", level=level,
               area_m2=area, volume_m3=area*3, height_m=3,
               room_type="Офис", t_in_heat=t_in_heat,
               supply_m3h=supply)
    project.spaces.append(sp)
    project._space_by_id[sid] = sp
    return sp


class TestEquipmentCreation:

    def test_auto_create_systems(self):
        """auto_assign_zones создаёт системы с дефолтами."""
        project = HVACProject()
        _add_space(project, "1", "B01-001", "B1", 20)
        _add_space(project, "2", "B02-001", "B2", 30)
        project.auto_assign_zones(mode="by_prefix")

        assert "Блок B01" in project.ventilation_systems
        assert "Блок B02" in project.ventilation_systems
        assert "Блок B01" in project.heating_systems
        assert "Блок B01" in project.cooling_systems

        # Дефолтные значения
        ahu = project.ventilation_systems["Блок B01"]
        assert ahu.has_recovery == False
        assert ahu.t_supply_winter == 16.0
        assert ahu.t_supply_summer == 18.0


class TestAHULoads:

    def test_simple_supply_no_recovery(self):
        """Простая приточка без рекуперации, парковка 1000 м³/ч,
        нагрев от -15 до +16 = 31K."""
        project = HVACProject()
        project.params.t_out_heating = -15
        project.params.t_out_cooling = 36
        project.params.w_out_summer_g_kg = 8.0
        _add_space(project, "1", "B01-001", "B1", 20, supply=1000)
        project.auto_assign_zones(mode="by_prefix")

        loads = project.calculate_ahu_loads()
        d = loads["Блок B01"]
        # Q = 0.28 × 1000 × 1.42 × 1.005 × 31 × 1.0 = 12390 Вт
        assert d["q_heater_w"] == pytest.approx(12390, rel=0.05)
        assert d["supply_m3h"] == 1000

    def test_with_recovery_reduces_heater(self):
        """Рекуператор 75% существенно снижает нагрузку калорифера.

        Корректная физика: t' = t_нар + η·(t_внут − t_нар).
        При t_нар=-15, t_внут=20, η=0.75 → t' = -15 + 0.75·35 = 11.25°C.
        Нагрев от 11.25 до t_подачи=16 = 4.75 K (вместо 31 K без рекуператора).
        Q = 0.28·1000·ρ(-15)·1.005·4.75 ≈ 1830 Вт.
        """
        project = HVACProject()
        project.params.t_out_heating = -15
        _add_space(project, "1", "OFC-100", "L02", 20, supply=1000)
        project.auto_assign_zones(mode="by_prefix")

        ahu = project.ventilation_systems["Блок OFC"]
        ahu.has_recovery = True
        ahu.recovery_efficiency_winter = 0.75

        loads = project.calculate_ahu_loads()
        d = loads["Блок OFC"]
        assert d["q_heater_w"] == pytest.approx(1830, rel=0.05)
        # Должно быть ~15% от безрекуператорного варианта (4.75/31 = 15%)
        assert d["q_heater_w"] < 2200

    def test_zero_latent_in_dry_climate(self):
        """В сухом климате (Δw < 0) скрытая нагрузка охладителя = 0.

        Если наружный воздух уже суше целевого внутреннего, осушать ничего
        не нужно (отрицательной нагрузки быть не может — охладитель не
        увлажняет). Корректное поведение: Q_lat = 0."""
        project = HVACProject()
        project.params.w_out_summer_g_kg = 7.0
        _add_space(project, "1", "B01-001", "B1", 20, supply=1000)
        project.auto_assign_zones(mode="by_prefix")

        ahu = project.ventilation_systems["Блок B01"]
        ahu.w_supply_summer = 9.3  # цель — внутренние условия

        loads = project.calculate_ahu_loads()
        d = loads["Блок B01"]
        # Δw = 7 - 9.3 = -2.3 → охладитель не осушает → 0
        assert d["q_cooler_lat_w"] == 0.0

    def test_supply_aggregated_per_system(self):
        """Несколько помещений одной системы суммируются."""
        project = HVACProject()
        _add_space(project, "1", "B01-001", "B1", 20, supply=500)
        _add_space(project, "2", "B01-002", "B1", 30, supply=700)
        _add_space(project, "3", "B02-001", "B2", 40, supply=1000)
        project.auto_assign_zones(mode="by_prefix")

        loads = project.calculate_ahu_loads()
        assert loads["Блок B01"]["supply_m3h"] == 1200
        assert loads["Блок B02"]["supply_m3h"] == 1000
        assert loads["Блок B01"]["n_spaces"] == 2


class TestRoomEquipment:
    """Назначение конечного оборудования в помещения (project.set_room_equipment)."""

    def test_method_is_attached_to_project(self):
        """Регрессия: set_room_equipment должен быть МЕТОДОМ проекта, а не
        потерянной вложенной функцией (баг отступа в _project_manual_entry)."""
        project = HVACProject()
        assert hasattr(project, "set_room_equipment")
        assert callable(project.set_room_equipment)

    def test_set_creates_equipment(self):
        project = HVACProject()
        sp = _add_space(project, "1", "101", "L1", 20)
        ok = project.set_room_equipment(
            "1", heating_terminal_type="Радиатор стальной",
            heating_terminal_power_w=1200, heating_terminal_qty=2)
        assert ok is True
        assert sp.room_equipment is not None
        assert sp.room_equipment.heating_total_w == 2400

    def test_unknown_space_returns_false(self):
        project = HVACProject()
        assert project.set_room_equipment("nope", heating_terminal_qty=1) is False

    def test_emits_equipment_changed(self):
        project = HVACProject()
        _add_space(project, "1", "101", "L1", 20)
        seen = []
        project.subscribe("equipment_changed", lambda **k: seen.append(True))
        project.set_room_equipment("1", heating_terminal_qty=1)
        assert seen == [True]

    def test_ignores_unknown_fields(self):
        project = HVACProject()
        sp = _add_space(project, "1", "101", "L1", 20)
        project.set_room_equipment("1", heating_terminal_qty=1, bogus_field=999)
        assert not hasattr(sp.room_equipment, "bogus_field")

    def test_round_trip_persistence(self):
        from hvac.io_json import save_project, load_project
        project = HVACProject()
        _add_space(project, "1", "101", "L1", 20)
        project.set_room_equipment(
            "1", cooling_terminal_type="Фанкойл кассетный",
            cooling_terminal_power_w=3500, cooling_terminal_qty=1,
            notes="осевой")
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json",
                                          delete=False) as f:
            path = f.name
        try:
            save_project(project, path)
            new = HVACProject()
            _add_space(new, "1", "101", "L1", 20)
            load_project(new, path)
            eq = new._space_by_id["1"].room_equipment
            assert eq is not None
            assert eq.cooling_terminal_type == "Фанкойл кассетный"
            assert eq.cooling_total_w == 3500
            assert eq.notes == "осевой"
        finally:
            os.unlink(path)


class TestPersistence:

    def test_save_load_systems(self):
        """Системы оборудования сохраняются в JSON."""
        from hvac.io_json import save_project, load_project

        project = HVACProject()
        _add_space(project, "1", "B01-001", "B1", 20)
        project.auto_assign_zones(mode="by_prefix")

        # Меняем параметры П1
        ahu = project.ventilation_systems["Блок B01"]
        ahu.has_recovery = True
        ahu.recovery_efficiency_winter = 0.80
        ahu.t_supply_winter = 18.0
        ahu.note = "Тестовая установка"

        with tempfile.NamedTemporaryFile(mode="w", suffix=".json",
                                          delete=False) as f:
            path = f.name
        try:
            save_project(project, path)

            # Загружаем в новый проект
            new_project = HVACProject()
            _add_space(new_project, "1", "B01-001", "B1", 20)
            load_project(new_project, path)

            # Параметры должны восстановиться
            assert "Блок B01" in new_project.ventilation_systems
            ahu2 = new_project.ventilation_systems["Блок B01"]
            assert ahu2.has_recovery == True
            assert ahu2.recovery_efficiency_winter == 0.80
            assert ahu2.t_supply_winter == 18.0
            assert ahu2.note == "Тестовая установка"
        finally:
            os.unlink(path)
