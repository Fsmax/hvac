# -*- coding: utf-8 -*-
"""Общие построители данных для пояснительной записки (PDF и DOCX).

io_pdf.py и io_docx.py печатают одну и ту же записку в двух форматах.
Чтобы разделы не расходились, СОДЕРЖИМОЕ таблиц (строки-списки строк)
строится здесь, а экспортёры занимаются только вёрсткой.

Все таблицы возвращаются как ``List[List[str]]`` с шапкой в первой
строке; ``None`` — если данных нет (раздел/таблицу не печатать).
"""

from __future__ import annotations

from collections import defaultdict
from typing import Dict, List, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from hvac.project import HVACProject
    from hvac.energy import EnergyPassport

# Больше этого числа помещений — по-помещенные таблицы не печатаются
# (остаётся свод по уровням), чтобы записка не разбухала на тысячи строк.
ROOM_TABLE_LIMIT = 200


def fmt(x: float, dec: int = 0) -> str:
    """Число с пробелом-разделителем тысяч: 12 345 / 12 345.6."""
    return f"{x:,.{dec}f}".replace(",", " ")


def _room_sort_key(sp) -> tuple:
    """Сортировка помещений: уровень, затем номер (числа — по значению)."""
    num = (sp.number or "").strip()
    try:
        return (sp.level or "", 0, float(num.replace(",", ".")), "")
    except ValueError:
        return (sp.level or "", 1, 0.0, num)


def _multi_level(project: "HVACProject") -> bool:
    return len({s.level for s in project.spaces}) > 1


class SectionNumberer:
    """Сквозная нумерация печатаемых разделов — без дыр вида «7 → 11»."""

    def __init__(self) -> None:
        self._n = 0

    def title(self, text: str) -> str:
        self._n += 1
        return f"{self._n}. {text}"


# ============================================================================
# Теплопотери / теплопоступления
# ============================================================================

def heat_loss_level_rows(project: "HVACProject") -> Optional[List[List[str]]]:
    """Свод теплопотерь по уровням (+ ИТОГО)."""
    loaded = [s for s in project.spaces if s.heat_loss_w > 0]
    if not loaded:
        return None
    by_level: Dict[str, dict] = defaultdict(
        lambda: {"n": 0, "area": 0.0, "q": 0.0})
    for s in loaded:
        by_level[s.level]["n"] += 1
        by_level[s.level]["area"] += s.area_m2
        by_level[s.level]["q"] += s.heat_loss_w
    total = sum(s.heat_loss_w for s in loaded)
    total_area = sum(s.area_m2 for s in loaded)
    rows = [["Уровень", "Кол-во", "Площадь, м²", "Q, кВт", "Уд., Вт/м²"]]
    for lvl in sorted(by_level.keys()):
        d = by_level[lvl]
        rows.append([lvl, str(d["n"]), fmt(d["area"]),
                     f"{d['q'] / 1000:.1f}",
                     f"{d['q'] / max(d['area'], 1):.1f}"])
    rows.append(["ИТОГО", str(len(loaded)), fmt(total_area),
                 f"{total / 1000:.1f}", f"{total / max(total_area, 1):.1f}"])
    return rows


def heat_loss_room_rows(project: "HVACProject") -> Optional[List[List[str]]]:
    """По-помещенная таблица теплопотерь (+ ИТОГО). None — нет данных
    или помещений больше ROOM_TABLE_LIMIT."""
    loaded = [s for s in project.spaces if s.heat_loss_w > 0]
    if not loaded or len(loaded) > ROOM_TABLE_LIMIT:
        return None
    multi = _multi_level(project)
    head = ["№", "Наименование", "S, м²", "tв, °C", "Q, Вт", "Уд., Вт/м²"]
    if multi:
        head.insert(2, "Уровень")
    rows = [head]
    for s in sorted(loaded, key=_room_sort_key):
        r = [s.number, (s.name or "").replace("\n", " ")[:60],
             fmt(s.area_m2), f"{s.t_in_heat:.0f}",
             fmt(s.heat_loss_w), f"{s.heat_loss_w / max(s.area_m2, 0.1):.0f}"]
        if multi:
            r.insert(2, s.level)
        rows.append(r)
    total = sum(s.heat_loss_w for s in loaded)
    total_area = sum(s.area_m2 for s in loaded)
    t = ["ИТОГО", f"{len(loaded)} помещ.", fmt(total_area), "",
         fmt(total), f"{total / max(total_area, 1):.0f}"]
    if multi:
        t.insert(2, "")
    rows.append(t)
    return rows


