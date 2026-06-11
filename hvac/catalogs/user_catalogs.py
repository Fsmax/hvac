# -*- coding: utf-8 -*-
"""Пользовательские каталоги оборудования (радиаторы, фанкойлы).

Встроенные каталоги лежат в ``hvac/catalogs/data/radiators.json`` и
``fancoils.json``. Дополнить их своими моделями можно без правки кода:
положите JSON-файл в ``~/.hvac_calc/catalogs/`` (имя любое, расширение
``.json``). Каждый файл объявляет тип каталога:

    {
      "type": "radiators",            // или "fancoils"
      "models": [ { ...поля модели... }, ... ],
      "panel_families": [ ... ]       // только radiators, опционально —
                                      // генератор панельных семейств
    }

Поля моделей совпадают с полями dataclass-моделей
(``RadiatorModel`` / ``FancoilModel``); неизвестные ключи игнорируются,
так что в файле можно держать собственные пометки. Битые файлы
пропускаются с предупреждением в лог — программа продолжает работу
на встроенном каталоге.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Iterator, Optional, Union

log = logging.getLogger(__name__)

#: Папка пользовательских каталогов (создаётся пользователем вручную).
USER_CATALOG_DIR = Path.home() / ".hvac_calc" / "catalogs"


def iter_user_catalogs(kind: str,
                       user_dir: Optional[Union[str, Path]] = None,
                       ) -> Iterator[dict]:
    """Перебирает пользовательские JSON-каталоги заданного типа.

    kind     : "radiators" | "fancoils" — отдаются только файлы,
               у которых совпало поле "type".
    user_dir : переопределение папки (для тестов); по умолчанию
               USER_CATALOG_DIR.

    Файлы с ошибками парсинга или чтения пропускаются с warning-ом.
    """
    d = Path(user_dir) if user_dir is not None else USER_CATALOG_DIR
    if not d.is_dir():
        return
    for p in sorted(d.glob("*.json")):
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            log.warning("Пользовательский каталог %s пропущен: %s", p, exc)
            continue
        if not isinstance(data, dict) or data.get("type") != kind:
            continue
        yield data
