# -*- coding: utf-8 -*-
"""Тесты для контуров отопления/холодоснабжения, AHU как виртуальных
потребителей, подбора циркуляционных насосов и пересчёта по ручным длинам."""

import pytest
import tempfile, os

from hvac.project import HVACProject
from hvac.models import Space
from hvac.equipment import (
    HeatingSystem, CoolingSystem, VentilationSystem,
    HeatingCircuit, CoolingCircuit, DuctZone,
)
from hvac import pipe_sizing
from hvac.pipe_sizing import (
    select_pump, build_circuit_network, recompute_pipe_network,
    size_project_pipes, size_project_cooling_pipes, water_properties,
)
from hvac.ahu_load import aggregate_ahus, summary_by_circuit


def _add_space(project, sid, num, level, area, q_heat=0, q_gain=0,
               supply=0, ach_inf=0.0):
    sp = Space(space_id=sid, number=num, name="X", level=level,
               area_m2=area, volume_m3=area * 3, height_m=3,
               room_type="Офис", ach_inf=ach_inf, supply_m3h=supply)
    sp.heat_loss_w = q_heat
    sp.heat_gain_w = q_gain
    project.spaces.append(sp)
    project._space_by_id[sid] = sp
    return sp


# ============================================================================
# Подбор насоса
# ============================================================================

class TestPumpSelection:

    def test_small_circuit_picks_small_pump(self):
        """Малый радиаторный контур: ~0.5 м³/ч, 2 м напор → UPS 25-40."""
        model, q_max, h_max = select_pump(0.5, 2.0)
        assert "UPS" in model or "Magna" in model
        assert q_max >= 0.5 * 1.1
        assert h_max >= 2.0 * 1.3

    def test_large_circuit_picks_magna(self):
        """50 м³/ч, 8 м напор → должен быть из Magna серии."""
        model, q_max, h_max = select_pump(50.0, 8.0)
        assert q_max >= 50.0 * 1.1
        assert h_max >= 8.0 * 1.3

    def test_oversized_returns_warning(self):
        """Запрос больше каталога → возвращается крупнейший с пометкой."""
        model, _, _ = select_pump(1000.0, 50.0)
        assert "уточнения" in model or "превышен" in model

    def test_zero_flow_returns_dash(self):
        model, _, _ = select_pump(0, 5)
        assert model == "—"


# ============================================================================
# Свойства воды
# ============================================================================

class TestWaterProperties:

    def test_at_7c_dense(self):
        rho, nu = water_properties(7)
        assert rho == pytest.approx(999.9, rel=0.01)

    def test_at_70c_less_dense(self):
        rho, _ = water_properties(70)
        assert rho == pytest.approx(977.7, rel=0.01)

    def test_interpolation_at_30c(self):
        rho, _ = water_properties(30)
        # 30°C между 7 и 45: интерполируем
        assert 990 < rho < 999


# ============================================================================
# Построение контура
# ============================================================================

class TestCircuitNetwork:

    def test_single_radiator_circuit(self):
        """Один радиатор 2 кВт → сеть с подводкой/веткой/магистралью."""
        project = HVACProject()
        sp = _add_space(project, "1", "101", "1", 20, q_heat=2000)
        net = build_circuit_network(
            "Рад-1", spaces=[sp],
            circuit_type="radiator", medium="heating",
            t_supply=80, t_return=60,
        )
        assert net.n_terminals == 1
        assert net.total_heat_load_w == 2000
        assert net.delta_t_k == 20
        # 3 типа участков: connection, branch, main
        types = {s.section_type for s in net.sections}
        assert types == {"connection", "branch", "main"}
        assert net.pump_head_m > 0
        assert net.pump_model

    def test_floor_heating_lower_temp(self):
        """Тёплый пол 45/35 → меньшая Δt → больший расход на тот же Q."""
        project = HVACProject()
        sp = _add_space(project, "1", "101", "1", 50, q_heat=2500)

        net_rad = build_circuit_network(
            "Рад", spaces=[sp], t_supply=80, t_return=60, medium="heating",
        )
        net_tp = build_circuit_network(
            "ТП", spaces=[sp], t_supply=45, t_return=35, medium="heating",
            circuit_type="floor",
        )
        # При Δt=10 (ТП) расход в 2 раза больше чем при Δt=20 (рад.)
        assert net_tp.total_flow_kg_h == pytest.approx(
            net_rad.total_flow_kg_h * 2.0, rel=0.05)

    def test_ahu_as_virtual_consumer(self):
        """AHU добавляется как виртуальная подводка к контуру."""
        project = HVACProject()
        sp = _add_space(project, "1", "101", "1", 20, q_heat=2000)
        net = build_circuit_network(
            "AHU-кал", spaces=[sp],
            ahu_loads=[("ПВ-1", 15000)],   # 15 кВт калорифер AHU
            circuit_type="ahu_heater",
        )
        assert net.n_terminals == 2  # 1 помещение + 1 AHU
        assert net.total_heat_load_w == 17000
        # Среди подводок должна быть виртуальная для AHU
        virtual = [s for s in net.sections if s.is_virtual]
        assert len(virtual) == 1
        assert "ПВ-1" in virtual[0].note

    def test_cooling_circuit_uses_heat_gain(self):
        """Контур охлаждения берёт sp.heat_gain_w, а не heat_loss_w."""
        project = HVACProject()
        sp = _add_space(project, "1", "101", "1", 20, q_heat=2000, q_gain=4000)
        net = build_circuit_network(
            "ФК", spaces=[sp], medium="cooling",
            t_supply=7, t_return=12, insulated=True,
        )
        assert net.total_heat_load_w == 4000   # не 2000!
        assert net.medium == "cooling"
        assert net.insulated is True


