# -*- coding: utf-8 -*-
"""Тесты 8760-часовой симуляции."""

import pytest
from hvac.energy_simulation import (
    HOURS_IN_YEAR, SCHEDULES, hour_to_iso_datetime, occupancy_factor,
    schedule_for_room_type, simulate_year, synth_outdoor_temperature,
)
from hvac.project import HVACProject
from hvac.models import Space


class TestSchedules:
    def test_office_low_at_night(self):
        """Офис ночью почти пуст."""
        f = occupancy_factor("office", 3)  # 3 утра
        assert f < 0.1

    def test_office_high_at_noon(self):
        """Полдень будний день — полная нагрузка."""
        f = occupancy_factor("office", 11)  # понедельник 11:00
        assert f >= 0.9

    def test_residential_high_at_evening(self):
        f = occupancy_factor("residential", 19)
        assert f >= 0.9

    def test_unknown_falls_to_office(self):
        f = occupancy_factor("unknown_type", 11)
        # Должен использовать office по умолчанию
        assert f == occupancy_factor("office", 11)

    def test_weekend_office_low(self):
        """Суббота 12 — офис пуст."""
        # День 5 = суббота при day_of_year % 7 == 5
        f = occupancy_factor("office", 5 * 24 + 12)
        assert f <= 0.1


class TestSchedulesMapping:
    def test_office_room_maps_to_office(self):
        assert schedule_for_room_type("Офис") == "office"

    def test_class_maps_to_school(self):
        assert schedule_for_room_type("Класс / аудитория") == "school"

    def test_residential_default(self):
        assert schedule_for_room_type("Жилая комната") == "residential"


class TestSyntheticTemperature:
    def test_winter_morning_cold(self):
        """Январь 5 утра — около зимнего расчётного."""
        # День 15 (15 января), час 5
        t = synth_outdoor_temperature(-15, 36, 14, 15 * 24 + 5)
        assert t < 0

    def test_summer_afternoon_hot(self):
        """15 июля 15 часов — около летнего расчётного."""
        t = synth_outdoor_temperature(-15, 36, 14, 196 * 24 + 15)
        # Должен быть близок к 36
        assert t > 30

    def test_daily_amplitude(self):
        """Разница между 15:00 и 5:00 — около daily_amplitude."""
        t_day = synth_outdoor_temperature(-15, 36, 14, 196 * 24 + 15)
        t_night = synth_outdoor_temperature(-15, 36, 14, 196 * 24 + 5)
        assert (t_day - t_night) > 10   # около 14, но синус не идеален


class TestSimulation:
    def _make_project(self, n=4, q_loss=2000, q_gain=2500,
                       city="Ташкент"):
        p = HVACProject()
        p.params.apply_city(city)
        for i in range(n):
            sp = Space(
                space_id=f"r{i}", number=f"R-{i:03d}",
                name="Office", level="L1",
                area_m2=25, volume_m3=75, height_m=3,
                t_in_heat=20, t_in_cool=24,
                room_type="Офис",
                heat_loss_w=q_loss, heat_gain_w=q_gain,
                heat_gain_sensible_w=q_gain * 0.75,
                heat_gain_latent_w=q_gain * 0.25,
                lighting_w_m2=12, equipment_w_m2=10,
                occupancy_people=2,
            )
            p.spaces.append(sp); p._space_by_id[sp.space_id] = sp
        return p

    def test_basic_run(self):
        p = self._make_project()
        result = simulate_year(p)
        assert result.n_spaces == 4
        assert result.total_area_m2 == 100
        assert result.e_heat_kwh > 0 or result.e_cool_kwh > 0
        assert result.q_peak_heat_w >= 0
        assert result.q_peak_cool_w >= 0

    def test_specific_consumption_in_reasonable_range(self):
        """Удельные показатели должны быть в инженерном диапазоне."""
        p = self._make_project()
        result = simulate_year(p)
        # Для Ташкента и расчётной нагрузки ~80 Вт/м² типичная
        # годовая потребность 50-200 кВт·ч/м². Допускаем широкий диапазон.
        assert 10 < result.e_total_kwh_m2 < 500

    def test_hourly_arrays_when_requested(self):
        p = self._make_project()
        result = simulate_year(p, keep_hourly=True)
        assert result.hourly_q_heat_w is not None
        assert len(result.hourly_q_heat_w) == HOURS_IN_YEAR
        assert result.hourly_t_out_c is not None
        # Зимой ниже летнего
        winter_t = result.hourly_t_out_c[15 * 24 + 5]
        summer_t = result.hourly_t_out_c[196 * 24 + 15]
        assert summer_t > winter_t

    def test_no_hourly_when_disabled(self):
        p = self._make_project()
        result = simulate_year(p, keep_hourly=False)
        assert result.hourly_q_heat_w is None

    def test_colder_city_more_heating(self):
        """В Москве потребление на отопление выше, чем в Ташкенте."""
        p_tash = self._make_project(city="Ташкент")
        p_mosk = self._make_project(city="Москва")
        r_tash = simulate_year(p_tash)
        r_mosk = simulate_year(p_mosk)
        assert r_mosk.e_heat_kwh > r_tash.e_heat_kwh

    def test_setpoint_offset_reduces_consumption(self):
        """Ночное отступление снижает потребление."""
        p = self._make_project(city="Москва")
        base = simulate_year(p)
        with_setback = simulate_year(
            p, heating_setpoint_offset=-2.0,
        )
        assert with_setback.e_heat_kwh < base.e_heat_kwh

    def test_thermal_mass_filters_peaks(self):
        """Массивное здание (τ=20 ч) сглаживает пики сильнее, чем лёгкое (τ=4 ч)."""
        p = self._make_project()
        light = simulate_year(p, thermal_mass_tau_h=4.0)
        heavy = simulate_year(p, thermal_mass_tau_h=20.0)
        # Пик нагрузки в массивном здании ниже
        assert heavy.q_peak_heat_w <= light.q_peak_heat_w * 1.01

    def test_empty_project_returns_empty(self):
        p = HVACProject()
        result = simulate_year(p)
        assert result.n_spaces == 0
        assert result.e_heat_kwh == 0


class TestIsoDatetime:
    def test_hour_0(self):
        s = hour_to_iso_datetime(0)
        assert s.startswith("2026-01-01 00:")

    def test_july_15_noon(self):
        # 196 * 24 + 12 — это 15 июля около полудня
        s = hour_to_iso_datetime(196 * 24 + 12)
        assert "07-16" in s or "07-15" in s  # около этого
