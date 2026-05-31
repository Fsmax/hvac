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
from hvac.i18n.ru import RU
from hvac.i18n.uz import UZ

TRANSLATIONS: Dict[str, Dict[str, str]] = {
    "ru": RU,
    "uz": UZ,
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
