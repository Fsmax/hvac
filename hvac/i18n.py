# -*- coding: utf-8 -*-
"""Локализация: словари RU / UZ и функция перевода t(key).

Использование
-------------
    from hvac.i18n import t, set_language

    set_language("uz")
    label.setText(t("welcome.title"))     # "HVAC Calculator-ga xush kelibsiz"

Все строки UI хранятся как машинные ключи в формате
«домен.раздел.строка», например:
    welcome.title, welcome.action_open, sidebar.spaces, topbar.recalc, ...

Если ключ не найден в словаре — возвращается сам ключ (для отладки видно,
что строка не локализована).
"""

from __future__ import annotations

import os
from typing import Callable, Dict, List, Optional


SUPPORTED_LANGUAGES = ("ru", "uz")
DEFAULT_LANGUAGE = "ru"

# Подписчики на смену языка. Виджеты подписываются через on_language_change
# и обновляют свои подписи в callback. См. main_window._apply_translations.
_language_listeners: List[Callable[[str], None]] = []


# ============================================================================
# Словари локализации
# ============================================================================

# Узбекский — латиница (как принято в современной Республике Узбекистан).
# Технические термины ОВиК сохраняются близко к русским аналогам, поскольку
# в проектной практике в УЗ используются и русские, и узбекские названия.

