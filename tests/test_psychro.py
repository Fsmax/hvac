# -*- coding: utf-8 -*-
"""Тесты психрометрики и процессов AHU."""

import pytest
from hvac.psychro import (
    AirState, P_ATM, cool, cool_dehumidify, dew_point, enthalpy,
    heat, heat_recovery, humidify_adiabatic, humidify_steam,
    humidity_ratio_from_rh, mass_flow_from_volume, mix_streams,
    relative_humidity, saturation_pressure_pa, specific_volume,
    temperature_from_h_w, wet_bulb,
)


class TestSaturationPressure:
    """Проверка по справочным точкам ASHRAE."""

    @pytest.mark.parametrize("t,p_ref", [
        (0.0, 611.2),
        (10.0, 1227.7),
        (20.0, 2338.8),
        (25.0, 3169.0),
        (30.0, 4245.0),
        (40.0, 7384.0),
    ])
    def test_sat_pressure(self, t, p_ref):
        p = saturation_pressure_pa(t)
        # ASHRAE eq (6) дают <0.5% отклонения от табличных
        assert p == pytest.approx(p_ref, rel=0.01)

    def test_sub_zero(self):
        """Над льдом: при −10°C psat ≈ 260 Па."""
        p = saturation_pressure_pa(-10.0)
        assert p == pytest.approx(260, rel=0.02)


class TestHumidityRatio:
    def test_w_from_rh_20c_50pct(self):
        """20°C, 50% RH → W ≈ 7.26 г/кг (справочно)."""
        W = humidity_ratio_from_rh(20.0, 0.50)
        assert W * 1000 == pytest.approx(7.26, rel=0.02)

    def test_w_from_rh_at_zero_rh(self):
        assert humidity_ratio_from_rh(25.0, 0.0) == 0.0

    def test_rh_roundtrip(self):
        """rh → W → rh должно сходиться."""
        for t in (5.0, 15.0, 25.0, 35.0):
            for rh in (0.3, 0.5, 0.7, 0.9):
                W = humidity_ratio_from_rh(t, rh)
                rh2 = relative_humidity(t, W)
                assert rh == pytest.approx(rh2, abs=0.001)


class TestEnthalpy:
    def test_dry_air(self):
        """Сухой воздух 20°C: H ≈ 20.12 кДж/кг."""
        h = enthalpy(20.0, 0.0)
        assert h == pytest.approx(20.12, rel=0.01)

    def test_humid_air_20c_50pct(self):
        """20°C, 50% — H ≈ 38.6 кДж/кг."""
        W = humidity_ratio_from_rh(20.0, 0.50)
        h = enthalpy(20.0, W)
        assert h == pytest.approx(38.6, rel=0.02)

    def test_temperature_from_h_w(self):
        """T из (H, W) должно быть обратной от enthalpy."""
        t_orig = 24.0
        W = humidity_ratio_from_rh(t_orig, 0.50)
        h = enthalpy(t_orig, W)
        t_calc = temperature_from_h_w(h, W)
        assert t_calc == pytest.approx(t_orig, abs=0.01)


class TestDewPoint:
    def test_25c_60pct(self):
        """25°C, 60% → Td ≈ 16.7°C."""
        W = humidity_ratio_from_rh(25.0, 0.60)
        td = dew_point(W)
        assert td == pytest.approx(16.7, abs=0.5)

    def test_saturated_air(self):
        """Насыщенный воздух: Td ≈ T."""
        W = humidity_ratio_from_rh(20.0, 1.0)
        td = dew_point(W)
        assert td == pytest.approx(20.0, abs=0.3)


class TestWetBulb:
    def test_wb_25c_50pct(self):
        """25°C, 50% RH → Twb ≈ 18.0°C."""
        W = humidity_ratio_from_rh(25.0, 0.50)
        twb = wet_bulb(25.0, W)
        assert twb == pytest.approx(18.0, abs=0.5)

    def test_wb_at_saturation_equals_t(self):
        W = humidity_ratio_from_rh(20.0, 1.0)
        twb = wet_bulb(20.0, W)
        assert twb == pytest.approx(20.0, abs=0.2)


class TestSpecificVolume:
    def test_v_dry_air_20c(self):
        """Сухой воздух при 20°C, 101325 Па: v ≈ 0.830 м³/кг."""
        v = specific_volume(20.0, 0.0)
        assert v == pytest.approx(0.830, rel=0.005)

    def test_v_humid_20c_50pct(self):
        """Влажный 20°C, 50%: v ≈ 0.840 м³/кг."""
        W = humidity_ratio_from_rh(20.0, 0.50)
        v = specific_volume(20.0, W)
        assert v == pytest.approx(0.840, rel=0.01)


