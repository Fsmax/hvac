# -*- coding: utf-8 -*-
"""Тесты движка КМК 2.04.05-91 (Узбекистан).

КМК наследует формулы СП 50.13330, но СОХРАНЯЕТ надбавку +0.05 на угловое
помещение (СП 50 её отменил). Поэтому для угловых помещений КМК даёт больше
теплопотерь, для прочих — совпадает с СП 50.
"""

import pytest
from hvac.engine import list_engines, get_engine
from hvac.engine.sp50 import SP50Engine
from hvac.engine.kmk import KMKEngine
from tests.test_engine_sp50 import make_minimal_project


KMK_NAME = "КМК 2.04.05-91 + КМК 2.01.04-18"


class TestRegistration:

    def test_kmk_in_engine_list(self):
        assert KMK_NAME in list_engines()

    def test_get_engine_resolves_kmk(self):
        assert isinstance(get_engine(KMK_NAME), KMKEngine)

    def test_kmk_name_property(self):
        assert KMKEngine().name == KMK_NAME


class TestCornerSupplement:

    def test_non_corner_equals_sp50(self):
        """Не угловое помещение → КМК совпадает с СП 50.13330."""
        project, sp = make_minimal_project()
        sp.is_corner = False
        sp50 = SP50Engine().heat_loss(sp, project)["Через ограждения"]
        kmk = KMKEngine().heat_loss(sp, project)["Через ограждения"]
        assert pytest.approx(kmk, rel=1e-9) == sp50

    def test_corner_adds_005(self):
        """Угловое помещение → КМК добавляет +0.05 к β наружной стены.

        Стена на север: СП 50 β=0.10 → (1.10); КМК β=0.10+0.05 → (1.15).
        """
        project, sp = make_minimal_project()
        sp.is_corner = True
        sp50 = SP50Engine().heat_loss(sp, project)["Через ограждения"]
        kmk = KMKEngine().heat_loss(sp, project)["Через ограждения"]
        assert kmk > sp50
        assert pytest.approx(kmk / sp50, rel=1e-6) == 1.15 / 1.10

    def test_corner_flag_drives_supplement(self):
        """Без флага угловое — надбавки нет, с флагом — есть."""
        project, sp = make_minimal_project()
        engine = KMKEngine()
        sp.is_corner = False
        plain = engine.heat_loss(sp, project)["Через ограждения"]
        sp.is_corner = True
        cornered = engine.heat_loss(sp, project)["Через ограждения"]
        assert cornered > plain


class TestHeatGainInherited:

    def test_heat_gain_matches_sp50(self):
        """Теплопоступления (охлаждение) КМК не отличаются от СП 60."""
        project, sp = make_minimal_project()
        sp.is_corner = True   # на охлаждение угловая надбавка не влияет
        sp50 = SP50Engine().heat_gain(sp, project)["ИТОГО"]
        kmk = KMKEngine().heat_gain(sp, project)["ИТОГО"]
        assert pytest.approx(kmk, rel=1e-9) == sp50
