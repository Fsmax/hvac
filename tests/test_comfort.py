# -*- coding: utf-8 -*-
"""Тесты PMV/PPD по ISO 7730 (метод Фангера)."""

import pytest

from hvac.comfort import (
    assess_space, calc_pmv, calc_ppd, comfort_category,
)
from hvac.models import Space


class TestPMVReferenceValues:
    """Контрольные точки из ISO 7730:2005 Приложение D, табл. D.1."""

    def test_case_cool_office(self):
        """ta=tr=22°C, v=0.10, RH=60%, 1.2 met, 0.5 clo → PMV=−0.75, PPD=17%."""
        pmv = calc_pmv(22.0, 22.0, 0.10, 60.0, met=1.2, clo=0.5)
        assert pmv == pytest.approx(-0.75, abs=0.05)
        assert calc_ppd(pmv) == pytest.approx(17.0, abs=2.0)

    def test_case_warm_office(self):
        """ta=tr=27°C, v=0.10, RH=60%, 1.2 met, 0.5 clo → PMV=+0.77, PPD=17%."""
        pmv = calc_pmv(27.0, 27.0, 0.10, 60.0, met=1.2, clo=0.5)
        assert pmv == pytest.approx(0.77, abs=0.05)
        assert calc_ppd(pmv) == pytest.approx(17.0, abs=2.0)

    def test_case_air_speed_cools(self):
        """ta=tr=27°C, но v=0.30 м/с → PMV падает до ≈+0.44 (обдув охлаждает)."""
        pmv = calc_pmv(27.0, 27.0, 0.30, 60.0, met=1.2, clo=0.5)
        assert pmv == pytest.approx(0.44, abs=0.05)


class TestPPD:
    def test_minimum_at_neutral(self):
        """PPD(0) = 5% — даже в идеале 5% людей недовольны."""
        assert calc_ppd(0.0) == pytest.approx(5.0)

    def test_symmetric(self):
        assert calc_ppd(0.5) == pytest.approx(calc_ppd(-0.5))

    def test_monotonic_from_neutral(self):
        assert calc_ppd(0.2) < calc_ppd(0.5) < calc_ppd(1.0) < calc_ppd(2.0)


class TestPhysics:
    def test_pmv_monotonic_in_temperature(self):
        """Теплее воздух → выше PMV."""
        vals = [calc_pmv(t, rh_pct=50, met=1.2, clo=1.0)
                for t in (18.0, 20.0, 22.0, 24.0)]
        assert vals == sorted(vals)

    def test_more_clothing_warmer(self):
        assert (calc_pmv(20.0, clo=1.0) > calc_pmv(20.0, clo=0.5))

    def test_higher_met_warmer(self):
        assert (calc_pmv(20.0, met=1.6, clo=1.0)
                > calc_pmv(20.0, met=1.2, clo=1.0))


class TestCategory:
    def test_thresholds(self):
        assert comfort_category(0.1) == "A"
        assert comfort_category(-0.3) == "B"
        assert comfort_category(0.6) == "C"
        assert comfort_category(1.2) == "—"


def _space(sid="1", t_heat=20.0, t_cool=24.0, room_type="Офис"):
    return Space(space_id=sid, number=sid, name="Room", level="L1",
                 area_m2=20, volume_m3=60, height_m=3,
                 room_type=room_type, t_in_heat=t_heat, t_in_cool=t_cool)


class TestAssess:
    def test_assess_space_heating_defaults(self):
        """Зима: clo=1.0, t = t_in_heat, RH по типу помещения (офис 50%)."""
        r = assess_space(_space(), "heating")
        assert r.t_air_c == 20.0
        assert r.clo == 1.0
        assert r.rh_pct == 50
        assert r.category in ("A", "B", "C", "—")

    def test_assess_space_cooling_defaults(self):
        r = assess_space(_space(), "cooling")
        assert r.t_air_c == 24.0
        assert r.clo == 0.5

    def test_office_setpoints_are_comfortable(self):
        """Типовые уставки 20/24°C для офиса попадают в категории A–C."""
        for season in ("heating", "cooling"):
            r = assess_space(_space(), season)
            assert r.category != "—", f"{season}: PMV={r.pmv}"

    def test_project_facade(self):
        from hvac.project import HVACProject
        p = HVACProject()
        p.spaces = [_space("1"), _space("2", t_heat=22.0)]
        result = p.calculate_comfort()
        assert set(result.keys()) == {"heating", "cooling"}
        assert set(result["heating"].keys()) == {"1", "2"}
        assert p.comfort_results is result

    def test_rh_override(self):
        r = assess_space(_space(), "heating", rh_override=30.0)
        assert r.rh_pct == 30.0
