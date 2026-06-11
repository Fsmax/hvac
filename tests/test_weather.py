# -*- coding: utf-8 -*-
"""Тесты парсера EPW и интеграции с 8760-симуляцией."""

import math

import pytest

from hvac.weather import HOURS_IN_YEAR, load_epw


def _make_epw(path, hours=HOURS_IN_YEAR, t_func=None, rh=50.0, ghi=200.0,
              location="Testgrad", country="UZB"):
    """Пишет минимальный валидный EPW-файл."""
    if t_func is None:
        # Простая годовая синусоида: −10 зимой, +30 летом
        def t_func(h):
            return 10.0 - 20.0 * math.cos(2 * math.pi * (h / 24 - 196) / 365)
    lines = [
        f"LOCATION,{location},-,{country},TMY,38457,41.3,69.3,5.0,430.0",
        "DESIGN CONDITIONS,0",
        "TYPICAL/EXTREME PERIODS,0",
        "GROUND TEMPERATURES,0",
        "HOLIDAYS/DAYLIGHT SAVINGS,No,0,0,0",
        "COMMENTS 1,test",
        "COMMENTS 2,test",
        "DATA PERIODS,1,1,Data,Sunday,1/1,12/31",
    ]
    for h in range(hours):
        day = h // 24
        month = min(12, day // 30 + 1)
        dom = day % 30 + 1
        t = t_func(h)
        # поля: год,мес,день,час,мин,флаги,t_db,t_dp,RH,давл,4×радиация…
        row = (f"2020,{month},{dom},{h % 24 + 1},0,?,"
               f"{t:.1f},{t - 5:.1f},{rh},101325,0,0,300,{ghi},100,50,"
               "0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0")
        lines.append(row)
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


class TestLoadEPW:
    def test_parses_header_and_series(self, tmp_path):
        wd = load_epw(_make_epw(tmp_path / "t.epw"))
        assert wd.location == "Testgrad"
        assert wd.country == "UZB"
        assert wd.latitude == pytest.approx(41.3)
        assert wd.elevation_m == pytest.approx(430.0)
        assert len(wd.t_dry_bulb_c) == HOURS_IN_YEAR
        assert len(wd.rh_pct) == HOURS_IN_YEAR
        assert len(wd.ghi_w_m2) == HOURS_IN_YEAR
        # Синусоида: зимой холодно, летом тепло
        assert wd.t_min_c < 0 < wd.t_max_c
        assert -15 < wd.t_mean_c < 25

    def test_leap_year_truncated(self, tmp_path):
        wd = load_epw(_make_epw(tmp_path / "leap.epw", hours=8784))
        assert len(wd.t_dry_bulb_c) == HOURS_IN_YEAR

    def test_too_short_raises(self, tmp_path):
        with pytest.raises(ValueError, match="8760"):
            load_epw(_make_epw(tmp_path / "short.epw", hours=100))

    def test_not_epw_raises(self, tmp_path):
        p = tmp_path / "x.epw"
        p.write_text("\n".join(["junk"] * 20), encoding="utf-8")
        with pytest.raises(ValueError, match="LOCATION"):
            load_epw(p)

    def test_missing_values_filled(self, tmp_path):
        """Код 99.9 (нет данных) заменяется последним валидным значением."""
        def t_func(h):
            return 99.9 if h == 10 else 5.0
        wd = load_epw(_make_epw(tmp_path / "m.epw", t_func=t_func))
        assert wd.t_dry_bulb_c[10] == pytest.approx(5.0)


class TestSimulationWithWeather:
    def _project(self):
        from hvac.models import Space
        from hvac.project import HVACProject
        p = HVACProject()
        p.params.apply_city("Ташкент")
        sp = Space(space_id="1", number="1", name="Офис", level="L1",
                   area_m2=25, volume_m3=75, height_m=3,
                   heat_loss_w=1500, heat_gain_w=2000,
                   heat_gain_sensible_w=1500)
        p.spaces.append(sp)
        p._space_by_id[sp.space_id] = sp
        return p

    def test_simulation_uses_epw_temperatures(self, tmp_path):
        p = self._project()
        p.load_weather(str(_make_epw(tmp_path / "t.epw")))
        result = p.simulate_annual_energy(keep_hourly=True)
        assert result.weather_source == "Testgrad"
        # Температурный профиль симуляции — ровно из файла
        assert result.hourly_t_out_c[0] == pytest.approx(
            p.weather_data.t_dry_bulb_c[0])
        assert result.e_heat_kwh > 0

    def test_clear_weather_returns_to_synthetic(self, tmp_path):
        p = self._project()
        p.load_weather(str(_make_epw(tmp_path / "t.epw")))
        p.clear_weather()
        result = p.simulate_annual_energy()
        assert result.weather_source == ""

    def test_warmer_climate_less_heating(self, tmp_path):
        """Сдвиг всего года на +5°C должен снизить отопление и
        увеличить охлаждение — sanity-check физики."""
        p = self._project()
        p.load_weather(str(_make_epw(tmp_path / "cold.epw")))
        base = p.simulate_annual_energy()
        p.load_weather(str(_make_epw(
            tmp_path / "warm.epw",
            t_func=lambda h: 15.0 - 20.0 * math.cos(
                2 * math.pi * (h / 24 - 196) / 365))))
        warm = p.simulate_annual_energy()
        assert warm.e_heat_kwh < base.e_heat_kwh
        assert warm.e_cool_kwh > base.e_cool_kwh
