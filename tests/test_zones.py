# -*- coding: utf-8 -*-
"""Тесты группировки помещений по зонам/системам."""

import pytest
from hvac.project import HVACProject
from hvac.models import Space


def _add_space(project, sp_id, number, name, level, area, room_type="Офис"):
    sp = Space(space_id=sp_id, number=number, name=name, level=level,
               area_m2=area, volume_m3=area * 3, height_m=3.0,
               room_type=room_type, occupancy_people=2.0)
    project.spaces.append(sp)
    project._space_by_id[sp_id] = sp
    return sp


class TestAutoAssignZones:

    def test_by_prefix(self):
        """По префиксу: B01-001 → Блок B01."""
        project = HVACProject()
        _add_space(project, "1", "B01-001", "Office A", "B1", 20)
        _add_space(project, "2", "B01-002", "Office B", "B1", 30)
        _add_space(project, "3", "B02-001", "Storage", "B2", 50)
        _add_space(project, "4", "OFC-100", "Hotel room", "L02", 25)

        project.auto_assign_zones(mode="by_prefix")

        assert project.spaces[0].system_heating == "Блок B01"
        assert project.spaces[1].system_heating == "Блок B01"
        assert project.spaces[2].system_heating == "Блок B02"
        assert project.spaces[3].system_heating == "Блок OFC"
        # Cooling и ventilation тоже должны быть назначены
        assert project.spaces[0].system_cooling == "Блок B01"
        assert project.spaces[0].system_ventilation == "Блок B01"

    def test_by_level(self):
        project = HVACProject()
        _add_space(project, "1", "B01-001", "Office", "B1 (FFL)", 20)
        _add_space(project, "2", "OFC-100", "Hotel", "L02 (FFL)", 25)
        project.auto_assign_zones(mode="by_level")
        assert "B1" in project.spaces[0].system_heating
        assert "L02" in project.spaces[1].system_heating

    def test_no_overwrite_by_default(self):
        """Без overwrite не перезаписывает существующие назначения."""
        project = HVACProject()
        sp = _add_space(project, "1", "B01-001", "Office", "B1", 20)
        sp.system_heating = "Custom Zone"
        project.auto_assign_zones(mode="by_prefix", overwrite=False)
        # Heating остался Custom Zone
        assert sp.system_heating == "Custom Zone"
        # Cooling и ventilation были пустые → присвоились
        assert sp.system_cooling == "Блок B01"

    def test_overwrite(self):
        project = HVACProject()
        sp = _add_space(project, "1", "B01-001", "Office", "B1", 20)
        sp.system_heating = "Old"
        project.auto_assign_zones(mode="by_prefix", overwrite=True)
        assert sp.system_heating == "Блок B01"


class TestZoneSummary:

    def test_aggregation(self):
        """Σ нагрузки по зонам."""
        project = HVACProject()
        sp1 = _add_space(project, "1", "B01-001", "A", "B1", 20)
        sp2 = _add_space(project, "2", "B01-002", "B", "B1", 30)
        sp3 = _add_space(project, "3", "B02-001", "C", "B2", 50)
        sp1.heat_loss_w = 1000
        sp2.heat_loss_w = 2000
        sp3.heat_loss_w = 3000
        sp1.system_heating = sp2.system_heating = "Блок B01"
        sp3.system_heating = "Блок B02"

        s = project.get_zone_summary("heating")
        assert s["Блок B01"]["q_heating_w"] == 3000
        assert s["Блок B01"]["n_spaces"] == 2
        assert s["Блок B01"]["area_m2"] == 50
        assert s["Блок B02"]["q_heating_w"] == 3000

    def test_unassigned_grouped(self):
        """Помещения без зоны идут в «(не назначено)»."""
        project = HVACProject()
        _add_space(project, "1", "B01-001", "A", "B1", 20)
        s = project.get_zone_summary("heating")
        assert "(не назначено)" in s

    def test_sensible_latent_in_summary(self):
        project = HVACProject()
        sp = _add_space(project, "1", "B01-001", "A", "B1", 20)
        sp.system_cooling = "Блок A"
        sp.heat_gain_sensible_w = 1000
        sp.heat_gain_latent_w = -200  # отрицательная (сухой климат)
        sp.heat_gain_w = 800
        s = project.get_zone_summary("cooling")
        assert s["Блок A"]["q_sensible_w"] == 1000
        assert s["Блок A"]["q_latent_w"] == -200
        assert s["Блок A"]["q_cooling_w"] == 800

    def test_ventilation_summary(self):
        project = HVACProject()
        sp = _add_space(project, "1", "B01-001", "A", "B1", 20)
        sp.system_ventilation = "AHU-1"
        sp.supply_m3h = 500
        sp.exhaust_m3h = 480
        sp.hood_m3h = 100
        s = project.get_zone_summary("ventilation")
        assert s["AHU-1"]["supply_m3h"] == 500
        assert s["AHU-1"]["exhaust_m3h"] == 480
        assert s["AHU-1"]["hood_m3h"] == 100
