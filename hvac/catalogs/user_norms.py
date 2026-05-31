# -*- coding: utf-8 -*-
"""Глобальное пользовательское переопределение норм вентиляции
и пользовательские (custom) типы помещений.

Хранится в `<user_dir>/HVAC/user_norms.json`:
  • Windows: %APPDATA%/HVAC/user_norms.json
  • Linux/Mac: ~/.config/HVAC/user_norms.json (или ~/.hvac/user_norms.json)

Применяется ко ВСЕМ проектам — в отличие от пер-проектных правок Supply/
Exhaust на конкретные помещения. Если пользователь поменял норму
«Офис: 40 → 60 м³/ч·чел», это значение сразу подхватится в любом
открытом проекте при пересчёте вентиляции.

Структура файла:
{
  "version": 1,
  "ventilation_overrides": {
    "Офис": {"m3_per_person": 60, "min_ach": 1.2}
  },
  "custom_types": {
    "СПА-зона": {
      "thermal":     {"t_in_heat": 26, ...},
      "ventilation": {"m3_per_person": 50, ...}
    }
  }
}

API:
  • get_ventilation_norms(room_type)  — эффективные нормы для типа
  • get_all_room_types()              — список всех типов (built-in + custom)
  • get_thermal_preset(room_type)     — тепловые дефолты для типа
  • save_overrides(...)               — записать на диск
  • reset_ventilation_override(type)  — убрать пер-типовой override
  • delete_custom_type(name)          — удалить custom-тип
"""

from __future__ import annotations
import copy
import json
import logging
import os
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

# Версия формата файла. Если меняется структура — увеличиваем и пишем
# миграцию в _load_raw().
FILE_VERSION = 1


def _user_norms_path() -> str:
    """Путь к глобальному файлу пользовательских норм."""
    if os.name == "nt":
        base = os.environ.get("APPDATA") or os.path.expanduser("~")
        return os.path.join(base, "HVAC", "user_norms.json")
    # Linux / Mac
    xdg = os.environ.get("XDG_CONFIG_HOME")
    if xdg:
        return os.path.join(xdg, "HVAC", "user_norms.json")
    return os.path.join(os.path.expanduser("~"), ".hvac", "user_norms.json")


# Кэш: загружается один раз и используется до явного reload
_cache: Optional[Dict] = None


def _empty_data() -> Dict:
    return {
        "version": FILE_VERSION,
        "ventilation_overrides": {},
        "custom_types": {},
    }


def _load_raw() -> Dict:
    """Читает файл с диска. Возвращает _empty_data() если файла нет."""
    path = _user_norms_path()
    if not os.path.exists(path):
        return _empty_data()
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        logger.warning("Не удалось прочитать %s: %s. Использую дефолты.",
                       path, e)
        return _empty_data()
    # Минимальная валидация структуры
    if not isinstance(data, dict):
        return _empty_data()
    data.setdefault("version", FILE_VERSION)
    data.setdefault("ventilation_overrides", {})
    data.setdefault("custom_types", {})
    if not isinstance(data["ventilation_overrides"], dict):
        data["ventilation_overrides"] = {}
    if not isinstance(data["custom_types"], dict):
        data["custom_types"] = {}
    return data


def _get_data() -> Dict:
    """Возвращает кэш или подгружает с диска."""
    global _cache
    if _cache is None:
        _cache = _load_raw()
    return _cache


def reload_from_disk() -> None:
    """Принудительно перечитать файл (например после внешнего изменения)."""
    global _cache
    _cache = None


def save_to_disk() -> str:
    """Записать текущий кэш на диск. Возвращает путь к файлу."""
    path = _user_norms_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    data = _get_data()
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    return path


# ---------- Публичный API ----------


def get_ventilation_norms(room_type: str) -> Dict:
    """Эффективные нормы вентиляции для типа помещения.

    Слияние (по приоритету):
      1) custom_types[room_type].ventilation         (если это custom-тип)
      2) ventilation_overrides[room_type]            (override для built-in)
      3) VENTILATION_NORMS[room_type]                (встроенный СП)
      4) VENTILATION_NORMS["Прочее"]                 (фолбэк)
    """
    # Импорт внутри функции — чтобы избежать циклической зависимости при
    # инициализации модуля (ventilation_norms.py может импортироваться раньше).
    from hvac.catalogs.ventilation_norms import VENTILATION_NORMS

    data = _get_data()

    # Custom type? Тогда вся норма из custom + СП-дефолт «Прочее» как база.
    custom = data["custom_types"].get(room_type)
    if custom is not None:
        base = dict(VENTILATION_NORMS["Прочее"])
        vent = custom.get("ventilation", {}) or {}
        base.update(vent)
        return base

    # Built-in type, возможно с override
    base = dict(VENTILATION_NORMS.get(room_type, VENTILATION_NORMS["Прочее"]))
    override = data["ventilation_overrides"].get(room_type)
    if override:
        base.update(override)
    return base


def get_thermal_preset(room_type: str) -> Dict:
    """Тепловые параметры (t_in_heat, ach_inf, ...) для типа помещения.

    Для custom-типов берётся `thermal` из их definition (или копия «Прочее»
    если у custom-типа нет thermal). Для built-in — обычный ROOM_TYPE_PRESETS.
    """
    from hvac.catalogs.room_types import ROOM_TYPE_PRESETS

    data = _get_data()

    custom = data["custom_types"].get(room_type)
    if custom is not None:
        base = copy.deepcopy(ROOM_TYPE_PRESETS["Прочее"])
        therm = custom.get("thermal", {}) or {}
        base.update(therm)
        return base

    return ROOM_TYPE_PRESETS.get(room_type, ROOM_TYPE_PRESETS["Прочее"])


