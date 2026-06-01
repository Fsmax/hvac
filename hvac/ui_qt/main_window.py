# -*- coding: utf-8 -*-
"""Главное окно: топбар + sidebar + центр (с чек-листом) + статусбар.

Центральная область — QStackedWidget; каждый пункт sidebar открывает свою
панель. Чек-лист справа всегда виден.
"""
from __future__ import annotations

from functools import partial
from pathlib import Path
from typing import Dict

from PySide6.QtCore import QTimer
from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtWidgets import (
    QApplication, QHBoxLayout, QLabel, QMainWindow, QMessageBox,
    QStackedWidget, QStatusBar, QVBoxLayout, QWidget,
)

from hvac.io_json import load_project, save_project
from hvac.project import HVACProject
from hvac.ui_qt import settings as user_settings
from hvac.ui_qt.bridge import ProjectBridge
from hvac.ui_qt.commands import Command, CommandRegistry
from hvac.ui_qt.export_center import ExportCenter
from hvac.ui_qt.panels.calculation_panel import CalculationPanel
from hvac.ui_qt.panels.charts_panel import ChartsPanel
from hvac.ui_qt.panels.constructions_panel import ConstructionsPanel
from hvac.ui_qt.panels.data_panel import DataPanel
from hvac.ui_qt.panels.equipment_panel import EquipmentPanel
from hvac.ui_qt.panels.engineering_panel import EngineeringPanel
from hvac.ui_qt.panels.extensions_panel import ExtensionsPanel
from hvac.ui_qt.panels.problems_panel import ProblemsPanel
from hvac.ui_qt.panels.room_equipment_panel import RoomEquipmentPanel
from hvac.ui_qt.panels.smoke_panel import SmokePanel
from hvac.ui_qt.panels.spaces_panel import SpacesPanel
from hvac.ui_qt.panels.ventilation_panel import VentilationPanel
from hvac.ui_qt.panels.welcome import WelcomePanel
from hvac.ui_qt.panels.zones_panel import ZonesPanel
from hvac.ui_qt.theme import Theme, apply_theme, current_theme
from hvac.ui_qt.widgets.checklist import ChecklistPanel
from hvac.ui_qt.widgets.palette import CommandPalette
from hvac.ui_qt.widgets.sidebar import Sidebar, SidebarItem
from hvac.ui_qt.widgets.topbar import TopBar


from hvac.i18n import t as _t, on_language_change


def _build_sidebar_items():
    """Строит список SidebarItem с локализованными подписями."""
    return [
        SidebarItem("welcome",        "🏠", _t("sidebar.home")),
        SidebarItem("data",           "📂", _t("sidebar.data")),
        SidebarItem("spaces",         "🏢", _t("sidebar.spaces")),
        SidebarItem("constructions",  "🧱", _t("sidebar.constructions")),
        SidebarItem("calculation",    "🌡",  _t("sidebar.calculation")),
        SidebarItem("ventilation",    "💨", _t("sidebar.ventilation")),
        SidebarItem("zones",          "🗺",  _t("sidebar.zones")),
        SidebarItem("equipment",      "⚙",  _t("sidebar.equipment")),
        SidebarItem("room_equipment", "🔧", _t("sidebar.room_equipment")),
        SidebarItem("smoke",          "🔥", _t("sidebar.smoke")),
        SidebarItem("charts",         "📊", _t("sidebar.charts")),
        SidebarItem("extensions",     "⚡", _t("sidebar.extensions")),
        SidebarItem("engineering",    "🔬", _t("sidebar.engineering")),
        SidebarItem("problems",       "⚠", _t("sidebar.problems")),
    ]


# Совместимость со старым именем — используется в импортах.
SIDEBAR_ITEMS = _build_sidebar_items()


