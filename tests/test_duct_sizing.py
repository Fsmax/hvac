# -*- coding: utf-8 -*-
"""Тесты модуля duct_sizing — подбор воздуховодов."""

import math
import unittest

from hvac.duct_sizing import (
    diameter_for_flow_and_velocity, pick_round_diameter, pick_rect_section,
    hydraulic_diameter_mm, pressure_loss_friction_pa, pressure_loss_local_pa,
    round_up_to_std_round, round_up_to_std_rect,
    STD_ROUND_DIAMETERS_MM, RECOMMENDED_VELOCITIES, AIR_DENSITY_KG_M3,
    FRICTION_FACTOR_GALV,
)


class TestRounding(unittest.TestCase):

    def test_round_up_round(self):
        """100 → 100, 130 → 160, 1500 → 1600."""
        self.assertEqual(round_up_to_std_round(100), 100)
        self.assertEqual(round_up_to_std_round(130), 160)
        self.assertEqual(round_up_to_std_round(1500), 1600)

    def test_round_up_too_big(self):
        """Сверх диапазона → берётся последний (2000)."""
        self.assertEqual(round_up_to_std_round(3000), 2000)


class TestDiameterFromFlow(unittest.TestCase):

    def test_zero_flow(self):
        self.assertEqual(diameter_for_flow_and_velocity(0, 5), 0)

    def test_known_value(self):
        """1000 м³/ч / 5 м/с:
        Q = 1000/3600 = 0.278 м³/с
        A = 0.278/5 = 0.0556 м²
        d = √(4×0.0556/π) = 0.266 м = 266 мм"""
        d = diameter_for_flow_and_velocity(1000, 5)
        self.assertAlmostEqual(d, 266, delta=2)

    def test_scaling(self):
        """При удвоении расхода диаметр × √2."""
        d1 = diameter_for_flow_and_velocity(1000, 5)
        d2 = diameter_for_flow_and_velocity(2000, 5)
        self.assertAlmostEqual(d2 / d1, math.sqrt(2), places=2)


class TestPickRoundDiameter(unittest.TestCase):

    def test_small_flow(self):
        """100 м³/ч / 5 → расчётный ~84 → станд. 100 мм."""
        d, v = pick_round_diameter(100, 5)
        self.assertEqual(d, 100)
        # Фактическая скорость на этом сечении меньше 5
        self.assertLess(v, 5)

    def test_large_flow(self):
        """10000 м³/ч / 8 → должен дать средне-крупный воздуховод."""
        d, v = pick_round_diameter(10000, 8)
        # 10000/3600 = 2.78 м³/с, A = 2.78/8 = 0.347 м², d = 665 мм → станд. 800
        self.assertEqual(d, 800)
        # Фактическая v на 800 мм ≈ 5.53 м/с
        self.assertLess(v, 8)
        self.assertGreater(v, 5)

    def test_velocity_always_below_max(self):
        """Фактическая скорость на станд. размере всегда ≤ v_max."""
        for q in [500, 1000, 2000, 5000, 10000]:
            d, v = pick_round_diameter(q, 6)
            self.assertLessEqual(v, 6.001, f"Q={q}: d={d}, v={v}")

    def test_zero_flow_returns_zero(self):
        d, v = pick_round_diameter(0, 5)
        self.assertEqual(d, 0)


class TestPickRectSection(unittest.TestCase):

    def test_basic(self):
        """5000 м³/ч × 6 м/с → A = 0.231 м² = 231 000 мм²."""
        w, h, v = pick_rect_section(5000, 6)
        self.assertLessEqual(v, 6.01)
        # Площадь должна быть ≥ требуемой
        self.assertGreaterEqual(w * h / 1e6, 5000 / 3600 / 6 * 0.99)

    def test_aspect_ratio_respected(self):
        """Aspect ratio не должен превышать 3."""
        w, h, v = pick_rect_section(10000, 8, max_aspect_ratio=3.0)
        self.assertLessEqual(max(w, h) / min(w, h), 3.0)

    def test_preferred_height(self):
        """С заданной высотой — она используется."""
        w, h, v = pick_rect_section(5000, 6, preferred_height_mm=300)
        self.assertEqual(h, 300)


class TestHydraulicDiameter(unittest.TestCase):

    def test_square(self):
        """Квадрат: d_h = сторона."""
        self.assertAlmostEqual(hydraulic_diameter_mm(500, 500), 500)

    def test_strong_rect(self):
        """Прямоугольник 1000×500: d_h = 2×1000×500/(1500) = 667 мм."""
        d_h = hydraulic_diameter_mm(1000, 500)
        self.assertAlmostEqual(d_h, 666.7, places=0)


class TestPressureLoss(unittest.TestCase):

    def test_zero_velocity(self):
        self.assertEqual(pressure_loss_friction_pa(10, 200, 0), 0)

    def test_known_case(self):
        """L=20 м, d=400 мм, v=7 м/с, λ=0.022, ρ=1.2:
        Δp = 0.022 × (20/0.4) × (1.2 × 49 / 2) = 0.022 × 50 × 29.4 = 32.34 Па"""
        dp = pressure_loss_friction_pa(20, 400, 7,
                                       friction=FRICTION_FACTOR_GALV)
        self.assertAlmostEqual(dp, 32.34, places=1)

    def test_quadratic_in_velocity(self):
        """Δp ∝ v²."""
        dp1 = pressure_loss_friction_pa(10, 300, 5)
        dp2 = pressure_loss_friction_pa(10, 300, 10)
        self.assertAlmostEqual(dp2 / dp1, 4.0, places=1)

    def test_local_loss(self):
        """Δp_местн = ζ × ρv²/2."""
        dp = pressure_loss_local_pa(sum_zeta=2.5, v_m_s=5)
        # 2.5 × 1.2 × 25 / 2 = 37.5 Па
        self.assertAlmostEqual(dp, 37.5, places=1)


class TestVelocityCatalog(unittest.TestCase):

    def test_categories_present(self):
        self.assertIn("public", RECOMMENDED_VELOCITIES)
        self.assertIn("residential", RECOMMENDED_VELOCITIES)
        self.assertIn("industrial", RECOMMENDED_VELOCITIES)

    def test_hierarchy(self):
        """Магистраль > ветка > терминал по скорости."""
        for cat, vels in RECOMMENDED_VELOCITIES.items():
            self.assertGreater(vels["trunk"], vels["branch"])
            self.assertGreater(vels["branch"], vels["terminal"])

    def test_residential_slower_than_public(self):
        self.assertLess(RECOMMENDED_VELOCITIES["residential"]["trunk"],
                        RECOMMENDED_VELOCITIES["public"]["trunk"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