# ============================================================================
# Группировка проекта по контурам
# ============================================================================

class TestProjectGrouping:

    def _make_project_with_circuits(self):
        """Проект с ИТП на 3 контура: радиаторы, тёплый пол, AHU-калорифер."""
        project = HVACProject()
        # Помещение 101 — радиаторы
        sp1 = _add_space(project, "s1", "101", "1", 20, q_heat=2000, q_gain=2500)
        sp1.system_heating = "ИТП-1"
        sp1.circuit_heating = "Рад-1"
        sp1.system_cooling = "Чиллер-1"
        sp1.circuit_cooling = "ФК-1"
        # Помещение 201 — тёплый пол
        sp2 = _add_space(project, "s2", "201", "2", 30, q_heat=3000)
        sp2.system_heating = "ИТП-1"
        sp2.circuit_heating = "ТП-1"
        # Помещение 102 без контура — попадает в fallback "ИТП-2"
        sp3 = _add_space(project, "s3", "102", "1", 25, q_heat=1500)
        sp3.system_heating = "ИТП-2"
        # Контуры
        project.heating_systems["ИТП-1"] = HeatingSystem(name="ИТП-1")
        project.heating_systems["ИТП-2"] = HeatingSystem(name="ИТП-2")
        project.heating_circuits["Рад-1"] = HeatingCircuit(
            name="Рад-1", parent_system="ИТП-1", circuit_type="radiator",
            t_supply=80, t_return=60)
        project.heating_circuits["ТП-1"] = HeatingCircuit(
            name="ТП-1", parent_system="ИТП-1", circuit_type="floor",
            t_supply=45, t_return=35, has_mixing_node=True)
        project.cooling_systems["Чиллер-1"] = CoolingSystem(name="Чиллер-1")
        project.cooling_circuits["ФК-1"] = CoolingCircuit(
            name="ФК-1", parent_system="Чиллер-1", circuit_type="fancoil",
            t_supply=7, t_return=12)
        return project

    def test_heating_grouped_by_circuit_not_system(self):
        """Радиатор и тёплый пол одного ИТП = разные сети с разными Δt."""
        project = self._make_project_with_circuits()
        nets = size_project_pipes(project)
        assert "Рад-1" in nets
        assert "ТП-1" in nets
        assert nets["Рад-1"].delta_t_k == 20
        assert nets["ТП-1"].delta_t_k == 10
        # Каждый имеет свой подобранный насос
        assert nets["Рад-1"].pump_model
        assert nets["ТП-1"].pump_model

    def test_orphan_space_falls_back_to_system(self):
        """Помещение с system_heating без circuit_heating → отдельная сеть."""
        project = self._make_project_with_circuits()
        nets = size_project_pipes(project)
        assert "ИТП-2" in nets
        assert nets["ИТП-2"].total_heat_load_w == 1500

    def test_cooling_uses_separate_function(self):
        """Холодильные контуры считаются через size_project_cooling_pipes."""
        project = self._make_project_with_circuits()
        nets = size_project_cooling_pipes(project)
        assert "ФК-1" in nets
        assert nets["ФК-1"].medium == "cooling"
        assert nets["ФК-1"].t_supply_c == 7
        assert nets["ФК-1"].total_heat_load_w == 2500  # heat_gain_w sp1

    def test_ahu_load_added_to_circuit(self):
        """AHU с heating_circuit добавляет свою нагрузку калорифера в контур."""
        project = self._make_project_with_circuits()
        # AHU с калорифером на контур ТП-1
        ahu = VentilationSystem(name="ПВ-1", heating_circuit="ТП-1",
                                 t_supply_winter=18.0, has_recovery=False)
        project.ventilation_systems["ПВ-1"] = ahu
        project.ahu_loads = {"ПВ-1": {"q_heater_w": 5000,
                                       "q_cooler_total_w": 0}}
        nets = size_project_pipes(project)
        # ТП-1 должен включать sp2 (3000 Вт) + AHU (5000 Вт) = 8000
        assert nets["ТП-1"].total_heat_load_w == 8000
        # Среди участков должна быть виртуальная для AHU
        virtual = [s for s in nets["ТП-1"].sections if s.is_virtual]
        assert len(virtual) == 1


