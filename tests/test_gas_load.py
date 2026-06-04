# -*- coding: utf-8 -*-
"""Тесты расчёта потребности в газе и письма-расчёта для ТУ."""
import pytest

from hvac.project import HVACProject
from hvac.equipment import HeatingSystem
from hvac.gas_load import (
    BoilerGroup, compute_gas_load, gas_boilers_from_project,
    project_efficiency, export_gas_load_pdf, export_project_gas_load_pdf,
    kcal_to_kwh, kwh_to_kcal,
    NATURAL_GAS_LHV_KWH_M3, NATURAL_GAS_LHV_KCAL_M3,
    DEFAULT_EFFICIENCY, DEFAULT_LOAD_FACTOR,
)


# --------------------------------------------------------------------------
# Расчёт
# --------------------------------------------------------------------------

def test_compute_single_group_clean_numbers():
    """B = P/(Qнр·η); суточный = B·24·K; годовой = суточный·D_отоп."""
    r = compute_gas_load(
        [BoilerGroup(power_kw=1000.0, count=1)],
        lhv_kwh_m3=10.0, efficiency=1.0,
        hours_per_day=24.0, load_factor=0.85,
        days_per_month=30.0, heating_days=130.0,
    )
    assert r.boilers[0].hourly_per_unit_m3h == pytest.approx(100.0)
    assert r.hourly_m3h == pytest.approx(100.0)
    assert r.daily_m3day == pytest.approx(2040.0)        # 100·24·0,85
    assert r.monthly_m3month == pytest.approx(61200.0)   # 2040·30
    assert r.annual_m3year == pytest.approx(265200.0)    # 2040·130
    assert r.total_power_kw == pytest.approx(1000.0)


def test_compute_multi_group_sums_hourly():
    r = compute_gas_load(
        [BoilerGroup(power_kw=1000.0, count=1),
         BoilerGroup(power_kw=500.0, count=2)],
        lhv_kwh_m3=10.0, efficiency=1.0,
    )
    # 1×100 + 2×50 = 200 м³/ч
    assert r.hourly_m3h == pytest.approx(200.0)
    assert r.total_power_kw == pytest.approx(2000.0)


def test_compute_uses_lhv_and_efficiency():
    """Меньший Qнр·η → больший расход."""
    base = compute_gas_load([BoilerGroup(2360.0, 2)])
    # дефолты: Qнр=9,30, η=0,92 → ~276 м³/ч на котёл
    assert base.boilers[0].hourly_per_unit_m3h == pytest.approx(
        2360.0 / (NATURAL_GAS_LHV_KWH_M3 * DEFAULT_EFFICIENCY))
    assert base.hourly_m3h == pytest.approx(
        2 * 2360.0 / (NATURAL_GAS_LHV_KWH_M3 * DEFAULT_EFFICIENCY))
    assert base.load_factor == DEFAULT_LOAD_FACTOR


def test_compute_rejects_empty_and_bad_params():
    with pytest.raises(ValueError):
        compute_gas_load([])
    with pytest.raises(ValueError):
        compute_gas_load([BoilerGroup(1000.0, 1)], efficiency=0.0)


def test_kcal_kwh_roundtrip_and_defaults():
    assert kwh_to_kcal(kcal_to_kwh(8000.0)) == pytest.approx(8000.0)
    # дефолтная Qнр в кВт·ч соответствует ровно 8000 ккал/м³
    assert kwh_to_kcal(NATURAL_GAS_LHV_KWH_M3) == pytest.approx(
        NATURAL_GAS_LHV_KCAL_M3)


def test_result_stores_kcal():
    r = compute_gas_load([BoilerGroup(1000.0, 1)])
    assert r.lhv_kcal_m3 == pytest.approx(NATURAL_GAS_LHV_KCAL_M3, rel=1e-3)


def test_overrides_change_consumption():
    """Меньший Qнр и K → меняют суточный расход предсказуемо."""
    boilers = [BoilerGroup(1000.0, 1)]
    r = compute_gas_load(boilers, lhv_kwh_m3=kcal_to_kwh(7000.0),
                         efficiency=0.90, load_factor=0.7,
                         heating_days=200.0)
    expected_hourly = 1000.0 / (kcal_to_kwh(7000.0) * 0.90)
    assert r.hourly_m3h == pytest.approx(expected_hourly)
    assert r.daily_m3day == pytest.approx(expected_hourly * 24 * 0.7)
    assert r.annual_m3year == pytest.approx(r.daily_m3day * 200.0)


# --------------------------------------------------------------------------
# Сбор котлов из проекта
# --------------------------------------------------------------------------

