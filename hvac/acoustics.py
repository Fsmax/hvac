# -*- coding: utf-8 -*-
"""Акустический расчёт вентиляционных систем и подбор шумоглушителей.

Считает уровень звукового давления Lp в обслуживаемой зоне по
октавным полосам 63-8000 Гц, выполняет А-коррекцию, сравнивает с
нормативным уровнем (СН 2.2.4/2.1.8.562-96, СП 51.13330) и подбирает
шумоглушитель из встроенного каталога по требуемому затуханию.

Модель цепочки звука
--------------------
    L_fan(63..8000)              — спектр звукового давления вентилятора
       │
       ▼ −ΔL_duct        затухание в прямых воздуховодах
       ▼ −ΔL_elbow       затухание в отводах
       ▼ −ΔL_silencer    шумоглушитель (вставка по спектру)
       ▼ −ΔL_branch      потери на ответвлениях
       ▼ −ΔL_terminal    затухание выпуска (диффузор → помещение)
       ▼ +ΔL_room        прибавка от помещения (геометрия, поглощение)
    = L_p(63..8000) → ΣA = LpA в дБА

Источники
---------
ASHRAE HOF 2017, гл. 49 (Sound and Vibration Control)
СП 51.13330.2011 «Защита от шума»
АВОК Справочник 5.7 «Акустика систем вентиляции»
ГОСТ 31295.2-2005 (затухание в прямых воздуховодах)
ГОСТ Р 53187-2008 (классы звукоизоляции)
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple


# ============================================================================
# Октавные полосы и А-коррекция
# ============================================================================

OCTAVE_BANDS_HZ = (63, 125, 250, 500, 1000, 2000, 4000, 8000)

# А-коррекция (МЭК 61672), дБ
A_WEIGHTING_DB: Dict[int, float] = {
    63:   -26.2,
    125:  -16.1,
    250:   -8.6,
    500:   -3.2,
    1000:   0.0,
    2000:   1.2,
    4000:   1.0,
    8000:  -1.1,
}


# Тип спектра — обычная разбивка по октавам, словарь {Гц: дБ}.
Spectrum = Dict[int, float]


def zero_spectrum() -> Spectrum:
    return {b: 0.0 for b in OCTAVE_BANDS_HZ}


def a_weighted_level(spectrum: Spectrum) -> float:
    """Эквивалентный уровень LpA в дБА — логарифмическое суммирование
    скорректированных по A полос."""
    total = 0.0
    for band, lp in spectrum.items():
        if band not in A_WEIGHTING_DB:
            continue
        l_a = lp + A_WEIGHTING_DB[band]
        total += 10.0 ** (l_a / 10.0)
    if total <= 0:
        return 0.0
    return 10.0 * math.log10(total)


def add_sources(*spectra: Spectrum) -> Spectrum:
    """Логарифмическое сложение двух и более источников."""
    out = zero_spectrum()
    for band in OCTAVE_BANDS_HZ:
        s = 0.0
        for sp in spectra:
            lp = sp.get(band, 0.0)
            if lp > 0:
                s += 10.0 ** (lp / 10.0)
        out[band] = 10.0 * math.log10(s) if s > 0 else 0.0
    return out


def subtract_attenuation(source: Spectrum,
                          attenuation: Spectrum) -> Spectrum:
    """Вычитает затухание (поэлементно)."""
    out = {}
    for band in OCTAVE_BANDS_HZ:
        out[band] = max(source.get(band, 0.0) - attenuation.get(band, 0.0),
                        0.0)
    return out


# ============================================================================
# Спектр шума вентилятора
# ============================================================================

# Базовая разбивка спектра шума типового центробежного вентилятора
# (равная по громкости коррекция от LwA, дБ — добавляется к LwA вентилятора,
# чтобы получить LpW в октавах). Источник: ASHRAE HOF 2017 Table 22.
FAN_SPECTRUM_OFFSETS_CENTRIFUGAL: Dict[int, float] = {
    63:   -2.0,
    125:  -7.0,
    250: -12.0,
    500: -17.0,
    1000:-22.0,
    2000:-27.0,
    4000:-32.0,
    8000:-37.0,
}

FAN_SPECTRUM_OFFSETS_AXIAL: Dict[int, float] = {
    63:   -7.0,
    125: -11.0,
    250: -14.0,
    500: -15.0,
    1000:-15.0,
    2000:-19.0,
    4000:-25.0,
    8000:-34.0,
}


def fan_sound_power_spectrum(
    lw_total_dba: float,
    fan_type: str = "centrifugal",
) -> Spectrum:
    """Восстанавливает Lw по октавам из общего LwA вентилятора.

    Использует типовые «формы» спектра по типу вентилятора.
    Точные значения LwA брать из техпаспорта вентилятора;
    эта функция нужна для оценки, когда известно только общее значение.
    """
    offsets = (FAN_SPECTRUM_OFFSETS_CENTRIFUGAL
               if fan_type == "centrifugal"
               else FAN_SPECTRUM_OFFSETS_AXIAL)
    return {band: lw_total_dba + off for band, off in offsets.items()}


def fan_lw_estimate_beranek(
    fan_flow_m3_h: float,
    fan_pressure_pa: float,
    *,
    efficiency: float = 0.65,
    blade_passing_correction_db: float = 3.0,
) -> float:
    """Эмпирическая оценка LwA вентилятора по Beranek (общее звуковое мощность).

    Формула (грубая, для ранней оценки):
        Lw = 67 + 10·lg(Q[м³/с]) + 10·lg(ΔP[Па]) + 3 (если КПД < 0.7)

    Для точного значения брать из паспорта вентилятора.
    """
    if fan_flow_m3_h <= 0 or fan_pressure_pa <= 0:
        return 0.0
    q_m3s = fan_flow_m3_h / 3600.0
    lw = 67.0 + 10.0 * math.log10(q_m3s) + 10.0 * math.log10(fan_pressure_pa)
    if efficiency < 0.70:
        lw += blade_passing_correction_db
    return lw


# ============================================================================
# Затухание в элементах воздуховодной сети
# ============================================================================

# Удельное затухание в круглом необлицованном воздуховоде (дБ/м)
# по ГОСТ 31295.2-2005. Зависит от диаметра.
def duct_attenuation_per_m(diameter_mm: float,
                            lined: bool = False) -> Spectrum:
    """Затухание в прямом воздуховоде, дБ/м (по октавам)."""
    if diameter_mm >= 800:
        base = {63: 0.10, 125: 0.10, 250: 0.15, 500: 0.15,
                1000: 0.10, 2000: 0.10, 4000: 0.10, 8000: 0.10}
    elif diameter_mm >= 400:
        base = {63: 0.15, 125: 0.20, 250: 0.30, 500: 0.40,
                1000: 0.30, 2000: 0.25, 4000: 0.20, 8000: 0.15}
    else:
        base = {63: 0.30, 125: 0.40, 250: 0.60, 500: 0.80,
                1000: 0.50, 2000: 0.40, 4000: 0.30, 8000: 0.20}
    if lined:
        # Облицовка увеличивает затухание в 3-5 раз на средних частотах
        return {b: v * (3.0 if 250 <= b <= 2000 else 1.5)
                for b, v in base.items()}
    return base


# Затухание в отводе 90°, дБ (по АВОК Справочнику 5.7)
ELBOW_90_ATTENUATION: Spectrum = {
    63: 0.0, 125: 0.0, 250: 1.0, 500: 2.0,
    1000: 3.0, 2000: 3.0, 4000: 3.0, 8000: 3.0,
}

# Затухание выпуска через приточный диффузор в помещение
TERMINAL_ATTENUATION: Spectrum = {
    63: 1.0, 125: 1.0, 250: 1.5, 500: 2.0,
    1000: 2.5, 2000: 3.0, 4000: 3.5, 8000: 4.0,
}


def branch_split_attenuation(flow_main_m3_h: float,
                              flow_branch_m3_h: float) -> Spectrum:
    """Затухание на ответвлении, дБ.

        ΔL = 10·lg(L_main / L_branch)

    Звук делится пропорционально расходу в ответвлениях."""
    if flow_main_m3_h <= 0 or flow_branch_m3_h <= 0:
        return zero_spectrum()
    ratio = flow_main_m3_h / flow_branch_m3_h
    dl = 10.0 * math.log10(ratio) if ratio > 0 else 0.0
    return {b: dl for b in OCTAVE_BANDS_HZ}


def room_attenuation(room_volume_m3: float,
                      distance_m: float = 1.5,
                      reverb_constant_m2: float = 20.0) -> Spectrum:
    """Прибавка/затухание от помещения (диффузный + прямой).

    Lp = Lw + 10·lg(Q/(4πr²) + 4/R)

    где Q — фактор направленности (1 для всенаправленного),
        R — постоянная помещения (зависит от поглощения).

    Возвращает «отрицательное затухание» Lw → Lp, т.е. величину, на которую
    Lw нужно скорректировать, чтобы получить Lp в точке. Для практики:
        ΔL ≈ 6 (близко к диффузору) … 12 дБ (в дальней зоне)
    """
    if distance_m <= 0:
        distance_m = 0.5
    direct = 1.0 / (4.0 * math.pi * distance_m * distance_m)
    diffuse = 4.0 / max(reverb_constant_m2, 1.0)
    factor = direct + diffuse
    delta = 10.0 * math.log10(factor)   # обычно отрицательное (затухание)
    # Отдаём как «затухание» (положительное), которое будет вычитаться из Lw
    return {b: -delta for b in OCTAVE_BANDS_HZ}


# ============================================================================
# Норматив СН 2.2.4/2.1.8.562-96 и СП 51.13330
# ============================================================================

# Нормативный LpA в помещениях, дБА (СП 51.13330.2011 Прил. К,
# ночное / дневное время для жилья — здесь дневное)
ROOM_NOISE_NORMS_DBA: Dict[str, float] = {
    "Жилая комната": 40.0,             # день
    "Спальня (ночь)": 30.0,
    "Офис": 50.0,
    "Конференц-зал": 35.0,
    "Гостиничный номер": 40.0,
    "Класс / аудитория": 40.0,
    "Палата больничная": 35.0,
    "Кабинет врача": 35.0,
    "Ресторан / кухня": 60.0,
    "Магазин / торговля": 55.0,
    "Технич. помещение": 70.0,
    "Серверная": 70.0,
    "Гараж / автостоянка": 70.0,
    "Прочее": 50.0,
}


def required_noise_level(room_type: str, default: float = 50.0) -> float:
    return ROOM_NOISE_NORMS_DBA.get(room_type, default)


# ============================================================================
# Шумоглушители
# ============================================================================

@dataclass
class Silencer:
    """Запись каталога шумоглушителя — затухание по октавам."""
    name: str
    length_mm: int                         # длина 600 / 900 / 1200 / 1500
    insertion_loss: Spectrum = field(default_factory=zero_spectrum)
    pressure_drop_pa: float = 30.0
    note: str = ""


# Типовые круглые/прямоугольные шумоглушители (КСП, ГП, Trox MSA).
# IL — Insertion Loss (затухание вставки) по октавам, дБ.
SILENCER_CATALOG: List[Silencer] = [
    Silencer("ШГ-600 круглый", 600,
              insertion_loss={63: 3, 125: 6, 250: 12, 500: 18,
                              1000: 22, 2000: 24, 4000: 18, 8000: 10},
              pressure_drop_pa=25),
    Silencer("ШГ-900 круглый", 900,
              insertion_loss={63: 4, 125: 8, 250: 16, 500: 24,
                              1000: 30, 2000: 30, 4000: 24, 8000: 14},
              pressure_drop_pa=35),
    Silencer("ШГ-1200 круглый", 1200,
              insertion_loss={63: 5, 125: 10, 250: 20, 500: 30,
                              1000: 36, 2000: 36, 4000: 28, 8000: 16},
              pressure_drop_pa=45),
    Silencer("ШГ-1500 круглый", 1500,
              insertion_loss={63: 6, 125: 12, 250: 24, 500: 34,
                              1000: 40, 2000: 40, 4000: 30, 8000: 18},
              pressure_drop_pa=55),
    Silencer("ГП-600 пластинчатый", 600,
              insertion_loss={63: 4, 125: 8, 250: 14, 500: 20,
                              1000: 25, 2000: 25, 4000: 20, 8000: 12},
              pressure_drop_pa=20),
    Silencer("ГП-1200 пластинчатый", 1200,
              insertion_loss={63: 7, 125: 14, 250: 24, 500: 32,
                              1000: 38, 2000: 38, 4000: 30, 8000: 18},
              pressure_drop_pa=40),
    Silencer("ГП-2000 пластинчатый", 2000,
              insertion_loss={63: 10, 125: 18, 250: 30, 500: 40,
                              1000: 45, 2000: 45, 4000: 36, 8000: 22},
              pressure_drop_pa=65),
]


@dataclass
class AcousticAnalysis:
    """Результат акустического расчёта одной обслуживаемой точки."""
    lp_at_terminal: Spectrum = field(default_factory=zero_spectrum)
    lpa_at_terminal: float = 0.0
    lpa_required_dba: float = 0.0
    margin_dba: float = 0.0                # required − actual (отриц. = превышение)
    silencer_selected: Optional[Silencer] = None
    silencer_required: bool = False
    chain_breakdown: List[Tuple[str, Spectrum]] = field(default_factory=list)


def analyze_path(
    fan_lw_dba: float,
    *,
    fan_type: str = "centrifugal",
    duct_segments: Optional[List[Tuple[float, float, bool]]] = None,
    elbows_90_count: int = 0,
    branch_flow_ratios: Optional[List[Tuple[float, float]]] = None,
    silencer: Optional[Silencer] = None,
    room_volume_m3: float = 30.0,
    room_distance_m: float = 1.5,
    room_reverb_const_m2: float = 20.0,
    room_norm_dba: float = 40.0,
) -> AcousticAnalysis:
    """Полный акустический расчёт цепочки от вентилятора до точки в помещении.

    Параметры
    ---------
    fan_lw_dba          : общее LwA вентилятора, дБА (из паспорта или
                          fan_lw_estimate_beranek)
    fan_type            : centrifugal / axial — форма спектра
    duct_segments       : список (длина_м, диаметр_мм, lined) — прямые участки
    elbows_90_count     : сколько отводов 90° по пути
    branch_flow_ratios  : список (Lглавн, Lветвь) — затухание на разветвлениях
    silencer            : установленный шумоглушитель (или None)
    room_*              : геометрия помещения и норма шума
    """
    fan_spec = fan_sound_power_spectrum(fan_lw_dba, fan_type=fan_type)
    chain: List[Tuple[str, Spectrum]] = [("Вентилятор Lw", dict(fan_spec))]
    current = dict(fan_spec)

    # Прямые участки
    if duct_segments:
        for length_m, dia_mm, lined in duct_segments:
            per_m = duct_attenuation_per_m(dia_mm, lined=lined)
            att = {b: per_m[b] * length_m for b in OCTAVE_BANDS_HZ}
            current = subtract_attenuation(current, att)
            chain.append((f"Воздуховод L={length_m}м Ø{dia_mm}", att))

    # Отводы
    if elbows_90_count > 0:
        att = {b: ELBOW_90_ATTENUATION[b] * elbows_90_count
               for b in OCTAVE_BANDS_HZ}
        current = subtract_attenuation(current, att)
        chain.append((f"Отводы ×{elbows_90_count}", att))

    # Шумоглушитель
    if silencer is not None:
        current = subtract_attenuation(current, silencer.insertion_loss)
        chain.append((f"Шумоглушитель {silencer.name}",
                       dict(silencer.insertion_loss)))

    # Разветвления
    if branch_flow_ratios:
        for main, branch in branch_flow_ratios:
            att = branch_split_attenuation(main, branch)
            current = subtract_attenuation(current, att)
            chain.append((f"Разветвление {main:.0f}→{branch:.0f}", att))

    # Терминал
    current = subtract_attenuation(current, TERMINAL_ATTENUATION)
    chain.append(("Выпуск диффузор", dict(TERMINAL_ATTENUATION)))

    # Помещение: пересчёт Lw → Lp
    room_att = room_attenuation(room_volume_m3, room_distance_m,
                                  room_reverb_const_m2)
    current = subtract_attenuation(current, room_att)
    chain.append(("Прибавка помещения (Lw→Lp)", dict(room_att)))

    lpa = a_weighted_level(current)
    return AcousticAnalysis(
        lp_at_terminal=current,
        lpa_at_terminal=lpa,
        lpa_required_dba=room_norm_dba,
        margin_dba=room_norm_dba - lpa,
        silencer_selected=silencer,
        silencer_required=lpa > room_norm_dba,
        chain_breakdown=chain,
    )


def select_silencer(
    fan_lw_dba: float,
    room_norm_dba: float,
    *,
    fan_type: str = "centrifugal",
    duct_segments: Optional[List[Tuple[float, float, bool]]] = None,
    elbows_90_count: int = 0,
    branch_flow_ratios: Optional[List[Tuple[float, float]]] = None,
    room_volume_m3: float = 30.0,
    room_distance_m: float = 1.5,
    room_reverb_const_m2: float = 20.0,
    catalog: Optional[List[Silencer]] = None,
) -> AcousticAnalysis:
    """Подбирает первый шумоглушитель из каталога, обеспечивающий
    Lpa ≤ room_norm_dba. Если без глушителя норматив уже выполнен —
    возвращает результат без подбора.
    """
    # Сначала проверка без глушителя
    base = analyze_path(
        fan_lw_dba, fan_type=fan_type,
        duct_segments=duct_segments,
        elbows_90_count=elbows_90_count,
        branch_flow_ratios=branch_flow_ratios,
        silencer=None,
        room_volume_m3=room_volume_m3,
        room_distance_m=room_distance_m,
        room_reverb_const_m2=room_reverb_const_m2,
        room_norm_dba=room_norm_dba,
    )
    if base.lpa_at_terminal <= room_norm_dba:
        base.silencer_required = False
        return base

    cat = catalog if catalog is not None else SILENCER_CATALOG
    # Подбираем самый короткий, который дотягивает до норматива.
    # Если ни один не дотянет — возвращаем САМЫЙ эффективный (макс. снижение)
    # с предупреждением, что норматив не выполнен.
    best: Optional[AcousticAnalysis] = None
    fallback: Optional[AcousticAnalysis] = None
    best_lpa = float("inf")
    for s in cat:
        res = analyze_path(
            fan_lw_dba, fan_type=fan_type,
            duct_segments=duct_segments,
            elbows_90_count=elbows_90_count,
            branch_flow_ratios=branch_flow_ratios,
            silencer=s,
            room_volume_m3=room_volume_m3,
            room_distance_m=room_distance_m,
            room_reverb_const_m2=room_reverb_const_m2,
            room_norm_dba=room_norm_dba,
        )
        if res.lpa_at_terminal < best_lpa:
            best_lpa = res.lpa_at_terminal
            fallback = res
        if res.lpa_at_terminal <= room_norm_dba and best is None:
            best = res
    return best if best is not None else (fallback or base)
