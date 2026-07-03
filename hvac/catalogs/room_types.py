# -*- coding: utf-8 -*-
"""Справочник типов помещений (ШНҚ 2.08.02-23 / 2.04.05-22 / 2.08.01-24).

Каждый тип содержит ключевые слова для авто-определения по названию
помещения и набор расчётных параметров: температуры, занятость,
освещение, оборудование, кратность инфильтрации.

Структура справочника — словарь, чтобы при необходимости легко
выгрузить/загрузить в JSON для редактирования без правки кода.
"""

from __future__ import annotations
from typing import Dict
from hvac.models import Space


def _load_room_type_presets() -> Dict[str, Dict]:
    """Читает пресеты типов помещений из
    hvac/catalogs/data/room_types.json (см. примечание в docstring модуля)."""
    import json
    from importlib.resources import files
    raw = (files("hvac.catalogs") / "data" / "room_types.json").read_text("utf-8")
    return json.loads(raw)


ROOM_TYPE_PRESETS: Dict[str, Dict] = _load_room_type_presets()


# Типы помещений БЕЗ постоянного пребывания людей → занятость 0 для расчёта
# теплопоступлений от людей. Машинные/складские/шахты + транзитные + санитарные:
# люди в них не находятся постоянно, поэтому людской теплоприток не учитывается
# (иначе крупный гараж/техпомещение при плотности 100 м²/чел копит десятки
# фантомных людей). Выбор пользователя (CHORSU): транзит + санитарные + техзоны.
NO_OCCUPANCY_TYPES = {
    "Лестница", "Лифт / шахта", "Склад", "Технич. помещение",
    "Гараж / автостоянка", "Серверная", "Архив / хранилище",
    "Холодильная камера", "Балкон / терраса", "Мусорокамера", "Уборочная",
    "Коридор", "Вестибюль", "Пожаробезопасная зона",
    "Санузел", "Душевая", "Гардероб", "Раздевалка",
}


# Типы с ФИКСИРОВАННЫМ числом людей — по факту заселения, а не по площади.
# Гостиничный номер и жилая комната (спальня/гостиная) — 2 чел (двухместное).
FIXED_OCCUPANCY = {
    "Гостиничный номер": 2,
    "Жилая комната": 2,
}


def compute_occupancy_people(room_type: str, area_m2: float) -> int:
    """Число людей для помещения — ЦЕЛОЕ.

    Помещения без постоянного пребывания людей (NO_OCCUPANCY_TYPES) → 0.
    Типы с фиксированной занятостью (FIXED_OCCUPANCY: номер, жилая) → их значение.
    Остальные: площадь / плотность (м²/чел), округлённая до ближайшего целого.
    """
    if room_type in NO_OCCUPANCY_TYPES:
        return 0
    if room_type in FIXED_OCCUPANCY:
        return FIXED_OCCUPANCY[room_type]
    from hvac.catalogs.user_norms import get_thermal_preset
    dens = get_thermal_preset(room_type).get(
        "occupancy_density_m2_per_person", 0) or 0
    if dens <= 0:
        return 0
    return int(round((area_m2 or 0.0) / dens))


# Порог температуры отопления, при котором тип помещения считается
# НЕОТАПЛИВАЕМЫМ (только защита от промерзания — постоянных отопительных
# приборов нет). Отделяет лифтовые шахты, паркинг, балконы/террасы,
# венткамеры/техпомещения и холодильные камеры (t_in_heat ≤ 5 °C) от
# отапливаемых складов (12 °C) и лестниц (16 °C).
NON_HEATED_MAX_T_HEAT = 5.0


