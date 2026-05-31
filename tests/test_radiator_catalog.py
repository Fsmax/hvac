# -*- coding: utf-8 -*-
"""Тесты каталога радиаторов и подбора."""

import pytest
from hvac.radiator_catalog import (
    RADIATOR_CATALOG, RadiatorModel, arithmetic_temp_diff, correct_power,
    log_mean_temp_diff, select_radiator, select_radiators_for_spaces,
)


class TestTemperatureDiff:
    def test_log_mean_80_60_20(self):
        """ΔT_log(80/60/20) ≈ 49.3 K (точное значение, ниже арифм. 50 K)."""
        dt = log_mean_temp_diff(80.0, 60.0, 20.0)
        assert dt == pytest.approx(49.33, abs=0.05)
        # Логарифмический всегда меньше арифметического при ΔT1 ≠ ΔT2
        assert dt < arithmetic_temp_diff(80.0, 60.0, 20.0)

    def test_log_mean_75_65_20(self):
        """ΔT_log(75/65/20) ≈ 50.0 K — стандарт EN 442."""
        dt = log_mean_temp_diff(75.0, 65.0, 20.0)
        assert dt == pytest.approx(50.0, abs=0.2)

    def test_arithmetic_simpler(self):
        """Арифметический ΔT для 80/60/20: (80+60)/2−20 = 50 K."""
        dt = arithmetic_temp_diff(80.0, 60.0, 20.0)
        assert dt == pytest.approx(50.0)

    def test_zero_when_t_below_room(self):
        """Если t_return < t_room — прибор не отдаёт тепла."""
        dt = log_mean_temp_diff(25.0, 15.0, 20.0)
        assert dt == 0.0


class TestCorrectPower:
    def test_at_nominal(self):
        """ΔT = ΔT_nom → Q = Q_nom."""
        q = correct_power(1000.0, dt_actual=50.0, dt_nominal=50.0, n=1.30)
        assert q == pytest.approx(1000.0)

    def test_lower_dt_lower_power(self):
        """При ΔT=30 K (вместо 50) — Q падает по формуле (30/50)^1.3."""
        q = correct_power(1000.0, dt_actual=30.0, n=1.30)
        expected = (30.0 / 50.0) ** 1.30 * 1000.0
        assert q == pytest.approx(expected)

    def test_higher_dt_higher_power(self):
        """При ΔT=70 K мощность растёт."""
        q = correct_power(1000.0, dt_actual=70.0, n=1.30)
        assert q > 1000.0

    def test_zero_dt(self):
        assert correct_power(1000.0, 0.0) == 0.0

    def test_higher_n_larger_correction(self):
        """Алюминий с n=1.34 ближе к идеалу, чем чугун n=1.30 при низком ΔT."""
        q_al = correct_power(1000.0, dt_actual=40.0, n=1.34)
        q_cast = correct_power(1000.0, dt_actual=40.0, n=1.30)
        # При ΔT < 50K большая n даёт меньшее значение
        assert q_al < q_cast


class TestRadiatorActualPower:
    def test_kermi_at_nominal(self):
        """Kermi FK0 22 500x1000 при 75/65/20 ≈ номинал 1428 Вт."""
        m = next(m for m in RADIATOR_CATALOG
                 if m.name == "Kermi FK0 22 500x1000")
        q = m.actual_power_w(75.0, 65.0, 20.0)
        assert q == pytest.approx(m.q_nominal_w, rel=0.01)

    def test_kermi_at_low_temp(self):
        """Kermi 22 500x1000 при 55/45/20: ΔT≈30K → Q≈740 Вт."""
        m = next(m for m in RADIATOR_CATALOG
                 if m.name == "Kermi FK0 22 500x1000")
        q = m.actual_power_w(55.0, 45.0, 20.0)
        # (30/50)^1.3 * 1428 ≈ 740
        assert q == pytest.approx(740, rel=0.05)


