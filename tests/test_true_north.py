# -*- coding: utf-8 -*-
"""Тесты для поворота True North и эффективной ориентации."""

import pytest
from hvac.parsers import effective_orientation, azimuth_to_sector
from hvac.project import HVACProject
from hvac.models import Space, BoundaryElement, Construction
from hvac.engine.sp50 import SP50Engine


class TestEffectiveOrientation:

    def test_zero_offset_returns_input(self):
        """Без поворота — возвращается исходная ориентация."""
        assert effective_orientation("N", 0, 0) == "N"
        assert effective_orientation("S", 180, 0) == "S"
        assert effective_orientation("W", 270, 0) == "W"

    def test_45_offset_rotates_n_to_ne(self):
        """+45° поворот: N (0°) → NE (45°)."""
        assert effective_orientation("N", 0, 45) == "NE"
        assert effective_orientation("E", 90, 45) == "SE"
        assert effective_orientation("S", 180, 45) == "SW"
        assert effective_orientation("W", 270, 45) == "NW"

    def test_90_offset_rotates_n_to_e(self):
        """+90° поворот: каждая сторона смещается на одну позицию по часовой."""
        assert effective_orientation("N", 0, 90) == "E"
        assert effective_orientation("E", 90, 90) == "S"
        assert effective_orientation("S", 180, 90) == "W"
        assert effective_orientation("W", 270, 90) == "N"

    def test_negative_offset(self):
        """-45° поворот (по часовой): N → NW."""
        assert effective_orientation("N", 0, -45) == "NW"
        assert effective_orientation("E", 90, -45) == "NE"

    def test_offset_360_wrap(self):
        """Поворот +360° = поворот 0°."""
        assert effective_orientation("N", 0, 360) == "N"
        assert effective_orientation("S", 180, 720) == "S"

    def test_offset_without_deg_uses_sector_center(self):
        """Если orientation_deg=None, используется середина сектора."""
        # N центр = 0°, +45 → NE
        assert effective_orientation("N", None, 45) == "NE"
        # NE центр = 45°, +45 → E
        assert effective_orientation("NE", None, 45) == "E"

    def test_empty_orientation_returns_empty(self):
        """Пустая ориентация остаётся пустой."""
        assert effective_orientation("", None, 45) == ""
        assert effective_orientation("", 0, 0) == ""


class TestSolarWithRotation:
    """Проверка что поворот реально меняет солнечную нагрузку."""

    def _setup_project(self, orientation, orientation_deg, tn_offset=0):
        project = HVACProject()
        project.params.true_north_offset_deg = tn_offset
        project.params.t_out_cooling = 36
        project.params.t_out_heating = -16
        project.params.solar_intensity_w_m2 = 750
        project.params.solar_shading_factor = 1.0

        sp = Space(space_id="1", number="101", name="Test", level="L1",
                   area_m2=20, volume_m3=60, height_m=3, room_type="Офис")
        project.spaces.append(sp)
        project._space_by_id["1"] = sp

        # Окно 10 м² с SHGC=0.6
        el = BoundaryElement(
            space_id="1", row_type="opening", is_exterior=True,
            element_id="W1", category="Окна", family="GL", type_name="T1",
            boundary_length_m=0, space_height_m=3,
            approx_area_m2=10, element_area_m2=10, thickness_mm=20,
            function="Exterior", host_element_id="", boundary_space_count=1,
            orientation=orientation, orientation_deg=orientation_deg,
            u_value=1.5, net_area_m2=10,
        )
        el.construction_key = "Окна/GL/T1/20"
        project.elements.append(el)
        project.constructions["Окна/GL/T1/20"] = Construction(
            key="Окна/GL/T1/20", category="Окна", family="GL",
            type_name="T1", thickness_mm=20, u_value=1.5, shgc=0.6)
        return project, sp

    def test_n_window_no_offset(self):
        """Окно N без поворота: пик f=0.20 → ~675 Вт солнца (с CLF)."""
        project, sp = self._setup_project("N", 0)
        engine = SP50Engine()
        br = engine.heat_gain(sp, project)
        # Q_солнце = 0.6 × 10 × 750 × 0.20(N) × 1.0 × 0.75(CLF) = 675 Вт
        assert br["Солнечная радиация"] == pytest.approx(675, rel=0.01)

    def test_n_window_with_45_offset_becomes_ne(self):
        """Окно N с поворотом +45° → реально NE: пик f=0.55 → ~1856 Вт (с CLF)."""
        project, sp = self._setup_project("N", 0, tn_offset=45)
        engine = SP50Engine()
        br = engine.heat_gain(sp, project)
        # Q_солнце = 0.6 × 10 × 750 × 0.55(NE) × 1.0 × 0.75(CLF) = 1856.25 Вт
        assert br["Солнечная радиация"] == pytest.approx(1856.25, rel=0.01)

    def test_w_window_with_45_offset_becomes_nw(self):
        """Окно W (270°) с поворотом +45° → 315° = NW: пик f=0.55 → ~1856 Вт.
        Контрольная точка: запад без поворота даёт максимум солнца (~3206)."""
        project, sp = self._setup_project("W", 270, tn_offset=45)
        engine = SP50Engine()
        br = engine.heat_gain(sp, project)
        # Q_солнце = 0.6 × 10 × 750 × 0.55(NW) × 1.0 × 0.75(CLF) = 1856.25 Вт
        assert br["Солнечная радиация"] == pytest.approx(1856.25, rel=0.01)

    def test_no_offset_w_max_solar(self):
        """Контроль: окно W без поворота — максимальное солнце пик f=0.95."""
        project, sp = self._setup_project("W", 270, tn_offset=0)
        engine = SP50Engine()
        br = engine.heat_gain(sp, project)
        # Q_солнце = 0.6 × 10 × 750 × 0.95(W) × 1.0 × 0.75(CLF) = 3206.25 Вт
        assert br["Солнечная радиация"] == pytest.approx(3206.25, rel=0.01)


class TestPersistence:

    def test_true_north_saves_to_json(self):
        """true_north_offset_deg сохраняется в JSON и загружается."""
        from hvac.io_json import save_project, load_project
        import tempfile, os

        project = HVACProject()
        project.new_empty_project("test", "Ташкент")
        project.params.true_north_offset_deg = 37.5

        with tempfile.NamedTemporaryFile(mode="w", suffix=".json",
                                          delete=False) as f:
            path = f.name
        try:
            save_project(project, path)
            p2 = HVACProject()
            load_project(p2, path)
            assert p2.params.true_north_offset_deg == 37.5
        finally:
            os.unlink(path)
