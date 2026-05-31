# -*- coding: utf-8 -*-
"""Справочник типов помещений (СП 60.13330).

Каждый тип содержит ключевые слова для авто-определения по названию
помещения и набор расчётных параметров: температуры, занятость,
освещение, оборудование, кратность инфильтрации.

Структура справочника — словарь, чтобы при необходимости легко
выгрузить/загрузить в JSON для редактирования без правки кода.
"""

from __future__ import annotations
from typing import Dict
from hvac.models import Space


ROOM_TYPE_PRESETS: Dict[str, Dict] = {
    "Офис": {
        "keywords": ["office", "офис", "кабинет"],
        "t_in_heat": 20, "t_in_cool": 24, "ach_inf": 0.5,
        "occupancy_density_m2_per_person": 10.0,
        "lighting_w_m2": 12, "equipment_w_m2": 15,
    },
    "Жилая комната": {
        "keywords": ["bedroom", "living", "спальня", "гостиная", "жилая"],
        "t_in_heat": 20, "t_in_cool": 24, "ach_inf": 0.5,
        "occupancy_density_m2_per_person": 20.0,
        "lighting_w_m2": 10, "equipment_w_m2": 8,
    },
    "Коридор": {
        "keywords": ["corridor", "hall ", "hall,", "коридор", "холл"],
        "t_in_heat": 18, "t_in_cool": 26, "ach_inf": 0.3,
        "occupancy_density_m2_per_person": 50.0,
        "lighting_w_m2": 8, "equipment_w_m2": 0,
    },
    "Вестибюль": {
        "keywords": ["vestibule", "lobby", "вестибюль", "тамбур"],
        "t_in_heat": 16, "t_in_cool": 26, "ach_inf": 1.5,
        "occupancy_density_m2_per_person": 30.0,
        "lighting_w_m2": 10, "equipment_w_m2": 0,
    },
    "Лестница": {
        "keywords": ["stair", "лестниц"],
        "t_in_heat": 16, "t_in_cool": 28, "ach_inf": 0.3,
        "occupancy_density_m2_per_person": 100.0,
        "lighting_w_m2": 6, "equipment_w_m2": 0,
    },
    "Лифт / шахта": {
        "keywords": ["elevator", "lift", "лифт"],
        "t_in_heat": 5, "t_in_cool": 30, "ach_inf": 0.0,
        "occupancy_density_m2_per_person": 100.0,
        "lighting_w_m2": 5, "equipment_w_m2": 0,
    },
    "Склад": {
        "keywords": ["storage", "warehouse", "склад", "кладовая"],
        "t_in_heat": 12, "t_in_cool": 28, "ach_inf": 0.2,
        "occupancy_density_m2_per_person": 100.0,
        "lighting_w_m2": 6, "equipment_w_m2": 2,
    },
    "Технич. помещение": {
        "keywords": ["mechanical", "electrical", "transformer",
                     "weak current", "machine", "техническ",
                     "электрощит", "венткамер", "ИТП", "насос"],
        "t_in_heat": 5, "t_in_cool": 35, "ach_inf": 0.2,
        "occupancy_density_m2_per_person": 100.0,
        "lighting_w_m2": 5, "equipment_w_m2": 30,
    },
    "Гараж / автостоянка": {
        "keywords": ["carpark", "parking", "garage",
                     "парковка", "стоянка", "гараж"],
        "t_in_heat": 5, "t_in_cool": 30, "ach_inf": 0.3,
        "occupancy_density_m2_per_person": 100.0,
        "lighting_w_m2": 4, "equipment_w_m2": 0,
    },
    "Санузел": {
        "keywords": ["toilet", "wc", "bathroom",
                     "санузел", "туалет", "ванная"],
        "t_in_heat": 24, "t_in_cool": 26, "ach_inf": 1.0,
        "occupancy_density_m2_per_person": 5.0,
        "lighting_w_m2": 8, "equipment_w_m2": 2,
    },
    "Конференц-зал": {
        "keywords": ["conference", "meeting", "конференц", "переговор"],
        "t_in_heat": 20, "t_in_cool": 24, "ach_inf": 0.5,
        "occupancy_density_m2_per_person": 3.0,
        "lighting_w_m2": 12, "equipment_w_m2": 10,
    },
    "Ресторан / кухня": {
        "keywords": ["kitchen", "restaurant", "dining", "кухня", "ресторан"],
        "t_in_heat": 20, "t_in_cool": 22, "ach_inf": 1.0,
        "occupancy_density_m2_per_person": 1.5,
        "lighting_w_m2": 15, "equipment_w_m2": 200,
    },
    "Гостиничный номер": {
        "keywords": ["hotel room", "guest room", "номер"],
        "t_in_heat": 20, "t_in_cool": 24, "ach_inf": 0.5,
        "occupancy_density_m2_per_person": 15.0,
        "lighting_w_m2": 10, "equipment_w_m2": 8,
    },
    "Магазин / торговля": {
        "keywords": ["shop", "retail", "store", "магазин"],
        "t_in_heat": 16, "t_in_cool": 24, "ach_inf": 0.8,
        "occupancy_density_m2_per_person": 5.0,
        "lighting_w_m2": 20, "equipment_w_m2": 15,
    },
    "Серверная": {
        "keywords": ["server", "data center", "серверн"],
        "t_in_heat": 18, "t_in_cool": 22, "ach_inf": 0.5,
        "occupancy_density_m2_per_person": 100.0,
        "lighting_w_m2": 5, "equipment_w_m2": 500,
    },
    "Прочее": {
        "keywords": [],
        "t_in_heat": 18, "t_in_cool": 26, "ach_inf": 0.5,
        "occupancy_density_m2_per_person": 20.0,
        "lighting_w_m2": 8, "equipment_w_m2": 5,
    },
}


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
    dens = preset["occupancy_density_m2_per_person"]
    space.occupancy_people = round(space.area_m2 / dens, 2) if dens > 0 else 0


def get_all_room_types() -> list:
    """Все известные типы (built-in СП + пользовательские).
    Используйте этот хелпер вместо list(ROOM_TYPE_PRESETS.keys()) в UI
    чтобы кастомные типы были видны в выпадающих списках."""
    from hvac.catalogs.user_norms import get_all_room_types as _all
    return _all()