class TestAirState:
    def test_from_t_rh(self):
        s = AirState.from_t_rh(20.0, 0.50)
        assert s.rh == pytest.approx(0.50, abs=0.001)
        assert s.w_g_kg == pytest.approx(7.26, rel=0.02)

    def test_from_t_wb_roundtrip(self):
        """Из (T, Twb) → AirState → проверка Twb."""
        s = AirState.from_t_wb(25.0, 18.0)
        assert s.t_wb_c == pytest.approx(18.0, abs=0.5)

    def test_from_t_dp(self):
        s = AirState.from_t_dp(25.0, 15.0)
        assert s.t_dp_c == pytest.approx(15.0, abs=0.3)


class TestMixing:
    def test_two_equal_streams(self):
        """Смесь 50/50 двух одинаковых = тот же воздух."""
        s = AirState.from_t_rh(20.0, 0.50)
        mixed = mix_streams([(s, 1.0), (s, 1.0)])
        assert mixed.t_c == pytest.approx(20.0, abs=0.01)
        assert mixed.W == pytest.approx(s.W, abs=1e-6)

    def test_recirculation(self):
        """Зимой смесь 70% наружного (-15°C) и 30% внутреннего (22°C)
        даёт около -4°C."""
        out = AirState.from_t_rh(-15.0, 0.85)
        ind = AirState.from_t_rh(22.0, 0.30)
        m = mix_streams([(out, 0.7), (ind, 0.3)])
        assert m.t_c == pytest.approx(-3.9, abs=0.5)


class TestHeatingCooling:
    def test_dry_heating_w_const(self):
        """Калорифер: W const, T растёт."""
        s = AirState.from_t_rh(-15.0, 0.85)
        s2 = heat(s, 22.0)
        assert s2.t_c == pytest.approx(22.0)
        assert s2.W == pytest.approx(s.W)
        # RH должна резко упасть
        assert s2.rh < 0.10

    def test_cooling_above_dp_is_dry(self):
        """Охлаждение выше точки росы — сухое."""
        s = AirState.from_t_rh(30.0, 0.40)
        td = s.t_dp_c
        s2 = cool(s, td + 2.0)
        assert s2.W == pytest.approx(s.W)

    def test_cooling_below_dp_condenses(self):
        """Охлаждение ниже Td — конденсация, W падает."""
        s = AirState.from_t_rh(30.0, 0.60)
        td = s.t_dp_c
        s2 = cool(s, td - 5.0)
        assert s2.W < s.W
        # Выход насыщенный
        assert s2.rh == pytest.approx(1.0, abs=0.01)

    def test_cool_dehumidify_with_bf(self):
        """Реальный охладитель: выход между ADP и вход с пропорцией BF."""
        s = AirState.from_t_rh(28.0, 0.55)
        out = cool_dehumidify(s, t_adp=10.0, bypass_factor=0.15)
        # Температура выхода должна быть между ADP и Tin
        assert 10.0 < out.t_c < 28.0
        # Влагосодержание упало
        assert out.W < s.W


class TestHumidify:
    def test_steam_raises_w_keeps_t(self):
        s = AirState.from_t_rh(20.0, 0.20)
        target = AirState.from_t_rh(20.0, 0.50)
        s2 = humidify_steam(s, target.W)
        assert s2.t_c == pytest.approx(20.0, abs=0.1)
        assert s2.W == pytest.approx(target.W, rel=0.001)

    def test_adiabatic_drops_t(self):
        """Адиабат: t падает, Twb ≈ const."""
        s = AirState.from_t_rh(22.0, 0.20)
        twb_in = s.t_wb_c
        s2 = humidify_adiabatic(s, efficiency=0.85)
        assert s2.t_c < s.t_c
        # Twb сохраняется приближённо
        assert s2.t_wb_c == pytest.approx(twb_in, abs=0.5)


class TestHeatRecovery:
    def test_perfect_recovery(self):
        """η=1.0 → t_out = t_extract."""
        out = AirState.from_t_rh(-15.0, 0.85)
        ext = AirState.from_t_rh(22.0, 0.30)
        rec = heat_recovery(out, ext, efficiency_t=1.0)
        assert rec.t_c == pytest.approx(22.0, abs=0.01)

    def test_zero_recovery(self):
        out = AirState.from_t_rh(-15.0, 0.85)
        ext = AirState.from_t_rh(22.0, 0.30)
        rec = heat_recovery(out, ext, efficiency_t=0.0)
        assert rec.t_c == pytest.approx(-15.0)

    def test_typical_plate_60pct(self):
        """Пластинчатый рекуператор 60% от -15 до 22°C даёт +7.2°C."""
        out = AirState.from_t_rh(-15.0, 0.85)
        ext = AirState.from_t_rh(22.0, 0.30)
        rec = heat_recovery(out, ext, efficiency_t=0.60)
        assert rec.t_c == pytest.approx(-15.0 + 0.60 * 37.0, abs=0.1)
        # Влагосодержание не меняется (пластинчатый, η_w=0)
        assert rec.W == pytest.approx(out.W)


