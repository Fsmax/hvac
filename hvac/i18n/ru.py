# -*- coding: utf-8 -*-
"""Русские строки UI (RU).

Авто-выделено из прежнего hvac/i18n.py. Ключи машинные
(«домен.раздел.строка»). Полнота RU↔UZ проверяется tests/test_i18n.py.
"""
from __future__ import annotations
from typing import Dict

RU: Dict[str, str] = {
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
    "sidebar.blocks":        "Блоки",
    "sidebar.constructions": "Конструкции",
    "sidebar.calculation":   "Расчёт нагрузок",
    "sidebar.ventilation":   "Вентиляция",
    "sidebar.systems":       "Системы и оборудование",
    "sidebar.zones":         "Зоны и системы",
    "sidebar.equipment":     "Оборудование",
    "sidebar.balance":       "Тепловой баланс",
    "sidebar.airbalance":    "Баланс воздуха",
    "sidebar.room_equipment":"Оборудование в помещениях",
    "sidebar.smoke":         "Дымоудаление",
    "sidebar.charts":        "Графики",
    "sidebar.extensions":    "Расширения",
    "sidebar.engineering":   "Инженерия",
    "sidebar.problems":      "Проблемы",
    "sidebar.comparison":    "Сравнение",
    # Группы сайдбара (по маршруту работы) + сворачивание
    "sidebar.group.project":  "Проект",
    "sidebar.group.model":    "Модель",
    "sidebar.group.calc":     "Расчёт",
    "sidebar.group.systems":  "Системы",
    "sidebar.group.analysis": "Анализ",
    "sidebar.collapse":       "Свернуть",
    "sidebar.expand":         "Развернуть панель",

    # ========== Panel: Comparison (сравнение вариантов) ==========
    "panel.comparison.title":       "Сравнение вариантов",
    "panel.comparison.hint":        "Загрузите второй .hvac.json — сравним метрики.",
    "panel.comparison.btn_load":    "Загрузить вариант…",
    "panel.comparison.not_loaded":  "Вариант для сравнения не загружен.",
    "panel.comparison.loaded":      "Текущий: {cur}  ·  Сравнение: {other} ({name})",
    "panel.comparison.dlg_title":   "Выберите проект для сравнения",
    "panel.comparison.dlg_filter":  "Проекты HVAC (*.hvac.json *.json)",
    "panel.comparison.col.metric":     "Показатель",
    "panel.comparison.col.current":    "Текущий",
    "panel.comparison.col.other":      "Сравнение",
    "panel.comparison.col.delta":      "Δ",
    "panel.comparison.col.delta_pct":  "Δ %",
    "panel.comparison.row.n_spaces":   "Помещений",
    "panel.comparison.row.area":       "Площадь, м²",
    "panel.comparison.row.ql":         "Σ теплопотери, кВт",
    "panel.comparison.row.qg":         "Σ теплопоступления, кВт",
    "panel.comparison.row.density":    "Уд. теплопотери, Вт/м²",
    "panel.comparison.row.supply":     "Σ приток, м³/ч",
    "panel.comparison.row.exhaust":    "Σ вытяжка, м³/ч",

    # ========== Табличные правки (общее: буфер/fill-down/undo) ==========
    "tableedit.paste":       "Вставлено значений: {n}",
    "tableedit.fill":        "Заполнено вниз: {n}",
    "tableedit.undo":        "Отменено ({n})",
    "tableedit.redo":        "Повторено ({n})",
    "tableedit.ctx.copy":    "Копировать (Ctrl+C)",
    "tableedit.ctx.paste":   "Вставить (Ctrl+V)",
    "tableedit.ctx.fill_down": "Заполнить вниз (Ctrl+D)",
    "tableedit.ctx.undo":    "Отменить (Ctrl+Z)",
    "tableedit.ctx.redo":    "Повторить (Ctrl+Y)",

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
    "btn.edit_space":        "Изменить…",
    "btn.space_detail":      "Свойства…",
    "btn.compute":           "Рассчитать",
    "btn.run":               "Запустить",
    "btn.cancel":            "Отмена",
    "btn.ok":                "OK",
    "btn.close":             "Закрыть",
    "btn.more":              "Ещё…",
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
    "checklist.step_dhw":           "ГВС посчитано",
    "checklist.dhw_hint":           "{n} систем",
    "checklist.dhw_hint_empty":     "не задано",
    "checklist.step_smoke":         "Дымоудаление / подпор",
    "checklist.smoke_hint":         "{n} систем",
    "checklist.smoke_hint_empty":   "не задано",
    "checklist.collapse":           "Свернуть чек-лист",
    "checklist.expand":             "Развернуть чек-лист",

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
    "status.dropped_project": "Открыт проект: {name}",
    "status.drop_need_both": "Перетащите spaces.csv и thermal_all.csv вместе (или откройте на вкладке «Данные»).",
    "status.kw_summary":     "Σ зима {h:.1f} кВт · Σ лето {c:.1f} кВт",
    "status.lang_switched":  "Язык переключён: Русский",
    "status.autosave_done":  "Auto-save: {name}",
    "status.autosave_error": "Auto-save: ошибка {err}",
    "status.calc_cancelled": "Расчёт отменён — результаты не изменены",
    "status.journal_title":  "Последние события",
    "status.journal_empty":  "Событий пока нет",

    # ========== Лента «результаты устарели» ==========
    "ribbon.stale_prefix":   "⚠ Данные изменены — устарело: ",
    "ribbon.layer.loads":    "нагрузки",
    "ribbon.layer.ventilation": "вентиляция",
    "ribbon.layer.ahu":      "приточные установки",
    "ribbon.recalc_all":     "Пересчитать всё",
    "ribbon.dismiss_tip":    "Скрыть до следующего изменения",

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
    "btn.project_boundaries":"Ограждения проекта…",

    # ===== Диалог: общепроектный редактор ограждений =====
    "dlg.projbnd.title":     "Ограждения проекта",
    "dlg.projbnd.hint":      ("Все стены и проёмы всех помещений. Отфильтруйте "
                               "(этаж/тип/ориентация/наружн.), выделите строки и "
                               "пометьте внутренними или наружными пачкой. "
                               "Внутренние ограждения не теряют тепло — полезно, "
                               "когда Revit ошибочно дал «наружные» стены."),
    "dlg.projbnd.col.room":  "Помещение",
    "dlg.projbnd.f.orient":  "Ориент.:",
    "dlg.projbnd.f.ext":     "Граница:",
    "dlg.projbnd.ext.only_ext":"Только наружные",
    "dlg.projbnd.ext.only_int":"Только внутренние",
    "dlg.projbnd.count":     "Показано: {n} из {total}",
    "dlg.projbnd.no_selection":"Выделите строки в таблице",

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
    "panel.data.climate.gsop_cap":    "ГСОП, °C·сут",
    "panel.data.climate.solar_cap":   "Солн. рад., Вт/м²",
    "panel.data.climate.override":    "Переопределить вручную:",
    "panel.data.climate.t_heat_short":"t зима",
    "panel.data.climate.t_cool_short":"t лето",
    "panel.data.climate.true_north":  "Поворот True North:",
    "panel.data.climate.true_north_hint": ("Глобально поворачивает стороны "
        "света всех фасадов для солнечного расчёта (+ против часовой). "
        "Применяется при пересчёте — править ориентацию по каждому "
        "ограждению вручную не нужно."),
    "panel.data.climate.zone":        "Климатическая зона (ШНҚ):",
    "panel.data.climate.zone_apply":  "Применить tв(лето)",
    "panel.data.climate.zone_info":   "ШНҚ 2.08.02-23 табл.18: tв(лето) ≈ {t} °C, φ ≤ {rh}%, v ≤ {v} м/с",
    "panel.data.climate.shading":     "Защита от солнца:",
    "panel.data.climate.shade_none":  "Без затенения (100% солнца)",
    "panel.data.climate.shade_inner": "Внутренние жалюзи / тонировка (−30%)",
    "panel.data.climate.shade_outer": "Внешние ламели / маркизы (−50%)",
    "panel.data.climate.shade_deep":  "Глубокие ниши + жалюзи (−70%)",
    "panel.data.sources.title": "Источники геометрии",
    "panel.data.sources.desc":  ("CSV, выгруженные из Revit-Dynamo: "
                                  "spaces.csv (помещения) и thermal.csv "
                                  "(ограждения)."),
    "panel.data.keep_overrides": ("Сохранить ручные правки помещений при "
                                   "перезагрузке"),
    "panel.data.btn_load_csv":  "📥  Загрузить CSV",
    "panel.data.btn_revit_import": "🔄  Импорт из Revit",
    "panel.data.revit.tooltip": ("Выгрузить помещения и ограждения прямо из открытой модели "
                                  "Revit (без Dynamo). Нужен включённый Revit MCP Switch."),
    "panel.data.revit.pick_dir": "Папка для spaces.csv / thermal_all.csv",
    "panel.data.revit.not_connected.title": "Revit недоступен",
    "panel.data.revit.not_connected.body": ("Не удалось подключиться к Revit (127.0.0.1:8080).\n\n"
                                  "Проверьте: Revit открыт с моделью, включён переключатель "
                                  "«Revit MCP Switch» на ленте."),
    "panel.data.status.revit_import": "Импорт из Revit… (большая модель — несколько минут)",
    "panel.data.revit.done": ("Выгружено из Revit ({source}): помещений {spaces}, "
                                  "строк границ {thermal}"),
    "panel.data.err.revit":     "Ошибка импорта из Revit",
    "panel.data.btn_revit_tools": "Revit-инструменты ▾",
    "panel.data.revit.act_diff": "Сравнить модель с проектом",
    "panel.data.revit.act_color_heat": "Раскрасить: отопление, Вт/м²",
    "panel.data.revit.act_color_cool": "Раскрасить: охлаждение, Вт/м²",
    "panel.data.revit.act_color_ach": "Раскрасить: кратность, 1/ч",
    "panel.data.revit.act_color_clear": "Сбросить раскраску",
    "panel.data.status.revit_diff": "Сравнение с моделью Revit…",
    "panel.data.status.revit_color": "Раскраска помещений в Revit…",
    "panel.data.revit.diff.no_project": ("Проект пуст — сначала загрузите данные "
                                  "(CSV или импорт из Revit)."),
    "panel.data.revit.diff.in_sync": ("Модель Revit совпадает с проектом: "
                                  "{n} помещений без расхождений."),
    "panel.data.revit.diff.summary": ("Модель Revit разошлась с проектом.\n\n"
                                  "Новых помещений в Revit: {added}\n"
                                  "Удалено из Revit: {removed}\n"
                                  "Изменено (площадь/объём/атрибуты): {changed}\n"
                                  "Без изменений: {unchanged}\n\n"
                                  "Подробности — кнопка «Показать подробности». "
                                  "Обновить проект: «Импорт из Revit»."),
    "panel.data.revit.diff.h_added": "— Новые в Revit —",
    "panel.data.revit.diff.h_removed": "— Удалённые из Revit —",
    "panel.data.revit.diff.h_changed": "— Изменённые —",
    "panel.data.revit.color.done": ("Раскрашено {n} помещений на виде «{view}» "
                                  "(диапазон {vmin}…{vmax})"),
    "panel.data.revit.color.cleared": "Сброшена раскраска {n} помещений на виде «{view}»",
    "panel.data.revit.act_equip": "Импорт оборудования помещений",
    "panel.data.status.revit_equip": "Чтение оборудования из Revit…",
    "panel.data.revit.equip.none": ("В модели не найдено оборудования, привязанного "
                                  "к помещениям (решётки/диффузоры, фанкойлы, "
                                  "радиаторы)."),
    "panel.data.revit.equip.summary": ("Распознано экземпляров: {total}\n"
                                  "Обновлено помещений: {spaces}\n\n"
                                  "Приток: {supply} · Вытяжка: {exhaust} · "
                                  "Отопление: {heating} · Охлаждение: {cooling}\n"
                                  "Вне помещений: {no_space} · Нет в проекте: "
                                  "{unmatched} · Не распознано: {unrec}"),
    "panel.data.revit.equip.h_assigned": "— Назначено по помещениям —",
    "panel.data.revit.equip.h_unrec": "— Не распознано (семейство / тип) —",
    "panel.data.revit.equip.slot.supply": "приток",
    "panel.data.revit.equip.slot.exhaust": "вытяжка",
    "panel.data.revit.equip.slot.heating": "отопление",
    "panel.data.revit.equip.slot.cooling": "охлаждение",
    "panel.data.revit.equip.line": "  {number} {name}: {slot} — {qty} × {type} ({model})",
    "panel.data.revit.equip.val.flow": " · {v} м³/ч на шт.",
    "panel.data.revit.equip.val.power": " · {v} Вт на шт.",
    "panel.data.revit.equip.done": "Оборудование из Revit: обновлено помещений — {spaces}",
    "panel.data.revit.act_facades": "Проверить фасады по модели",
    "panel.data.status.revit_facades": "Лучевая проверка фасадов в Revit…",
    "panel.data.revit.fac.none": "В проекте нет наружных стен для проверки.",
    "panel.data.revit.fac.all_ok": ("Все наружные стены подтверждены фасадами: {n} шт. "
                                  "(без геометрии, пропущено: {skip})."),
    "panel.data.revit.fac.summary": ("Проверено стен лучом: {checked}\n"
                                  "Подтверждены фасадами: {facades}\n"
                                  "Переведено во внутренние: {fixed} элементов "
                                  "в {rooms} помещениях\n"
                                  "Без геометрии (пропущено): {skip}\n\n"
                                  "Теплопотери пересчитаны; изменения сохранятся "
                                  "в проекте как ручные правки."),
    "panel.data.revit.fac.h_fixed": "— Переведены во внутренние —",
    "panel.data.revit.fac.line": ("  {number} {name}: {family} {type} {area} м² — "
                                  "за стеной {hit} ({dist} м)"),
    "panel.data.revit.fac.done": ("Фасады проверены: {fixed} элементов в {rooms} "
                                  "помещениях стали внутренними"),
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
    "panel.data.status.true_north":   "Поворот True North = {deg:+.0f}° (применится при пересчёте)",
    "panel.data.status.shading":      "Защита от солнца: теплопоступления −{pct}% (применится при пересчёте)",
    "panel.data.status.zone_applied": "tв(лето) {t} °C применена к {n} помещениям (применится при пересчёте)",
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
    "panel.spaces.col.t_cool":    "t лето",
    "panel.spaces.col.occup":     "Люди",
    "panel.spaces.col.light":     "Освещ., Вт/м²",
    "panel.spaces.col.equip":     "Обор., Вт/м²",
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
    "panel.spaces.bulk.menu":           "Групповая правка выделенных…",
    "panel.spaces.bulk.btn":       "Групповая правка…",
    "panel.spaces.bulk.scope":     "Применить к:",
    "panel.spaces.bulk.scope_selected": "выделенным строкам ({n})",
    "panel.spaces.bulk.scope_filtered": "всем отфильтрованным ({n})",
    "panel.spaces.bulk.title":          "Групповая правка помещений",
    "panel.spaces.bulk.field":          "Поле",
    "panel.spaces.bulk.value":          "Значение",
    "panel.spaces.bulk.t_heat":         "t зима",
    "panel.spaces.bulk.t_cool":         "t лето",
    "panel.spaces.bulk.occup":          "Люди, чел.",
    "panel.spaces.bulk.light":          "Освещение, Вт/м²",
    "panel.spaces.bulk.equip":          "Оборудование, Вт/м²",
    "panel.spaces.bulk.inf":            "Инфильтрация, 1/ч",
    "panel.spaces.bulk.hint":           "Будет применено к {n} выделенным помещениям.",
    "panel.spaces.bulk.no_selection":   ("Не выделено ни одного помещения. "
                                          "Выделите строки (Ctrl/Shift) и повторите."),
    "panel.spaces.bulk.applied":        "Групповая правка: обновлено {n}",
    # Переопределение типа помещения авто-определением по названию
    "panel.spaces.redetect.menu":       "Определить типы заново (для «Прочее»)",
    "panel.spaces.redetect.none":       ("Нет помещений «Прочее», для которых "
                                          "удаётся определить тип по названию."),
    "panel.spaces.redetect.confirm":    ("Определить тип по названию для {n} "
                                          "помещений «Прочее»? Ручные правки "
                                          "сохранятся, вентиляция пересчитается."),
    "panel.spaces.redetect.done":       ("Переопределено типов: {n}. "
                                          "Вентиляция пересчитана."),
    # Ограждения выделенных помещений (внутренние / наружные)
    "panel.spaces.env.menu":            "Ограждения выделенных помещений",
    "panel.spaces.env.make_internal":   "🏠 Сделать внутренними",
    "panel.spaces.env.make_external":   "🌤 Сделать наружными",
    "panel.spaces.env.lbl_internal":    "внутренними",
    "panel.spaces.env.lbl_external":    "наружными",
    "panel.spaces.env.nothing":         ("У выделенных помещений ({n}) все стены "
                                          "и проёмы уже помечены {label}."),
    "panel.spaces.env.confirm.title":   "Подтверждение",
    "panel.spaces.env.confirm.body":    ("Помещений выделено: {rooms}\n"
                                          "Будет помечено элементов {label}: {elems}\n\n"
                                          "Внутренние ограждения не участвуют в "
                                          "расчёте теплопотерь (остаётся только "
                                          "инфильтрация). После этого выполнится "
                                          "пересчёт. Продолжить?"),
    "panel.spaces.env.done":            ("Помечено элементов: {elems} "
                                          "({rooms} помещ.). Пересчёт выполнен."),
    "panel.spaces.detail.title":        "Свойства помещения",

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
    "panel.room_eq.col.heat_circ": "Контур отопл.",
    "panel.room_eq.col.cool_circ": "Контур холода",
    "panel.room_eq.col.vent_sys":  "Приточка (AHU)",
    "panel.room_eq.hint":          "💡 Двойной клик — назначить; Ctrl/Shift — выделить несколько для групповых операций (ПКМ).",
    # --- Групповые операции ---
    "panel.room_eq.btn.apply_sel": "Применить к выделенным…",
    "panel.room_eq.btn.clear":     "Очистить",
    "panel.room_eq.msg.no_selection": "Сначала выделите помещения (Ctrl/Shift).",
    "panel.room_eq.dlg.apply_title":  "Оборудование → {n} помещениям",
    "panel.room_eq.ctx.edit":      "Изменить…",
    "panel.room_eq.ctx.apply_sel": "Применить к выделенным…",
    "panel.room_eq.ctx.copy":      "Копировать оборудование",
    "panel.room_eq.ctx.paste":     "Вставить в выделенные",
    "panel.room_eq.ctx.clear":     "Очистить оборудование",
    "panel.room_eq.ctx.undo":      "Отменить",
    "panel.room_eq.status.applied":     "Оборудование применено к {n} пом.",
    "panel.room_eq.status.copied":      "Скопировано оборудование пом. {room}",
    "panel.room_eq.status.nothing_copy": "В помещении нет оборудования для копирования.",
    "panel.room_eq.status.pasted":      "Вставлено в {n} пом.",
    "panel.room_eq.status.cleared":     "Очищено: {n} пом.",
    # --- Диалог назначения оборудования ---
    "dlg.room_eq.title":           "Оборудование помещения: {room}",
    "dlg.room_eq.loads":           ("Расчёт: Q зима {qh:.2f} кВт · Q лето {qc:.2f} кВт · "
                                    "приток {sup:.0f} м³/ч · вытяжка {exh:.0f} м³/ч"),
    "dlg.room_eq.sec.heating":     "Отопительный прибор",
    "dlg.room_eq.sec.cooling":     "Охлаждение",
    "dlg.room_eq.sec.supply":      "Приток (воздухораспределитель)",
    "dlg.room_eq.sec.exhaust":     "Вытяжка",
    "dlg.room_eq.f.type":          "Тип:",
    "dlg.room_eq.f.model":         "Модель:",
    "dlg.room_eq.f.power":         "Мощность 1 шт., Вт:",
    "dlg.room_eq.f.flow":          "Расход 1 шт., м³/ч:",
    "dlg.room_eq.f.qty":           "Кол-во, шт.:",
    "dlg.room_eq.f.notes":         "Примечания:",
    "dlg.room_eq.sec.connect":     "Подключение к системам",
    "dlg.room_eq.f.heat_circ":     "Контур отопления",
    "dlg.room_eq.f.cool_circ":     "Контур холода",
    "dlg.room_eq.f.vent_sys":      "Приточная установка (AHU)",
    "dlg.room_eq.sum_power":       "Σ = {total:.0f} Вт",
    "dlg.room_eq.sum_flow":        "Σ = {total:.0f} м³/ч",
    "dlg.room_eq.coverage":        "  ·  {cov:.0f}% покрытия",

    # ========== Panel: Equipment ==========
    "panel.equipment.title":  "Оборудование (системы)",
    "panel.equipment.subtitle": ("Подбор источников по контурам: мощность и "
                                  "количество котлов / чиллеров, нагрузка "
                                  "контуров, DN, Δp и насосы. Системы и контуры "
                                  "задаются в «Зонах и системах»."),
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

    # ----- Подбор источников (деревья Источник→Контуры) -----
    "panel.equipment.btn.compute":      "Посчитать подбор",
    "panel.equipment.lbl.margin_heat":  "Запас тепло ×",
    "panel.equipment.lbl.margin_cool":  "Запас холод ×",
    "panel.equipment.tcol.name":        "Источник / контур",
    "panel.equipment.tcol.load":        "Нагрузка, кВт",
    "panel.equipment.tcol.pick":        "Подбор / тип",
    "panel.equipment.tcol.dn":          "DN",
    "panel.equipment.tcol.dp":          "Δp, кПа",
    "panel.equipment.tcol.pump":        "Насос",
    "panel.equipment.fmt.units":        "{kw} кВт × {n}",
    "panel.equipment.fmt.pump":         "{model} · {flow} м³/ч · {head} м",
    "panel.equipment.direct":           "Без контура",
    "panel.equipment.dhw":              ("ГВС: {kw} кВт — добавьте к источнику, "
                                          "греющему воду"),
    "panel.equipment.acol.ahu":         "AHU",
    "panel.equipment.acol.flow":        "Расход, м³/ч",
    "panel.equipment.acol.fan":         "Вентилятор",
    "panel.equipment.acol.q_heater":    "Калорифер, кВт",
    "panel.equipment.acol.q_cooler":    "Охладитель, кВт",
    "panel.equipment.acol.recovery":    "Рекуператор",
    "panel.equipment.status.computed":  "Подбор обновлён",
    # добавление / редактирование (ручная настройка)
    "panel.equipment.btn.add_boiler":   "+ Котёл",
    "panel.equipment.btn.add_chiller":  "+ Чиллер",
    "panel.equipment.btn.add_ahu":      "+ AHU",
    "panel.equipment.hint.edit":        ("Двойной клик по источнику / контуру / "
                                          "AHU — настроить параметры и привязки."),
    "panel.equipment.hint.required":    "Расчётная нагрузка: {kw} кВт",
    "panel.equipment.fmt.manual":       "{pick} (вручную)",
    "panel.equipment.dlg.source_title": "Источник: {name}",
    "panel.equipment.dlg.circuit_title":"Контур: {name}",
    "panel.equipment.dlg.ahu_title":    "AHU: {name}",
    "panel.equipment.dlg.add_boiler":   "Новый котёл / источник тепла",
    "panel.equipment.dlg.add_chiller":  "Новый чиллер / источник холода",
    "panel.equipment.dlg.add_ahu":      "Новая приточная установка (AHU)",
    "panel.equipment.f.name":           "Имя:",
    "panel.equipment.f.capacity":       "Ручная мощность агрегата, кВт (0 — авто)",
    "panel.equipment.f.units":          "Количество агрегатов",
    "panel.equipment.f.model":          "Модель",
    "panel.equipment.f.t_in_s":         "t притока лето, °C",
    "panel.equipment.f.heating_circuit":"Калорифер → контур",
    "panel.equipment.f.cooling_circuit":"Охладитель → контур",
    "panel.equipment.f.pipe_material":  "Материал труб",
    "panel.equipment.f.pump_reserve":   "Запас насоса ×",
    "panel.equipment.f.has_recovery":   "Рекуперация",

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
    "panel.ventilation.col.air":     "Возд.",
    "panel.ventilation.col.imbal":   "Дисбаланс",
    "panel.ventilation.tooltip.manual": ("Расход исправлен вручную — "
                                          "пересчёт не перетирает это помещение"),
    "panel.ventilation.btn_bulk":    "Групповая правка…",
    "panel.ventilation.bulk.title":  "Групповая правка расходов воздуха",
    "panel.ventilation.bulk.field":  "Параметр",
    "panel.ventilation.bulk.mode":   "Операция",
    "panel.ventilation.bulk.mode.set":   "Задать значение",
    "panel.ventilation.bulk.mode.scale": "Изменить на",
    "panel.ventilation.bulk.mode.ach":   "По кратности (ACH)",
    "panel.ventilation.bulk.value":  "Значение",
    "panel.ventilation.bulk.hint":   "Будет применено к {n} выделенным помещениям.",
    "panel.ventilation.bulk.no_selection": ("Не выделено ни одного помещения. "
                                            "Выделите строки (Ctrl/Shift) и повторите."),
    "panel.ventilation.bulk.applied": "Групповая правка: обновлено {n}",
    "panel.ventilation.ctx.reset":   "Сбросить ручную правку (пересчитать)",
    "panel.ventilation.ctx.reset_done": "Сброшено и пересчитано: {n}",
    "panel.ventilation.ctx.copy":    "Копировать (Ctrl+C)",
    "panel.ventilation.ctx.paste":   "Вставить (Ctrl+V)",
    "panel.ventilation.ctx.fill_down": "Заполнить вниз (Ctrl+D)",
    "panel.ventilation.ctx.clear":   "Очистить (Del)",
    "panel.ventilation.ctx.clear_done": "Очищено ячеек в строках: {n}",
    "panel.ventilation.ctx.undo":    "Отменить (Ctrl+Z)",
    "panel.ventilation.ctx.redo":    "Повторить (Ctrl+Y)",
    "panel.ventilation.paste.done":  "Вставлено значений: {n}",
    "panel.ventilation.fill_down.done": "Заполнено вниз: {n}",
    "panel.ventilation.undo.done":   "Отменено ({n})",
    "panel.ventilation.redo.done":   "Повторено ({n})",
    "panel.ventilation.preset.menu": "Применить пресет расхода",
    "panel.ventilation.preset.toilet":     "Санузел — вытяжка 10-кратная",
    "panel.ventilation.preset.toilet_ind": "Санузел индивид. — 50 м³/ч вытяжка",
    "panel.ventilation.preset.shower":     "Душевая — 75 м³/ч вытяжка",
    "panel.ventilation.preset.kitchen":    "Кухня — 60 м³/ч вытяжка",
    "panel.ventilation.preset.living":     "Жилая — приток 1-кратный",
    "panel.ventilation.preset.office":     "Офис — приток 3-кратный",
    "panel.ventilation.preset.applied":    "Пресет применён: {n}",
    "panel.ventilation.btn_norms":         "Нормы…",

    # ========== Диалог: редактор норм вентиляции по типам ==========
    "dlg.vent_norms.title":       "Нормы вентиляции — редактор",
    "dlg.vent_norms.scope_hint": (
        "Изменения сохраняются глобально для всех проектов:\n{path}\n"
        "Применяются к помещениям соответствующего типа при следующем "
        "расчёте вентиляции."),
    "dlg.vent_norms.types_group":  "Типы помещений",
    "dlg.vent_norms.col_type":     "Тип",
    "dlg.vent_norms.col_source":   "Источник",
    "dlg.vent_norms.src_sp":            "СП",
    "dlg.vent_norms.src_sp_overridden": "СП ✓",
    "dlg.vent_norms.src_custom":        "польз.",
    "dlg.vent_norms.btn_new":      "+ Новый тип",
    "dlg.vent_norms.btn_delete":   "🗑 Удалить",
    "dlg.vent_norms.params_group": "Параметры нормы",
    "dlg.vent_norms.status_custom": (
        "⊕ Пользовательский тип — все поля сохраняются как есть."),
    "dlg.vent_norms.status_overridden": (
        "✓ Переопределены поля: {fields}. СП-значения остальных полей "
        "сохраняются."),
    "dlg.vent_norms.status_default": (
        "○ Без правок — используются значения по СП."),
    "dlg.vent_norms.sep.supply":   "Приток (бóльшее из критериев)",
    "dlg.vent_norms.sep.exhaust":  "Вытяжка",
    "dlg.vent_norms.sep.hood":     "Зонт",
    "dlg.vent_norms.sep.desc":     "Описание",
    "dlg.vent_norms.f.is_nc": (
        "Без принудительной вентиляции (NC) — лестницы, лифты"),
    "dlg.vent_norms.f.exhaust_only": (
        "Только вытяжка (туалеты) — приток из перетока"),
    "dlg.vent_norms.f.has_hood": (
        "С зонтом (кухня) — часть вытяжки через зонт"),
    "dlg.vent_norms.f.has_co_control": "Управление по CO (парковки)",
    "dlg.vent_norms.f.m3_per_person": "На человека, м³/ч",
    "dlg.vent_norms.f.m3_per_m2":     "На м² площади, м³/ч·м²",
    "dlg.vent_norms.f.min_ach":       "Минимальная кратность, 1/ч",
    "dlg.vent_norms.f.m3_per_kw":     "На кВт тепловыделений, м³/ч·кВт",
    "dlg.vent_norms.f.m3_per_spectator": "На зрителя, м³/ч",
    "dlg.vent_norms.f.m3_per_car":    "На машино-место, м³/ч",
    "dlg.vent_norms.f.balance": (
        "Дисбаланс, % (отриц. → вытяжка > приток)"),
    "dlg.vent_norms.f.exhaust_per_m2": "Удельная вытяжка (туалеты), м³/ч·м²",
    "dlg.vent_norms.f.exhaust_min":    "Минимальная вытяжка, м³/ч",
    "dlg.vent_norms.f.hood_factor":    "Доля вытяжки через зонт (0..1)",
    "dlg.vent_norms.f.note":           "Норматив / комментарий",
    "dlg.vent_norms.btn_reset":        "↺ Сбросить тип к СП",
    "dlg.vent_norms.btn_save":         "💾 Сохранить",
    "dlg.vent_norms.btn_save_recalc":  "💾 Сохранить и пересчитать",
    "dlg.vent_norms.new_title":  "Новый тип",
    "dlg.vent_norms.new_prompt": (
        "Имя нового типа помещения (например: «СПА-зона», «Кинозал», "
        "«Бассейн»):"),
    "dlg.vent_norms.err_title":      "Ошибка",
    "dlg.vent_norms.err_not_number": "Поле «{label}» не число: {val}",
    "dlg.vent_norms.del_builtin_title": "Нельзя удалить",
    "dlg.vent_norms.del_builtin_msg": (
        "Тип «{t}» встроенный (СП). Можно только сбросить его override."),
    "dlg.vent_norms.del_confirm_title": "Удалить тип?",
    "dlg.vent_norms.del_confirm_msg": (
        "Удалить пользовательский тип «{t}»?{extra}"),
    "dlg.vent_norms.del_in_use": (
        "\n\n⚠ В текущем проекте {n} помещений имеют этот тип. После "
        "удаления они станут использовать дефолт «Прочее»."),
    "dlg.vent_norms.info_title":       "Информация",
    "dlg.vent_norms.reset_custom_msg": (
        "Пользовательский тип нельзя «сбросить к СП» — только удалить."),
    "dlg.vent_norms.reset_none_msg": (
        "У типа «{t}» нет правок — значения уже из СП."),
    "dlg.vent_norms.save_err_title": "Ошибка записи",
    "dlg.vent_norms.save_err_msg":   "Не удалось сохранить нормы:\n{e}",
    "dlg.vent_norms.reset_manual_title": "Сбросить ручные правки?",
    "dlg.vent_norms.reset_manual_msg": (
        "В проекте {n} помещений с ручными правками вентиляции. Сбросить "
        "их, чтобы пересчёт применил новые нормы?\n\n«Нет» — пересчитать "
        "только помещения без ручных правок."),
    "dlg.vent_norms.done_title":      "Готово",
    "dlg.vent_norms.done_recalc_msg": (
        "Нормы сохранены: {path}\nВентиляция пересчитана."),
    "dlg.vent_norms.saved_title": "Сохранено",
    "dlg.vent_norms.saved_msg": (
        "Нормы сохранены: {path}\nОни применятся при следующем расчёте "
        "вентиляции."),
    "dlg.vent_norms.calc_err_title": "Ошибка расчёта",

    # ========== Panel: Problems (проверки проекта) ==========
    "panel.problems.title":          "Проблемы и проверки",
    "panel.problems.hint":           "Двойной клик по строке — перейти к помещению.",
    "panel.problems.col.severity":   "Уровень",
    "panel.problems.col.category":   "Категория",
    "panel.problems.col.space":      "Помещение",
    "panel.problems.col.message":    "Сообщение",
    "panel.problems.severity.error": "Ошибка",
    "panel.problems.severity.warning": "Предупр.",
    "panel.problems.severity.info":  "Инфо",
    "panel.problems.summary":        "Ошибок: {e} · Предупреждений: {w} · Инфо: {i}",
    "panel.problems.empty":          "Проблем не найдено — проект в порядке.",
    "panel.problems.not_calculated": "Загрузите данные и выполните расчёт, чтобы увидеть проверки.",
    "panel.problems.tab.issues":     "Проверки",
    "panel.problems.tab.coverage":   "Матрица обслуживания",
    "panel.coverage.summary":        ("Всего: {total} · Требуют назначения: {missing} · "
                                        "Готовы: {ready}"),
    "panel.coverage.only_missing":   "Только не назначенные",
    "panel.coverage.search":         "Поиск по помещению или системе…",
    "panel.coverage.col.number":     "№",
    "panel.coverage.col.name":       "Помещение",
    "panel.coverage.col.level":      "Уровень",
    "panel.coverage.col.heating":    "Отопление",
    "panel.coverage.col.cooling":    "Охлаждение",
    "panel.coverage.col.ventilation": "Вентиляция",
    "panel.coverage.col.smoke":      "Дым/подпор",
    "panel.coverage.col.status":     "Статус",
    "panel.coverage.not_required":   "Не требуется",
    "panel.coverage.not_assigned":   "НЕ НАЗНАЧЕНО",
    "panel.coverage.unknown_system": "Нет в каталоге: {name}",
    "panel.coverage.air_prefix":     "Воздух: {name}",
    "panel.coverage.no_flow":        "Нет расхода",
    "panel.coverage.supply":         "П: {value}",
    "panel.coverage.exhaust":        "В: {value}",
    "panel.coverage.ready":          "Готово",
    "panel.coverage.problem":        "Требуется назначение",

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
    "panel.props.flag.unheated": "пол над неотапл.",
    "panel.props.flag.air_heat": "возд. отопление",
    "panel.props.flag.air_cool": "возд. охлаждение",
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
    "panel.ext.sum.energy":    ("Класс энергоэффективности (СП 50): {cls}\n"
                                 "Удельное потребление: {q:.1f} "
                                 "кВт·ч/(м²·год)\nОтклонение от нормы: "
                                 "{dev:+.1f} %\nШНҚ 2.01.18-24: {shnq}"),
    "panel.ext.sum.energy.shnq_ok":   "соответствует ({qd:.1f} ≤ {qov} Вт/м²)",
    "panel.ext.sum.energy.shnq_fail": "НЕ соответствует ({qd:.1f} > {qov} Вт/м²)",
    "panel.ext.sum.energy.shnq_na":   "нет норматива для типа/этажности",
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

    # ----- Единый рабочий стол «Зоны и системы» (ручное зонирование) -----
    "panel.zones.hint":             ("Слева — системы и контуры, справа — "
                                      "помещения. Выделите помещения и назначьте "
                                      "их системе/контуру кнопкой, перетаскиванием "
                                      "на узел дерева или через правый клик."),
    "panel.zones.domain.heating":      "Отопление",
    "panel.zones.domain.cooling":      "Холод",
    "panel.zones.domain.ventilation":  "Вентиляция",
    "panel.zones.load.heating":        "Q отопл., кВт",
    "panel.zones.load.cooling":        "Q охл., кВт",
    "panel.zones.load.ventilation":    "Приток, м³/ч",
    "panel.zones.tree.title":          "Системы и контуры",
    "panel.zones.tree.col.name":       "Система / контур",
    "panel.zones.tree.col.count":      "Помещ.",
    "panel.zones.rooms.title":         "Помещения",
    "panel.zones.btn.assistant":       "Помощник ▾",
    "panel.zones.btn.undo":            "↶ Отмена",
    "panel.zones.btn.add_system":      "+ Система",
    "panel.zones.btn.add_circuit":     "+ Контур",
    "panel.zones.btn.rename":          "Переименовать",
    "panel.zones.btn.delete":          "Удалить",
    "panel.zones.btn.assign_system":   "Назначить системе ▾",
    "panel.zones.btn.assign_circuit":  "Назначить контуру ▾",
    "panel.zones.btn.clear":           "Снять назначение",
    "panel.zones.rcol.number":         "№",
    "panel.zones.rcol.level":          "Этаж",
    "panel.zones.rcol.name":           "Помещение",
    "panel.zones.rcol.area":           "S, м²",
    "panel.zones.rcol.load":           "Нагрузка",
    "panel.zones.rcol.system":         "Система",
    "panel.zones.rcol.circuit":        "Контур / зона",
    "panel.zones.ctype.radiator":      "Радиаторы",
    "panel.zones.ctype.floor":         "Тёплый пол",
    "panel.zones.ctype.fancoil":       "Фанкойлы",
    "panel.zones.ctype.ahu_heater":    "Калорифер AHU",
    "panel.zones.ctype.ahu_cooler":    "Охладитель AHU",
    "panel.zones.ctype.chilled_beam":  "Охлаждаемые балки",
    "panel.zones.dlg.add_system_title":  "Новая система",
    "panel.zones.dlg.system_name":       "Имя системы:",
    "panel.zones.dlg.add_circuit_title": "Новый контур / зона",
    "panel.zones.dlg.circuit_name":      "Имя контура:",
    "panel.zones.dlg.circuit_type":      "Тип контура:",
    "panel.zones.dlg.parent_system":     "Система:",
    "panel.zones.dlg.rename_title":      "Переименование",
    "panel.zones.dlg.new_name":          "Новое имя:",
    "panel.zones.confirm.title":         "Подтверждение",
    "panel.zones.confirm.delete_system": ("Удалить систему «{name}» и её "
                                           "контуры? Помещения будут отвязаны."),
    "panel.zones.confirm.delete_circuit":("Удалить контур «{name}»? "
                                           "Помещения будут отвязаны."),
    "panel.zones.msg.no_selection":      "Выделите помещения в таблице.",
    "panel.zones.menu.new_system":       "➕ Новая система…",
    "panel.zones.menu.new_circuit":      "➕ Новый контур…",
    "panel.zones.menu.no_circuits":      "(контуров пока нет)",
    "panel.zones.menu.unassign_circuit": "✖ Без контура",
    "panel.zones.menu.assign_supply":    "Приток отдельно →",
    "panel.zones.menu.assign_exhaust":   "Вытяжка отдельно →",
    "panel.zones.menu.clear_split":      "✖ Снять раздельный приток/вытяжку",
    "panel.zones.status.assigned_flow":  "Раздельная привязка ({flow}): {n}",
    "panel.zones.status.assigned_sys":   "Назначено системе: {n}",
    "panel.zones.status.assigned_circ":  "Назначено контуру: {n}",
    "panel.zones.status.cleared":        "Снято назначение: {n}",
    "panel.zones.status.undone":         "Отменено: {n}",
    "panel.zones.summary.line":          ("Систем: {systems}  ·  назначено "
                                           "{assigned} из {rooms}"),

    # ----- Единый рабочий стол «Системы и оборудование» -----
    "panel.sysworkspace.title":      "Системы и оборудование",
    "panel.sysworkspace.hint":       ("Назначьте помещения системам слева, "
                                       "затем «Посчитать подбор»."),
    "panel.sysworkspace.empty_tree": "Систем пока нет",
    "panel.sysworkspace.empty_tree_hint":
        "Создайте источник кнопкой «+ Система» — или перетащите помещения "
        "на узел позже.",
    "panel.sysworkspace.tree.name":  "Источник / контур",
    "panel.sysworkspace.tree.kw":    "кВт",
    "panel.sysworkspace.rcol.device":"Прибор",
    "panel.sysworkspace.rcol.exhaust":"Вытяжка, м³/ч",
    "panel.sysworkspace.rcol.hood":  "Зонт, м³/ч",
    "panel.sysworkspace.btn.device": "Прибор…",
    "panel.sysworkspace.filter_node":"Только выбранный узел",
    "panel.sysworkspace.summary.none":"Выберите источник или контур слева",
    "panel.sysworkspace.sum.source": "{name}  ·  требуется {req} кВт  ·  подобрано {pick}",
    "panel.sysworkspace.sum.circuit":("{name}  ·  нагрузка {load} кВт  ·  DN {dn}  ·  "
                                       "Δp {dp} кПа  ·  насос {pump}"),
    "panel.sysworkspace.sum.ahu":    ("{name}  ·  расход {flow} м³/ч  ·  вентилятор {fan}  ·  "
                                       "калорифер {qh} кВт  ·  охладитель {qc} кВт"),
    # Воздушное отопление / охлаждение
    "panel.sysworkspace.rcol.air":   "Возд.",
    "panel.sysworkspace.air.mark_heat": "О",
    "panel.sysworkspace.air.mark_cool": "Х",
    "panel.sysworkspace.air.menu":   "Воздушное отопление / охлаждение",
    "panel.sysworkspace.air.heat_on":"Включить отопление",
    "panel.sysworkspace.air.cool_on":"Включить охлаждение",
    "panel.sysworkspace.air.both_on":"Включить отопление и охлаждение",
    "panel.sysworkspace.air.off":    "Выключить воздушный режим",
    "panel.sysworkspace.air.status": "Воздушный режим: изменено {n} помещ.",
    "panel.sysworkspace.assistant.missing": "Заполнить только пропуски…",
    "panel.sysworkspace.assistant.missing_title": "Безопасное назначение систем",
    "panel.sysworkspace.assistant.missing_preview": (
        "Будут заполнены только пустые назначения; существующие ручные связи "
        "останутся без изменений.\n\n"
        "Помещения: {rooms}\n"
        "• отопление: {heat}\n• охлаждение: {cool}\n• вентиляция: {vent}\n\n"
        "Новые системы: {systems}\n"
        "• отопление: {heat_sys}\n• охлаждение: {cool_sys}\n"
        "• вентиляция: {vent_sys}\n\n"
        "Имена AUTO — предварительные. После назначения проверьте и при "
        "необходимости объедините системы. Продолжить?"),
    "panel.sysworkspace.assistant.missing_none": (
        "Пропусков назначения нет — все требуемые системы зарегистрированы."),
    "panel.sysworkspace.assistant.missing_status": (
        "Назначено помещений: {rooms} · создано систем: {systems}"),
    "panel.sysworkspace.assistant.finalize": "Проверить и объединить AUTO…",
    "panel.sysworkspace.assistant.finalize_title": "Финализация AUTO-систем",
    "panel.sysworkspace.assistant.finalize_preview": (
        "Предварительных систем AUTO: {auto}\n"
        "Групп объединения: {groups} · будет удалено дублей: {removed}\n"
        "Исправлений геометрии: {geometry}\n\n{details}\n\n"
        "После применения программа повторит полный расчёт нагрузок, "
        "вентиляции, AHU и подбора мощностей. Продолжить?"),
    "panel.sysworkspace.assistant.finalize_merge_line": (
        "• {sources} → {target}: {rooms} помещ., {flow} м³/ч"),
    "panel.sysworkspace.assistant.finalize_geometry_line": (
        "• объём {number} → {volume} м³"),
    "panel.sysworkspace.assistant.finalize_none": (
        "Нет безопасных групп для объединения и исправлений геометрии."),
    "panel.sysworkspace.assistant.finalize_status": (
        "Объединено групп: {groups} · удалено систем: {systems} · "
        "исправлено объёмов: {geometry} · после пересчёта назначено помещений: "
        "{rooms} · создано систем: {created}"),
    "panel.sysworkspace.assistant.circuits": "Создать контуры и связать AHU…",
    "panel.sysworkspace.assistant.circuits_title": (
        "Контуры отопления и холодоснабжения"),
    "panel.sysworkspace.assistant.circuits_preview": (
        "Будет создано контуров: {circuits} "
        "(отопление {heat_circuits}, холод {cool_circuits})\n"
        "Назначений помещений: {rooms} "
        "(отопление {heat_rooms}, холод {cool_rooms})\n"
        "Связей теплообменников AHU: {ahus} "
        "(калориферы {heat_ahus}, охладители {cool_ahus})\n"
        "Типы: радиаторы / фанкойлы / калориферы и охладители AHU\n"
        "Конфликтов имён: {conflicts} · неоднозначных связей пропущено: {skipped}\n\n"
        "Ручные контуры и существующие связи не изменяются. После применения "
        "программа пересчитает AHU, трубопроводы, насосы и мощности. Продолжить?"),
    "panel.sysworkspace.assistant.circuits_none": (
        "Нет безопасных назначений контуров. Конфликтов имён: {conflicts}; "
        "неоднозначных связей AHU: {skipped}."),
    "panel.sysworkspace.assistant.circuits_status": (
        "Создано контуров: {circuits} · назначено помещений: {rooms} · "
        "связано теплообменников AHU: {ahus}"),
    "panel.sysworkspace.assistant.catalog": "Подобрать котлы и чиллеры N+1…",
    "panel.sysworkspace.assistant.catalog_title": (
        "Каталоговый подбор источников N+1"),
    "panel.sysworkspace.assistant.catalog_preview": (
        "Будет подобрано источников: {systems} "
        "(отопление {heat}, холод {cool})\n"
        "Пропущено ручных или несовместимых систем: {skipped}\n\n"
        "{details}\n\n"
        "Подбор выполняется только для AUTO-систем без ручной модели. "
        "Мощность указана на один агрегат; схема — рабочие + резервные. "
        "Каталог предварительный. Продолжить?"),
    "panel.sysworkspace.assistant.catalog_line": (
        "• {system}: требуется {required} кВт → {model}, {unit} кВт "
        "({working}+{reserve})"),
    "panel.sysworkspace.assistant.catalog_none": (
        "Нет AUTO-источников для безопасного каталогового подбора. "
        "Пропущено ручных или несовместимых систем: {skipped}."),
    "panel.sysworkspace.assistant.catalog_status": (
        "Подобраны котлы и чиллеры с резервом N+1: {systems}"),
    # Вкладки правой панели + выбор вида оборудования
    "panel.sysworkspace.tab.rooms":  "Помещения",
    "panel.sysworkspace.tab.calc":   "Расчёт",
    "panel.sysworkspace.dlg.kind_title": "Новое оборудование",
    "panel.sysworkspace.dlg.kind":   "Вид оборудования:",
    # Детальный расчёт оборудования
    "panel.detail.none":     "Выберите оборудование или источник слева для детального расчёта",
    "panel.detail.params":   "Параметры (правка → живой пересчёт)",
    "panel.detail.f.t_supply_w": "t подачи зима, °C",
    "panel.detail.f.t_supply_s": "t подачи лето, °C",
    "panel.detail.f.eta_w":  "КПД рекуп. зима",
    "panel.detail.f.eta_s":  "КПД рекуп. лето",
    "panel.detail.f.fan_pressure": "Давление вент., Па (0 — авто)",
    "panel.detail.f.fan_eff": "КПД вентилятора",
    "panel.detail.kind.ahu":          "Приточная установка",
    "panel.detail.kind.supply_fan":   "Приточный вентилятор",
    "panel.detail.kind.exhaust_fan":  "Вытяжной вентилятор",
    "panel.detail.kind.local_exhaust":"Местный отсос / зонт",
    "panel.detail.flows":    "Помещений: {n} · приток {sup} м³/ч · вытяжка {exh} м³/ч",
    "panel.detail.heater":   "Калорифер (зима)",
    "panel.detail.cooler":   "Охладитель (лето)",
    "panel.detail.coil_air": "Воздух: {q} кВт · {tin}→{tout} °C (Δt {dt})",
    "panel.detail.coil_water": "Вода: {ts}/{tr} °C · Δt {dtw} · G {g} кг/ч ({gm} м³/ч) · DN {dn} · v {v} м/с",
    "panel.detail.cooler_extra": "явн. {qs} / скр. {ql} кВт · конденсат {cond} кг/ч",
    "panel.detail.fan_supply":  "Вентилятор (приток)",
    "panel.detail.fan_exhaust": "Вентилятор (вытяжка)",
    "panel.detail.fan_line": "{flow} м³/ч · {dp} Па ({src}) · {kw} кВт · SFP {sfp} Вт/(м³/с)",
    "panel.detail.src.manual":  "ручное",
    "panel.detail.src.network": "из сети",
    "panel.detail.src.default": "типовое",
    "panel.detail.source_head": "Требуется {req} кВт · подбор {unit} кВт ×{n} · нагрузка {q} кВт",
    "panel.detail.source_circ": "Контур {name}: {q} кВт · {rooms} помещ. · DN {dn} · насос {pump}",
    "panel.detail.circuit_head": "Нагрузка {q} кВт ({rooms} помещ. + AHU {qa} кВт) · DN {dn} · Δp {dp} кПа · насос {pump}",
    # Источник тепла/холода (карточка «Оборудование»)
    "panel.detail.kind.boiler":  "Источник тепла",
    "panel.detail.kind.chiller": "Источник холода",
    "panel.detail.f.t_sup":      "t подачи, °C",
    "panel.detail.f.t_ret":      "t обратки, °C",
    "panel.detail.f.eff":        "КПД источника",
    "panel.detail.f.cop":        "COP / EER",
    "panel.detail.f.capacity":   "Ед. мощность, кВт (0 — авто)",
    "panel.detail.f.units":      "Кол-во агрегатов",
    "panel.detail.src.required": "Требуется {req} кВт (нагрузка {q} кВт × запас {m})",
    "panel.detail.src.block_heat": ("Тепловой баланс блока «{block}»: "
                                    "помещения {rooms} + приточные {ahu} "
                                    "+ ГВС {dhw} = <b>{q} кВт</b>"),
    "panel.detail.src.block_cool": ("Тепловой баланс блока «{block}»: "
                                    "помещения {rooms} + приточные {ahu} "
                                    "= <b>{q} кВт</b>"),
    "panel.detail.src.picked_auto":   "Подбор (авто): {unit} кВт × {n}",
    "panel.detail.src.picked_manual": (
        "Подбор (каталог): {unit} кВт × {n} "
        "(раб. {working} + резерв {reserve}) · {model}"),
    "panel.detail.src.ahu":      "в т.ч. калориферы/охладители AHU: {q} кВт",
    "panel.detail.src.direct":   "Помещений напрямую: {n} ({q} кВт)",
    # ===== Panel: Equipment (раздел «Оборудование») =====
    "panel.equipws.title":   "Оборудование",
    "panel.equipws.hint":    ("Слева — всё оборудование по категориям. Выберите "
                               "установку: справа полная информация и правка "
                               "параметров с живым пересчётом."),
    "panel.equipws.cat.heat":"Источники тепла",
    "panel.equipws.cat.cool":"Источники холода",
    "panel.equipws.cat.vent":"Вентиляция",
    "panel.equipws.btn.add": "Добавить",
    "panel.equipws.col.name":"Оборудование",
    "panel.equipws.col.power":"Подбор",
    "panel.equipws.menu.block": "🏗 Блок",
    "panel.equipws.grp.kw":   "Σ {kw} кВт",
    "panel.equipws.add.boiler":  "Котёл / источник тепла",
    "panel.equipws.add.chiller": "Чиллер / источник холода",

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
    "panel.constructions.btn_add":        "Добавить…",
    "panel.constructions.btn_edit":       "Изменить…",
    "panel.constructions.btn_delete":     "Удалить",
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
    "panel.constructions.dlg.new_title":  "Новая конструкция",
    "panel.constructions.dlg.edit_title": "Изменить конструкцию",
    "panel.constructions.dlg.family":     "Семейство:",
    "panel.constructions.dlg.type":       "Тип:",
    "panel.constructions.dlg.thickness":  "Толщина δ, мм:",
    "panel.constructions.dlg.u":          "U, Вт/(м²·К):",
    "panel.constructions.dlg.shgc":       "SHGC (для светопрозрачных):",
    "panel.constructions.dlg.note":       "Примечание:",
    "panel.constructions.dlg.r_hint":     "R = {r} м²·К/Вт",
    "panel.constructions.dlg.preset_desc": "{description}<br><i>Категория: {category}, слоёв: {n}</i>",
    "panel.constructions.msg.edit_pick":  "Выделите одну конструкцию для изменения.",
    "panel.constructions.msg.delete_pick": "Выделите конструкцию для удаления.",
    "panel.constructions.msg.delete_ask": "Удалить конструкцию «{key}»?\nНа неё ссылаются элементов: {n}.",
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
    "panel.constructions.title.add":      "Добавление конструкции",
    "panel.constructions.title.edit":     "Изменение конструкции",
    "panel.constructions.title.delete":   "Удаление конструкции",
    "panel.constructions.title.err":      "Ошибка",
    "panel.constructions.title.layers":   "Слои",
    "panel.constructions.title.preset":   "Пресет",
    "panel.constructions.title.bulk":     "Bulk-edit",
    "panel.constructions.title.cleanup":  "Очистка",
    "panel.constructions.title.remove":   "Удалить неиспользуемые",
    "panel.constructions.title.import_strategy": "Стратегия импорта",
    "panel.constructions.title.export":   "Экспорт каталога конструкций",
    "panel.constructions.title.import":   "Импорт каталога конструкций",
    "panel.constructions.title.import_err": "Ошибка импорта",
    "panel.constructions.status.created": "Создана конструкция «{key}».",
    "panel.constructions.status.updated": "Конструкция «{key}» изменена.",
    "panel.constructions.status.deleted": "Удалена конструкция «{key}» (затронуто элементов: {n}).",
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
    "panel.boundaries.btn_internal":    "🏠 Внутренними",
    "panel.boundaries.btn_external":    "🌤 Наружными",
    "panel.boundaries.status.ext":      "Помечено ограждений: {n}. Пересчёт выполнен.",
    "panel.boundaries.status.ext_noop": "Нечего менять: ограждения уже в нужном состоянии.",
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
    "dlg.space.title_edit":      "Изменить помещение",
    "dlg.space.number":          "№ помещения:",
    "dlg.space.number_ph":       "Например, 101 или B01-105",
    "dlg.space.name":            "Название:",
    "dlg.space.name_ph":         "Например, «Гостиная 18 м²»",
    "dlg.space.level":           "Этаж:",
    "dlg.space.area":            "Площадь:",
    "dlg.space.height":          "Высота:",
    "dlg.space.volume":          "Объём:",
    "dlg.space.t_heat":          "tв зимой:",
    "dlg.space.t_cool":          "tв летом:",
    "dlg.space.wc_count":        "Унитазов:",
    "dlg.space.urinal_count":    "Писсуаров:",
    "dlg.space.sanitary_hint":   "Для санузлов: вытяжка по приборам (ШНҚ 2.08.02-23 — 100 м³/ч на унитаз, 50 на писсуар). 0 — расчёт по площади.",
    "dlg.space.water_surface":   "Зеркало воды:",
    "dlg.space.water_temp":      "tводы:",
    "dlg.space.pool_hint":       "Для бассейнов: приток берёт max с расходом на удаление влаги (испарение с зеркала, СП 31-113). 0 — без влагоудаления.",
    "dlg.space.spectator_count": "Зрит. мест:",
    "dlg.space.car_count":       "Машино-мест:",
    "dlg.space.occupancy_hint":  "Зрители (ШНҚ табл.23: +20 м³/ч на место) — для спортзалов/залов; машино-места — для парковок (расчёт по CO). 0 — не учитывать.",
    "dlg.space.geom_hint":       "Объём = площадь × высота. Меняешь объём — пересчитывается высота.",
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
    "dlg.smoke.err.no_name":     "Введите имя системы — без имени систему нельзя создать.",
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
    "dlg.smoke.kmk_corr.width":  "B — ширина створки двери, м:",
    "dlg.smoke.kmk_corr.height": "H — высота двери, м (≤2.5):",
    "dlg.smoke.kmk_corr.kind":   "Тип здания:",
    "dlg.smoke.kmk_corr.public": "Общественное / адм.-быт. / произв.",
    "dlg.smoke.kmk_corr.residential": "Жилое",
    "dlg.smoke.kmk_corr.kd":     "Kd — коэф. открывания (1.0 / 0.8):",
    "dlg.smoke.kmk_corr.formula":("Формула (жил.):  G = 3420 · B · n · H^1.5\n"
                                   "Формула (общ.):  G = 4300 · B · n · H^1.5 · Kd   [кг/ч]"),
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
    "dlg.smoke.method.kmk_corridor":       "КМК Прил. 22 ф.(1)/(2): коридор G = K·B·n·H^1.5",
    "dlg.smoke.method.nfpa_plume_axi":     "NFPA 92 п. 5.5.1: осесимметричный плюм",
    "dlg.smoke.method.manual":             "Ручной ввод расхода",
    "dlg.smoke.method.stairs_pressure":    "Подпор лестничной клетки",
    "dlg.smoke.method.elevator_pressure":  "Подпор шахты лифта",
    "dlg.smoke.systype.smoke_removal":     "СДУ — удаление дыма",
    "dlg.smoke.systype.air_supply":        "СПВ — подпор воздуха",
    "dlg.smoke.systype.compensation":      "Компенсирующая подача",
    "dlg.smoke.purpose.parking":           "Парковка",
    "dlg.smoke.purpose.warehouse":         "Склад",
    "dlg.smoke.purpose.technical":         "Техническое (кабельное, электрощитовая)",
    "dlg.smoke.purpose.corridor":          "Коридор",
    "dlg.smoke.purpose.atrium":            "Атриум / зал сборки людей",
    "dlg.smoke.purpose.trading_hall":      "Торговый зал",
    "dlg.smoke.purpose.stairs":            "Лестничная клетка",
    "dlg.smoke.purpose.elevator":          "Шахта лифта",
    "dlg.smoke.purpose.vestibule":         "Тамбур-шлюз",
    "dlg.smoke.purpose.refuge":            "Зона безопасности МГН",

    # ========== Dialog: Smoke attach spaces ==========
    "dlg.smoke_attach.title":            "Привязка помещений: {name}",
    "dlg.smoke_attach.search":           "Поиск: номер, название, система…",
    "dlg.smoke_attach.col.number":       "Номер",
    "dlg.smoke_attach.col.name":         "Название",
    "dlg.smoke_attach.col.level":        "Этаж",
    "dlg.smoke_attach.col.type":         "Тип",
    "dlg.smoke_attach.col.area":         "Площадь, м²",
    "dlg.smoke_attach.col.current":      "Текущая система",
    "dlg.smoke_attach.check_visible":    "Отметить видимые",
    "dlg.smoke_attach.uncheck_visible":  "Снять видимые",
    "dlg.smoke_attach.count":            "Отмечено: {n}",
    "dlg.smoke_attach.hint":             ("Отмеченные помещения будут привязаны к системе, снятые — "
                                          "отвязаны от неё. Привязка к другой системе того же типа "
                                          "будет переназначена."),

    # ========== Panel: Smoke ==========
    "panel.smoke.title":              "Дымоудаление и подпор",
    "panel.smoke.card.params.title":  "Параметры",
    "panel.smoke.card.params.sub":    "Активный норматив, сценарий пожара и общие действия над системами.",
    "panel.smoke.norm":               "Норматив:",
    "panel.smoke.scenario":           "Сценарий:",
    "panel.smoke.scenario.single":    "Один очаг пожара",
    "panel.smoke.scenario.multiple":  "Несколько зон одновременно (запас)",
    "panel.smoke.btn_assign":         "Авто-присвоить",
    "panel.smoke.btn_assign_tt":      ("Создать системы СДУ для парковок, складов, технических "
                                        "помещений, длинных коридоров, залов сборки людей и СПВ "
                                        "для лестниц/лифтов."),
    "panel.smoke.btn_calc":           "▶  Рассчитать",
    "panel.smoke.card.systems.title": "Системы",
    "panel.smoke.card.systems.sub":   "Двойной клик по строке — редактировать параметры.",
    "panel.smoke.btn_add":            "➕  Добавить",
    "panel.smoke.btn_edit":           "Редактировать",
    "panel.smoke.btn_attach":         "Привязать помещения",
    "panel.smoke.btn_attach_tt":      ("Отметить помещения, обслуживаемые выбранной системой "
                                        "СДУ/СПВ (например, техпомещения, которые авто-присвоение "
                                        "не охватывает)."),
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
    "panel.smoke.status.attached":    "Система {name}: привязано {added}, отвязано {removed}",
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
    "panel.eng.tab.comfort":         "Комфорт PMV/PPD",
    "panel.eng.tab.curtain":         "Тепловые завесы",
    "panel.eng.tab.itp":             "ИТП / ТО",
    "panel.eng.tab.grilles":         "Решётки",

    # ========== Engineering: подбор решёток (ARKTIKA/Арктос) ==========
    "panel.eng.grille.info":         ("Подбор воздухораспределительных решёток по каталогу "
                                        "ARKTIKA/Арктос (изд. 8.02). Главный критерий — звуковая "
                                        "мощность LwA; дополнительно скорость в живом сечении и "
                                        "ΔPполн. Каталожный предподбор; финальный — по программе "
                                        "изготовителя."),
    "panel.eng.grille.mount":        "Монтаж:",
    "panel.eng.grille.mount.all":    "Любой",
    "panel.eng.grille.mount.wall":   "Настенные",
    "panel.eng.grille.mount.plenum": "С присоед. камерой (-К)",
    "panel.eng.grille.mount.round_duct": "Для круглых воздуховодов",
    "panel.eng.grille.mount.slot":   "Щелевые",
    "panel.eng.grille.mount.transfer": "Переточные",
    "panel.eng.grille.mount.floor":  "Напольные",
    "panel.eng.grille.family":       "Серия:",
    "panel.eng.grille.family.all":   "Все",
    "panel.eng.grille.lwa":          "Шум LwA ≤",
    "panel.eng.grille.lwa.unit":     "дБ(А)",
    "panel.eng.grille.vel":          "Скорость ≤",
    "panel.eng.grille.vel.unit":     "м/с",
    "panel.eng.grille.vel.any":      "любая",
    "panel.eng.grille.size":         "Габарит:",
    "panel.eng.grille.size.unit":    " мм",
    "panel.eng.grille.calc.title":   "Калькулятор подбора",
    "panel.eng.grille.calc.flow":    "Расход L₀, м³/ч:",
    "panel.eng.grille.calc.btn":     "▶  Подобрать",
    "panel.eng.grille.calc.empty":   ("Под заданный расход и ограничения ничего не подошло — "
                                        "ослабьте ограничение по шуму либо смените серию/монтаж."),
    "panel.eng.grille.proj.title":   "Подбор по помещениям проекта",
    "panel.eng.grille.proj.btn":     "▶  Подобрать для всех помещений",
    "panel.eng.grille.proj.status":  "Решётки подобраны: {n} помещ.",
    "panel.eng.grille.proj.none":    "Нет помещений с заданным вентрасходом (приток/вытяжка).",
    "panel.eng.grille.col.variant":  "Решётка",
    "panel.eng.grille.col.size":     "Размер",
    "panel.eng.grille.col.qty":      "Кол-во",
    "panel.eng.grille.col.v":        "v, м/с",
    "panel.eng.grille.col.lwa":      "LwA, дБ(А)",
    "panel.eng.grille.col.dp":       "ΔP, Па",
    "panel.eng.grille.col.throw":    "Дальноб., м",
    "panel.eng.grille.col.note":     "Примечание",
    "panel.eng.grille.col.no":       "№",
    "panel.eng.grille.col.room":     "Помещение",
    "panel.eng.grille.col.qs":       "Приток, м³/ч",
    "panel.eng.grille.col.gs":       "Приточная решётка",
    "panel.eng.grille.col.qe":       "Вытяжка, м³/ч",
    "panel.eng.grille.col.ge":       "Вытяжная решётка",
    "panel.eng.grille.dash":         "—",

    # ========== Engineering: воздушно-тепловые завесы ==========
    "panel.eng.cu.info":             ("Подбор воздушно-тепловой завесы шиберующего типа "
                                        "(СНиП 2.04.05 прил. 20 / СП 60.13330 п.7.7): расход и "
                                        "тепловая мощность по разности давлений на проёме. "
                                        "Коэффициенты q̄ и μ уточняйте по данным изготовителя."),
    "panel.eng.cu.type":             "Тип проёма:",
    "panel.eng.cu.type_door":        "Наружная дверь",
    "panel.eng.cu.type_gate":        "Ворота / технологический проём",
    "panel.eng.cu.purpose":          "Назначение:",
    "panel.eng.cu.purpose_public":   "Общественное / адм.-бытовое (t_см 14 °C)",
    "panel.eng.cu.purpose_ind_light": "Производственное, лёгкая работа (t_см 12 °C)",
    "panel.eng.cu.purpose_ind_none": "Произв. без пост. рабочих мест (t_см 5 °C)",
    "panel.eng.cu.width":            "Ширина проёма:",
    "panel.eng.cu.height":           "Высота проёма:",
    "panel.eng.cu.bld_height":       "Высота здания:",
    "panel.eng.cu.t_out":            "t наружная (Б):",
    "panel.eng.cu.t_in":             "t внутренняя:",
    "panel.eng.cu.t_mix":            "t смеси у проёма:",
    "panel.eng.cu.wind":             "Скорость ветра:",
    "panel.eng.cu.q_ratio":          "q̄ (G_зав/G_проёма):",
    "panel.eng.cu.mu":               "μ (коэф. расхода):",
    "panel.eng.cu.slot":             "Площадь щелей (0 — нет):",
    "panel.eng.cu.intake_inside":    "Забор воздуха изнутри",
    "panel.eng.cu.btn_run":          "▶ Рассчитать завесу",
    "panel.eng.cu.col.param":        "Параметр",
    "panel.eng.cu.col.value":        "Значение",
    "panel.eng.cu.row.area":         "Площадь проёма, м²",
    "panel.eng.cu.row.dp":           "Расчётная Δp, Па",
    "panel.eng.cu.row.g":            "Расход завесы, кг/ч",
    "panel.eng.cu.row.l":            "Расход завесы, м³/ч",
    "panel.eng.cu.row.t_supply":     "t подачи завесы, °C",
    "panel.eng.cu.row.q":            "Мощность калорифера, кВт",
    "panel.eng.cu.row.v_slot":       "Скорость выпуска, м/с",
    "panel.eng.cu.status":           "Завеса рассчитана",

    # ========== Engineering: ИТП / теплообменники ==========
    "panel.eng.itp.info":            ("Подбор пластинчатого теплообменника по LMTD (противоток): "
                                        "поверхность с запасом на загрязнение и расходы сторон. "
                                        "k = 3000…5500 Вт/(м²·К) для разборных ТО вода-вода; "
                                        "финальный подбор — по программе изготовителя."),
    "panel.eng.itp.preset":          "Температурный график:",
    "panel.eng.itp.preset_95_70":    "Отопление 95/70 → 80/60",
    "panel.eng.itp.preset_80_60":    "Отопление 80/60 → 70/50",
    "panel.eng.itp.preset_dhw":      "ГВС 70/30 → 5/60",
    "panel.eng.itp.q":               "Нагрузка Q:",
    "panel.eng.itp.btn_from_project": "Q из теплопотерь проекта",
    "panel.eng.itp.no_loads":        "Теплопотери ещё не рассчитаны.",
    "panel.eng.itp.k":               "k теплопередачи:",
    "panel.eng.itp.margin":          "Запас поверхности:",
    "panel.eng.itp.t_hot_in":        "Греющая, вход:",
    "panel.eng.itp.t_hot_out":       "Греющая, выход:",
    "panel.eng.itp.t_cold_in":       "Нагреваемая, вход:",
    "panel.eng.itp.t_cold_out":      "Нагреваемая, выход:",
    "panel.eng.itp.btn_run":         "▶ Подобрать ТО",
    "panel.eng.itp.col.param":       "Параметр",
    "panel.eng.itp.col.value":       "Значение",
    "panel.eng.itp.row.lmtd":        "LMTD, K",
    "panel.eng.itp.row.area":        "Поверхность (с запасом), м²",
    "panel.eng.itp.row.g_hot":       "Расход греющей, м³/ч",
    "panel.eng.itp.row.g_cold":      "Расход нагреваемой, м³/ч",
    "panel.eng.itp.status":          "Теплообменник подобран",
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
    "panel.eng.duct.btn_fan":        "Подобрать вентилятор",
    "panel.eng.duct.fan_title":      "Подбор вентилятора",
    "panel.eng.duct.fan_head":       ("Рабочая точка: Q = {q} м³/ч, ΔP = {dp} Па.\n"
                                        "Каталожный предподбор (парабола по двум точкам) — "
                                        "финальный подбор по программе изготовителя."),
    "panel.eng.duct.fan_pick":       ("• {name} ({family}): {p_avail:.0f} Па в точке "
                                        "(запас {margin:.0f}%, {ratio:.0f}% кривой), "
                                        "{power:.0f} Вт, {noise:.0f} дБ(А)"),
    "panel.eng.duct.fan_none":       ("Для точки Q = {q} м³/ч, ΔP = {dp} Па в каталоге "
                                        "ничего не подошло. Добавьте модели в "
                                        "~/.hvac_calc/catalogs/ (тип \"fans\") или разбейте "
                                        "систему на несколько вентиляторов."),

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

    # Comfort (PMV/PPD, ISO 7730)
    "panel.eng.cf.info":             ("Тепловой комфорт по ISO 7730 (метод Фангера): PMV — средняя "
                                        "оценка теплоощущения (−3…+3), PPD — % недовольных. Категории: "
                                        "A (|PMV|<0.2), B (<0.5), C (<0.7). Расчёт по уставкам "
                                        "помещений; оптимум ГОСТ 30494 ≈ категория B."),
    "panel.eng.cf.btn_run":          "▶  Рассчитать PMV/PPD",
    "panel.eng.cf.met":              "Метаболизм, met:",
    "panel.eng.cf.vair":             "Подвижность воздуха, м/с:",
    "panel.eng.cf.col.number":       "№",
    "panel.eng.cf.col.name":         "Помещение",
    "panel.eng.cf.col.t_w":          "t зима, °C",
    "panel.eng.cf.col.pmv_w":        "PMV зима",
    "panel.eng.cf.col.ppd_w":        "PPD зима, %",
    "panel.eng.cf.col.cat_w":        "Кат. зима",
    "panel.eng.cf.col.t_s":          "t лето, °C",
    "panel.eng.cf.col.pmv_s":        "PMV лето",
    "panel.eng.cf.col.ppd_s":        "PPD лето, %",
    "panel.eng.cf.col.cat_s":        "Кат. лето",
    "panel.eng.cf.status":           "Комфорт рассчитан",

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
    "panel.eng.en.btn_epw":          "Загрузить EPW…",
    "panel.eng.en.btn_epw_clear":    "✕ Убрать EPW",
    "panel.eng.en.epw_filter":       "Погодные файлы EPW (*.epw);;Все файлы (*)",
    "panel.eng.en.epw_none":         ("Климат: синтетический профиль из расчётных T. "
                                        "Точнее — реальный метеогод EPW (climate.onebuilding.org)."),
    "panel.eng.en.epw_loaded":       "Климат: EPW {loc} ({tmin:+.1f}…{tmax:+.1f} °C)",
    "panel.eng.en.epw_design":       ("Расчётные по файлу: пятидневка {t5:+.1f} °C · "
                                        "лето 0,95: {t95:+.1f} °C · ГСОП {gsop:.0f}"),
    "panel.eng.en.epw_design_tt":    ("Расчётные параметры из почасовых данных EPW:\n"
                                        "Наиболее холодная пятидневка: {t5:+.1f} °C (≈ обесп. 0,92)\n"
                                        "Наиболее холодные сутки: {t1:+.1f} °C (≈ обесп. 0,98)\n"
                                        "Лето, обесп. 0,95 (≤440 ч/год): {t95:+.1f} °C\n"
                                        "Лето, обесп. 0,98 (≤88 ч/год): {t98:+.1f} °C\n"
                                        "Суточная амплитуда тёплого месяца: {amp:.1f} K\n"
                                        "Период ≤8 °C: {z8} сут, средняя {t8:+.1f} °C\n"
                                        "Период ≤12 °C: {z12} сут, средняя {t12:+.1f} °C\n"
                                        "ГСОП (t_в=20 °C): {gsop:.0f} °C·сут\n"
                                        "Зимние значения — по одному метеогоду, сверяйте со справочником."),
    "panel.eng.en.epw_err":          "Ошибка чтения EPW",
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
    "panel.eng.en.row.e_solar":      "Солнце через остекление (EPW), кВт·ч/год",
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
    "export.blocked.title":          "Финальная выдача заблокирована",
    "export.blocked.msg":            ("Найдено критических проблем: {n}. Исправьте их в разделе "
                                        "«Проблемы → Матрица обслуживания»."),
    "export.blocked.more":           "…и ещё {n}",
    "export.fmt.excel.title":        "Полный Excel-отчёт",
    "export.fmt.excel.desc":         ("14 листов: помещения, ограждения, сводки, ГВС, энергопаспорт, "
                                        "точка росы, воздуховоды, трубы."),
    "export.fmt.excel.name":         "HVAC_{name}.xlsx",
    "export.fmt.pdf.title":          "PDF: пояснительная записка",
    "export.fmt.pdf.desc":           "До 12 разделов по заполненным данным проекта.",
    "export.fmt.pdf.name":           "Отчёт_{name}.pdf",
    "export.fmt.docx.title":         "DOCX: пояснительная записка (Word)",
    "export.fmt.docx.desc":          ("Те же разделы, что в PDF, но в редактируемом формате — "
                                        "для доработки под требования экспертизы. Нужен python-docx."),
    "export.fmt.docx.name":          "Отчёт_{name}.docx",
    "export.fmt.equipment.title":    "Сводная таблица оборудования",
    "export.fmt.equipment.desc":     "Сводка по помещениям + спецификации радиаторов/фанкойлов/диффузоров.",
    "export.fmt.equipment.name":     "Оборудование_{name}.xlsx",
    "export.fmt.revit.title":        "CSV для Revit (обратная запись)",
    "export.fmt.revit.desc":         ("Полный набор: нагрузки, вентиляция (приток/вытяжка/кратность), "
                                        "температуры, имена систем и контуров. Запустите "
                                        "revit_dynamo_apply_results.py в Dynamo — значения запишутся "
                                        "в параметры Space/Room."),
    "export.fmt.revit.name":         "results_for_revit.csv",
    "export.fmt.revit_live.title":   "Запись в Revit (живой мост)",
    "export.fmt.revit_live.desc":    ("Пишет нагрузки/расходы/системы прямо в параметры Spaces "
                                        "открытой модели Revit через плагин Revit MCP (порт 8080), "
                                        "без Dynamo. CSV сохраняется рядом как артефакт. В модели "
                                        "должны быть созданы Project Parameters (Heating Load и др.)."),
    "export.fmt.revit_live.name":    "results_for_revit.csv",
    "export.fmt.spec.title":         "Спецификация по ГОСТ 21.110",
    "export.fmt.spec.desc":          ("Полная спецификация оборудования и материалов: котлы, AHU, "
                                        "радиаторы, фанкойлы, VRF, насосы, баки, шумоглушители, медь, "
                                        "трубы тёплого пола. Группировка по разделам ГОСТ 21.110-2013."),
    "export.fmt.spec.name":          "Спецификация_{name}.xlsx",
    "export.fmt.passport.title":     "Паспорта вентсистем (DOCX)",
    "export.fmt.passport.desc":      ("Паспорт на каждую вентустановку: расчётные расходы, "
                                        "калорифер/охладитель, вентилятор и сеть, обслуживаемые "
                                        "помещения. Колонка «Факт» — для наладчика."),
    "export.fmt.passport.name":      "Паспорта_вентсистем_{name}.docx",
    "export.fmt.gas.title":          "PDF: расчёт газа (письмо для ТУ)",
    "export.fmt.gas.desc":           ("Письмо-расчёт потребности в газе от мощности газовых котлов "
                                        "проекта: часовой / суточный / месячный / годовой расход."),
    "export.fmt.gas.name":           "Расчёт_газа_{name}.pdf",
    "export.gas.params":             "Параметры расчёта газа",
    "export.gas.object":             "Объект",
    "export.gas.signatory":          "Должность подписанта",
    "export.gas.signatory_default":  "ГИП",
    "export.gas.signatory_name":     "Ф.И.О. подписанта",
    "export.gas.lhv":                "Qнр газа, ккал/м³",
    "export.gas.eff":                "КПД котла η",
    "export.gas.k":                  "Коэф. использования K",
    "export.gas.hours":              "Часов работы в сутки",
    "export.gas.days_month":         "Суток в месяце",
    "export.gas.heating_days":       "Отопительный период, сут",
    "export.fmt.hlgc.title":         "HLGC Design Table (мастер-таблица)",
    "export.fmt.hlgc.desc":          ("Заполняет проектную таблицу HLGC нагрузками по номерам "
                                        "помещений (лист «HLGC»). Движок Excel COM сохраняет формулы "
                                        "и стили; при отсутствии Excel — fallback на openpyxl."),
    "export.fmt.hlgc.name":          "HLGC Design Table_filled.xlsx",
    "export.hlgc.params":            "Параметры HLGC-экспорта",
    "export.hlgc.source":            "Исходная таблица (шаблон)",
    "export.hlgc.source_ph":         "Выберите .xlsx/.xls таблицу для заполнения…",
    "export.hlgc.source_dlg":        "Выберите HLGC Design Table",
    "export.hlgc.mode":              "Режим записи",
    "export.hlgc.mode.match":        "Обновить совпадающие по № (не добавлять строки)",
    "export.hlgc.mode.append":       "Обновить + добавить недостающие помещения",
    "export.hlgc.mode.rebuild":      "Перестроить всю таблицу из проекта",
    "export.hlgc.only_empty":        "Писать только в пустые ячейки",
    "export.hlgc.no_source.title":   "Нет шаблона",
    "export.hlgc.no_source.msg":     ("Укажите исходную HLGC Design Table (.xlsx/.xls), "
                                        "которую нужно заполнить."),
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
    "panel.calc.validate.open": "Открыть список →",
    "panel.calc.progress":      "{done} / {total} помещений",
    "panel.calc.cancel":        "Отменить",
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

    # ===== Panel: Balance (раздел «Тепловой баланс») =====
    "panel.airbalance.title":        "Баланс воздуха",
    "panel.airbalance.hint":         ("Баланс приточно-вытяжного воздуха по этажам "
                                       "(или системам). Правьте расходы в строках "
                                       "помещений; цветом отмечен дисбаланс. "
                                       "Баланс = приток − (вытяжка + зонт)."),
    "panel.airbalance.group.level":  "По этажам",
    "panel.airbalance.group.system": "По системам",
    "panel.airbalance.btn.expand":   "Развернуть",
    "panel.airbalance.btn.collapse": "Свернуть",
    "panel.airbalance.filter.system": "Система:",
    "panel.airbalance.filter.block": "Блок:",
    "panel.airbalance.col.node":     "Этаж / помещение",
    "panel.airbalance.col.supply":   "Приток",
    "panel.airbalance.col.exhaust":  "Вытяжка",
    "panel.airbalance.col.hood":     "Зонт",
    "panel.airbalance.col.extract":  "Удаление",
    "panel.airbalance.col.balance":  "Баланс",
    "panel.airbalance.col.pct":      "%",
    "panel.airbalance.summary":      ("Здание:  приток {sup}  ·  удаление {ext}  ·  "
                                       "баланс {bal} м³/ч  ({pct}%)"),
    "panel.airbalance.none":         "(без системы)",

    # ----- Раздел «Блоки» -----
    "panel.blocks.title":            "Блоки здания",
    "panel.blocks.hint":             ("Выделите помещения внизу → «Назначить "
                                      "блок». Автопомощники «1./2.» заполняют "
                                      "только пустое. Прочее — в правом клике "
                                      "по строке."),
    "panel.blocks.empty_summary":    "Блоков пока нет",
    "panel.blocks.empty_summary_hint":
        "Создайте блок кнопкой «+ Блок» или запустите автопомощник "
        "«1. Помещения по блокам».",
    "panel.blocks.btn.assign_rooms":   "1. Помещения по блокам",
    "panel.blocks.btn.assign_systems": "2. Системы по блокам",
    "panel.blocks.btn.reassign":     "Переопределить всё",
    "panel.blocks.btn.recalc_ahu":   "Пересчитать установки",
    "panel.blocks.col.name":         "Блок / установка",
    "panel.blocks.col.rooms":        "Помещ.",
    "panel.blocks.col.area":         "S, м²",
    "panel.blocks.col.qh_rooms":     "Q отопл. пом., кВт",
    "panel.blocks.col.qc_rooms":     "Q охл. пом., кВт",
    "panel.blocks.col.qh_ahu":       "Q калориф., кВт",
    "panel.blocks.col.qc_ahu":       "Q охлад., кВт",
    "panel.blocks.col.qh_total":     "Q отопл. ИТОГО, кВт",
    "panel.blocks.col.qc_total":     "Q охл. ИТОГО, кВт",
    "panel.blocks.col.supply":       "Приток, м³/ч",
    "panel.blocks.col.exhaust":      "Вытяжка, м³/ч",
    "panel.blocks.none":             "(без блока)",
    "panel.blocks.status.assigned":  "Блок определён: {n} помещ.",
    "panel.blocks.status.assigned_sys": "Блок назначен: {n} систем(ы)",
    "panel.blocks.status.rooms_set": "Блок «{b}»: назначено {n} помещ.",
    "panel.blocks.menu.set_block":   "Блок установки {name}:",
    "panel.blocks.menu.auto":        "(авто)",
    "panel.blocks.menu.new_block":   "➕ Новый блок…",
    "panel.blocks.menu.clear_block": "✖ Снять блок",
    "panel.blocks.menu.block_actions": "Блок «{name}»",
    "panel.blocks.menu.rename_block":  "✏ Переименовать блок…",
    "panel.blocks.menu.delete_block":  "✖ Удалить блок…",
    "panel.blocks.dlg.block_name":   "Имя блока:",
    "panel.blocks.btn.set_block":    "Назначить блок",
    "panel.blocks.btn.new_block":    "➕ Блок",
    "panel.blocks.confirm.delete_block": ("Удалить блок «{name}»? Помещений: "
                                          "{rooms}, систем: {sys} — останутся "
                                          "без блока."),
    "panel.blocks.status.block_created":  "Блок «{name}» создан",
    "panel.blocks.status.block_exists":   "Блок «{name}» уже есть",
    "panel.blocks.status.block_renamed":  ("Блок «{old}» → «{new}»: помещений "
                                           "{rooms}, систем {sys}"),
    "panel.blocks.status.block_deleted":  ("Блок «{name}» удалён: снято с "
                                           "{rooms} помещ. и {sys} систем"),
    "panel.blocks.rooms.col.number": "№",
    "panel.blocks.rooms.col.name":   "Имя",
    "panel.blocks.rooms.col.level":  "Уровень",
    "panel.blocks.rooms.col.type":   "Тип",
    "panel.blocks.rooms.col.block":  "Блок",
    "panel.blocks.rooms.col.area":   "S, м²",
    "panel.blocks.rooms.col.supply": "Приток",
    "panel.blocks.rooms.col.exhaust":"Вытяжка",
    "panel.blocks.rooms.count":      "видно {visible} из {total}",
    "panel.blocks.confirm.reassign": ("Переопределить блоки у ВСЕХ помещений? "
                                      "Ручные назначения будут перезаписаны."),
    "panel.blocks.summary.line":     ("Блоков: {blocks}  ·  помещений {rooms} "
                                      "(без блока {no_block})  ·  Q отопл. {qh} кВт  ·  "
                                      "Q охл. {qc} кВт  ·  ГВС {dhw} кВт  ·  "
                                      "приток {sup} / вытяжка {exh} м³/ч"),
    "panel.blocks.ahu.serves":       "  → обслуживает: {list} м³/ч",
    "panel.blocks.filter.block":     "Блок:",
    "panel.blocks.col.dhw":          "ГВС, кВт",
    "panel.blocks.menu.dhw":         "🚿 Нагрузка ГВС…",
    "panel.blocks.dlg.dhw_title":    "ГВС блока «{block}»",
    "panel.blocks.dlg.dhw_hint":     ("Расход ГВС считается в ВК-программе — "
                                      "сюда вводится готовая нагрузка на "
                                      "котельную блока."),
    "panel.blocks.dlg.dhw_kw":       "Нагрузка ГВС, кВт (0 — убрать):",
    "panel.blocks.dlg.dhw_v":        "Расход, м³/сут (справочно):",
    "panel.blocks.dhw.sys_name":     "ГВС-{block}",
    "panel.blocks.dhw.manual_note":  "ручной ввод (расчёт ГВС в ВК-программе)",
    "panel.blocks.status.dhw_set":     "ГВС «{block}»: {kw} кВт",
    "panel.blocks.status.dhw_removed": "ГВС «{block}» убрано",
    "panel.blocks.src.pick_fmt":     "{name} · {n} × {kw} кВт — {model}",
    "panel.blocks.dhw.fmt":          "{name} · {v} м³/сут",
    "panel.blocks.menu.pick_boilers":  "🔥 Подобрать котлы из каталога…",
    "panel.blocks.menu.pick_chillers": "❄ Подобрать чиллеры из каталога…",
    "panel.blocks.src.boiler_name":  "Котлы {block}",
    "panel.blocks.src.chiller_name": "Чиллеры {block}",
    "panel.blocks.status.source_set": "{sys}: {n} × {kw} кВт — {model}",

    # ---- диалог подбора котлов/чиллеров из каталога ----
    "panel.srcpick.title.heating":   "Каталог котлов — подбор",
    "panel.srcpick.title.cooling":   "Каталог чиллеров — подбор",
    "panel.srcpick.f.required":      "Требуемая мощность, кВт:",
    "panel.srcpick.f.reserve":       "+1 резервный агрегат (N+1)",
    "panel.srcpick.search.ph":       "Поиск: модель, производитель, тип…",
    "panel.srcpick.col.model":       "Модель",
    "panel.srcpick.col.manufacturer":"Производитель",
    "panel.srcpick.col.family":      "Тип",
    "panel.srcpick.col.q":           "кВт/агрегат",
    "panel.srcpick.col.eff":         "КПД",
    "panel.srcpick.col.eer":         "EER",
    "panel.srcpick.col.units":       "N раб.",
    "panel.srcpick.col.total":       "Σ кВт",
    "panel.srcpick.col.margin":      "Запас, %",
    "panel.srcpick.col.note":        "Примечание",
    "panel.srcpick.hint": ("Типовые каталожные данные — для предподбора; "
                           "финальный типоразмер уточняйте по программе "
                           "подбора производителя. Свои модели: "
                           "~/.hvac_calc/catalogs/*.json "
                           "(type: \"boilers\" / \"chillers\")."),
    "panel.srcpick.ctx.block":  ("Блок «{block}»: нагрузка {q} кВт × "
                                 "запас {m}"),
    "panel.srcpick.ctx.block_dhw": ("Блок «{block}»: отопление+вент. {q} кВт "
                                    "+ ГВС {dhw} кВт, запас ×{m}"),
    "panel.srcpick.ctx.system": ("Источник «{name}»: требуется {q} кВт "
                                 "(нагрузка × запас)"),
    "panel.detail.btn.catalog":      "Подобрать из каталога…",

    "panel.balance.title":   "Тепловой баланс",
    "panel.balance.hint":    ("Отметьте, какие помещения отапливаются и "
                               "охлаждаются — итог суммирует нагрузки помещений "
                               "и приточных установок. «О»/«Х» — помещение на "
                               "воздушном отоплении/охлаждении: его нагрузку "
                               "несёт калорифер/охладитель AHU, поэтому галочку "
                               "обычно снимают, чтобы не задвоить. «Авто» "
                               "расставляет галочки по нагрузке."),
    "panel.balance.btn.auto":     "Авто (по нагрузке)",
    "panel.balance.btn.compute":  "Посчитать AHU",
    "panel.balance.btn.heat_on":  "Отапл. ✓",
    "panel.balance.btn.heat_off": "Отапл. ✗",
    "panel.balance.btn.cool_on":  "Охл. ✓",
    "panel.balance.btn.cool_off": "Охл. ✗",
    "panel.balance.col.qh":       "Qотоп, кВт",
    "panel.balance.col.heated":   "Отапл.",
    "panel.balance.col.qc":       "Qохл, кВт",
    "panel.balance.col.cooled":   "Охл.",
    "panel.balance.ahu.title":    "Приточные установки",
    "panel.balance.ahu.name":     "Установка",
    "panel.balance.ahu.spaces":   "Помещ.",
    "panel.balance.ahu.flow":     "Расход, м³/ч",
    "panel.balance.ahu.heater":   "Калорифер, кВт",
    "panel.balance.ahu.cooler":   "Охладитель, кВт",
    "panel.balance.totals.title":   "Итог",
    "panel.balance.totals.heating": "Отопление",
    "panel.balance.totals.cooling": "Охлаждение",
    "panel.balance.totals.rooms":   "Помещения: {q} кВт  ({n} помещ.)",
    "panel.balance.totals.ahu":     "Приточные установки: {q} кВт  ({n} шт.)",
    "panel.balance.totals.total":   "Итого: {q} кВт",
    "panel.balance.status.auto":    "Классифицировано по нагрузке: {n} помещ.",
    "panel.balance.status.bulk":    "Изменено помещений: {n}",
    "panel.balance.status.computed":"Нагрузки приточных установок пересчитаны",
    "panel.balance.status.no_selection": "Выделите помещения в таблице",
}
