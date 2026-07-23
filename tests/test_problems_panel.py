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


def test_severity_tokens_exist_in_both_themes():
    """Регрессия: 'info' ссылался на несуществующий токен «muted» →
    KeyError в data() и каскад ошибок модели. Карта серьёзностей обязана
    указывать только на реальные токены обеих тем."""
    from hvac.ui_qt.panels.problems_panel import _SEVERITY_TOKEN
    from hvac.ui_qt.theme import TOKENS, Theme
    for theme in (Theme.DARK, Theme.LIGHT):
        for sev, token in _SEVERITY_TOKEN.items():
            assert token in TOKENS[theme], (
                f"токен {token!r} (severity={sev!r}) отсутствует "
                f"в TOKENS[{theme.value}]")
        # Дефолт в data() для неизвестного severity — тоже реальный токен.
        assert "text_muted" in TOKENS[theme]


def test_foreground_role_for_all_severities(qapp, monkeypatch):
    """info-строка и неизвестный severity не роняют data()."""
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QBrush
    p = HVACProject()
    rows = [
        {"severity": "error", "category": "c", "space_id": "", "msg": "e"},
        {"severity": "warning", "category": "c", "space_id": "", "msg": "w"},
        {"severity": "info", "category": "c", "space_id": "", "msg": "i"},
        {"severity": "strange", "category": "c", "space_id": "", "msg": "?"},
    ]
    monkeypatch.setattr(p, "validate_detailed", lambda: list(rows))
    m = _model(p)
    assert m.rowCount() == len(rows)
    for r in range(m.rowCount()):
        brush = m.data(m.index(r, 0), Qt.ForegroundRole)
        assert isinstance(brush, QBrush)
        assert brush.color().isValid()


def test_coverage_model_surfaces_unassigned_services(qapp):
    from hvac.ui_qt.panels.problems_panel import CoverageModel

    p = _project_with_problem()
    model = CoverageModel(p)
    model.refresh()

    assert model.rowCount() == len(p.spaces)
    assert any(model.has_blockers_at(row)
               for row in range(model.rowCount()))


def test_coverage_double_click_navigates_to_space(qapp):
    from hvac.ui_qt.bridge import ProjectBridge
    from hvac.ui_qt.panels.problems_panel import ProblemsPanel

    p = _project_with_problem()
    captured = []
    panel = ProblemsPanel(p, ProjectBridge(p),
                          navigate=lambda sid: captured.append(sid))

    panel._on_coverage_double_click(panel.coverage_proxy.index(0, 0))

    assert captured


def test_final_export_not_blocked_by_problems(qapp, monkeypatch):
    """Гейт экспорта снят: проблемы модели не мешают выпуску записки."""
    from PySide6.QtWidgets import QMessageBox
    from hvac.ui_qt.export_center import ExportCenter

    dialog = ExportCenter(_project_with_problem())
    dialog.path_edit.setText("")   # пустой путь: до воркера не доходим
    critical, warned = [], []
    monkeypatch.setattr(
        QMessageBox, "critical", lambda *args: critical.append(args))
    monkeypatch.setattr(
        QMessageBox, "warning", lambda *args: warned.append(args))

    dialog._do_export()

    assert not critical            # блокирующего диалога больше нет
    assert warned                  # дошли до проверки пути сохранения
    assert dialog._thread is None
