# -*- coding: utf-8 -*-
"""Headless-тест выпадающих фильтров (этаж / тип / зона) в разделе
«Вентиляция». Пропускается, если Qt-платформа недоступна."""
import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication  # noqa: E402

from hvac.i18n import t as _t  # noqa: E402
from hvac.models import Space  # noqa: E402
from hvac.project import HVACProject  # noqa: E402


@pytest.fixture(scope="module")
def qapp():
    try:
        return QApplication.instance() or QApplication([])
    except Exception as exc:  # pragma: no cover
        pytest.skip(f"Qt недоступен: {exc}")


def _project():
    p = HVACProject()
    p.params.apply_city("Ташкент")
    rows = [
        ("R1", "L02", "Офис",    "ПВ-1"),
        ("R2", "L12", "Спальня", "ПВ-1"),
        ("R3", "L22", "Офис",    "ПВ-2"),
        ("R4", "L02", "Ванная",  ""),
    ]
    for i, (num, lvl, typ, vent) in enumerate(rows):
        sp = Space(space_id=f"r{i}", number=num, name="x", level=lvl,
                   area_m2=20, volume_m3=60, height_m=3,
                   room_type=typ, t_in_heat=20.0)
        sp.system_ventilation = vent
        p.spaces.append(sp)
        p._space_by_id[sp.space_id] = sp
    return p


def _panel(p):
    from hvac.ui_qt.bridge import ProjectBridge
    from hvac.ui_qt.panels.ventilation_panel import VentilationPanel
    return VentilationPanel(p, ProjectBridge(p))


def _items(combo):
    return [combo.itemText(i) for i in range(combo.count())]


def _visible_numbers(panel):
    out = set()
    for r in range(panel.proxy.rowCount()):
        out.add(panel.proxy.data(panel.proxy.index(r, 0)))
    return out


def test_filter_options_populated(qapp):
    panel = _panel(_project())
    alll = _t("filter.all")
    assert _items(panel.level_filter) == [alll, "L02", "L12", "L22"]
    assert set(_items(panel.type_filter)) == {alll, "Ванная", "Офис", "Спальня"}
    assert set(_items(panel.zone_filter)) == {alll, "ПВ-1", "ПВ-2"}


def test_level_filter(qapp):
    panel = _panel(_project())
    panel.level_filter.setCurrentText("L02")
    assert _visible_numbers(panel) == {"R1", "R4"}


def test_type_filter(qapp):
    panel = _panel(_project())
    panel.type_filter.setCurrentText("Офис")
    assert _visible_numbers(panel) == {"R1", "R3"}


def test_zone_filter_is_vent_system(qapp):
    panel = _panel(_project())
    panel.zone_filter.setCurrentText("ПВ-1")
    assert _visible_numbers(panel) == {"R1", "R2"}


def test_combined_filters(qapp):
    panel = _panel(_project())
    panel.type_filter.setCurrentText("Офис")
    panel.zone_filter.setCurrentText("ПВ-2")
    assert _visible_numbers(panel) == {"R3"}
