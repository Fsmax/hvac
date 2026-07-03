# -*- coding: utf-8 -*-
"""Тесты модуля dhw — расчёт ГВС по СП 30.13330."""

import unittest

from hvac.dhw import (
    DHWSystem, DHWDemand, DHW_NORMS, calculate_space_demand,
    aggregate_to_system, power_for_volume,
    WATER_SPECIFIC_HEAT_PER_M3_WH_K, T_HOT_DEFAULT_C, T_COLD_WINTER_C,
)
from hvac.models import Space


def make_space(room_type, n_people=2, area=30.0, **kw):
    """Утилита: создать Space с минимумом полей."""
    sp = Space(
        space_id="t1", number="101", name="Test", level="L1",
        area_m2=area, volume_m3=area * 3, room_type=room_type,
        occupancy_people=n_people, **kw,
    )
    return sp


class TestNorms(unittest.TestCase):

    def test_residential_has_norm(self):
        n = DHW_NORMS["Жилая комната"]
        self.assertEqual(n.norm_unit, "person")
        self.assertEqual(n.q_daily_l, 105)

    def test_hotel_has_higher_norm(self):
        """Гостиница 140 > жильё 105 л/чел·сут."""
        self.assertGreater(DHW_NORMS["Гостиничный номер"].q_daily_l,
                           DHW_NORMS["Жилая комната"].q_daily_l)

    def test_office_low_norm(self):
        """Офис 7 л/чел·сут (только умывальники)."""
        self.assertEqual(DHW_NORMS["Офис"].q_daily_l, 7)

    def test_no_dhw_for_parking(self):
        """В парковке ГВС не предусмотрен."""
        self.assertEqual(DHW_NORMS["Гараж / автостоянка"].norm_unit, "fixed")
        self.assertEqual(DHW_NORMS["Гараж / автостоянка"].q_daily_l, 0)


class TestCalculateSpaceDemand(unittest.TestCase):

    def test_hotel_room_2_people(self):
        """5 номеров × 2 чел × 140 л = 1400 л/сут per space."""
        sp = make_space("Гостиничный номер", n_people=2)
        d = calculate_space_demand(sp)
        self.assertAlmostEqual(d.v_daily_m3, 0.28, places=2)

    def test_office_3_people(self):
        """3 человека × 7 л = 21 л/сут = 0.021 м³/сут."""
        sp = make_space("Офис", n_people=3, area=25)
        d = calculate_space_demand(sp)
        self.assertAlmostEqual(d.v_daily_m3, 0.021, places=3)

    def test_restaurant_by_area(self):
        """Ресторан: норма по площади 15 л/м²·сут."""
        sp = make_space("Ресторан / зал", n_people=10, area=80)
        d = calculate_space_demand(sp)
        # 80 м² × 15 л = 1200 л = 1.2 м³
        self.assertAlmostEqual(d.v_daily_m3, 1.2, places=2)

    def test_parking_zero(self):
        """Парковка → 0."""
        sp = make_space("Гараж / автостоянка")
        d = calculate_space_demand(sp)
        self.assertEqual(d.v_daily_m3, 0)


class TestPowerCalculation(unittest.TestCase):

    def test_power_for_volume(self):
        """1 м³/ч × Δt=55 К → 63 965 Вт ≈ 64 кВт.
        c_p × ρ × Δt = 1163 × 1 × 55 = 63 965 Вт"""
        q = power_for_volume(1.0, 55.0)
        self.assertAlmostEqual(q, 63965, delta=50)

    def test_power_scales_linearly(self):
        q1 = power_for_volume(1.0, 55.0)
        q2 = power_for_volume(2.0, 55.0)
        self.assertAlmostEqual(q2 / q1, 2.0, places=2)


