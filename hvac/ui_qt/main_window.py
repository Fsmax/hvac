# -*- coding: utf-8 -*-
"""Главное окно: топбар + sidebar + центр (с чек-листом) + статусбар.

Центральная область — QStackedWidget; каждый пункт sidebar открывает свою
панель. Чек-лист справа всегда виден.
"""
from __future__ import annotations

from functools import partial
from pathlib import Path
from typing import Dict

from PySide6.QtCore import QByteArray, Qt, QTimer
from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtWidgets import (
    QApplication, QDialog, QFrame, QHBoxLayout, QLabel, QMainWindow,
    QMessageBox, QPushButton, QSplitter, QStackedWidget, QStatusBar,
    QVBoxLayout, QWidget,
)

from hvac.io_json import load_project, save_project
from hvac.project import HVACProject
from hvac.ui_qt import settings as user_settings
from hvac.ui_qt.bridge import ProjectBridge
from hvac.ui_qt.commands import Command, CommandRegistry
from hvac.ui_qt.export_center import ExportCenter
# Панели «горячего» пути импортируются сразу; остальные — внутри фабрик
# в _build_panels: их модули (matplotlib в графиках/инженерии, тяжёлые
# таблицы) не грузятся, пока раздел не открыт (F18 ревизии UI).
from hvac.ui_qt.panels.calculation_panel import CalculationPanel
from hvac.ui_qt.panels.data_panel import DataPanel
from hvac.ui_qt.panels.problems_panel import ProblemsPanel
from hvac.ui_qt.panels.welcome import WelcomePanel
from hvac.ui_qt.staleness import StalenessTracker
from hvac.ui_qt.theme import Theme, apply_theme, current_theme
from hvac.ui_qt.widgets.checklist import ChecklistPanel
from hvac.ui_qt.widgets.palette import CommandPalette
from hvac.ui_qt.widgets.sidebar import Sidebar, SidebarItem
from hvac.ui_qt.widgets.topbar import TopBar


from hvac.i18n import t as _t, on_language_change


