# -*- coding: utf-8 -*-
"""Изоляция тестов от глобального состояния пользователя.

Без этого fixture модуль hvac.catalogs.user_norms подгружал бы реальный
файл ~/HVAC/user_norms.json пользователя, и любые сохранённые там
override’ы (например «Офис: m3_per_person=60») ломали бы детерминизм
тестов, которые ожидают СП-дефолты.
"""

import pytest

from hvac.catalogs import user_norms


@pytest.fixture(autouse=True)
def _isolate_user_norms(tmp_path, monkeypatch):
    """Каждый тест получает чистую временную папку для user_norms.json.

    autouse=True → срабатывает для всех тестов автоматически, никакого
    декоратора в самих тестах не нужно.
    """
    # 1. Сбрасываем кэш модуля
    user_norms._cache = None
    # 2. Перенаправляем путь к файлу на временный
    fake_path = str(tmp_path / "user_norms.json")
    monkeypatch.setattr(user_norms, "_user_norms_path", lambda: fake_path)
    yield
    # 3. После теста — снова сбрасываем кэш (на случай если тест
    #    сам что-то писал в overrides).
    user_norms._cache = None
