# -*- coding: utf-8 -*-
"""Тесты модуля dew_point — проверка точки росы и формул конденсации."""

import math
import unittest

from hvac.dew_point import (
    dew_point_c, saturation_pressure_pa, surface_temperature,
    r_si_for_category, dt_normative_for_category,
    R_SI_WALL, R_SI_CEILING, R_SI_FLOOR, DT_NORM,
    DT_NORM_BY_NORM, resolve_dt_norm, is_public_room,
    ROOM_TYPE_RH_DESIGN,
)


class TestDewPoint(unittest.TestCase):
    """Формула Магнуса для точки росы."""

    def test_dew_point_at_100_percent(self):
        """При 100% RH t_d = t_air."""
        for t in [-10, 0, 10, 20, 30]:
            self.assertAlmostEqual(dew_point_c(t, 100), t, places=1)

    def test_dew_point_at_50_percent_20c(self):
        """Стандартное значение: 20°C/50% → ~9.3°C."""
        td = dew_point_c(20.0, 50.0)
        self.assertAlmostEqual(td, 9.26, places=1)

    def test_dew_point_lower_rh_lower_dew(self):
        """При уменьшении RH точка росы должна снижаться."""
        rhs = [80, 60, 40, 20]
        dews = [dew_point_c(20, rh) for rh in rhs]
        for i in range(len(dews) - 1):
            self.assertGreater(dews[i], dews[i + 1])

    def test_dew_point_at_0_rh_negative(self):
        """При 0% RH (сухой воздух) — вырожденный случай."""
        td = dew_point_c(20, 0)
        self.assertLess(td, -100)  # очень низкое

    def test_dew_point_high_temp(self):
        """Точка росы при 30°C/60% ≈ 21.4°C."""
        td = dew_point_c(30, 60)
        self.assertAlmostEqual(td, 21.4, places=0)


class TestSaturationPressure(unittest.TestCase):

    def test_at_zero(self):
        """При 0°C p_нас ≈ 611 Па."""
        p = saturation_pressure_pa(0)
        self.assertAlmostEqual(p, 611, delta=5)

    def test_at_20c(self):
        """При 20°C p_нас ≈ 2340 Па."""
        p = saturation_pressure_pa(20)
        self.assertAlmostEqual(p, 2340, delta=30)

    def test_at_100c(self):
        """При 100°C ≈ 101 325 Па."""
        p = saturation_pressure_pa(100)
        self.assertAlmostEqual(p, 101325, delta=15000)  # формула Магнуса неточна выше 50°C


class TestSurfaceTemperature(unittest.TestCase):
    """τ_int = t_in - (t_in - t_out) × R_si × U"""

    def test_good_wall(self):
        """U=0.4, R_si=0.115, t_in=20, t_out=-15:
        τ = 20 - 35 × 0.115 × 0.4 = 20 - 1.61 = 18.39"""
        tau = surface_temperature(0.4, 20, -15, R_SI_WALL)
        self.assertAlmostEqual(tau, 18.39, places=1)

    def test_bad_wall(self):
        """Плохая стена U=2.5 даёт τ близкое к dew point."""
        tau = surface_temperature(2.5, 20, -15, R_SI_WALL)
        self.assertLess(tau, 12.0)
        self.assertGreater(tau, 5.0)

    def test_zero_u_returns_t_in(self):
        """U=0 (нет теплопередачи) → τ = t_in."""
        self.assertEqual(surface_temperature(0, 20, -15), 20)

    def test_at_same_temp(self):
        """t_in = t_out → τ = t_in."""
        self.assertAlmostEqual(surface_temperature(1.0, 20, 20), 20)


class TestRSiCategoryDispatch(unittest.TestCase):

    def test_wall_dispatch(self):
        self.assertEqual(r_si_for_category("Наружная стена"), R_SI_WALL)
        self.assertEqual(r_si_for_category("Внутренняя стена"), R_SI_WALL)

    def test_ceiling_dispatch(self):
        self.assertEqual(r_si_for_category("Потолок"), R_SI_CEILING)
        self.assertEqual(r_si_for_category("Покрытие"), R_SI_CEILING)
        self.assertEqual(r_si_for_category("Перекрытие"), R_SI_CEILING)

    def test_floor_dispatch(self):
        self.assertEqual(r_si_for_category("Пол"), R_SI_FLOOR)


