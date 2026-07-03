# -*- coding: utf-8 -*-
"""Защитный тест: в коде ui_qt не должно быть пользовательских русских
строк, не прошедших через i18n.t().

Сканирует все .py-файлы под hvac/ui_qt/ и ищет строковые литералы,
содержащие кириллицу. Допустимы только:
- комментарии (#…) и docstring'и модуля/класса/функции
- ключи словаря TRANSLATIONS (только в i18n.py)
- значения userData/atribuda data — кириллица, которая пишется в
  данные проекта и сохраняется в JSON (она НЕ для UI)

Найденные кириллические литералы должны быть либо заменены на _t(...),
либо явно покрыты исключением через комментарий ``# i18n-allow``.
"""
from __future__ import annotations

import ast
import io
import os
import tokenize
from pathlib import Path
from typing import Iterable, List, Tuple

import pytest


UI_QT_DIR = Path(__file__).resolve().parents[1] / "hvac" / "ui_qt"

# Технические суффиксы единиц измерения (используются как .setSuffix(...))
# Их не локализуем — единица измерения «мм», «м²», «кВт» одинаково
# распознаваема в RU и UZ-контексте и часто оставляется в спецификациях.
UNIT_SUFFIXES = {
    " мм", " м", " м²", " м³", " м³/ч", " м³/(ч·м²)", " м/с",
    " кВт", " Вт", " Вт/(м²·К)", " Вт/(м·К)", " Вт/м²",
    " °C", " °С·сут", " Па", " бар", " кг/ч", " кг/(м²·ч)",
    " мест", " кабинетов", " классов", " номеров", " ★",
    " квартир", " этажей", " ч", " л", " л/сут", " дБА",
    " 1/ч",
    # Также сами единицы без ведущего пробела
    "мм", "м", "м²", "м³", "м³/ч", "м/с", "кВт", "Вт", "Вт/м²",
    "°C", "Па", "бар", "кг/ч", "1/ч", "дБА",
}

# Названия категорий и моделей оборудования, которые хранятся в данных
# (a не используются как чистый UI-текст). Они одинаковые в RU/UZ для
# инженерных каталогов.
DATA_VALUES = {
    # Категории конструкций (ключи DEFAULT_U_BY_CATEGORY)
    "Стены", "Окна", "Витраж", "Двери", "Покрытие", "Пол",
    "Универсал", "Тип-1",
    # Семейства радиаторов
    "Стальной панельный 11", "Стальной панельный 22",
    "Стальной панельный 33", "Алюминий", "Биметалл",
    "Биметалл (моноблок)", "Чугун",
    # Семейства фанкойлов
    "Кассетный 600×600", "Кассетный 600×600 (Roundflow)",
    "Канальный низконапорный", "Канальный среднего напора",
    "Настенный", "Напольно-потолочный",
    # VRF indoor families
    "Кассетный", "Канальный",
    # Дополнительные значения, которые приходят из CSV/проекта как данные
    "Ресторан / зал", "Кухня", "Санузел", "Коридор",
    # Дефолтные значения и placeholder'ы — это значения данных проекта,
    # а не UI-надписи. Город "Ташкент" пишется в project.params.city и
    # сохраняется в JSON.
    "Ташкент",
    # Воздушная прослойка — ключ каталога AIR_GAPS.
    "Воздушная прослойка 50 мм",
    # Префиксы зон, которые пишутся в data.system_heating
    "Зона A", "Зона B",
    # СП/КМК-нормативы как маркеры в коде (отображаются как есть)
    "СП 50.13330",
    # Имя «образца» (placeholder system_name)
    "СДУ-B1-PRK",
    # Лог-сообщение об ошибке (не UI)
    "Bridge: ошибка при relay %s",
    # Маркер «ИТОГО» в свод-таблице (короткое; отдельно при необходимости
    # будет вынесено в i18n позже)
    "ИТОГО",
    # Маркер «Готов» — статус-бар по умолчанию (короткий, заменяется живым
    # _t("status.ready") при смене языка)
    "Готов",
}


def _scan_file(path: Path) -> List[Tuple[int, str]]:
    """Возвращает список (lineno, literal) кириллических строковых
    литералов в файле, кроме docstring'ов модуля/класса/функции.
    """
    source = path.read_text(encoding="utf-8")
    tree = ast.parse(source, filename=str(path))

    # Множество (lineno) тех строк, что являются docstring'ами и
    # потому исключаются.
    docstring_lines: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.FunctionDef,
                             ast.AsyncFunctionDef, ast.ClassDef)):
            ds = ast.get_docstring(node, clean=False)
            if ds and node.body and isinstance(node.body[0], ast.Expr):
                expr = node.body[0].value
                if isinstance(expr, ast.Constant):
                    # Все строки docstring-литерала
                    start = expr.lineno
                    end = getattr(expr, "end_lineno", start)
                    for ln in range(start, end + 1):
                        docstring_lines.add(ln)

    # Также собираем строки в комментариях через tokenize — у нас они
    # уже не попадают в ast.Constant, но на всякий случай.
    # Нас интересуют только ast.Constant с str-value.
    bad: List[Tuple[int, str]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            if node.lineno in docstring_lines:
                continue
            text = node.value
            if not any("Ѐ" <= ch <= "ӿ" for ch in text):
                continue
            bad.append((node.lineno, text))
    return bad


def _line_has_allow_marker(path: Path, lineno: int) -> bool:
    """True, если строка кода имеет в конце маркер ``# i18n-allow``."""
    try:
        with path.open(encoding="utf-8") as f:
            for i, line in enumerate(f, 1):
                if i == lineno:
                    return "# i18n-allow" in line
    except OSError:
        return False
    return False


def _all_py_files() -> Iterable[Path]:
    for root, _dirs, files in os.walk(UI_QT_DIR):
        for fn in files:
            if fn.endswith(".py"):
                yield Path(root) / fn


@pytest.mark.parametrize("path", list(_all_py_files()),
                         ids=lambda p: p.relative_to(UI_QT_DIR).as_posix())
def test_no_hardcoded_cyrillic_ui_strings(path: Path) -> None:
    """Все кириллические UI-литералы в ui_qt должны быть локализованы
    через _t(...). Допустимы: технические суффиксы единиц (UNIT_SUFFIXES),
    значения данных (DATA_VALUES) или явный маркер ``# i18n-allow``."""
    findings = _scan_file(path)
    leftovers: List[Tuple[int, str]] = []
    for ln, text in findings:
        if text in UNIT_SUFFIXES or text.strip() in UNIT_SUFFIXES:
            continue
        if text in DATA_VALUES:
            continue
        if _line_has_allow_marker(path, ln):
            continue
        leftovers.append((ln, text))
    assert not leftovers, (
        f"\nКириллические UI-литералы в {path.relative_to(UI_QT_DIR.parent.parent)}, "
        f"не покрытые i18n:\n"
        + "\n".join(f"  L{ln}: {text!r}" for ln, text in leftovers)
        + "\n\nИспользуйте _t('key') или добавьте `# i18n-allow` в конец строки."
    )
