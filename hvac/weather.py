# -*- coding: utf-8 -*-
"""Загрузка погодных файлов EPW (EnergyPlus Weather).

EPW — стандартный формат годовых почасовых климатических данных
(TMY/IWEC/типовой метеогод): 8 строк заголовка + 8760 строк данных.
Файлы для большинства городов мира свободно доступны на
climate.onebuilding.org и energyplus.net/weather.

Используется 8760-часовой симуляцией (hvac/energy_simulation.py):
вместо синтетического синусоидального профиля наружной температуры
подставляются реальные почасовые значения. Влажность и солнечная
радиация читаются и сохраняются для отчётов и будущих уточнений.

Пропуски в данных (коды 99.9 / 999 / 9999 по спецификации EPW)
заполняются последним валидным значением.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Union

HOURS_IN_YEAR = 8760

# Коды «нет данных» по спецификации EPW (Auxiliary Programs, гл. 2)
_MISSING_DRY_BULB = 99.9
_MISSING_RH = 999.0
_MISSING_RADIATION = 9999.0


@dataclass
class WeatherData:
    """Годовой почасовой климат из EPW-файла (8760 значений в списках)."""
    source: str = ""                 # путь к файлу
    location: str = ""               # город из заголовка LOCATION
    country: str = ""
    latitude: float = 0.0
    longitude: float = 0.0
    elevation_m: float = 0.0
    t_dry_bulb_c: List[float] = field(default_factory=list)
    rh_pct: List[float] = field(default_factory=list)
    ghi_w_m2: List[float] = field(default_factory=list)   # глоб. горизонт. радиация

    @property
    def t_min_c(self) -> float:
        return min(self.t_dry_bulb_c) if self.t_dry_bulb_c else 0.0

    @property
    def t_max_c(self) -> float:
        return max(self.t_dry_bulb_c) if self.t_dry_bulb_c else 0.0

    @property
    def t_mean_c(self) -> float:
        if not self.t_dry_bulb_c:
            return 0.0
        return sum(self.t_dry_bulb_c) / len(self.t_dry_bulb_c)


def _clean_series(values: List[float], missing_code: float) -> List[float]:
    """Заменяет коды «нет данных» последним валидным значением."""
    out: List[float] = []
    last_valid = 0.0
    for v in values:
        if v >= missing_code:
            v = last_valid
        else:
            last_valid = v
        out.append(v)
    return out


def load_epw(path: Union[str, Path]) -> WeatherData:
    """Читает EPW-файл и возвращает WeatherData.

    Поднимает ValueError при неправильном формате (мало строк данных,
    нечисловые поля). Високосные файлы (8784 ч) усечены до 8760.
    """
    p = Path(path)
    text = p.read_text(encoding="utf-8", errors="replace")
    lines = [ln for ln in text.splitlines() if ln.strip()]
    if len(lines) < 9:
        raise ValueError(f"EPW: слишком короткий файл ({len(lines)} строк)")

    wd = WeatherData(source=str(p))

    # Заголовок LOCATION: город, регион, страна, источник, WMO,
    # широта, долгота, часовой пояс, высота
    head = lines[0].split(",")
    if head[0].strip().upper() != "LOCATION":
        raise ValueError("EPW: первая строка должна начинаться с LOCATION")
    if len(head) > 3:
        wd.location = head[1].strip()
        wd.country = head[3].strip()
    try:
        wd.latitude = float(head[6])
        wd.longitude = float(head[7])
        wd.elevation_m = float(head[9])
    except (IndexError, ValueError):
        pass                               # координаты необязательны

    # Данные начинаются после 8 строк заголовка. Некоторые файлы содержат
    # лишние строки комментариев — ищем первую строку, где ≥30 полей и
    # первое поле — год (число).
    t: List[float] = []
    rh: List[float] = []
    ghi: List[float] = []
    for ln in lines[8:]:
        fields_ = ln.split(",")
        if len(fields_) < 16:
            continue
        try:
            float(fields_[0])              # год — проверка, что строка данных
            t.append(float(fields_[6]))    # сухой термометр, °C
            rh.append(float(fields_[8]))   # отн. влажность, %
            ghi.append(float(fields_[13]))  # глоб. гориз. радиация, Вт·ч/м²
        except ValueError as exc:
            raise ValueError(f"EPW: нечисловое поле в строке данных: {exc}")
        if len(t) >= HOURS_IN_YEAR:
            break                          # 8784 (високосный) → усечь

    if len(t) < HOURS_IN_YEAR:
        raise ValueError(
            f"EPW: ожидалось {HOURS_IN_YEAR} часов данных, найдено {len(t)}")

    wd.t_dry_bulb_c = _clean_series(t, _MISSING_DRY_BULB)
    wd.rh_pct = _clean_series(rh, _MISSING_RH)
    wd.ghi_w_m2 = _clean_series(ghi, _MISSING_RADIATION)
    return wd