# ============================================================================
# Пересчёт по ручным длинам
# ============================================================================

class TestRecompute:

    def test_recompute_with_longer_pipes_higher_dp(self):
        """Увеличение длин участков → выше Δp → выше требуемый напор."""
        project = HVACProject()
        sp = _add_space(project, "1", "101", "1", 50, q_heat=5000)
        net = build_circuit_network(
            "Тест", spaces=[sp], t_supply=80, t_return=60,
        )
        head_before = net.pump_head_m

        # Удваиваем длины всех участков
        for s in net.sections:
            s.length_m *= 2.0
        recompute_pipe_network(net)

        # Δp вырастет (но не строго в 2 раза из-за разных вкладов трения и
        # местных сопротивлений). Главное — увеличился.
        assert net.pump_head_m > head_before * 1.2

    def test_elevation_adds_to_pump_head(self):
        """Перепад высот добавляется к напору насоса."""
        project = HVACProject()
        sp = _add_space(project, "1", "101", "1", 50, q_heat=5000)
        net = build_circuit_network(
            "Тест", spaces=[sp], t_supply=80, t_return=60,
        )
        head_before = net.pump_head_m

        # Указываем 15 м перепад на магистрали (10-этажное здание)
        for s in net.sections:
            if s.section_type == "main":
                s.elevation_m = 15.0
        recompute_pipe_network(net)

        # Должен вырасти примерно на 15 × 1.3 = 19.5 м
        # (статич. давление умножается на запас 1.3)
        assert net.pump_head_m > head_before + 15
        assert net.pump_head_m < head_before + 30


# ============================================================================
# AHU агрегация (новый модуль)
# ============================================================================

class TestAHUAggregation:

    def test_aggregation_returns_structured_loads(self):
        """aggregate_ahus возвращает AHULoad с полной информацией."""
        project = HVACProject()
        sp = _add_space(project, "1", "B01-001", "1", 20, supply=1000)
        project.auto_assign_zones(mode="by_prefix")

        loads = aggregate_ahus(project)
        assert "Блок B01" in loads
        load = loads["Блок B01"]
        assert load.supply_m3_h == 1000
        assert load.q_heater_w > 0
        assert load.n_spaces == 1

    def test_summary_by_circuit_groups_loads(self):
        """summary_by_circuit группирует нагрузки AHU по контурам ИТП."""
        project = HVACProject()
        sp = _add_space(project, "1", "B01-001", "1", 20, supply=1000)
        project.auto_assign_zones(mode="by_prefix")

        ahu = project.ventilation_systems["Блок B01"]
        ahu.heating_circuit = "AHU-кал"
        ahu.cooling_circuit = "AHU-хол"

        loads = aggregate_ahus(project)
        summary = summary_by_circuit(loads)
        assert "AHU-кал" in summary
        assert summary["AHU-кал"]["q_heating_w"] > 0
        assert "Блок B01" in summary["AHU-кал"]["ahus"]


# ============================================================================
# JSON персистентность
# ============================================================================

class TestPersistence:

    def test_circuits_round_trip(self):
        """Контуры, зоны и cooling_pipe_networks сохраняются/загружаются."""
        from hvac.io_json import save_project, load_project

        project = HVACProject()
        project.new_empty_project("test", "Ташкент")
        project.add_space("101", "Кабинет", "1", 20.0)
        sp = project.spaces[0]
        sp.heat_loss_w = 2000
        sp.heat_gain_w = 2500

        project.heating_circuits["Рад-1"] = HeatingCircuit(
            name="Рад-1", parent_system="ИТП-1", t_supply=80, t_return=60)
        project.cooling_circuits["ФК-1"] = CoolingCircuit(
            name="ФК-1", parent_system="Чиллер-1", t_supply=7, t_return=12)
        project.duct_zones["Зона А"] = DuctZone(
            name="Зона А", parent_ahu="ПВ-1", has_vav=True)
        sp.circuit_heating = "Рад-1"
        sp.circuit_cooling = "ФК-1"
        sp.duct_zone = "Зона А"

        # Считаем сеть и проверяем что она сохранится с насосом
        nets = size_project_pipes(project)
        project.pipe_networks = nets
        cooling_nets = size_project_cooling_pipes(project)
        project.cooling_pipe_networks = cooling_nets

        with tempfile.NamedTemporaryFile(mode="w", suffix=".json",
                                          delete=False) as f:
            path = f.name
        try:
            save_project(project, path)
            p2 = HVACProject()
            load_project(p2, path)
            assert "Рад-1" in p2.heating_circuits
            assert "ФК-1" in p2.cooling_circuits
            assert "Зона А" in p2.duct_zones
            assert p2.spaces[0].circuit_heating == "Рад-1"
            # Сети тоже восстановились с моделью насоса
            assert "Рад-1" in p2.pipe_networks
            assert "ФК-1" in p2.cooling_pipe_networks
            assert p2.pipe_networks["Рад-1"].pump_model
        finally:
            os.unlink(path)
