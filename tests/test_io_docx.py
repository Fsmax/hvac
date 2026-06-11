# -*- coding: utf-8 -*-
"""Smoke-тест DOCX-экспорта: пояснительная записка формируется без
ошибок на насыщенном проекте (зеркало test_io_pdf). Пропускается,
если python-docx недоступен."""
import zipfile

import pytest

from hvac.models import Space
from hvac.project import HVACProject

pytest.importorskip("docx")
from hvac.io_docx import export_to_docx


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
        p.size_pipes,
    ):
        fn()
    return p


def test_export_docx_produces_valid_file(tmp_path):
    out = tmp_path / "report.docx"
    export_to_docx(_rich_project(), str(out))
    assert out.exists()
    # .docx — это zip с word/document.xml
    with zipfile.ZipFile(out) as z:
        xml = z.read("word/document.xml").decode("utf-8")
    assert "ПОЯСНИТЕЛЬНАЯ ЗАПИСКА" in xml
    assert "Исходные данные" in xml
    assert "Энергетический паспорт" in xml


def test_export_docx_sections_subset(tmp_path):
    out = tmp_path / "short.docx"
    export_to_docx(_rich_project(), str(out),
                   include_sections=["inputs", "heat_loss"])
    with zipfile.ZipFile(out) as z:
        xml = z.read("word/document.xml").decode("utf-8")
    assert "Исходные данные" in xml
    assert "ПОЯСНИТЕЛЬНАЯ ЗАПИСКА" not in xml      # титула нет


def test_export_docx_empty_project(tmp_path):
    """Пустой проект не валит экспорт."""
    p = HVACProject()
    p.params.apply_city("Ташкент")
    out = tmp_path / "empty.docx"
    export_to_docx(p, str(out))
    assert out.exists()
