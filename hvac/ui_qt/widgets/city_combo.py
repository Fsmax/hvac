# -*- coding: utf-8 -*-
"""Combo-box со списком городов СП 131 + быстрый autocomplete по подстроке."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QComboBox, QCompleter, QWidget

from hvac.catalogs.climate import CLIMATE_DB


class CityCombo(QComboBox):
    """Combo-box со всеми 85 городами CLIMATE_DB."""

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setEditable(True)
        self.setInsertPolicy(QComboBox.NoInsert)

        # Сортируем: сначала Узбекистан, потом по алфавиту в рамках страны.
        cities = sorted(
            CLIMATE_DB.items(),
            key=lambda kv: (kv[1].get("country", "ZZ") != "UZ",
                            kv[1].get("country", ""), kv[0]),
        )
        for name, info in cities:
            country = info.get("country", "")
            label = f"{name}  ·  {country}" if country else name
            self.addItem(label, userData=name)

        completer = QCompleter([c[0] for c in cities], self)
        completer.setCaseSensitivity(Qt.CaseInsensitive)
        completer.setFilterMode(Qt.MatchContains)
        self.setCompleter(completer)

    def selected_city(self) -> str:
        """Возвращает имя выбранного города из CLIMATE_DB.

        Если пользователь напечатал текст, который ровно совпадает с одним
        из городов — возвращает его; иначе пустую строку.
        """
        data = self.currentData()
        if data:
            return data
        text = self.currentText().strip().split("·")[0].strip()
        if text in CLIMATE_DB:
            return text
        return ""

    def set_city(self, name: str) -> None:
        for i in range(self.count()):
            if self.itemData(i) == name:
                self.setCurrentIndex(i)
                return
