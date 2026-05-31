# -*- coding: utf-8 -*-
"""Тесты для каталога нормативов и формул дымоудаления."""

import pytest

from hvac import HVACProject
from hvac.catalogs.smoke_norms import (
    SMOKE_NORMS, get_smoke_norm, list_smoke_norms,
    SP7_RU, KMK_UZ, NFPA_92, CUSTOM, DEFAULT_SMOKE_NORM_CODE,
)
from hvac.smoke import SmokeSystem
from hvac.smoke_formulas import (
    kmk_zone_perimeter_kg_h, kmk_corridor_kg_h,
    nfpa_axisymmetric_plume_kg_s, nfpa_axisymmetric_plume_kg_h,
    smoke_density_kg_m3, mass_to_volume_m3h, calc_smoke_flow_m3h,
)


# ---------------------------------------------------------------------------
# Каталог нормативов
# ---------------------------------------------------------------------------

class TestSmokeNormsCatalog:

    def test_four_norms_registered(self):
        assert set(SMOKE_NORMS.keys()) == {"SP7_RU", "KMK_UZ",
                                           "NFPA_92", "CUSTOM"}

    def test_default_is_sp7(self):
        assert DEFAULT_SMOKE_NORM_CODE == "SP7_RU"

    def test_get_smoke_norm_returns_correct(self):
        assert get_smoke_norm("SP7_RU") is SP7_RU
        assert get_smoke_norm("KMK_UZ") is KMK_UZ
        assert get_smoke_norm("NFPA_92") is NFPA_92
        assert get_smoke_norm("CUSTOM") is CUSTOM

    def test_unknown_norm_falls_back_to_sp7(self):
        assert get_smoke_norm("UNKNOWN_XYZ") is SP7_RU

    def test_list_smoke_norms_has_four(self):
        assert len(list_smoke_norms()) == 4

    def test_each_norm_has_required_fields(self):
        for norm in list_smoke_norms():
            assert norm.code
            assert norm.title
            assert norm.reference
            assert norm.norms_per_m2          # должны быть значения
            assert norm.pressurization_rates_m3h
            assert norm.max_zone_area_m2 > 0
            assert 0 < norm.default_makeup_ratio <= 1.0
            assert norm.default_t_smoke_C > 0
            assert norm.calc_method_recommended
            assert norm.available_calc_methods

    def test_sp7_has_known_parking_value(self):
        # СП 7 — практическая норма для закрытой парковки = 24 м³/ч·м²
        assert SP7_RU.norms_per_m2["parking_closed"] == 24.0

    def test_kmk_recommends_perimeter_formula(self):
        # КМК — рекомендован метод плюм-теории помещения
        assert KMK_UZ.calc_method_recommended == "kmk_zone_perimeter"
        assert "kmk_zone_perimeter" in KMK_UZ.available_calc_methods
        assert "kmk_corridor" in KMK_UZ.available_calc_methods

    def test_nfpa_recommends_plume(self):
        assert NFPA_92.calc_method_recommended == "nfpa_plume_axi"
        # NFPA пересчитан в Па (4.4.2): 0.05 in WC ≈ 12.5 Па
        assert NFPA_92.default_pressure_pa == pytest.approx(12.5, rel=0.05)

    def test_custom_starts_as_copy_of_sp7(self):
        assert CUSTOM.norms_per_m2 == SP7_RU.norms_per_m2
        assert CUSTOM.pressurization_rates_m3h == SP7_RU.pressurization_rates_m3h
        # Но это РАЗНЫЕ объекты — правка CUSTOM не меняет SP7
        CUSTOM.norms_per_m2["test_key"] = 999.0
        assert "test_key" not in SP7_RU.norms_per_m2
        del CUSTOM.norms_per_m2["test_key"]   # очистка


# ---------------------------------------------------------------------------
# Формулы КМК
# ---------------------------------------------------------------------------