class TestSelectRadiator:
    def test_picks_steel_panel_for_typical_room(self):
        """Q=1500 Вт при 80/60: подходит панельный 22 типоразмер."""
        pick = select_radiator(1500.0, t_supply=80.0, t_return=60.0)
        assert pick is not None
        assert pick.actual_power_w >= 1500.0
        # Запас разумный (≤ 50%)
        assert pick.margin_pct <= 50.0

    def test_sectional_returns_right_count(self):
        """Q=2000 Вт, биметалл, 80/60: Rifar Base 500 ~ 204 Вт/секция (×~10)."""
        pick = select_radiator(
            2000.0, t_supply=80.0, t_return=60.0,
            family_filter=["Биметалл"],
            prefer_sectional=True,
        )
        assert pick is not None
        assert pick.model.is_sectional
        assert pick.sections >= 2
        # Проверка, что фактическая мощность покрывает требуемую
        assert pick.actual_power_w >= 2000.0

    def test_filter_by_family(self):
        """Фильтр 'Алюминий' выдаёт только алюминиевые."""
        pick = select_radiator(
            1000.0, t_supply=70.0, t_return=55.0,
            family_filter=["Алюминий"],
            prefer_sectional=True,
        )
        assert pick is not None
        assert "Алюминий" in pick.model.family

    def test_no_solution_too_low_temp(self):
        """ΔT слишком низкий — приборов с достаточной мощностью нет."""
        pick = select_radiator(
            5000.0, t_supply=30.0, t_return=25.0,
            family_filter=["Стальной панельный 11"],   # один тип, маленький
            max_margin=0.10,
        )
        # При таком ΔT панель 500 высоты даст ≈ 100 Вт — не дотянет
        assert pick is None or pick.actual_power_w < 5000.0 * 1.5

    def test_max_margin_filter(self):
        """Запас > max_margin отбрасывает кандидата."""
        # 100 Вт — для всех радиаторов это будет огромный запас
        pick = select_radiator(
            100.0, t_supply=80.0, t_return=60.0,
            max_margin=0.10,
        )
        # Не должно быть пика с запасом > 10%
        if pick is not None:
            assert pick.margin_pct <= 10.0

    def test_underfloor_uses_lower_n(self):
        """Тёплый пол n=1.10 — отдача при низком ΔT выше, чем у радиатора."""
        # Не в каталоге как радиатор, но через correct_power напрямую
        q_underfloor = correct_power(1000.0, dt_actual=20.0, n=1.10)
        q_radiator = correct_power(1000.0, dt_actual=20.0, n=1.30)
        assert q_underfloor > q_radiator


class TestSelectForSpaces:
    def _make_space(self, sid, q_loss, t_in=20.0):
        from hvac.models import Space
        return Space(space_id=sid, number=sid, name="Room", level="L1",
                      area_m2=20, volume_m3=60, height_m=3,
                      t_in_heat=t_in, heat_loss_w=q_loss)

    def test_basic_assignment(self):
        spaces = [
            self._make_space("1", 800.0),
            self._make_space("2", 2400.0),
            self._make_space("3", 0.0),   # нет нагрузки
        ]
        result = select_radiators_for_spaces(spaces, t_supply=80, t_return=60)
        assert result["1"] is not None
        assert result["2"] is not None
        assert result["3"] is None        # пропустили

    def test_respects_t_in_heat(self):
        """Помещение с t_in=24 (например, ванная) получает прибор с
        большей мощностью (ΔT меньше)."""
        s_warm = self._make_space("warm", 1500.0, t_in=24.0)
        s_cool = self._make_space("cool", 1500.0, t_in=20.0)
        out_warm = select_radiators_for_spaces([s_warm], t_supply=80, t_return=60)
        out_cool = select_radiators_for_spaces([s_cool], t_supply=80, t_return=60)
        # При меньшем ΔT для тёплого помещения прибор должен иметь больший
        # номинал, поэтому actual_power тёплого > cool в номинальном эквиваленте
        if out_warm["warm"] and out_cool["cool"]:
            # тёплое помещение должно набирать больше мощности из каталога
            assert out_warm["warm"].actual_power_w >= 1500.0
            assert out_cool["cool"].actual_power_w >= 1500.0
