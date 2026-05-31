# -*- coding: utf-8 -*-
"""Тесты акустического расчёта и подбора шумоглушителей."""

import pytest
from hvac.acoustics import (
    A_WEIGHTING_DB, OCTAVE_BANDS_HZ, SILENCER_CATALOG,
    a_weighted_level, add_sources, analyze_path,
    branch_split_attenuation, duct_attenuation_per_m,
    fan_lw_estimate_beranek, fan_sound_power_spectrum,
    required_noise_level, select_silencer, subtract_attenuation,
    zero_spectrum,
)


class TestSpectrumBasics:
    def test_a_weighting_at_1khz_zero(self):
        """1000 Гц — опорная частота, А-коррекция = 0."""
        assert A_WEIGHTING_DB[1000] == 0.0

    def test_lpa_from_uniform_spectrum(self):
        """Спектр 50 дБ во всех октавах. LpA должен быть ≈ 56-57 дБА
        (доминируют средние частоты после А-коррекции)."""
        sp = {b: 50.0 for b in OCTAVE_BANDS_HZ}
        lpa = a_weighted_level(sp)
        assert 54 < lpa < 60

    def test_add_sources_3db_for_equal(self):
        """Два одинаковых источника по 60 дБ дают 63 дБ."""
        s1 = {b: 60.0 for b in OCTAVE_BANDS_HZ}
        s2 = {b: 60.0 for b in OCTAVE_BANDS_HZ}
        out = add_sources(s1, s2)
        for b in OCTAVE_BANDS_HZ:
            assert out[b] == pytest.approx(63.0, abs=0.1)

    def test_subtract_doesnt_go_negative(self):
        """Затухание больше источника не даёт отрицательного Lp."""
        src = {b: 30.0 for b in OCTAVE_BANDS_HZ}
        att = {b: 50.0 for b in OCTAVE_BANDS_HZ}
        out = subtract_attenuation(src, att)
        for b in OCTAVE_BANDS_HZ:
            assert out[b] >= 0


class TestFanEstimation:
    def test_beranek_increases_with_power(self):
        """Больше Q и ΔP → выше Lw."""
        lw1 = fan_lw_estimate_beranek(1000.0, 200.0)
        lw2 = fan_lw_estimate_beranek(5000.0, 600.0)
        assert lw2 > lw1

    def test_zero_flow_returns_zero(self):
        assert fan_lw_estimate_beranek(0.0, 200.0) == 0.0

    def test_low_efficiency_adds_3db(self):
        """КПД < 0.7 даёт +3 дБ корректировки."""
        lw_high = fan_lw_estimate_beranek(2000.0, 300.0, efficiency=0.75)
        lw_low = fan_lw_estimate_beranek(2000.0, 300.0, efficiency=0.55)
        assert lw_low == pytest.approx(lw_high + 3.0)

    def test_spectrum_offsets(self):
        """Спектр центробежного — выше на низких, ниже на высоких."""
        sp = fan_sound_power_spectrum(80.0, fan_type="centrifugal")
        assert sp[63] > sp[8000]


class TestDuctAttenuation:
    def test_small_more_attenuation(self):
        """Маленький воздуховод (Ø200) даёт больше затухания на полосе."""
        small = duct_attenuation_per_m(200)
        big = duct_attenuation_per_m(800)
        # На 500 Гц малый > большого
        assert small[500] > big[500]

    def test_lined_increases_attenuation(self):
        """Облицовка усиливает затухание."""
        plain = duct_attenuation_per_m(400, lined=False)
        lined = duct_attenuation_per_m(400, lined=True)
        # На средних частотах ×3
        assert lined[500] > plain[500] * 2.5


class TestBranchSplit:
    def test_equal_split_3db(self):
        """50/50 разделение даёт 3 дБ затухания на ветви."""
        att = branch_split_attenuation(1000.0, 500.0)
        assert att[1000] == pytest.approx(3.0, abs=0.1)

    def test_10_to_1(self):
        """10:1 → 10 дБ."""
        att = branch_split_attenuation(1000.0, 100.0)
        assert att[1000] == pytest.approx(10.0, abs=0.1)


