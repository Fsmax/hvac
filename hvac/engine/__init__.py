# -*- coding: utf-8 -*-
"""Расчётные движки. Импорт модуля автоматически регистрирует все движки."""

from hvac.engine.base import (
    CalculationEngine,
    register_engine,
    get_engine,
    list_engines,
    air_density,
)

# Импорты ниже — регистрируют движки в реестре через декораторы.
# Порядок импорта = порядок в выпадающем списке «Методика».
from hvac.engine import sp50  # noqa: F401
from hvac.engine import kmk   # noqa: F401
from hvac.engine import ventilation  # noqa: F401

# Чтобы добавить новый движок (например ASHRAE), создайте hvac/engine/ashrae.py
# с @register_engine, и добавьте сюда: from hvac.engine import ashrae  # noqa

__all__ = ["CalculationEngine", "register_engine", "get_engine",
           "list_engines", "air_density"]
