# -*- coding: utf-8 -*-
"""Листы подробной инженерии v4.1/v4.2: психрометрика AHU, аэродинамика,
насосы и баки, радиаторы, акустика, тёплый пол, фанкойлы, VRF."""
from __future__ import annotations

from hvac.io_excel._common import style_header, autofit, sum_fill, sum_font


def write_detailed_sheets(wb, project) -> None:
    # ====================================================================
    # ===== Расширения v4.1: подробная инженерия =====
    # ====================================================================

    # ===== Психрометрика AHU =====
    if getattr(project, "ahu_processes", None):
        ws = wb.create_sheet("Психрометрика AHU")
        headers = ["AHU", "Режим", "Точка процесса",
                   "T, °C", "W, г/кг", "RH, %", "H, кДж/кг", "Td, °C"]
        ws.append(headers)
        style_header(ws[1])
        # Сводка мощностей по режимам в начале листа
        for ahu_name, by_mode in project.ahu_processes.items():
            for mode in ("winter", "transitional", "summer"):
                proc = by_mode.get(mode)
                if proc is None:
                    continue
                for point_name, st in proc.points.items():
                    ws.append([
                        ahu_name, mode, point_name,
                        round(st.t_c, 1),
                        round(st.w_g_kg, 2),
                        round(st.rh * 100, 1),
                        round(st.h_kj_kg, 2),
                        round(st.t_dp_c, 1),
                    ])
                # Строка-итог мощностей
                ws.append([
                    ahu_name, mode, "Σ мощность",
                    "", "", "",
                    (f"Калорифер {proc.q_heater_kw:.1f} кВт; "
                     f"Охладитель {proc.q_cooler_total_kw:.1f} кВт "
                     f"(явная {proc.q_cooler_sensible_kw:.1f} / "
                     f"скрытая {proc.q_cooler_latent_kw:.1f}); "
                     f"Увлажнитель {proc.q_humidifier_kw:.1f} кВт"),
                    "",
                ])
                last = ws.max_row
                for c in ws[last]:
                    c.fill = sum_fill
                    c.font = sum_font
        autofit(ws, len(headers))

    # ===== Аэродинамика воздуховодов (детальная) =====
    if getattr(project, "duct_networks_detailed", None):
        ws = wb.create_sheet("Аэродинамика (детально)")
        headers = ["Система", "Участок", "Родитель", "Назначение",
                   "L, м³/ч", "Дл., м", "Форма", "Размер, мм",
                   "v, м/с", "Δp тр., Па", "Δp мест., Па", "Σ Δp, Па"]
        ws.append(headers)
        style_header(ws[1])
        for name, net in project.duct_networks_detailed.items():
            for e in net.edges.values():
                size = (f"Ø{e.diameter_mm:.0f}" if e.shape == "round"
                        else f"{e.width_mm:.0f}×{e.height_mm:.0f}")
                ws.append([
                    name, e.edge_id, e.parent_id or "(корень)",
                    e.terminal_name or "проход",
                    round(e.flow_m3_h, 0),
                    round(e.length_m, 1),
                    e.shape, size,
                    round(e.velocity_m_s, 2),
                    round(e.dp_friction_pa, 1),
                    round(e.dp_local_pa, 1),
                    round(e.dp_total_pa, 1),
                ])
            # Сводка по вентилятору
            ws.append([
                name, "ИТОГО", "", "ветви: " + str(len(net.branches)),
                round(net.fan_flow_m3_h, 0), "", "", "",
                "—",
                "—", "—",
                round(net.fan_pressure_required_pa, 0),
            ])
            last = ws.max_row
            for c in ws[last]:
                c.fill = sum_fill
                c.font = sum_font
        autofit(ws, len(headers))

    # ===== Насосы и расширительные баки =====
    if getattr(project, "heating_hydraulics_results", None):
        ws = wb.create_sheet("Насосы и баки")
        headers = ["Контур", "Q, м³/ч", "H, м",
                   "Насос (модель)", "Q насоса", "H насоса", "P, Вт",
                   "Объём системы, л", "ΔV расш., л",
                   "Объём бака расч., л", "Бак модель",
                   "P_max, бар", "P_init, бар", "Подпитка, л/сут"]
        ws.append(headers)
        style_header(ws[1])
        for name, r in project.heating_hydraulics_results.items():
            ws.append([
                name,
                round(r.pump.flow_m3_h, 2),
                round(r.pump.head_m, 2),
                r.pump.selected_model or "—",
                round(r.pump.selected_flow_m3_h, 2),
                round(r.pump.selected_head_m, 2),
                round(r.pump.selected_power_w, 0),
                round(r.expansion_tank.system_volume_l, 1),
                round(r.expansion_tank.expansion_volume_l, 1),
                round(r.expansion_tank.required_tank_volume_l, 1),
                r.expansion_tank.selected_model or "—",
                round(r.expansion_tank.p_max_bar, 2),
                round(r.expansion_tank.p_init_bar, 2),
                round(r.makeup.daily_makeup_l, 1),
            ])
        autofit(ws, len(headers))

    # ===== Радиаторы по помещениям =====
    if getattr(project, "radiator_picks", None):
        ws = wb.create_sheet("Радиаторы")
        headers = ["№ помещ.", "Название", "Уровень", "Q треб., Вт",
                   "Модель", "Семейство",
                   "Высота, мм", "Длина, мм",
                   "Секций", "Q факт., Вт", "Запас, %", "V воды, л"]
        ws.append(headers)
        style_header(ws[1])
        for sp in project.spaces:
            pick = project.radiator_picks.get(sp.space_id)
            if pick is None:
                continue
            v_water = (pick.model.water_volume_l * pick.sections
                       if pick.model.is_sectional
                       else pick.model.water_volume_l)
            ws.append([
                sp.number, sp.name, sp.level,
                round(sp.heat_loss_w, 0),
                pick.model.name, pick.model.family,
                pick.model.height_mm, pick.model.length_mm,
                pick.sections if pick.model.is_sectional else "—",
                round(pick.actual_power_w, 0),
                round(pick.margin_pct, 1),
                round(v_water, 2),
            ])
        # Сводка: Σ воды
        if project.radiator_picks:
            total_water = 0.0
            for sp in project.spaces:
                pick = project.radiator_picks.get(sp.space_id)
                if pick is None:
                    continue
                vv = (pick.model.water_volume_l * pick.sections
                      if pick.model.is_sectional
                      else pick.model.water_volume_l)
                total_water += vv
            ws.append(["ИТОГО", "", "", "", "", "", "", "", "",
                       "", "", round(total_water, 1)])
            last = ws.max_row
            for c in ws[last]:
                c.fill = sum_fill
                c.font = sum_font
        autofit(ws, len(headers))

    # ===== Акустика =====
    if getattr(project, "acoustics_results", None):
        ws = wb.create_sheet("Акустика")
        headers = ["AHU", "Норма Lp, дБА", "Расчёт Lp, дБА", "Запас, дБА",
                   "Глушитель нужен?", "Глушитель", "Длина, мм",
                   "ΔP глушителя, Па"]
        ws.append(headers)
        style_header(ws[1])
        for name, a in project.acoustics_results.items():
            sil = a.silencer_selected
            ws.append([
                name,
                round(a.lpa_required_dba, 1),
                round(a.lpa_at_terminal, 1),
                round(a.margin_dba, 1),
                "Да" if a.silencer_required else "Нет",
                sil.name if sil else "—",
                sil.length_mm if sil else "—",
                round(sil.pressure_drop_pa, 0) if sil else "—",
            ])
        autofit(ws, len(headers))

    # ===== Тёплый пол =====
    if getattr(project, "underfloor_loops", None):
        ws = wb.create_sheet("Тёплый пол")
        headers = ["№", "Помещение", "Уровень", "Площадь, м²", "Q треб., Вт",
                    "Шаг, мм", "Покрытие", "Зона",
                    "T под./об., °C", "T пов., °C", "Лимит T, °C",
                    "Q факт., Вт/м²", "Q факт., Вт",
                    "Длина трубы, м", "G, кг/ч", "Δp, кПа",
                    "Трубка", "Замечания"]
        ws.append(headers)
        style_header(ws[1])
        total_pipe_m = 0.0
        for sp in project.spaces:
            loop = project.underfloor_loops.get(sp.space_id)
            if loop is None:
                continue
            total_pipe_m += loop.pipe_length_m
            ws.append([
                sp.number, sp.name, sp.level,
                round(loop.area_m2, 1),
                round(loop.q_required_w, 0),
                loop.pitch_mm, loop.cover, loop.zone,
                f"{loop.t_supply_c:.0f}/{loop.t_return_c:.0f}",
                round(loop.t_floor_surface_c, 1),
                round(loop.t_floor_limit_c, 1),
                round(loop.q_actual_w_m2, 1),
                round(loop.q_actual_w, 0),
                round(loop.pipe_length_m, 1),
                round(loop.flow_kg_h, 1),
                round(loop.pressure_drop_kpa, 1),
                loop.pipe.name if loop.pipe else "—",
                "; ".join(loop.warnings) or "—",
            ])
        if project.underfloor_loops:
            ws.append(["ИТОГО", "", "", "", "", "", "", "", "", "", "",
                        "", "", round(total_pipe_m, 0), "", "", "", ""])
            last = ws.max_row
            for c in ws[last]:
                c.fill = sum_fill
                c.font = sum_font
        autofit(ws, len(headers))

    # ===== Фанкойлы по помещениям =====
    if getattr(project, "fancoil_picks", None):
        ws = wb.create_sheet("Фанкойлы")
        headers = ["№", "Помещение", "Q_холод треб., Вт", "Q_тепло треб., Вт",
                    "Модель", "Семейство", "Труб",
                    "Q_холод факт., Вт", "Q_тепло факт., Вт",
                    "Запас холод, %", "Запас тепло, %",
                    "Воздух, м³/ч", "Шум, дБА"]
        ws.append(headers)
        style_header(ws[1])
        for sp in project.spaces:
            pick = project.fancoil_picks.get(sp.space_id)
            if pick is None:
                continue
            ws.append([
                sp.number, sp.name,
                round(sp.heat_gain_w, 0),
                round(sp.heat_loss_w, 0),
                pick.model.name, pick.model.family, pick.model.pipes,
                round(pick.actual_cool_w, 0),
                round(pick.actual_heat_w, 0),
                round(pick.cool_margin_pct, 1),
                round(pick.heat_margin_pct, 1),
                round(pick.model.air_flow_m3_h, 0),
                round(pick.model.noise_db_a, 0),
            ])
        autofit(ws, len(headers))

    # ===== VRF/VRV =====
    if getattr(project, "vrf_systems", None):
        ws = wb.create_sheet("VRF")
        # Сводка систем
        headers = ["Система", "Внешний блок", "Внутренних блоков",
                    "Σ индекс", "K соединения",
                    "Q_холод (кат), кВт", "Q_тепло (кат), кВт",
                    "Q_холод корр., кВт",
                    "Магистраль, м", "Макс. до внутреннего, м",
                    "Δh, м", "Корректировка"]
        ws.append(headers)
        style_header(ws[1])
        for name, sys in project.vrf_systems.items():
            out_name = sys.outdoor.name if sys.outdoor else "—"
            q_cool_cat = (sys.outdoor.q_cool_w / 1000.0
                          if sys.outdoor else 0.0)
            q_heat_cat = (sys.outdoor.q_heat_w / 1000.0
                          if sys.outdoor else 0.0)
            ws.append([
                name, out_name,
                len(sys.indoors), sys.total_indoor_capacity_index,
                round(sys.combination_ratio, 2),
                round(q_cool_cat, 1), round(q_heat_cat, 1),
                round(sys.corrected_cool_w / 1000.0, 1),
                round(sys.main_pipe_length_m, 0),
                round(sys.max_pipe_length_to_indoor_m, 0),
                round(sys.max_height_diff_m, 0),
                round(sys.capacity_correction_factor, 3),
            ])
        autofit(ws, len(headers))

        # Внутренние блоки и медные трубы — следующая страница / диапазон
        ws2 = wb.create_sheet("VRF внутренние блоки")
        headers2 = ["Система", "Помещение", "Внутренний блок",
                    "Семейство", "Индекс",
                    "Q_холод, Вт", "Q_тепло, Вт",
                    "Длина трассы, м",
                    "Ø жидкость, мм", "Ø газ, мм"]
        ws2.append(headers2)
        style_header(ws2[1])
        from hvac.vrf import pipe_diameters_by_index
        for name, sys in project.vrf_systems.items():
            for a in sys.indoors:
                liq, gas = pipe_diameters_by_index(a.indoor.capacity_index)
                ws2.append([
                    name,
                    a.space_id or "—",
                    a.indoor.name, a.indoor.family,
                    a.indoor.capacity_index,
                    round(a.indoor.q_cool_w, 0),
                    round(a.indoor.q_heat_w, 0),
                    round(a.pipe_length_m or
                          sys.max_pipe_length_to_indoor_m, 1),
                    liq, gas,
                ])
        autofit(ws2, len(headers2))
