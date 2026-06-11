# -*- coding: utf-8 -*-
"""Тесты паспортов вентсистем (hvac/io_passport.py).
Пропускаются, если python-docx недоступен."""
import zipfile

import pytest

from hvac.models import Space
from hvac.project import HVACProject

pytest.importorskip("docx")
from hvac.io_passport import export_ventilation_passports


def _project_with_systems() -> HVACProject:
    p = HVACProject()
    p.params.apply_city("Ташкент")
    for i in range(5):
        sp = Space(
            space_id=f"r{i}", number=f"B01-{i:03d}",
            name="Офис" if i % 2 else "Переговорная", level="L1",
            area_m2=25, volume_m3=75, height_m=3,
            t_in_heat=20, t_in_cool=24, occupancy_people=2,
            heat_loss_w=1800, heat_gain_w=2500, heat_gain_sensible_w=1800,
        )
        p.spaces.append(sp)
        p._space_by_id[sp.space_id] = sp
    p.calculate_ventilation()
    p.auto_assign_zones()          # создаёт ventilation_systems
    p.calculate_ahu_loads()
    return p


def test_passports_produce_valid_docx(tmp_path):
    p = _project_with_systems()
    assert p.ventilation_systems, "auto_assign_zones должен создать системы"
    out = tmp_path / "passports.docx"
    n = export_ventilation_passports(p, str(out))
    assert n == len(p.ventilation_systems)
    with zipfile.ZipFile(out) as z:
        xml = z.read("word/document.xml").decode("utf-8")
    assert "ПАСПОРТ" in xml
    assert "Расчётные данные" in xml
    assert "Обслуживаемые помещения" in xml
    # Имя каждой системы попало в документ
    for name in p.ventilation_systems:
        assert name in xml


def test_passports_include_duct_network_data(tmp_path):
    """Если для системы построена сеть — её точка попадает в паспорт."""
    from hvac.duct_network import DuctEdge, DuctNetworkDetailed
    p = _project_with_systems()
    name = next(iter(p.ventilation_systems))
    net = DuctNetworkDetailed(system_name=name)
    net.add_edge(DuctEdge(edge_id="trunk", parent_id="",
                          flow_m3_h=1000, length_m=10, shape="round",
                          diameter_mm=250))
    net.compute()
    p.duct_networks_detailed = {name: net}
    out = tmp_path / "p.docx"
    export_ventilation_passports(p, str(out))
    with zipfile.ZipFile(out) as z:
        xml = z.read("word/document.xml").decode("utf-8")
    assert "Полное давление" in xml


def test_no_systems_raises(tmp_path):
    p = HVACProject()
    p.params.apply_city("Ташкент")
    with pytest.raises(ValueError, match="нет систем"):
        export_ventilation_passports(p, str(tmp_path / "x.docx"))