def heat_gain_level_rows(project: "HVACProject") -> Optional[List[List[str]]]:
    """Свод теплопоступлений по уровням (+ ИТОГО)."""
    loaded = [s for s in project.spaces if s.heat_gain_w > 0]
    if not loaded:
        return None
    by_level: Dict[str, dict] = defaultdict(
        lambda: {"n": 0, "area": 0.0, "q": 0.0, "sens": 0.0, "lat": 0.0})
    for s in loaded:
        d = by_level[s.level]
        d["n"] += 1
        d["area"] += s.area_m2
        d["q"] += s.heat_gain_w
        d["sens"] += s.heat_gain_sensible_w
        d["lat"] += s.heat_gain_latent_w
    rows = [["Уровень", "Кол-во", "Площадь, м²", "Q, кВт",
             "Явная, кВт", "Скрытая, кВт", "Уд., Вт/м²"]]
    for lvl in sorted(by_level.keys()):
        d = by_level[lvl]
        rows.append([lvl, str(d["n"]), fmt(d["area"]),
                     f"{d['q'] / 1000:.1f}", f"{d['sens'] / 1000:.1f}",
                     f"{d['lat'] / 1000:.1f}",
                     f"{d['q'] / max(d['area'], 1):.1f}"])
    total = sum(s.heat_gain_w for s in loaded)
    area = sum(s.area_m2 for s in loaded)
    rows.append(["ИТОГО", str(len(loaded)), fmt(area),
                 f"{total / 1000:.1f}",
                 f"{sum(s.heat_gain_sensible_w for s in loaded) / 1000:.1f}",
                 f"{sum(s.heat_gain_latent_w for s in loaded) / 1000:.1f}",
                 f"{total / max(area, 1):.1f}"])
    return rows


def heat_gain_room_rows(project: "HVACProject") -> Optional[List[List[str]]]:
    """По-помещенная таблица теплопоступлений (+ ИТОГО)."""
    loaded = [s for s in project.spaces if s.heat_gain_w > 0]
    if not loaded or len(loaded) > ROOM_TABLE_LIMIT:
        return None
    multi = _multi_level(project)
    head = ["№", "Наименование", "S, м²", "Q, Вт",
            "Явная, Вт", "Скрытая, Вт", "Уд., Вт/м²"]
    if multi:
        head.insert(2, "Уровень")
    rows = [head]
    for s in sorted(loaded, key=_room_sort_key):
        r = [s.number, (s.name or "").replace("\n", " ")[:60],
             fmt(s.area_m2), fmt(s.heat_gain_w),
             fmt(s.heat_gain_sensible_w), fmt(s.heat_gain_latent_w),
             f"{s.heat_gain_w / max(s.area_m2, 0.1):.0f}"]
        if multi:
            r.insert(2, s.level)
        rows.append(r)
    total = sum(s.heat_gain_w for s in loaded)
    area = sum(s.area_m2 for s in loaded)
    t = ["ИТОГО", f"{len(loaded)} помещ.", fmt(area), fmt(total),
         fmt(sum(s.heat_gain_sensible_w for s in loaded)),
         fmt(sum(s.heat_gain_latent_w for s in loaded)),
         f"{total / max(area, 1):.0f}"]
    if multi:
        t.insert(2, "")
    rows.append(t)
    return rows


# ============================================================================
# Вентиляция: таблица воздухообменов и сводка по системам
# ============================================================================