class TestKMKFormulas:

    def test_kmk_zone_perimeter_basic(self):
        """G = 676.8 · P · y^1.5 · Ks; P=12, y=2.5, Ks=1.0
        → G = 676.8 · 12 · 3.9528... · 1.0 ≈ 32 100 кг/ч"""
        G = kmk_zone_perimeter_kg_h(12.0, 2.5, 1.0)
        expected = 676.8 * 12.0 * (2.5 ** 1.5)
        assert G == pytest.approx(expected, rel=1e-9)
        assert G == pytest.approx(32099.6, rel=0.001)

    def test_kmk_zone_perimeter_with_sprinkler(self):
        """Ks=1.2 для помещений со спринклерами"""
        G_no = kmk_zone_perimeter_kg_h(12.0, 2.5, 1.0)
        G_sp = kmk_zone_perimeter_kg_h(12.0, 2.5, 1.2)
        assert G_sp == pytest.approx(G_no * 1.2, rel=1e-9)

    def test_kmk_zone_perimeter_caps_p_at_12(self):
        """P > 12 м обрезается до 12 м (норматив)"""
        G_12 = kmk_zone_perimeter_kg_h(12.0, 2.5)
        G_20 = kmk_zone_perimeter_kg_h(20.0, 2.5)
        assert G_12 == G_20

    def test_kmk_zone_perimeter_min_layer_height(self):
        """y < 2.5 м поднимается до 2.5 м (норматив)"""
        G_1 = kmk_zone_perimeter_kg_h(12.0, 1.5)
        G_25 = kmk_zone_perimeter_kg_h(12.0, 2.5)
        assert G_1 == G_25

    def test_kmk_zone_perimeter_zero_inputs(self):
        assert kmk_zone_perimeter_kg_h(0, 2.5) == 0.0
        assert kmk_zone_perimeter_kg_h(12, 0) == 0.0

    def test_kmk_corridor_no_door(self):
        """G1 = 3420 · n^1.5; n=1.0 → 3420 кг/ч"""
        assert kmk_corridor_kg_h(1.0) == pytest.approx(3420.0)

    def test_kmk_corridor_with_door(self):
        """G1 = 4300 · n^1.5 · Kd; n=1.0, Kd=1.0 → 4300 кг/ч"""
        assert kmk_corridor_kg_h(1.0, kd_door=1.0, with_door=True) == \
            pytest.approx(4300.0)

    def test_kmk_corridor_scales_with_n(self):
        """n удваивается → G растёт в 2^1.5 ≈ 2.83 раза"""
        g1 = kmk_corridor_kg_h(1.0)
        g2 = kmk_corridor_kg_h(2.0)
        assert g2 / g1 == pytest.approx(2.0 ** 1.5, rel=1e-9)

    def test_kmk_corridor_zero(self):
        assert kmk_corridor_kg_h(0) == 0.0


# ---------------------------------------------------------------------------
# Формулы NFPA 92
# ---------------------------------------------------------------------------