TRANSLATIONS: Dict[str, Dict[str, str]] = {
    "ru": {
        # ========== Welcome ==========
        "welcome.title":         "Добро пожаловать в HVAC Calculator",
        "welcome.subtitle":      ("Расчёт теплопотерь, вентиляции, ГВС и "
                                   "энергопаспорта по СП и КМК. С чего начнём?"),
        "welcome.action_open":   "📂  Открыть проект",
        "welcome.action_open_desc": "Загрузить ранее сохранённый .hvac.json",
        "welcome.action_csv":    "📥  Загрузить из Revit (CSV)",
        "welcome.action_csv_desc":"Импорт spaces.csv + thermal.csv из Dynamo",
        "welcome.action_new":    "🆕  Создать пустой проект",
        "welcome.action_new_desc":"Ручной ввод помещений без Revit",
        "welcome.action_template":"📐  Из шаблона типового здания",
        "welcome.action_template_desc":"Школа, гостиница, ТРЦ, жилой дом, офис",
        "welcome.hint":          ("Подсказка: Ctrl+K — командная палитра, "
                                   "F5 — пересчитать, Ctrl+S — сохранить."),

        # ========== Sidebar ==========
        "sidebar.home":          "Главная",
        "sidebar.data":          "Данные проекта",
        "sidebar.spaces":        "Помещения",
        "sidebar.constructions": "Конструкции",
        "sidebar.calculation":   "Расчёт нагрузок",
        "sidebar.ventilation":   "Вентиляция",
        "sidebar.zones":         "Зоны и системы",
        "sidebar.equipment":     "Оборудование (системы)",
        "sidebar.room_equipment":"Оборудование в помещениях",
        "sidebar.smoke":         "Дымоудаление",
        "sidebar.charts":        "Графики",
        "sidebar.extensions":    "Расширения v3.7",
        "sidebar.engineering":   "Подробная инженерия v4.1",

        # ========== Topbar ==========
        "topbar.recalc":         "Пересчитать",
        "topbar.save":           "Сохранить",
        "topbar.export":         "Экспорт",
        "topbar.theme":          "Тема",
        "topbar.no_project":     "Без проекта",
        "topbar.lang_tooltip":   "Переключить язык: RU ⇄ UZ  (Til almashtirish)",
        "topbar.lang_tooltip_current":   "Текущий: {label}. Клик — переключить (RU ⇄ UZ)",
        "topbar.theme_tooltip":  "Переключить тему  (Ctrl+T)",

        # ========== Menu Файл ==========
        "menu.file":             "Файл",
        "menu.view":             "Вид",
        "menu.calc":             "Расчёт",
        "menu.file.new":         "Новый пустой проект",
        "menu.file.open":        "Открыть проект…",
        "menu.file.csv":         "Импорт CSV из Revit…",
        "menu.file.save":        "Сохранить проект",
        "menu.file.export":      "Экспорт…",
        "menu.file.quit":        "Выход",
        "menu.file.recent":      "Недавние",

        # ========== Engineering tabs ==========
        "eng.title":             "Подробная инженерия (v4.1 + v4.2)",
        "eng.psychro":           "Психрометрика AHU",
        "eng.duct":              "Аэродинамика сети",
        "eng.hydraulics":        "Гидравлика отопления",
        "eng.radiators":         "Радиаторы",
        "eng.acoustics":         "Акустика",
        "eng.underfloor":        "Тёплый пол",
        "eng.fancoils":          "Фанкойлы",
        "eng.vrf":               "VRF/VRV",

        # ========== Кнопки общего назначения ==========
        "btn.add":               "Добавить",
        "btn.edit":              "Редактировать",
        "btn.delete":            "Удалить",
        "btn.duplicate":         "Копировать",
        "btn.compute":           "Рассчитать",
        "btn.run":               "Запустить",
        "btn.cancel":            "Отмена",
        "btn.ok":                "OK",
        "btn.close":             "Закрыть",
        "btn.apply":             "Применить",

        # ========== Статусы ==========
        "status.ready":          "Готов",
        "status.computing":      "Вычисление…",
        "status.done":           "Готово",

        # ========== Чек-лист ==========
        "checklist.title":              "Готовность проекта",
        "checklist.step_csv":           "Загружены CSV / проект",
        "checklist.step_city":          "Выбран город / климат",
        "checklist.step_u":             "U-значения утверждены",
        "checklist.step_zones":         "Зоны назначены",
        "checklist.step_calc":          "Расчёт нагрузок выполнен",
        "checklist.step_vent":          "Вентиляция посчитана",
        "checklist.csv_hint":           "{n} помещений",
        "checklist.csv_hint_empty":     "не загружено",
        "checklist.city_hint_empty":    "—",
        "checklist.u_hint":             "{n} типов",
        "checklist.u_hint_empty":       "каталог пуст",
        "checklist.zones_hint":         "{n} зон",
        "checklist.zones_hint_empty":   "нет",
        "checklist.calc_hint":          "Σ {kw:.1f} кВт",
        "checklist.calc_hint_empty":    "не выполнен",
        "checklist.vent_hint":          "Σ {m3h} м³/ч",
        "checklist.vent_hint_empty":    "не выполнено",

        # ========== Языки ==========
        "lang.ru":               "Русский",
        "lang.uz":                "O‘zbek (lotin)",

        # ========== Категории команд (палитра, меню) ==========
        "cmd.cat.nav":           "Навигация",
        "cmd.cat.file":          "Файл",
        "cmd.cat.calc":          "Расчёт",
        "cmd.cat.view":          "Вид",
        "cmd.go_prefix":         "Перейти: ",

        # ========== Команды: Файл ==========
        "cmd.file.new":          "Новый пустой проект",
        "cmd.file.open":         "Открыть проект…",
        "cmd.file.csv":          "Импорт CSV из Revit…",
        "cmd.file.save":         "Сохранить проект",
        "cmd.file.export":       "Экспорт…",
        "cmd.file.quit":         "Выход",

        # ========== Команды: Расчёт ==========
        "cmd.calc.heat":         "Пересчитать нагрузки",
        "cmd.calc.vent":         "Рассчитать вентиляцию",
        "cmd.calc.ahu":          "Рассчитать AHU",
        "cmd.calc.all":          "Полный расчёт",

        # ========== Команды: Вид ==========
        "cmd.view.theme":        "Переключить тему (dark/light)",
        "cmd.view.palette":      "Командная палитра",
        "cmd.view.lang_ru":      "Язык: Русский",
        "cmd.view.lang_uz":      "Til: O‘zbek (lotin)",

        # ========== Меню (с & для мнемоники) ==========
        "menu_bar.file":         "&Файл",
        "menu_bar.view":         "&Вид",
        "menu_bar.calc":         "&Расчёт",
        "menu.lang_submenu":     "🌐  Язык / Til",

        # ========== Статус-бар (с {placeholders}) ==========
        "status.calc_done":      "Расчёт выполнен",
        "status.no_data_for_calc": "Нет данных для расчёта",
        "status.loaded_spaces":  "Загружено помещений: {n}",
        "status.kw_summary":     "Σ зима {h:.1f} кВт · Σ лето {c:.1f} кВт",
        "status.lang_switched":  "Язык переключён: Русский",
        "status.autosave_done":  "Auto-save: {name}",
        "status.autosave_error": "Auto-save: ошибка {err}",
        "status.template_applied": ("Создано из шаблона: «{title}», "
                                     "помещений: {n}"),

        # ========== QMessageBox ==========
        "dialog.file_not_found.title": "Файл не найден",
        "dialog.file_not_found.body":  "Файл не существует:\n{path}",
        "dialog.error.title":          "Ошибка",
        "dialog.new_project.title":    "Новый проект",
        "dialog.unsaved.body":         ("Есть несохранённые изменения. "
                                         "Продолжить?"),
        "dialog.unsaved_close.body":   ("Есть несохранённые изменения. "
                                         "Закрыть без сохранения?"),
        "dialog.no_data.title":        "Нет данных",
        "dialog.no_data.body":         ("Загрузите проект или выполните "
                                         "расчёт перед экспортом."),
        "dialog.quit.title":           "Выход",

        # ========== Recent files ==========
        "recent.empty":          "(пусто)",

        # ========== Общие фильтры/виджеты ==========
        "filter.all":            "(все)",
        "filter.not_set":        "— не выбран —",
        "btn.pick":              "Выбрать…",
        "btn.import":            "Импорт…",
        "btn.template":          "Шаблон дома…",
        "btn.add_space":         "+ Помещение",

        # ========== Panel: Data ==========
        "panel.data.title":      "Данные проекта",
        "panel.data.subtitle":   "Климат, параметры расчёта, источники геометрии.",
        "panel.data.project.title": "Проект",
        "panel.data.project.desc":  "Имя и применяемая методика расчёта.",
        "panel.data.field.name":    "Название:",
        "panel.data.field.name.ph": "Например: Жилой комплекс Чорсу, Блок B",
        "panel.data.field.method":  "Методика:",
        "panel.data.climate.title": "Климат",
        "panel.data.climate.desc":  "Расчётные температуры по СП 131.13330 / КМК.",
        "panel.data.field.city":    "Город:",
        "panel.data.climate.t_heat_cap":  "t зима, °C",
        "panel.data.climate.t_cool_cap":  "t лето, °C",
        "panel.data.climate.gsop_cap":    "ГСОП₁₈, °C·сут",
        "panel.data.climate.solar_cap":   "Солн. рад., Вт/м²",
        "panel.data.climate.override":    "Переопределить вручную:",
        "panel.data.climate.t_heat_short":"t зима",
        "panel.data.climate.t_cool_short":"t лето",
        "panel.data.sources.title": "Источники геометрии",
        "panel.data.sources.desc":  ("CSV, выгруженные из Revit-Dynamo: "
                                      "spaces.csv (помещения) и thermal.csv "
                                      "(ограждения)."),
        "panel.data.keep_overrides": ("Сохранить ручные правки помещений при "
                                       "перезагрузке"),
        "panel.data.btn_load_csv":  "📥  Загрузить CSV",
        "panel.data.summary_loaded": ("✓ Загружено: {sp} помещений · "
                                       "{el} ограждений · {co} типов конструкций"),
        "panel.data.actions.title": "Проект",
        "panel.data.actions.desc":  ("Открыть ранее сохранённый .hvac.json "
                                      "или создать новый."),
        "panel.data.btn_new":       "🆕  Новый пустой проект",
        "panel.data.btn_open":      "📂  Открыть .hvac.json…",
        "panel.data.btn_save":      "💾  Сохранить",
        "panel.data.btn_save_full": "Сохранить самодостаточный…",
        "panel.data.dlg.pick_spaces":  "Выберите spaces.csv",
        "panel.data.dlg.pick_thermal": "Выберите thermal.csv",
        "panel.data.dlg.open_project": "Открыть проект",
        "panel.data.dlg.save_project": "Сохранить проект",
        "panel.data.dlg.save_full":    "Сохранить самодостаточный проект",
        "panel.data.dlg.filter.hvac":  ("Проект HVAC (*.hvac.json);;"
                                         "JSON (*.json);;Все (*)"),
        "panel.data.dlg.filter.csv":   "CSV (*.csv);;Все (*)",
        "panel.data.dlg.filter.hvac_save": ("Проект HVAC (*.hvac.json);;"
                                              "JSON (*.json)"),
        "panel.data.err.csv_load":  "Не удалось загрузить CSV",
        "panel.data.err.open":      "Не удалось открыть проект",
        "panel.data.err.save":      "Не удалось сохранить",
        "panel.data.err.save_full": "Не удалось сохранить полный проект",
        "panel.data.dialog.new_clear.body": ("Текущий проект будет очищен. "
                                               "Продолжить?"),
        "panel.data.status.loading_csv":     "Загружаю CSV…",
        "panel.data.status.climate_applied": "Применён климат: {name}",
        "panel.data.status.opened":          "Открыто: {path}",
        "panel.data.status.saved":           "Сохранено: {path}",
        "panel.data.status.saved_full":      "Сохранён полный проект: {path}",
        "panel.data.suffix_new_project":     "Новый проект",
        "panel.data.suffix_full":            "_полный",

        # ========== Panel: Spaces ==========
        "panel.spaces.title":         "Помещения",
        "panel.spaces.col.number":    "№",
        "panel.spaces.col.name":      "Имя",
        "panel.spaces.col.level":     "Этаж",
        "panel.spaces.col.type":      "Тип",
        "panel.spaces.col.area":      "S, м²",
        "panel.spaces.col.volume":    "V, м³",
        "panel.spaces.col.t_heat":    "t зима",
        "panel.spaces.col.q_heat":    "Q зима, кВт",
        "panel.spaces.col.q_cool":    "Q лето, кВт",
        "panel.spaces.col.density":   "Вт/м²",
        "panel.spaces.col.zone":      "Зона",
        "panel.spaces.search.ph":     "Поиск по номеру / имени / типу…",
        "panel.spaces.filter.level":  "Этаж:",
        "panel.spaces.filter.type":   "Тип:",
        "panel.spaces.filter.zone":   "Зона:",
        "panel.spaces.count_total":   "{n} помещений",
        "panel.spaces.count_filtered":"{visible} из {total} помещений",
        "panel.spaces.count_empty":   "Нет загруженных помещений",
        "panel.spaces.tooltip":       ("{number} · {name}\nЭтаж: {level}\n"
                                        "Тип: {type}{mod}"),
        "panel.spaces.tooltip.modified": " (ручная правка)",
        "panel.spaces.dlg.no_number.title": "Нет номера",
        "panel.spaces.dlg.no_number.body":  "Введите номер помещения.",
        "panel.spaces.dlg.not_added":       "Не добавлено",
        "panel.spaces.dlg.delete.title":    "Удалить",
        "panel.spaces.dlg.delete.body":     "Удалить помещение «{number} {name}»?",
        "panel.spaces.dlg.delete.elems":    ("\n\nБудет также удалено {n} "
                                              "ограждений."),
        "panel.spaces.dlg.import.title":    "Импорт списка помещений",
        "panel.spaces.dlg.import.filter":   ("Таблицы (*.xlsx *.csv);;"
                                              "Excel (*.xlsx);;CSV (*.csv)"),
        "panel.spaces.dlg.import_err":      "Ошибка импорта",
        "panel.spaces.dlg.tpl_empty.title": "Пусто",
        "panel.spaces.dlg.tpl_empty.body":  "В шаблоне нет ни одной комнаты.",
        "panel.spaces.status.imported":     ("Импортировано {n} помещений "
                                               "из {path}."),
        "panel.spaces.status.tpl_created":  "Создано {n} помещений по шаблону.",
        "panel.spaces.default_level":       "1 этаж",

        # ========== Common ==========
        "btn.refresh":            "Обновить",
        "btn.recalc":             "Пересчитать",
        "btn.search.ph":          "Поиск…",
        "common.empty_no_data":   "Нет данных. Загрузите проект и выполните расчёт.",
        "common.empty_no_results": ("Нет результатов расчёта. Перейдите "
                                      "в «Расчёт нагрузок»."),
        "common.empty_no_spaces": "Нет загруженных помещений.",
        "common.recovery_yes":    "✓",
        "common.recovery_no":     "—",
        "common.not_yet":         "<i>Расчёт ещё не выполнен.</i>",

        # ========== Panel: Charts ==========
        "panel.charts.title":     "Графики",
        "panel.charts.err.draw":  "Ошибка построения графика:\n{err}",

        # ========== Panel: Room equipment ==========
        "panel.room_eq.title":    "Оборудование в помещениях",
        "panel.room_eq.subtitle": ("Радиаторы, фанкойлы, диффузоры — что "
                                    "физически стоит в комнате. Заполняется "
                                    "после расчёта нагрузок."),
        "panel.room_eq.col.number":    "№",
        "panel.room_eq.col.name":      "Имя",
        "panel.room_eq.col.q_heat":    "Q зима, кВт",
        "panel.room_eq.col.terminal":  "Радиатор/фанкойл",
        "panel.room_eq.col.power":     "Мощн., Вт",
        "panel.room_eq.col.qty":       "Кол-во",
        "panel.room_eq.col.diffuser":  "Воздухораспред.",
        "panel.room_eq.col.diff_qty":  "Кол-во",

        # ========== Panel: Equipment ==========
        "panel.equipment.title":  "Оборудование (системы)",
        "panel.equipment.subtitle": ("Каталоги систем отопления / охлаждения / "
                                      "вентиляции. Системы создаются "
                                      "автоматически при назначении зон в "
                                      "«Зонах и системах»."),
        "panel.equipment.tab.heat":  "Отопление",
        "panel.equipment.tab.cool":  "Охлаждение",
        "panel.equipment.tab.ahu":   "Вентиляция (AHU)",
        "panel.equipment.tab.load":  "Нагрузка AHU",
        "panel.equipment.col.name":   "Имя системы",
        "panel.equipment.col.type":   "Тип",
        "panel.equipment.col.t_sup":  "t подачи, °C",
        "panel.equipment.col.t_ret":  "t обратки, °C",
        "panel.equipment.col.fuel":   "Топливо",
        "panel.equipment.col.eff":    "КПД",
        "panel.equipment.col.cop":    "COP",
        "panel.equipment.col.refr":   "Хладагент",
        "panel.equipment.col.ahu":    "Имя AHU",
        "panel.equipment.col.recov":  "Рекуператор",
        "panel.equipment.col.eta_w":  "η зима",
        "panel.equipment.col.eta_s":  "η лето",
        "panel.equipment.col.t_in_w": "t притока зима, °C",
        "panel.equipment.col.q_win":  "Q зима, кВт",
        "panel.equipment.col.q_sens": "Q лето (явная), кВт",
        "panel.equipment.col.q_lat":  "Q лето (скрытая), кВт",
        "panel.equipment.col.flow":   "Расход, м³/ч",

        # ========== Panel: Ventilation ==========
        "panel.ventilation.title":    "Вентиляция",
        "panel.ventilation.btn_run":  "▶  Пересчитать вентиляцию",
        "panel.ventilation.summary_card.title":    "Сводка по системам",
        "panel.ventilation.summary_card.subtitle": "Суммарные расходы воздуха.",
        "panel.ventilation.summary_html": (
            "<b>Σ Приток:</b> {sup} м³/ч &nbsp;·&nbsp; "
            "<b>Σ Вытяжка:</b> {exh} м³/ч &nbsp;·&nbsp; "
            "<b>Σ Зонт:</b> {hood} м³/ч &nbsp;·&nbsp; "
            "<b>Дисбаланс:</b> {diff} м³/ч"
        ),
        "panel.ventilation.summary_not_yet": (
            "<i>Расчёт ещё не выполнен. Нажмите «Пересчитать вентиляцию».</i>"
        ),
        "panel.ventilation.col.number":  "№",
        "panel.ventilation.col.name":    "Имя",
        "panel.ventilation.col.level":   "Этаж",
        "panel.ventilation.col.type":    "Тип",
        "panel.ventilation.col.area":    "S, м²",
        "panel.ventilation.col.supply":  "Приток, м³/ч",
        "panel.ventilation.col.exhaust": "Вытяжка, м³/ч",
        "panel.ventilation.col.hood":    "Зонт, м³/ч",
        "panel.ventilation.col.ach":     "ACH, 1/ч",
        "panel.ventilation.col.imbal":   "Дисбаланс",

        # ========== Panel: Properties (правая панель Spaces) ==========
        "panel.props.empty":      "—",
        "panel.props.nothing":    "Ничего не выбрано",
        "panel.props.hint":       ("Выделите помещение в таблице слева, "
                                    "чтобы редактировать."),
        "panel.props.subtitle":   "Этаж {level} · {area:.1f} м² · {volume:.1f} м³{mod}",
        "panel.props.user_mark":  "  · ручная правка",
        "panel.props.field.type": "Тип помещения:",
        "panel.props.field.t_heat":  "t зима:",
        "panel.props.field.t_cool":  "t лето:",
        "panel.props.field.occup":   "Занятость:",
        "panel.props.field.light":   "Освещение:",
        "panel.props.field.equip":   "Оборудование:",
        "panel.props.field.inf":     "Инфильтрация:",
        "panel.props.field.flags":   "Признаки:",
        "panel.props.suffix.people": " чел.",
        "panel.props.flag.corner":   "угловое",
        "panel.props.flag.roof":     "под крышей",
        "panel.props.flag.floor":    "пол по грунту",
        "panel.props.results.title": "Результаты расчёта",
        "panel.props.results.not_yet": ("<i>Расчёт ещё не выполнен. "
                                          "Нажмите F5 или «Пересчитать».</i>"),
        "panel.props.heat_loss_label":  "Теплопотери (зима)",
        "panel.props.heat_gain_label":  "Теплопоступления (лето)",
        "panel.props.block_header":     "<b>{title}: {kw:.2f} кВт</b>",
        "panel.props.block_row":        "&nbsp;&nbsp;{key}: {w:.0f} Вт",

        # ========== Panel: Extensions ==========
        "panel.ext.title":     "Расширения v3.7",
        "panel.ext.subtitle":  ("ГВС, энергопаспорт, проверка точки росы, "
                                 "подбор воздуховодов и труб. Каждый расчёт "
                                 "можно запустить отдельно."),
        "panel.ext.dhw.title":     "ГВС",
        "panel.ext.dhw.desc":      ("Суточный расход, пиковая нагрузка, "
                                     "объём бака. Норматив: СП 30.13330."),
        "panel.ext.energy.title":  "Энергопаспорт",
        "panel.ext.energy.desc":   ("Годовое потребление, удельные показатели, "
                                     "класс A++…E."),
        "panel.ext.dew.title":     "Точка росы",
        "panel.ext.dew.desc":      ("Проверка наружных ограждений на "
                                     "конденсацию. Норматив: СП 50 Прил. Е."),
        "panel.ext.ducts.title":   "Подбор воздуховодов",
        "panel.ext.ducts.desc":    ("Подбор сечений Ø / AxB по "
                                     "рекомендованным скоростям."),
        "panel.ext.pipes.title":   "Подбор труб",
        "panel.ext.pipes.desc":    "Подбор DN труб отопления по СП 60 / Альтшулю.",
        "panel.ext.btn_run":       "Запустить",
        "panel.ext.summary.empty": "Расчёт ещё не выполнен.",
        "panel.ext.status.ok":     "Готово: {title}",
        "panel.ext.status.err":    "Ошибка ({title}): {err}",
        "panel.ext.sum.dhw":       ("Систем ГВС: {n}\nΣ суточный объём: "
                                     "{v:.1f} м³/сут\nΣ пиковая нагрузка: "
                                     "{q:.1f} кВт"),
        "panel.ext.sum.energy":    ("Класс энергоэффективности: {cls}\n"
                                     "Удельное потребление: {q:.1f} "
                                     "кВт·ч/(м²·год)\nОтклонение от нормы: "
                                     "{dev:+.1f} %"),
        "panel.ext.sum.dew":       ("Проверено ограждений: {n}\n"
                                     "С риском конденсации: {risky}"),
        "panel.ext.sum.ducts":     "Сетей воздуховодов: {n}\nУчастков: {s}",
        "panel.ext.sum.pipes":     "Сетей труб: {n}\nУчастков: {s}",

        # ========== Panel: Zones ==========
        "panel.zones.title":            "Зоны и системы",
        "panel.zones.auto.title":       "Авто-присвоение зон",
        "panel.zones.auto.desc":        ("Разделить помещения на системы "
                                          "отопления / охлаждения / вентиляции "
                                          "по выбранному критерию."),
        "panel.zones.criterion":        "Критерий:",
        "panel.zones.apply_to":         "Применить к:",
        "panel.zones.overwrite":        "Перезаписать существующие",
        "panel.zones.btn_apply":        "Применить",
        "panel.zones.mode.by_prefix":   "По префиксу номера (B01-001 → Блок B01)",
        "panel.zones.mode.by_level":    "По уровню",
        "panel.zones.mode.by_type":     "По группе типов",
        "panel.zones.system.all":       "Все системы",
        "panel.zones.system.heating":   "Только отопление",
        "panel.zones.system.cooling":   "Только охлаждение",
        "panel.zones.system.ventilation":"Только вентиляция",
        "panel.zones.summary.title":    "Сводка по зонам",
        "panel.zones.summary.desc":     ("Нагрузки, расход воздуха и количество "
                                          "помещений в каждой зоне."),
        "panel.zones.summary.heating":  "Отопление",
        "panel.zones.summary.cooling":  "Охлаждение",
        "panel.zones.summary.vent":     "Вентиляция",
        "panel.zones.col.zone":         "Зона",
        "panel.zones.col.n_spaces":     "Помещений",
        "panel.zones.col.area":         "S, м²",
        "panel.zones.col.q_heat":       "Q отопл., кВт",
        "panel.zones.col.q_cool":       "Q охлажд., кВт",
        "panel.zones.col.supply":       "Приток, м³/ч",
        "panel.zones.status.assigned":  "Назначено зон: {n}",

        # ========== Panel: Constructions ==========
        "panel.constructions.title":          "Конструкции",
        "panel.constructions.count":          "{total} типов · используется {used} · неиспольз. {unused}",
        "panel.constructions.count_empty":    "Каталог пуст",
        "panel.constructions.hint":           ("Двойной клик по <b>U/SHGC/Примечанию</b> — править. "
                                                "Двойной клик по <b>R</b> — открыть редактор слоёв. "
                                                "Выделите несколько строк и нажмите <b>«Применить пресет»</b> "
                                                "или <b>«Bulk-edit U»</b> для массовых правок."),
        "panel.constructions.search_ph":      "Поиск по категории / семейству / типу…",
        "panel.constructions.filter_all":     "Все категории",
        "panel.constructions.btn_preset":     "Применить пресет…",
        "panel.constructions.btn_bulk_u":     "Bulk-edit U…",
        "panel.constructions.btn_layers":     "Редактировать слои…",
        "panel.constructions.btn_remove":     "Удалить неиспольз.",
        "panel.constructions.btn_export":     "Экспорт каталога…",
        "panel.constructions.btn_import":     "Импорт каталога…",
        "panel.constructions.col.category":   "Категория",
        "panel.constructions.col.family":     "Семейство",
        "panel.constructions.col.type":       "Тип",
        "panel.constructions.col.th":         "δ, мм",
        "panel.constructions.col.u":          "U",
        "panel.constructions.col.r":          "R",
        "panel.constructions.col.rnorm":      "R_норм",
        "panel.constructions.col.shgc":       "SHGC",
        "panel.constructions.col.used":       "Использ.",
        "panel.constructions.col.area":       "Σ площ., м²",
        "panel.constructions.col.note":       "Примечание",
        "panel.constructions.note_manual_u":  " [U задан вручную]",
        "panel.constructions.tt.layers":      "<b>Слои:</b>",
        "panel.constructions.tt.layer_r":     "{i}. {material} — R = {r:.3f}",
        "panel.constructions.tt.layer_full":  "{i}. {material} — {th:.0f} мм, λ = {lam:g}",
        "panel.constructions.tt.rnorm":       "СП 50.13330 табл. 3 при ГСОП = {gsop:.0f} °С·сут",
        "panel.constructions.dlg.preset_title": "Применить пресет",
        "panel.constructions.dlg.category":   "Категория:",
        "panel.constructions.dlg.preset":     "Пресет:",
        "panel.constructions.dlg.all":        "Все",
        "panel.constructions.dlg.preset_desc": "{description}<br><i>Категория: {category}, слоёв: {n}</i>",
        "panel.constructions.msg.layers_pick": "Выделите одну строку для редактирования слоёв.",
        "panel.constructions.msg.layers_one": "Редактор слоёв работает с одной конструкцией. Выделите одну строку.",
        "panel.constructions.msg.preset_pick": "Выделите одну или несколько строк для применения пресета.",
        "panel.constructions.msg.bulk_pick":  "Выделите одну или несколько строк.",
        "panel.constructions.msg.bulk_prompt": "Новое U для {n} строк(и), Вт/(м²·К):",
        "panel.constructions.msg.unused_none": "Все конструкции используются.",
        "panel.constructions.msg.remove_ask": "Удалить из каталога {n} конструкций, на которые не ссылается ни один элемент?",
        "panel.constructions.msg.import_strategy": "Что делать при совпадении ключей?",
        "panel.constructions.import.merge":   "merge — добавить только новые",
        "panel.constructions.import.update":  "update_u — обновить U/SHGC/слои",
        "panel.constructions.import.replace": "replace — полностью заменить каталог",
        "panel.constructions.title.layers":   "Слои",
        "panel.constructions.title.preset":   "Пресет",
        "panel.constructions.title.bulk":     "Bulk-edit",
        "panel.constructions.title.cleanup":  "Очистка",
        "panel.constructions.title.remove":   "Удалить неиспользуемые",
        "panel.constructions.title.import_strategy": "Стратегия импорта",
        "panel.constructions.title.export":   "Экспорт каталога конструкций",
        "panel.constructions.title.import":   "Импорт каталога конструкций",
        "panel.constructions.title.import_err": "Ошибка импорта",
        "panel.constructions.status.preset":  "Пресет «{name}» применён к {n} конструкции(ям).",
        "panel.constructions.status.bulk":    "U = {u:.3f} проставлено в {n} строк(ах).",
        "panel.constructions.status.removed": "Удалено {n} неиспользуемых конструкций.",
        "panel.constructions.status.exported": "Экспортировано {n} записей в {path}.",
        "panel.constructions.status.imported": "Импорт: добавлено {added}, обновлено {updated}, пропущено {skipped}.",

        # ========== Panel: Boundaries ==========
        "panel.boundaries.title":           "Ограждения",
        "panel.boundaries.title_for":       "Ограждения — {number} · {name}",
        "panel.boundaries.summary":         "{n} элем. · Σ наружн. площ. {area:.1f} м²",
        "panel.boundaries.col.category":    "Категория",
        "panel.boundaries.col.construction":"Конструкция",
        "panel.boundaries.col.area":        "Площадь",
        "panel.boundaries.col.orient":      "Ориент.",
        "panel.boundaries.col.u":           "U",
        "panel.boundaries.col.ext":         "Наружн.",
        "panel.boundaries.btn_wall":        "+ Стена",
        "panel.boundaries.btn_window":      "+ Окно",
        "panel.boundaries.btn_door":        "+ Дверь",
        "panel.boundaries.btn_roof":        "+ Кровля",
        "panel.boundaries.btn_floor":       "+ Пол",
        "panel.boundaries.btn_delete":     "Удалить",
        "panel.boundaries.dlg.title":       "Новое ограждение: {number} {name}",
        "panel.boundaries.dlg.category":    "Категория:",
        "panel.boundaries.dlg.construction":"Конструкция:",
        "panel.boundaries.dlg.bnd_type":    "Тип границы:",
        "panel.boundaries.dlg.bnd_ext":     "Наружное",
        "panel.boundaries.dlg.bnd_int":     "Внутреннее",
        "panel.boundaries.dlg.area":        "Площадь:",
        "panel.boundaries.dlg.orient":      "Ориентация:",
        "panel.boundaries.dlg.thickness":   "Толщина:",
        "panel.boundaries.tt.element":      "{cat}\n{family} / {type}\nelement_id: {eid}",
        "panel.boundaries.ext_yes":         "Да",
        "panel.boundaries.ext_no":          "Нет",
        "panel.boundaries.msg.pick_space_title": "Выберите помещение",
        "panel.boundaries.msg.pick_space":  "Сначала выберите помещение в таблице.",
        "panel.boundaries.msg.no_construction_title": "Нет конструкции",
        "panel.boundaries.msg.no_construction": "Выберите или создайте конструкцию.",
        "panel.boundaries.auto_note":       "Создано автоматически",

        # ========== Dialog: Layers editor ==========
        "dlg.layers.title":          "Слои: {key}",
        "dlg.layers.category":       "Категория: <b>{category}</b>",
        "dlg.layers.col.material":   "Материал",
        "dlg.layers.col.th":         "δ, мм",
        "dlg.layers.col.lambda":     "λ, Вт/(м·К)",
        "dlg.layers.col.r":          "R, м²К/Вт",
        "dlg.layers.btn_add":        "Добавить слой",
        "dlg.layers.btn_delete":     "Удалить",
        "dlg.layers.btn_air":        "Возд. прослойка",
        "dlg.layers.summary_title":  "<b>Сводка</b>",
        "dlg.layers.summary":        ("R<sub>si</sub> = {rsi:.3f}<br>"
                                       "R<sub>se</sub> = {rse:.3f}<br>"
                                       "Σ R = <b>{r:.3f}</b> м²·К/Вт<br>"
                                       "U = <b>{u:.3f}</b> Вт/(м²·К)"),

        # ========== Dialog: Duct edge ==========
        "dlg.duct.title_new":        "Новый участок воздуховода",
        "dlg.duct.title_edit":       "Параметры участка: {edge_id}",
        "dlg.duct.gb_id":            "Идентификация",
        "dlg.duct.id":               "ID участка:",
        "dlg.duct.parent":           "Родитель:",
        "dlg.duct.parent_root":      "(корень / от вентилятора)",
        "dlg.duct.terminal_name":    "Имя терминала:",
        "dlg.duct.terminal_ph":      "Имя обслуживаемого помещения (для терминалов)",
        "dlg.duct.is_terminal":      "Концевой участок (терминал)",
        "dlg.duct.gb_geom":          "Геометрия и расход",
        "dlg.duct.flow":             "Расход:",
        "dlg.duct.length":           "Длина:",
        "dlg.duct.shape":            "Форма:",
        "dlg.duct.shape.round":      "Круглый (round)",
        "dlg.duct.shape.rect":       "Прямоугольный (rect)",
        "dlg.duct.diameter":         "Диаметр:",
        "dlg.duct.width":            "Ширина:",
        "dlg.duct.height":           "Высота:",
        "dlg.duct.gb_fittings":      "Местные сопротивления (фитинги)",
        "dlg.duct.btn_add":          "➕ Добавить",
        "dlg.duct.btn_delete":       "Удалить",
        "dlg.duct.fit.col_kind":     "Тип",
        "dlg.duct.fit.col_qty":      "Шт.",
        "dlg.duct.fit.col_zeta":     "ζ (опц.)",
        "dlg.duct.fit.col_dp":       "Δp (Па, опц.)",
        "dlg.duct.fit.col_note":     "Примеч.",
        "dlg.duct.fit.empty":        "(пусто — задайте ζ или Δp)",

        # ========== Dialog: Space (add / edit) ==========
        "dlg.space.title_new":       "Новое помещение",
        "dlg.space.number":          "№ помещения:",
        "dlg.space.number_ph":       "Например, 101 или B01-105",
        "dlg.space.name":            "Название:",
        "dlg.space.name_ph":         "Например, «Гостиная 18 м²»",
        "dlg.space.level":           "Этаж:",
        "dlg.space.area":            "Площадь:",
        "dlg.space.height":          "Высота:",
        "dlg.space.type":            "Тип:",
        "dlg.space.lvl_1":           "1 этаж",
        "dlg.space.lvl_2":           "2 этаж",
        "dlg.space.lvl_3":           "3 этаж",
        "dlg.space.default_type":    "Прочее",

        # ========== Dialog: Building template ==========
        "dlg.bldg.title":            "Шаблон жилого дома",
        "dlg.bldg.floors":           "Этажей:",
        "dlg.bldg.first_floor":      "Первый этаж №:",
        "dlg.bldg.apts":             "Квартир на этаже:",
        "dlg.bldg.height":           "Высота помещений:",
        "dlg.bldg.prefix":           "Префикс этажа:",
        "dlg.bldg.level_prefix":     "Этаж ",
        "dlg.bldg.composition":      "<b>Состав одной квартиры</b> (каждая строка — одна комната):",
        "dlg.bldg.col_name":         "Имя комнаты",
        "dlg.bldg.col_type":         "Тип",
        "dlg.bldg.col_area":         "Площадь, м²",
        "dlg.bldg.btn_add":          "Добавить комнату",
        "dlg.bldg.btn_delete":       "Удалить",
        "dlg.bldg.default_room":     "Комната",
        "dlg.bldg.default_type":     "Жилая комната",
        "dlg.bldg.total":            "Итого помещений: <b>{n}</b>, общая площадь ≈ <b>{area:.0f} м²</b>",
        "dlg.bldg.tpl.living":       "Гостиная",
        "dlg.bldg.tpl.bedroom1":     "Спальня 1",
        "dlg.bldg.tpl.bedroom2":     "Спальня 2",
        "dlg.bldg.tpl.kitchen":      "Кухня",
        "dlg.bldg.tpl.bathroom":     "Санузел",
        "dlg.bldg.tpl.corridor":     "Коридор",

        # ========== Dialog: Template ==========
        "dlg.tpl.title":             "Создать проект из шаблона",
        "dlg.tpl.gb_list":           "Шаблон",
        "dlg.tpl.choose":            "Выберите шаблон…",
        "dlg.tpl.gb_common":         "Общие параметры",
        "dlg.tpl.project_name":      "Название проекта:",
        "dlg.tpl.project_name_ph":   "Например, «Школа на Чорсу»",
        "dlg.tpl.project_name_hint": "Например, «{title}»",
        "dlg.tpl.city":              "Город (климат):",
        "dlg.tpl.default_city":      "Ташкент",
        "dlg.tpl.btn_create":        "Создать",
        "dlg.tpl.suffix.workplaces": " мест",
        "dlg.tpl.suffix.cabinets":   " кабинетов",
        "dlg.tpl.suffix.classes":    " классов",
        "dlg.tpl.suffix.rooms":      " номеров",
        "dlg.tpl.suffix.stars":      " ★",
        "dlg.tpl.suffix.m2":         " м²",
        "dlg.tpl.suffix.apts":       " квартир",
        "dlg.tpl.suffix.floors":     " этажей",
        "dlg.tpl.row.workplaces":    "Количество рабочих мест:",
        "dlg.tpl.row.cabinets":      "Количество кабинетов:",
        "dlg.tpl.row.classes":       "Количество классов:",
        "dlg.tpl.row.rooms":         "Номеров:",
        "dlg.tpl.row.stars":         "Звёзд:",
        "dlg.tpl.row.area":          "Общая площадь:",
        "dlg.tpl.row.apts":          "Квартир:",
        "dlg.tpl.row.floors":        "Этажей:",

        # ========== Dialog: Smoke system ==========
        "dlg.smoke.title_new":       "Новая система СДУ/СПВ",
        "dlg.smoke.title_edit":      "Параметры: {name}",
        "dlg.smoke.gb_id":           "Идентификация",
        "dlg.smoke.name":            "Имя:",
        "dlg.smoke.type":            "Тип:",
        "dlg.smoke.purpose":         "Назначение:",
        "dlg.smoke.gb_method":       "Метод расчёта расхода",
        "dlg.smoke.gb_common":       "Параметры дыма и оборудования",
        "dlg.smoke.t_smoke":         "Температура дыма:",
        "dlg.smoke.makeup":          "Доля компенсирующей подачи:",
        "dlg.smoke.fire_rating":     "Класс огнестойкости:",
        "dlg.smoke.note":            "Примечание:",
        "dlg.smoke.norm.norm":       "Норма расхода:",
        "dlg.smoke.norm.max_zone":   "Макс. площадь зоны:",
        "dlg.smoke.kmk_zone.perim":  "P — периметр очага (макс 12):",
        "dlg.smoke.kmk_zone.layer":  "y — высота свободной зоны:",
        "dlg.smoke.kmk_zone.ks":     "Ks (1.0 без АУПТ, 1.2 со спринклерами):",
        "dlg.smoke.kmk_zone.formula":"Формула: G = 676.8 · P · y^1.5 · Ks   [кг/ч]",
        "dlg.smoke.kmk_corr.n":      "n — коэф. по табл. КМК:",
        "dlg.smoke.kmk_corr.kd":     "Kd — коэф. дверей (1.0 = без):",
        "dlg.smoke.kmk_corr.formula":("Формула: G1 = 3420 · n^1.5  (без дверей)\n"
                                       "         G1 = 4300 · n^1.5 · Kd  (с дверями)   [кг/ч]"),
        "dlg.smoke.nfpa.hrr":        "Q — мощность пожара (HRR):",
        "dlg.smoke.nfpa.frac":       "Доля конвективной мощности:",
        "dlg.smoke.nfpa.plume_h":    "z — высота до слоя дыма:",
        "dlg.smoke.nfpa.formula":    ("Qc = α · Q\n"
                                       "z > zl:  m = 0.071·Qc^(1/3)·z^(5/3) + 0.0018·Qc   [кг/с]\n"
                                       "z ≤ zl:  m = 0.032·Qc^(3/5)·z"),
        "dlg.smoke.manual.l":        "Расход одной дымовой зоны:",
        "dlg.smoke.supply.rate":     "Расход подпора:",
        "dlg.smoke.supply.pressure": "Избыточное давление:",
        "dlg.smoke.hint.norm":       ("Упрощённый инженерный подход. Подходит для предварительной "
                                       "оценки. Для проектной документации сверять с действующим "
                                       "нормативом."),
        "dlg.smoke.hint.kmk_zone":   ("КМК 2.04.05-22, Прил. 20, ф.(3). Для помещений ≤ 1600 м² "
                                       "и периметром очага ≤ 12 м."),
        "dlg.smoke.hint.kmk_corr":   ("КМК 2.04.05-22, Прил. 20, ф.(1)/(2). Для коридоров и "
                                       "холлов. n по табл. в зависимости от назначения."),
        "dlg.smoke.hint.nfpa":       ("NFPA 92, п. 5.5.1. Осесимметричный плюм. Требует HRR "
                                       "и высоту от очага до слоя дыма."),
        "dlg.smoke.hint.manual":     "Расход задаётся вручную (например, по типовому проекту).",
        "dlg.smoke.hint.air":        "Расход подпора по нормативу для защищаемого объёма.",
        "dlg.smoke.method.norm_per_m2":        "Упрощённо: расход = площадь × норма",
        "dlg.smoke.method.kmk_zone_perimeter": "КМК Прил. 20 ф.(3): G = 676.8·P·y^1.5·Ks",
        "dlg.smoke.method.kmk_corridor":       "КМК Прил. 20 ф.(1)/(2): коридор G1 = 3420·n^1.5",
        "dlg.smoke.method.nfpa_plume_axi":     "NFPA 92 п. 5.5.1: осесимметричный плюм",
        "dlg.smoke.method.manual":             "Ручной ввод расхода",
        "dlg.smoke.method.stairs_pressure":    "Подпор лестничной клетки",
        "dlg.smoke.method.elevator_pressure":  "Подпор шахты лифта",
        "dlg.smoke.systype.smoke_removal":     "СДУ — удаление дыма",
        "dlg.smoke.systype.air_supply":        "СПВ — подпор воздуха",
        "dlg.smoke.systype.compensation":      "Компенсирующая подача",
        "dlg.smoke.purpose.parking":           "Парковка",
        "dlg.smoke.purpose.warehouse":         "Склад",
        "dlg.smoke.purpose.corridor":          "Коридор",
        "dlg.smoke.purpose.atrium":            "Атриум / зал сборки людей",
        "dlg.smoke.purpose.trading_hall":      "Торговый зал",
        "dlg.smoke.purpose.stairs":            "Лестничная клетка",
        "dlg.smoke.purpose.elevator":          "Шахта лифта",
        "dlg.smoke.purpose.vestibule":         "Тамбур-шлюз",
        "dlg.smoke.purpose.refuge":            "Зона безопасности МГН",

        # ========== Panel: Smoke ==========
        "panel.smoke.title":              "Дымоудаление и подпор",
        "panel.smoke.card.params.title":  "Параметры",
        "panel.smoke.card.params.sub":    "Активный норматив, сценарий пожара и общие действия над системами.",
        "panel.smoke.norm":               "Норматив:",
        "panel.smoke.scenario":           "Сценарий:",
        "panel.smoke.scenario.single":    "Один очаг пожара",
        "panel.smoke.scenario.multiple":  "Несколько зон одновременно (запас)",
        "panel.smoke.btn_assign":         "Авто-присвоить",
        "panel.smoke.btn_assign_tt":      ("Создать системы СДУ для парковок, складов, длинных коридоров, "
                                            "залов сборки людей и СПВ для лестниц/лифтов."),
        "panel.smoke.btn_calc":           "▶  Рассчитать",
        "panel.smoke.card.systems.title": "Системы",
        "panel.smoke.card.systems.sub":   "Двойной клик по строке — редактировать параметры.",
        "panel.smoke.btn_add":            "➕  Добавить",
        "panel.smoke.btn_edit":           "Редактировать",
        "panel.smoke.btn_dup":            "Копировать",
        "panel.smoke.btn_delete":         "Удалить",
        "panel.smoke.col.name":           "Имя",
        "panel.smoke.col.type":           "Тип",
        "panel.smoke.col.purpose":        "Назначение",
        "panel.smoke.col.method":         "Метод",
        "panel.smoke.col.norm":           "Норма, м³/(ч·м²)",
        "panel.smoke.col.spaces":         "Помещений",
        "panel.smoke.col.area":           "Площадь, м²",
        "panel.smoke.col.flow":           "Расход, м³/ч",
        "panel.smoke.col.makeup":         "Компенсация, м³/ч",
        "panel.smoke.col.zones":          "Зон",
        "panel.smoke.short_method.norm_per_m2":        "Площадь × норма",
        "panel.smoke.short_method.kmk_zone_perimeter": "КМК помещение (ф.3)",
        "panel.smoke.short_method.kmk_corridor":       "КМК коридор (ф.1/2)",
        "panel.smoke.short_method.nfpa_plume_axi":     "NFPA 92 плюм",
        "panel.smoke.short_method.manual":             "Ручной ввод",
        "panel.smoke.short_method.stairs_pressure":    "Подпор лестницы",
        "panel.smoke.short_method.elevator_pressure":  "Подпор лифта",
        "panel.smoke.title.change_norm":  "Смена норматива",
        "panel.smoke.msg.change_norm":    ("Применить параметры нормы «{title}» "
                                            "к уже созданным автоматически системам?\n\n"
                                            "Ручные системы (созданные через «Добавить») не "
                                            "затрагиваются."),
        "panel.smoke.status.norm":        "Норматив: {title}",
        "panel.smoke.status.norm_upd":    "  ·  обновлено: СДУ {smoke}, СПВ {pres}",
        "panel.smoke.status.norm_method": ", методов сменено: {n}",
        "panel.smoke.title.no_data":      "Нет данных",
        "panel.smoke.msg.no_data":        "Загрузите помещения, прежде чем создавать системы.",
        "panel.smoke.title.assign":       "Авто-присвоение",
        "panel.smoke.msg.assign_overwrite":("В проекте есть помещения с уже назначенными системами.\n"
                                             "Перезаписать назначения?"),
        "panel.smoke.title.err":          "Ошибка",
        "panel.smoke.status.assigned":    "Создано СДУ: {smoke}, СПВ: {pres}, назначено помещений: {n}",
        "panel.smoke.title.no_systems":   "Нет систем",
        "panel.smoke.msg.no_systems":     ("Создайте системы вручную («Добавить») или нажмите "
                                            "«Авто-присвоить»."),
        "panel.smoke.title.calc_err":     "Ошибка расчёта",
        "panel.smoke.status.calc_done":   "Расчёт СДУ/СПВ выполнен",
        "panel.smoke.note_manual":        "Создано вручную",
        "panel.smoke.status.created":     "Создана система: {name}",
        "panel.smoke.status.saved":       "Сохранены параметры: {name}",
        "panel.smoke.title.dup":          "Копировать систему",
        "panel.smoke.msg.dup":            "Имя новой системы:",
        "panel.smoke.dup.suffix":         "-копия",
        "panel.smoke.title.name_busy":    "Имя занято",
        "panel.smoke.msg.name_busy":      "Система '{name}' уже существует.",
        "panel.smoke.copy_suffix":        " (копия)",
        "panel.smoke.title.del":          "Удалить систему",
        "panel.smoke.msg.del":            "Удалить систему «{name}» и снять её со всех помещений?",
        "panel.smoke.status.deleted":     "Удалена система {name}; отвязано помещений: {n}",
        "panel.smoke.summary.total":      "Всего систем: {n}",
        "panel.smoke.summary.flows":      ("Σ СДУ {smoke:.1f} тыс. м³/ч  ·  "
                                            "Σ компенсация {makeup:.1f} тыс. м³/ч"),
        "panel.smoke.summary.empty":      "Систем не создано",

        # ========== Panel: Engineering ==========
        "panel.eng.title":               "Подробная инженерия (v4.1 + v4.2)",
        "panel.eng.card.title":          "Расчёты",
        "panel.eng.card.sub":            ("Психрометрика AHU, аэродинамика, гидравлика, радиаторы, "
                                            "акустика, тёплый пол, фанкойлы, VRF. Каждая вкладка "
                                            "использует фасадный метод HVACProject."),
        "panel.eng.tab.psychro":         "Психрометрика AHU",
        "panel.eng.tab.duct":            "Аэродинамика сети",
        "panel.eng.tab.hydro":           "Гидравлика отопления",
        "panel.eng.tab.radiators":       "Радиаторы",
        "panel.eng.tab.acoustics":       "Акустика",
        "panel.eng.tab.underfloor":      "Тёплый пол",
        "panel.eng.tab.fancoils":        "Фанкойлы",
        "panel.eng.tab.vrf":             "VRF/VRV",
        "panel.eng.tab.energy":          "Энергия (8760 ч)",
        "panel.eng.common.error":        "Ошибка",
        "panel.eng.common.no_data":      "Нет данных. Нажмите «Рассчитать».",

        # Psychro
        "panel.eng.psy.ahu":             "AHU:",
        "panel.eng.psy.mode":            "Режим:",
        "panel.eng.psy.mode.winter":     "Зима",
        "panel.eng.psy.mode.summer":     "Лето",
        "panel.eng.psy.mode.trans":      "Межсезонье",
        "panel.eng.psy.btn_chart":       "i-d диаграмма",
        "panel.eng.psy.btn_chart_tt":    "Показать диаграмму Молье с точками процесса для текущей AHU",
        "panel.eng.psy.btn_run":         "▶  Рассчитать все режимы",
        "panel.eng.psy.btn_table":       "Таблица",
        "panel.eng.psy.col.point":       "Точка",
        "panel.eng.psy.col.t":           "T, °C",
        "panel.eng.psy.col.w":           "W, г/кг",
        "panel.eng.psy.col.rh":          "RH, %",
        "panel.eng.psy.col.h":           "H, кДж/кг",
        "panel.eng.psy.col.td":          "Td, °C",
        "panel.eng.psy.matplotlib":      "Установите matplotlib (pip install matplotlib) для просмотра i-d диаграммы.",
        "panel.eng.psy.run_first":       "Сначала запустите расчёт («▶ Рассчитать все режимы»).",
        "panel.eng.psy.install":         "Установите matplotlib для просмотра диаграммы.",
        "panel.eng.psy.status":          "Психрометрика AHU рассчитана",
        "panel.eng.psy.summary":         ("{name} [{mode}]: калорифер {qh:.1f} кВт, "
                                            "охладитель {qc:.1f} кВт (явная {qs:.1f}, "
                                            "скрытая {ql:.1f}); конденсат {cond:.1f} кг/ч"),

        # Duct
        "panel.eng.duct.info":           ("Детальная аэродинамическая сеть: построение из упрощённого "
                                            "расчёта и ручное редактирование. Двойной клик по участку — "
                                            "редактировать; «Диктующая ветвь» определяет требуемый напор "
                                            "вентилятора с запасом 10%."),
        "panel.eng.duct.net":            "Сеть:",
        "panel.eng.duct.btn_build":      "Построить из упрощённых сетей",
        "panel.eng.duct.btn_recompute":  "▶ Пересчитать",
        "panel.eng.duct.btn_add":        "➕ Добавить участок",
        "panel.eng.duct.btn_edit":       "Редактировать",
        "panel.eng.duct.btn_delete":     "Удалить",
        "panel.eng.duct.col.sys":        "Система",
        "panel.eng.duct.col.terms":      "Терминалов",
        "panel.eng.duct.col.q":          "Q вент., м³/ч",
        "panel.eng.duct.col.dp":         "ΔP вент., Па",
        "panel.eng.duct.col.v":          "v max, м/с",
        "panel.eng.duct.col.crit":       "Диктующая ветвь",
        "panel.eng.duct.col.id":         "ID",
        "panel.eng.duct.col.parent":     "Родитель",
        "panel.eng.duct.col.terminal":   "Терминал?",
        "panel.eng.duct.col.name":       "Имя",
        "panel.eng.duct.col.flow":       "Q, м³/ч",
        "panel.eng.duct.col.len":        "L, м",
        "panel.eng.duct.col.size":       "Размер",
        "panel.eng.duct.col.vel":        "v, м/с",
        "panel.eng.duct.col.dpf":        "Δp тр., Па",
        "panel.eng.duct.col.dpl":        "Δp мест., Па",
        "panel.eng.duct.col.dpt":        "Σ Δp, Па",
        "panel.eng.duct.parent_root":    "(корень)",
        "panel.eng.duct.terminal_yes":   "Да",
        "panel.eng.duct.terminal_no":    "—",
        "panel.eng.duct.terminal_dflt":  "терминал {i}",
        "panel.eng.duct.status_built":   "Построено сетей: {n}",
        "panel.eng.duct.no_net":         "Нет сети",
        "panel.eng.duct.no_net_msg":     "Нет выбранной сети для пересчёта.",
        "panel.eng.duct.calc_err":       "Ошибка расчёта",
        "panel.eng.duct.recomp_status":  "Сеть «{name}» пересчитана",
        "panel.eng.duct.new_net_title":  "Новая сеть",
        "panel.eng.duct.new_net_combo":  "Имя системы вентиляции:",
        "panel.eng.duct.new_net_text":   "Имя системы:",
        "panel.eng.duct.del_block_title":"Удаление невозможно",
        "panel.eng.duct.del_block_msg":  ("У участка «{eid}» есть потомки: {children}.\n"
                                            "Сначала удалите или переподключите их."),
        "panel.eng.duct.del_title":      "Удалить участок",
        "panel.eng.duct.del_msg":        "Удалить участок «{eid}»?",
        "panel.eng.duct.fan_label":      "Вентилятор: Q = {q} м³/ч, ΔP = {dp} Па",

        # Hydraulics
        "panel.eng.hyd.h_static":        "Статическая высота:",
        "panel.eng.hyd.btn_run":         "▶  Подобрать насосы и баки",
        "panel.eng.hyd.col.loop":        "Контур",
        "panel.eng.hyd.col.q":           "Q, м³/ч",
        "panel.eng.hyd.col.h":           "H, м",
        "panel.eng.hyd.col.pump":        "Насос",
        "panel.eng.hyd.col.p":           "P, Вт",
        "panel.eng.hyd.col.vtank":       "V_бак расч., л",
        "panel.eng.hyd.col.tank":        "Бак",
        "panel.eng.hyd.col.pmax":        "P_max, бар",
        "panel.eng.hyd.col.makeup":      "Подпитка, л/сут",
        "panel.eng.hyd.status":          "Гидравлика рассчитана",

        # Radiators
        "panel.eng.rad.family":          "Семейство:",
        "panel.eng.rad.family.all":      "Все",
        "panel.eng.rad.btn_run":         "▶  Подобрать радиаторы",
        "panel.eng.rad.col.no":          "№",
        "panel.eng.rad.col.space":       "Помещение",
        "panel.eng.rad.col.q":           "Q, Вт",
        "panel.eng.rad.col.model":       "Модель",
        "panel.eng.rad.col.height":      "Высота",
        "panel.eng.rad.col.size":        "Длина/секций",
        "panel.eng.rad.col.qfact":       "Q факт., Вт",
        "panel.eng.rad.col.margin":      "Запас, %",
        "panel.eng.rad.status":          "Радиаторы подобраны",
        "panel.eng.rad.sect":            "{n} секц.",
        "panel.eng.rad.mm":              "{n} мм",

        # Acoustics
        "panel.eng.ac.info":             ("Оценка LpA в обслуживаемой зоне и подбор шумоглушителя. "
                                            "Для детального расчёта по веткам используйте API "
                                            "acoustics.select_silencer с явной топологией."),
        "panel.eng.ac.btn_run":          "▶  Подобрать шумоглушители",
        "panel.eng.ac.col.ahu":          "AHU",
        "panel.eng.ac.col.norm":         "Норма Lp, дБА",
        "panel.eng.ac.col.lp":           "Lp, дБА",
        "panel.eng.ac.col.margin":       "Запас, дБА",
        "panel.eng.ac.col.silencer":     "Шумоглушитель",
        "panel.eng.ac.col.length":       "Длина, мм",
        "panel.eng.ac.col.dp":           "ΔP, Па",
        "panel.eng.ac.status":           "Акустика рассчитана",

        # Underfloor
        "panel.eng.uf.pitch":            "Шаг:",
        "panel.eng.uf.cover":            "Покрытие:",
        "panel.eng.uf.cover.tile":       "Плитка",
        "panel.eng.uf.cover.laminate":   "Ламинат",
        "panel.eng.uf.cover.parquet":    "Паркет",
        "panel.eng.uf.cover.carpet":     "Ковролин",
        "panel.eng.uf.cover.linoleum":   "Линолеум",
        "panel.eng.uf.zone":             "Зона:",
        "panel.eng.uf.zone.habitable":   "Жилая (≤29°C)",
        "panel.eng.uf.zone.bath":        "Ванная (≤33°C)",
        "panel.eng.uf.zone.edge":        "Краевая (≤35°C)",
        "panel.eng.uf.zone.corridor":    "Коридор (≤27°C)",
        "panel.eng.uf.zone.office":      "Офис (≤28°C)",
        "panel.eng.uf.btn_run":          "▶ Рассчитать контуры",
        "panel.eng.uf.col.no":           "№",
        "panel.eng.uf.col.space":        "Помещение",
        "panel.eng.uf.col.area":         "F, м²",
        "panel.eng.uf.col.pitch":        "Шаг",
        "panel.eng.uf.col.cover":        "Покрытие",
        "panel.eng.uf.col.tsurf":        "T пов., °C",
        "panel.eng.uf.col.tlim":         "Лимит, °C",
        "panel.eng.uf.col.q_m2":         "Q, Вт/м²",
        "panel.eng.uf.col.qfact":        "Q факт., Вт",
        "panel.eng.uf.col.pipe":         "L трубы, м",
        "panel.eng.uf.col.notes":        "Замечания",
        "panel.eng.uf.status":           "Тёплый пол рассчитан",
        "panel.eng.uf.summary":          "Контуров: {n}; Σ длина трубы: {pipe:.0f} м",
        "panel.eng.uf.pitch_mm":         "{n} мм",

        # Fancoils
        "panel.eng.fc.family":           "Семейство:",
        "panel.eng.fc.family.all":       "Все",
        "panel.eng.fc.pipes":            "Труб:",
        "panel.eng.fc.pipes.any":        "Любое",
        "panel.eng.fc.pipes.2":          "2-трубные",
        "panel.eng.fc.pipes.4":          "4-трубные",
        "panel.eng.fc.btn_run":          "▶ Подобрать фанкойлы",
        "panel.eng.fc.col.no":           "№",
        "panel.eng.fc.col.space":        "Помещение",
        "panel.eng.fc.col.qc":           "Q_х, Вт",
        "panel.eng.fc.col.qh":           "Q_т, Вт",
        "panel.eng.fc.col.model":        "Модель",
        "panel.eng.fc.col.family":       "Семейство",
        "panel.eng.fc.col.pipes":        "Труб",
        "panel.eng.fc.col.qc_fact":      "Q_х факт., Вт",
        "panel.eng.fc.col.margin":       "Запас, %",
        "panel.eng.fc.col.air":          "L воздуха",
        "panel.eng.fc.col.noise":        "Шум, дБА",
        "panel.eng.fc.status":           "Фанкойлы подобраны",

        # VRF
        "panel.eng.vrf.info":            ("Подбор внешних/внутренних блоков VRF с проверкой ограничений "
                                            "производителя (длины трасс, перепад высот, коэф. соединения)."),
        "panel.eng.vrf.group":           "Группировка:",
        "panel.eng.vrf.group.level":     "По уровню",
        "panel.eng.vrf.group.all":       "Все вместе",
        "panel.eng.vrf.indoor":          "Внутренний:",
        "panel.eng.vrf.indoor.cassette": "Кассетный",
        "panel.eng.vrf.indoor.duct":     "Канальный",
        "panel.eng.vrf.indoor.wall":     "Настенный",
        "panel.eng.vrf.indoor.any":      "Любой",
        "panel.eng.vrf.btn_run":         "▶ Подобрать VRF",
        "panel.eng.vrf.main_pipe":       "Магистраль:",
        "panel.eng.vrf.max_pipe":        "Макс. до внутреннего:",
        "panel.eng.vrf.dh_max":          "Δh макс:",
        "panel.eng.vrf.col.sys":         "Система",
        "panel.eng.vrf.col.outdoor":     "Внешний",
        "panel.eng.vrf.col.indoor":      "Внутр.",
        "panel.eng.vrf.col.index":       "Σ индекс",
        "panel.eng.vrf.col.kconn":       "K соед.",
        "panel.eng.vrf.col.qc":          "Q_х, кВт",
        "panel.eng.vrf.col.qh":          "Q_т, кВт",
        "panel.eng.vrf.col.corr":        "Корр.",
        "panel.eng.vrf.col.check":       "Проверка",
        "panel.eng.vrf.col.sys2":        "Система",
        "panel.eng.vrf.col.space":       "Помещение",
        "panel.eng.vrf.col.idx":         "Индекс",
        "panel.eng.vrf.col.qc_w":        "Q_х, Вт",
        "panel.eng.vrf.col.dliq":        "Ø жидк.",
        "panel.eng.vrf.col.dgas":        "Ø газ",
        "panel.eng.vrf.col.indoor_model":"Внутренний",
        "panel.eng.vrf.status":          "VRF подобран",
        "panel.eng.vrf.ok":              "✓ OK",
        "panel.eng.vrf.warn":            "⚠ {n}",

        # Energy
        "panel.eng.en.info":             ("Симуляция 8760 часов: синтез почасовой T_наружного из ГСОП, "
                                            "расписания занятости по типу помещения, тепловая масса. "
                                            "Результат — годовое потребление и пиковые нагрузки."),
        "panel.eng.en.tau":              "Тепловая масса τ:",
        "panel.eng.en.setback":          "Ночное отступление:",
        "panel.eng.en.btn_chart":        "График года",
        "panel.eng.en.btn_chart_tt":     "Переключить таблицу / график",
        "panel.eng.en.btn_run":          "▶ Симулировать год",
        "panel.eng.en.btn_table":        "Таблица",
        "panel.eng.en.col.param":        "Параметр",
        "panel.eng.en.col.value":        "Значение",
        "panel.eng.en.matplotlib":       "Установите matplotlib для графиков.",
        "panel.eng.en.run_first":        "Сначала запустите симуляцию.",
        "panel.eng.en.install":          "Установите matplotlib для просмотра графика.",
        "panel.eng.en.status_err":       "Ошибка симуляции",
        "panel.eng.en.status":           "Годовая симуляция выполнена",
        "panel.eng.en.empty":            "Нет данных. Нажмите «Симулировать год».",
        "panel.eng.en.chart.t_year":     "Годовая T (среднесуточная)",
        "panel.eng.en.chart.t_ext":      "T нар., °C",
        "panel.eng.en.chart.qd_year":    "Годовые нагрузки (средние по суткам)",
        "panel.eng.en.chart.day":        "День года",
        "panel.eng.en.chart.q_avg":      "Q средн., кВт",
        "panel.eng.en.chart.heat":       "Отопление",
        "panel.eng.en.chart.cool":       "Охлаждение",
        "panel.eng.en.row.spaces":       "Помещений",
        "panel.eng.en.row.area":         "Площадь, м²",
        "panel.eng.en.row.e_heat":       "Σ отопление, кВт·ч/год",
        "panel.eng.en.row.e_cool":       "Σ охлаждение, кВт·ч/год",
        "panel.eng.en.row.e_heat_m2":    "Удельное отопление, кВт·ч/(м²·год)",
        "panel.eng.en.row.e_cool_m2":    "Удельное охлаждение, кВт·ч/(м²·год)",
        "panel.eng.en.row.e_total_m2":   "Удельное Σ, кВт·ч/(м²·год)",
        "panel.eng.en.row.q_peak_heat":  "Q пик отопление, кВт",
        "panel.eng.en.row.q_peak_cool":  "Q пик охлаждение, кВт",
        "panel.eng.en.row.t_peak_heat":  "Время пика отопления",
        "panel.eng.en.row.t_peak_cool":  "Время пика охлаждения",
        "panel.eng.en.row.h_peak_heat":  "Часов на пике (≥90%) отопл.",
        "panel.eng.en.row.h_peak_cool":  "Часов на пике (≥90%) охл.",
        "panel.eng.en.row.h_heat":       "Часов отопит. сезона",
        "panel.eng.en.row.h_cool":       "Часов охлажд. сезона",
        "panel.eng.en.summary":          ("Σ {total:.1f} кВт·ч/(м²·год) · "
                                            "пики Q_h={qh:.1f} кВт / Q_c={qc:.1f} кВт · "
                                            "сезоны: {hh} / {ch} часов"),

        # ========== Palette / city combo ==========
        "palette.search_ph":             "Введите команду или поиск…  (Esc — закрыть)",

        # ========== Export center ==========
        "export.title":                  "Экспорт",
        "export.h1":                     "Экспорт результатов",
        "export.sub":                    "Выберите формат и путь сохранения.",
        "export.path_ph":                "Файл сохранения…",
        "export.browse":                 "Обзор…",
        "export.open_folder":            "Открыть папку после сохранения",
        "export.btn_close":              "Закрыть",
        "export.btn_export":             "Экспортировать",
        "export.dlg_save":               "Сохранить как",
        "export.no_data.title":          "Нет данных",
        "export.no_data.msg":            "Загрузите проект и выполните расчёт.",
        "export.no_path.title":          "Нет пути",
        "export.no_path.msg":            "Укажите файл сохранения.",
        "export.err.title":              "Ошибка экспорта",
        "export.fmt.excel.title":        "Полный Excel-отчёт",
        "export.fmt.excel.desc":         ("14 листов: помещения, ограждения, сводки, ГВС, энергопаспорт, "
                                            "точка росы, воздуховоды, трубы."),
        "export.fmt.excel.name":         "HVAC_{name}.xlsx",
        "export.fmt.pdf.title":          "PDF: пояснительная записка",
        "export.fmt.pdf.desc":           "До 12 разделов по заполненным данным проекта.",
        "export.fmt.pdf.name":           "Отчёт_{name}.pdf",
        "export.fmt.equipment.title":    "Сводная таблица оборудования",
        "export.fmt.equipment.desc":     "Сводка по помещениям + спецификации радиаторов/фанкойлов/диффузоров.",
        "export.fmt.equipment.name":     "Оборудование_{name}.xlsx",
        "export.fmt.revit.title":        "CSV для Revit (обратная запись)",
        "export.fmt.revit.desc":         ("Запустите revit_dynamo_apply_results.py в Dynamo — Q зима/лето "
                                            "запишутся в параметры помещений."),
        "export.fmt.revit.name":         "results_for_revit.csv",
        "export.fmt.spec.title":         "Спецификация по ГОСТ 21.110",
        "export.fmt.spec.desc":          ("Полная спецификация оборудования и материалов: котлы, AHU, "
                                            "радиаторы, фанкойлы, VRF, насосы, баки, шумоглушители, медь, "
                                            "трубы тёплого пола. Группировка по разделам ГОСТ 21.110-2013."),
        "export.fmt.spec.name":          "Спецификация_{name}.xlsx",
        "export.default_name":           "Project",

        # ========== Panel: Calculation ==========
        "panel.calc.title":         "Расчёт нагрузок",
        "panel.calc.subtitle":      ("Запустите расчёты последовательно или "
                                       "все сразу. Результаты обновятся во "
                                       "всех панелях."),
        "panel.calc.heat.title":    "Теплопотери и теплопоступления",
        "panel.calc.heat.desc":     ("СП 50.13330: расчёт по всем помещениям "
                                       "с учётом ориентации, угловых и "
                                       "верхних этажей."),
        "panel.calc.heat.btn":      "Пересчитать",
        "panel.calc.vent.title":    "Вентиляция",
        "panel.calc.vent.desc":     ("СП 60.13330: приток / вытяжка / зонты "
                                       "по типам помещений. Помещения с "
                                       "ручной правкой не пересчитываются."),
        "panel.calc.vent.btn":      "Рассчитать",
        "panel.calc.ahu.title":     "Нагрузка приточных установок",
        "panel.calc.ahu.desc":      ("Нагрузка на калориферы и охладители AHU "
                                       "с учётом рекуператора."),
        "panel.calc.ahu.btn":       "Рассчитать",
        "panel.calc.all.title":     "Полный расчёт",
        "panel.calc.all.desc":      "Последовательно: нагрузки → вентиляция → AHU.",
        "panel.calc.all.btn":       "Всё сразу",
        "panel.calc.summary":       "Сводка",
        "panel.calc.status.done":   "✓ Готово",
        "panel.calc.status.not_done":"не выполнен",
        "panel.calc.validate.no_data":  ("Загрузите CSV или откройте проект, "
                                          "чтобы начать."),
        "panel.calc.validate.problems": ("⚠ Проблемы валидации: {n}. "
                                          "Первая: {first}"),
        "panel.calc.validate.ok":   "✓ Валидация без замечаний.",
        "panel.calc.run.heat":      "Считаю нагрузки…",
        "panel.calc.run.vent":      "Считаю вентиляцию…",
        "panel.calc.run.ahu":       "Считаю AHU…",
        "panel.calc.run.all":       "Полный расчёт…",
        "panel.calc.run.done":      "Расчёт завершён",
        "panel.calc.run.err":       "Ошибка расчёта",
        "panel.calc.summary.loss":      "Σ теплопотери",
        "panel.calc.summary.gain":      "Σ теплопоступления",
        "panel.calc.summary.area":      "Общая площадь",
        "panel.calc.summary.density":   "Удельные потери",
        "panel.calc.summary.supply":    "Σ приток",
        "panel.calc.summary.exhaust":   "Σ вытяжка",
    },

    "uz": {
        # ========== Welcome ==========
        "welcome.title":         "HVAC Calculator-ga xush kelibsiz",
        "welcome.subtitle":      ("Issiqlik yo‘qotish, ventilyatsiya, IIT va "
                                   "energetik pasport hisoblari (СП va КМК "
                                   "bo‘yicha). Nimadan boshlaymiz?"),
        "welcome.action_open":   "📂  Loyihani ochish",
        "welcome.action_open_desc": "Avval saqlangan .hvac.json faylini yuklash",
        "welcome.action_csv":    "📥  Revit'dan yuklab olish (CSV)",
        "welcome.action_csv_desc": "Dynamo'dan spaces.csv + thermal.csv import",
        "welcome.action_new":    "🆕  Bo‘sh loyiha yaratish",
        "welcome.action_new_desc":"Revit'siz xonalarni qo‘lda kiritish",
        "welcome.action_template":"📐  Tipik bino shablonidan",
        "welcome.action_template_desc": ("Maktab, mehmonxona, savdo markazi, "
                                          "turar joy, ofis"),
        "welcome.hint":          ("Maslahat: Ctrl+K — buyruq paneli, "
                                   "F5 — qayta hisoblash, Ctrl+S — saqlash."),

        # ========== Sidebar ==========
        "sidebar.home":          "Bosh sahifa",
        "sidebar.data":          "Loyiha ma'lumotlari",
        "sidebar.spaces":        "Xonalar",
        "sidebar.constructions": "Konstruksiyalar",
        "sidebar.calculation":   "Yuklamalar hisobi",
        "sidebar.ventilation":   "Ventilyatsiya",
        "sidebar.zones":         "Zonalar va tizimlar",
        "sidebar.equipment":     "Jihozlar (tizimlar)",
        "sidebar.room_equipment":"Xonalardagi jihozlar",
        "sidebar.smoke":         "Tutun chiqarish",
        "sidebar.charts":        "Grafiklar",
        "sidebar.extensions":    "Kengaytmalar v3.7",
        "sidebar.engineering":   "Mukammal injiniring v4.1",

        # ========== Topbar ==========
        "topbar.recalc":         "Qayta hisoblash",
        "topbar.save":           "Saqlash",
        "topbar.export":         "Eksport",
        "topbar.theme":          "Mavzu",
        "topbar.no_project":     "Loyihasiz",
        "topbar.lang_tooltip":   "Tilni almashtirish: RU ⇄ UZ  (Переключить язык)",
        "topbar.lang_tooltip_current":   "Joriy: {label}. Bosing — almashtirish (RU ⇄ UZ)",
        "topbar.theme_tooltip":  "Mavzuni almashtirish  (Ctrl+T)",

        # ========== Menu Файл ==========
        "menu.file":             "Fayl",
        "menu.view":             "Ko‘rinish",
        "menu.calc":             "Hisoblash",
        "menu.file.new":         "Yangi bo‘sh loyiha",
        "menu.file.open":        "Loyihani ochish…",
        "menu.file.csv":         "Revit'dan CSV import…",
        "menu.file.save":        "Loyihani saqlash",
        "menu.file.export":      "Eksport…",
        "menu.file.quit":        "Chiqish",
        "menu.file.recent":      "So‘nggi",

        # ========== Engineering tabs ==========
        "eng.title":             "Mukammal injiniring (v4.1 + v4.2)",
        "eng.psychro":           "AHU psixrometrika",
        "eng.duct":              "Tarmoq aerodinamikasi",
        "eng.hydraulics":        "Isitish gidravlikasi",
        "eng.radiators":         "Radiatorlar",
        "eng.acoustics":         "Akustika",
        "eng.underfloor":        "Issiq pol",
        "eng.fancoils":          "Fankoyllar",
        "eng.vrf":               "VRF/VRV",

        # ========== Кнопки общего назначения ==========
        "btn.add":               "Qo‘shish",
        "btn.edit":              "Tahrirlash",
        "btn.delete":            "O‘chirish",
        "btn.duplicate":         "Nusxalash",
        "btn.compute":           "Hisoblash",
        "btn.run":               "Ishga tushirish",
        "btn.cancel":            "Bekor qilish",
        "btn.ok":                "OK",
        "btn.close":             "Yopish",
        "btn.apply":             "Qo‘llash",

        # ========== Статусы ==========
        "status.ready":          "Tayyor",
        "status.computing":      "Hisoblanmoqda…",
        "status.done":           "Tayyor",

        # ========== Чек-лист ==========
        "checklist.title":              "Loyiha tayyorligi",
        "checklist.step_csv":           "CSV / loyiha yuklangan",
        "checklist.step_city":          "Shahar / iqlim tanlangan",
        "checklist.step_u":             "U qiymatlar tasdiqlangan",
        "checklist.step_zones":         "Zonalar belgilangan",
        "checklist.step_calc":          "Yuklamalar hisobi bajarilgan",
        "checklist.step_vent":          "Ventilyatsiya hisoblangan",
        "checklist.csv_hint":           "{n} ta xona",
        "checklist.csv_hint_empty":     "yuklanmagan",
        "checklist.city_hint_empty":    "—",
        "checklist.u_hint":             "{n} ta tur",
        "checklist.u_hint_empty":       "katalog bo‘sh",
        "checklist.zones_hint":         "{n} ta zona",
        "checklist.zones_hint_empty":   "yo‘q",
        "checklist.calc_hint":          "Σ {kw:.1f} kVt",
        "checklist.calc_hint_empty":    "bajarilmagan",
        "checklist.vent_hint":          "Σ {m3h} m³/soat",
        "checklist.vent_hint_empty":    "bajarilmagan",

        # ========== Языки ==========
        "lang.ru":               "Ruscha",
        "lang.uz":                "O‘zbekcha (lotin)",

        # ========== Категории команд ==========
        "cmd.cat.nav":           "Navigatsiya",
        "cmd.cat.file":          "Fayl",
        "cmd.cat.calc":          "Hisoblash",
        "cmd.cat.view":          "Ko‘rinish",
        "cmd.go_prefix":         "O‘tish: ",

        # ========== Команды: Файл ==========
        "cmd.file.new":          "Yangi bo‘sh loyiha",
        "cmd.file.open":         "Loyihani ochish…",
        "cmd.file.csv":          "Revit'dan CSV import…",
        "cmd.file.save":         "Loyihani saqlash",
        "cmd.file.export":       "Eksport…",
        "cmd.file.quit":         "Chiqish",

        # ========== Команды: Расчёт ==========
        "cmd.calc.heat":         "Yuklamalarni qayta hisoblash",
        "cmd.calc.vent":         "Ventilyatsiyani hisoblash",
        "cmd.calc.ahu":          "AHU ni hisoblash",
        "cmd.calc.all":          "To‘liq hisob",

        # ========== Команды: Вид ==========
        "cmd.view.theme":        "Mavzu (qorong‘i/yorug‘) almashtirish",
        "cmd.view.palette":      "Buyruq paneli",
        "cmd.view.lang_ru":      "Til: Ruscha",
        "cmd.view.lang_uz":      "Til: O‘zbek (lotin)",

        # ========== Меню ==========
        "menu_bar.file":         "&Fayl",
        "menu_bar.view":         "&Ko‘rinish",
        "menu_bar.calc":         "&Hisoblash",
        "menu.lang_submenu":     "🌐  Til / Язык",

        # ========== Статус-бар ==========
        "status.calc_done":      "Hisob bajarildi",
        "status.no_data_for_calc": "Hisob uchun ma'lumot yo‘q",
        "status.loaded_spaces":  "Yuklangan xonalar: {n}",
        "status.kw_summary":     "Σ qish {h:.1f} kVt · Σ yoz {c:.1f} kVt",
        "status.lang_switched":  "Til o‘zgartirildi: O‘zbek (lotin)",
        "status.autosave_done":  "Avto-saqlash: {name}",
        "status.autosave_error": "Avto-saqlash: xato {err}",
        "status.template_applied": ("Shablondan yaratildi: «{title}», "
                                     "xonalar: {n}"),

        # ========== QMessageBox ==========
        "dialog.file_not_found.title": "Fayl topilmadi",
        "dialog.file_not_found.body":  "Fayl mavjud emas:\n{path}",
        "dialog.error.title":          "Xato",
        "dialog.new_project.title":    "Yangi loyiha",
        "dialog.unsaved.body":         ("Saqlanmagan o‘zgarishlar bor. "
                                         "Davom etilsinmi?"),
        "dialog.unsaved_close.body":   ("Saqlanmagan o‘zgarishlar bor. "
                                         "Saqlamasdan yopilsinmi?"),
        "dialog.no_data.title":        "Ma'lumot yo‘q",
        "dialog.no_data.body":         ("Eksportdan oldin loyihani yuklang "
                                         "yoki hisobni bajaring."),
        "dialog.quit.title":           "Chiqish",

        # ========== Recent files ==========
        "recent.empty":          "(bo‘sh)",

        # ========== Общие фильтры/виджеты ==========
        "filter.all":            "(barchasi)",
        "filter.not_set":        "— tanlanmagan —",
        "btn.pick":              "Tanlash…",
        "btn.import":            "Import…",
        "btn.template":          "Bino shabloni…",
        "btn.add_space":         "+ Xona",

        # ========== Panel: Data ==========
        "panel.data.title":      "Loyiha ma'lumotlari",
        "panel.data.subtitle":   "Iqlim, hisob parametrlari, geometriya manbalari.",
        "panel.data.project.title": "Loyiha",
        "panel.data.project.desc":  ("Loyiha nomi va qo‘llaniladigan "
                                       "hisob metodikasi."),
        "panel.data.field.name":    "Nomi:",
        "panel.data.field.name.ph": "Masalan: Chorsu turar-joy majmuasi, Blok B",
        "panel.data.field.method":  "Metodika:",
        "panel.data.climate.title": "Iqlim",
        "panel.data.climate.desc":  ("Hisob haroratlari "
                                       "(СП 131.13330 / КМК bo‘yicha)."),
        "panel.data.field.city":    "Shahar:",
        "panel.data.climate.t_heat_cap":  "t qish, °C",
        "panel.data.climate.t_cool_cap":  "t yoz, °C",
        "panel.data.climate.gsop_cap":    "GSOP₁₈, °C·sut",
        "panel.data.climate.solar_cap":   "Quyosh rad., Vt/m²",
        "panel.data.climate.override":    "Qo‘lda o‘zgartirish:",
        "panel.data.climate.t_heat_short":"t qish",
        "panel.data.climate.t_cool_short":"t yoz",
        "panel.data.sources.title": "Geometriya manbalari",
        "panel.data.sources.desc":  ("Revit-Dynamo'dan eksport qilingan CSV: "
                                      "spaces.csv (xonalar) va thermal.csv "
                                      "(devorlar)."),
        "panel.data.keep_overrides": ("Qayta yuklashda xonalarning qo‘lda "
                                       "kiritilgan o‘zgarishlarini saqlash"),
        "panel.data.btn_load_csv":  "📥  CSV yuklash",
        "panel.data.summary_loaded": ("✓ Yuklandi: {sp} ta xona · "
                                       "{el} ta devor · {co} ta tip konstruksiya"),
        "panel.data.actions.title": "Loyiha",
        "panel.data.actions.desc":  ("Avval saqlangan .hvac.json faylini "
                                      "ochish yoki yangisini yaratish."),
        "panel.data.btn_new":       "🆕  Yangi bo‘sh loyiha",
        "panel.data.btn_open":      "📂  .hvac.json faylini ochish…",
        "panel.data.btn_save":      "💾  Saqlash",
        "panel.data.btn_save_full": "Mustaqil saqlash…",
        "panel.data.dlg.pick_spaces":  "spaces.csv ni tanlang",
        "panel.data.dlg.pick_thermal": "thermal.csv ni tanlang",
        "panel.data.dlg.open_project": "Loyihani ochish",
        "panel.data.dlg.save_project": "Loyihani saqlash",
        "panel.data.dlg.save_full":    "Mustaqil loyihani saqlash",
        "panel.data.dlg.filter.hvac":  ("HVAC loyihasi (*.hvac.json);;"
                                         "JSON (*.json);;Hammasi (*)"),
        "panel.data.dlg.filter.csv":   "CSV (*.csv);;Hammasi (*)",
        "panel.data.dlg.filter.hvac_save": ("HVAC loyihasi (*.hvac.json);;"
                                              "JSON (*.json)"),
        "panel.data.err.csv_load":  "CSV ni yuklab bo‘lmadi",
        "panel.data.err.open":      "Loyihani ocha olmadim",
        "panel.data.err.save":      "Saqlab bo‘lmadi",
        "panel.data.err.save_full": "To‘liq loyihani saqlab bo‘lmadi",
        "panel.data.dialog.new_clear.body": ("Joriy loyiha tozalanadi. "
                                               "Davom etilsinmi?"),
        "panel.data.status.loading_csv":     "CSV yuklanmoqda…",
        "panel.data.status.climate_applied": "Iqlim qo‘llanildi: {name}",
        "panel.data.status.opened":          "Ochildi: {path}",
        "panel.data.status.saved":           "Saqlandi: {path}",
        "panel.data.status.saved_full":      "To‘liq loyiha saqlandi: {path}",
        "panel.data.suffix_new_project":     "Yangi loyiha",
        "panel.data.suffix_full":            "_to‘liq",

        # ========== Panel: Spaces ==========
        "panel.spaces.title":         "Xonalar",
        "panel.spaces.col.number":    "№",
        "panel.spaces.col.name":      "Nomi",
        "panel.spaces.col.level":     "Qavat",
        "panel.spaces.col.type":      "Turi",
        "panel.spaces.col.area":      "S, m²",
        "panel.spaces.col.volume":    "V, m³",
        "panel.spaces.col.t_heat":    "t qish",
        "panel.spaces.col.q_heat":    "Q qish, kVt",
        "panel.spaces.col.q_cool":    "Q yoz, kVt",
        "panel.spaces.col.density":   "Vt/m²",
        "panel.spaces.col.zone":      "Zona",
        "panel.spaces.search.ph":     "№ / nomi / turi bo‘yicha qidirish…",
        "panel.spaces.filter.level":  "Qavat:",
        "panel.spaces.filter.type":   "Turi:",
        "panel.spaces.filter.zone":   "Zona:",
        "panel.spaces.count_total":   "{n} ta xona",
        "panel.spaces.count_filtered":"{total} dan {visible} ta xona",
        "panel.spaces.count_empty":   "Yuklangan xonalar yo‘q",
        "panel.spaces.tooltip":       ("{number} · {name}\nQavat: {level}\n"
                                        "Turi: {type}{mod}"),
        "panel.spaces.tooltip.modified": " (qo‘lda kiritildi)",
        "panel.spaces.dlg.no_number.title": "№ yo‘q",
        "panel.spaces.dlg.no_number.body":  "Xona raqamini kiriting.",
        "panel.spaces.dlg.not_added":       "Qo‘shilmadi",
        "panel.spaces.dlg.delete.title":    "O‘chirish",
        "panel.spaces.dlg.delete.body":     "«{number} {name}» xonasi o‘chirilsinmi?",
        "panel.spaces.dlg.delete.elems":    ("\n\nShuningdek {n} ta devor "
                                              "o‘chiriladi."),
        "panel.spaces.dlg.import.title":    "Xonalar ro‘yxatini import qilish",
        "panel.spaces.dlg.import.filter":   ("Jadvallar (*.xlsx *.csv);;"
                                              "Excel (*.xlsx);;CSV (*.csv)"),
        "panel.spaces.dlg.import_err":      "Import xatosi",
        "panel.spaces.dlg.tpl_empty.title": "Bo‘sh",
        "panel.spaces.dlg.tpl_empty.body":  "Shablonda birorta xona yo‘q.",
        "panel.spaces.status.imported":     ("{path} dan {n} ta xona "
                                               "import qilindi."),
        "panel.spaces.status.tpl_created":  "Shablon bo‘yicha {n} ta xona yaratildi.",
        "panel.spaces.default_level":       "1-qavat",

        # ========== Common ==========
        "btn.refresh":            "Yangilash",
        "btn.recalc":             "Qayta hisoblash",
        "btn.search.ph":          "Qidirish…",
        "common.empty_no_data":   ("Ma'lumot yo‘q. Loyihani yuklang va "
                                    "hisobni bajaring."),
        "common.empty_no_results": ("Hisob natijalari yo‘q. "
                                      "«Yuklamalar hisobi»ga o‘ting."),
        "common.empty_no_spaces":  "Yuklangan xonalar yo‘q.",
        "common.recovery_yes":     "✓",
        "common.recovery_no":      "—",
        "common.not_yet":          "<i>Hisob hali bajarilmagan.</i>",

        # ========== Panel: Charts ==========
        "panel.charts.title":      "Grafiklar",
        "panel.charts.err.draw":   "Grafik chizishda xato:\n{err}",

        # ========== Panel: Room equipment ==========
        "panel.room_eq.title":     "Xonalardagi jihozlar",
        "panel.room_eq.subtitle":  ("Radiatorlar, fankoyllar, diffuzorlar — "
                                     "xonada nima jismonan o‘rnatilgan. "
                                     "Hisobdan keyin to‘ldiriladi."),
        "panel.room_eq.col.number":    "№",
        "panel.room_eq.col.name":      "Nomi",
        "panel.room_eq.col.q_heat":    "Q qish, kVt",
        "panel.room_eq.col.terminal":  "Radiator/fankoyl",
        "panel.room_eq.col.power":     "Quvvat, Vt",
        "panel.room_eq.col.qty":       "Soni",
        "panel.room_eq.col.diffuser":  "Havo taqsim.",
        "panel.room_eq.col.diff_qty":  "Soni",

        # ========== Panel: Equipment ==========
        "panel.equipment.title":   "Jihozlar (tizimlar)",
        "panel.equipment.subtitle": ("Isitish / sovutish / ventilyatsiya "
                                      "tizimlari katalogi. Tizimlar «Zonalar va "
                                      "tizimlar»da zona belgilanganda "
                                      "avtomatik yaratiladi."),
        "panel.equipment.tab.heat":  "Isitish",
        "panel.equipment.tab.cool":  "Sovutish",
        "panel.equipment.tab.ahu":   "Ventilyatsiya (AHU)",
        "panel.equipment.tab.load":  "AHU yuklamasi",
        "panel.equipment.col.name":   "Tizim nomi",
        "panel.equipment.col.type":   "Turi",
        "panel.equipment.col.t_sup":  "t kelish, °C",
        "panel.equipment.col.t_ret":  "t qaytish, °C",
        "panel.equipment.col.fuel":   "Yoqilg‘i",
        "panel.equipment.col.eff":    "FIK",
        "panel.equipment.col.cop":    "COP",
        "panel.equipment.col.refr":   "Sovutgich",
        "panel.equipment.col.ahu":    "AHU nomi",
        "panel.equipment.col.recov":  "Rekuperator",
        "panel.equipment.col.eta_w":  "η qish",
        "panel.equipment.col.eta_s":  "η yoz",
        "panel.equipment.col.t_in_w": "t kelish qish, °C",
        "panel.equipment.col.q_win":  "Q qish, kVt",
        "panel.equipment.col.q_sens": "Q yoz (oshkor), kVt",
        "panel.equipment.col.q_lat":  "Q yoz (yashirin), kVt",
        "panel.equipment.col.flow":   "Sarf, m³/soat",

        # ========== Panel: Ventilation ==========
        "panel.ventilation.title":    "Ventilyatsiya",
        "panel.ventilation.btn_run":  "▶  Ventilyatsiyani qayta hisoblash",
        "panel.ventilation.summary_card.title":    "Tizimlar bo‘yicha xulosa",
        "panel.ventilation.summary_card.subtitle": "Havo sarflari yig‘indisi.",
        "panel.ventilation.summary_html": (
            "<b>Σ Kelish:</b> {sup} m³/soat &nbsp;·&nbsp; "
            "<b>Σ So‘rish:</b> {exh} m³/soat &nbsp;·&nbsp; "
            "<b>Σ Soyabon:</b> {hood} m³/soat &nbsp;·&nbsp; "
            "<b>Muvozanat:</b> {diff} m³/soat"
        ),
        "panel.ventilation.summary_not_yet": (
            "<i>Hisob hali bajarilmagan. "
            "«Ventilyatsiyani qayta hisoblash» ni bosing.</i>"
        ),
        "panel.ventilation.col.number":  "№",
        "panel.ventilation.col.name":    "Nomi",
        "panel.ventilation.col.level":   "Qavat",
        "panel.ventilation.col.type":    "Turi",
        "panel.ventilation.col.area":    "S, m²",
        "panel.ventilation.col.supply":  "Kelish, m³/soat",
        "panel.ventilation.col.exhaust": "So‘rish, m³/soat",
        "panel.ventilation.col.hood":    "Soyabon, m³/soat",
        "panel.ventilation.col.ach":     "ACH, 1/soat",
        "panel.ventilation.col.imbal":   "Muvozanat",

        # ========== Panel: Properties ==========
        "panel.props.empty":      "—",
        "panel.props.nothing":    "Tanlanmadi",
        "panel.props.hint":       ("Tahrirlash uchun chap jadvalda xonani "
                                    "tanlang."),
        "panel.props.subtitle":   "Qavat {level} · {area:.1f} m² · {volume:.1f} m³{mod}",
        "panel.props.user_mark":  "  · qo‘lda kiritildi",
        "panel.props.field.type": "Xona turi:",
        "panel.props.field.t_heat":  "t qish:",
        "panel.props.field.t_cool":  "t yoz:",
        "panel.props.field.occup":   "Bandlik:",
        "panel.props.field.light":   "Yoritish:",
        "panel.props.field.equip":   "Jihoz:",
        "panel.props.field.inf":     "Infiltratsiya:",
        "panel.props.field.flags":   "Belgilar:",
        "panel.props.suffix.people": " kishi",
        "panel.props.flag.corner":   "burchakli",
        "panel.props.flag.roof":     "tom ostida",
        "panel.props.flag.floor":    "tuproqqa tegishli pol",
        "panel.props.results.title": "Hisob natijalari",
        "panel.props.results.not_yet": ("<i>Hisob hali bajarilmagan. "
                                          "F5 yoki «Qayta hisoblash» bosing.</i>"),
        "panel.props.heat_loss_label":  "Issiqlik yo‘qotish (qish)",
        "panel.props.heat_gain_label":  "Issiqlik kelishi (yoz)",
        "panel.props.block_header":     "<b>{title}: {kw:.2f} kVt</b>",
        "panel.props.block_row":        "&nbsp;&nbsp;{key}: {w:.0f} Vt",

        # ========== Panel: Extensions ==========
        "panel.ext.title":     "Kengaytmalar v3.7",
        "panel.ext.subtitle":  ("IIT, energetik pasport, shudring nuqtasini "
                                 "tekshirish, havo o‘tkazgich va trubalarni "
                                 "tanlash. Har bir hisob alohida ishga "
                                 "tushiriladi."),
        "panel.ext.dhw.title":     "IIT",
        "panel.ext.dhw.desc":      ("Sutkalik sarf, cho‘qqi yuklamasi, "
                                     "bak hajmi. Norma: СП 30.13330."),
        "panel.ext.energy.title":  "Energetik pasport",
        "panel.ext.energy.desc":   ("Yillik iste'mol, solishtirma "
                                     "ko‘rsatkichlar, A++…E sinfi."),
        "panel.ext.dew.title":     "Shudring nuqtasi",
        "panel.ext.dew.desc":      ("Tashqi devorlarni kondensatga "
                                     "tekshirish. Norma: СП 50 Ilova Е."),
        "panel.ext.ducts.title":   "Havo o‘tkazgichlarini tanlash",
        "panel.ext.ducts.desc":    ("Tavsiya etilgan tezliklar bo‘yicha "
                                     "kesim Ø / AxB tanlash."),
        "panel.ext.pipes.title":   "Trubalarni tanlash",
        "panel.ext.pipes.desc":    ("Isitish trubalari DN ni СП 60 / Altshul "
                                     "bo‘yicha tanlash."),
        "panel.ext.btn_run":       "Ishga tushirish",
        "panel.ext.summary.empty": "Hisob hali bajarilmagan.",
        "panel.ext.status.ok":     "Tayyor: {title}",
        "panel.ext.status.err":    "Xato ({title}): {err}",
        "panel.ext.sum.dhw":       ("IIT tizimlari: {n}\nΣ sutkalik hajm: "
                                     "{v:.1f} m³/sut\nΣ cho‘qqi yuklama: "
                                     "{q:.1f} kVt"),
        "panel.ext.sum.energy":    ("Energiya samaradorligi sinfi: {cls}\n"
                                     "Solishtirma iste'mol: {q:.1f} "
                                     "kVt·soat/(m²·yil)\nNormaga nisbatan "
                                     "og‘ish: {dev:+.1f} %"),
        "panel.ext.sum.dew":       ("Tekshirilgan devorlar: {n}\n"
                                     "Kondensat xavfi bor: {risky}"),
        "panel.ext.sum.ducts":     ("Havo o‘tkazgich tarmoqlari: {n}\n"
                                     "Uchastkalar: {s}"),
        "panel.ext.sum.pipes":     "Truba tarmoqlari: {n}\nUchastkalar: {s}",

        # ========== Panel: Zones ==========
        "panel.zones.title":            "Zonalar va tizimlar",
        "panel.zones.auto.title":       "Zonalarni avtomatik belgilash",
        "panel.zones.auto.desc":        ("Xonalarni tanlangan mezon bo‘yicha "
                                          "isitish / sovutish / ventilyatsiya "
                                          "tizimlariga bo‘lish."),
        "panel.zones.criterion":        "Mezon:",
        "panel.zones.apply_to":         "Qo‘llash:",
        "panel.zones.overwrite":        "Mavjudlarini qayta yozish",
        "panel.zones.btn_apply":        "Qo‘llash",
        "panel.zones.mode.by_prefix":   ("№ prefiksi bo‘yicha "
                                          "(B01-001 → Blok B01)"),
        "panel.zones.mode.by_level":    "Qavat bo‘yicha",
        "panel.zones.mode.by_type":     "Turlari guruhi bo‘yicha",
        "panel.zones.system.all":       "Hamma tizimlar",
        "panel.zones.system.heating":   "Faqat isitish",
        "panel.zones.system.cooling":   "Faqat sovutish",
        "panel.zones.system.ventilation":"Faqat ventilyatsiya",
        "panel.zones.summary.title":    "Zonalar bo‘yicha xulosa",
        "panel.zones.summary.desc":     ("Har bir zonadagi yuklamalar, "
                                          "havo sarfi va xonalar soni."),
        "panel.zones.summary.heating":  "Isitish",
        "panel.zones.summary.cooling":  "Sovutish",
        "panel.zones.summary.vent":     "Ventilyatsiya",
        "panel.zones.col.zone":         "Zona",
        "panel.zones.col.n_spaces":     "Xonalar",
        "panel.zones.col.area":         "S, m²",
        "panel.zones.col.q_heat":       "Q isit., kVt",
        "panel.zones.col.q_cool":       "Q sov., kVt",
        "panel.zones.col.supply":       "Kelish, m³/soat",
        "panel.zones.status.assigned":  "Belgilangan zonalar: {n}",

        # ========== Panel: Constructions ==========
        "panel.constructions.title":          "Konstruksiyalar",
        "panel.constructions.count":          "{total} ta tur · ishlatilmoqda {used} · ishlatilmagan {unused}",
        "panel.constructions.count_empty":    "Katalog bo‘sh",
        "panel.constructions.hint":           ("<b>U/SHGC/Izoh</b> ustida ikki marta bosing — tahrirlash. "
                                                "<b>R</b> ustida ikki marta bosing — qatlamlar tahrirchisi. "
                                                "Bir nechta qatorni belgilang va <b>«Preset qo‘llash»</b> yoki "
                                                "<b>«Ommaviy U»</b> tugmasini bosing."),
        "panel.constructions.search_ph":      "Kategoriya / oila / tur bo‘yicha qidirish…",
        "panel.constructions.filter_all":     "Hamma kategoriyalar",
        "panel.constructions.btn_preset":     "Preset qo‘llash…",
        "panel.constructions.btn_bulk_u":     "Ommaviy U…",
        "panel.constructions.btn_layers":     "Qatlamlarni tahrirlash…",
        "panel.constructions.btn_remove":     "Ishlatilmaganini o‘chirish",
        "panel.constructions.btn_export":     "Katalogni eksport…",
        "panel.constructions.btn_import":     "Katalogni import…",
        "panel.constructions.col.category":   "Kategoriya",
        "panel.constructions.col.family":     "Oila",
        "panel.constructions.col.type":       "Tur",
        "panel.constructions.col.th":         "δ, mm",
        "panel.constructions.col.u":          "U",
        "panel.constructions.col.r":          "R",
        "panel.constructions.col.rnorm":      "R_norm",
        "panel.constructions.col.shgc":       "SHGC",
        "panel.constructions.col.used":       "Ishlatildi",
        "panel.constructions.col.area":       "Σ yuza, m²",
        "panel.constructions.col.note":       "Izoh",
        "panel.constructions.note_manual_u":  " [U qo‘lda kiritildi]",
        "panel.constructions.tt.layers":      "<b>Qatlamlar:</b>",
        "panel.constructions.tt.layer_r":     "{i}. {material} — R = {r:.3f}",
        "panel.constructions.tt.layer_full":  "{i}. {material} — {th:.0f} mm, λ = {lam:g}",
        "panel.constructions.tt.rnorm":       "SP 50.13330 jadval 3, GSOP = {gsop:.0f} °S·kun",
        "panel.constructions.dlg.preset_title": "Presetni qo‘llash",
        "panel.constructions.dlg.category":   "Kategoriya:",
        "panel.constructions.dlg.preset":     "Preset:",
        "panel.constructions.dlg.all":        "Hammasi",
        "panel.constructions.dlg.preset_desc": "{description}<br><i>Kategoriya: {category}, qatlamlar: {n}</i>",
        "panel.constructions.msg.layers_pick": "Qatlamlarni tahrirlash uchun bitta qatorni belgilang.",
        "panel.constructions.msg.layers_one": "Qatlamlar tahrirchisi bitta konstruksiya bilan ishlaydi. Bitta qatorni belgilang.",
        "panel.constructions.msg.preset_pick": "Presetni qo‘llash uchun bir yoki bir nechta qatorni belgilang.",
        "panel.constructions.msg.bulk_pick":  "Bir yoki bir nechta qatorni belgilang.",
        "panel.constructions.msg.bulk_prompt": "{n} ta qator uchun yangi U qiymati, Vt/(m²·K):",
        "panel.constructions.msg.unused_none": "Barcha konstruksiyalar ishlatilmoqda.",
        "panel.constructions.msg.remove_ask": "Katalogdan biror element havola qilmagan {n} ta konstruksiyani o‘chirish kerakmi?",
        "panel.constructions.msg.import_strategy": "Kalitlar mos kelganda nima qilish kerak?",
        "panel.constructions.import.merge":   "merge — faqat yangilarini qo‘shish",
        "panel.constructions.import.update":  "update_u — U/SHGC/qatlamlarni yangilash",
        "panel.constructions.import.replace": "replace — katalogni butunlay almashtirish",
        "panel.constructions.title.layers":   "Qatlamlar",
        "panel.constructions.title.preset":   "Preset",
        "panel.constructions.title.bulk":     "Ommaviy tahrirlash",
        "panel.constructions.title.cleanup":  "Tozalash",
        "panel.constructions.title.remove":   "Ishlatilmaganini o‘chirish",
        "panel.constructions.title.import_strategy": "Import strategiyasi",
        "panel.constructions.title.export":   "Konstruksiyalar katalogini eksport",
        "panel.constructions.title.import":   "Konstruksiyalar katalogini import",
        "panel.constructions.title.import_err": "Import xatosi",
        "panel.constructions.status.preset":  "«{name}» preseti {n} ta konstruksiyaga qo‘llandi.",
        "panel.constructions.status.bulk":    "U = {u:.3f} qiymati {n} ta qatorga kiritildi.",
        "panel.constructions.status.removed": "{n} ta ishlatilmagan konstruksiya o‘chirildi.",
        "panel.constructions.status.exported": "{n} ta yozuv {path} ga eksport qilindi.",
        "panel.constructions.status.imported": "Import: qo‘shildi {added}, yangilandi {updated}, o‘tkazildi {skipped}.",

        # ========== Panel: Boundaries ==========
        "panel.boundaries.title":           "Toʻsiqlar",
        "panel.boundaries.title_for":       "Toʻsiqlar — {number} · {name}",
        "panel.boundaries.summary":         "{n} ta element · Σ tashqi yuza {area:.1f} m²",
        "panel.boundaries.col.category":    "Kategoriya",
        "panel.boundaries.col.construction":"Konstruksiya",
        "panel.boundaries.col.area":        "Yuza",
        "panel.boundaries.col.orient":      "Yo‘nalish",
        "panel.boundaries.col.u":           "U",
        "panel.boundaries.col.ext":         "Tashqi",
        "panel.boundaries.btn_wall":        "+ Devor",
        "panel.boundaries.btn_window":      "+ Deraza",
        "panel.boundaries.btn_door":        "+ Eshik",
        "panel.boundaries.btn_roof":        "+ Tom",
        "panel.boundaries.btn_floor":       "+ Pol",
        "panel.boundaries.btn_delete":     "O‘chirish",
        "panel.boundaries.dlg.title":       "Yangi to‘siq: {number} {name}",
        "panel.boundaries.dlg.category":    "Kategoriya:",
        "panel.boundaries.dlg.construction":"Konstruksiya:",
        "panel.boundaries.dlg.bnd_type":    "Chegara turi:",
        "panel.boundaries.dlg.bnd_ext":     "Tashqi",
        "panel.boundaries.dlg.bnd_int":     "Ichki",
        "panel.boundaries.dlg.area":        "Yuza:",
        "panel.boundaries.dlg.orient":      "Yo‘nalish:",
        "panel.boundaries.dlg.thickness":   "Qalinlik:",
        "panel.boundaries.tt.element":      "{cat}\n{family} / {type}\nelement_id: {eid}",
        "panel.boundaries.ext_yes":         "Ha",
        "panel.boundaries.ext_no":          "Yo‘q",
        "panel.boundaries.msg.pick_space_title": "Xonani tanlang",
        "panel.boundaries.msg.pick_space":  "Avval jadvalda xonani tanlang.",
        "panel.boundaries.msg.no_construction_title": "Konstruksiya yo‘q",
        "panel.boundaries.msg.no_construction": "Konstruksiyani tanlang yoki yarating.",
        "panel.boundaries.auto_note":       "Avtomatik yaratildi",

        # ========== Dialog: Layers editor ==========
        "dlg.layers.title":          "Qatlamlar: {key}",
        "dlg.layers.category":       "Kategoriya: <b>{category}</b>",
        "dlg.layers.col.material":   "Material",
        "dlg.layers.col.th":         "δ, mm",
        "dlg.layers.col.lambda":     "λ, Vt/(m·K)",
        "dlg.layers.col.r":          "R, m²K/Vt",
        "dlg.layers.btn_add":        "Qatlam qo‘shish",
        "dlg.layers.btn_delete":     "O‘chirish",
        "dlg.layers.btn_air":        "Havo qatlami",
        "dlg.layers.summary_title":  "<b>Xulosa</b>",
        "dlg.layers.summary":        ("R<sub>si</sub> = {rsi:.3f}<br>"
                                       "R<sub>se</sub> = {rse:.3f}<br>"
                                       "Σ R = <b>{r:.3f}</b> m²·K/Vt<br>"
                                       "U = <b>{u:.3f}</b> Vt/(m²·K)"),

        # ========== Dialog: Duct edge ==========
        "dlg.duct.title_new":        "Yangi havo o‘tkazgich uchastkasi",
        "dlg.duct.title_edit":       "Uchastka parametrlari: {edge_id}",
        "dlg.duct.gb_id":            "Identifikatsiya",
        "dlg.duct.id":               "Uchastka ID:",
        "dlg.duct.parent":           "Ota uchastka:",
        "dlg.duct.parent_root":      "(ildiz / ventilyatordan)",
        "dlg.duct.terminal_name":    "Terminal nomi:",
        "dlg.duct.terminal_ph":      "Xizmat ko‘rsatayotgan xona nomi (terminallar uchun)",
        "dlg.duct.is_terminal":      "Yakuniy uchastka (terminal)",
        "dlg.duct.gb_geom":          "Geometriya va sarf",
        "dlg.duct.flow":             "Sarf:",
        "dlg.duct.length":           "Uzunlik:",
        "dlg.duct.shape":            "Shakl:",
        "dlg.duct.shape.round":      "Dumaloq (round)",
        "dlg.duct.shape.rect":       "To‘rtburchak (rect)",
        "dlg.duct.diameter":         "Diametr:",
        "dlg.duct.width":            "Eni:",
        "dlg.duct.height":           "Balandligi:",
        "dlg.duct.gb_fittings":      "Mahalliy qarshiliklar (fittinglar)",
        "dlg.duct.btn_add":          "➕ Qo‘shish",
        "dlg.duct.btn_delete":       "O‘chirish",
        "dlg.duct.fit.col_kind":     "Tur",
        "dlg.duct.fit.col_qty":      "Soni",
        "dlg.duct.fit.col_zeta":     "ζ (ixt.)",
        "dlg.duct.fit.col_dp":       "Δp (Pa, ixt.)",
        "dlg.duct.fit.col_note":     "Izoh",
        "dlg.duct.fit.empty":        "(bo‘sh — ζ yoki Δp kiriting)",

        # ========== Dialog: Space (add / edit) ==========
        "dlg.space.title_new":       "Yangi xona",
        "dlg.space.number":          "Xona №:",
        "dlg.space.number_ph":       "Masalan, 101 yoki B01-105",
        "dlg.space.name":            "Nomi:",
        "dlg.space.name_ph":         "Masalan, «Mehmonxona 18 m²»",
        "dlg.space.level":           "Qavat:",
        "dlg.space.area":            "Yuza:",
        "dlg.space.height":          "Balandlik:",
        "dlg.space.type":            "Tur:",
        "dlg.space.lvl_1":           "1-qavat",
        "dlg.space.lvl_2":           "2-qavat",
        "dlg.space.lvl_3":           "3-qavat",
        "dlg.space.default_type":    "Boshqa",

        # ========== Dialog: Building template ==========
        "dlg.bldg.title":            "Turar joy uyi shabloni",
        "dlg.bldg.floors":           "Qavatlar:",
        "dlg.bldg.first_floor":      "Birinchi qavat №:",
        "dlg.bldg.apts":             "Qavatdagi kvartiralar:",
        "dlg.bldg.height":           "Xonalar balandligi:",
        "dlg.bldg.prefix":           "Qavat prefiksi:",
        "dlg.bldg.level_prefix":     "Qavat ",
        "dlg.bldg.composition":      "<b>Bitta kvartiraning tarkibi</b> (har bir qator — bitta xona):",
        "dlg.bldg.col_name":         "Xona nomi",
        "dlg.bldg.col_type":         "Tur",
        "dlg.bldg.col_area":         "Yuza, m²",
        "dlg.bldg.btn_add":          "Xona qo‘shish",
        "dlg.bldg.btn_delete":       "O‘chirish",
        "dlg.bldg.default_room":     "Xona",
        "dlg.bldg.default_type":     "Turar xona",
        "dlg.bldg.total":            "Jami xonalar: <b>{n}</b>, umumiy yuza ≈ <b>{area:.0f} m²</b>",
        "dlg.bldg.tpl.living":       "Mehmonxona",
        "dlg.bldg.tpl.bedroom1":     "Yotoqxona 1",
        "dlg.bldg.tpl.bedroom2":     "Yotoqxona 2",
        "dlg.bldg.tpl.kitchen":      "Oshxona",
        "dlg.bldg.tpl.bathroom":     "Hojatxona",
        "dlg.bldg.tpl.corridor":     "Yo‘lak",

        # ========== Dialog: Template ==========
        "dlg.tpl.title":             "Shablon asosida loyiha yaratish",
        "dlg.tpl.gb_list":           "Shablon",
        "dlg.tpl.choose":            "Shablonni tanlang…",
        "dlg.tpl.gb_common":         "Umumiy parametrlar",
        "dlg.tpl.project_name":      "Loyiha nomi:",
        "dlg.tpl.project_name_ph":   "Masalan, «Chorsu maktabi»",
        "dlg.tpl.project_name_hint": "Masalan, «{title}»",
        "dlg.tpl.city":              "Shahar (iqlim):",
        "dlg.tpl.default_city":      "Toshkent",
        "dlg.tpl.btn_create":        "Yaratish",
        "dlg.tpl.suffix.workplaces": " ish o‘rni",
        "dlg.tpl.suffix.cabinets":   " kabinet",
        "dlg.tpl.suffix.classes":    " sinf",
        "dlg.tpl.suffix.rooms":      " xona",
        "dlg.tpl.suffix.stars":      " ★",
        "dlg.tpl.suffix.m2":         " m²",
        "dlg.tpl.suffix.apts":       " kvartira",
        "dlg.tpl.suffix.floors":     " qavat",
        "dlg.tpl.row.workplaces":    "Ish o‘rinlari soni:",
        "dlg.tpl.row.cabinets":      "Kabinetlar soni:",
        "dlg.tpl.row.classes":       "Sinflar soni:",
        "dlg.tpl.row.rooms":         "Xonalar:",
        "dlg.tpl.row.stars":         "Yulduzlar:",
        "dlg.tpl.row.area":          "Umumiy yuza:",
        "dlg.tpl.row.apts":          "Kvartiralar:",
        "dlg.tpl.row.floors":        "Qavatlar:",

        # ========== Dialog: Smoke system ==========
        "dlg.smoke.title_new":       "Yangi SDU/SPV tizimi",
        "dlg.smoke.title_edit":      "Parametrlar: {name}",
        "dlg.smoke.gb_id":           "Identifikatsiya",
        "dlg.smoke.name":            "Nomi:",
        "dlg.smoke.type":            "Tur:",
        "dlg.smoke.purpose":         "Vazifasi:",
        "dlg.smoke.gb_method":       "Sarf hisobi usuli",
        "dlg.smoke.gb_common":       "Tutun va jihoz parametrlari",
        "dlg.smoke.t_smoke":         "Tutun harorati:",
        "dlg.smoke.makeup":          "Kompensatsiya ulushi:",
        "dlg.smoke.fire_rating":     "O‘tga chidamlilik sinfi:",
        "dlg.smoke.note":            "Izoh:",
        "dlg.smoke.norm.norm":       "Sarf normasi:",
        "dlg.smoke.norm.max_zone":   "Maks. zona yuzasi:",
        "dlg.smoke.kmk_zone.perim":  "P — o‘choq perimetri (maks 12):",
        "dlg.smoke.kmk_zone.layer":  "y — erkin zona balandligi:",
        "dlg.smoke.kmk_zone.ks":     "Ks (1.0 AUPT siz, 1.2 sprinklerlar bilan):",
        "dlg.smoke.kmk_zone.formula":"Formula: G = 676.8 · P · y^1.5 · Ks   [kg/soat]",
        "dlg.smoke.kmk_corr.n":      "n — KMK jadvali koeff.:",
        "dlg.smoke.kmk_corr.kd":     "Kd — eshik koeff. (1.0 = yo‘q):",
        "dlg.smoke.kmk_corr.formula":("Formula: G1 = 3420 · n^1.5  (eshiksiz)\n"
                                       "         G1 = 4300 · n^1.5 · Kd  (eshik bilan)   [kg/soat]"),
        "dlg.smoke.nfpa.hrr":        "Q — yong‘in quvvati (HRR):",
        "dlg.smoke.nfpa.frac":       "Konvektiv quvvat ulushi:",
        "dlg.smoke.nfpa.plume_h":    "z — tutun qatlamigacha balandlik:",
        "dlg.smoke.nfpa.formula":    ("Qc = α · Q\n"
                                       "z > zl:  m = 0.071·Qc^(1/3)·z^(5/3) + 0.0018·Qc   [kg/s]\n"
                                       "z ≤ zl:  m = 0.032·Qc^(3/5)·z"),
        "dlg.smoke.manual.l":        "Bitta tutun zonasi sarfi:",
        "dlg.smoke.supply.rate":     "Podpor sarfi:",
        "dlg.smoke.supply.pressure": "Ortiqcha bosim:",
        "dlg.smoke.hint.norm":       ("Soddalashtirilgan muhandislik yondashuvi. Dastlabki "
                                       "baholash uchun. Loyiha hujjati uchun amaldagi norma bilan "
                                       "tekshirilsin."),
        "dlg.smoke.hint.kmk_zone":   ("KMK 2.04.05-22, 20-ilova, f.(3). Yuzasi ≤ 1600 m² "
                                       "va o‘choq perimetri ≤ 12 m bo‘lgan xonalar uchun."),
        "dlg.smoke.hint.kmk_corr":   ("KMK 2.04.05-22, 20-ilova, f.(1)/(2). Yo‘laklar va "
                                       "xollar uchun. n vazifasiga qarab jadvaldan."),
        "dlg.smoke.hint.nfpa":       ("NFPA 92, b. 5.5.1. O‘qsimmetrik plyum. HRR va "
                                       "o‘choqdan tutun qatlamigacha balandlikni talab qiladi."),
        "dlg.smoke.hint.manual":     "Sarf qo‘lda kiritiladi (masalan, tipovoy loyiha asosida).",
        "dlg.smoke.hint.air":        "Himoyalanadigan hajm uchun norma bo‘yicha podpor sarfi.",
        "dlg.smoke.method.norm_per_m2":        "Sodda: sarf = yuza × norma",
        "dlg.smoke.method.kmk_zone_perimeter": "KMK 20-ilova f.(3): G = 676.8·P·y^1.5·Ks",
        "dlg.smoke.method.kmk_corridor":       "KMK 20-ilova f.(1)/(2): yo‘lak G1 = 3420·n^1.5",
        "dlg.smoke.method.nfpa_plume_axi":     "NFPA 92 b. 5.5.1: o‘qsimmetrik plyum",
        "dlg.smoke.method.manual":             "Sarfni qo‘lda kiritish",
        "dlg.smoke.method.stairs_pressure":    "Zinapoya podpor",
        "dlg.smoke.method.elevator_pressure":  "Lift shaxtasi podpor",
        "dlg.smoke.systype.smoke_removal":     "SDU — tutunni chiqarish",
        "dlg.smoke.systype.air_supply":        "SPV — havo podpor",
        "dlg.smoke.systype.compensation":      "Kompensatsiyalovchi havo",
        "dlg.smoke.purpose.parking":           "Avtoturargoh",
        "dlg.smoke.purpose.warehouse":         "Ombor",
        "dlg.smoke.purpose.corridor":          "Yo‘lak",
        "dlg.smoke.purpose.atrium":            "Atrium / odamlar to‘planish zali",
        "dlg.smoke.purpose.trading_hall":      "Savdo zali",
        "dlg.smoke.purpose.stairs":            "Zinapoya",
        "dlg.smoke.purpose.elevator":          "Lift shaxtasi",
        "dlg.smoke.purpose.vestibule":         "Tambur-shlyuz",
        "dlg.smoke.purpose.refuge":            "Nogironlar uchun xavfsizlik zonasi",

        # ========== Panel: Smoke ==========
        "panel.smoke.title":              "Tutunni chiqarish va podpor",
        "panel.smoke.card.params.title":  "Parametrlar",
        "panel.smoke.card.params.sub":    "Faol norma, yong‘in stsenariyi va tizimlar ustidagi umumiy amallar.",
        "panel.smoke.norm":               "Norma:",
        "panel.smoke.scenario":           "Stsenariy:",
        "panel.smoke.scenario.single":    "Bitta yong‘in o‘chog‘i",
        "panel.smoke.scenario.multiple":  "Bir vaqtda bir nechta zona (zaxira)",
        "panel.smoke.btn_assign":         "Avto-belgilash",
        "panel.smoke.btn_assign_tt":      ("Avtoturargoh, ombor, uzun yo‘lak, odamlar to‘planish zallari "
                                            "uchun SDU va zinapoya/liftlar uchun SPV tizimlarini yaratish."),
        "panel.smoke.btn_calc":           "▶  Hisoblash",
        "panel.smoke.card.systems.title": "Tizimlar",
        "panel.smoke.card.systems.sub":   "Qatorga ikki marta bosing — parametrlarni tahrirlash.",
        "panel.smoke.btn_add":            "➕  Qo‘shish",
        "panel.smoke.btn_edit":           "Tahrirlash",
        "panel.smoke.btn_dup":            "Nusxalash",
        "panel.smoke.btn_delete":         "O‘chirish",
        "panel.smoke.col.name":           "Nomi",
        "panel.smoke.col.type":           "Tur",
        "panel.smoke.col.purpose":        "Vazifasi",
        "panel.smoke.col.method":         "Usul",
        "panel.smoke.col.norm":           "Norma, m³/(soat·m²)",
        "panel.smoke.col.spaces":         "Xonalar",
        "panel.smoke.col.area":           "Yuza, m²",
        "panel.smoke.col.flow":           "Sarf, m³/soat",
        "panel.smoke.col.makeup":         "Kompensatsiya, m³/soat",
        "panel.smoke.col.zones":          "Zonalar",
        "panel.smoke.short_method.norm_per_m2":        "Yuza × norma",
        "panel.smoke.short_method.kmk_zone_perimeter": "KMK xona (f.3)",
        "panel.smoke.short_method.kmk_corridor":       "KMK yo‘lak (f.1/2)",
        "panel.smoke.short_method.nfpa_plume_axi":     "NFPA 92 plyum",
        "panel.smoke.short_method.manual":             "Qo‘lda kiritish",
        "panel.smoke.short_method.stairs_pressure":    "Zinapoya podpor",
        "panel.smoke.short_method.elevator_pressure":  "Lift podpor",
        "panel.smoke.title.change_norm":  "Normani o‘zgartirish",
        "panel.smoke.msg.change_norm":    ("«{title}» norma parametrlarini avtomatik yaratilgan "
                                            "tizimlarga qo‘llashni xohlaysizmi?\n\n"
                                            "Qo‘lda yaratilgan tizimlar («Qo‘shish» orqali) "
                                            "o‘zgartirilmaydi."),
        "panel.smoke.status.norm":        "Norma: {title}",
        "panel.smoke.status.norm_upd":    "  ·  yangilandi: SDU {smoke}, SPV {pres}",
        "panel.smoke.status.norm_method": ", usul o‘zgartirildi: {n}",
        "panel.smoke.title.no_data":      "Ma’lumot yo‘q",
        "panel.smoke.msg.no_data":        "Tizimlar yaratishdan oldin xonalarni yuklang.",
        "panel.smoke.title.assign":       "Avto-belgilash",
        "panel.smoke.msg.assign_overwrite":("Loyihada allaqachon tizim belgilangan xonalar bor.\n"
                                             "Tayinlovlarni qayta yozish kerakmi?"),
        "panel.smoke.title.err":          "Xato",
        "panel.smoke.status.assigned":    "Yaratildi: SDU {smoke}, SPV {pres}, belgilangan xonalar: {n}",
        "panel.smoke.title.no_systems":   "Tizim yo‘q",
        "panel.smoke.msg.no_systems":     ("Tizimlarni qo‘lda yarating («Qo‘shish») yoki "
                                            "«Avto-belgilash» tugmasini bosing."),
        "panel.smoke.title.calc_err":     "Hisob xatosi",
        "panel.smoke.status.calc_done":   "SDU/SPV hisobi bajarildi",
        "panel.smoke.note_manual":        "Qo‘lda yaratilgan",
        "panel.smoke.status.created":     "Tizim yaratildi: {name}",
        "panel.smoke.status.saved":       "Parametrlar saqlandi: {name}",
        "panel.smoke.title.dup":          "Tizimni nusxalash",
        "panel.smoke.msg.dup":            "Yangi tizim nomi:",
        "panel.smoke.dup.suffix":         "-nusxa",
        "panel.smoke.title.name_busy":    "Nom band",
        "panel.smoke.msg.name_busy":      "«{name}» tizimi allaqachon mavjud.",
        "panel.smoke.copy_suffix":        " (nusxa)",
        "panel.smoke.title.del":          "Tizimni o‘chirish",
        "panel.smoke.msg.del":            "«{name}» tizimini o‘chirish va uni hamma xonalardan olib tashlash kerakmi?",
        "panel.smoke.status.deleted":     "{name} tizim o‘chirildi; bog‘lanmagan xonalar: {n}",
        "panel.smoke.summary.total":      "Jami tizimlar: {n}",
        "panel.smoke.summary.flows":      ("Σ SDU {smoke:.1f} ming m³/soat  ·  "
                                            "Σ kompensatsiya {makeup:.1f} ming m³/soat"),
        "panel.smoke.summary.empty":      "Tizimlar yaratilmagan",

        # ========== Panel: Engineering ==========
        "panel.eng.title":               "Batafsil muhandislik (v4.1 + v4.2)",
        "panel.eng.card.title":          "Hisoblar",
        "panel.eng.card.sub":            ("AHU psixrometrikasi, aerodinamika, gidravlika, radiatorlar, "
                                            "akustika, issiq pol, fankoyl, VRF. Har bir tab "
                                            "HVACProject fasad metodidan foydalanadi."),
        "panel.eng.tab.psychro":         "AHU psixrometrika",
        "panel.eng.tab.duct":            "Tarmoq aerodinamikasi",
        "panel.eng.tab.hydro":           "Isitish gidravlikasi",
        "panel.eng.tab.radiators":       "Radiatorlar",
        "panel.eng.tab.acoustics":       "Akustika",
        "panel.eng.tab.underfloor":      "Issiq pol",
        "panel.eng.tab.fancoils":        "Fankoyl",
        "panel.eng.tab.vrf":             "VRF/VRV",
        "panel.eng.tab.energy":          "Energiya (8760 soat)",
        "panel.eng.common.error":        "Xato",
        "panel.eng.common.no_data":      "Ma’lumot yo‘q. «Hisoblash» tugmasini bosing.",

        # Psychro
        "panel.eng.psy.ahu":             "AHU:",
        "panel.eng.psy.mode":            "Rejim:",
        "panel.eng.psy.mode.winter":     "Qish",
        "panel.eng.psy.mode.summer":     "Yoz",
        "panel.eng.psy.mode.trans":      "Oraliq fasl",
        "panel.eng.psy.btn_chart":       "i-d diagramma",
        "panel.eng.psy.btn_chart_tt":    "Joriy AHU uchun jarayon nuqtalari bilan Molye diagrammasini ko‘rsatish",
        "panel.eng.psy.btn_run":         "▶  Hamma rejimlarni hisoblash",
        "panel.eng.psy.btn_table":       "Jadval",
        "panel.eng.psy.col.point":       "Nuqta",
        "panel.eng.psy.col.t":           "T, °C",
        "panel.eng.psy.col.w":           "W, g/kg",
        "panel.eng.psy.col.rh":          "RH, %",
        "panel.eng.psy.col.h":           "H, kJ/kg",
        "panel.eng.psy.col.td":          "Td, °C",
        "panel.eng.psy.matplotlib":      "i-d diagrammani ko‘rish uchun matplotlib o‘rnating (pip install matplotlib).",
        "panel.eng.psy.run_first":       "Avval hisobni ishga tushiring («▶ Hamma rejimlarni hisoblash»).",
        "panel.eng.psy.install":         "Diagrammani ko‘rish uchun matplotlib o‘rnating.",
        "panel.eng.psy.status":          "AHU psixrometrikasi hisoblandi",
        "panel.eng.psy.summary":         ("{name} [{mode}]: kalorifer {qh:.1f} kVt, "
                                            "sovutgich {qc:.1f} kVt (oshkor {qs:.1f}, "
                                            "yashirin {ql:.1f}); kondensat {cond:.1f} kg/soat"),

        # Duct
        "panel.eng.duct.info":           ("Batafsil aerodinamik tarmoq: soddalashtirilgan hisobdan qurish "
                                            "va qo‘lda tahrirlash. Uchastkaga ikki marta bosing — "
                                            "tahrirlash; «Kritik shoxoba» ventilyator bosimini 10% zaxira "
                                            "bilan belgilaydi."),
        "panel.eng.duct.net":            "Tarmoq:",
        "panel.eng.duct.btn_build":      "Soddalashtirilgan tarmoqlardan qurish",
        "panel.eng.duct.btn_recompute":  "▶ Qayta hisoblash",
        "panel.eng.duct.btn_add":        "➕ Uchastka qo‘shish",
        "panel.eng.duct.btn_edit":       "Tahrirlash",
        "panel.eng.duct.btn_delete":     "O‘chirish",
        "panel.eng.duct.col.sys":        "Tizim",
        "panel.eng.duct.col.terms":      "Terminallar",
        "panel.eng.duct.col.q":          "Q vent., m³/soat",
        "panel.eng.duct.col.dp":         "ΔP vent., Pa",
        "panel.eng.duct.col.v":          "v max, m/s",
        "panel.eng.duct.col.crit":       "Kritik shoxoba",
        "panel.eng.duct.col.id":         "ID",
        "panel.eng.duct.col.parent":     "Ota",
        "panel.eng.duct.col.terminal":   "Terminal?",
        "panel.eng.duct.col.name":       "Nomi",
        "panel.eng.duct.col.flow":       "Q, m³/soat",
        "panel.eng.duct.col.len":        "L, m",
        "panel.eng.duct.col.size":       "O‘lcham",
        "panel.eng.duct.col.vel":        "v, m/s",
        "panel.eng.duct.col.dpf":        "Δp ish., Pa",
        "panel.eng.duct.col.dpl":        "Δp mah., Pa",
        "panel.eng.duct.col.dpt":        "Σ Δp, Pa",
        "panel.eng.duct.parent_root":    "(ildiz)",
        "panel.eng.duct.terminal_yes":   "Ha",
        "panel.eng.duct.terminal_no":    "—",
        "panel.eng.duct.terminal_dflt":  "terminal {i}",
        "panel.eng.duct.status_built":   "Tarmoqlar qurildi: {n}",
        "panel.eng.duct.no_net":         "Tarmoq yo‘q",
        "panel.eng.duct.no_net_msg":     "Qayta hisoblash uchun tarmoq tanlanmagan.",
        "panel.eng.duct.calc_err":       "Hisob xatosi",
        "panel.eng.duct.recomp_status":  "«{name}» tarmog‘i qayta hisoblandi",
        "panel.eng.duct.new_net_title":  "Yangi tarmoq",
        "panel.eng.duct.new_net_combo":  "Ventilyatsiya tizimining nomi:",
        "panel.eng.duct.new_net_text":   "Tizim nomi:",
        "panel.eng.duct.del_block_title":"O‘chirib bo‘lmaydi",
        "panel.eng.duct.del_block_msg":  ("«{eid}» uchastkaning bolalari bor: {children}.\n"
                                            "Avval ularni o‘chiring yoki qayta ulang."),
        "panel.eng.duct.del_title":      "Uchastkani o‘chirish",
        "panel.eng.duct.del_msg":        "«{eid}» uchastkani o‘chirish kerakmi?",
        "panel.eng.duct.fan_label":      "Ventilyator: Q = {q} m³/soat, ΔP = {dp} Pa",

        # Hydraulics
        "panel.eng.hyd.h_static":        "Statik balandlik:",
        "panel.eng.hyd.btn_run":         "▶  Nasos va baklarni tanlash",
        "panel.eng.hyd.col.loop":        "Kontur",
        "panel.eng.hyd.col.q":           "Q, m³/soat",
        "panel.eng.hyd.col.h":           "H, m",
        "panel.eng.hyd.col.pump":        "Nasos",
        "panel.eng.hyd.col.p":           "P, Vt",
        "panel.eng.hyd.col.vtank":       "V_bak hisob, l",
        "panel.eng.hyd.col.tank":        "Bak",
        "panel.eng.hyd.col.pmax":        "P_max, bar",
        "panel.eng.hyd.col.makeup":      "To‘ldirish, l/sutka",
        "panel.eng.hyd.status":          "Gidravlika hisoblandi",

        # Radiators
        "panel.eng.rad.family":          "Oila:",
        "panel.eng.rad.family.all":      "Hammasi",
        "panel.eng.rad.btn_run":         "▶  Radiatorlarni tanlash",
        "panel.eng.rad.col.no":          "№",
        "panel.eng.rad.col.space":       "Xona",
        "panel.eng.rad.col.q":           "Q, Vt",
        "panel.eng.rad.col.model":       "Model",
        "panel.eng.rad.col.height":      "Balandlik",
        "panel.eng.rad.col.size":        "Uzunlik/seks.",
        "panel.eng.rad.col.qfact":       "Q amal., Vt",
        "panel.eng.rad.col.margin":      "Zaxira, %",
        "panel.eng.rad.status":          "Radiatorlar tanlandi",
        "panel.eng.rad.sect":            "{n} seks.",
        "panel.eng.rad.mm":              "{n} mm",

        # Acoustics
        "panel.eng.ac.info":             ("Xizmat zonasida LpA bahosi va shovqin pasaytirgich tanlash. "
                                            "Tarmoqlar bo‘yicha batafsil hisob uchun "
                                            "acoustics.select_silencer API’dan oshkor topologiya bilan foydalaning."),
        "panel.eng.ac.btn_run":          "▶  Shovqin pasaytirgichlarni tanlash",
        "panel.eng.ac.col.ahu":          "AHU",
        "panel.eng.ac.col.norm":         "Norma Lp, dBA",
        "panel.eng.ac.col.lp":           "Lp, dBA",
        "panel.eng.ac.col.margin":       "Zaxira, dBA",
        "panel.eng.ac.col.silencer":     "Shovqin pasaytirgich",
        "panel.eng.ac.col.length":       "Uzunlik, mm",
        "panel.eng.ac.col.dp":           "ΔP, Pa",
        "panel.eng.ac.status":           "Akustika hisoblandi",

        # Underfloor
        "panel.eng.uf.pitch":            "Qadam:",
        "panel.eng.uf.cover":            "Qoplama:",
        "panel.eng.uf.cover.tile":       "Plitka",
        "panel.eng.uf.cover.laminate":   "Laminat",
        "panel.eng.uf.cover.parquet":    "Parket",
        "panel.eng.uf.cover.carpet":     "Gilam",
        "panel.eng.uf.cover.linoleum":   "Linoleum",
        "panel.eng.uf.zone":             "Zona:",
        "panel.eng.uf.zone.habitable":   "Yashash (≤29°C)",
        "panel.eng.uf.zone.bath":        "Hammom (≤33°C)",
        "panel.eng.uf.zone.edge":        "Chekka (≤35°C)",
        "panel.eng.uf.zone.corridor":    "Yo‘lak (≤27°C)",
        "panel.eng.uf.zone.office":      "Ofis (≤28°C)",
        "panel.eng.uf.btn_run":          "▶ Konturlarni hisoblash",
        "panel.eng.uf.col.no":           "№",
        "panel.eng.uf.col.space":        "Xona",
        "panel.eng.uf.col.area":         "F, m²",
        "panel.eng.uf.col.pitch":        "Qadam",
        "panel.eng.uf.col.cover":        "Qoplama",
        "panel.eng.uf.col.tsurf":        "T yuza, °C",
        "panel.eng.uf.col.tlim":         "Limit, °C",
        "panel.eng.uf.col.q_m2":         "Q, Vt/m²",
        "panel.eng.uf.col.qfact":        "Q amal., Vt",
        "panel.eng.uf.col.pipe":         "L quvur, m",
        "panel.eng.uf.col.notes":        "Izohlar",
        "panel.eng.uf.status":           "Issiq pol hisoblandi",
        "panel.eng.uf.summary":          "Konturlar: {n}; Σ quvur uzunligi: {pipe:.0f} m",
        "panel.eng.uf.pitch_mm":         "{n} mm",

        # Fancoils
        "panel.eng.fc.family":           "Oila:",
        "panel.eng.fc.family.all":       "Hammasi",
        "panel.eng.fc.pipes":            "Quvurlar:",
        "panel.eng.fc.pipes.any":        "Har qanday",
        "panel.eng.fc.pipes.2":          "2-quvurli",
        "panel.eng.fc.pipes.4":          "4-quvurli",
        "panel.eng.fc.btn_run":          "▶ Fankoylarni tanlash",
        "panel.eng.fc.col.no":           "№",
        "panel.eng.fc.col.space":        "Xona",
        "panel.eng.fc.col.qc":           "Q_s, Vt",
        "panel.eng.fc.col.qh":           "Q_i, Vt",
        "panel.eng.fc.col.model":        "Model",
        "panel.eng.fc.col.family":       "Oila",
        "panel.eng.fc.col.pipes":        "Quvurlar",
        "panel.eng.fc.col.qc_fact":      "Q_s amal., Vt",
        "panel.eng.fc.col.margin":       "Zaxira, %",
        "panel.eng.fc.col.air":          "L havo",
        "panel.eng.fc.col.noise":        "Shovqin, dBA",
        "panel.eng.fc.status":           "Fankoyl tanlandi",

        # VRF
        "panel.eng.vrf.info":            ("Ishlab chiqaruvchi cheklovlarini (trassa uzunligi, balandlik farqi, "
                                            "ulanish koeff.) tekshirgan holda VRF tashqi/ichki bloklarini tanlash."),
        "panel.eng.vrf.group":           "Guruhlash:",
        "panel.eng.vrf.group.level":     "Qavat bo‘yicha",
        "panel.eng.vrf.group.all":       "Hammasi birga",
        "panel.eng.vrf.indoor":          "Ichki:",
        "panel.eng.vrf.indoor.cassette": "Kasetali",
        "panel.eng.vrf.indoor.duct":     "Kanal",
        "panel.eng.vrf.indoor.wall":     "Devorga",
        "panel.eng.vrf.indoor.any":      "Har qanday",
        "panel.eng.vrf.btn_run":         "▶ VRF tanlash",
        "panel.eng.vrf.main_pipe":       "Magistral:",
        "panel.eng.vrf.max_pipe":        "Maks. ichkigacha:",
        "panel.eng.vrf.dh_max":          "Δh maks:",
        "panel.eng.vrf.col.sys":         "Tizim",
        "panel.eng.vrf.col.outdoor":     "Tashqi",
        "panel.eng.vrf.col.indoor":      "Ichki",
        "panel.eng.vrf.col.index":       "Σ indeks",
        "panel.eng.vrf.col.kconn":       "K ulan.",
        "panel.eng.vrf.col.qc":          "Q_s, kVt",
        "panel.eng.vrf.col.qh":          "Q_i, kVt",
        "panel.eng.vrf.col.corr":        "Korr.",
        "panel.eng.vrf.col.check":       "Tekshiruv",
        "panel.eng.vrf.col.sys2":        "Tizim",
        "panel.eng.vrf.col.space":       "Xona",
        "panel.eng.vrf.col.idx":         "Indeks",
        "panel.eng.vrf.col.qc_w":        "Q_s, Vt",
        "panel.eng.vrf.col.dliq":        "Ø suyuq.",
        "panel.eng.vrf.col.dgas":        "Ø gaz",
        "panel.eng.vrf.col.indoor_model":"Ichki",
        "panel.eng.vrf.status":          "VRF tanlandi",
        "panel.eng.vrf.ok":              "✓ OK",
        "panel.eng.vrf.warn":            "⚠ {n}",

        # Energy
        "panel.eng.en.info":             ("8760 soatlik simulyatsiya: GSOPdan har soatlik T_tashqi sintezi, "
                                            "xona turi bo‘yicha bandlik jadvali, termik massa. "
                                            "Natija — yillik iste’mol va eng katta yuklamalar."),
        "panel.eng.en.tau":              "Termik massa τ:",
        "panel.eng.en.setback":          "Tungi pasaytirish:",
        "panel.eng.en.btn_chart":        "Yillik grafik",
        "panel.eng.en.btn_chart_tt":     "Jadval / grafik o‘rtasida almashtirish",
        "panel.eng.en.btn_run":          "▶ Yilni simulyatsiya qilish",
        "panel.eng.en.btn_table":        "Jadval",
        "panel.eng.en.col.param":        "Parametr",
        "panel.eng.en.col.value":        "Qiymat",
        "panel.eng.en.matplotlib":       "Grafiklar uchun matplotlib o‘rnating.",
        "panel.eng.en.run_first":        "Avval simulyatsiyani ishga tushiring.",
        "panel.eng.en.install":          "Grafikni ko‘rish uchun matplotlib o‘rnating.",
        "panel.eng.en.status_err":       "Simulyatsiya xatosi",
        "panel.eng.en.status":           "Yillik simulyatsiya bajarildi",
        "panel.eng.en.empty":            "Ma’lumot yo‘q. «Yilni simulyatsiya qilish» tugmasini bosing.",
        "panel.eng.en.chart.t_year":     "Yillik T (o‘rtacha sutkalik)",
        "panel.eng.en.chart.t_ext":      "T tash., °C",
        "panel.eng.en.chart.qd_year":    "Yillik yuklamalar (o‘rtacha sutkalik)",
        "panel.eng.en.chart.day":        "Yil kuni",
        "panel.eng.en.chart.q_avg":      "Q o‘rt., kVt",
        "panel.eng.en.chart.heat":       "Isitish",
        "panel.eng.en.chart.cool":       "Sovutish",
        "panel.eng.en.row.spaces":       "Xonalar",
        "panel.eng.en.row.area":         "Maydon, m²",
        "panel.eng.en.row.e_heat":       "Σ isitish, kVt·s/yil",
        "panel.eng.en.row.e_cool":       "Σ sovutish, kVt·s/yil",
        "panel.eng.en.row.e_heat_m2":    "Solishtirma isitish, kVt·s/(m²·yil)",
        "panel.eng.en.row.e_cool_m2":    "Solishtirma sovutish, kVt·s/(m²·yil)",
        "panel.eng.en.row.e_total_m2":   "Solishtirma Σ, kVt·s/(m²·yil)",
        "panel.eng.en.row.q_peak_heat":  "Q maks. isitish, kVt",
        "panel.eng.en.row.q_peak_cool":  "Q maks. sovutish, kVt",
        "panel.eng.en.row.t_peak_heat":  "Isitish maks. vaqti",
        "panel.eng.en.row.t_peak_cool":  "Sovutish maks. vaqti",
        "panel.eng.en.row.h_peak_heat":  "Maks. soatlar (≥90%) isit.",
        "panel.eng.en.row.h_peak_cool":  "Maks. soatlar (≥90%) sov.",
        "panel.eng.en.row.h_heat":       "Isitish mavsumi soatlari",
        "panel.eng.en.row.h_cool":       "Sovutish mavsumi soatlari",
        "panel.eng.en.summary":          ("Σ {total:.1f} kVt·s/(m²·yil) · "
                                            "maks. Q_h={qh:.1f} kVt / Q_c={qc:.1f} kVt · "
                                            "mavsumlar: {hh} / {ch} soat"),

        # ========== Palette / city combo ==========
        "palette.search_ph":             "Buyruq nomini yoki qidiruvni kiriting…  (Esc — yopish)",

        # ========== Export center ==========
        "export.title":                  "Eksport",
        "export.h1":                     "Natijalarni eksport qilish",
        "export.sub":                    "Formatni va saqlash yo‘lini tanlang.",
        "export.path_ph":                "Saqlash fayli…",
        "export.browse":                 "Ko‘rib chiqish…",
        "export.open_folder":            "Saqlashdan keyin papkani ochish",
        "export.btn_close":              "Yopish",
        "export.btn_export":             "Eksport qilish",
        "export.dlg_save":               "Sifatida saqlash",
        "export.no_data.title":          "Ma’lumot yo‘q",
        "export.no_data.msg":            "Loyihani yuklang va hisobni bajaring.",
        "export.no_path.title":          "Yo‘l yo‘q",
        "export.no_path.msg":            "Saqlash faylini ko‘rsating.",
        "export.err.title":              "Eksport xatosi",
        "export.fmt.excel.title":        "To‘liq Excel hisobot",
        "export.fmt.excel.desc":         ("14 ta varaq: xonalar, to‘siqlar, xulosalar, IIV, energo-pasport, "
                                            "shudring nuqtasi, havo o‘tkazgichlar, quvurlar."),
        "export.fmt.excel.name":         "HVAC_{name}.xlsx",
        "export.fmt.pdf.title":          "PDF: tushuntirish xati",
        "export.fmt.pdf.desc":           "Loyiha ma’lumotlari asosida 12 tagacha bo‘lim.",
        "export.fmt.pdf.name":           "Hisobot_{name}.pdf",
        "export.fmt.equipment.title":    "Jihozlar bo‘yicha xulosa jadvali",
        "export.fmt.equipment.desc":     "Xonalar bo‘yicha xulosa + radiator/fankoyl/diffuzor spetsifikatsiyalari.",
        "export.fmt.equipment.name":     "Jihozlar_{name}.xlsx",
        "export.fmt.revit.title":        "Revit uchun CSV (teskari yozish)",
        "export.fmt.revit.desc":         ("Dynamo’da revit_dynamo_apply_results.py ni ishga tushiring — "
                                            "Q qish/yoz xona parametrlariga yoziladi."),
        "export.fmt.revit.name":         "results_for_revit.csv",
        "export.fmt.spec.title":         "GOST 21.110 bo‘yicha spetsifikatsiya",
        "export.fmt.spec.desc":          ("Jihoz va materiallarning to‘liq spetsifikatsiyasi: qozonlar, AHU, "
                                            "radiatorlar, fankoyl, VRF, nasoslar, baklar, shovqin pasaytirgich, "
                                            "mis, issiq pol quvurlari. GOST 21.110-2013 bo‘limlari bo‘yicha guruhlanadi."),
        "export.fmt.spec.name":          "Spetsifikatsiya_{name}.xlsx",
        "export.default_name":           "Loyiha",

        # ========== Panel: Calculation ==========
        "panel.calc.title":         "Yuklamalar hisobi",
        "panel.calc.subtitle":      ("Hisoblarni ketma-ket yoki birdaniga "
                                       "ishga tushiring. Natijalar barcha "
                                       "panellarda yangilanadi."),
        "panel.calc.heat.title":    "Issiqlik yo‘qotish va kelishi",
        "panel.calc.heat.desc":     ("СП 50.13330: barcha xonalar bo‘yicha "
                                       "yo‘nalish, burchak va yuqori qavatlarni "
                                       "hisobga olib hisoblash."),
        "panel.calc.heat.btn":      "Qayta hisoblash",
        "panel.calc.vent.title":    "Ventilyatsiya",
        "panel.calc.vent.desc":     ("СП 60.13330: xona turlariga ko‘ra "
                                       "kelish / so‘rish / soyabon. Qo‘lda "
                                       "tahrirlangan xonalar qayta hisoblanmaydi."),
        "panel.calc.vent.btn":      "Hisoblash",
        "panel.calc.ahu.title":     "Havo yuborish qurilmalari yuklamasi",
        "panel.calc.ahu.desc":      ("Rekuperatorni hisobga olib AHU "
                                       "kaloriferi va sovutgichi yuklamasi."),
        "panel.calc.ahu.btn":       "Hisoblash",
        "panel.calc.all.title":     "To‘liq hisob",
        "panel.calc.all.desc":      ("Ketma-ket: yuklamalar → ventilyatsiya "
                                       "→ AHU."),
        "panel.calc.all.btn":       "Hammasi birdan",
        "panel.calc.summary":       "Xulosa",
        "panel.calc.status.done":   "✓ Tayyor",
        "panel.calc.status.not_done":"bajarilmagan",
        "panel.calc.validate.no_data":  ("Boshlash uchun CSV ni yuklang "
                                          "yoki loyihani oching."),
        "panel.calc.validate.problems": ("⚠ Validatsiya muammolari: {n}. "
                                          "Birinchi: {first}"),
        "panel.calc.validate.ok":   "✓ Validatsiya muvaffaqiyatli.",
        "panel.calc.run.heat":      "Yuklamalar hisoblanmoqda…",
        "panel.calc.run.vent":      "Ventilyatsiya hisoblanmoqda…",
        "panel.calc.run.ahu":       "AHU hisoblanmoqda…",
        "panel.calc.run.all":       "To‘liq hisob…",
        "panel.calc.run.done":      "Hisob tugadi",
        "panel.calc.run.err":       "Hisob xatosi",
        "panel.calc.summary.loss":      "Σ issiqlik yo‘qotish",
        "panel.calc.summary.gain":      "Σ issiqlik kelishi",
        "panel.calc.summary.area":      "Umumiy maydon",
        "panel.calc.summary.density":   "Solishtirma yo‘qotish",
        "panel.calc.summary.supply":    "Σ kelish",
        "panel.calc.summary.exhaust":   "Σ so‘rish",
    },
}


