# -*- coding: utf-8 -*-
"""Хранилище пользовательских настроек: recent files, тема, путь к auto-save.

Простой JSON в ~/.hvac_calc/settings.json. Использовать QSettings излишне —
у нас одна машина, файл проще для отладки.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any


_DIR = Path.home() / ".hvac_calc"
_FILE = _DIR / "settings.json"

DEFAULTS: dict[str, Any] = {
    "recent": [],            # list[str] — пути к проектам
    "theme": "dark",         # "dark" | "light"
    "autosave_enabled": True,
    "autosave_interval_min": 5,
    "language": "ru",        # "ru" | "uz"
    # Состояние окна между запусками: geometry (base64 от saveGeometry)
    # и splitters {ключ: base64 от saveState}.
    "window": {},
}


def _ensure_dir() -> None:
    _DIR.mkdir(parents=True, exist_ok=True)
    autosave_dir().mkdir(parents=True, exist_ok=True)


def autosave_dir() -> Path:
    return _DIR / "autosave"


def load() -> dict[str, Any]:
    if not _FILE.exists():
        return dict(DEFAULTS)
    try:
        data = json.loads(_FILE.read_text(encoding="utf-8"))
    except Exception:
        return dict(DEFAULTS)
    result = dict(DEFAULTS)
    result.update(data)
    return result


def save(data: dict[str, Any]) -> None:
    _ensure_dir()
    _FILE.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def push_recent(path: str, limit: int = 10) -> list[str]:
    data = load()
    recent = [p for p in data.get("recent", []) if p != path]
    recent.insert(0, path)
    recent = recent[:limit]
    data["recent"] = recent
    save(data)
    return recent
