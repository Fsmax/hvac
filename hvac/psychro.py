# -*- coding: utf-8 -*-
"""Психрометрика влажного воздуха.

Реализация основных формул ASHRAE Handbook of Fundamentals 2017,
глава 1 (Psychrometrics). Используется для расчёта точек процесса в
приточных установках, построения i-d диаграммы и проверки конденсации.

Конвенции
---------
Все температуры в **°C** (не Кельвинах).
Влагосодержание W (humidity ratio) — **в кг воды на кг сухого воздуха**.
В отчётах удобнее г/кг — для этого есть `to_g_kg(W)` / `from_g_kg(w)`.
Энтальпия H в **кДж/кг сухого воздуха**.
Давление воздуха p в **Па**, по умолчанию 101325 Па (уровень моря).

Опорные функции
---------------
    saturation_pressure_pa(t)      — давление насыщения, Па
    humidity_ratio_from_pw(pw, p)  — W из парциального давления пара
    pw_from_humidity_ratio(W, p)   — обратная
    relative_humidity(t, W, p)     — φ из (T, W)
    humidity_ratio_from_rh(t, rh, p) — W из (T, φ)
    enthalpy(t, W)                 — H = 1.006·t + W·(2501 + 1.86·t)
    dew_point(W, p)                — точка росы по W
    wet_bulb(t, W, p)              — температура мокрого термометра (итерационно)
    specific_volume(t, W, p)       — удельный объём, м³/кг сухого воздуха

Конструктор состояний
---------------------
    AirState — неизменяемая точка с расчётом всех параметров от (T, W)
    AirState.from_t_rh(t, rh)
    AirState.from_t_wb(t, twb)
    AirState.from_t_dp(t, td)

Процессы
--------
    mix_streams([(state, mass_flow), ...])  — смешение потоков
    heat(state, t_out)                       — сухой нагрев (W = const)
    cool(state, t_out)                       — охлаждение (с конденсацией если ниже Td)
    cool_dehumidify(state, t_out, bf=0.15)   — охлаждение с заданным BF
    humidify_steam(state, W_out)             — пароувлажнение (t ≈ const)
    humidify_adiabatic(state, eff)           — адиабатическое (Twb ≈ const)
    heat_recovery(t_out, t_extract, eff)     — приближение пластинчатого рекуператора
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import List, Tuple


# ============================================================================
# Константы
# ============================================================================

P_ATM = 101_325.0           # Па, атмосферное давление на уровне моря
R_DRY_AIR = 287.055         # Дж/(кг·К), газовая постоянная сухого воздуха
R_VAPOR = 461.5             # Дж/(кг·К), газовая постоянная пара
C_PA = 1.006                # кДж/(кг·К), удельная теплоёмкость сухого воздуха
C_PV = 1.86                 # кДж/(кг·К), удельная теплоёмкость водяного пара
H_FG_0 = 2501.0             # кДж/кг, скрытая теплота парообразования при 0°C


# ============================================================================
# Базовые функции
# ============================================================================

def saturation_pressure_pa(t_c: float) -> float:
    """Давление насыщенного водяного пара при температуре t, °C.

    Формула ASHRAE 2017 HOF, ур. (5)-(6):
    Для T = −100..0°C — ур. (5), для 0..200°C — ур. (6).
    Возвращает значение в **паскалях**.
    """
    T = t_c + 273.15
    if T < 173.15:
        T = 173.15
    if t_c < 0:
        # ASHRAE eq. (5): надо льда
        ln_pws = (
            -5.6745359e+3 / T
            + 6.3925247
            - 9.677843e-3 * T
            + 6.2215701e-7 * T ** 2
            + 2.0747825e-9 * T ** 3
            - 9.484024e-13 * T ** 4
            + 4.1635019 * math.log(T)
        )
    else:
        # ASHRAE eq. (6): над водой
        ln_pws = (
            -5.8002206e+3 / T
            + 1.3914993
            - 4.8640239e-2 * T
            + 4.1764768e-5 * T ** 2
            - 1.4452093e-8 * T ** 3
            + 6.5459673 * math.log(T)
        )
    return math.exp(ln_pws)


def humidity_ratio_from_pw(pw: float, p: float = P_ATM) -> float:
    """W из парциального давления пара pw [Па] и общего p [Па]."""
    if pw <= 0:
        return 0.0
    if pw >= p:
        # физически невозможно
        pw = 0.999 * p
    return 0.621945 * pw / (p - pw)


def pw_from_humidity_ratio(W: float, p: float = P_ATM) -> float:
    """Обратная: pw из W."""
    if W <= 0:
        return 0.0
    return p * W / (0.621945 + W)


def humidity_ratio_from_rh(t_c: float, rh: float,
                            p: float = P_ATM) -> float:
    """W из температуры t [°C] и относительной влажности rh ∈ [0..1]."""
    if rh <= 0:
        return 0.0
    pws = saturation_pressure_pa(t_c)
    pw = rh * pws
    return humidity_ratio_from_pw(pw, p)


def relative_humidity(t_c: float, W: float, p: float = P_ATM) -> float:
    """φ ∈ [0..1] из (t, W)."""
    pws = saturation_pressure_pa(t_c)
    pw = pw_from_humidity_ratio(W, p)
    if pws <= 0:
        return 0.0
    return min(pw / pws, 1.0)


def enthalpy(t_c: float, W: float) -> float:
    """Удельная энтальпия влажного воздуха, кДж/кг сухого воздуха.

    H = c_pa·t + W·(h_fg0 + c_pv·t)
      = 1.006·t + W·(2501 + 1.86·t)
    """
    return C_PA * t_c + W * (H_FG_0 + C_PV * t_c)


def temperature_from_h_w(h: float, W: float) -> float:
    """T из (H, W). Решение линейного уравнения для энтальпии."""
    return (h - W * H_FG_0) / (C_PA + W * C_PV)


def dew_point(W: float, p: float = P_ATM) -> float:
    """Точка росы [°C] по W."""
    if W <= 0:
        return -100.0
    pw = pw_from_humidity_ratio(W, p)
    # Обратное решение для pws = pw методом бисекции
    lo, hi = -80.0, 100.0
    for _ in range(60):
        mid = 0.5 * (lo + hi)
        if saturation_pressure_pa(mid) < pw:
            lo = mid
        else:
            hi = mid
    return 0.5 * (lo + hi)


def specific_volume(t_c: float, W: float, p: float = P_ATM) -> float:
    """Удельный объём смеси, м³/кг сухого воздуха.
    ASHRAE HOF ур. (26): v = R·T·(1 + 1.6078·W) / p,
    где R берётся для сухого воздуха."""
    T = t_c + 273.15
    return R_DRY_AIR * T * (1.0 + 1.6078 * W) / p


def wet_bulb(t_c: float, W: float, p: float = P_ATM) -> float:
    """Температура мокрого термометра, °C.

    Итерационный поиск Twb такой, что:
        H(Twb, Wsat(Twb)) ≈ H(t, W) + (W − Wsat(Twb)) · c_l · Twb,
    где c_l ≈ 4.186 кДж/(кг·К) — теплоёмкость воды.
    Используем упрощённое приближение через равенство энтальпий
    (ошибка < 0.2°C в диапазоне 0..40°C).
    """
    h = enthalpy(t_c, W)
    lo, hi = -20.0, t_c + 0.001
    for _ in range(50):
        mid = 0.5 * (lo + hi)
        W_sat = humidity_ratio_from_rh(mid, 1.0, p)
        h_sat = enthalpy(mid, W_sat)
        if h_sat < h:
            lo = mid
        else:
            hi = mid
    return 0.5 * (lo + hi)


# ============================================================================
# Состояние воздуха
# ============================================================================

@dataclass(frozen=True)
class AirState:
    """Точка на i-d диаграмме (неизменяемая).

    Минимальный набор полей: t_c, W, p. Остальные свойства вычисляются.
    """
    t_c: float                      # °C
    W: float                        # кг/кг сухого воздуха
    p: float = P_ATM                # Па

    # ---------- Альтернативные конструкторы ----------
    @classmethod
    def from_t_rh(cls, t_c: float, rh: float,
                  p: float = P_ATM) -> "AirState":
        return cls(t_c=t_c, W=humidity_ratio_from_rh(t_c, rh, p), p=p)

    @classmethod
    def from_t_wb(cls, t_c: float, t_wb: float,
                  p: float = P_ATM) -> "AirState":
        """Из сухого и мокрого термометра.
        Итерационный поиск W, при котором wet_bulb(t, W) = t_wb."""
        lo, hi = 0.0, humidity_ratio_from_rh(t_c, 1.0, p)
        for _ in range(40):
            mid = 0.5 * (lo + hi)
            if wet_bulb(t_c, mid, p) < t_wb:
                lo = mid
            else:
                hi = mid
        return cls(t_c=t_c, W=0.5 * (lo + hi), p=p)

    @classmethod
    def from_t_dp(cls, t_c: float, t_dp: float,
                  p: float = P_ATM) -> "AirState":
        """Из сухого термометра и точки росы."""
        pw = saturation_pressure_pa(t_dp)
        return cls(t_c=t_c, W=humidity_ratio_from_pw(pw, p), p=p)

    # ---------- Вычисляемые свойства ----------
    @property
    def rh(self) -> float:
        return relative_humidity(self.t_c, self.W, self.p)

    @property
    def h_kj_kg(self) -> float:
        return enthalpy(self.t_c, self.W)

    @property
    def t_dp_c(self) -> float:
        return dew_point(self.W, self.p)

    @property
    def t_wb_c(self) -> float:
        return wet_bulb(self.t_c, self.W, self.p)

    @property
    def v_m3_kg(self) -> float:
        return specific_volume(self.t_c, self.W, self.p)

    @property
    def w_g_kg(self) -> float:
        return self.W * 1000.0


# ============================================================================
# Процессы
# ============================================================================

def mix_streams(streams: List[Tuple[AirState, float]],
                p: float = P_ATM) -> AirState:
    """Смешение n потоков влажного воздуха.

    streams — список (AirState, mass_flow_kg_s).
    Расход может задаваться и в кг/с, и в кг/ч — лишь бы одни единицы.

    Возвращает результирующее состояние. Применяется формула баланса
    сухого воздуха и воды:
        m_total = Σ m_i
        W_mix = Σ (m_i · W_i) / m_total
        H_mix = Σ (m_i · H_i) / m_total
        T_mix = из (H_mix, W_mix)
    """
    if not streams:
        raise ValueError("mix_streams: пустой список потоков")
    total = sum(m for _, m in streams)
    if total <= 0:
        # Нечего смешивать — возвращаем первый
        return streams[0][0]
    W_mix = sum(s.W * m for s, m in streams) / total
    H_mix = sum(s.h_kj_kg * m for s, m in streams) / total
    t_mix = temperature_from_h_w(H_mix, W_mix)
    return AirState(t_c=t_mix, W=W_mix, p=p)


def heat(state: AirState, t_out: float) -> AirState:
    """Сухой нагрев (W = const). Калорифер без увлажнения."""
    if t_out < state.t_c:
        # Нагревом нельзя охлаждать
        t_out = state.t_c
    return AirState(t_c=t_out, W=state.W, p=state.p)


def cool(state: AirState, t_out: float) -> AirState:
    """Охлаждение поверхностным охладителем.

    Если t_out > t_dp(state) — сухое охлаждение, W = const.
    Если t_out ≤ t_dp(state) — конденсация: W пересчитывается так,
    чтобы воздух на выходе был насыщен при t_out (φ = 100%).

    Возвращает выходное состояние. Для практичного расчёта с bypass
    factor используйте `cool_dehumidify`.
    """
    if t_out >= state.t_c:
        return state
    if t_out > state.t_dp_c:
        return AirState(t_c=t_out, W=state.W, p=state.p)
    # Конденсация — точка пересекла линию насыщения
    W_out = humidity_ratio_from_rh(t_out, 1.0, state.p)
    return AirState(t_c=t_out, W=W_out, p=state.p)


def cool_dehumidify(state: AirState, t_adp: float,
                     bypass_factor: float = 0.15) -> AirState:
    """Реальный поверхностный охладитель с bypass factor.

    Модель ASHRAE: часть потока (BF) проходит через теплообменник без
    контакта с поверхностью и сохраняет исходное состояние; оставшаяся
    часть (1 − BF) приводится к состоянию ADP (apparatus dew point) —
    точка насыщения на поверхности.

    Параметры
    ---------
    state         : вход в охладитель
    t_adp         : температура поверхности (apparatus dew point), °C.
                    Типично 7-12°C для фанкойлов и AHU.
    bypass_factor : 0..1, доля «обходного» потока. Типично 0.10-0.20.

    Возвращает выходное состояние (смесь BF·state + (1−BF)·sat(t_adp)).
    """
    bf = max(0.0, min(1.0, bypass_factor))
    if t_adp >= state.t_c:
        return state
    W_adp_sat = humidity_ratio_from_rh(t_adp, 1.0, state.p)
    # Если входной воздух суше, чем насыщенная ADP-точка (т.е. T_adp выше
    # точки росы входа), конденсация физически невозможна — это сухой режим.
    # ADP-модель в чистом виде дала бы прирост W, что нефизично.
    if W_adp_sat >= state.W:
        return AirState(t_c=t_adp + bf * (state.t_c - t_adp),
                         W=state.W, p=state.p)
    adp = AirState(t_c=t_adp, W=W_adp_sat, p=state.p)
    return mix_streams([(state, bf), (adp, 1.0 - bf)], p=state.p)


def humidify_steam(state: AirState, W_out: float) -> AirState:
    """Пароувлажнение: W растёт, t ≈ const.

    Технически вместе с паром поступает небольшое количество явной
    теплоты (пар обычно 100-110°C), но в инженерных расчётах принимают
    приближение T = const, что даёт ошибку < 0.5°C при штатной нагрузке.
    """
    if W_out <= state.W:
        return state
    return AirState(t_c=state.t_c, W=W_out, p=state.p)


def humidify_adiabatic(state: AirState, efficiency: float = 0.85
                       ) -> AirState:
    """Адиабатическое увлажнение (форсунки, сотовое).

    Процесс идёт вдоль линии Twb = const на i-d диаграмме (точнее, h ≈ const,
    с лёгкой коррекцией на теплоту жидкой воды). Эффективность η — доля
    приближения к насыщению:
        W_out = W_in + η · (W_sat(Twb) − W_in)
    """
    eta = max(0.0, min(1.0, efficiency))
    t_wb = state.t_wb_c
    # Максимально достижимое W — насыщение при Twb
    W_sat = humidity_ratio_from_rh(t_wb, 1.0, state.p)
    W_out = state.W + eta * (W_sat - state.W)
    # Температура падает (адиабат): t ≈ t_wb + (1-η)·(t_in - t_wb)
    t_out = t_wb + (1.0 - eta) * (state.t_c - t_wb)
    return AirState(t_c=t_out, W=W_out, p=state.p)


def heat_recovery(outdoor: AirState, extract: AirState,
                  efficiency_t: float,
                  efficiency_w: float = 0.0) -> AirState:
    """Воздух наружный после рекуператора.

    Параметры
    ---------
    outdoor       : наружный воздух (вход в рекуператор)
    extract       : вытяжной воздух из помещения (другой поток рекуператора)
    efficiency_t  : температурная эффективность ηt ∈ [0..1].
                    Пластинчатый: 0.50-0.65, роторный: 0.70-0.85.
    efficiency_w  : эффективность по влаге ηw. Для пластинчатого = 0,
                    для гигроскопичного ротора 0.60-0.75.

    Возвращает состояние НАРУЖНОГО воздуха после рекуператора.
    """
    eta_t = max(0.0, min(1.0, efficiency_t))
    eta_w = max(0.0, min(1.0, efficiency_w))
    t_out = outdoor.t_c + eta_t * (extract.t_c - outdoor.t_c)
    W_out = outdoor.W + eta_w * (extract.W - outdoor.W)
    return AirState(t_c=t_out, W=W_out, p=outdoor.p)


# ============================================================================
# Тепловые мощности процессов
# ============================================================================

def air_power_kw(mass_flow_kg_s: float,
                  state_in: AirState,
                  state_out: AirState) -> float:
    """Мощность процесса по разности энтальпий, кВт.

        Q = m · (H_out - H_in)

    Положительная — нагрев / увлажнение, отрицательная — охлаждение.
    """
    return mass_flow_kg_s * (state_out.h_kj_kg - state_in.h_kj_kg)


def mass_flow_from_volume(L_m3_h: float, state: AirState) -> float:
    """Массовый расход сухого воздуха [кг/с] из объёмного [м³/ч]
    и состояния воздуха."""
    if L_m3_h <= 0 or state.v_m3_kg <= 0:
        return 0.0
    return (L_m3_h / 3600.0) / state.v_m3_kg


def latent_power_kw(mass_flow_kg_s: float,
                     W_in: float, W_out: float) -> float:
    """Скрытая часть мощности процесса, кВт.

        Q_lat = m · ΔW · h_fg0   ≈ m · ΔW · 2501

    Используется для разделения нагрузки охладителя на явную/скрытую.
    """
    return mass_flow_kg_s * (W_out - W_in) * H_FG_0


def sensible_power_kw(mass_flow_kg_s: float,
                       t_in: float, t_out: float, W_avg: float = 0.0) -> float:
    """Явная часть мощности процесса, кВт.

        Q_sens = m · c_p · ΔT,   c_p = c_pa + W·c_pv
    """
    cp = C_PA + W_avg * C_PV
    return mass_flow_kg_s * cp * (t_out - t_in)


# ============================================================================
# Вспомогательное
# ============================================================================

def to_g_kg(W: float) -> float:
    """W [кг/кг] → w [г/кг]."""
    return W * 1000.0


def from_g_kg(w: float) -> float:
    """w [г/кг] → W [кг/кг]."""
    return w / 1000.0
