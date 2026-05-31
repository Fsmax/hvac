# -*- coding: utf-8 -*-
"""Тесты модуля energy — энергопаспорт по СП 50."""

import unittest

from hvac.energy import (
    estimate_heating_season_from_gsop, annual_heating_energy_kwh,
    annual_cooling_energy_kwh, hours_per_year_cooling,
    normative_qh, energy_class_for_deviation,
    ENERGY_CLASS_THRESHOLDS, BASE_HEATING_NORMS_KWH_M2,
)


class TestHeatingSeasonEstimate(unittest.TestCase):
    """Калибровка длительности сезона по справочным данным СП 131."""

    def test_zero_gsop(self):
        """ГСОП=0 (тропики) → сезона нет."""
        r = estimate_heating_season_from_gsop(0)
        self.assertEqual(r["z_days"], 0)

    def test_tashkent_close_to_reference(self):
        """Ташкент: ГСОП=2100, ожидаемые ~132 дня (±10%)."""
        r = estimate_heating_season_from_gsop(2100)
        self.assertAlmostEqual(r["z_days"], 132, delta=15)
        # Средняя t_от ~3.8°C
        self.assertAlmostEqual(r["t_avg"], 3.8, delta=2)

    def test_moscow_close_to_reference(self):
        """Москва: ГСОП=4943, ожидаемые ~214 дней."""
        r = estimate_heating_season_from_gsop(4943)
        self.assertAlmostEqual(r["z_days"], 214, delta=15)
        self.assertAlmostEqual(r["t_avg"], -2.2, delta=3)

    def test_yakutsk_extreme(self):
        """Якутск: ГСОП=9931, ~254 дня."""
        r = estimate_heating_season_from_gsop(9931)
        self.assertAlmostEqual(r["z_days"], 254, delta=20)

    def test_z_days_monotone(self):
        """Чем больше ГСОП — тем длиннее сезон."""
        z1 = estimate_heating_season_from_gsop(2000)["z_days"]
        z2 = estimate_heating_season_from_gsop(5000)["z_days"]
        z3 = estimate_heating_season_from_gsop(8000)["z_days"]
        self.assertLess(z1, z2)
        self.assertLess(z2, z3)

    def test_z_days_bounded(self):
        """Сезон не должен превышать 300 дней даже для очень холодных мест."""
        r = estimate_heating_season_from_gsop(20000)
        self.assertLessEqual(r["z_days"], 300)

    def test_gsop_consistency(self):
        """z × (t_in - t_avg) ≈ ГСОП."""
        gsop = 4943
        r = estimate_heating_season_from_gsop(gsop, t_in=20.0)
        reconstructed = r["z_days"] * (20.0 - r["t_avg"])
        self.assertAlmostEqual(reconstructed, gsop, delta=10)


class TestAnnualEnergy(unittest.TestCase):

    def test_zero_for_zero_load(self):
        e = annual_heating_energy_kwh(0, 20, -25, 200, -3)
        self.assertEqual(e, 0.0)

    def test_proportional_to_q_peak(self):
        """E пропорционально Q_peak при прочих равных."""
        e1 = annual_heating_energy_kwh(100000, 20, -25, 200, -3)
        e2 = annual_heating_energy_kwh(200000, 20, -25, 200, -3)
        self.assertAlmostEqual(e2 / e1, 2.0, places=2)

    def test_lower_t_avg_more_energy(self):
        """Чем холоднее средняя — тем больше годового потребления."""
        e_cold = annual_heating_energy_kwh(100000, 20, -25, 200, -5)
        e_warm = annual_heating_energy_kwh(100000, 20, -25, 200, 0)
        self.assertGreater(e_cold, e_warm)

    def test_regulation_reduces_energy(self):
        """k_reg=0.85 → энергопотребление меньше."""
        e_no = annual_heating_energy_kwh(100000, 20, -25, 200, -3, k_reg=1.0)
        e_yes = annual_heating_energy_kwh(100000, 20, -25, 200, -3, k_reg=0.85)
        self.assertLess(e_yes, e_no)
        self.assertAlmostEqual(e_yes / e_no, 0.85, places=2)


class TestCoolingHours(unittest.TestCase):

    def test_hot_climate_long_season(self):
        self.assertGreater(hours_per_year_cooling(36),
                           hours_per_year_cooling(28))

    def test_cold_climate_short(self):
        self.assertLess(hours_per_year_cooling(22), 500)


class TestNormativeQh(unittest.TestCase):

    def test_at_4000_gsop_returns_base(self):
        """При ГСОП=4000 норма равна базовой."""
        self.assertEqual(normative_qh("офис", 4000),
                         BASE_HEATING_NORMS_KWH_M2["офис"])

    def test_higher_gsop_higher_norm(self):
        """Чем холоднее город (выше ГСОП) — тем выше норма."""
        n_warm = normative_qh("офис", 2000)
        n_cold = normative_qh("офис", 6000)
        self.assertLess(n_warm, n_cold)

    def test_residential_lower_floors_higher_norm(self):
        """Малоэтажное жильё имеет более высокую норму, чем многоэтажное."""
        n_low = normative_qh("жилое 1-3 этажа", 4000)
        n_high = normative_qh("жилое 12+", 4000)
        self.assertGreater(n_low, n_high)


class TestEnergyClass(unittest.TestCase):

    def test_at_norm(self):
        """Близко к нулю отклонения → класс C+."""
        r = energy_class_for_deviation(0)
        self.assertEqual(r["class"], "C+")

    def test_very_good(self):
        """-55% — класс A+."""
        r = energy_class_for_deviation(-55)
        self.assertEqual(r["class"], "A+")

    def test_bad(self):
        """+60% — класс E."""
        r = energy_class_for_deviation(60)
        self.assertEqual(r["class"], "E")

    def test_all_thresholds_have_class(self):
        """Все диапазоны thresholds должны иметь класс."""
        for lo, hi, cls, desc in ENERGY_CLASS_THRESHOLDS:
            self.assertIsInstance(cls, str)
            self.assertTrue(len(cls) > 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