class TestDtNormative(unittest.TestCase):

    def test_walls(self):
        self.assertEqual(dt_normative_for_category("Стена"), DT_NORM["wall"])

    def test_ceilings(self):
        self.assertEqual(dt_normative_for_category("Потолок"),
                         DT_NORM["ceiling"])

    def test_floors(self):
        self.assertEqual(dt_normative_for_category("Пол"), DT_NORM["floor"])


class TestCeilingRSi(unittest.TestCase):
    """α_в потолка — по КМК Табл.5/СП Табл.4 гладкий потолок = 8.7 (не 8.0)."""

    def test_ceiling_rsi_is_one_over_8_7(self):
        self.assertAlmostEqual(R_SI_CEILING, 1.0 / 8.7, places=4)
        # гладкий потолок = стена/пол по α_в
        self.assertEqual(R_SI_CEILING, R_SI_WALL)


class TestDtNormByNorm(unittest.TestCase):
    """Переключение Δt_н по активной норме (КМК / СП) и категории здания."""

    def test_kmk_residential_ceiling_is_35(self):
        s = resolve_dt_norm("KMK_UZ", is_public=False)
        self.assertEqual(s["wall"], 4.0)
        self.assertEqual(s["ceiling"], 3.5)   # КМК Табл.4 (не 3.0)
        self.assertEqual(s["floor"], 2.0)

    def test_sp_residential_ceiling_is_30(self):
        s = resolve_dt_norm("SP_RU", is_public=False)
        self.assertEqual(s["ceiling"], 3.0)   # СП 50 Табл.5

    def test_kmk_public_relaxed(self):
        s = resolve_dt_norm("KMK_UZ", is_public=True)
        self.assertEqual(s["wall"], 5.0)
        self.assertEqual(s["ceiling"], 4.5)
        self.assertEqual(s["floor"], 2.5)

    def test_unknown_norm_falls_back_to_kmk(self):
        self.assertEqual(resolve_dt_norm("???", False),
                         resolve_dt_norm("KMK_UZ", False))

    def test_default_dt_norm_is_kmk_residential(self):
        self.assertEqual(DT_NORM, DT_NORM_BY_NORM["KMK_UZ"]["residential"])

    def test_is_public_room(self):
        self.assertFalse(is_public_room("Жилая комната"))
        self.assertFalse(is_public_room("Гостиничный номер"))
        self.assertTrue(is_public_room("Офис"))
        self.assertTrue(is_public_room("Магазин / торговля"))

    def test_dt_normative_respects_passed_set(self):
        sp = resolve_dt_norm("SP_RU", is_public=False)
        kmk = resolve_dt_norm("KMK_UZ", is_public=False)
        self.assertEqual(dt_normative_for_category("Покрытие", sp), 3.0)
        self.assertEqual(dt_normative_for_category("Покрытие", kmk), 3.5)


class TestRoomTypeRH(unittest.TestCase):

    def test_known_types(self):
        """Известные типы должны быть в таблице с разумными RH."""
        self.assertIn("Офис", ROOM_TYPE_RH_DESIGN)
        self.assertIn("Санузел", ROOM_TYPE_RH_DESIGN)
        self.assertGreater(ROOM_TYPE_RH_DESIGN["Санузел"],
                           ROOM_TYPE_RH_DESIGN["Офис"])  # ванная больше офиса

    def test_all_rh_in_range(self):
        """Все RH должны быть в диапазоне 35..75%."""
        for room, rh in ROOM_TYPE_RH_DESIGN.items():
            self.assertGreaterEqual(rh, 35, f"{room}: RH={rh}")
            self.assertLessEqual(rh, 75, f"{room}: RH={rh}")


if __name__ == "__main__":
    unittest.main(verbosity=2)