class TestAggregateToSystem(unittest.TestCase):

    def test_aggregation_sums_volumes(self):
        demands = [
            DHWDemand(space_id=str(i), space_number=f"R{i}", space_name="r",
                      room_type="Гостиничный номер", base_unit="person",
                      base_qty=2, v_daily_m3=0.28, v_hourly_m3=0.024)
            for i in range(5)
        ]
        sys = DHWSystem(name="Test")
        aggregate_to_system(demands, sys)
        self.assertAlmostEqual(sys.v_daily_total_m3, 1.4, places=2)
        self.assertEqual(sys.n_consumers, 5)

    def test_power_with_circulation(self):
        """С циркуляцией мощность выше пиковой."""
        demands = [DHWDemand(space_id="1", space_number="1", space_name="x",
                             room_type="Гостиничный номер", base_unit="person",
                             base_qty=10, v_daily_m3=1.4, v_hourly_m3=0.12)]
        sys = DHWSystem(name="Test", has_circulation=True,
                        circulation_loss_fraction=0.15)
        aggregate_to_system(demands, sys)
        self.assertGreater(sys.q_with_circulation_w, sys.q_peak_w)
        # 15% надбавки
        ratio = sys.q_with_circulation_w / sys.q_peak_w
        self.assertAlmostEqual(ratio, 1.15, places=2)

    def test_efficiency_increases_heater_size(self):
        demands = [DHWDemand(space_id="1", space_number="1", space_name="x",
                             room_type="Гостиничный номер", base_unit="person",
                             base_qty=10, v_daily_m3=1.4, v_hourly_m3=0.12)]
        sys_high = DHWSystem(name="A", efficiency=0.95)
        sys_low = DHWSystem(name="B", efficiency=0.70)
        aggregate_to_system(demands, sys_high)
        aggregate_to_system(demands[:], sys_low)
        # При низком КПД нужно больше пиковой мощности нагревателя
        self.assertGreater(sys_low.q_heater_size_w, sys_high.q_heater_size_w)


class TestByBlockStrategy(unittest.TestCase):
    """Стратегия by_block — отдельная система ГВС на каждый блок здания."""

    @staticmethod
    def _sp(sid, block, room_type, people):
        return Space(space_id=sid, number=sid, name="X", level="L1",
                     area_m2=30.0, volume_m3=90.0, room_type=room_type,
                     occupancy_people=people, block=block)

    def test_by_block_systems(self):
        from hvac.dhw import calculate_project_dhw
        from hvac.project import HVACProject
        p = HVACProject()
        p.spaces = [
            self._sp("1", "A", "Жилая комната", 2),
            self._sp("2", "A", "Жилая комната", 2),
            self._sp("3", "B", "Офис", 5),
            self._sp("4", "", "Жилая комната", 1),
            self._sp("5", "C", "Коридор", 0),     # без потребления ГВС
        ]
        res = calculate_project_dhw(p, system_strategy="by_block")
        # блок C (только коридор) системы не порождает
        self.assertEqual(set(res), {"ГВС-A", "ГВС-B", "ГВС-Прочие"})
        self.assertEqual(res["ГВС-A"].block, "A")
        self.assertEqual(res["ГВС-B"].block, "B")
        self.assertEqual(res["ГВС-Прочие"].block, "")
        # A: 4 чел × 105 л = 0.42 м³/сут; жильё мощнее офиса на 5 чел
        self.assertAlmostEqual(res["ГВС-A"].v_daily_total_m3, 0.42, places=3)
        self.assertGreater(res["ГВС-A"].q_with_circulation_w,
                           res["ГВС-B"].q_with_circulation_w)

    def test_by_block_reuses_existing_system(self):
        from hvac.dhw import calculate_project_dhw
        from hvac.project import HVACProject
        p = HVACProject()
        p.spaces = [self._sp("1", "A", "Жилая комната", 2)]
        keep = DHWSystem(name="ГВС-A", efficiency=0.85, note="ручная")
        p.dhw_systems["ГВС-A"] = keep
        res = calculate_project_dhw(p, system_strategy="by_block")
        self.assertIs(res["ГВС-A"], keep)          # параметры не потеряны
        self.assertEqual(keep.block, "A")
        self.assertGreater(keep.q_with_circulation_w, 0.0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