class TestNFPAFormulas:

    def test_nfpa_plume_above_limiting_height(self):
        """Q=5000 кВт, Qc=3500, z=6 м, zl=0.166·3500^0.4=0.166·26.05=4.32
        z > zl → m = 0.071·Qc^(1/3)·z^(5/3) + 0.0018·Qc
        = 0.071·15.18·19.81 + 0.0018·3500 = 21.36 + 6.30 ≈ 27.66 кг/с"""
        m = nfpa_axisymmetric_plume_kg_s(5000.0, 6.0, 0.7)
        # Qc = 3500
        Qc = 3500.0
        z = 6.0
        expected = 0.071 * Qc**(1/3) * z**(5/3) + 0.0018 * Qc
        assert m == pytest.approx(expected, rel=1e-9)

    def test_nfpa_plume_kg_per_hour(self):
        """kg/h = kg/s × 3600"""
        m_s = nfpa_axisymmetric_plume_kg_s(5000.0, 6.0)
        m_h = nfpa_axisymmetric_plume_kg_h(5000.0, 6.0)
        assert m_h == pytest.approx(m_s * 3600.0, rel=1e-12)

    def test_nfpa_plume_within_flame(self):
        """z < zl → m = 0.032·Qc^(3/5)·z (внутри пламени)
        Q=5000, Qc=3500, zl≈4.32, z=2 → m = 0.032·3500^0.6·2 = 0.032·134.0·2 ≈ 8.58"""
        m = nfpa_axisymmetric_plume_kg_s(5000.0, 2.0, 0.7)
        Qc = 3500.0
        expected = 0.032 * Qc**(3/5) * 2.0
        assert m == pytest.approx(expected, rel=1e-9)

    def test_nfpa_plume_zero_inputs(self):
        assert nfpa_axisymmetric_plume_kg_s(0, 5.0) == 0.0
        assert nfpa_axisymmetric_plume_kg_s(5000, 0) == 0.0

    def test_nfpa_plume_scales_with_height_above_limit(self):
        """Чем выше z над пожаром, тем больше захват воздуха в плюме"""
        m_low = nfpa_axisymmetric_plume_kg_s(5000, 5.0)
        m_high = nfpa_axisymmetric_plume_kg_s(5000, 10.0)
        assert m_high > m_low


# ---------------------------------------------------------------------------
# Конвертация массового → объёмного расхода
# ---------------------------------------------------------------------------

class TestMassToVolume:

    def test_density_at_20C(self):
        """ρ воздуха при 20°C ≈ 1.204 кг/м³"""
        assert smoke_density_kg_m3(20.0) == pytest.approx(1.204, rel=0.01)

    def test_density_decreases_with_temperature(self):
        """Горячий газ легче"""
        rho_20 = smoke_density_kg_m3(20.0)
        rho_300 = smoke_density_kg_m3(300.0)
        assert rho_300 < rho_20

    def test_density_at_300C(self):
        """ρ при 300°C ≈ 1.205 × 293/573 ≈ 0.617 кг/м³"""
        assert smoke_density_kg_m3(300.0) == pytest.approx(0.617, rel=0.02)

    def test_mass_to_volume_roundtrip(self):
        """L [м³/ч] = G [кг/ч] / ρ [кг/м³]"""
        rho = smoke_density_kg_m3(300.0)
        L = mass_to_volume_m3h(10000.0, 300.0)
        assert L == pytest.approx(10000.0 / rho, rel=1e-9)


# ---------------------------------------------------------------------------
# Универсальный диспетчер calc_smoke_flow_m3h
# ---------------------------------------------------------------------------

class TestCalcDispatcher:

    def test_norm_per_m2(self):
        sm = SmokeSystem(name="T", calc_method="norm_per_m2",
                          norm_per_m2=24.0)
        # 1000 м² × 24 м³/ч·м² = 24 000 м³/ч
        assert calc_smoke_flow_m3h(sm, 1000.0) == 24000.0

    def test_kmk_zone_perimeter(self):
        sm = SmokeSystem(name="T", calc_method="kmk_zone_perimeter",
                          fire_perimeter_m=12.0, layer_height_m=2.5,
                          ks_sprinkler=1.0, t_smoke_C=300.0)
        L = calc_smoke_flow_m3h(sm, area_m2=0)  # area не важна для плюма
        # G = 676.8·12·2.5^1.5 ≈ 32100 кг/ч; ρ@300 ≈ 0.617 → L ≈ 52 000 м³/ч
        G = kmk_zone_perimeter_kg_h(12.0, 2.5, 1.0)
        rho = smoke_density_kg_m3(300.0)
        assert L == pytest.approx(G / rho, rel=1e-9)

    def test_kmk_corridor(self):
        sm = SmokeSystem(name="T", calc_method="kmk_corridor",
                          n_corridor=1.5, kd_door=1.0, t_smoke_C=300.0)
        L = calc_smoke_flow_m3h(sm, area_m2=0)
        # G1 = 3420·1.5^1.5 = 3420·1.837 ≈ 6283
        G = kmk_corridor_kg_h(1.5)
        rho = smoke_density_kg_m3(300.0)
        assert L == pytest.approx(G / rho, rel=1e-9)

    def test_nfpa_plume(self):
        sm = SmokeSystem(name="T", calc_method="nfpa_plume_axi",
                          hrr_kw=5000.0, plume_height_m=6.0,
                          convective_fraction=0.7, t_smoke_C=300.0)
        L = calc_smoke_flow_m3h(sm, area_m2=0)
        G = nfpa_axisymmetric_plume_kg_h(5000.0, 6.0, 0.7)
        rho = smoke_density_kg_m3(300.0)
        assert L == pytest.approx(G / rho, rel=1e-9)

    def test_manual(self):
        sm = SmokeSystem(name="T", calc_method="manual",
                          L_smoke_m3h=12345.0)
        assert calc_smoke_flow_m3h(sm, 1000.0) == 12345.0

    def test_unknown_falls_back_to_norm(self):
        sm = SmokeSystem(name="T", calc_method="unknown_xyz",
                          norm_per_m2=10.0)
        assert calc_smoke_flow_m3h(sm, 500.0) == 5000.0