def is_non_heated_type(room_type: str) -> bool:
    """True, если тип помещения по своей природе не отапливается.

    Критерий — расчётная температура отопления пресета:
    t_in_heat ≤ NON_HEATED_MAX_T_HEAT (5 °C, только защита от промерзания).
    Сюда попадают «Лифт / шахта», «Гараж / автостоянка», «Балкон / терраса»,
    «Технич. помещение», «Холодильная камера». Неизвестные и пользовательские
    типы без заданной t считаются отапливаемыми (фолбэк «Прочее» = 18 °C).

    Используется разделом «Тепловой баланс» (кнопка «Авто (по нагрузке)»),
    чтобы автоматически снимать галочку «Отапл.» с таких помещений — даже
    если у них посчитаны теплопотери через наружные стены.
    """
    from hvac.catalogs.user_norms import get_thermal_preset
    t_heat = get_thermal_preset(room_type).get("t_in_heat", 18)
    try:
        return float(t_heat) <= NON_HEATED_MAX_T_HEAT
    except (TypeError, ValueError):
        return False


# Порог температуры охлаждения, при котором тип помещения считается
# НЕОХЛАЖДАЕМЫМ (комфортного охлаждения нет, температуре дают «плыть»).
# t_in_cool ≥ 30 °C отделяет чисто неохлаждаемые лифтовые шахты, паркинг,
# балконы/террасы и венткамеры/техпомещения от комфортных 22–26 °C и лёгкого
# охлаждения лестниц/складов (28). Холодильная камера (4 °C) охлаждается
# активно и сюда НЕ попадает.
NON_COOLED_MIN_T_COOL = 30.0


def is_non_cooled_type(room_type: str) -> bool:
    """True, если тип помещения по своей природе не охлаждается.

    Критерий — расчётная температура охлаждения пресета:
    t_in_cool ≥ NON_COOLED_MIN_T_COOL (30 °C). Сюда попадают «Лифт / шахта»,
    «Гараж / автостоянка», «Балкон / терраса», «Технич. помещение».
    «Холодильная камера» (активно охлаждается до 4 °C) неохлаждаемой НЕ
    считается. Неизвестные и пользовательские типы без заданной t считаются
    охлаждаемыми (фолбэк «Прочее» = 26 °C).

    Используется разделом «Тепловой баланс» (кнопка «Авто (по нагрузке)»)
    симметрично is_non_heated_type — снимает галочку «Охл.» с таких помещений.
    """
    from hvac.catalogs.user_norms import get_thermal_preset
    t_cool = get_thermal_preset(room_type).get("t_in_cool", 26)
    try:
        return float(t_cool) >= NON_COOLED_MIN_T_COOL
    except (TypeError, ValueError):
        return False


def auto_detect_room_type(name: str) -> str:
    """Определяет тип помещения по ключевым словам в названии."""
    n = (name or "").lower()
    best = ("Прочее", 0)
    for rtype, info in ROOM_TYPE_PRESETS.items():
        for kw in info["keywords"]:
            if kw and kw.lower() in n:
                if len(kw) > best[1]:
                    best = (rtype, len(kw))
    return best[0]


def apply_room_type_defaults(space: Space) -> None:
    """Заполняет в Space параметры из пресета типа помещения.

    Поддерживает пользовательские (custom) типы из user_norms.json —
    если space.room_type не встроенный, тепловые параметры берутся из
    custom_types[...].thermal (с фолбэком на 'Прочее' для незаполненных полей).
    """
    # Локальный импорт во избежание циклической зависимости при загрузке
    # модулей (user_norms тоже импортирует room_types).
    from hvac.catalogs.user_norms import get_thermal_preset
    preset = get_thermal_preset(space.room_type)
    space.t_in_heat = preset["t_in_heat"]
    space.t_in_cool = preset["t_in_cool"]
    space.ach_inf = preset["ach_inf"]
    space.lighting_w_m2 = preset["lighting_w_m2"]
    space.equipment_w_m2 = preset["equipment_w_m2"]
    space.occupancy_people = compute_occupancy_people(
        space.room_type, space.area_m2)


def get_all_room_types() -> list:
    """Все известные типы (built-in СП + пользовательские).
    Используйте этот хелпер вместо list(ROOM_TYPE_PRESETS.keys()) в UI
    чтобы кастомные типы были видны в выпадающих списках."""
    from hvac.catalogs.user_norms import get_all_room_types as _all
    return _all()