# ============================================================================
# Глобальное состояние и API
# ============================================================================

_current_language = DEFAULT_LANGUAGE


def get_language() -> str:
    """Текущий язык интерфейса."""
    return _current_language


def set_language(lang: str) -> None:
    """Устанавливает язык интерфейса. Допустимы: 'ru', 'uz'.

    Если язык неизвестен — используется DEFAULT_LANGUAGE.
    Уведомляет всех подписчиков on_language_change.
    """
    global _current_language
    if lang not in SUPPORTED_LANGUAGES:
        lang = DEFAULT_LANGUAGE
    if lang == _current_language:
        return
    _current_language = lang
    for cb in list(_language_listeners):
        try:
            cb(lang)
        except Exception:
            import traceback
            traceback.print_exc()


def on_language_change(callback: Callable[[str], None]) -> Callable[[], None]:
    """Подписаться на смену языка. callback(lang_code) вызывается каждый
    раз когда меняется язык. Возвращает функцию-unsubscriber.
    """
    _language_listeners.append(callback)
    def _unsub():
        try:
            _language_listeners.remove(callback)
        except ValueError:
            pass
    return _unsub


def t(key: str, default: Optional[str] = None) -> str:
    """Перевод по ключу.

    Если ключ не найден ни в активном языке, ни в RU — возвращает default
    или сам key (последнее удобно для разработки: видно, какие строки
    не локализованы).
    """
    lang = _current_language
    val = TRANSLATIONS.get(lang, {}).get(key)
    if val is None:
        # Fallback на русский
        val = TRANSLATIONS.get(DEFAULT_LANGUAGE, {}).get(key)
    if val is None:
        return default if default is not None else key
    return val


def supported_languages_with_labels() -> Dict[str, str]:
    """Возвращает {code: human-name} для UI-выбора языка."""
    return {
        "ru": "Русский",
        "uz": "O‘zbek (lotin)",
    }


# ============================================================================
# Инициализация при импорте: язык берётся из настроек или env
# ============================================================================

def _try_load_from_settings() -> None:
    """При импорте читает язык из пользовательских настроек hvac.ui_qt.settings.
    Не падает, если модуль настроек недоступен (например в тестах CLI).
    """
    env_lang = os.environ.get("HVAC_LANG", "").strip().lower()
    if env_lang in SUPPORTED_LANGUAGES:
        set_language(env_lang)
        return
    try:
        from hvac.ui_qt import settings as user_settings
        cfg = user_settings.load()
        lang = (cfg.get("language") or DEFAULT_LANGUAGE).lower()
        if lang in SUPPORTED_LANGUAGES:
            set_language(lang)
    except Exception:
        pass


_try_load_from_settings()
