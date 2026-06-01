# -*- coding: utf-8 -*-
"""Регрессы по аудиту: C1 (дефолтная методика), H-A (спецификация ГВС),
H-B (ключи AHU-нагрузок), H-2 (протяжка U конструкции в элементы)."""

import pytest

from hvac.project import HVACProject
from hvac.models import Space, Construction, BoundaryElement
from hvac.engine import get_engine, list_engines
from hvac.engine.kmk import KMKEngine


def _space(project, sid="1", num="101", level="L1", area=20, supply=0):
    sp = Space(space_id=sid, number=num, name="X", level=level,
               area_m2=area, volume_m3=area * 3, height_m=3,
               room_type="Офис", t_in_heat=20, supply_m3h=supply)
    project.spaces.append(sp)
    project._space_by_id[sid] = sp
    return sp


class TestC1DefaultMethodology:
    """Дефолтная методика должна совпадать с ИМЕНЕМ зарегистрированного
    движка (иначе get_engine молча падает в fallback)."""

    def test_default_methodology_is_registered_engine(self):
        p = HVACProject()
        assert p.params.methodology in list_engines()

    def test_default_resolves_to_kmk(self):
        p = HVACProject()
        assert isinstance(get_engine(p.params.methodology), KMKEngine)

    def test_template_default_is_registered(self):
        from hvac.templates import BuildingTemplate
        assert BuildingTemplate.__dataclass_fields__["default_methodology"].default \
            in list_engines()


class TestHADhwSpecification:
    """Спецификация ГВС должна читать поля DHWSystem (а не DHWDemand)."""

    def test_dhw_spec_non_zero(self):
        from hvac.dhw import DHWSystem
        from hvac.specification import build_specification
        p = HVACProject()
        p.dhw_systems = {"ГВС-1": DHWSystem(
            name="ГВС-1", v_daily_total_m3=2.4, q_peak_w=15000,
            storage_recommended_m3=0.3)}
        spec = build_specification(p)
        dhw = [i for i in spec.items if i.section == "ГВС"]
        assert dhw, "нет позиции ГВС в спецификации"
        td = dhw[0].technical_data
        assert "2.40" in td          # V_сут, м³/сут
        assert "15.0" in td          # Q_пик, кВт
        assert "300" in td           # бак: 0.3 м³ → 300 л
        assert "0.00" not in td      # регресс: было V_сут=0.00


class TestHBAhuLoadKeys:
    """Панель AHU-нагрузок читает те же ключи, что пишет ahu_load."""

    def test_producer_emits_expected_keys(self):
        p = HVACProject()
        p.params.t_out_heating = -15
        _space(p, "1", "B01-001", "B1", 20, supply=1000)
        p.auto_assign_zones(mode="by_prefix")
        loads = p.calculate_ahu_loads()
        info = next(iter(loads.values()))
        # Ключи, которые читает equipment_panel._refresh
        for key in ("q_heater_w", "q_cooler_sens_w", "q_cooler_lat_w",
                    "supply_m3h"):
            assert key in info, f"ahu_loads без ключа {key}"
        # И прежние НЕверные ключи отсутствуют (чтобы панель не вернулась к ним)
        assert "q_heating_w" not in info


class TestH2ConstructionUPropagation:
    """Правка U конструкции должна доходить до el.u_value (apply_constructions)."""

    def test_apply_constructions_refreshes_element_u(self):
        p = HVACProject()
        key = "Стены / Базовая / Test / 200"
        el = BoundaryElement(
            space_id="1", row_type="external_wall", is_exterior=True,
            element_id="W1", category="Стены", family="Базовая",
            type_name="Test", boundary_length_m=4, space_height_m=3,
            approx_area_m2=12, element_area_m2=12, thickness_mm=200,
            function="Наружные", host_element_id="", boundary_space_count=1,
            construction_key=key, orientation="N", u_value=0.5, net_area_m2=12)
        con = Construction(key=key, category="Стены", family="Базовая",
                           type_name="Test", thickness_mm=200, u_value=0.5)
        p.elements = [el]
        p.constructions = {key: con}
        p.apply_constructions()
        assert el.u_value == 0.5
        con.u_value = 0.25            # пользователь правит каталог
        p.apply_constructions()       # вызов из ConstructionsModel._after_change
        assert el.u_value == 0.25