class TestMassFlow:
    def test_volume_to_mass(self):
        """1000 м³/ч стандартного воздуха ≈ 0.335 кг/с."""
        s = AirState.from_t_rh(20.0, 0.50)
        m = mass_flow_from_volume(1000.0, s)
        # m = (1000/3600) / 0.84 ≈ 0.331 кг/с
        assert m == pytest.approx(0.331, abs=0.005)


# ============================================================================
# AHU process
# ============================================================================

class TestAHUProcess:
    """Тесты модуля ahu_process."""

    def _make_load(self, t_in_w=22.0, t_in_s=24.0):
        from hvac.ahu_load import AHULoad
        return AHULoad(
            system_name="ПВ-1",
            n_spaces=10,
            supply_m3_h=5000.0,
            exhaust_m3_h=5000.0,
            t_supply_winter=18.0,
            t_supply_summer=18.0,
            t_indoor_avg_winter=t_in_w,
            t_indoor_avg_summer=t_in_s,
            has_recovery=True,
            recovery_eff_winter=0.65,
            recovery_eff_summer=0.55,
        )

    def _make_params(self):
        from hvac.models import ProjectParameters
        p = ProjectParameters()
        p.apply_city("Ташкент")
        return p

    def test_winter_has_recovery_and_heater(self):
        from hvac.ahu_process import compute_ahu_process
        load = self._make_load()
        params = self._make_params()
        proc = compute_ahu_process(load, params, mode="winter")
        assert "outdoor" in proc.points
        assert "after_recovery" in proc.points
        assert "after_heater" in proc.points
        assert "supply" in proc.points
        # Калорифер тратит мощность
        assert proc.q_heater_kw > 0
        # После рекуператора теплее наружного
        assert (proc.points["after_recovery"].t_c
                > proc.points["outdoor"].t_c)
        # Финальная подача = t_supply_winter
        assert proc.points["supply"].t_c == pytest.approx(18.0, abs=0.1)

    def test_summer_cools_and_dehumidifies(self):
        from hvac.ahu_process import compute_ahu_process
        load = self._make_load()
        params = self._make_params()
        proc = compute_ahu_process(load, params, mode="summer")
        assert "after_cooler" in proc.points
        # Охладитель снимает мощность
        assert proc.q_cooler_total_kw > 0
        # Скрытая часть > 0 — конденсация
        assert proc.q_cooler_latent_kw >= 0
        # Финальная температура близка к t_supply_summer
        assert proc.points["supply"].t_c == pytest.approx(18.0, abs=1.0)

    def test_winter_with_humidifier(self):
        from hvac.ahu_process import compute_ahu_process
        load = self._make_load()
        params = self._make_params()
        proc = compute_ahu_process(load, params, mode="winter",
                                     humidifier_target_rh=0.40,
                                     humidifier_kind="steam")
        assert "after_humid" in proc.points
        assert proc.humidifier_water_kg_h > 0
        # RH на подаче ≈ 0.40
        assert proc.points["supply"].rh == pytest.approx(0.40, abs=0.02)

    def test_recirculation_warms_winter(self):
        """С рециркуляцией 30% вход в калорифер теплее."""
        from hvac.ahu_process import compute_ahu_process
        load = self._make_load()
        params = self._make_params()
        no_rec = compute_ahu_process(load, params, mode="winter",
                                       recirculation_ratio=0.0)
        with_rec = compute_ahu_process(load, params, mode="winter",
                                         recirculation_ratio=0.3)
        # Мощность калорифера падает при рециркуляции
        assert with_rec.q_heater_kw < no_rec.q_heater_kw

    def test_transitional_mode(self):
        from hvac.ahu_process import compute_ahu_process
        load = self._make_load()
        params = self._make_params()
        proc = compute_ahu_process(load, params, mode="transitional")
        assert proc.points["outdoor"].t_c == pytest.approx(5.0)
        # Тёплый калорифер — но менее мощный, чем зимой
        proc_w = compute_ahu_process(load, params, mode="winter")
        assert proc.q_heater_kw < proc_w.q_heater_kw

    def test_unknown_mode_raises(self):
        from hvac.ahu_process import compute_ahu_process
        load = self._make_load()
        params = self._make_params()
        with pytest.raises(ValueError):
            compute_ahu_process(load, params, mode="autumn")
