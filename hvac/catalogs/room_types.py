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


def _load_room_type_presets() -> Dict[str, Dict]:
    """Читает пресеты типов помещений из
    hvac/catalogs/data/room_types.json (см. примечание в docstring модуля)."""
    import json
    from importlib.resources import files
    raw = (files("hvac.catalogs") / "data" / "room_types.json").read_text("utf-8")
    return json.loads(raw)


ROOM_TYPE_PRESETS: Dict[str, Dict] = _load_room_type_presets()


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