def _build_sidebar_items():
    """Строит список SidebarItem с локализованными подписями.

    Порядок и группы отражают маршрут работы: проект → модель здания →
    расчёты → системы/оборудование → анализ результатов.
    """
    g_project  = _t("sidebar.group.project")
    g_model    = _t("sidebar.group.model")
    g_calc     = _t("sidebar.group.calc")
    g_systems  = _t("sidebar.group.systems")
    g_analysis = _t("sidebar.group.analysis")
    return [
        SidebarItem("welcome",        "🏠", _t("sidebar.home"), g_project),
        SidebarItem("data",           "📂", _t("sidebar.data")),
        SidebarItem("spaces",         "🏢", _t("sidebar.spaces"), g_model),
        SidebarItem("blocks",         "🏗", _t("sidebar.blocks")),
        SidebarItem("constructions",  "🧱", _t("sidebar.constructions")),
        SidebarItem("calculation",    "🌡",  _t("sidebar.calculation"), g_calc),
        SidebarItem("ventilation",    "💨", _t("sidebar.ventilation")),
        SidebarItem("airbalance",     "🔀", _t("sidebar.airbalance")),
        SidebarItem("smoke",          "🔥", _t("sidebar.smoke")),
        SidebarItem("extensions",     "⚡", _t("sidebar.extensions")),
        SidebarItem("systems",        "⚙",  _t("sidebar.systems"), g_systems),
        SidebarItem("equipment",      "🛠", _t("sidebar.equipment")),
        SidebarItem("balance",        "🧮", _t("sidebar.balance")),
        SidebarItem("charts",         "📊", _t("sidebar.charts"), g_analysis),
        SidebarItem("engineering",    "🔬", _t("sidebar.engineering")),
        SidebarItem("comparison",     "⚖", _t("sidebar.comparison")),
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
        self.setAcceptDrops(True)  # перетаскивание .hvac.json / CSV на окно

        self._build_ui()
        self.staleness = StalenessTracker(project, self.bridge, self)
        self.staleness.changed.connect(self._on_staleness_changed)
        self._register_commands()
        self._build_menu()
        self._wire_signals()
        self._setup_autosave()
        self._restore_window_state()

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

        # Лента актуальности: «данные изменены — результаты устарели»
        outer.addWidget(self._build_ribbon())

        # Sidebar + контент + checklist
        body = QHBoxLayout()
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(0)
        outer.addLayout(body, stretch=1)

        collapsed = bool(user_settings.load().get("sidebar_collapsed", False))
        self.sidebar = Sidebar(SIDEBAR_ITEMS, collapsed=collapsed)
        self.sidebar.collapsedChanged.connect(self._on_sidebar_collapsed)
        body.addWidget(self.sidebar)

        self.stack = QStackedWidget()
        body.addWidget(self.stack, stretch=1)

        self._panels: Dict[str, QWidget] = {}
        self._panel_factories: Dict[str, object] = {}
        self._build_panels()

        # Правый dock — чек-лист (создаём ПОСЛЕ _build_panels,
        # т.к. его navigate-обработчик использует sidebar.select)
        self.checklist = ChecklistPanel(
            self.project, self.bridge, navigate=self._navigate_to)
        body.addWidget(self.checklist)

        # Статусбар
        self.setStatusBar(self._build_statusbar())

    # ---------- Лента актуальности (F06) ----------
    def _build_ribbon(self) -> QFrame:
        rib = QFrame()
        rib.setObjectName("StalenessRibbon")
        lay = QHBoxLayout(rib)
        lay.setContentsMargins(14, 4, 8, 4)
        lay.setSpacing(10)
        self.ribbon_lbl = QLabel("")
        lay.addWidget(self.ribbon_lbl, stretch=1)
        self.ribbon_recalc = QPushButton(_t("ribbon.recalc_all"))
        self.ribbon_recalc.setProperty("role", "ribbonAction")
        self.ribbon_recalc.setCursor(Qt.PointingHandCursor)
        self.ribbon_recalc.clicked.connect(self._action_recalc_all)
        lay.addWidget(self.ribbon_recalc)
        self.ribbon_close = QPushButton("✕")
        self.ribbon_close.setProperty("role", "ribbonClose")
        self.ribbon_close.setCursor(Qt.PointingHandCursor)
        self.ribbon_close.setToolTip(_t("ribbon.dismiss_tip"))
        self.ribbon_close.clicked.connect(
            lambda: self.staleness.dismiss())
        lay.addWidget(self.ribbon_close)
        rib.setVisible(False)
        self.ribbon = rib
        return rib

    def _on_staleness_changed(self) -> None:
        stale = self.staleness.stale_layers()
        if stale and not self.staleness.is_dismissed():
            names = " · ".join(_t(f"ribbon.layer.{k}") for k in stale)
            self.ribbon_lbl.setText(_t("ribbon.stale_prefix") + names)
            self.ribbon.setVisible(True)
        else:
            self.ribbon.setVisible(False)
        # Жёлтые точки на затронутых разделах.
        self.sidebar.set_stale(
            "calculation", "loads" in stale or "ahu" in stale)
        self.sidebar.set_stale("ventilation", "ventilation" in stale)

    def _action_recalc_all(self) -> None:
        """Полная цепочка нагрузки → вентиляция → AHU из ленты."""
        if not self.project.spaces:
            return
        panel = self._panels.get("calculation")
        if isinstance(panel, CalculationPanel):
            # Переходим на экран расчёта: там прогресс и «Отменить».
            self._navigate_to("calculation")
            panel._run_all()  # noqa: SLF001

    def _build_panels(self) -> None:
        """Горячие панели — сразу, остальные — фабриками при первом открытии.

        Ленивые фабрики держат импорт внутри себя: модуль панели (и его
        зависимости вроде matplotlib) не грузится, пока раздел не открыт.
        Панель, созданная позже, строится от текущего состояния проекта —
        все панели и так инициализируются полным _refresh().
        """
        welcome = WelcomePanel()
        welcome.openProject.connect(self._action_open_project)
        welcome.loadCsv.connect(self._goto_data)
        welcome.newEmpty.connect(self._action_new_empty)
        welcome.fromTemplate.connect(self._action_from_template)
        self._register_panel("welcome", welcome)

        # Горячий путь: открытие/сохранение (data), пересчёт с топбара и
        # ленты (calculation), бейдж числа проблем (problems).
        self._register_panel("data",
                             DataPanel(self.project, self.bridge))
        self._register_panel("calculation",
                             CalculationPanel(self.project, self.bridge,
                                              navigate=self._navigate_to))
        self._register_panel("problems",
                             ProblemsPanel(self.project, self.bridge,
                                           navigate=self._navigate_to_space))

        p, b = self.project, self.bridge
        F = self._panel_factories

        def _f(module: str, cls: str):
            def make() -> QWidget:
                import importlib
                mod = importlib.import_module(
                    f"hvac.ui_qt.panels.{module}")
                return getattr(mod, cls)(p, b)
            return make

        F["spaces"] = _f("spaces_panel", "SpacesPanel")
        F["blocks"] = _f("blocks_panel", "BlocksPanel")
        F["constructions"] = _f("constructions_panel", "ConstructionsPanel")
        F["ventilation"] = _f("ventilation_panel", "VentilationPanel")
        F["airbalance"] = _f("air_balance_panel", "AirBalancePanel")
        F["smoke"] = _f("smoke_panel", "SmokePanel")
        F["extensions"] = _f("extensions_panel", "ExtensionsPanel")
        F["systems"] = _f("systems_workspace", "SystemsWorkspacePanel")
        F["equipment"] = _f("equipment_workspace", "EquipmentWorkspacePanel")
        F["balance"] = _f("balance_panel", "BalancePanel")
        F["charts"] = _f("charts_panel", "ChartsPanel")
        F["engineering"] = _f("engineering_panel", "EngineeringPanel")
        F["comparison"] = _f("comparison_panel", "ComparisonPanel")

    def _register_panel(self, key: str, widget: QWidget) -> None:
        self._panels[key] = widget
        self.stack.addWidget(widget)

    def _get_panel(self, key: str) -> QWidget | None:
        """Панель по ключу; ленивая создаётся при первом обращении."""
        w = self._panels.get(key)
        if w is None and key in self._panel_factories:
            w = self._panel_factories.pop(key)()
            self._register_panel(key, w)
            self._restore_panel_splitters(key, w)
        return w

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
        # Журнал: складываем все сообщения статусбара, показываем по клику.
        # messageChanged ловит любые showMessage — и от bridge, и прямые.
        from collections import deque
        self._status_journal: deque = deque(maxlen=50)
        bar.messageChanged.connect(self._on_status_message_changed)
        bar.setToolTip(_t("status.journal_title"))
        bar.installEventFilter(self)
        return bar

    def _on_status_message_changed(self, text: str) -> None:
        if not text:
            return
        from datetime import datetime
        self._status_journal.append((datetime.now().strftime("%H:%M:%S"),
                                     text))

    def eventFilter(self, obj, event) -> bool:  # noqa: N802 (Qt API)
        from PySide6.QtCore import QEvent
        if (obj is self.statusBar()
                and event.type() == QEvent.MouseButtonPress):
            self._show_status_journal()
            return True
        return super().eventFilter(obj, event)

    def _show_status_journal(self) -> None:
        """Меню с последними событиями — по клику на статусбар."""
        from PySide6.QtWidgets import QMenu
        from PySide6.QtGui import QCursor
        menu = QMenu(self)
        title = menu.addAction(_t("status.journal_title"))
        title.setEnabled(False)
        menu.addSeparator()
        if not self._status_journal:
            empty = menu.addAction(_t("status.journal_empty"))
            empty.setEnabled(False)
        else:
            for ts, text in list(self._status_journal)[-15:][::-1]:
                act = menu.addAction(f"{ts}   {text}")
                act.setEnabled(False)
        menu.exec(QCursor.pos())

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

        # 2. TopBar + лента актуальности
        self.topbar.retranslate()
        self.topbar.set_language_label(get_language())
        self.ribbon_recalc.setText(_t("ribbon.recalc_all"))
        self.ribbon_close.setToolTip(_t("ribbon.dismiss_tip"))
        self._on_staleness_changed()

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
        # Бейдж проблем — по тем же событиям, что и панель «Проблемы».
        for sig in (self.bridge.dataLoaded, self.bridge.projectLoaded,
                    self.bridge.calculationDone, self.bridge.ventilationDone,
                    self.bridge.constructionsChanged):
            sig.connect(self._refresh_problem_badge)
        # Глобальная «занятость»: на время расчёта/экспорта гасим
        # кнопку «Пересчитать», чтобы не запустить второй поток.
        self.bridge.busyChanged.connect(self._on_busy_changed)
        # Топбар должен обновляться при любых правках имени/города/методики,
        # т.к. эти правки сейчас не имеют отдельного события.
        self.bridge.dirtyChanged.connect(self._refresh_topbar)
        self.bridge.spacesChanged.connect(self._refresh_topbar)
        self.bridge.statusMessage.connect(
            lambda text, ms: self.statusBar().showMessage(text, ms)
        )

    # ---------- Реакции ----------
    def _on_sidebar_selected(self, key: str) -> None:
        widget = self._get_panel(key)
        if widget is not None:
            self.stack.setCurrentWidget(widget)

    def _on_sidebar_collapsed(self, collapsed: bool) -> None:
        cfg = user_settings.load()
        cfg["sidebar_collapsed"] = bool(collapsed)
        user_settings.save(cfg)

    def _refresh_problem_badge(self, *_args) -> None:
        """Счётчик «ошибки + предупреждения» на пункте «Проблемы».

        Инфо-замечания в бейдж не входят — иначе он горел бы всегда.
        Числа берём из модели панели «Проблемы»: она подписана на те же
        сигналы и обновляется раньше (её connect'ы созданы при сборке
        панелей, до подписок главного окна).
        """
        n = 0
        panel = self._panels.get("problems")
        try:
            c = panel.model.counts()
            n = int(c.get("error", 0)) + int(c.get("warning", 0))
        except Exception:
            n = 0
        self.sidebar.set_badge("problems", str(n) if n else "")

    def _navigate_to(self, key: str) -> None:
        self.sidebar.select(key)
        self._on_sidebar_selected(key)

    def _navigate_to_space(self, space_id: str) -> None:
        """Переход к помещению в разделе «Помещения» (из панели «Проблемы»)."""
        self._navigate_to("spaces")
        panel = self._get_panel("spaces")
        if panel is not None and hasattr(panel, "select_space"):
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

    def _on_busy_changed(self, busy: bool, text: str) -> None:
        """Глобальная блокировка повторного запуска на время работы."""
        self.topbar.recalc_btn.setEnabled(not busy)
        if busy and text:
            self.statusBar().showMessage(text, 0)

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
        self._load_project_path(path)

    def _load_project_path(self, path: str) -> None:
        """Загружает проект из .hvac.json (recent / drag-drop)."""
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
            self.statusBar().showMessage(
                _t("status.dropped_project").format(name=Path(path).name), 4000)
        except Exception as e:
            QMessageBox.critical(self, _t("dialog.error.title"), str(e))

    # ---------- Drag & drop файлов ----------
    def dragEnterEvent(self, event) -> None:  # noqa: N802 (Qt API)
        md = event.mimeData()
        if md.hasUrls():
            for url in md.urls():
                low = url.toLocalFile().lower()
                if low.endswith((".hvac.json", ".json", ".csv")):
                    event.acceptProposedAction()
                    return
        event.ignore()

    def dropEvent(self, event) -> None:  # noqa: N802 (Qt API)
        paths = [u.toLocalFile() for u in event.mimeData().urls()
                 if u.isLocalFile()]
        if not paths:
            event.ignore()
            return
        event.acceptProposedAction()
        jsons = [p for p in paths if p.lower().endswith(".json")]
        csvs = [p for p in paths if p.lower().endswith(".csv")]
        if jsons:
            self._load_project_path(jsons[0])
        elif csvs:
            self._load_dropped_csv(csvs)

    def _load_dropped_csv(self, csvs: list[str]) -> None:
        """Грузит пару spaces.csv + thermal_all.csv, найденную среди дропнутых
        файлов (или соседнюю thermal_all.csv рядом со spaces.csv)."""
        def _find(token: str):
            return next((p for p in csvs
                         if token in Path(p).name.lower()), None)
        spaces = _find("space")
        thermal = _find("thermal")
        if spaces and not thermal:
            cand = Path(spaces).parent / "thermal_all.csv"
            if cand.exists():
                thermal = str(cand)
        if spaces and thermal:
            try:
                self.project.load(spaces, thermal)
            except Exception as e:
                QMessageBox.critical(self, _t("dialog.error.title"), str(e))
            return
        # Неполный набор — отправляем пользователя на вкладку «Данные».
        self._navigate_to("data")
        self.statusBar().showMessage(_t("status.drop_need_both"), 5000)

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
        if dlg.exec() != QDialog.Accepted:
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
        dlg = ExportCenter(self.project, self, bridge=self.bridge)
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

    # ---------- Геометрия окна между запусками ----------
    # Сплиттеры ключуются «панель:номер» (objectName не задан; порядок
    # findChildren детерминирован структурой UI). При несовпадении
    # (панель переделали) restoreState вернёт False — вреда нет.
    def _restore_panel_splitters(self, pkey: str, panel: QWidget) -> None:
        """Применяет сохранённые сплиттеры к (только что созданной) панели.
        Ленивые панели восстанавливаются в момент создания."""
        splitters = (user_settings.load().get("window") or {}) \
            .get("splitters") or {}
        if not splitters:
            return
        for i, sp in enumerate(panel.findChildren(QSplitter)):
            b64 = splitters.get(f"{pkey}:{i}")
            if not b64:
                continue
            try:
                sp.restoreState(QByteArray.fromBase64(b64.encode("ascii")))
            except Exception:
                pass

    def _restore_window_state(self) -> None:
        st = user_settings.load().get("window") or {}
        geo = st.get("geometry")
        if geo:
            try:
                self.restoreGeometry(
                    QByteArray.fromBase64(geo.encode("ascii")))
            except Exception:
                pass
        for pkey, panel in self._panels.items():
            self._restore_panel_splitters(pkey, panel)

    def _save_window_state(self) -> None:
        try:
            cfg = user_settings.load()
            st = dict(cfg.get("window") or {})
            # Merge: несозданные ленивые панели сохраняют прежние значения.
            splitters = dict(st.get("splitters") or {})
            for pkey, panel in self._panels.items():
                for i, sp in enumerate(panel.findChildren(QSplitter)):
                    splitters[f"{pkey}:{i}"] = bytes(
                        sp.saveState().toBase64()).decode("ascii")
            st["geometry"] = bytes(
                self.saveGeometry().toBase64()).decode("ascii")
            st["splitters"] = splitters
            cfg["window"] = st
            user_settings.save(cfg)
        except Exception:
            pass  # настройки не должны мешать закрытию

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
        self._save_window_state()
        event.accept()
