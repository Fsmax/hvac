# -*- coding: utf-8 -*-
"""Тесты модуля energy — энергопаспорт по СП 50."""

import unittest

from hvac.energy import (
    estimate_heating_season_from_gsop, annual_heating_energy_kwh,
    annual_cooling_energy_kwh, hours_per_year_cooling,
    normative_qh, energy_class_for_deviation,
    ENERGY_CLASS_THRESHOLDS, BASE_HEATING_NORMS_KWH_M2,
    degree_days_heating, heating_period_at, calculate_passport,
)
from hvac.project import HVACProject
from hvac.catalogs.shnq_energy import (
    normative_q_ov_shnq, building_type_to_shnq, dd_band_index,
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


class TestShnqEnergy(unittest.TestCase):
    """Норматив q_ov по ШНҚ 2.01.18-24 Табл.1-3 (Узбекистан)."""

    def test_residential_table_values(self):
        # Жилые 1 эт.: [94, 100, 102] для полос Dd ≤2000 / 2000-3000 / >3000
        self.assertEqual(normative_q_ov_shnq("residential", 1, 1500), 94)
        self.assertEqual(normative_q_ov_shnq("residential", 1, 2500), 100)
        self.assertEqual(normative_q_ov_shnq("residential", 1, 3500), 102)
        # Жилые 9 эт.: [48, 57, 59]
        self.assertEqual(normative_q_ov_shnq("residential", 9, 1500), 48)

    def test_floor_selection_nearest_below(self):
        # n_floors=7 → строка 5 (ближайшая зашитая ≤7)
        self.assertEqual(normative_q_ov_shnq("residential", 7, 1500),
                         normative_q_ov_shnq("residential", 5, 1500))
        # n_floors=20 → строка 9 (макс. зашитая)
        self.assertEqual(normative_q_ov_shnq("residential", 20, 1500),
                         normative_q_ov_shnq("residential", 9, 1500))

    def test_floor_below_min_uses_min(self):
        # school начинается с 2 эт.; n_floors=1 → берётся строка 2
        self.assertEqual(normative_q_ov_shnq("school", 1, 1500),
                         normative_q_ov_shnq("school", 2, 1500))

    def test_dd_band_boundaries(self):
        self.assertEqual(dd_band_index(2000), 0)   # ≤2000
        self.assertEqual(dd_band_index(2001), 1)
        self.assertEqual(dd_band_index(3000), 1)   # ≤3000
        self.assertEqual(dd_band_index(3001), 2)

    def test_building_type_mapping(self):
        self.assertEqual(building_type_to_shnq("гостиница"), "hotel")
        self.assertEqual(building_type_to_shnq("офис"), "office")
        self.assertEqual(building_type_to_shnq("жилое 4-5 этажей"), "residential")
        self.assertEqual(building_type_to_shnq("магазин"), "shop")
        # неизвестный → обобщённый общественный (office)
        self.assertEqual(building_type_to_shnq("неизвестно"), "office")

    def test_unknown_category_returns_none(self):
        self.assertIsNone(normative_q_ov_shnq("???", 1, 2000))

    def test_passport_has_panel_summary_fields(self):
        """Атрибуты, читаемые панелью «Энергия» (_energy_summary), существуют
        под правильными именами (защита от регрессии class_letter/q_h_*)."""
        from hvac.energy import EnergyPassport
        ep = EnergyPassport()
        for attr in ("energy_class", "qh_specific_kwh_m2", "deviation_percent",
                     "shnq_compliant", "q_design_specific_w_m2",
                     "q_ov_normative_w_m2"):
            self.assertTrue(hasattr(ep, attr), attr)


class TestDegreeDaysDd(unittest.TestCase):
    """Dd по КМК 2.01.04-18 форм.(1) с порогом сезона 10°C."""

    def test_formula(self):
        # Dd = (tв − tот.пер)·zот.пер
        self.assertAlmostEqual(degree_days_heating(20.0, 4.0, 150), 2400.0)
        self.assertAlmostEqual(degree_days_heating(18.0, 3.8, 132),
                               (18.0 - 3.8) * 132)

    def test_zero_duration(self):
        self.assertEqual(degree_days_heating(20.0, 4.0, 0), 0.0)

    def test_heating_period_interp_to_10(self):
        # ШНҚ даёт ≤8 и ≤12; при 10°C — ровно середина (среднее)
        clim = {"z_ht_8": 100, "t_ht_8": 2.0, "z_ht_12": 140, "t_ht_12": 4.0}
        r = heating_period_at(clim, 10.0)
        self.assertAlmostEqual(r["z_days"], 120.0)   # (100+140)/2
        self.assertAlmostEqual(r["t_avg"], 3.0)      # (2+4)/2
        # при пороге 8 → ровно табличные ≤8°C
        r8 = heating_period_at(clim, 8.0)
        self.assertAlmostEqual(r8["z_days"], 100.0)
        self.assertAlmostEqual(r8["t_avg"], 2.0)

    def test_heating_period_none_without_fields(self):
        self.assertIsNone(heating_period_at({"gsop_18": 2100}, 10.0))

    def test_passport_exact_for_uz_city(self):
        """Узб. город с данными ≤8/≤12 в climate.json → Dd точный."""
        p = HVACProject()
        p.params.city = "Ташкент"   # z_ht_8/12 есть в climate.json
        ep = calculate_passport(p)
        self.assertTrue(ep.dd_exact)
        # Dd = (20 − (2.7+4.0)/2)·(129+166)/2 = 16.65·147.5
        self.assertAlmostEqual(ep.dd_shnq, 16.65 * 147.5, places=1)

    def test_passport_approx_without_period_data(self):
        """Город без полей ≤8/≤12 → Dd приближённый (dd_exact=False)."""
        p = HVACProject()
        p.params.city = "Москва"    # в climate.json нет z_ht_8/12
        p.params.gsop_18 = 4943
        ep = calculate_passport(p)
        self.assertFalse(ep.dd_exact)
        self.assertGreater(ep.dd_shnq, 0)


class TestHeatingSeasonForAndRefresh(unittest.TestCase):
    """Сезон из климата города + актуализация паспорта перед печатью."""

    def test_season_exact_from_climate(self):
        from hvac.energy import heating_season_for
        p = HVACProject()
        p.params.apply_city("Ташкент")     # z_ht_8=129, t_ht_8=2.7
        s = heating_season_for(p.params)
        self.assertTrue(s["exact"])
        self.assertAlmostEqual(s["z_days"], 129.0)
        self.assertAlmostEqual(s["t_avg"], 2.7)

    def test_season_fallback_to_gsop(self):
        from hvac.energy import heating_season_for
        p = HVACProject()
        p.params.city = "Неизвестный город"
        p.params.gsop_18 = 3000
        s = heating_season_for(p.params)
        self.assertFalse(s["exact"])
        self.assertGreater(s["z_days"], 0)

    def _project_with_space(self, q_loss: float) -> HVACProject:
        from hvac.models import Space
        p = HVACProject()
        p.params.apply_city("Ташкент")
        sp = Space(space_id="s1", number="1", name="Офис", level="L1",
                   area_m2=50, volume_m3=150, height_m=3,
                   heat_loss_w=q_loss, heat_gain_w=q_loss * 1.5)
        p.spaces.append(sp)
        p._space_by_id[sp.space_id] = sp
        return p

    def test_refresh_passport_recalculates_stale(self):
        from hvac.energy import refresh_passport
        p = self._project_with_space(3000.0)
        p.calculate_energy_passport()
        self.assertAlmostEqual(
            p.energy_passport.q_peak_heating_w, 3000.0)
        p.spaces[0].heat_loss_w = 9000.0          # правка после расчёта
        fresh = refresh_passport(p)
        self.assertAlmostEqual(fresh.q_peak_heating_w, 9000.0)
        self.assertIs(fresh, p.energy_passport)

    def test_refresh_passport_none_without_passport(self):
        from hvac.energy import refresh_passport
        p = self._project_with_space(3000.0)
        self.assertIsNone(refresh_passport(p))


if __name__ == "__main__":
    unittest.main(verbosity=2)