def air_exchange_room_rows(project: "HVACProject") -> Optional[List[List[str]]]:
    """Таблица воздухообменов по помещениям (+ ИТОГО) — основная таблица
    раздела «Вентиляция» для экспертизы."""
    spaces = [s for s in project.spaces
              if s.supply_m3h > 0 or s.exhaust_m3h > 0 or s.hood_m3h > 0]
    if not spaces or len(spaces) > ROOM_TABLE_LIMIT:
        return None
    multi = _multi_level(project)
    any_hood = any(s.hood_m3h > 0 for s in spaces)
    any_sys = any(s.vent_system_supply or s.vent_system_exhaust
                  for s in spaces)
    head = ["№", "Наименование", "S, м²", "V, м³", "Люди",
            "Приток, м³/ч", "Вытяжка, м³/ч", "Кр. пр., 1/ч", "Кр. выт., 1/ч"]
    if any_hood:
        head.insert(7, "Зонт, м³/ч")
    if multi:
        head.insert(2, "Уровень")
    if any_sys:
        head.append("Системы")
    rows = [head]
    for s in sorted(spaces, key=_room_sort_key):
        vol = max(s.volume_m3, 0.1)
        r = [s.number, (s.name or "").replace("\n", " ")[:60],
             fmt(s.area_m2), fmt(s.volume_m3),
             (f"{s.occupancy_people:.0f}" if s.occupancy_people else "—"),
             fmt(s.supply_m3h), fmt(s.exhaust_m3h),
             f"{s.supply_m3h / vol:.1f}", f"{s.exhaust_m3h / vol:.1f}"]
        if any_hood:
            r.insert(7, fmt(s.hood_m3h) if s.hood_m3h else "—")
        if multi:
            r.insert(2, s.level)
        if any_sys:
            sup, exh = s.vent_system_supply, s.vent_system_exhaust
            r.append(sup if sup == exh else
                     " / ".join(x or "—" for x in (sup, exh)))
        rows.append(r)
    sum_s = sum(s.supply_m3h for s in spaces)
    sum_e = sum(s.exhaust_m3h for s in spaces)
    t = ["ИТОГО", f"{len(spaces)} помещ.",
         fmt(sum(s.area_m2 for s in spaces)),
         fmt(sum(s.volume_m3 for s in spaces)),
         fmt(sum(s.occupancy_people for s in spaces)),
         fmt(sum_s), fmt(sum_e), "", ""]
    if any_hood:
        t.insert(7, fmt(sum(s.hood_m3h for s in spaces)))
    if multi:
        t.insert(2, "")
    if any_sys:
        t.append("")
    rows.append(t)
    return rows


def vent_system_summary_rows(project: "HVACProject"
                             ) -> Optional[List[List[str]]]:
    """Сводка расходов по вентиляционным системам (если привязки назначены)."""
    agg: Dict[str, dict] = defaultdict(
        lambda: {"n": 0, "supply": 0.0, "exhaust": 0.0, "hood": 0.0})
    for s in project.spaces:
        if s.vent_system_supply and s.supply_m3h > 0:
            agg[s.vent_system_supply]["supply"] += s.supply_m3h
            agg[s.vent_system_supply]["n"] += 1
        if s.vent_system_exhaust and (s.exhaust_m3h > 0 or s.hood_m3h > 0):
            agg[s.vent_system_exhaust]["exhaust"] += s.exhaust_m3h
            agg[s.vent_system_exhaust]["hood"] += s.hood_m3h
            if not (s.vent_system_supply == s.vent_system_exhaust
                    and s.supply_m3h > 0):
                agg[s.vent_system_exhaust]["n"] += 1
    if not agg:
        return None
    any_hood = any(d["hood"] > 0 for d in agg.values())
    head = ["Система", "Помещений", "Приток, м³/ч", "Вытяжка, м³/ч"]
    if any_hood:
        head.append("Зонты, м³/ч")
    rows = [head]
    for name in sorted(agg.keys()):
        d = agg[name]
        r = [name, str(d["n"]), fmt(d["supply"]), fmt(d["exhaust"])]
        if any_hood:
            r.append(fmt(d["hood"]))
        rows.append(r)
    t = ["ИТОГО", "",
         fmt(sum(d["supply"] for d in agg.values())),
         fmt(sum(d["exhaust"] for d in agg.values()))]
    if any_hood:
        t.append(fmt(sum(d["hood"] for d in agg.values())))
    rows.append(t)
    return rows


