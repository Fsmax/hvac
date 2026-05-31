# -*- coding: utf-8 -*-
"""Утилиты парсинга строк из Revit CSV."""

from __future__ import annotations
import re
from typing import Optional

_NUM_RE = re.compile(r"-?\d+[\.,]?\d*")


def parse_number(value) -> Optional[float]:
    """Достаёт число из строки вроде '7.5 м²', '210.00', '12,3', '+420.42'.
    Возвращает None если не удалось распарсить."""
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    s = str(value).strip()
    if not s:
        return None
    s = s.replace("\xa0", " ").replace(",", ".")
    m = _NUM_RE.search(s)
    if not m:
        return None
    try:
        return float(m.group(0))
    except ValueError:
        return None


def parse_area(value) -> float:
    """То же что parse_number, но возвращает 0.0 при отсутствии значения."""
    v = parse_number(value)
    return v if v is not None else 0.0


# Конвертация азимута (0..360°) в розу ветров (8 секторов)
ORIENTATION_SECTORS = [
    ("N",  337.5, 360.0), ("N",   0.0,  22.5),
    ("NE", 22.5,  67.5),
    ("E",  67.5, 112.5),
    ("SE", 112.5, 157.5),
    ("S",  157.5, 202.5),
    ("SW", 202.5, 247.5),
    ("W",  247.5, 292.5),
    ("NW", 292.5, 337.5),
]


def azimuth_to_sector(azimuth) -> str:
    """0° = N, 90° = E, 180° = S, 270° = W. Возвращает код сектора или ''."""
    a = parse_number(azimuth)
    if a is None:
        return ""
    a = a % 360
    for label, lo, hi in ORIENTATION_SECTORS:
        if lo <= a < hi:
            return label
    return ""


def effective_orientation(element_orientation: str,
                           element_orientation_deg,
                           true_north_offset_deg: float) -> str:
    """Возвращает код стороны света (N/NE/E/.../NW) с учётом поворота
    True North относительно Project North.

    Если `element_orientation_deg` задан (из Revit) — применяет к нему
    поворот и пересчитывает сектор. Иначе возвращает исходный
    `element_orientation` (для ручного ввода, где deg может быть не задан).

    Параметры
    ---------
    element_orientation : код сектора без поправки ("N", "SE", "" и т.д.)
    element_orientation_deg : азимут в градусах (0..360) или None
    true_north_offset_deg : сдвиг True North против часовой, °
                            (положительный — против часовой)
    """
    if not true_north_offset_deg or true_north_offset_deg == 0:
        return element_orientation or ""
    deg = parse_number(element_orientation_deg)
    if deg is None:
        # Нет точного азимута — приближённо пересчитаем по коду:
        # для каждого сектора берём его середину
        sector_centers = {"N": 0, "NE": 45, "E": 90, "SE": 135,
                          "S": 180, "SW": 225, "W": 270, "NW": 315}
        if element_orientation not in sector_centers:
            return element_orientation or ""
        deg = sector_centers[element_orientation]
    adjusted = (deg + true_north_offset_deg) % 360
    return azimuth_to_sector(adjusted)
