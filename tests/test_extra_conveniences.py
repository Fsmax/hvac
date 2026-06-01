# -*- coding: utf-8 -*-
"""Headless-тесты дополнительных удобств: сравнение вариантов, пресеты
расхода, drag-drop CSV. Пропускаются, если Qt-платформа недоступна.
"""
import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication  # noqa: E402

from hvac.project import HVACProject  # noqa: E402
from hvac.models import Space  # noqa: E402


@pytest.fixture(scope="module")
def qapp():
    try:
        return QApplication.instance() or QApplication([])
    except Exception as exc:  # pragma: no cover
        pytest.skip(f"Qt-платформа недоступна: {exc}")


def _project(n=3, supply=100.0, ql=1000.0):
    p = HVACProject()
    p.params.apply_city("Ташкент")
    for i in range(n):
        sp = Space(space_id=f"r{i}", number=f"R{i}", name="x", level="L1",
                   area_m2=20, volume_m3=60, height_m=3)
        sp.heat_loss_w = ql
        sp.heat_gain_w = ql * 1.5
        sp.supply_m3h = supply
        sp.exhaust_m3h = supply * 0.8
        p.spaces.append(sp)
        p._space_by_id[sp.space_id] = sp
    return p


# ===================== Сравнение вариантов =====================

def test_comparison_metrics_basic():
    from hvac.ui_qt.panels.comparison_panel import comparison_metrics
    m = comparison_metrics(_project(3, supply=100, ql=1000))
    assert m["n_spaces"] == 3
    assert abs(m["area"] - 60) < 1e-9
    assert abs(m["ql_kw"] - 3.0) < 1e-9
    assert abs(m["supply"] - 300) < 1e-9
    assert abs(m["q_density"] - (3000 / 60)) < 1e-9  # 50 Вт/м²


def test_comparison_metrics_empty():
    from hvac.ui_qt.panels.comparison_panel import comparison_metrics
    p = HVACProject()
    p.params.apply_city("Ташкент")
    m = comparison_metrics(p)
    assert m["n_spaces"] == 0 and m["area"] == 0 and m["q_density"] == 0


def test_comparison_panel_no_other(qapp):
    from hvac.ui_qt.bridge import ProjectBridge
    from hvac.ui_qt.panels.comparison_panel import ComparisonPanel
    panel = ComparisonPanel(_project(), ProjectBridge(_project()))
    assert panel.table.item(0, 2).text() == "—"  # колонка «Сравнение» пуста


def test_comparison_panel_with_other(qapp):
    from hvac.ui_qt.bridge import ProjectBridge
    from hvac.ui_qt.panels.comparison_panel import ComparisonPanel
    cur = _project(3, supply=100, ql=1000)
    other = _project(3, supply=100, ql=2000)  # вдвое больше теплопотери
    panel = ComparisonPanel(cur, ProjectBridge(cur))
    panel._other = other
    panel._other_name = "other.hvac.json"
    panel._refresh()
    # строка ql_kw — индекс 2; current 3.00, other 6.00, Δ +3.00
    assert panel.table.item(2, 1).text().startswith("3")
    assert panel.table.item(2, 2).text().startswith("6")
    assert panel.table.item(2, 3).text().startswith("+")


# ===================== Пресеты расхода =====================

def test_airflow_preset_toilet_by_ach(qapp):
    from hvac.ui_qt.bridge import ProjectBridge
    from hvac.ui_qt.panels.ventilation_panel import (
        VentilationModel, _AIRFLOW_PRESETS, _COL_EXHAUST,
    )
    p = _project(2, supply=0, ql=0)
    for sp in p.spaces:
        sp.exhaust_m3h = 0.0
    m = VentilationModel(p, ProjectBridge(p))
    label_key, col, mode, value = _AIRFLOW_PRESETS[0]  # санузел: exhaust ach 10
    assert col == _COL_EXHAUST and mode == "ach" and value == 10.0
    m.apply_bulk([0, 1], col, mode, value)
    # 10 крат × объём 60 м³ = 600 м³/ч
    assert all(abs(sp.exhaust_m3h - 600.0) < 1e-9 for sp in p.spaces)


def test_airflow_preset_fixed_value(qapp):
    from hvac.ui_qt.bridge import ProjectBridge
    from hvac.ui_qt.panels.ventilation_panel import (
        VentilationModel, _AIRFLOW_PRESETS,
    )
    p = _project(2, supply=0, ql=0)
    m = VentilationModel(p, ProjectBridge(p))
    # «Санузел индивид. — 50 м³/ч вытяжка» (set)
    _key, col, mode, value = next(x for x in _AIRFLOW_PRESETS if x[2] == "set")
    m.apply_bulk([0, 1], col, mode, value)
    assert all(abs(getattr(sp, "exhaust_m3h") - value) < 1e-9 for sp in p.spaces)


# ===================== Drag-drop CSV =====================

def test_dropped_csv_pair(qapp, tmp_path, monkeypatch):
    from hvac.ui_qt.main_window import MainWindow
    p = _project()
    w = MainWindow(p)
    sp = tmp_path / "spaces.csv"
    th = tmp_path / "thermal_all.csv"
    sp.write_text("x", encoding="utf-8")
    th.write_text("x", encoding="utf-8")
    called = {}
    monkeypatch.setattr(p, "load",
                        lambda a, b: called.update(spaces=a, thermal=b))
    w._load_dropped_csv([str(sp), str(th)])
    assert called.get("spaces") == str(sp)
    assert called.get("thermal") == str(th)


def test_dropped_csv_finds_sibling_thermal(qapp, tmp_path, monkeypatch):
    from hvac.ui_qt.main_window import MainWindow
    p = _project()
    w = MainWindow(p)
    sp = tmp_path / "spaces.csv"
    th = tmp_path / "thermal_all.csv"
    sp.write_text("x", encoding="utf-8")
    th.write_text("x", encoding="utf-8")
    called = {}
    monkeypatch.setattr(p, "load",
                        lambda a, b: called.update(spaces=a, thermal=b))
    # дропнули только spaces.csv → должен найтись соседний thermal_all.csv
    w._load_dropped_csv([str(sp)])
    assert called.get("thermal") == str(th)
