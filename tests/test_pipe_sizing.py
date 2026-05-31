# -*- coding: utf-8 -*-
"""Тесты модуля pipe_sizing — гидравлика труб отопления."""

import unittest

from hvac.pipe_sizing import (
    mass_flow_kg_h, volume_flow_m3_h, velocity_in_pipe_m_s,
    pick_dn, friction_factor_altshul, reynolds,
    pressure_loss_friction_water_pa, pressure_loss_local_water_pa,
    STEEL_INNER_DIAMETER, PEX_AL_PEX,
    WATER_DENSITY_70C, WATER_SPECIFIC_HEAT_WH_KG_K,
    ROUGHNESS_STEEL_MM,
)


class TestMassFlow(unittest.TestCase):

    def test_zero_load(self):
        self.assertEqual(mass_flow_kg_h(0, 20), 0.0)

    def test_zero_dt(self):
        self.assertEqual(mass_flow_kg_h(1000, 0), 0.0)

    def test_radiator_1500w_dt20(self):
        """Q=1500, Δt=20 → G = 1500/(1.163×20) = 64.5 кг/ч."""
        g = mass_flow_kg_h(1500, 20)
        self.assertAlmostEqual(g, 64.49, places=1)

    def test_boiler_100kw_dt20(self):
        """Q=100 кВт, Δt=20 → G ≈ 4299 кг/ч."""
        g = mass_flow_kg_h(100_000, 20)
        self.assertAlmostEqual(g, 4299, delta=2)

    def test_proportional_to_load(self):
        """G ∝ Q."""
        g1 = mass_flow_kg_h(10000, 20)
        g2 = mass_flow_kg_h(20000, 20)
        self.assertAlmostEqual(g2 / g1, 2.0)

    def test_inversely_proportional_to_dt(self):
        """G ∝ 1/Δt."""
        g1 = mass_flow_kg_h(10000, 10)
        g2 = mass_flow_kg_h(10000, 20)
        self.assertAlmostEqual(g1 / g2, 2.0)


class TestVolumeFlow(unittest.TestCase):

    def test_relationship_to_mass(self):
        """V = G / ρ."""
        v = volume_flow_m3_h(10000, 20)
        g = mass_flow_kg_h(10000, 20)
        self.assertAlmostEqual(v, g / WATER_DENSITY_70C, places=3)


class TestVelocityInPipe(unittest.TestCase):

    def test_zero(self):
        self.assertEqual(velocity_in_pipe_m_s(0, 50), 0)
        self.assertEqual(velocity_in_pipe_m_s(5, 0), 0)

    def test_known(self):
        """V=1 м³/ч в d=20 мм:
        A = π × 0.02² / 4 = 3.14e-4 м²
        v = (1/3600) / 3.14e-4 = 0.884 м/с"""
        v = velocity_in_pipe_m_s(1.0, 20)
        self.assertAlmostEqual(v, 0.884, places=2)


class TestPickDN(unittest.TestCase):

    def test_zero_flow_returns_zero(self):
        dn, d, v = pick_dn(0)
        self.assertEqual(dn, 0)

    def test_radiator_load(self):
        """1500 Вт радиатор → DN10 для стали (малый расход)."""
        v_m3h = volume_flow_m3_h(1500, 20)
        dn, d, v = pick_dn(v_m3h, "steel")
        self.assertLessEqual(dn, 15)

    def test_large_load(self):
        """100 кВт → DN50."""
        v_m3h = volume_flow_m3_h(100_000, 20)
        dn, d, v = pick_dn(v_m3h, "steel")
        self.assertIn(dn, [40, 50, 65])  # в зоне 40-65

    def test_velocity_within_recommended(self):
        """Скорость в подобранной трубе должна быть в рекомендованном диапазоне."""
        for q_w in [1000, 5000, 10000, 50000, 100000]:
            v_m3h = volume_flow_m3_h(q_w, 20)
            dn, d, v = pick_dn(v_m3h, "steel")
            # Не должна превышать 2 м/с (макс. рекомендованная)
            self.assertLess(v, 2.1, f"Q={q_w}: DN{dn}, v={v}")

    def test_pex_diameters(self):
        """PEX-Al-PEX даёт другие размеры."""
        v_m3h = volume_flow_m3_h(1500, 20)
        dn, d, v = pick_dn(v_m3h, "pex")
        self.assertIn(dn, PEX_AL_PEX.keys())


class TestReynolds(unittest.TestCase):

    def test_zero(self):
        self.assertEqual(reynolds(0, 50), 0)
        self.assertEqual(reynolds(1, 0), 0)

    def test_typical_heating(self):
        """v=1 м/с, d=50 мм: Re = 1×0.05/0.413e-6 ≈ 121 000 (турбулентный)."""
        re = reynolds(1.0, 50.0)
        self.assertGreater(re, 100_000)


class TestFrictionAltshul(unittest.TestCase):

    def test_returns_reasonable(self):
        """Для типового случая λ ∈ (0.02; 0.05)."""
        lam = friction_factor_altshul(1.0, 50.0, ROUGHNESS_STEEL_MM)
        self.assertGreater(lam, 0.015)
        self.assertLess(lam, 0.060)

    def test_smoother_pipe_lower_lambda(self):
        """Гладкая труба (меньше шерох.) → меньше λ."""
        lam_steel = friction_factor_altshul(1, 50, 0.2)
        lam_pex = friction_factor_altshul(1, 50, 0.01)
        self.assertGreater(lam_steel, lam_pex)


class TestPressureLoss(unittest.TestCase):

    def test_quadratic_in_velocity(self):
        """Δp ∝ v²."""
        dp1 = pressure_loss_friction_water_pa(10, 50, 0.5)
        dp2 = pressure_loss_friction_water_pa(10, 50, 1.0)
        # При тех же L, d, и приблиз. таком же λ ratio ≈ 4
        self.assertGreater(dp2 / dp1, 3.5)
        self.assertLess(dp2 / dp1, 4.5)

    def test_proportional_to_length(self):
        """Δp ∝ L."""
        dp1 = pressure_loss_friction_water_pa(10, 50, 1.0)
        dp2 = pressure_loss_friction_water_pa(20, 50, 1.0)
        self.assertAlmostEqual(dp2 / dp1, 2.0, places=2)

    def test_zero_velocity(self):
        self.assertEqual(pressure_loss_friction_water_pa(10, 50, 0), 0)

    def test_local_pressure_loss(self):
        """Δp_местн = ζ × ρv²/2 = 7 × 977.7 × 1²/2 ≈ 3422 Па."""
        dp = pressure_loss_local_water_pa(sum_zeta=7.0, velocity_m_s=1.0)
        self.assertAlmostEqual(dp, 3422, delta=5)


class TestStandardCatalogs(unittest.TestCase):

    def test_steel_dns_monotone(self):
        """Внутренний диаметр растёт с DN."""
        dns = sorted(STEEL_INNER_DIAMETER.keys())
        for i in range(len(dns) - 1):
            self.assertLess(STEEL_INNER_DIAMETER[dns[i]],
                            STEEL_INNER_DIAMETER[dns[i + 1]])

    def test_pex_diameters(self):
        """PEX-Al-PEX 16, 20, 26… имеют внутренние диаметры меньше наружных."""
        for dn, inner in PEX_AL_PEX.items():
            self.assertLess(inner, dn)


if __name__ == "__main__":
    unittest.main(verbosity=2)
