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
    tz_offset_h: float = 0.0         # часовой пояс из LOCATION (ч от UTC)
    elevation_m: float = 0.0
    t_dry_bulb_c: List[float] = field(default_factory=list)
    rh_pct: List[float] = field(default_factory=list)
    ghi_w_m2: List[float] = field(default_factory=list)   # глоб. горизонт. радиация

    @property
    def has_solar(self) -> bool:
        """Есть ли пригодные данные радиации (не все нули) и координаты."""
        return (self.latitude != 0.0 and bool(self.ghi_w_m2)
                and max(self.ghi_w_m2) > 0.0)

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
        wd.tz_offset_h = float(head[8])
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


# ============================================================================
# Расчётные климатические параметры из почасовых данных
# ============================================================================

# Обеспеченность тёплого периода по СНиП 2.04.05 (прил. 8): параметр
# обеспеченностью 0,95 превышается не более 440 ч/год, 0,98 — 88 ч/год.
_EXCEED_HOURS_095 = 440
_EXCEED_HOURS_098 = 88

_MONTH_DAYS = (31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31)


@dataclass
class DesignConditions:
    """Расчётные параметры климата, выведенные из почасовых данных EPW.

    Зимние значения — характеристики ЭТОГО типового метеогода (одна
    реализация), поэтому сопоставимы с табличной обеспеченностью
    0,92/0,98 лишь приближённо. Летние обеспеченности 0,95/0,98 считаются
    строго по определению СНиП (квантиль по часам превышения). Периоды
    z/t (≤8 и ≤12 °C) и ГСОП сопоставимы с полями справочника климата
    (catalogs/climate.py) и пригодны для точного расчёта Dd.
    """
    t_cold_5day_c: float = 0.0   # мин. 5-суточная средняя (≈ t_heat_092)
    t_cold_1day_c: float = 0.0   # мин. суточная средняя (≈ t_heat_098)
    t_cool_095_c: float = 0.0    # лето, превышается ≤440 ч/год
    t_cool_098_c: float = 0.0    # лето, превышается ≤88 ч/год
    daily_amp_summer_k: float = 0.0  # ср. суточная амплитуда тёплого месяца
    z_ht_8_days: int = 0         # сутки со среднесуточной ≤8 °C
    t_ht_8_c: float = 0.0        # средняя температура этих суток
    z_ht_12_days: int = 0        # то же для порога ≤12 °C
    t_ht_12_c: float = 0.0
    gsop_18: float = 0.0         # (20 − t_ht_8)·z_ht_8, как gsop_18 каталога


def derive_design_conditions(wd: WeatherData) -> DesignConditions:
    """Вычисляет расчётные параметры климата из 8760-часовых данных."""
    t = wd.t_dry_bulb_c
    if len(t) < HOURS_IN_YEAR:
        raise ValueError(
            f"derive_design_conditions: нужно {HOURS_IN_YEAR} часов, "
            f"получено {len(t)}")

    n_days = HOURS_IN_YEAR // 24
    daily = [sum(t[d * 24:(d + 1) * 24]) / 24.0 for d in range(n_days)]

    # Холодная пятидневка может пересекать границу года — замыкаем кольцо
    ring = daily + daily[:4]
    t5 = min(sum(ring[i:i + 5]) / 5.0 for i in range(n_days))
    t1 = min(daily)

    # Летние обеспеченности: квантиль по числу часов превышения
    hot_sorted = sorted(t, reverse=True)
    t95 = hot_sorted[_EXCEED_HOURS_095]
    t98 = hot_sorted[_EXCEED_HOURS_098]

    # Суточная амплитуда самого тёплого месяца
    month_of_day: List[int] = []
    for m, nd in enumerate(_MONTH_DAYS):
        month_of_day.extend([m] * nd)
    month_mean = [0.0] * 12
    month_days_n = [0] * 12
    for d in range(n_days):
        month_mean[month_of_day[d]] += daily[d]
        month_days_n[month_of_day[d]] += 1
    for m in range(12):
        month_mean[m] /= max(month_days_n[m], 1)
    warm_month = month_mean.index(max(month_mean))
    amps = [
        max(t[d * 24:(d + 1) * 24]) - min(t[d * 24:(d + 1) * 24])
        for d in range(n_days) if month_of_day[d] == warm_month
    ]
    amp = sum(amps) / len(amps) if amps else 0.0

    # Отопительный период: сутки со среднесуточной ≤ порога
    def _period(threshold: float) -> tuple[int, float]:
        cold = [v for v in daily if v <= threshold]
        if not cold:
            return 0, 0.0
        return len(cold), sum(cold) / len(cold)

    z8, t8 = _period(8.0)
    z12, t12 = _period(12.0)
    gsop = (20.0 - t8) * z8 if z8 else 0.0

    return DesignConditions(
        t_cold_5day_c=round(t5, 1),
        t_cold_1day_c=round(t1, 1),
        t_cool_095_c=round(t95, 1),
        t_cool_098_c=round(t98, 1),
        daily_amp_summer_k=round(amp, 1),
        z_ht_8_days=z8,
        t_ht_8_c=round(t8, 1),
        z_ht_12_days=z12,
        t_ht_12_c=round(t12, 1),
        gsop_18=round(gsop),
    )
