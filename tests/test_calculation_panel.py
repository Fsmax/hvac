# -*- coding: utf-8 -*-
"""Regression tests for the calculation-panel orchestration."""

from hvac.ui_qt.panels.calculation_panel import CalculationPanel


class _ProjectDouble:
    def __init__(self, recalculate_results=(True, True)):
        self.calls = []
        self.spaces = [object()]
        self._recalculate_results = iter(recalculate_results)

    def recalculate(self, progress=None):
        self.calls.append("heat")
        if progress is not None:
            assert progress(0, 1) is True
        return next(self._recalculate_results)

    def calculate_ventilation(self):
        self.calls.append("ventilation")

    def calculate_ahu_loads(self):
        self.calls.append("ahu")


class _PanelDouble:
    def __init__(self, project):
        self.project = project
        self.result = None

    def _start(self, _status, fn, supports_progress=False):
        assert supports_progress is True
        self.result = fn(lambda _done, _total: True)


def test_run_all_recalculates_heat_after_ventilation():
    project = _ProjectDouble()
    panel = _PanelDouble(project)

    CalculationPanel._run_all(panel)

    assert panel.result is True
    assert project.calls == ["heat", "ventilation", "heat", "ahu"]


def test_run_all_cancellation_on_final_heat_skips_ahu():
    project = _ProjectDouble(recalculate_results=(True, False))
    panel = _PanelDouble(project)

    CalculationPanel._run_all(panel)

    assert panel.result is False
    assert project.calls == ["heat", "ventilation", "heat"]
