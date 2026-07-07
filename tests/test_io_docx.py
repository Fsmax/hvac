# -*- coding: utf-8 -*-
"""Тесты DOCX-экспорта пояснительной записки: подписи норм по профилю
проекта (УзР ШНҚ/КМК либо РФ СП), сквозная нумерация разделов,
актуализация энергопаспорта при экспорте. Пропускается, если
python-docx недоступен."""
import re
import zipfile

import pytest

from hvac.models import Space
from hvac.project import HVACProject

pytest.importorskip("docx")
from docx import Document as DocxDocument          # noqa: E402

from hvac.io_docx import export_to_docx           # noqa: E402


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


def _document_xml(path) -> str:
    with zipfile.ZipFile(path) as z:
        return z.read("word/document.xml").decode("utf-8")


def test_export_docx_produces_valid_file(tmp_path):
    out = tmp_path / "report.docx"
    export_to_docx(_rich_project(), str(out))
    assert out.exists()
    xml = _document_xml(out)
    assert "ПОЯСНИТЕЛЬНАЯ ЗАПИСКА" in xml
    assert "Исходные данные" in xml
    assert "Энергоэффективность здания" in xml
    assert "Таблица воздухообменов по помещениям" in xml
    assert "Теплопотери по помещениям" in xml


def test_export_docx_uz_norm_labels(tmp_path):
    """Профиль УзР (thermal_norm=KMK_UZ, дефолт): записка ссылается на
    ШНҚ/КМК, а не на российские СП; класс СП 50 не печатается."""
    proj = _rich_project()
    assert proj.params.thermal_norm == "KMK_UZ"
    out = tmp_path / "uz.docx"
    export_to_docx(proj, str(out))
    xml = _document_xml(out)
    assert "ШНҚ 2.04.05-22" in xml           # ОВК
    assert "ШНҚ 2.01.01-22" in xml           # климатология
    assert "КМК 2.01.04-18" in xml           # теплотехника
    assert "ШНҚ 2.01.18-24" in xml           # энергоэффективность q_ov
    assert "СП 131.13330" not in xml
    assert "СП 60.13330" not in xml
    assert "КЛАСС ЭНЕРГОЭФФЕКТИВНОСТИ" not in xml
    assert ("СООТВЕТСТВУЕТ ШНҚ 2.01.18-24" in xml
            or "НЕ СООТВЕТСТВУЕТ ШНҚ 2.01.18-24" in xml
            or "не табулирован" in xml)


def test_export_docx_ru_norm_labels(tmp_path):
    """Профиль РФ (thermal_norm=SP_RU): прежние подписи СП и класс."""
    proj = _rich_project()
    proj.params.thermal_norm = "SP_RU"
    out = tmp_path / "ru.docx"
    export_to_docx(proj, str(out))
    xml = _document_xml(out)
    assert "СП 131.13330" in xml
    assert "СП 50.13330" in xml
    assert "КЛАСС ЭНЕРГОЭФФЕКТИВНОСТИ" in xml


def test_export_docx_refreshes_stale_passport(tmp_path):
    """Устаревший энергопаспорт актуализируется при экспорте: цифры
    в записке соответствуют текущим помещениям, а не моменту расчёта."""
    proj = _rich_project()
    stale_q = proj.energy_passport.q_peak_heating_w
    for sp in proj.spaces:
        sp.heat_loss_w *= 3.0
    out = tmp_path / "fresh.docx"
    export_to_docx(proj, str(out))
    fresh_q = proj.energy_passport.q_peak_heating_w
    assert fresh_q == pytest.approx(stale_q * 3.0)
    assert proj.energy_passport.q_peak_heating_w == pytest.approx(
        sum(sp.heat_loss_w for sp in proj.spaces))


def test_export_docx_section_numbering_contiguous(tmp_path):
    """Номера разделов сквозные (1..N) без дыр, даже когда часть
    разделов не печатается (нет данных)."""
    out = tmp_path / "numbered.docx"
    export_to_docx(_rich_project(), str(out))
    doc = DocxDocument(str(out))
    nums = []
    for par in doc.paragraphs:
        if par.style.name.startswith("Heading 1"):
            m = re.match(r"(\d+)\.\s", par.text)
            if m:
                nums.append(int(m.group(1)))
    assert nums, "нет нумерованных заголовков"
    assert nums == list(range(1, len(nums) + 1))


def test_export_docx_empty_equipment_section_skipped(tmp_path):
    """Раздел «Системы оборудования» не печатается пустым."""
    p = HVACProject()
    p.params.apply_city("Ташкент")
    sp = Space(space_id="r1", number="001", name="Офис", level="L1",
               area_m2=25, volume_m3=75, height_m=3, heat_loss_w=1500,
               heat_gain_w=2000)
    p.spaces.append(sp)
    p._space_by_id[sp.space_id] = sp
    out = tmp_path / "noequip.docx"
    export_to_docx(p, str(out))
    xml = _document_xml(out)
    assert "Системы оборудования" not in xml


def test_export_docx_sections_subset(tmp_path):
    out = tmp_path / "short.docx"
    export_to_docx(_rich_project(), str(out),
                   include_sections=["inputs", "heat_loss"])
    xml = _document_xml(out)
    assert "Исходные данные" in xml
    assert "ПОЯСНИТЕЛЬНАЯ ЗАПИСКА" not in xml      # титула нет


def test_export_docx_empty_project(tmp_path):
    """Пустой проект не валит экспорт."""
    p = HVACProject()
    p.params.apply_city("Ташкент")
    out = tmp_path / "empty.docx"
    export_to_docx(p, str(out))
    assert out.exists()