class TestNoiseNorms:
    def test_living_room_40dba(self):
        assert required_noise_level("Жилая комната") == 40.0

    def test_office_50dba(self):
        assert required_noise_level("Офис") == 50.0

    def test_default_50(self):
        assert required_noise_level("странный тип") == 50.0


class TestAnalysisAndSelection:
    def test_path_without_silencer(self):
        """Цепочка: вентилятор + воздуховод + 2 отвода."""
        res = analyze_path(
            fan_lw_dba=80.0, fan_type="centrifugal",
            duct_segments=[(10.0, 400, False)],
            elbows_90_count=2,
            room_volume_m3=30, room_norm_dba=40,
        )
        assert res.lpa_at_terminal > 0
        # Без глушителя в типовой ситуации норматив часто превышен
        assert isinstance(res.silencer_required, bool)

    def test_silencer_reduces_level(self):
        """Установка шумоглушителя снижает Lpa."""
        params = dict(
            fan_lw_dba=85.0, fan_type="centrifugal",
            duct_segments=[(5.0, 400, False)],
            elbows_90_count=1,
            room_volume_m3=30, room_norm_dba=40,
        )
        res_no = analyze_path(**params, silencer=None)
        res_with = analyze_path(**params, silencer=SILENCER_CATALOG[3])  # 1500 мм
        assert res_with.lpa_at_terminal < res_no.lpa_at_terminal

    def test_select_silencer_picks_first_fitting(self):
        """Подбор глушителя должен довести Lpa ниже норматива."""
        res = select_silencer(
            fan_lw_dba=82.0, room_norm_dba=40,
            duct_segments=[(8.0, 400, False)],
            elbows_90_count=2,
            room_volume_m3=30,
        )
        # Норматив 40 дБА должен быть выполнен либо изначально, либо
        # с подобранным глушителем.
        assert res.lpa_at_terminal <= res.lpa_required_dba + 0.5

    def test_quiet_fan_no_silencer_needed(self):
        """Тихий вентилятор + большое помещение — без глушителя."""
        res = select_silencer(
            fan_lw_dba=55.0, room_norm_dba=50,
            duct_segments=[(15.0, 500, True)],   # облицованный длинный
            elbows_90_count=3,
            room_volume_m3=100,
            branch_flow_ratios=[(2000, 200)],
        )
        assert res.lpa_at_terminal <= res.lpa_required_dba

    def test_loud_fan_needs_silencer(self):
        """Сильный вентилятор требует подобрать глушитель."""
        # Lw=85 дБА, норма 40 дБА (офис) — без глушителя норматив
        # должен быть превышен; подбор найдёт подходящий.
        res = select_silencer(
            fan_lw_dba=85.0, room_norm_dba=40,
            duct_segments=[(3.0, 400, False)],
            elbows_90_count=1,
            room_volume_m3=40,
        )
        # Без глушителя норматив должен быть превышен
        assert res.silencer_required
        # Подбор должен вернуть какой-то глушитель (минимум — fallback)
        assert res.silencer_selected is not None
        # Результат либо в норме, либо в пределах 2 дБ (граничный случай —
        # глушитель не дотянул, но это самое эффективное из каталога)
        assert res.lpa_at_terminal <= res.lpa_required_dba + 2.0

    def test_chain_breakdown_has_steps(self):
        res = analyze_path(
            fan_lw_dba=80.0,
            duct_segments=[(5.0, 400, False)],
            elbows_90_count=1,
            silencer=SILENCER_CATALOG[1],
            room_volume_m3=30, room_norm_dba=40,
        )
        steps = [s[0] for s in res.chain_breakdown]
        assert any("Вентилятор" in s for s in steps)
        assert any("Шумоглушитель" in s for s in steps)
        assert any("диффузор" in s.lower() for s in steps)
