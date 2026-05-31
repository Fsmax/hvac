# -*- coding: utf-8 -*-
"""Базовый интерфейс расчётного движка.

Каждая методика (СП 50.13330, ASHRAE, EN 12831, КМК и т.д.) реализует
этот интерфейс как отдельный класс. Подключение нового движка =
наследование от CalculationEngine + декоратор @register_engine.
"""

from __future__ import annotations
from abc import ABC, abstractmethod
from typing import Dict, List, Type


def air_density(t_c: float) -> float:
    """Плотность воздуха, кг/м³ (упрощённая формула для расчётов)."""
    return 353.0 / (273.0 + t_c)


class CalculationEngine(ABC):
    """Абстрактный расчётный движок.

    Подклассы реализуют heat_loss и heat_gain для одного помещения.
    Универсальные расчёты (площади, инфильтрация) могут быть общими
    helper-функциями вне класса.
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Отображаемое имя методики (например 'СП 50.13330')."""

    @abstractmethod
    def heat_loss(self, space, project) -> Dict[str, float]:
        """Расчёт теплопотерь помещения. Возвращает разбивку по статьям."""

    @abstractmethod
    def heat_gain(self, space, project) -> Dict[str, float]:
        """Расчёт теплопоступлений помещения. Возвращает разбивку."""


# ---------- Реестр движков ----------

_ENGINE_REGISTRY: Dict[str, Type[CalculationEngine]] = {}


def register_engine(cls: Type[CalculationEngine]) -> Type[CalculationEngine]:
    """Декоратор регистрации движка."""
    instance = cls()
    _ENGINE_REGISTRY[instance.name] = cls
    return cls


def get_engine(name: str) -> CalculationEngine:
    """Возвращает экземпляр движка по имени."""
    cls = _ENGINE_REGISTRY.get(name)
    if cls is None:
        # Fallback на дефолт
        cls = next(iter(_ENGINE_REGISTRY.values()))
    return cls()


def list_engines() -> List[str]:
    """Имена всех зарегистрированных движков."""
    return list(_ENGINE_REGISTRY.keys())