def _project_with_boilers() -> HVACProject:
    p = HVACProject()
    p.params.project_name = "Котельная ОПУ"
    p.heating_systems["Котёл-газ"] = HeatingSystem(
        name="Котёл-газ", system_type="boiler_gas", fuel="gas",
        efficiency=0.92, design_capacity_kw=2360.0, unit_count=2)
    p.heating_systems["Котёл-эл"] = HeatingSystem(
        name="Котёл-эл", system_type="boiler_electric", fuel="electric",
        design_capacity_kw=100.0, unit_count=1)
    # газовый, но без заданной мощности/количества → пропускается
    p.heating_systems["Котёл-авто"] = HeatingSystem(
        name="Котёл-авто", fuel="gas")
    return p


def test_gas_boilers_from_project_filters():
    p = _project_with_boilers()
    boilers = gas_boilers_from_project(p)
    assert len(boilers) == 1
    assert boilers[0].power_kw == 2360.0
    assert boilers[0].count == 2
    assert boilers[0].name == "Котёл-газ"


def test_project_efficiency_from_first_gas_boiler():
    p = _project_with_boilers()
    assert project_efficiency(p) == pytest.approx(0.92)
    assert project_efficiency(HVACProject()) == DEFAULT_EFFICIENCY


# --------------------------------------------------------------------------
# PDF
# --------------------------------------------------------------------------

pytest.importorskip("reportlab")


def test_export_gas_load_pdf_smoke(tmp_path):
    r = compute_gas_load([BoilerGroup(2360.0, 2, name="напольный")])
    out = tmp_path / "gas.pdf"
    export_gas_load_pdf(str(out), r, object_name="Здание ОПУ",
                        signatory_name="Иванов И.И.")
    assert out.exists()
    assert out.read_bytes().startswith(b"%PDF")


def test_export_project_gas_load_pdf(tmp_path):
    p = _project_with_boilers()
    out = tmp_path / "gas_project.pdf"
    result = export_project_gas_load_pdf(p, str(out))
    assert out.exists()
    assert out.read_bytes().startswith(b"%PDF")
    assert result.hourly_m3h > 0


def test_export_project_gas_load_pdf_with_overrides(tmp_path):
    p = _project_with_boilers()
    out = tmp_path / "gas_override.pdf"
    result = export_project_gas_load_pdf(
        p, str(out),
        lhv_kwh_m3=kcal_to_kwh(8500.0), efficiency=0.94,
        load_factor=0.80, heating_days=150.0,
        object_name="Тест-объект", signatory="Главный инженер",
        signatory_name="Петров П.П.",
    )
    assert out.exists()
    assert out.read_bytes().startswith(b"%PDF")
    assert result.efficiency == pytest.approx(0.94)
    assert result.heating_days == 150.0


def test_export_project_gas_load_pdf_no_boilers_raises(tmp_path):
    p = HVACProject()
    out = tmp_path / "gas_empty.pdf"
    with pytest.raises(RuntimeError):
        export_project_gas_load_pdf(p, str(out))


# --------------------------------------------------------------------------
# Export Center: блок параметров и проброс в runner
# --------------------------------------------------------------------------

def test_export_center_gas_params(tmp_path):
    import os
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    pytest.importorskip("PySide6")
    from PySide6.QtWidgets import QApplication
    try:
        QApplication.instance() or QApplication([])
    except Exception as exc:  # pragma: no cover
        pytest.skip(f"Qt-платформа недоступна: {exc}")

    from hvac.ui_qt.export_center import ExportCenter, _gas_load

    p = _project_with_boilers()
    dlg = ExportCenter(p)
    # По умолчанию выбран первый формат — блок газа скрыт.
    # isVisibleTo(dlg) отражает флаг видимости без показа окна.
    assert not dlg.gas_params.isVisibleTo(dlg)

    # Переключаемся на формат газа → блок виден.
    dlg._format_widgets["gas_load"].setChecked(True)
    assert dlg.gas_params.isVisibleTo(dlg)

    # Поля предзаполнены данными проекта.
    assert dlg.gas_object.text() == "Котельная ОПУ"
    assert dlg.gas_eff.value() == pytest.approx(0.92)

    # Меняем параметры и собираем kwargs.
    dlg.gas_lhv.setValue(8500.0)
    dlg.gas_k.setValue(0.80)
    dlg.gas_heating_days.setValue(150)
    params = dlg._collect_gas_params()
    assert params["load_factor"] == pytest.approx(0.80)
    assert params["heating_days"] == 150.0
    assert params["object_name"] == "Котельная ОПУ"

    # Параметры реально доходят до генератора PDF.
    out = tmp_path / "gas_ui.pdf"
    _gas_load(p, str(out), **params)
    assert out.exists()
    assert out.read_bytes().startswith(b"%PDF")
