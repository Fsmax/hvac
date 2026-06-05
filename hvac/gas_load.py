# -*- coding: utf-8 -*-
"""Расчёт потребности в природном газе для технических условий (ТУ).

Считает часовой / суточный / месячный / годовой расход газа котельной
«от мощности котла» и формирует одностраничное письмо-расчёт в PDF
(формат «Направляем расчёт потребности в топливе газоснабжения…»).

Методика
--------
Расход газа на ОДИН котёл от номинальной мощности::

    b = P / (Qнр · η)                  [м³/ч]

Расходы котельной::

    B_час = Σ (n_i · b_i)              [м³/ч]   — часовой
    B_сут = B_час · T · K              [м³/сут] — суточный
    B_мес = B_сут · D_мес             [м³/мес] — месячный
    B_год = B_час · T · K · D_отоп    [м³/год] — годовой

где
    P      — единичная мощность котла, кВт;
    Qнр    — низшая теплота сгорания газа, кВт·ч/м³ (8000 ккал/м³ ≈ 9,30);
    η      — КПД котла (по паспорту, обычно 0,92);
    T      — число часов работы в сутки (24);
    K      — коэффициент использования (загрузки), обычно 0,85;
    D_мес  — расчётное число суток в месяце (30);
    D_отоп — продолжительность отопительного периода, сут (≈130).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import List, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from hvac.project import HVACProject


# ============================================================================
# Константы и значения по умолчанию
# ============================================================================

# Переводной коэффициент: 1 кВт·ч = 859,845 ккал.
KCAL_PER_KWH: float = 859.845

# Низшая теплота сгорания природного газа (Qнр). В отрасли задаётся в ккал/м³;
# 8000 ккал/м³ ÷ 859,845 ≈ 9,30 кВт·ч/м³ — типовое расчётное значение для
# природного газа (КМК/ШНҚ, СП). Задаётся параметром.
NATURAL_GAS_LHV_KCAL_M3: float = 8000.0
NATURAL_GAS_LHV_KWH_M3: float = NATURAL_GAS_LHV_KCAL_M3 / KCAL_PER_KWH


def kcal_to_kwh(kcal_m3: float) -> float:
    """ккал/м³ → кВт·ч/м³."""
    return kcal_m3 / KCAL_PER_KWH


def kwh_to_kcal(kwh_m3: float) -> float:
    """кВт·ч/м³ → ккал/м³."""
    return kwh_m3 * KCAL_PER_KWH

DEFAULT_EFFICIENCY: float = 0.92        # КПД котла, η
DEFAULT_HOURS_PER_DAY: float = 24.0     # часов работы в сутки, T
DEFAULT_LOAD_FACTOR: float = 0.85       # коэффициент использования, K
DEFAULT_DAYS_PER_MONTH: float = 30.0    # суток в месяце, D_мес
DEFAULT_HEATING_DAYS: float = 130.0     # отопительный период, сут, D_отоп


# ============================================================================
# Модель данных
# ============================================================================

@dataclass
class BoilerGroup:
    """Группа одинаковых газовых котлов."""
    power_kw: float                     # единичная мощность котла, кВт
    count: int                          # количество, шт
    name: str = ""                      # имя/марка (для справки)
    hourly_per_unit_m3h: float = 0.0    # расход на один котёл, м³/ч (расчёт)

    @property
    def hourly_group_m3h(self) -> float:
        """Часовой расход всей группы, м³/ч."""
        return self.count * self.hourly_per_unit_m3h


@dataclass
class GasLoadResult:
    """Результат расчёта потребности в газе."""
    boilers: List[BoilerGroup]
    # Параметры расчёта
    lhv_kwh_m3: float
    efficiency: float
    hours_per_day: float
    load_factor: float
    days_per_month: float
    heating_days: float
    # Результаты (точные значения)
    lhv_kcal_m3: float = 0.0
    total_power_kw: float = 0.0
    hourly_m3h: float = 0.0
    daily_m3day: float = 0.0
    monthly_m3month: float = 0.0
    annual_m3year: float = 0.0

    @property
    def annual_mln_m3(self) -> float:
        """Годовой расход, млн м³/год."""
        return self.annual_m3year / 1_000_000.0


# ============================================================================
# Расчёт
# ============================================================================

def compute_gas_load(
    boilers: List[BoilerGroup],
    *,
    lhv_kwh_m3: float = NATURAL_GAS_LHV_KWH_M3,
    efficiency: float = DEFAULT_EFFICIENCY,
    hours_per_day: float = DEFAULT_HOURS_PER_DAY,
    load_factor: float = DEFAULT_LOAD_FACTOR,
    days_per_month: float = DEFAULT_DAYS_PER_MONTH,
    heating_days: float = DEFAULT_HEATING_DAYS,
) -> GasLoadResult:
    """Считает расход газа котельной «от мощности котла».

    Параметры
    ---------
    boilers       : список групп котлов (мощность + количество).
    lhv_kwh_m3    : Qнр газа, кВт·ч/м³.
    efficiency    : КПД котла η, 0..1.
    hours_per_day : часов работы в сутки T.
    load_factor   : коэффициент использования K.
    days_per_month: суток в месяце D_мес.
    heating_days  : длительность отопительного периода D_отоп, сут.
    """
    denom = lhv_kwh_m3 * efficiency
    if denom <= 0:
        raise ValueError("Qнр·η должно быть > 0 (проверьте теплоту сгорания и КПД).")
    if not boilers:
        raise ValueError("Нет газовых котлов для расчёта.")

    hourly = 0.0
    total_power = 0.0
    for b in boilers:
        b.hourly_per_unit_m3h = b.power_kw / denom
        hourly += b.count * b.hourly_per_unit_m3h
        total_power += b.count * b.power_kw

    daily = hourly * hours_per_day * load_factor
    monthly = daily * days_per_month
    annual = daily * heating_days

    return GasLoadResult(
        boilers=boilers,
        lhv_kwh_m3=lhv_kwh_m3,
        efficiency=efficiency,
        hours_per_day=hours_per_day,
        load_factor=load_factor,
        days_per_month=days_per_month,
        heating_days=heating_days,
        lhv_kcal_m3=lhv_kwh_m3 * KCAL_PER_KWH,
        total_power_kw=total_power,
        hourly_m3h=hourly,
        daily_m3day=daily,
        monthly_m3month=monthly,
        annual_m3year=annual,
    )


def gas_boilers_from_project(project: "HVACProject") -> List[BoilerGroup]:
    """Собирает газовые котлы проекта в список BoilerGroup.

    Берёт источники тепла с топливом «gas» (или типом boiler_gas*),
    у которых задана единичная мощность и количество (ручной подбор).
    """
    out: List[BoilerGroup] = []
    for name, h in project.heating_systems.items():
        is_gas = (getattr(h, "fuel", "") == "gas"
                  or str(getattr(h, "system_type", "")).startswith("boiler_gas"))
        power = float(getattr(h, "design_capacity_kw", 0.0) or 0.0)
        count = int(getattr(h, "unit_count", 0) or 0)
        if not is_gas or power <= 0 or count <= 0:
            continue
        out.append(BoilerGroup(power_kw=power, count=count, name=h.name))
    return out


def project_efficiency(project: "HVACProject") -> float:
    """КПД первого газового котла проекта (для единой формулы в письме)."""
    for h in project.heating_systems.values():
        is_gas = (getattr(h, "fuel", "") == "gas"
                  or str(getattr(h, "system_type", "")).startswith("boiler_gas"))
        eff = float(getattr(h, "efficiency", 0.0) or 0.0)
        if is_gas and eff > 0:
            return eff
    return DEFAULT_EFFICIENCY


# ============================================================================
# Форматирование чисел (русский стиль: пробел-разряд, запятая-дробь)
# ============================================================================

_NBSP = " "  # неразрывный пробел — разделитель разрядов в PDF


def _fmt_int(x: float) -> str:
    """Целое с разделителем разрядов: 1463904 → '1 463 904'."""
    return f"{round(x):,}".replace(",", _NBSP)


def _fmt_g(x: float) -> str:
    """Число без лишних нулей, запятая как дробь: 0.85 → '0,85', 24.0 → '24'."""
    if abs(x - round(x)) < 1e-9:
        return str(int(round(x)))
    return f"{x:g}".replace(".", ",")


def _fmt_dec(x: float, n: int = 2) -> str:
    """Число с фиксированными знаками и запятой: 9.304 → '9,30'."""
    return f"{x:.{n}f}".replace(".", ",")


def _fmt_mln(x: float) -> str:
    """Миллионы с двумя знаками: 1463904 → '1,46'."""
    return f"{x / 1_000_000.0:.2f}".replace(".", ",")


# ============================================================================
# PDF: одностраничное письмо-расчёт
# ============================================================================

def export_gas_load_pdf(
    path: str,
    result: GasLoadResult,
    *,
    object_name: str = "",
    boiler_label: str = "газовых напольных котлов",
    signatory: str = "ГИП",
    signatory_name: str = "",
    header_lines: Optional[List[str]] = None,
    show_date: bool = True,
) -> None:
    """Создаёт PDF-письмо «Расчёт потребности в топливе газоснабжения».

    Параметры
    ---------
    path           : путь к выходному PDF.
    result         : результат compute_gas_load().
    object_name    : наименование объекта.
    boiler_label   : подпись типа котлов («газовых напольных котлов»).
    signatory      : должность подписанта («ГИП»).
    signatory_name : Ф.И.О. подписанта (печатается справа от подписи).
    header_lines   : строки шапки (адресат / организация); None — без шапки.
    show_date      : печатать дату внизу.
    """
    try:
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.units import cm
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.lib.enums import TA_JUSTIFY, TA_RIGHT
        from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
    except ImportError:
        raise RuntimeError("Не установлен reportlab. "
                           "Выполните: pip install reportlab")

    # Регистрация кириллического шрифта (общая утилита из io_pdf).
    from hvac.io_pdf import _register_fonts
    font_name, font_bold = _register_fonts()

    styles = getSampleStyleSheet()
    style_body = ParagraphStyle(
        "GasBody", parent=styles["Normal"], fontName=font_name,
        fontSize=12, leading=18, alignment=TA_JUSTIFY, spaceAfter=4,
    )
    style_item = ParagraphStyle(
        "GasItem", parent=style_body, leftIndent=0.8 * cm, spaceAfter=2,
    )
    style_small = ParagraphStyle(
        "GasSmall", parent=styles["Normal"], fontName=font_name,
        fontSize=9, leading=12, alignment=TA_JUSTIFY,
    )
    style_right = ParagraphStyle(
        "GasRight", parent=style_body, alignment=TA_RIGHT,
    )

    r = result
    el = []

    # --- Шапка (адресат / организация) ---
    if header_lines:
        for line in header_lines:
            el.append(Paragraph(line, style_right))
        el.append(Spacer(1, 0.8 * cm))

    # --- Вводная строка ---
    obj = object_name or "объекту"
    el.append(Paragraph(
        f"Направляем расчёт потребности в топливе газоснабжения по объекту: "
        f"<b>{obj}</b>", style_body))
    el.append(Spacer(1, 0.5 * cm))

    # --- К установке принято ---
    el.append(Paragraph("К установке принято:", style_body))
    for g in r.boilers:
        suffix = f" ({g.name})" if g.name else ""
        el.append(Paragraph(
            f"– {boiler_label} {_fmt_g(g.power_kw)} кВт – {g.count} шт{suffix}",
            style_item))
    el.append(Spacer(1, 0.4 * cm))

    el.append(Paragraph(
        "Согласно паспортных данных отопительного котла и режима работы, "
        "расход газа составляет:", style_body))
    el.append(Spacer(1, 0.2 * cm))

    # --- Расчётные строки (печатаемая арифметика «бьётся» по округлённым
    #     значениям, чтобы инженер мог проверить умножение на бумаге) ---
    b_disp = [round(g.power_kw / (r.lhv_kwh_m3 * r.efficiency)) for g in r.boilers]
    hourly_int = sum(g.count * b for g, b in zip(r.boilers, b_disp))
    daily_int = round(hourly_int * r.hours_per_day * r.load_factor)
    monthly_int = round(daily_int * r.days_per_month)
    annual_int = round(hourly_int * r.hours_per_day
                       * r.load_factor * r.heating_days)

    # Ядро часового выражения: для одной группы — «N × b», иначе сумма групп.
    if len(r.boilers) == 1:
        core = f"{r.boilers[0].count} × {_fmt_int(b_disp[0])}"
    else:
        core = " + ".join(f"{g.count} × {_fmt_int(b)}"
                          for g, b in zip(r.boilers, b_disp))
    # Для суточного/годового при нескольких группах опираемся на сумму.
    daily_core = core if len(r.boilers) == 1 else _fmt_int(hourly_int)

    hh = _fmt_g(r.hours_per_day)
    kk = _fmt_g(r.load_factor)
    dm = _fmt_g(r.days_per_month)
    dh = _fmt_g(r.heating_days)

    el.append(Paragraph(
        f"– Часовой – {core} = <b>{_fmt_int(hourly_int)}</b> м³/час",
        style_item))
    el.append(Paragraph(
        f"– Суточный – {daily_core} × {hh} × {kk} = "
        f"<b>{_fmt_int(daily_int)}</b> м³/сут", style_item))
    el.append(Paragraph(
        f"– Месячный – {_fmt_int(daily_int)} × {dm} = "
        f"<b>{_fmt_int(monthly_int)}</b> м³/мес", style_item))
    annual_txt = f"{_fmt_int(annual_int)} м³/год"
    if annual_int >= 1_000_000:
        annual_txt = f"{_fmt_int(annual_int)} м³/год (≈ {_fmt_mln(annual_int)} млн)"
    el.append(Paragraph(
        f"– Годовой – {daily_core} × {hh} × {kk} × {dh} = "
        f"<b>{annual_txt}</b>", style_item))
    el.append(Spacer(1, 0.5 * cm))

    # --- Методическая сноска ---
    lhv_kcal = r.lhv_kcal_m3 or (r.lhv_kwh_m3 * KCAL_PER_KWH)
    el.append(Paragraph(
        "Расход газа на котёл принят от номинальной мощности: "
        "B = P / (Qнр·η), где Qнр = "
        f"{_fmt_int(lhv_kcal)} ккал/м³ "
        f"({_fmt_dec(r.lhv_kwh_m3)} кВт·ч/м³) — низшая теплота "
        f"сгорания природного газа, η = {_fmt_g(r.efficiency)} — КПД котла; "
        f"коэффициент использования K = {kk}, продолжительность "
        f"отопительного периода {dh} сут.", style_small))
    el.append(Spacer(1, 1.2 * cm))

    # --- Подпись ---
    sign_line = f"{signatory}: " + "_" * 28
    if signatory_name:
        sign_line += f"  {signatory_name}"
    el.append(Paragraph(sign_line, style_body))

    if show_date:
        el.append(Spacer(1, 0.6 * cm))
        el.append(Paragraph(
            datetime.now().strftime("%d.%m.%Y"), style_small))

    doc = SimpleDocTemplate(
        path, pagesize=A4,
        leftMargin=2.5 * cm, rightMargin=2 * cm,
        topMargin=2.5 * cm, bottomMargin=2 * cm,
        title="Расчёт потребности в газе",
        author="HVAC Calculator",
    )
    doc.build(el)


def export_project_gas_load_pdf(
    project: "HVACProject",
    path: str,
    *,
    lhv_kwh_m3: float = NATURAL_GAS_LHV_KWH_M3,
    load_factor: float = DEFAULT_LOAD_FACTOR,
    hours_per_day: float = DEFAULT_HOURS_PER_DAY,
    days_per_month: float = DEFAULT_DAYS_PER_MONTH,
    heating_days: float = DEFAULT_HEATING_DAYS,
    efficiency: Optional[float] = None,
    **pdf_kwargs,
) -> GasLoadResult:
    """Считает расход газа по газовым котлам проекта и пишет письмо-расчёт.

    Возвращает GasLoadResult. Бросает RuntimeError, если в проекте нет
    газовых котлов с заданной мощностью и количеством.
    """
    boilers = gas_boilers_from_project(project)
    if not boilers:
        raise RuntimeError(
            "В проекте нет газовых котлов с заданной мощностью и количеством. "
            "Задайте в панели «Оборудование» источник тепла с топливом «газ», "
            "единичной мощностью (кВт) и количеством (шт).")

    eff = efficiency if efficiency is not None else project_efficiency(project)
    result = compute_gas_load(
        boilers,
        lhv_kwh_m3=lhv_kwh_m3,
        efficiency=eff,
        hours_per_day=hours_per_day,
        load_factor=load_factor,
        days_per_month=days_per_month,
        heating_days=heating_days,
    )
    object_name = pdf_kwargs.pop("object_name", None)
    if object_name is None:
        object_name = getattr(project.params, "project_name", "") or ""
    export_gas_load_pdf(path, result, object_name=object_name, **pdf_kwargs)
    return result