class MainWindow(QMainWindow):
    """Главное окно приложения."""

    def __init__(self, project: HVACProject):
        super().__init__()
        self.project = project
        self.bridge = ProjectBridge(project, self)
        self.commands = CommandRegistry()
        self.cmd_palette: CommandPalette | None = None
        self._dirty = False
        # Глобальные actions (зарегистрированные через addAction для shortcut'ов).
        # Хранятся отдельно, чтобы их можно было корректно снять при
        # пересоздании меню после смены языка — иначе остаются висеть
        # на главном окне и shortcut'ы дублируются.
        self._global_actions: list[QAction] = []

        self.setWindowTitle("HVAC Calculator")
        self.resize(1480, 920)
        self.setMinimumSize(1100, 700)

        self._build_ui()
        self._register_commands()
        self._build_menu()
        self._wire_signals()
        self._setup_autosave()

        self.sidebar.select("welcome")
        self._refresh_topbar()

        # Подписаться на смену языка — обновляем меню, команды, статусбар.
        # Раньше при switch на UZ всё это оставалось на старом языке.
        self._unsub_lang = on_language_change(
            lambda _code: self._apply_translations())

    # ---------- UI ----------
    def _build_ui(self) -> None:
        central = QWidget()
        self.setCentralWidget(central)
        outer = QVBoxLayout(central)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # Топбар
        self.topbar = TopBar()
        outer.addWidget(self.topbar)

        # Sidebar + контент + checklist
        body = QHBoxLayout()
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(0)
        outer.addLayout(body, stretch=1)

        self.sidebar = Sidebar(SIDEBAR_ITEMS)
        body.addWidget(self.sidebar)

        self.stack = QStackedWidget()
        body.addWidget(self.stack, stretch=1)

        self._panels: Dict[str, QWidget] = {}
        self._build_panels()

        # Правый dock — чек-лист (создаём ПОСЛЕ _build_panels,
        # т.к. его navigate-обработчик использует sidebar.select)
        self.checklist = ChecklistPanel(
            self.project, self.bridge, navigate=self._navigate_to)
        body.addWidget(self.checklist)

        # Статусбар
        self.setStatusBar(self._build_statusbar())

    def _build_panels(self) -> None:
        welcome = WelcomePanel()
        welcome.openProject.connect(self._action_open_project)
        welcome.loadCsv.connect(self._goto_data)
        welcome.newEmpty.connect(self._action_new_empty)
        welcome.fromTemplate.connect(self._action_from_template)
        self._register_panel("welcome", welcome)

        self._register_panel("data",
                             DataPanel(self.project, self.bridge))
        self._register_panel("spaces",
                             SpacesPanel(self.project, self.bridge))
        self._register_panel("calculation",
                             CalculationPanel(self.project, self.bridge))
        self._register_panel("charts",
                             ChartsPanel(self.project, self.bridge))
        self._register_panel("constructions",
                             ConstructionsPanel(self.project, self.bridge))
        self._register_panel("ventilation",
                             VentilationPanel(self.project, self.bridge))
        self._register_panel("zones",
                             ZonesPanel(self.project, self.bridge))
        self._register_panel("equipment",
                             EquipmentPanel(self.project, self.bridge))
        self._register_panel("smoke",
                             SmokePanel(self.project, self.bridge))
        self._register_panel("extensions",
                             ExtensionsPanel(self.project, self.bridge))
        self._register_panel("room_equipment",
                             RoomEquipmentPanel(self.project, self.bridge))
        self._register_panel("engineering",
                             EngineeringPanel(self.project, self.bridge))
        self._register_panel("problems",
                             ProblemsPanel(self.project, self.bridge,
                                           navigate=self._navigate_to_space))

    def _register_panel(self, key: str, widget: QWidget) -> None:
        self._panels[key] = widget
        self.stack.addWidget(widget)

    def _panel_title(self, key: str) -> str:
        for item in SIDEBAR_ITEMS:
            if item.key == key:
                return item.tooltip
        return key

    def _build_statusbar(self) -> QStatusBar:
        bar = QStatusBar(self)
        self.status_left = QLabel(_t("status.ready"))
        self.status_right = QLabel("")
        self.status_right.setProperty("role", "muted")
        bar.addWidget(self.status_left, 1)
        bar.addPermanentWidget(self.status_right)
        return bar

    # ---------- Меню + команды ----------
    def _register_commands(self) -> None:
        cmds = self.commands
        cat_nav  = _t("cmd.cat.nav")
        cat_file = _t("cmd.cat.file")
        cat_calc = _t("cmd.cat.calc")
        cat_view = _t("cmd.cat.view")
        go_prefix = _t("cmd.go_prefix")

        # Навигация
        for item in SIDEBAR_ITEMS:
            cmds.add(Command(
                id=f"go.{item.key}",
                title=f"{go_prefix}{item.tooltip}",
                category=cat_nav,
                handler=partial(self._navigate_to, item.key),
            ))

        # Файл
        cmds.add(Command(
            "file.new", _t("cmd.file.new"), cat_file,
            self._action_new_empty, shortcut="Ctrl+N"))
        cmds.add(Command(
            "file.open", _t("cmd.file.open"), cat_file,
            self._action_open_project, shortcut="Ctrl+O"))
        cmds.add(Command(
            "file.csv", _t("cmd.file.csv"), cat_file,
            self._action_load_csv, shortcut="Ctrl+I"))
        cmds.add(Command(
            "file.save", _t("cmd.file.save"), cat_file,
            self._action_save, shortcut="Ctrl+S"))
        cmds.add(Command(
            "file.export", _t("cmd.file.export"), cat_file,
            self._action_export, shortcut="Ctrl+E"))
        cmds.add(Command(
            "file.quit", _t("cmd.file.quit"), cat_file,
            self.close, shortcut="Ctrl+Q"))

        # Расчёт
        cmds.add(Command(
            "calc.heat", _t("cmd.calc.heat"), cat_calc,
            self._action_recalc, shortcut="F5"))
        cmds.add(Command(
            "calc.vent", _t("cmd.calc.vent"), cat_calc,
            lambda: self._panels["calculation"]._run_vent()))
        cmds.add(Command(
            "calc.ahu", _t("cmd.calc.ahu"), cat_calc,
            lambda: self._panels["calculation"]._run_ahu()))
        cmds.add(Command(
            "calc.all", _t("cmd.calc.all"), cat_calc,
            lambda: self._panels["calculation"]._run_all()))

        # Вид
        cmds.add(Command(
            "view.theme", _t("cmd.view.theme"), cat_view,
            self._action_toggle_theme, shortcut="Ctrl+T"))
        cmds.add(Command(
            "view.palette", _t("cmd.view.palette"), cat_view,
            self._open_palette, shortcut="Ctrl+K"))
        cmds.add(Command(
            "view.lang.ru", _t("cmd.view.lang_ru"), cat_view,
            lambda: self._action_set_language("ru")))
        cmds.add(Command(
            "view.lang.uz", _t("cmd.view.lang_uz"), cat_view,
            lambda: self._action_set_language("uz")))

    def _build_menu(self) -> None:
        mb = self.menuBar()
        file_menu = mb.addMenu(_t("menu_bar.file"))

        for cmd_id in ("file.new", "file.open", "file.csv"):
            self._add_cmd_action(file_menu, cmd_id)
        file_menu.addSeparator()
        for cmd_id in ("file.save", "file.export"):
            self._add_cmd_action(file_menu, cmd_id)
        file_menu.addSeparator()

        self.recent_menu = file_menu.addMenu(_t("menu.file.recent"))
        self._refresh_recent()
        file_menu.addSeparator()
        self._add_cmd_action(file_menu, "file.quit")

        view_menu = mb.addMenu(_t("menu_bar.view"))
        self._add_cmd_action(view_menu, "view.palette")
        self._add_cmd_action(view_menu, "view.theme")
        view_menu.addSeparator()
        self._build_language_submenu(view_menu)

        calc_menu = mb.addMenu(_t("menu_bar.calc"))
        for cmd_id in ("calc.heat", "calc.vent", "calc.ahu", "calc.all"):
            self._add_cmd_action(calc_menu, cmd_id)

    def _build_language_submenu(self, parent_menu) -> None:
        """Подменю «Язык» с переключением RU/UZ."""
        from PySide6.QtGui import QActionGroup
        from hvac.i18n import (
            get_language, supported_languages_with_labels,
        )

        lang_menu = parent_menu.addMenu(_t("menu.lang_submenu"))
        group = QActionGroup(self)
        group.setExclusive(True)
        current = get_language()
        for code, label in supported_languages_with_labels().items():
            act = QAction(label, self, checkable=True)
            act.setChecked(code == current)
            act.setData(code)
            group.addAction(act)
            lang_menu.addAction(act)
            act.triggered.connect(
                lambda _checked=False, c=code: self._action_set_language(c))

    def _action_set_language(self, code: str) -> None:
        """Меняет язык интерфейса вживую (без перезапуска).

        set_language() уведомит подписчиков, и _apply_translations
        отработает автоматически (см. подписку в __init__). Здесь только
        сохраняем выбор и показываем подтверждающее сообщение.
        """
        from hvac.i18n import set_language as _set, get_language
        if get_language() == code:
            return
        cfg = user_settings.load()
        cfg["language"] = code
        user_settings.save(cfg)
        _set(code)
        # status сообщение уже на новом языке (set_language переключил)
        self.statusBar().showMessage(_t("status.lang_switched"), 4000)

    def _action_toggle_language(self) -> None:
        """Переключатель RU ⇄ UZ для кнопки на топбаре."""
        from hvac.i18n import get_language
        current = get_language()
        new = "uz" if current == "ru" else "ru"
        self._action_set_language(new)

    def _apply_translations(self) -> None:
        """Применяет текущий язык ко всем известным виджетам без
        перезапуска приложения.

        Что обновляется:
        - sidebar: подписи разделов (retranslate)
        - topbar: кнопки и значок языка
        - menu bar: пересоздаётся целиком (команды + actions + recent)
        - status bar: сообщение «Готов»
        - welcome: пересоздаётся (подписи захардкожены при init)
        - все панели с методом retranslate_ui() — вызываются по очереди
        - command palette: сбрасывается, чтобы при следующем открытии
          подгрузила обновлённые titles
        """
        from hvac.i18n import get_language

        # 1. Sidebar
        items = _build_sidebar_items()
        self.sidebar.retranslate(items)

        # 2. TopBar
        self.topbar.retranslate()
        self.topbar.set_language_label(get_language())

        # 3. MenuBar: снять старые global actions, очистить меню,
        # пересоздать команды и меню с новыми переводами.
        for act in self._global_actions:
            try:
                self.removeAction(act)
            except RuntimeError:
                pass  # actions уже удалены при clear()
        self._global_actions.clear()
        self.menuBar().clear()
        self.commands = CommandRegistry()
        self._register_commands()
        self._build_menu()

        # 4. Status bar — обновляем дефолтное «Готов» (но не затираем
        # сообщение от пользователя, если оно есть и не дефолтное).
        if self.status_left.text() in (_t("status.ready"), "Готов", "Tayyor"):
            self.status_left.setText(_t("status.ready"))

        # 5. Welcome — пересоздаём, его подписи задаются в __init__
        try:
            old = self._panels.get("welcome")
            if old is not None:
                from hvac.ui_qt.panels.welcome import WelcomePanel
                new_welcome = WelcomePanel()
                new_welcome.openProject.connect(self._action_open_project)
                new_welcome.loadCsv.connect(self._goto_data)
                new_welcome.newEmpty.connect(self._action_new_empty)
                new_welcome.fromTemplate.connect(
                    self._action_from_template)
                idx = self.stack.indexOf(old)
                if idx >= 0:
                    self.stack.removeWidget(old)
                    old.deleteLater()
                self.stack.insertWidget(idx, new_welcome)
                self._panels["welcome"] = new_welcome
                if (self.sidebar._buttons.get("welcome")
                        and self.sidebar._buttons["welcome"].isChecked()):
                    self.stack.setCurrentWidget(new_welcome)
        except Exception:
            import traceback
            traceback.print_exc()

        # 6. Остальные панели — у тех, кто реализовал retranslate_ui().
        # Безопасно: если метод не определён, просто пропускаем.
        for key, panel in self._panels.items():
            if key == "welcome":
                continue
            fn = getattr(panel, "retranslate_ui", None)
            if callable(fn):
                try:
                    fn()
                except Exception:
                    import traceback
                    traceback.print_exc()

        # 7. Command palette — следующее открытие создаст новую с
        # актуальным CommandRegistry.
        self.cmd_palette = None

    def _add_cmd_action(self, menu, cmd_id: str) -> None:
        cmd = self.commands.find(cmd_id)
        if not cmd:
            return
        act = QAction(cmd.title, self)
        if cmd.shortcut:
            act.setShortcut(QKeySequence(cmd.shortcut))
        act.triggered.connect(cmd.handler)
        menu.addAction(act)
        # Регистрируем shortcut на главное окно тоже, чтобы работало
        # из любой панели (Ctrl+K, F5). Сохраняем ссылку в _global_actions
        # чтобы корректно снять при пересборке меню после смены языка.
        if cmd.shortcut:
            self.addAction(act)
            self._global_actions.append(act)

    # ---------- Сигналы ----------
    def _wire_signals(self) -> None:
        self.sidebar.selected.connect(self._on_sidebar_selected)
        self.topbar.recalcRequested.connect(self._action_recalc)
        self.topbar.saveRequested.connect(self._action_save)
        self.topbar.exportRequested.connect(self._action_export)
        self.topbar.themeToggleRequested.connect(self._action_toggle_theme)
        self.topbar.languageToggleRequested.connect(
            self._action_toggle_language)
        # Установим текущую иконку темы
        self.topbar.set_theme_icon(current_theme() == Theme.DARK)
        # Установим текущий язык на кнопке-переключателе
        from hvac.i18n import get_language
        self.topbar.set_language_label(get_language())
        self.topbar.retranslate()

        self.bridge.dataLoaded.connect(self._on_data_loaded)
        self.bridge.projectLoaded.connect(self._on_data_loaded)
        self.bridge.calculationDone.connect(self._on_calculation_done)
        self.bridge.dirtyChanged.connect(self._on_dirty_changed)
        # Топбар должен обновляться при любых правках имени/города/методики,
        # т.к. эти правки сейчас не имеют отдельного события.
        self.bridge.dirtyChanged.connect(self._refresh_topbar)
        self.bridge.spacesChanged.connect(self._refresh_topbar)
        self.bridge.statusMessage.connect(
            lambda text, ms: self.statusBar().showMessage(text, ms)
        )

    # ---------- Реакции ----------
    def _on_sidebar_selected(self, key: str) -> None:
        widget = self._panels.get(key)
        if widget is not None:
            self.stack.setCurrentWidget(widget)

    def _navigate_to(self, key: str) -> None:
        self.sidebar.select(key)
        self._on_sidebar_selected(key)

    def _navigate_to_space(self, space_id: str) -> None:
        """Переход к помещению в разделе «Помещения» (из панели «Проблемы»)."""
        self._navigate_to("spaces")
        panel = self._panels.get("spaces")
        if hasattr(panel, "select_space"):
            panel.select_space(space_id)

    def _on_data_loaded(self) -> None:
        self._refresh_topbar()
        n = len(self.project.spaces)
        self.status_left.setText(_t("status.loaded_spaces").format(n=n))
        self._dirty = False
        self._update_title()
        if n > 0 and self.stack.currentWidget() is self._panels["welcome"]:
            self._navigate_to("spaces")

    def _on_calculation_done(self) -> None:
        total_kw = sum(s.heat_loss_w for s in self.project.spaces) / 1000.0
        cool_kw = sum(s.heat_gain_w for s in self.project.spaces) / 1000.0
        self.status_right.setText(
            _t("status.kw_summary").format(h=total_kw, c=cool_kw)
        )
        self.status_left.setText(_t("status.calc_done"))

    def _on_dirty_changed(self, dirty: bool) -> None:
        self._dirty = bool(dirty)
        self._update_title()

    def _update_title(self) -> None:
        name = self.project.params.project_name or "HVAC Calculator"
        prefix = "● " if self._dirty else ""
        self.setWindowTitle(f"{prefix}{name} — HVAC Calculator")

    def _refresh_topbar(self, *_args) -> None:
        # Пилюли отражают текущие параметры независимо от наличия помещений:
        # пустой проект с именем «Жилой комплекс» — это уже проект.
        p = self.project
        self.topbar.set_project_name(p.params.project_name or "")
        self.topbar.set_city(p.params.city or "")
        self.topbar.set_methodology(p.params.methodology)

    # ---------- Recent files ----------
    def _refresh_recent(self) -> None:
        self.recent_menu.clear()
        recent = user_settings.load().get("recent", [])
        if not recent:
            act = QAction(_t("recent.empty"), self)
            act.setEnabled(False)
            self.recent_menu.addAction(act)
            return
        for path in recent:
            act = QAction(path, self)
            act.triggered.connect(lambda _=False, p=path: self._open_recent(p))
            self.recent_menu.addAction(act)

    def _open_recent(self, path: str) -> None:
        if not Path(path).exists():
            QMessageBox.warning(
                self, _t("dialog.file_not_found.title"),
                _t("dialog.file_not_found.body").format(path=path))
            return
        try:
            load_project(self.project, path)
            self.project.emit("project_loaded")
            user_settings.push_recent(path)
            self._refresh_recent()
        except Exception as e:
            QMessageBox.critical(self, _t("dialog.error.title"), str(e))

    # ---------- Auto-save ----------
    def _setup_autosave(self) -> None:
        cfg = user_settings.load()
        if not cfg.get("autosave_enabled", True):
            return
        minutes = max(1, int(cfg.get("autosave_interval_min", 5)))
        self._autosave_timer = QTimer(self)
        self._autosave_timer.setInterval(minutes * 60 * 1000)
        self._autosave_timer.timeout.connect(self._autosave_tick)
        self._autosave_timer.start()

    def _autosave_tick(self) -> None:
        # Сохраняем пустой проект тоже, если он dirty: пользователь мог
        # настроить параметры / каталог / системы до загрузки помещений.
        if not self._dirty:
            return
        from datetime import datetime
        user_settings._ensure_dir()  # type: ignore[attr-defined]
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        name = (self.project.params.project_name or "project").replace(" ", "_")
        path = user_settings.autosave_dir() / f"{name}_{ts}.hvac.json"
        try:
            save_project(self.project, str(path), force_self_contained=True)
            self.statusBar().showMessage(
                _t("status.autosave_done").format(name=path.name), 3000)
        except Exception as e:
            self.statusBar().showMessage(
                _t("status.autosave_error").format(err=e), 4000)

    # ---------- Действия ----------
    def _goto_data(self) -> None:
        self._navigate_to("data")

    def _action_new_empty(self) -> None:
        if self._dirty and self.project.spaces:
            ok = QMessageBox.question(
                self, _t("dialog.new_project.title"),
                _t("dialog.unsaved.body"),
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
            if ok != QMessageBox.Yes:
                return
        self.project.new_empty_project()
        self._goto_data()
        self._dirty = False
        self._update_title()
        self._refresh_topbar()

    def _action_from_template(self) -> None:
        """Создание проекта из типового шаблона здания."""
        if self._dirty and self.project.spaces:
            ok = QMessageBox.question(
                self, _t("dialog.new_project.title"),
                _t("dialog.unsaved.body"),
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
            if ok != QMessageBox.Yes:
                return
        from hvac.ui_qt.widgets.template_dialog import TemplateDialog
        from hvac.templates import apply_template
        dlg = TemplateDialog(self, default_city=self.project.params.city
                              or "Ташкент")
        if dlg.exec() != dlg.Accepted:
            return
        if dlg.template is None:
            return
        n = apply_template(self.project, dlg.template,
                            project_name=dlg.project_name,
                            city=dlg.city)
        self._dirty = True
        self._refresh_topbar()
        self._update_title()
        self.statusBar().showMessage(
            _t("status.template_applied").format(
                title=dlg.template.title, n=n), 6000)
        self._navigate_to("spaces")

    def _action_open_project(self) -> None:
        self._goto_data()
        panel = self._panels.get("data")
        if isinstance(panel, DataPanel):
            panel._open_project()  # noqa: SLF001

    def _action_load_csv(self) -> None:
        self._goto_data()

    def _action_save(self) -> None:
        panel = self._panels.get("data")
        if isinstance(panel, DataPanel):
            panel._save_project()  # noqa: SLF001
        else:
            self._goto_data()

    def _action_export(self) -> None:
        if not self.project.spaces:
            QMessageBox.information(
                self, _t("dialog.no_data.title"),
                _t("dialog.no_data.body"))
            return
        dlg = ExportCenter(self.project, self)
        dlg.exec()

    def _action_recalc(self) -> None:
        if not self.project.spaces:
            self.statusBar().showMessage(_t("status.no_data_for_calc"), 3000)
            return
        panel = self._panels.get("calculation")
        if isinstance(panel, CalculationPanel):
            panel._run_heat()  # noqa: SLF001
        else:
            self.project.recalculate()

    def _action_toggle_theme(self) -> None:
        new_theme = Theme.LIGHT if current_theme() == Theme.DARK else Theme.DARK
        app = QApplication.instance()
        if isinstance(app, QApplication):
            apply_theme(app, new_theme)
        self.topbar.set_theme_icon(new_theme == Theme.DARK)
        cfg = user_settings.load()
        cfg["theme"] = new_theme.value
        user_settings.save(cfg)

    def _open_palette(self) -> None:
        if self.cmd_palette is None:
            self.cmd_palette = CommandPalette(self.commands, self)
        self.cmd_palette.show_at(self)

    # ---------- Закрытие ----------
    def closeEvent(self, event) -> None:
        if self._dirty and self.project.spaces:
            ans = QMessageBox.question(
                self, _t("dialog.quit.title"),
                _t("dialog.unsaved_close.body"),
                QMessageBox.Save | QMessageBox.Discard | QMessageBox.Cancel,
                QMessageBox.Cancel,
            )
            if ans == QMessageBox.Cancel:
                event.ignore()
                return
            if ans == QMessageBox.Save:
                self._action_save()
        event.accept()