def get_all_room_types() -> List[str]:
    """Все известные типы помещений — built-in СП + пользовательские."""
    from hvac.catalogs.room_types import ROOM_TYPE_PRESETS

    builtin = list(ROOM_TYPE_PRESETS.keys())
    data = _get_data()
    custom = list(data["custom_types"].keys())
    # Кастомные после встроенных, без дубликатов
    return builtin + [t for t in custom if t not in builtin]


def get_builtin_room_types() -> List[str]:
    """Только встроенные (для редактора, чтобы пометить их особо)."""
    from hvac.catalogs.room_types import ROOM_TYPE_PRESETS
    return list(ROOM_TYPE_PRESETS.keys())


def get_custom_room_types() -> List[str]:
    """Только пользовательские типы."""
    return list(_get_data()["custom_types"].keys())


def is_custom_type(room_type: str) -> bool:
    return room_type in _get_data()["custom_types"]


def has_ventilation_override(room_type: str) -> bool:
    return room_type in _get_data()["ventilation_overrides"]


def get_raw_override(room_type: str) -> Dict:
    """Возвращает копию override (для UI — что именно поменял пользователь).
    Для custom-типа возвращает ventilation из definition."""
    data = _get_data()
    if room_type in data["custom_types"]:
        return dict(data["custom_types"][room_type].get("ventilation", {}))
    return dict(data["ventilation_overrides"].get(room_type, {}))


# ---------- Изменение ----------


def set_ventilation_override(room_type: str, new_norms: Dict,
                              autosave: bool = True) -> None:
    """Установить override норм вентиляции для built-in типа.

    new_norms — полный словарь полей (только переданные значения; остальные
    останутся как в built-in справочнике).
    """
    from hvac.catalogs.ventilation_norms import VENTILATION_NORMS

    data = _get_data()
    if room_type in data["custom_types"]:
        # Это custom-тип — апдейтим его ventilation секцию
        data["custom_types"][room_type].setdefault("ventilation", {})
        data["custom_types"][room_type]["ventilation"] = dict(new_norms)
    else:
        if room_type not in VENTILATION_NORMS:
            raise ValueError(
                f"Тип '{room_type}' не существует. "
                f"Используйте add_custom_type() для нового типа.")
        # Сохраняем только те поля, которые отличаются от built-in
        # (это позволяет видеть в файле что реально изменил пользователь).
        builtin = VENTILATION_NORMS[room_type]
        diff = {k: v for k, v in new_norms.items()
                if builtin.get(k) != v}
        if diff:
            data["ventilation_overrides"][room_type] = diff
        else:
            data["ventilation_overrides"].pop(room_type, None)
    if autosave:
        save_to_disk()


def reset_ventilation_override(room_type: str,
                                autosave: bool = True) -> bool:
    """Убрать override для built-in типа (вернуться к значениям СП).
    Для custom-типов — операция не имеет смысла, вернёт False."""
    data = _get_data()
    if room_type in data["custom_types"]:
        return False
    if room_type not in data["ventilation_overrides"]:
        return False
    del data["ventilation_overrides"][room_type]
    if autosave:
        save_to_disk()
    return True


def add_custom_type(name: str,
                     ventilation: Optional[Dict] = None,
                     thermal: Optional[Dict] = None,
                     autosave: bool = True) -> None:
    """Создать новый пользовательский тип помещения.

    name        — отображаемое имя (например «СПА-зона»)
    ventilation — словарь норм (m3_per_person, m3_per_m2, ...)
    thermal     — словарь тепловых дефолтов (t_in_heat, ach_inf, ...)
    """
    from hvac.catalogs.ventilation_norms import VENTILATION_NORMS
    name = (name or "").strip()
    if not name:
        raise ValueError("Имя типа не может быть пустым")
    data = _get_data()
    if name in VENTILATION_NORMS:
        raise ValueError(
            f"Тип '{name}' уже существует как встроенный (СП). "
            f"Используйте set_ventilation_override() для его изменения.")
    if name in data["custom_types"]:
        raise ValueError(f"Тип '{name}' уже определён как пользовательский.")
    data["custom_types"][name] = {
        "ventilation": dict(ventilation or {}),
        "thermal": dict(thermal or {}),
    }
    if autosave:
        save_to_disk()


def delete_custom_type(name: str, autosave: bool = True) -> bool:
    """Удалить пользовательский тип. Встроенные удалить нельзя."""
    data = _get_data()
    if name not in data["custom_types"]:
        return False
    del data["custom_types"][name]
    if autosave:
        save_to_disk()
    return True


def rename_custom_type(old_name: str, new_name: str,
                        autosave: bool = True) -> bool:
    """Переименовать пользовательский тип."""
    new_name = (new_name or "").strip()
    if not new_name:
        raise ValueError("Новое имя пусто")
    data = _get_data()
    if old_name not in data["custom_types"]:
        return False
    from hvac.catalogs.ventilation_norms import VENTILATION_NORMS
    if new_name in VENTILATION_NORMS or new_name in data["custom_types"]:
        raise ValueError(f"Тип '{new_name}' уже существует")
    data["custom_types"][new_name] = data["custom_types"].pop(old_name)
    if autosave:
        save_to_disk()
    return True
