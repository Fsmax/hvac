# -*- coding: utf-8 -*-
"""Тесты солнечной геометрии (hvac/solar.py) и интеграции с симуляцией."""

import math

import pytest

from hvac.solar import (
    ORIENT_AZIMUTH_DEG, facade_irradiance_year, solar_position,
    split_ghi_erbs, vertical_irradiance)
from hvac.weather import HOURS_IN_YEAR, WeatherData

# Ташкент
LAT, LON, TZ = 41.3, 69.3, 5.0


class TestSolarPosition:
    def test_june_noon_high_sun(self):
        """21 июня в полдень на 41° с.ш. солнце ≈ 72° над горизонтом."""
        h = 171 * 24 + 12
        alt, az = solar_position(LAT, LON, TZ, h)
        assert alt > 65.0
        assert 150.0 < az < 210.0          # около юга

    def test_december_noon_lower_than_june(self):
        alt_jun, _ = solar_position(LAT, LON, TZ, 171 * 24 + 12)
        alt_dec, _ = solar_position(LAT, LON, TZ, 354 * 24 + 12)
        assert alt_dec < alt_jun
        # зимний полдень: ≈ 90 − 41.3 − 23.45 ≈ 25°
        assert 15.0 < alt_dec < 35.0

    def test_midnight_below_horizon(self):
        alt, _ = solar_position(LAT, LON, TZ, 171 * 24 + 0)
        assert alt < 0.0

    def test_morning_sun_in_east(self):
        alt, az = solar_position(LAT, LON, TZ, 171 * 24 + 7)
        assert alt > 0.0
        assert 45.0 < az < 135.0           # восточная половина неба


class TestErbsSplit:
    def test_zero_ghi(self):
        assert split_ghi_erbs(0.0, 45.0, 172) == (0.0, 0.0)

    def test_low_sun_all_diffuse(self):
        dni, dhi = split_ghi_erbs(50.0, 1.0, 172)
        assert dni == 0.0
        assert dhi == pytest.approx(50.0)

    def test_components_reconstruct_ghi(self):
        """DNI·sin(alt) + DHI = GHI (баланс на горизонтали)."""
        ghi, alt = 600.0, 50.0
        dni, dhi = split_ghi_erbs(ghi, alt, 172)
        assert dni > 0
        assert dhi > 0
        assert dni * math.sin(math.radians(alt)) + dhi == pytest.approx(ghi)

    def test_clear_sky_mostly_beam(self):
        """Высокий kT → доля рассеянной мала."""
        dni, dhi = split_ghi_erbs(900.0, 60.0, 172)
        assert dhi / 900.0 < 0.35


class TestVerticalIrradiance:
    def test_south_beats_north_at_winter_noon(self):
        # Солнце на юге, 20° над горизонтом
        irr_s = vertical_irradiance(400.0, 20.0, 180.0, 180.0, 354)
        irr_n = vertical_irradiance(400.0, 20.0, 180.0, 0.0, 354)
        assert irr_s > irr_n
        # Север — только рассеянная и отражённая
        _dni, dhi = split_ghi_erbs(400.0, 20.0, 354)
        assert irr_n == pytest.approx(0.5 * dhi + 0.5 * 0.2 * 400.0)

    def test_zero_ghi_zero_irradiance(self):
        assert vertical_irradiance(0.0, 45.0, 180.0, 180.0, 172) == 0.0


def _wd_solar(ghi_noon=600.0):
    """Год: t синусоида, GHI — дневной колокол c пиком ghi_noon."""
    t, ghi = [], []
    for h in range(HOURS_IN_YEAR):
        hod = h % 24
        t.append(10.0 - 20.0 * math.cos(2 * math.pi * (h / 24 - 196) / 365))
        ghi.append(max(0.0, ghi_noon * math.sin(math.pi * (hod - 6) / 12))
                   if 6 <= hod <= 18 else 0.0)
    return WeatherData(location="Testgrad", latitude=LAT, longitude=LON,
                       tz_offset_h=TZ, t_dry_bulb_c=t,
                       rh_pct=[50.0] * HOURS_IN_YEAR, ghi_w_m2=ghi)


class TestFacadeIrradianceYear:
    def test_south_facade_gets_most_annual_sun(self):
        irr = facade_irradiance_year(_wd_solar())
        sums = {k: sum(v) for k, v in irr.items()}
        assert sums["S"] > sums["N"]
        assert sums["S"] >= max(sums.values()) * 0.85   # юг среди лидеров

    def test_night_hours_zero(self):
        irr = facade_irradiance_year(_wd_solar())
        for k in ORIENT_AZIMUTH_DEG:
            assert irr[k][0] == 0.0                     # 1 января 00:30

    def test_no_solar_data_all_zero(self):
        wd = _wd_solar()
        wd.ghi_w_m2 = [0.0] * HOURS_IN_YEAR
        irr = facade_irradiance_year(wd)
        assert all(sum(v) == 0.0 for v in irr.values())


class TestSimulationWithSolar:
    def _project(self, wwr=0.3):
        from hvac.models import BoundaryElement, Space
        from hvac.project import HVACProject
        p = HVACProject()
        p.params.apply_city("Ташкент")
        p.params.wwr_estimate = wwr
        sp = Space(space_id="1", number="1", name="Офис", level="L1",
                   area_m2=25, volume_m3=75, height_m=3,
                   heat_loss_w=1500, heat_gain_w=2000,
                   heat_gain_sensible_w=1500)
        sp.heat_gain_breakdown_sensible = {"Солнечная радиация": 300.0}
        p.spaces.append(sp)
        p._space_by_id[sp.space_id] = sp
        el = BoundaryElement(
            space_id="1", row_type="external_wall", is_exterior=True,
            element_id="w1", category="Стены", family="f", type_name="t",
            boundary_length_m=5, space_height_m=3, approx_area_m2=15,
            element_area_m2=15, thickness_mm=200, function="",
            host_element_id="", boundary_space_count=1,
            orientation="S", orientation_deg=180.0,
            u_value=0.5, net_area_m2=15.0)
        p.elements.append(el)
        p._invalidate_elements_index()
        return p

    def test_solar_accounted_with_epw_radiation(self):
        p = self._project()
        p.weather_data = _wd_solar()
        result = p.simulate_annual_energy()
        assert result.solar_from_epw is True
        assert result.e_solar_kwh > 0

    def test_winter_sun_reduces_heating(self):
        p = self._project()
        p.weather_data = _wd_solar()
        with_sun = p.simulate_annual_energy()
        p.weather_data.ghi_w_m2 = [0.0] * HOURS_IN_YEAR
        no_sun = p.simulate_annual_energy()
        assert no_sun.solar_from_epw is False
        assert with_sun.e_heat_kwh <= no_sun.e_heat_kwh

    def test_no_glazing_no_solar_energy(self):
        """Без окон (WWR=0, стекла нет) солнце не влияет на нагрузки."""
        p = self._project(wwr=0.0)
        p.weather_data = _wd_solar()
        result = p.simulate_annual_energy()
        assert result.solar_from_epw is True   # данные есть…
        assert result.e_solar_kwh == 0.0       # …но апертуры нет
