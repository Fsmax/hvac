# -*- coding: utf-8 -*-
"""PDF-отчёт «Пояснительная записка» по проекту ОВиК.

Сводный документ для сдачи заказчику / в экспертизу. Использует reportlab.
Включает все рассчитанные разделы:

  Титульный лист → Исходные данные → Конструкции → Теплопотери →
  Теплопоступления → Вентиляция → ГВС → Системы оборудования →
  Дымоудаление → Воздуховоды → Трубы отопления → Энергопаспорт →
  Точка росы

Шрифт DejaVu Sans (поддерживает кириллицу), путь определяется автоматически.
"""

from __future__ import annotations
import os
from datetime import datetime
from typing import List, TYPE_CHECKING

if TYPE_CHECKING:
    from hvac.project import HVACProject


# ============================================================================
# Поиск шрифта с кириллицей
# ============================================================================

def _find_cyrillic_font() -> tuple:
    """Возвращает (regular_path, bold_path) для шрифта с поддержкой кириллицы.
    
    Ищет в стандартных местах Linux/macOS/Windows.
    """
    candidates_regular = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",            # Linux Debian/Ubuntu
        "/usr/share/fonts/dejavu/DejaVuSans.ttf",                      # Linux Fedora
        "/usr/share/fonts/TTF/DejaVuSans.ttf",                         # Linux Arch
        "/Library/Fonts/Arial Unicode.ttf",                            # macOS
        "/Library/Fonts/DejaVuSans.ttf",                               # macOS (manual)
        "C:/Windows/Fonts/arial.ttf",                                  # Windows
        "C:/Windows/Fonts/dejavusans.ttf",
    ]
    candidates_bold = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/TTF/DejaVuSans-Bold.ttf",
        "/Library/Fonts/Arial Unicode.ttf",
        "/Library/Fonts/DejaVuSans-Bold.ttf",
        "C:/Windows/Fonts/arialbd.ttf",
        "C:/Windows/Fonts/dejavusans-bold.ttf",
    ]
    reg = next((p for p in candidates_regular if os.path.exists(p)), None)
    bold = next((p for p in candidates_bold if os.path.exists(p)), reg)
    return reg, bold


def _register_fonts() -> tuple:
    """Регистрирует шрифты в reportlab. Возвращает (font_name, font_bold)."""
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont

    reg_path, bold_path = _find_cyrillic_font()
    if reg_path is None:
        # Fallback на Helvetica (только латиница — кириллица будет ???)
        return ("Helvetica", "Helvetica-Bold")

    pdfmetrics.registerFont(TTFont("DejaVu", reg_path))
    if bold_path and bold_path != reg_path:
        pdfmetrics.registerFont(TTFont("DejaVu-Bold", bold_path))
        return ("DejaVu", "DejaVu-Bold")
    return ("DejaVu", "DejaVu")


# ============================================================================
# Генерация отчёта
# ============================================================================