def air_balance_note(project: "HVACProject") -> str:
    """Строка воздушного баланса здания."""
    sum_s = sum(s.supply_m3h for s in project.spaces)
    sum_e = sum(s.exhaust_m3h + s.hood_m3h for s in project.spaces)
    diff = sum_s - sum_e
    pct = diff / sum_e * 100.0 if sum_e > 0 else 0.0
    diff_str = f"{diff:+,.0f}".replace(",", " ")
    return (f"Воздушный баланс здания: приток {fmt(sum_s)} м³/ч, "
            f"вытяжка (с зонтами) {fmt(sum_e)} м³/ч, "
            f"дисбаланс {diff_str} м³/ч ({pct:+.1f}%).")


# ============================================================================
# Энергоэффективность (блок по профилю норм)
# ============================================================================

def energy_section_data(ep: "EnergyPassport", profile: Dict[str, str]) -> Dict:
    """Содержимое раздела «Энергоэффективность» по профилю норм.

    Возвращает {"heading", "intro", "kv_main", "kv_annual",
    "verdict", "verdict_ok", "notes"}.

    Профиль УзР: основное сравнение — удельная расчётная мощность
    отопления+вентиляции q против норматива q_ov ШНҚ 2.01.18-24 (Вт/м²);
    класс энергоэффективности СП 50 не печатается. Профиль РФ — прежний
    паспорт по СП 50.13330 Прил. Г с классом.
    """
    from hvac.catalogs.shnq_energy import shnq_category_title

    uz = profile.get("energy_primary") == "SHNQ"
    season_src = ("по климату города" if ep.season_exact
                  else "оценка по ГСОП")
    dd_src = ("климат города, ШНҚ 2.01.01-22 Табл.4, интерп. на ≤10°C"
              if ep.dd_exact else "приближение по ГСОП")

    kv_main: List[List[str]] = [
        ["Тип здания (автоопределение по помещениям)", ep.building_type],
        ["Отапливаемая площадь, м²", fmt(ep.total_area_m2)],
        ["Отапливаемый объём, м³", fmt(ep.total_volume_m3)],
        ["Этажность (по уровням)", str(ep.n_floors)],
        ["Длительность отопит. сезона, сут "
         f"({season_src})", f"{ep.z_heating_days:.0f}"],
        ["Средняя tн за сезон, °C", f"{ep.t_avg_heating:.1f}"],
        ["Q расчётная отопления, кВт", f"{ep.q_peak_heating_w / 1000:.1f}"],
        ["Q расчётная нагрева вентиляции, кВт",
         f"{ep.q_peak_ventilation_heating_w / 1000:.1f}"],
        ["Q расчётная охлаждения, кВт", f"{ep.q_peak_cooling_w / 1000:.1f}"],
    ]
    if ep.q_peak_dhw_w > 0:
        kv_main.append(["Q расчётная ГВС (с циркуляцией), кВт",
                        f"{ep.q_peak_dhw_w / 1000:.1f}"])

    kv_annual: List[List[str]] = [
        ["Годовое отопление, МВт·ч/год", f"{ep.e_heating_kwh_year / 1000:.1f}"],
        ["Годовой нагрев вентиляции, МВт·ч/год",
         f"{ep.e_ventilation_kwh_year / 1000:.1f}"],
        ["Годовое охлаждение (эл.), МВт·ч/год",
         f"{ep.e_cooling_kwh_year / 1000:.1f}"],
        ["Годовое ГВС, МВт·ч/год", f"{ep.e_dhw_kwh_year / 1000:.1f}"],
        ["Удельный годовой расход тепла qh, кВт·ч/(м²·год)",
         f"{ep.qh_specific_kwh_m2:.1f}"],
    ]

    notes = ["Годовые расходы — упрощённый бин-метод по средней температуре "
             "отопительного периода (справочно, не заменяет энергоаудит)."]

    if uz:
        cat_title = shnq_category_title(ep.shnq_category)
        heading = "Энергоэффективность здания (ШНҚ 2.01.18-24, КМК 2.01.04-18)"
        intro = (
            "Оценка энергоэффективности выполнена сравнением удельной "
            "расчётной мощности на отопление и вентиляцию q с нормативом "
            "удельного расхода тепла q_ov по ШНҚ 2.01.18-24 (Табл. 1–3, "
            f"категория «{cat_title}», этажность {ep.n_floors}). "
            "Градусо-сутки отопительного периода Dd — по КМК 2.01.04-18, "
            "формула (1): Dd = (tв − tот.пер)·zот.пер."
        )
        kv_main.insert(4, ["Градусо-сутки Dd, °C·сут "
                           f"({dd_src})", f"{ep.dd_shnq:.0f}"])
        kv_main += [
            ["q удельная расчётная (отопл.+вент.), Вт/м²",
             f"{ep.q_design_specific_w_m2:.1f}"],
            ["q_ov норматив ШНҚ 2.01.18-24, Вт/м²",
             (f"{ep.q_ov_normative_w_m2:.0f}"
              if ep.q_ov_normative_w_m2 > 0 else "не табулирован")],
        ]
        if ep.shnq_compliant is None:
            verdict = ("Норматив q_ov для данного типа здания не табулирован "
                       "в ШНҚ 2.01.18-24 Табл. 1–3 — соответствие не "
                       "оценивается.")
            verdict_ok = None
        elif ep.shnq_compliant:
            verdict = (f"СООТВЕТСТВУЕТ ШНҚ 2.01.18-24: "
                       f"q = {ep.q_design_specific_w_m2:.1f} Вт/м² ≤ "
                       f"q_ov = {ep.q_ov_normative_w_m2:.0f} Вт/м²")
            verdict_ok = True
        else:
            verdict = (f"НЕ СООТВЕТСТВУЕТ ШНҚ 2.01.18-24: "
                       f"q = {ep.q_design_specific_w_m2:.1f} Вт/м² > "
                       f"q_ov = {ep.q_ov_normative_w_m2:.0f} Вт/м² — "
                       "требуются мероприятия (утепление ограждений, "
                       "утилизация теплоты вытяжного воздуха, автоматика)")
            verdict_ok = False
        notes.append("Классы энергоэффективности по СП 50.13330 в профиле "
                     "норм УзР не применяются.")
    else:
        heading = "Энергетический паспорт (СП 50.13330 Прил. Г)"
        intro = (f"Тип здания: {ep.building_type}. Расчёт удельного годового "
                 "потребления тепла на отопление по упрощённому бин-методу "
                 "на основе ГСОП.")
        kv_main.insert(4, ["ГСОП, °C·сут", f"{ep.gsop_18:.0f}"])
        kv_annual += [
            ["qh нормативный (СП 50 Табл. 14), кВт·ч/(м²·год)",
             f"{ep.qh_normative_kwh_m2:.1f}"],
            ["Отклонение от нормы, %", f"{ep.deviation_percent:+.1f}"],
        ]
        verdict = (f"КЛАСС ЭНЕРГОЭФФЕКТИВНОСТИ: {ep.energy_class} — "
                   f"{ep.energy_class_description}")
        verdict_ok = ep.deviation_percent <= 15.0

    return {"heading": heading, "intro": intro, "kv_main": kv_main,
            "kv_annual": kv_annual, "verdict": verdict,
            "verdict_ok": verdict_ok, "notes": notes}
