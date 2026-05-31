# -*- coding: utf-8 -*-
"""Smoke-тест PDF-экспорта: проверяет, что пояснительная записка
формируется без ошибок на насыщенном проекте. Страховка для типизации
io_pdf. Пропускается, если reportlab недоступен."""
import pytest

from hvac.project import HVACProject
from hvac.models import Space

pytest.importorskip("reportlab")
from hvac.io_pdf import export_to_pdf


def _rich_project() -> HVACProject:
    p = HVACProject()
    p.params.apply_city("Ташкент")
    for i in range(6):
        sp = Space(
            space_id=f"r{i}", number=f"B01-{i:03d}",
            name="Офис" if i % 2 else "Санузел",
            level="L1" if i < 3 else "L2",
            area_m2=25, volume_m3=75, height_m=3,
            t_in_heat=20, t_in_cool=24, occupancy_people=2,
            heat_loss_w=1800 + 150 * i, heat_gain_w=2500 + 200 * i,
            heat_gain_sensible_w=1800 + 150 * i,
        )
        p.spaces.append(sp)
        p._space_by_id[sp.space_id] = sp

    for fn in (
        p.calculate_ventilation, p.auto_assign_zones, p.calculate_ahu_loads,
        p.auto_assign_smoke_systems, p.calculate_smoke_loads, p.calculate_dhw,
        p.calculate_energy_passport, p.check_condensation_risk, p.size_ducts,
        p.size_pipes, p.size_cooling_pipes,
    ):
        fn()
    p.build_vrf_systems(group_by="all", indoor_family="Кассетный")
    return p


def test_export_pdf_produces_valid_file(tmp_path):
    out = tmp_path / "report.pdf"
    export_to_pdf(_rich_project(), str(out))
    assert out.exists()
    data = out.read_bytes()
    assert data[:4] == b"%PDF"
    assert len(data) > 2000  # непустой документ