def export_to_pdf(project: "HVACProject", path: str,
                  include_sections: List[str] = None) -> None:
    """Создаёт PDF-отчёт по проекту.

    Параметры
    ---------
    include_sections : список разделов (None = все). Возможные:
                       'cover', 'inputs', 'constructions', 'heat_loss',
                       'heat_gain', 'ventilation', 'dhw', 'equipment',
                       'smoke', 'ducts', 'pipes', 'energy', 'condensation'.
    """
    try:
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.units import cm
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY
        from reportlab.lib import colors
        from reportlab.platypus import (
            SimpleDocTemplate, Paragraph, Spacer, PageBreak,
            Table, TableStyle,
        )
    except ImportError:
        raise RuntimeError("Не установлен reportlab. "
                           "Выполните: pip install reportlab")

    font_name, font_bold = _register_fonts()

    # Стили
    styles = getSampleStyleSheet()
    style_title = ParagraphStyle(
        "TitleRu", parent=styles["Title"], fontName=font_bold,
        fontSize=22, leading=26, alignment=TA_CENTER, spaceAfter=20,
    )
    style_subtitle = ParagraphStyle(
        "SubtitleRu", parent=styles["Heading2"], fontName=font_bold,
        fontSize=16, leading=20, alignment=TA_CENTER, spaceAfter=14,
    )
    style_h1 = ParagraphStyle(
        "H1Ru", parent=styles["Heading1"], fontName=font_bold,
        fontSize=14, leading=18, spaceBefore=18, spaceAfter=10,
    )
    style_h2 = ParagraphStyle(
        "H2Ru", parent=styles["Heading2"], fontName=font_bold,
        fontSize=12, leading=15, spaceBefore=10, spaceAfter=6,
    )
    style_body = ParagraphStyle(
        "BodyRu", parent=styles["Normal"], fontName=font_name,
        fontSize=10, leading=13, alignment=TA_JUSTIFY,
    )
    style_small = ParagraphStyle(
        "SmallRu", parent=styles["Normal"], fontName=font_name,
        fontSize=8, leading=11,
    )
    style_caption = ParagraphStyle(
        "CapRu", parent=styles["Normal"], fontName=font_name,
        fontSize=9, leading=11, alignment=TA_CENTER, spaceAfter=4,
        textColor=colors.HexColor("#555555"),
    )

    if include_sections is None:
        include_sections = [
            "cover", "inputs", "constructions", "heat_loss", "heat_gain",
            "ventilation", "dhw", "equipment", "smoke",
            "ducts", "pipes", "energy", "condensation",
            # v4.1
            "ahu_process", "duct_detailed", "hydraulics",
            "radiators", "acoustics",
            # v4.2
            "underfloor", "fancoils", "vrf",
        ]

    # Временные PNG-файлы для встраиваемых диаграмм — удаляются после
    # doc.build(), потому что reportlab читает их именно на этом этапе.
    _temp_image_paths: List[str] = []

    elements = []
    p = project.params

    def add_table(data, col_widths=None, header_row=True):
        """Утилита: добавить таблицу с единым стилем."""
        if not data:
            return
        t = Table(data, colWidths=col_widths, repeatRows=1 if header_row else 0)
        style = [
            ("FONTNAME", (0, 0), (-1, -1), font_name),
            ("FONTSIZE", (0, 0), (-1, -1), 9),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#888888")),
            ("LEFTPADDING", (0, 0), (-1, -1), 4),
            ("RIGHTPADDING", (0, 0), (-1, -1), 4),
            ("TOPPADDING", (0, 0), (-1, -1), 3),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ]
        if header_row:
            style.append(("BACKGROUND", (0, 0), (-1, 0),
                          colors.HexColor("#1F4E78")))
            style.append(("TEXTCOLOR", (0, 0), (-1, 0), colors.white))
            style.append(("FONTNAME", (0, 0), (-1, 0), font_bold))
            style.append(("ALIGN", (0, 0), (-1, 0), "CENTER"))
        t.setStyle(TableStyle(style))
        elements.append(t)
        elements.append(Spacer(1, 6))

    def add_kv(rows):
        """Таблица 'параметр — значение'."""
        data = [["Параметр", "Значение"]] + rows
        add_table(data, col_widths=[10 * cm, 7 * cm])

    # =================== ТИТУЛЬНЫЙ ЛИСТ ===================
    if "cover" in include_sections:
        elements.append(Spacer(1, 4 * cm))
        elements.append(Paragraph("ПОЯСНИТЕЛЬНАЯ ЗАПИСКА", style_title))
        elements.append(Paragraph(
            "Раздел «Отопление, вентиляция и кондиционирование воздуха»",
            style_subtitle))
        elements.append(Spacer(1, 3 * cm))

        proj_name = p.project_name or "Объект"
        elements.append(Paragraph(f"<b>Объект:</b> {proj_name}", style_h2))
        elements.append(Paragraph(f"<b>Город:</b> {p.city}", style_h2))
        elements.append(Spacer(1, 2 * cm))

        n_spaces = len(project.spaces)
        total_area = sum(s.area_m2 for s in project.spaces)
        total_q = sum(s.heat_loss_w for s in project.spaces) / 1000.0
        total_qg = sum(s.heat_gain_w for s in project.spaces) / 1000.0

        elements.append(Paragraph(
            f"Помещений: {n_spaces}, общая площадь {total_area:,.0f} м²"
            .replace(",", " "), style_body))
        elements.append(Paragraph(
            f"Σ Q отопления: {total_q:.1f} кВт", style_body))
        elements.append(Paragraph(
            f"Σ Q охлаждения: {total_qg:.1f} кВт", style_body))

        elements.append(Spacer(1, 4 * cm))
        elements.append(Paragraph(
            f"Расчёт выполнен: {datetime.now().strftime('%d.%m.%Y')}",
            style_body))
        elements.append(Paragraph(
            "ПО: HVAC Calculator v3.7", style_body))
        elements.append(Paragraph(
            "Методики: СП 50.13330, СП 60.13330, СП 7.13130, СП 30.13330, "
            "СП 131.13330, КМК Узбекистана", style_body))
        elements.append(PageBreak())

    # =================== 1. ИСХОДНЫЕ ДАННЫЕ ===================
    if "inputs" in include_sections:
        elements.append(Paragraph("1. Исходные данные", style_h1))
        elements.append(Paragraph(
            "Климатические параметры приняты по СП 131.13330.2018 для города "
            f"<b>{p.city}</b>. Внутренние параметры — по СП 60.13330.2020 "
            "для соответствующих типов помещений.", style_body))
        elements.append(Spacer(1, 4))

        add_kv([
            ["Город", p.city],
            ["Расчётная зимняя tн, °C (обесп. 0.92)",
             f"{p.t_out_heating}"],
            ["Расчётная летняя tн, °C (обесп. 0.95)",
             f"{p.t_out_cooling}"],
            ["Суточная амплитуда летом, K", f"{p.daily_amplitude}"],
            ["ГСОП (t_в=+20°C, ≤8°C), °C·сут", f"{p.gsop_18:.0f}"],
            ["Солнечная радиация на вертик., Вт/м²",
             f"{p.solar_intensity_w_m2}"],
            ["Влагосодержание нар. лето, г/кг",
             f"{p.w_out_summer_g_kg}"],
            ["Влагосодержание вн. лето, г/кг",
             f"{p.w_in_summer_g_kg}"],
            ["Методика расчёта", p.methodology],
            ["Коэф. поправки инфильтрации", f"{p.inf_correction_k}"],
            ["Запас на отопление", f"{p.safety_margin_heating}"],
            ["Запас на охлаждение", f"{p.safety_margin_cooling}"],
            ["WWR (оценка остекл.)", f"{p.wwr_estimate}"],
            ["Коэф. солнцезащиты", f"{p.solar_shading_factor}"],
        ])

    # =================== 2. КОНСТРУКЦИИ ===================
    if "constructions" in include_sections and project.constructions:
        elements.append(Paragraph("2. Каталог конструкций", style_h1))
        elements.append(Paragraph(
            "Каталог U-значений и SHGC ограждающих конструкций. Сформирован "
            "автоматически по типам элементов из Revit, значения U "
            "назначены пользователем.", style_body))
        elements.append(Spacer(1, 4))

        rows = [["Категория", "Семейство", "Тип", "Δ, мм", "U", "SHGC"]]
        for key, c in sorted(project.constructions.items(),
                             key=lambda kv: (kv[1].category, kv[1].family)):
            rows.append([
                c.category, c.family, c.type_name[:35],
                f"{c.thickness_mm:.0f}",
                f"{c.u_value:.2f}" if c.u_value > 0 else "—",
                f"{c.shgc:.2f}" if c.shgc > 0 else "—",
            ])
        add_table(rows, col_widths=[2.5 * cm, 3 * cm, 5.5 * cm,
                                     1.3 * cm, 1.3 * cm, 1.4 * cm])

    # =================== 3. ТЕПЛОПОТЕРИ ===================
    if "heat_loss" in include_sections and project.spaces:
        elements.append(Paragraph("3. Теплопотери (СП 50.13330)", style_h1))
        loaded = [s for s in project.spaces if s.heat_loss_w > 0]
        total = sum(s.heat_loss_w for s in loaded)
        total_area = sum(s.area_m2 for s in loaded)
        elements.append(Paragraph(
            f"Расчёт теплопотерь выполнен по СП 50.13330.2012 с разбивкой "
            f"по статьям. Σ = <b>{total/1000:.1f} кВт</b> "
            f"({total / max(total_area, 1):.1f} Вт/м² удельно).", style_body))

        # Свод по этажам
        from collections import defaultdict
        by_level: dict = defaultdict(lambda: {"n": 0, "area": 0.0, "q": 0.0})
        for s in loaded:
            by_level[s.level]["n"] += 1
            by_level[s.level]["area"] += s.area_m2
            by_level[s.level]["q"] += s.heat_loss_w

        rows = [["Уровень", "Кол-во", "Площадь, м²", "Q, кВт",
                 "Уд., Вт/м²"]]
        for lvl in sorted(by_level.keys()):
            d = by_level[lvl]
            ud = d["q"] / max(d["area"], 1)
            rows.append([lvl, d["n"], f"{d['area']:.0f}",
                         f"{d['q']/1000:.1f}", f"{ud:.1f}"])
        rows.append(["ИТОГО", str(len(loaded)), f"{total_area:.0f}",
                     f"{total/1000:.1f}", f"{total/max(total_area,1):.1f}"])
        add_table(rows, col_widths=[3 * cm, 2 * cm, 3 * cm, 3 * cm, 3 * cm])

    # =================== 4. ТЕПЛОПОСТУПЛЕНИЯ ===================
    if "heat_gain" in include_sections and project.spaces:
        elements.append(Paragraph(
            "4. Теплопоступления (СП 60.13330)", style_h1))
        loaded = [s for s in project.spaces if s.heat_gain_w > 0]
        total = sum(s.heat_gain_w for s in loaded)
        total_sens = sum(s.heat_gain_sensible_w for s in loaded)
        total_lat = sum(s.heat_gain_latent_w for s in loaded)
        elements.append(Paragraph(
            f"Расчёт по СП 60.13330.2020 с разделением на явную (sensible) "
            f"и скрытую (latent) теплоту. Σ = <b>{total/1000:.1f} кВт</b>, "
            f"из них sensible {total_sens/1000:.1f}, "
            f"latent {total_lat/1000:.1f}.", style_body))

    # =================== 5. ВЕНТИЛЯЦИЯ ===================
    if "ventilation" in include_sections and project.spaces:
        elements.append(Paragraph("5. Вентиляция (СП 60.13330)", style_h1))
        sum_supply = sum(s.supply_m3h for s in project.spaces)
        sum_exhaust = sum(s.exhaust_m3h for s in project.spaces)
        sum_hood = sum(s.hood_m3h for s in project.spaces)
        elements.append(Paragraph(
            f"Расходы по СП 60.13330.2020. Σ Supply = "
            f"<b>{sum_supply:,.0f} м³/ч</b>, "
            f"Σ Exhaust = <b>{sum_exhaust:,.0f} м³/ч</b>, "
            f"Зонты кухонь = {sum_hood:,.0f} м³/ч.".replace(",", " "),
            style_body))

    # =================== 6. ГВС ===================
    if "dhw" in include_sections and project.dhw_systems:
        elements.append(Paragraph(
            "6. Горячее водоснабжение (СП 30.13330)", style_h1))
        elements.append(Paragraph(
            "Расчёт по СП 30.13330.2020 Приложение А (Табл. А.2) — норма "
            "расхода 60°C-воды на потребителя в сутки. Учтены потери на "
            "циркуляцию и КПД нагревателей.", style_body))

        rows = [["Система", "N", "V сут, м³", "V час, м³/ч",
                 "Q пик, кВт", "Q нагр., кВт", "V бака, м³"]]
        total_v = total_q = 0.0
        for name, sys in sorted(project.dhw_systems.items()):
            rows.append([
                name, str(sys.n_consumers),
                f"{sys.v_daily_total_m3:.1f}",
                f"{sys.v_hourly_max_m3:.2f}",
                f"{sys.q_peak_w/1000:.1f}",
                f"{sys.q_heater_size_w/1000:.1f}",
                f"{sys.storage_recommended_m3:.2f}",
            ])
            total_v += sys.v_daily_total_m3
            total_q += sys.q_heater_size_w
        rows.append(["ИТОГО", "", f"{total_v:.1f}", "",
                     "", f"{total_q/1000:.1f}", ""])
        add_table(rows, col_widths=[3.5 * cm, 1.5 * cm, 2.3 * cm,
                                     2.3 * cm, 2.3 * cm, 2.3 * cm, 2 * cm])

    # =================== 7. СИСТЕМЫ ОБОРУДОВАНИЯ ===================
    if "equipment" in include_sections:
        elements.append(Paragraph(
            "7. Системы оборудования", style_h1))
        if project.ventilation_systems:
            elements.append(Paragraph("Приточные/вытяжные установки", style_h2))
            rows = [["Имя", "Тип", "Рекуп.", "η зима", "t под. зима",
                     "t под. лето"]]
            for name, v in sorted(project.ventilation_systems.items()):
                rows.append([
                    name, v.system_type,
                    "Да" if v.has_recovery else "Нет",
                    f"{v.recovery_efficiency_winter:.2f}",
                    f"{v.t_supply_winter}°C",
                    f"{v.t_supply_summer}°C",
                ])
            add_table(rows, col_widths=[3.5 * cm, 3 * cm, 1.7 * cm,
                                         2 * cm, 2.7 * cm, 2.7 * cm])

        if project.heating_systems:
            elements.append(Paragraph("Источники тепла", style_h2))
            rows = [["Имя", "Тип", "t подачи", "t обр.", "Топливо", "η"]]
            for name, h in sorted(project.heating_systems.items()):
                rows.append([name, h.system_type, f"{h.t_supply}°C",
                             f"{h.t_return}°C", h.fuel,
                             f"{h.efficiency:.2f}"])
            add_table(rows, col_widths=[3.5 * cm, 4 * cm, 2 * cm,
                                         2 * cm, 2.5 * cm, 1.5 * cm])

        if project.cooling_systems:
            elements.append(Paragraph("Источники холода", style_h2))
            rows = [["Имя", "Тип", "t подачи", "t обр.", "Хладагент", "EER/COP"]]
            for name, cs in sorted(project.cooling_systems.items()):
                rows.append([name, cs.system_type, f"{cs.t_supply}°C",
                             f"{cs.t_return}°C", cs.refrigerant,
                             f"{cs.cop:.2f}"])
            add_table(rows, col_widths=[3.5 * cm, 4 * cm, 2 * cm,
                                         2 * cm, 2.5 * cm, 1.5 * cm])

        # Нагрузки от приточек
        if project.ahu_loads:
            elements.append(Paragraph("Нагрузки от приточных установок", style_h2))
            rows = [["AHU", "Supply, м³/ч", "Q калорифера, кВт",
                     "Q охлад. явный, кВт", "Q охлад. скрытый, кВт"]]
            total_h = total_cs = total_cl = 0.0
            for name, d in sorted(project.ahu_loads.items()):
                rows.append([
                    name, f"{d['supply_m3h']:,.0f}".replace(",", " "),
                    f"{d['q_heater_w']/1000:.1f}",
                    f"{d['q_cooler_sens_w']/1000:.1f}",
                    f"{d['q_cooler_lat_w']/1000:.1f}",
                ])
                total_h += d["q_heater_w"]
                total_cs += d["q_cooler_sens_w"]
                total_cl += d["q_cooler_lat_w"]
            rows.append(["ИТОГО", "", f"{total_h/1000:.1f}",
                         f"{total_cs/1000:.1f}", f"{total_cl/1000:.1f}"])
            add_table(rows, col_widths=[3 * cm, 3 * cm, 3 * cm, 3.5 * cm,
                                         3.5 * cm])

    # =================== 8. ДЫМОУДАЛЕНИЕ ===================
    if "smoke" in include_sections and project.smoke_systems:
        from hvac.catalogs.smoke_norms import get_smoke_norm
        active_norm = get_smoke_norm(
            getattr(project.params, "smoke_norm", "SP7_RU"))

        elements.append(Paragraph(
            f"8. Дымоудаление и подпор воздуха — {active_norm.title}",
            style_h1))
        elements.append(Paragraph(
            f"<b>Действующий норматив:</b> {active_norm.reference}",
            style_body))
        if active_norm.note:
            elements.append(Paragraph(
                f"<i>{active_norm.note}</i>", style_body))
        elements.append(Spacer(1, 4))

        # Краткая сводка параметров норматива
        add_kv([
            ("Макс. площадь дымовой зоны, м²",
                f"{active_norm.max_zone_area_m2:.0f}"),
            ("Доля компенсирующей подачи",
                f"{active_norm.default_makeup_ratio:.0%}"),
            ("Расчётная температура дыма, °C",
                f"{active_norm.default_t_smoke_C:.0f}"),
            ("Избыточное давление подпора, Па",
                f"{active_norm.default_pressure_pa:.1f}"),
            ("Класс огнестойкости (по умолчанию)",
                active_norm.default_fire_rating),
            ("Рекомендованный метод расчёта",
                active_norm.calc_method_recommended),
        ])
        elements.append(Spacer(1, 6))

        smoke = {k: v for k, v in project.smoke_systems.items()
                 if v.system_type == "smoke_removal"}
        press = {k: v for k, v in project.smoke_systems.items()
                 if v.system_type == "air_supply"}

        # Человекочитаемые названия методов
        method_labels = {
            "norm_per_m2":        "По норме (м³/ч·м²)",
            "kmk_zone_perimeter": "КМК Прил. 20, ф.(3): G=676.8·P·y^1.5·Ks",
            "kmk_corridor":       "КМК Прил. 22, ф.(1)/(2): G=K·B·n·H^1.5",
            "nfpa_plume_axi":     "NFPA 92 п. 5.5.1: axisymmetric plume",
            "manual":             "Расход задан вручную",
            "corridor_formula":   "Упрощённая формула коридора",
            "stairs_pressure":    "Подпор лестницы",
            "elevator_pressure":  "Подпор лифта",
        }

        def _system_params_str(s) -> str:
            """Краткая строка с входными параметрами расчёта по методу."""
            m = s.calc_method
            if m == "norm_per_m2":
                return f"норма={s.norm_per_m2} м³/ч·м²"
            if m == "kmk_zone_perimeter":
                return (f"P={s.fire_perimeter_m} м, "
                        f"y={s.layer_height_m} м, "
                        f"Ks={s.ks_sprinkler}")
            if m == "kmk_corridor":
                kind = "общ." if s.corridor_public else "жил."
                return (f"B={s.corridor_door_width_m} м, "
                        f"H={s.corridor_door_height_m} м, "
                        f"{kind}, Kd={s.kd_door}")
            if m == "nfpa_plume_axi":
                return (f"Q={s.hrr_kw:.0f} кВт, "
                        f"z={s.plume_height_m} м, "
                        f"α={s.convective_fraction}")
            if m == "manual":
                return "ручной ввод"
            return m

        if smoke:
            elements.append(Paragraph("Системы дымоудаления (СДУ)", style_h2))
            rows = [["Имя", "Назначение", "Метод / параметры",
                     "Площадь, м²", "Зон",
                     "L зоны, м³/ч", "L сист., м³/ч", "L комп., м³/ч",
                     "Огнест."]]
            for name, ss in sorted(smoke.items()):
                method_label = method_labels.get(ss.calc_method, ss.calc_method)
                method_cell = f"{method_label}\n{_system_params_str(ss)}"
                rows.append([
                    name, ss.purpose, method_cell,
                    f"{ss.served_area_m2:.0f}",
                    str(ss.n_zones),
                    f"{ss.L_per_zone_m3h:,.0f}".replace(",", " "),
                    f"{ss.L_smoke_m3h:,.0f}".replace(",", " "),
                    f"{ss.L_makeup_m3h:,.0f}".replace(",", " "),
                    ss.fire_rating,
                ])
            add_table(rows, col_widths=[2.2 * cm, 2.2 * cm, 4.5 * cm,
                                         1.6 * cm, 1.0 * cm,
                                         1.8 * cm, 1.8 * cm, 1.8 * cm,
                                         1.6 * cm])

            # Итоги по СДУ
            total_smoke = sum(s.L_smoke_m3h for s in smoke.values())
            total_makeup = sum(s.L_makeup_m3h for s in smoke.values())
            elements.append(Spacer(1, 4))
            elements.append(Paragraph(
                f"<b>Итого СДУ:</b> {len(smoke)} систем, "
                f"Σ дым = {total_smoke:,.0f} м³/ч, "
                f"Σ компенсация = {total_makeup:,.0f} м³/ч"
                .replace(",", " "), style_body))

        if press:
            elements.append(Spacer(1, 6))
            elements.append(Paragraph(
                "Системы подпора воздуха (СПВ)", style_h2))
            rows = [["Имя", "Назначение", "Помещение",
                     "L, м³/ч", "Давление, Па"]]
            for name, ps in sorted(press.items()):
                # Найти первое помещение, к которому привязана СПВ
                room_label = ""
                for sp in project.spaces:
                    if sp.pressurization_system == name:
                        room_label = f"{sp.number} {sp.name}"[:30]
                        break
                rows.append([
                    name, ps.purpose, room_label,
                    f"{ps.L_smoke_m3h:,.0f}".replace(",", " "),
                    f"{ps.pressure_pa:.1f}",
                ])
            add_table(rows, col_widths=[3 * cm, 2.5 * cm, 5 * cm,
                                         2.5 * cm, 2.5 * cm])

            total_pres = sum(s.L_smoke_m3h for s in press.values())
            elements.append(Spacer(1, 4))
            elements.append(Paragraph(
                f"<b>Итого СПВ:</b> {len(press)} систем, "
                f"Σ подпор = {total_pres:,.0f} м³/ч".replace(",", " "),
                style_body))

    # =================== 9. ВОЗДУХОВОДЫ ===================
    if "ducts" in include_sections and project.duct_networks:
        elements.append(Paragraph(
            "9. Подбор воздуховодов (упрощённая аэродинамика)", style_h1))
        elements.append(Paragraph(
            "Подбор по рекомендованным скоростям, потери давления — формула "
            "Дарси-Вейсбаха. Точная увязка сети — в специализированном ПО.",
            style_body))
        for sys_name, net in sorted(project.duct_networks.items()):
            elements.append(Paragraph(
                f"{sys_name}: Σ Q = {net.total_flow_m3h:,.0f} м³/ч, "
                f"Δp для AHU ≈ {net.total_pressure_loss_pa:.0f} Па"
                .replace(",", " "), style_h2))
            rows = [["Участок", "Q, м³/ч", "Размер", "v, м/с", "Δp, Па"]]
            for sec in net.sections:
                size_str = (f"Ø{int(sec.diameter_mm)}" if sec.shape == "round"
                            else f"{int(sec.width_mm)}×{int(sec.height_mm)}")
                rows.append([
                    sec.id[-30:],
                    f"{sec.flow_m3h:,.0f}".replace(",", " "),
                    size_str,
                    f"{sec.velocity_m_s:.1f}",
                    f"{sec.pressure_loss_total_pa:.0f}",
                ])
            add_table(rows, col_widths=[6 * cm, 2.5 * cm, 2.5 * cm,
                                         2 * cm, 2 * cm])

    # =================== 10. ТРУБЫ ОТОПЛЕНИЯ ===================
    if "pipes" in include_sections and project.pipe_networks:
        elements.append(Paragraph(
            "10. Подбор труб отопления (гидравлический расчёт)", style_h1))
        from hvac.pipe_sizing import WATER_DENSITY_70C
        elements.append(Paragraph(
            "Подбор по рекомендованным скоростям (СП 60), потери давления — "
            "формула Альтшуля. Точная балансировка стояков — в "
            "Audytor C.O. или MagiCAD.", style_body))
        for sys_name, pnet in sorted(project.pipe_networks.items()):
            pump_m = pnet.total_pressure_loss_pa / (WATER_DENSITY_70C * 9.81)
            elements.append(Paragraph(
                f"{sys_name}: Σ Q = {pnet.total_heat_load_w/1000:.1f} кВт, "
                f"Σ G = {pnet.total_flow_kg_h:.0f} кг/ч, "
                f"Δp = {pnet.total_pressure_loss_pa/1000:.1f} кПа, "
                f"напор насоса ≈ {pump_m:.1f} м", style_h2))
            rows = [["Участок", "Q, Вт", "DN", "v, м/с", "Δp, Па"]]
            for psec in pnet.sections:
                rows.append([
                    psec.id[-30:],
                    f"{psec.heat_load_w:,.0f}".replace(",", " "),
                    f"{int(psec.dn_mm)}",
                    f"{psec.velocity_m_s:.2f}",
                    f"{psec.pressure_loss_total_pa:.0f}",
                ])
            add_table(rows, col_widths=[6 * cm, 3 * cm, 2 * cm,
                                         2 * cm, 2 * cm])

    # =================== 11. ЭНЕРГОПАСПОРТ ===================
    if "energy" in include_sections and project.energy_passport:
        ep = project.energy_passport
        elements.append(Paragraph(
            "11. Энергетический паспорт (СП 50.13330 Прил. Г)", style_h1))
        elements.append(Paragraph(
            f"Тип здания: <b>{ep.building_type}</b>. "
            f"Расчёт удельного годового потребления тепла на отопление "
            "по упрощённому бин-методу на основе ГСОП.", style_body))

        add_kv([
            ["Отапливаемая площадь, м²", f"{ep.total_area_m2:.0f}"],
            ["Объём, м³", f"{ep.total_volume_m3:.0f}"],
            ["ГСОП", f"{ep.gsop_18:.0f}"],
            ["Длительность отопит. сезона, сут", f"{ep.z_heating_days:.0f}"],
            ["Средняя tн за сезон, °C", f"{ep.t_avg_heating}"],
            ["Q пиковая отопления, кВт",
             f"{ep.q_peak_heating_w/1000:.1f}"],
            ["Q пиковая охлаждения, кВт",
             f"{ep.q_peak_cooling_w/1000:.1f}"],
            ["Q пиковая нагрев вент., кВт",
             f"{ep.q_peak_ventilation_heating_w/1000:.1f}"],
            ["Q пиковая ГВС, кВт",
             f"{ep.q_peak_dhw_w/1000:.1f}"],
            ["Годовое отопление, МВт·ч/год",
             f"{ep.e_heating_kwh_year/1000:.1f}"],
            ["Годовое охлаждение (эл.), МВт·ч/год",
             f"{ep.e_cooling_kwh_year/1000:.1f}"],
            ["Годовое ГВС, МВт·ч/год",
             f"{ep.e_dhw_kwh_year/1000:.1f}"],
            ["qh у удельный, кВт·ч/(м²·год)",
             f"{ep.qh_specific_kwh_m2:.1f}"],
            ["qh н нормативный, кВт·ч/(м²·год)",
             f"{ep.qh_normative_kwh_m2:.1f}"],
            ["Отклонение от нормы, %",
             f"{ep.deviation_percent:+.1f}"],
            ["q расч. удельный (отопл.+вент.), Вт/м²",
             f"{ep.q_design_specific_w_m2:.1f}"],
            ["q_ov норматив ШНҚ 2.01.18-24, Вт/м²",
             (f"{ep.q_ov_normative_w_m2:.0f}"
              if ep.q_ov_normative_w_m2 > 0 else "—")],
            ["Соответствие ШНҚ (q ≤ q_ov)",
             (("да" if ep.shnq_compliant else "нет")
              if ep.shnq_compliant is not None else "н/д")],
        ])

        # Класс — крупно
        elements.append(Spacer(1, 6))
        cls_text = (f"<b>КЛАСС ЭНЕРГОЭФФЕКТИВНОСТИ: "
                    f"{ep.energy_class}</b> — {ep.energy_class_description}")
        elements.append(Paragraph(cls_text, ParagraphStyle(
            "ClassRu", parent=style_body, fontName=font_bold,
            fontSize=13, alignment=TA_CENTER,
            backColor=colors.HexColor("#DCE6F1"),
            borderColor=colors.HexColor("#1F4E78"),
            borderWidth=1, borderPadding=8,
        )))

    # =================== 12. ТОЧКА РОСЫ ===================
    if "condensation" in include_sections and project.condensation_results:
        elements.append(Paragraph(
            "12. Проверка ограждений на конденсацию (СП 50.13330 Прил. Е)",
            style_h1))
        from hvac.dew_point import total_problems
        prob = total_problems(project.condensation_results)
        if prob["condensation"] == 0 and prob["normative_fail"] == 0:
            elements.append(Paragraph(
                f"Проверено элементов: {prob['total']}. "
                "Конденсата и нарушений нормативного перепада нет.",
                style_body))
        else:
            elements.append(Paragraph(
                f"Проверено элементов: <b>{prob['total']}</b>. "
                f"Риск конденсации: <b>{prob['condensation']}</b>, "
                f"нарушений СП 50: <b>{prob['normative_fail']}</b>, "
                f"OK: {prob['ok']}.", style_body))

            # Только проблемные элементы
            problem_checks = [c for c in project.condensation_results
                              if c.condensation_risk or c.normative_fail]
            if problem_checks:
                rows = [["Помещение", "Категория", "U", "τ_int", "t_d",
                         "Δt факт", "Запас", "Статус"]]
                for c in problem_checks[:80]:  # ограничение в PDF
                    status = ("КОНД." if c.condensation_risk else "Δt>норм")
                    rows.append([
                        f"{c.space_number}",
                        c.category[:18],
                        f"{c.u_value:.2f}",
                        f"{c.t_surface:.1f}",
                        f"{c.t_dew:.1f}",
                        f"{c.dt_actual:.1f}",
                        f"{c.margin_to_dew:.1f}",
                        status,
                    ])
                if len(problem_checks) > 80:
                    rows.append(["…", f"+ ещё {len(problem_checks) - 80}",
                                 "", "", "", "", "", ""])
                add_table(rows, col_widths=[2.5 * cm, 3.5 * cm,
                                             1.3 * cm, 1.5 * cm, 1.5 * cm,
                                             1.6 * cm, 1.6 * cm, 1.5 * cm])

    # ========================================================================
    # v4.1: Подробная инженерия
    # ========================================================================

    # =================== Психрометрика AHU + i-d диаграмма ===================
    ahu_processes = getattr(project, "ahu_processes", {}) or {}
    if "ahu_process" in include_sections and ahu_processes:
        elements.append(PageBreak())
        elements.append(Paragraph("Психрометрика приточных установок",
                                    style_h1))
        elements.append(Paragraph(
            "Точки процесса обработки воздуха в AHU для трёх режимов работы: "
            "зимнего, летнего и переходного. Расчёт по ASHRAE Handbook of "
            "Fundamentals 2017 (глава 1 — Psychrometrics).", style_body))

        for ahu_name, by_mode in ahu_processes.items():
            elements.append(Paragraph(f"AHU «{ahu_name}»", style_h2))

            # Таблица параметров точек для каждого режима
            for mode_code in ("winter", "transitional", "summer"):
                proc = by_mode.get(mode_code)
                if proc is None:
                    continue
                mode_label = {"winter": "Зима", "summer": "Лето",
                              "transitional": "Межсезонье"}[mode_code]
                elements.append(Paragraph(f"Режим: {mode_label}",
                                            style_body))
                rows = [["Точка", "T, °C", "W, г/кг", "RH, %",
                          "H, кДж/кг", "Td, °C"]]
                for name, st in proc.points.items():
                    rows.append([
                        name,
                        f"{st.t_c:.1f}",
                        f"{st.w_g_kg:.2f}",
                        f"{st.rh * 100:.1f}",
                        f"{st.h_kj_kg:.2f}",
                        f"{st.t_dp_c:.1f}",
                    ])
                add_table(rows, col_widths=[3.5 * cm, 1.6 * cm, 1.8 * cm,
                                             1.5 * cm, 2.0 * cm, 1.6 * cm])
                elements.append(Paragraph(
                    f"Калорифер: {proc.q_heater_kw:.1f} кВт; "
                    f"охладитель: {proc.q_cooler_total_kw:.1f} кВт "
                    f"(явная {proc.q_cooler_sensible_kw:.1f} / "
                    f"скрытая {proc.q_cooler_latent_kw:.1f}); "
                    f"увлажнитель: {proc.q_humidifier_kw:.1f} кВт; "
                    f"конденсат: {proc.condensate_kg_h:.1f} кг/ч.",
                    style_small))
                elements.append(Spacer(1, 4))

            # i-d диаграмма (если matplotlib доступен)
            try:
                import tempfile
                from hvac.psychro_chart import (
                    render_processes_for_ahu, save_id_chart,
                )
                from reportlab.platypus import Image as _RLImage
                fig = render_processes_for_ahu(
                    ahu_processes, ahu_name,
                    modes=("winter", "summer", "transitional"),
                )
                with tempfile.NamedTemporaryFile(
                    suffix=".png", delete=False) as tf:
                    chart_path = tf.name
                save_id_chart(fig, chart_path, dpi=130)
                _temp_image_paths.append(chart_path)
                img = _RLImage(chart_path, width=16 * cm,
                                 height=12 * cm, kind="proportional")
                elements.append(img)
                elements.append(Paragraph(
                    f"Рис. i-d диаграмма процессов в AHU «{ahu_name}»",
                    style_caption))
            except ImportError:
                pass     # matplotlib не установлен — диаграмму пропускаем
            except Exception:
                pass     # любые ошибки рендера не должны валить отчёт

    # =================== Аэродинамика (детально) ===================
    detailed_ducts = getattr(project, "duct_networks_detailed", {}) or {}
    if "duct_detailed" in include_sections and detailed_ducts:
        elements.append(PageBreak())
        elements.append(Paragraph("Аэродинамика воздуховодов (детально)",
                                    style_h1))
        elements.append(Paragraph(
            "Расчёт падения давления по магистрали и определение диктующей "
            "ветви для подбора вентилятора. Местные сопротивления учитываются "
            "по фитингам на каждом участке (АВОК Справочник 5.5).",
            style_body))
        for sys_name, net in detailed_ducts.items():
            elements.append(Paragraph(f"Система «{sys_name}»", style_h2))
            elements.append(Paragraph(
                f"Расход вентилятора: {net.fan_flow_m3_h:,.0f} м³/ч; "
                f"требуемое давление: {net.fan_pressure_required_pa:,.0f} Па "
                f"(c запасом ×{net.fan_safety_factor:.2f}); "
                f"терминалов: {len(net.branches)}.".replace(",", " "),
                style_body))
            rows = [["Участок", "Q, м³/ч", "L, м", "Размер", "v, м/с",
                      "Δp тр., Па", "Δp мест., Па", "Σ, Па"]]
            for e in net.edges.values():
                size = (f"Ø{e.diameter_mm:.0f}" if e.shape == "round"
                        else f"{e.width_mm:.0f}×{e.height_mm:.0f}")
                rows.append([
                    e.edge_id,
                    f"{e.flow_m3_h:.0f}",
                    f"{e.length_m:.1f}",
                    size,
                    f"{e.velocity_m_s:.2f}",
                    f"{e.dp_friction_pa:.1f}",
                    f"{e.dp_local_pa:.1f}",
                    f"{e.dp_total_pa:.1f}",
                ])
            add_table(rows, col_widths=[2.5*cm, 1.7*cm, 1.4*cm,
                                          2.0*cm, 1.4*cm, 1.8*cm,
                                          2.0*cm, 1.6*cm])
            # Балансировка
            if net.branches:
                elements.append(Paragraph("Балансировка ветвей:",
                                            style_body))
                rows = [["Терминал", "Q, м³/ч", "Σ Δp, Па",
                          "Δp балансир., Па"]]
                for b in sorted(net.branches,
                                 key=lambda x: -x.dp_total_pa):
                    rows.append([
                        b.terminal_name,
                        f"{b.flow_m3_h:.0f}",
                        f"{b.dp_total_pa:.1f}",
                        f"{b.balancing_dp_pa:.1f}",
                    ])
                add_table(rows, col_widths=[5*cm, 2.5*cm, 2.5*cm, 3*cm])

    # =================== Гидравлика (насосы и баки) ===================
    hydraulics = getattr(project, "heating_hydraulics_results", {}) or {}
    if "hydraulics" in include_sections and hydraulics:
        elements.append(PageBreak())
        elements.append(Paragraph("Гидравлика отопления", style_h1))
        elements.append(Paragraph(
            "Подбор циркуляционных насосов (Q, H) и мембранных "
            "расширительных баков (ГОСТ 17032 / СП 60.13330 п. 6.4) для "
            "каждого контура отопления.", style_body))
        # Насосы
        elements.append(Paragraph("Подбор насосов", style_h2))
        rows = [["Контур", "Q треб., м³/ч", "H треб., м",
                  "Модель", "Q, м³/ч", "H, м", "P, Вт"]]
        for name, r in hydraulics.items():
            rows.append([
                name,
                f"{r.pump.flow_m3_h:.2f}",
                f"{r.pump.head_m:.2f}",
                r.pump.selected_model or "—",
                f"{r.pump.selected_flow_m3_h:.1f}",
                f"{r.pump.selected_head_m:.1f}",
                f"{r.pump.selected_power_w:.0f}",
            ])
        add_table(rows, col_widths=[3*cm, 2.2*cm, 2.0*cm, 4.5*cm,
                                      1.8*cm, 1.5*cm, 1.5*cm])
        # Баки
        elements.append(Paragraph("Расширительные баки и подпитка",
                                    style_h2))
        rows = [["Контур", "V_сист., л", "ΔV расш., л",
                  "V_бак расч., л", "Бак (модель)",
                  "P_max, бар", "Подпитка, л/сут"]]
        for name, r in hydraulics.items():
            rows.append([
                name,
                f"{r.expansion_tank.system_volume_l:.0f}",
                f"{r.expansion_tank.expansion_volume_l:.1f}",
                f"{r.expansion_tank.required_tank_volume_l:.1f}",
                r.expansion_tank.selected_model or "—",
                f"{r.expansion_tank.p_max_bar:.2f}",
                f"{r.makeup.daily_makeup_l:.1f}",
            ])
        add_table(rows, col_widths=[2.8*cm, 1.7*cm, 1.8*cm, 2.0*cm,
                                      3.5*cm, 1.6*cm, 2.0*cm])

    # =================== Радиаторы ===================
    radiator_picks = getattr(project, "radiator_picks", {}) or {}
    if "radiators" in include_sections and radiator_picks:
        elements.append(PageBreak())
        elements.append(Paragraph("Подбор отопительных приборов",
                                    style_h1))
        elements.append(Paragraph(
            "Подбор приборов отопления выполнен по фактическому "
            "температурному графику с пересчётом номинальной мощности по "
            "формуле EN 442 (Q = Q_ном · (ΔT/50)^n).", style_body))
        rows = [["№", "Помещение", "Q треб., Вт",
                  "Модель", "Размер / секций", "Q факт., Вт", "Запас, %"]]
        total_water_l = 0.0
        for sp in project.spaces:
            pick = radiator_picks.get(sp.space_id)
            if pick is None:
                continue
            if pick.model.is_sectional:
                size = f"{pick.sections} секц. ×{pick.model.height_mm}"
                total_water_l += pick.model.water_volume_l * pick.sections
            else:
                size = f"{pick.model.height_mm}×{pick.model.length_mm}"
                total_water_l += pick.model.water_volume_l
            rows.append([
                sp.number, sp.name,
                f"{sp.heat_loss_w:.0f}",
                pick.model.name,
                size,
                f"{pick.actual_power_w:.0f}",
                f"{pick.margin_pct:.1f}",
            ])
        # Лимит для слишком длинного отчёта
        if len(rows) > 200:
            rows = rows[:200] + [["…", f"+ ещё {len(rows)-200}",
                                    "", "", "", "", ""]]
        add_table(rows, col_widths=[1.5*cm, 4.0*cm, 1.6*cm, 4.2*cm,
                                      2.5*cm, 1.6*cm, 1.4*cm])
        elements.append(Paragraph(
            f"Суммарный объём воды в приборах: {total_water_l:.1f} л",
            style_body))

    # =================== Акустика ===================
    acoustics = getattr(project, "acoustics_results", {}) or {}
    if "acoustics" in include_sections and acoustics:
        elements.append(PageBreak())
        elements.append(Paragraph("Акустика и подбор шумоглушителей",
                                    style_h1))
        elements.append(Paragraph(
            "Расчёт уровня звукового давления в обслуживаемой зоне "
            "(LpA, дБА) и подбор шумоглушителя для достижения норм "
            "СН 2.2.4/2.1.8.562-96 и СП 51.13330. Спектр строится по "
            "октавам 63–8000 Гц с учётом затухания в воздуховодах, "
            "отводах, ответвлениях и в самом помещении.", style_body))
        rows = [["AHU", "Норма Lp, дБА", "Lp расч., дБА",
                  "Запас, дБА", "Шумоглушитель", "Длина, мм",
                  "ΔP, Па"]]
        for name, a in acoustics.items():
            sil = a.silencer_selected
            rows.append([
                name,
                f"{a.lpa_required_dba:.1f}",
                f"{a.lpa_at_terminal:.1f}",
                f"{a.margin_dba:+.1f}",
                sil.name if sil else "—",
                str(sil.length_mm) if sil else "—",
                f"{sil.pressure_drop_pa:.0f}" if sil else "—",
            ])
        add_table(rows, col_widths=[3*cm, 2*cm, 2*cm, 1.7*cm,
                                      4.5*cm, 1.6*cm, 1.4*cm])

    # ========================================================================
    # v4.2: тёплый пол, фанкойлы, VRF
    # ========================================================================

    # =================== Тёплый пол ===================
    underfloor_loops = getattr(project, "underfloor_loops", {}) or {}
    if "underfloor" in include_sections and underfloor_loops:
        elements.append(PageBreak())
        elements.append(Paragraph("Водяной тёплый пол", style_h1))
        elements.append(Paragraph(
            "Расчёт по EN 1264 / СП 60.13330 Прил. Г. Контролируется "
            "температура поверхности (29°C для жилых, 35°C для краевых "
            "зон по EN 1264-2). Длина петли ограничена производителем.",
            style_body))
        rows = [["№", "Помещение", "F, м²", "Q, Вт", "Шаг", "Покр.",
                  "T под/об", "T пов",
                  "L трубы, м", "G, кг/ч", "Замечания"]]
        total_pipe = 0.0
        for sp in project.spaces:
            loop = underfloor_loops.get(sp.space_id)
            if loop is None:
                continue
            total_pipe += loop.pipe_length_m
            warns = "; ".join(loop.warnings)[:60]
            rows.append([
                sp.number, sp.name[:18],
                f"{loop.area_m2:.0f}",
                f"{loop.q_actual_w:.0f}",
                f"{loop.pitch_mm}",
                loop.cover,
                f"{loop.t_supply_c:.0f}/{loop.t_return_c:.0f}",
                f"{loop.t_floor_surface_c:.1f}",
                f"{loop.pipe_length_m:.0f}",
                f"{loop.flow_kg_h:.0f}",
                warns or "—",
            ])
        if len(rows) > 200:
            rows = rows[:200] + [["…", f"+ ещё {len(rows)-200}",
                                    "", "", "", "", "", "", "", "", ""]]
        add_table(rows, col_widths=[1.4 * cm, 2.7 * cm, 1.2 * cm,
                                      1.4 * cm, 1.2 * cm, 1.6 * cm,
                                      1.5 * cm, 1.3 * cm, 1.5 * cm,
                                      1.4 * cm, 3.2 * cm])
        elements.append(Paragraph(
            f"Суммарная длина трубы по всем петлям: {total_pipe:.0f} м",
            style_body))

    # =================== Фанкойлы ===================
    fancoil_picks = getattr(project, "fancoil_picks", {}) or {}
    if "fancoils" in include_sections and fancoil_picks:
        elements.append(PageBreak())
        elements.append(Paragraph("Подбор фанкойлов", style_h1))
        elements.append(Paragraph(
            "Подбор внутренних блоков фанкойлов по EN 1397 с линейным "
            "пересчётом производительности на фактический температурный "
            "напор. Расчётные условия для холода: 27°C DB / 19°C WB / "
            "вода 7/12°C; для тепла: 20°C / вода 60/40°C.", style_body))
        rows = [["№", "Помещение", "Q_х, Вт", "Q_т, Вт",
                  "Модель", "Семейство", "Труб",
                  "Q_х факт., Вт", "Q_т факт., Вт",
                  "Запас_х, %", "L_воздуха"]]
        for sp in project.spaces:
            pick = fancoil_picks.get(sp.space_id)
            if pick is None:
                continue
            rows.append([
                sp.number, sp.name[:18],
                f"{sp.heat_gain_w:.0f}",
                f"{sp.heat_loss_w:.0f}",
                pick.model.name, pick.model.family[:14],
                pick.model.pipes,
                f"{pick.actual_cool_w:.0f}",
                f"{pick.actual_heat_w:.0f}",
                f"{pick.cool_margin_pct:.0f}",
                f"{pick.model.air_flow_m3_h:.0f}",
            ])
        if len(rows) > 200:
            rows = rows[:200] + [["…", f"+ ещё {len(rows)-200}",
                                    "", "", "", "", "", "", "", "", ""]]
        add_table(rows, col_widths=[1.4 * cm, 2.5 * cm, 1.3 * cm,
                                      1.3 * cm, 2.8 * cm, 2.5 * cm,
                                      1.0 * cm, 1.6 * cm, 1.6 * cm,
                                      1.3 * cm, 1.6 * cm])

    # =================== VRF/VRV ===================
    vrf_systems = getattr(project, "vrf_systems", {}) or {}
    if "vrf" in include_sections and vrf_systems:
        elements.append(PageBreak())
        elements.append(Paragraph("VRF / VRV-системы", style_h1))
        elements.append(Paragraph(
            "Подбор внешних и внутренних блоков с проверкой ограничений "
            "производителя: коэффициент соединения, максимальная длина "
            "трасс хладагента, перепад высот. Диаметры медных труб — "
            "по таблице Daikin VRV-IV.", style_body))

        # Сводка систем
        rows = [["Система", "Внешний", "Внутр. блоков", "Σ индекс",
                  "K соед.", "Q_х, кВт", "Q_т, кВт", "Магистр., м",
                  "Δh, м"]]
        for name, sys in vrf_systems.items():
            out_name = sys.outdoor.name if sys.outdoor else "—"
            q_cool = (sys.outdoor.q_cool_w / 1000.0
                      if sys.outdoor else 0.0)
            q_heat = (sys.outdoor.q_heat_w / 1000.0
                      if sys.outdoor else 0.0)
            rows.append([
                name, out_name,
                str(len(sys.indoors)), str(sys.total_indoor_capacity_index),
                f"{sys.combination_ratio:.2f}",
                f"{q_cool:.1f}", f"{q_heat:.1f}",
                f"{sys.main_pipe_length_m:.0f}",
                f"{sys.max_height_diff_m:.0f}",
            ])
        add_table(rows, col_widths=[2.5 * cm, 2.4 * cm, 2.0 * cm,
                                      1.6 * cm, 1.4 * cm, 1.6 * cm,
                                      1.6 * cm, 1.8 * cm, 1.4 * cm])

        # Состав внутренних блоков
        elements.append(Paragraph("Состав внутренних блоков",
                                    style_h2))
        from hvac.vrf import pipe_diameters_by_index
        rows = [["Система", "Помещение", "Внутренний",
                  "Q_х, Вт", "Индекс", "Ø жидк.", "Ø газ"]]
        for name, sys in vrf_systems.items():
            for a in sys.indoors:
                liq, gas = pipe_diameters_by_index(a.indoor.capacity_index)
                rows.append([
                    name, a.space_id or "—",
                    a.indoor.name,
                    f"{a.indoor.q_cool_w:.0f}",
                    a.indoor.capacity_index,
                    f"{liq}", f"{gas}",
                ])
        if len(rows) > 150:
            rows = rows[:150] + [["…", f"+ ещё {len(rows)-150}",
                                    "", "", "", "", ""]]
        add_table(rows, col_widths=[2.0 * cm, 2.0 * cm, 3.2 * cm,
                                      1.6 * cm, 1.4 * cm, 1.6 * cm,
                                      1.4 * cm])

    # =================== Подвал ===================
    elements.append(Spacer(1, 1.5 * cm))
    elements.append(Paragraph(
        "Отчёт сгенерирован автоматически программой HVAC Calculator v4.1. "
        "Результаты основаны на исходных данных, выгруженных из Revit, и "
        "параметрах, заданных пользователем. Окончательные решения требуют "
        "проверки инженером-проектировщиком.", style_caption))

    # Сборка
    doc = SimpleDocTemplate(
        path, pagesize=A4,
        leftMargin=2 * cm, rightMargin=2 * cm,
        topMargin=2 * cm, bottomMargin=2 * cm,
        title=f"ОВиК — {p.project_name}",
        author="HVAC Calculator v3.7",
    )
    doc.build(elements)

    # Удаляем временные PNG-файлы диаграмм после сборки PDF
    import os as _os
    for _path in _temp_image_paths:
        try:
            _os.unlink(_path)
        except OSError:
            pass
