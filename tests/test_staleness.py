# -*- coding: utf-8 -*-
"""Тесты StalenessTracker — актуальность расчётных слоёв (F06 ревизии UI).

Правка данных помечает слои с результатами устаревшими; пересчёт слоя
снимает пометку с него и помечает нижележащие (вентиляция зависит от
нагрузок, AHU — от вентиляции). Пропускаются без Qt.
"""
import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication  # noqa: E402

from hvac.models import Space  # noqa: E402
from hvac.project import HVACProject  # noqa: E402
from hvac.ui_qt.bridge import ProjectBridge  # noqa: E402
from hvac.ui_qt.staleness import StalenessTracker  # noqa: E402


@pytest.fixture(scope="module")
def qapp():
    try:
        return QApplication.instance() or QApplication([])
    except Exception as exc:  # pragma: no cover
        pytest.skip(f"Qt-платформа недоступна: {exc}")


def _project(with_loads=True, with_vent=False) -> HVACProject:
    p = HVACProject()
    sp = Space(space_id="s1", number="1", name="Комната", level="L1",
               area_m2=20, volume_m3=60, height_m=3)
    if with_loads:
        sp.heat_loss_w = 500.0
    if with_vent:
        sp.supply_m3h = 60.0
    p.spaces.append(sp)
    p._space_by_id[sp.space_id] = sp
    return p


def _tracker(p):
    bridge = ProjectBridge(p)
    return StalenessTracker(p, bridge), bridge


def test_edit_marks_layers_with_results(qapp):
    p = _project(with_loads=True, with_vent=True)
    tr, bridge = _tracker(p)
    assert tr.stale_layers() == []
    bridge.dataEdited.emit()
    assert tr.stale_layers() == ["loads", "ventilation"]


def test_edit_marks_nothing_without_results(qapp):
    p = _project(with_loads=False, with_vent=False)
    tr, bridge = _tracker(p)
    bridge.dataEdited.emit()
    assert tr.stale_layers() == []


def test_recalc_chain_clears_in_order(qapp):
    p = _project(with_loads=True, with_vent=True)
    tr, bridge = _tracker(p)
    bridge.dataEdited.emit()
    # Пересчёт нагрузок: loads чист, вентиляция остаётся устаревшей
    # (воздушное отопление зависит от нагрузок).
    p.emit("calculation_done")
    assert tr.stale_layers() == ["ventilation"]
    p.emit("ventilation_done", skipped=0)
    assert tr.stale_layers() == []


def test_project_load_resets(qapp):
    p = _project(with_loads=True)
    tr, bridge = _tracker(p)
    bridge.dataEdited.emit()
    assert tr.stale_layers()
    p.emit("project_loaded")
    assert tr.stale_layers() == []


def test_dismiss_keeps_marks_until_next_change(qapp):
    p = _project(with_loads=True)
    tr, bridge = _tracker(p)
    bridge.dataEdited.emit()
    tr.dismiss()
    assert tr.is_dismissed()
    assert tr.stale_layers() == ["loads"]   # пометки не сняты
    bridge.dataEdited.emit()                # уже помечено → dismissed
    assert tr.is_dismissed()                # не сбрасывается без новых слоёв
    p.emit("calculation_done")
    bridge.dataEdited.emit()                # новая пометка → лента снова видна
    assert not tr.is_dismissed()
