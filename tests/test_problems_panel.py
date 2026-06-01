# -*- coding: utf-8 -*-
"""Headless-тесты панели «Проблемы» (ProblemsModel / навигация).

Пропускаются, если Qt-платформа недоступна.
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


def _project_with_problem() -> HVACProject:
    p = HVACProject()
    p.params.apply_city("Ташкент")
    # area_m2 = 0 → validate_detailed даёт error «Геометрия» с space_id.
    bad = Space(space_id="bad", number="B1", name="Битое", level="L1",
                area_m2=0.0, volume_m3=0.0, height_m=3)
    good = Space(space_id="ok", number="G1", name="Норм", level="L1",
                 area_m2=20, volume_m3=60, height_m=3)
    for sp in (bad, good):
        p.spaces.append(sp)
        p._space_by_id[sp.space_id] = sp
    return p


def _model(p):
    from hvac.ui_qt.panels.problems_panel import ProblemsModel
    m = ProblemsModel(p)
    m.refresh()
    return m


def test_model_surfaces_geometry_error(qapp):
    p = _project_with_problem()
    m = _model(p)
    assert m.rowCount() > 0
    # Есть хотя бы одна запись, привязанная к «битому» помещению.
    space_ids = {m.space_id_at(r) for r in range(m.rowCount())}
    assert "bad" in space_ids


def test_counts_has_error(qapp):
    p = _project_with_problem()
    m = _model(p)
    assert m.counts()["error"] >= 1


def test_empty_project_no_rows(qapp):
    p = HVACProject()
    p.params.apply_city("Ташкент")
    m = _model(p)
    # validate_detailed на пустом проекте даёт одну запись «Нет помещений».
    assert m.rowCount() >= 1


def test_navigation_callback_receives_space_id(qapp):
    from hvac.ui_qt.bridge import ProjectBridge
    from hvac.ui_qt.panels.problems_panel import ProblemsPanel
    p = _project_with_problem()
    captured = []
    panel = ProblemsPanel(p, ProjectBridge(p),
                          navigate=lambda sid: captured.append(sid))
    # Находим прокси-строку с привязкой к помещению и эмулируем двойной клик.
    row = None
    for r in range(panel.proxy.rowCount()):
        src = panel.proxy.mapToSource(panel.proxy.index(r, 0))
        if panel.model.space_id_at(src.row()):
            row = r
            break
    assert row is not None
    panel._on_double_click(panel.proxy.index(row, 0))
    assert captured and captured[0]