# ---------------------------------------------------------------------------
# Интеграция: переключение норматива на уровне HVACProject
# ---------------------------------------------------------------------------

class TestNormSwitch:

    def _make_parking_project(self, norm_code: str) -> HVACProject:
        p = HVACProject()
        p.params.smoke_norm = norm_code
        # Один уровень парковки, 2000 м²
        from hvac.models import Space
        for i in range(4):
            sp = Space(space_id=f"P{i}", number=f"P-{i}",
                       name="Парковка", level="B1", area_m2=500.0,
                       volume_m3=2000.0, room_type="Гараж / автостоянка")
            p.spaces.append(sp)
            p._space_by_id[sp.space_id] = sp
        return p

    def test_sp7_default_parking_norm(self):
        p = self._make_parking_project("SP7_RU")
        p.auto_assign_smoke_systems()
        # СДУ создалась, norm_per_m2 = 24 (СП 7)
        sdu = next(s for s in p.smoke_systems.values()
                   if s.system_type == "smoke_removal")
        assert sdu.norm_per_m2 == 24.0
        assert sdu.max_zone_area_m2 == 1600.0
        assert sdu.makeup_ratio == 0.7

    def test_nfpa_parking_uses_different_norm(self):
        p = self._make_parking_project("NFPA_92")
        p.auto_assign_smoke_systems()
        sdu = next(s for s in p.smoke_systems.values()
                   if s.system_type == "smoke_removal")
        # NFPA — 9 м³/ч·м² (≈ 0.5 cfm/sqft)
        assert sdu.norm_per_m2 == 9.0
        # Площадь дымовой зоны по IBC — 4645 м² (50 000 sqft)
        assert sdu.max_zone_area_m2 == pytest.approx(4645.0)
        # NFPA — makeup ratio 0.85
        assert sdu.makeup_ratio == pytest.approx(0.85)

    def test_kmk_parking_matches_sp7_values(self):
        """КМК практические значения — копия СП 7"""
        p = self._make_parking_project("KMK_UZ")
        p.auto_assign_smoke_systems()
        sdu = next(s for s in p.smoke_systems.values()
                   if s.system_type == "smoke_removal")
        assert sdu.norm_per_m2 == 24.0

    def test_switching_norm_after_assignment_does_not_regenerate(self):
        """Переключение норматива не пересоздаёт уже назначенные системы.
        Дефолты применяются только при следующем auto_assign."""
        p = self._make_parking_project("SP7_RU")
        p.auto_assign_smoke_systems()
        original_norm = next(iter(p.smoke_systems.values())).norm_per_m2
        p.params.smoke_norm = "NFPA_92"
        # Системы остались с прежними значениями (до явного пересоздания)
        assert next(iter(p.smoke_systems.values())).norm_per_m2 == original_norm
