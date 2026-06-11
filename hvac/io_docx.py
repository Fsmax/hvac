# -*- coding: utf-8 -*-
"""Экспорт пояснительной записки в DOCX (Microsoft Word).

Редактируемый аналог PDF-записки (io_pdf.py): те же разделы и данные,
но в формате, который дорабатывают вручную под требования экспертизы.
Использует python-docx (pip install python-docx).

Разделы (include_sections): 'cover', 'inputs', 'constructions',
'heat_loss', 'heat_gain', 'ventilation', 'dhw', 'equipment', 'smoke',
'ducts', 'pipes', 'energy', 'condensation'. None — все.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from typing import List, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from hvac.project import HVACProject

ALL_SECTIONS = [
    "cover", "inputs", "constructions", "heat_loss", "heat_gain",
    "ventilation", "dhw", "equipment", "smoke", "ducts", "pipes",
    "energy", "condensation",
]


def export_to_docx(project: "HVACProject", path: str,
                   include_sections: Optional[List[str]] = None) -> None:
    """Создаёт DOCX-отчёт «Пояснительная записка» по проекту.

    include_sections : список разделов (None = все, см. ALL_SECTIONS).
    """
    try:
        from docx import Document
        from docx.enum.text import WD_ALIGN_PARAGRAPH
        from docx.shared import Pt
    except ImportError:
        raise RuntimeError("Не установлен python-docx. "
                           "Выполните: pip install python-docx")

    if include_sections is None:
        include_sections = list(ALL_SECTIONS)

    doc = Document()
    style = doc.styles["Normal"]
    style.font.name = "Calibri"
    style.font.size = Pt(10)

    p = project.params

    def add_para(text: str, *, bold: bool = False, center: bool = False,
                 size: Optional[int] = None):
        par = doc.add_paragraph()
        if center:
            par.alignment = WD_ALIGN_PARAGRAPH.CENTER
        run = par.add_run(text)
        run.bold = bold
        if size:
            run.font.size = Pt(size)
        return par

    def add_table(rows: List[List], header_row: bool = True):
        """Таблица с единым стилем; первая строка — шапка."""
        if not rows:
            return
        t = doc.add_table(rows=len(rows), cols=len(rows[0]))
        t.style = "Table Grid"
        for i, row in enumerate(rows):
            for j, val in enumerate(row):
                cell = t.cell(i, j)
                cell.text = str(val)
                for par in cell.paragraphs:
                    for run in par.runs:
                        run.font.size = Pt(9)
                        if header_row and i == 0:
                            run.bold = True
        doc.add_paragraph()

    def add_kv(rows: List[List]):
        add_table([["Параметр", "Значение"]] + [list(r) for r in rows])

    # =================== ТИТУЛЬНЫЙ ЛИСТ ===================
    if "cover" in include_sections:
        for _ in range(6):
            doc.add_paragraph()
        add_para("ПОЯСНИТЕЛЬНАЯ ЗАПИСКА", bold=True, center=True, size=22)
        add_para("Раздел «Отопление, вентиляция и кондиционирование воздуха»",
                 bold=True, center=True, size=14)
        doc.add_paragraph()
        add_para(f"Объект: {p.project_name or 'Объект'}", bold=True)
        add_para(f"Город: {p.city}", bold=True)
        doc.add_paragraph()

        n_spaces = len(project.spaces)
        total_area = sum(s.area_m2 for s in project.spaces)
        total_q = sum(s.heat_loss_w for s in project.spaces) / 1000.0
        total_qg = sum(s.heat_gain_w for s in project.spaces) / 1000.0
        add_para(f"Помещений: {n_spaces}, общая площадь "
                 f"{total_area:,.0f} м²".replace(",", " "))
        add_para(f"Σ Q отопления: {total_q:.1f} кВт")
        add_para(f"Σ Q охлаждения: {total_qg:.1f} кВт")
        doc.add_paragraph()
        add_para(f"Расчёт выполнен: {datetime.now().strftime('%d.%m.%Y')}")
        add_para("ПО: HVAC Calculator v4")
        add_para("Методики: СП 50.13330, СП 60.13330, СП 7.13130, "
                 "СП 30.13330, СП 131.13330, КМК Узбекистана")
        doc.add_page_break()

    # =================== 1. ИСХОДНЫЕ ДАННЫЕ ===================
    if "inputs" in include_sections:
        doc.add_heading("1. Исходные данные", level=1)
        add_para("Климатические параметры приняты по СП 131.13330.2018 для "
                 f"города {p.city}. Внутренние параметры — по "
                 "СП 60.13330.2020 для соответствующих типов помещений.")
        add_kv([
            ["Город", p.city],
            ["Расчётная зимняя tн, °C (обесп. 0.92)", f"{p.t_out_heating}"],
            ["Расчётная летняя tн, °C (обесп. 0.95)", f"{p.t_out_cooling}"],
            ["Суточная амплитуда летом, K", f"{p.daily_amplitude}"],
            ["ГСОП (t_в=+20°C, ≤8°C), °C·сут", f"{p.gsop_18:.0f}"],
            ["Солнечная радиация на вертик., Вт/м²",
             f"{p.solar_intensity_w_m2}"],
            ["Методика расчёта", p.methodology],
            ["Коэф. поправки инфильтрации", f"{p.inf_correction_k}"],
            ["Запас на отопление", f"{p.safety_margin_heating}"],
            ["Запас на охлаждение", f"{p.safety_margin_cooling}"],
        ])

    # =================== 2. КОНСТРУКЦИИ ===================
    if "constructions" in include_sections and project.constructions:
        doc.add_heading("2. Каталог конструкций", level=1)
        add_para("Каталог U-значений и SHGC ограждающих конструкций. "
                 "Сформирован автоматически по типам элементов из Revit.")
        rows = [["Категория", "Семейство", "Тип", "Δ, мм", "U", "SHGC"]]
        for key, c in sorted(project.constructions.items(),
                             key=lambda kv: (kv[1].category, kv[1].family)):
            rows.append([
                c.category, c.family, c.type_name[:35],
                f"{c.thickness_mm:.0f}",
                f"{c.u_value:.2f}" if c.u_value > 0 else "—",
                f"{c.shgc:.2f}" if c.shgc > 0 else "—",
            ])
        add_table(rows)

    # =================== 3. ТЕПЛОПОТЕРИ ===================
    if "heat_loss" in include_sections and project.spaces:
        doc.add_heading("3. Теплопотери (СП 50.13330)", level=1)
        loaded = [s for s in project.spaces if s.heat_loss_w > 0]
        total = sum(s.heat_loss_w for s in loaded)
        total_area = sum(s.area_m2 for s in loaded)
        add_para("Расчёт теплопотерь выполнен по СП 50.13330.2012 с "
                 f"разбивкой по статьям. Σ = {total / 1000:.1f} кВт "
                 f"({total / max(total_area, 1):.1f} Вт/м² удельно).")

        by_level: dict = defaultdict(lambda: {"n": 0, "area": 0.0, "q": 0.0})
        for s in loaded:
            by_level[s.level]["n"] += 1
            by_level[s.level]["area"] += s.area_m2
            by_level[s.level]["q"] += s.heat_loss_w
        rows = [["Уровень", "Кол-во", "Площадь, м²", "Q, кВт", "Уд., Вт/м²"]]
        for lvl in sorted(by_level.keys()):
            d = by_level[lvl]
            rows.append([lvl, d["n"], f"{d['area']:.0f}",
                         f"{d['q'] / 1000:.1f}",
                         f"{d['q'] / max(d['area'], 1):.1f}"])
        rows.append(["ИТОГО", str(len(loaded)), f"{total_area:.0f}",
                     f"{total / 1000:.1f}",
                     f"{total / max(total_area, 1):.1f}"])
        add_table(rows)

    # =================== 4. ТЕПЛОПОСТУПЛЕНИЯ ===================
    if "heat_gain" in include_sections and project.spaces:
        doc.add_heading("4. Теплопоступления (СП 60.13330)", level=1)
        loaded = [s for s in project.spaces if s.heat_gain_w > 0]
        total = sum(s.heat_gain_w for s in loaded)
        total_sens = sum(s.heat_gain_sensible_w for s in loaded)
        total_lat = sum(s.heat_gain_latent_w for s in loaded)
        add_para("Расчёт по СП 60.13330.2020 с разделением на явную "
                 f"(sensible) и скрытую (latent) теплоту. "
                 f"Σ = {total / 1000:.1f} кВт, из них sensible "
                 f"{total_sens / 1000:.1f}, latent {total_lat / 1000:.1f}.")

    # =================== 5. ВЕНТИЛЯЦИЯ ===================
    if "ventilation" in include_sections and project.spaces:
        doc.add_heading("5. Вентиляция (СП 60.13330)", level=1)
        sum_supply = sum(s.supply_m3h for s in project.spaces)
        sum_exhaust = sum(s.exhaust_m3h for s in project.spaces)
        sum_hood = sum(s.hood_m3h for s in project.spaces)
        add_para(f"Расходы по СП 60.13330.2020. Σ Supply = "
                 f"{sum_supply:,.0f} м³/ч, Σ Exhaust = "
                 f"{sum_exhaust:,.0f} м³/ч, Зонты кухонь = "
                 f"{sum_hood:,.0f} м³/ч.".replace(",", " "))

    # =================== 6. ГВС ===================
    if "dhw" in include_sections and project.dhw_systems:
        doc.add_heading("6. Горячее водоснабжение (СП 30.13330)", level=1)
        add_para("Расчёт по СП 30.13330.2020 Приложение А (Табл. А.2). "
                 "Учтены потери на циркуляцию и КПД нагревателей.")
        rows = [["Система", "N", "V сут, м³", "V час, м³/ч",
                 "Q пик, кВт", "Q нагр., кВт", "V бака, м³"]]
        total_v = total_q = 0.0
        for name, sys in sorted(project.dhw_systems.items()):
            rows.append([
                name, str(sys.n_consumers),
                f"{sys.v_daily_total_m3:.1f}",
                f"{sys.v_hourly_max_m3:.2f}",
                f"{sys.q_peak_w / 1000:.1f}",
                f"{sys.q_heater_size_w / 1000:.1f}",
                f"{sys.storage_recommended_m3:.2f}",
            ])
            total_v += sys.v_daily_total_m3
            total_q += sys.q_heater_size_w
        rows.append(["ИТОГО", "", f"{total_v:.1f}", "", "",
                     f"{total_q / 1000:.1f}", ""])
        add_table(rows)

    # =================== 7. СИСТЕМЫ ОБОРУДОВАНИЯ ===================
    if "equipment" in include_sections:
        doc.add_heading("7. Системы оборудования", level=1)
        if project.ventilation_systems:
            doc.add_heading("Приточные/вытяжные установки", level=2)
            rows = [["Имя", "Тип", "Рекуп.", "η зима",
                     "t под. зима", "t под. лето"]]
            for name, v in sorted(project.ventilation_systems.items()):
                rows.append([
                    name, v.system_type,
                    "Да" if v.has_recovery else "Нет",
                    f"{v.recovery_efficiency_winter:.2f}",
                    f"{v.t_supply_winter}°C", f"{v.t_supply_summer}°C",
                ])
            add_table(rows)
        if project.heating_systems:
            doc.add_heading("Источники тепла", level=2)
            rows = [["Имя", "Тип", "t подачи", "t обр.", "Топливо", "η"]]
            for name, h in sorted(project.heating_systems.items()):
                rows.append([name, h.system_type, f"{h.t_supply}°C",
                             f"{h.t_return}°C", h.fuel, f"{h.efficiency:.2f}"])
            add_table(rows)
        if project.cooling_systems:
            doc.add_heading("Источники холода", level=2)
            rows = [["Имя", "Тип", "t подачи", "t обр.",
                     "Хладагент", "EER/COP"]]
            for name, cs in sorted(project.cooling_systems.items()):
                rows.append([name, cs.system_type, f"{cs.t_supply}°C",
                             f"{cs.t_return}°C", cs.refrigerant,
                             f"{cs.cop:.2f}"])
            add_table(rows)
        if project.ahu_loads:
            doc.add_heading("Нагрузки от приточных установок", level=2)
            rows = [["AHU", "Supply, м³/ч", "Q калориф., кВт",
                     "Q охл. явн., кВт", "Q охл. скр., кВт"]]
            total_h = total_cs = total_cl = 0.0
            for name, d in sorted(project.ahu_loads.items()):
                rows.append([
                    name, f"{d['supply_m3h']:,.0f}".replace(",", " "),
                    f"{d['q_heater_w'] / 1000:.1f}",
                    f"{d['q_cooler_sens_w'] / 1000:.1f}",
                    f"{d['q_cooler_lat_w'] / 1000:.1f}",
                ])
                total_h += d["q_heater_w"]
                total_cs += d["q_cooler_sens_w"]
                total_cl += d["q_cooler_lat_w"]
            rows.append(["ИТОГО", "", f"{total_h / 1000:.1f}",
                         f"{total_cs / 1000:.1f}", f"{total_cl / 1000:.1f}"])
            add_table(rows)

    # =================== 8. ДЫМОУДАЛЕНИЕ ===================
    if "smoke" in include_sections and project.smoke_systems:
        from hvac.catalogs.smoke_norms import get_smoke_norm
        norm = get_smoke_norm(getattr(project.params, "smoke_norm", "SP7_RU"))
        doc.add_heading(
            f"8. Дымоудаление и подпор воздуха — {norm.title}", level=1)
        add_para(f"Действующий норматив: {norm.reference}")

        smoke = {k: v for k, v in project.smoke_systems.items()
                 if v.system_type == "smoke_removal"}
        press = {k: v for k, v in project.smoke_systems.items()
                 if v.system_type == "air_supply"}
        if smoke:
            doc.add_heading("Системы дымоудаления (СДУ)", level=2)
            rows = [["Имя", "Назначение", "Метод", "Площадь, м²", "Зон",
                     "L сист., м³/ч", "L комп., м³/ч", "Огнест."]]
            for name, ss in sorted(smoke.items()):
                rows.append([
                    name, ss.purpose, ss.calc_method,
                    f"{ss.served_area_m2:.0f}", str(ss.n_zones),
                    f"{ss.L_smoke_m3h:,.0f}".replace(",", " "),
                    f"{ss.L_makeup_m3h:,.0f}".replace(",", " "),
                    ss.fire_rating,
                ])
            add_table(rows)
        if press:
            doc.add_heading("Системы подпора воздуха (СПВ)", level=2)
            rows = [["Имя", "Назначение", "L, м³/ч", "Давление, Па"]]
            for name, ps in sorted(press.items()):
                rows.append([
                    name, ps.purpose,
                    f"{ps.L_smoke_m3h:,.0f}".replace(",", " "),
                    f"{ps.pressure_pa:.1f}",
                ])
            add_table(rows)

    # =================== 9. ВОЗДУХОВОДЫ ===================
    if "ducts" in include_sections and project.duct_networks:
        doc.add_heading(
            "9. Подбор воздуховодов (упрощённая аэродинамика)", level=1)
        add_para("Подбор по рекомендованным скоростям, потери давления — "
                 "формула Дарси-Вейсбаха.")
        for sys_name, net in sorted(project.duct_networks.items()):
            doc.add_heading(
                f"{sys_name}: Σ Q = {net.total_flow_m3h:,.0f} м³/ч, "
                f"Δp ≈ {net.total_pressure_loss_pa:.0f} Па"
                .replace(",", " "), level=2)
            rows = [["Участок", "Q, м³/ч", "Размер", "v, м/с", "Δp, Па"]]
            for sec in net.sections:
                size_str = (f"Ø{int(sec.diameter_mm)}"
                            if sec.shape == "round"
                            else f"{int(sec.width_mm)}×{int(sec.height_mm)}")
                rows.append([
                    sec.id[-30:],
                    f"{sec.flow_m3h:,.0f}".replace(",", " "), size_str,
                    f"{sec.velocity_m_s:.1f}",
                    f"{sec.pressure_loss_total_pa:.0f}",
                ])
            add_table(rows)

    # =================== 10. ТРУБЫ ОТОПЛЕНИЯ ===================
    if "pipes" in include_sections and project.pipe_networks:
        doc.add_heading(
            "10. Подбор труб отопления (гидравлический расчёт)", level=1)
        from hvac.pipe_sizing import WATER_DENSITY_70C
        add_para("Подбор по рекомендованным скоростям (СП 60), потери "
                 "давления — формула Альтшуля.")
        for sys_name, pnet in sorted(project.pipe_networks.items()):
            pump_m = pnet.total_pressure_loss_pa / (WATER_DENSITY_70C * 9.81)
            doc.add_heading(
                f"{sys_name}: Σ Q = {pnet.total_heat_load_w / 1000:.1f} кВт, "
                f"Σ G = {pnet.total_flow_kg_h:.0f} кг/ч, "
                f"Δp = {pnet.total_pressure_loss_pa / 1000:.1f} кПа, "
                f"напор ≈ {pump_m:.1f} м", level=2)
            rows = [["Участок", "Q, Вт", "DN", "v, м/с", "Δp, Па"]]
            for psec in pnet.sections:
                rows.append([
                    psec.id[-30:],
                    f"{psec.heat_load_w:,.0f}".replace(",", " "),
                    f"{int(psec.dn_mm)}", f"{psec.velocity_m_s:.2f}",
                    f"{psec.pressure_loss_total_pa:.0f}",
                ])
            add_table(rows)

    # =================== 11. ЭНЕРГОПАСПОРТ ===================
    if "energy" in include_sections and project.energy_passport:
        ep = project.energy_passport
        doc.add_heading(
            "11. Энергетический паспорт (СП 50.13330 Прил. Г)", level=1)
        add_para(f"Тип здания: {ep.building_type}. Расчёт удельного "
                 "годового потребления тепла на отопление по упрощённому "
                 "бин-методу на основе ГСОП.")
        add_kv([
            ["Отапливаемая площадь, м²", f"{ep.total_area_m2:.0f}"],
            ["Объём, м³", f"{ep.total_volume_m3:.0f}"],
            ["ГСОП", f"{ep.gsop_18:.0f}"],
            ["Длительность отопит. сезона, сут", f"{ep.z_heating_days:.0f}"],
            ["Q пиковая отопления, кВт", f"{ep.q_peak_heating_w / 1000:.1f}"],
            ["Q пиковая охлаждения, кВт", f"{ep.q_peak_cooling_w / 1000:.1f}"],
            ["Годовое отопление, МВт·ч/год",
             f"{ep.e_heating_kwh_year / 1000:.1f}"],
            ["Годовое охлаждение (эл.), МВт·ч/год",
             f"{ep.e_cooling_kwh_year / 1000:.1f}"],
            ["Годовое ГВС, МВт·ч/год", f"{ep.e_dhw_kwh_year / 1000:.1f}"],
            ["qh удельный, кВт·ч/(м²·год)", f"{ep.qh_specific_kwh_m2:.1f}"],
            ["qh нормативный, кВт·ч/(м²·год)",
             f"{ep.qh_normative_kwh_m2:.1f}"],
            ["Отклонение от нормы, %", f"{ep.deviation_percent:+.1f}"],
        ])
        add_para(f"КЛАСС ЭНЕРГОЭФФЕКТИВНОСТИ: {ep.energy_class} — "
                 f"{ep.energy_class_description}", bold=True, center=True)

    # =================== 12. ТОЧКА РОСЫ ===================
    if "condensation" in include_sections and project.condensation_results:
        doc.add_heading(
            "12. Проверка ограждений на конденсацию (СП 50.13330 Прил. Е)",
            level=1)
        bad = [c for c in project.condensation_results
               if c.condensation_risk or c.normative_fail]
        add_para(f"Проверено элементов: {len(project.condensation_results)}, "
                 f"с замечаниями: {len(bad)}.")
        if bad:
            rows = [["Помещение", "Категория", "U", "τ_int, °C",
                     "t_росы, °C", "Δt факт, K", "Δt норм, K", "Риск"]]
            for c in bad[:80]:
                rows.append([
                    f"{c.space_number} {c.space_name}"[:30], c.category,
                    f"{c.u_value:.2f}", f"{c.t_surface:.1f}",
                    f"{c.t_dew:.1f}", f"{c.dt_actual:.1f}",
                    f"{c.dt_normative:.1f}",
                    "конденсат" if c.condensation_risk else "норматив",
                ])
            add_table(rows)

    doc.core_properties.title = (p.project_name or "Пояснительная записка")
    doc.core_properties.comments = "HVAC Calculator"
    doc.save(path)
