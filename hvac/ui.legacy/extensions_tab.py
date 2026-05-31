# -*- coding: utf-8 -*-
"""Вкладка «11. Расширения» — GUI для функций v3.7.

Содержит под-Notebook с шестью разделами:
  1. Точка росы / конденсация (СП 50 Прил. Е)
  2. ГВС (СП 30.13330)
  3. Энергопаспорт (СП 50 Прил. Г)
  4. Воздуховоды (СП 60 / АВОК)
  5. Трубы отопления (Альтшуль / СП 60)
  6. PDF-отчёт «Пояснительная записка»

Подключение: импортировать `ExtensionsTab` и добавить в `TABS_REGISTRY`.
"""

from __future__ import annotations
import tkinter as tk
import traceback
from tkinter import ttk, filedialog, messagebox

from hvac.ui.tabs import BaseTab


# ===========================================================================
#  Главная вкладка-контейнер
# ===========================================================================


class ExtensionsTab(BaseTab):
    """Вкладка-контейнер для всех расчётов v3.7."""

    title = "11. Расширения"

    def build(self):
        info = ttk.Label(self, text=(
            "Расширения v3.7: ГВС (СП 30), энергопаспорт (СП 50), "
            "воздуховоды (СП 60), трубы (Альтшуль), точка росы (СП 50), "
            "PDF-отчёт. Каждая функция выполняется независимо."
        ), wraplength=900, padding=(10, 8))
        info.pack(fill="x")

        self.notebook = ttk.Notebook(self)
        self.notebook.pack(fill="both", expand=True, padx=10, pady=6)

        self.tab_dew = DewPointSubTab(self.notebook, self.project, self.app)
        self.tab_dhw = DHWSubTab(self.notebook, self.project, self.app)
        self.tab_energy = EnergySubTab(self.notebook, self.project, self.app)
        self.tab_ducts = DuctsSubTab(self.notebook, self.project, self.app)
        self.tab_pipes = PipesSubTab(self.notebook, self.project, self.app)
        self.tab_pdf = PDFSubTab(self.notebook, self.project, self.app)

        self.notebook.add(self.tab_dew, text="Точка росы")
        self.notebook.add(self.tab_dhw, text="ГВС")
        self.notebook.add(self.tab_energy, text="Энергопаспорт")
        self.notebook.add(self.tab_ducts, text="Воздуховоды")
        self.notebook.add(self.tab_pipes, text="Трубы отопления")
        self.notebook.add(self.tab_pdf, text="PDF-отчёт")


# ===========================================================================
#  1. Точка росы
# ===========================================================================


class DewPointSubTab(BaseTab):
    title = "Точка росы"

    def build(self):
        # Параметры
        fr = ttk.LabelFrame(self, text="Параметры проверки")
        fr.pack(fill="x", padx=8, pady=8)

        ttk.Label(fr, text="Относительная влажность внутри:")\
            .grid(row=0, column=0, sticky="e", padx=4, pady=4)
        self.var_rh_override = tk.StringVar(value="0")  # 0 = из таблицы по типу
        ttk.Entry(fr, textvariable=self.var_rh_override, width=10)\
            .grid(row=0, column=1, sticky="w", padx=4)
        ttk.Label(fr, text=" % (0 — брать из таблицы по типу помещения)",
                  foreground="#555").grid(row=0, column=2, sticky="w")

        ttk.Button(fr, text="▶ Проверить ограждения",
                   command=self.do_check).grid(row=1, column=0, padx=4, pady=6,
                                                sticky="w")
        ttk.Button(fr, text="🧹 Очистить",
                   command=self.do_clear).grid(row=1, column=1, padx=4,
                                                 sticky="w")
        self.status_var = tk.StringVar(value="")
        ttk.Label(fr, textvariable=self.status_var, foreground="#1F4E78")\
            .grid(row=1, column=2, sticky="w", padx=8)

        # Итоговая сводка
        sum_fr = ttk.LabelFrame(self, text="Сводка")
        sum_fr.pack(fill="x", padx=8, pady=4)
        self.summary_var = tk.StringVar(
            value="Расчёт не выполнен. Сначала задайте U-значения и расчёт.")
        ttk.Label(sum_fr, textvariable=self.summary_var, wraplength=900,
                  padding=8).pack(fill="x")

        # Таблица
        cols = ("Помещение", "Категория", "Конструкция",
                "U", "tв", "tн", "RH",
                "τ_int", "t_d", "Δt", "Δt_норм", "Запас", "Статус")
        widths = {"Помещение": 130, "Категория": 110, "Конструкция": 200,
                  "U": 50, "tв": 45, "tн": 45, "RH": 50,
                  "τ_int": 60, "t_d": 55, "Δt": 50,
                  "Δt_норм": 60, "Запас": 60, "Статус": 90}
        self.tree = ttk.Treeview(self, columns=cols, show="headings",
                                  height=20)
        for c in cols:
            anchor = "w" if c in ("Помещение", "Категория",
                                  "Конструкция", "Статус") else "e"
            self.tree.heading(c, text=c)
            self.tree.column(c, anchor=anchor, width=widths.get(c, 60))
        # Раскраска
        self.tree.tag_configure("cond", background="#F4B7B6")
        self.tree.tag_configure("norm", background="#FFE69A")
        self.tree.tag_configure("ok",   background="")
        self.tree.pack(fill="both", expand=True, padx=8, pady=4)

    def subscribe_events(self):
        self.project.subscribe("condensation_checked", self.refresh)

    def do_check(self):
        if not self.project.elements:
            messagebox.showwarning("Нет данных", "Сначала загрузите CSV.")
            return
        rh_str = self.var_rh_override.get().strip().replace(",", ".")
        rh_override = None
        try:
            v = float(rh_str)
            if v > 0:
                rh_override = v
        except ValueError:
            pass
        try:
            self.project.check_condensation_risk(rh_override=rh_override)
            self.status_var.set("Проверка выполнена.")
        except Exception as e:
            messagebox.showerror("Ошибка",
                                  f"{e}\n{traceback.format_exc()}")

    def do_clear(self):
        self.project.condensation_results = []
        self.refresh()
        self.status_var.set("")

    def refresh(self):
        from hvac.dew_point import total_problems
        for i in self.tree.get_children():
            self.tree.delete(i)
        checks = self.project.condensation_results
        if not checks:
            self.summary_var.set(
                "Расчёт не выполнен. Сначала задайте U-значения и расчёт.")
            return
        prob = total_problems(checks)
        self.summary_var.set(
            f"Проверено элементов: {prob['total']}. "
            f"Конденсат: {prob['condensation']}, "
            f"Нарушение Δt-норм СП 50: {prob['normative_fail']}, "
            f"OK: {prob['ok']}."
        )
        for c in checks:
            tag = ("cond" if c.condensation_risk
                   else "norm" if c.normative_fail else "ok")
            status = ("КОНДЕНСАТ" if c.condensation_risk
                      else "Δt > норм" if c.normative_fail else "OK")
            self.tree.insert("", "end", tags=(tag,), values=(
                f"{c.space_number} {c.space_name}",
                c.category, c.construction_key,
                f"{c.u_value:.2f}",
                f"{c.t_in:.1f}", f"{c.t_out:.1f}",
                f"{c.rh_in:.0f}",
                f"{c.t_surface:.2f}",
                f"{c.t_dew:.2f}",
                f"{c.dt_actual:.2f}",
                f"{c.dt_normative:.1f}",
                f"{c.margin_to_dew:+.2f}",
                status,
            ))


# ===========================================================================
#  2. ГВС
# ===========================================================================


class DHWSubTab(BaseTab):
    title = "ГВС"

    def build(self):
        fr = ttk.LabelFrame(self, text="Параметры расчёта")
        fr.pack(fill="x", padx=8, pady=8)

        ttk.Label(fr, text="Стратегия систем ГВС:")\
            .grid(row=0, column=0, sticky="e", padx=4, pady=4)
        self.var_strategy = tk.StringVar(value="single")
        cmb = ttk.Combobox(fr, textvariable=self.var_strategy,
                            values=["single", "by_type", "by_zone"],
                            state="readonly", width=15)
        cmb.grid(row=0, column=1, sticky="w", padx=4)
        ttk.Label(fr, text=(
            "single — одна общая система;  "
            "by_type — отдельные на жильё / гост. / офис / питание;  "
            "by_zone — по полю system_heating"),
            foreground="#555").grid(row=0, column=2, sticky="w", padx=8)

        ttk.Button(fr, text="▶ Рассчитать ГВС",
                   command=self.do_calc).grid(row=1, column=0, padx=4, pady=6,
                                               sticky="w")
        self.status_var = tk.StringVar(value="")
        ttk.Label(fr, textvariable=self.status_var, foreground="#1F4E78")\
            .grid(row=1, column=1, columnspan=2, sticky="w", padx=8)

        sum_fr = ttk.LabelFrame(self, text="Итого по проекту")
        sum_fr.pack(fill="x", padx=8, pady=4)
        self.summary_var = tk.StringVar(value="Расчёт не выполнен.")
        ttk.Label(sum_fr, textvariable=self.summary_var, wraplength=900,
                  padding=8).pack(fill="x")

        cols = ("Система", "Тип нагрев.", "Потреб.",
                "V сут, м³", "V час, м³/ч",
                "Q пик, кВт", "Q с цирк., кВт", "Q нагр., кВт",
                "V бака, м³", "Цирк.", "η")
        widths = {"Система": 130, "Тип нагрев.": 100, "Потреб.": 60,
                  "V сут, м³": 80, "V час, м³/ч": 90,
                  "Q пик, кВт": 80, "Q с цирк., кВт": 90,
                  "Q нагр., кВт": 80, "V бака, м³": 70, "Цирк.": 50, "η": 50}
        self.tree = ttk.Treeview(self, columns=cols, show="headings",
                                  height=14)
        for c in cols:
            self.tree.heading(c, text=c)
            self.tree.column(c, anchor=("w" if c in ("Система", "Тип нагрев.",
                                                      "Цирк.") else "e"),
                              width=widths.get(c, 80))
        self.tree.pack(fill="both", expand=True, padx=8, pady=4)

        edit_fr = ttk.Frame(self)
        edit_fr.pack(fill="x", padx=8, pady=4)
        ttk.Label(edit_fr, text="Двойной клик на системе — изменить КПД, "
                                "циркуляцию, тип нагревателя.",
                  foreground="#555").pack(side="left")
        self.tree.bind("<Double-1>", self.on_edit_system)

    def subscribe_events(self):
        self.project.subscribe("dhw_calculated", self.refresh)

    def do_calc(self):
        if not self.project.spaces:
            messagebox.showwarning("Нет данных", "Сначала загрузите CSV.")
            return
        try:
            n = len(self.project.calculate_dhw(
                strategy=self.var_strategy.get()))
            self.status_var.set(f"Рассчитано: {n} систем ГВС.")
        except Exception as e:
            messagebox.showerror("Ошибка",
                                  f"{e}\n{traceback.format_exc()}")

    def refresh(self):
        for i in self.tree.get_children():
            self.tree.delete(i)
        systems = self.project.dhw_systems
        if not systems:
            self.summary_var.set("Расчёт не выполнен.")
            return
        from hvac.dhw import total_dhw_summary
        s = total_dhw_summary(systems)
        self.summary_var.set(
            f"Σ V_сут = {s['v_daily_total_m3']:.2f} м³/сут, "
            f"Σ V_час = {s['v_hourly_max_m3']:.2f} м³/ч, "
            f"Σ Q пик с циркуляцией = {s['q_with_circulation_total_w']/1000:.1f} кВт, "
            f"Σ Q нагревателей = {s['q_heater_total_w']/1000:.1f} кВт, "
            f"Σ V баков = {s['storage_total_m3']:.2f} м³."
        )
        for name, sys in sorted(systems.items()):
            self.tree.insert("", "end", iid=name, values=(
                name, sys.heater_type, sys.n_consumers,
                f"{sys.v_daily_total_m3:.2f}",
                f"{sys.v_hourly_max_m3:.2f}",
                f"{sys.q_peak_w/1000:.1f}",
                f"{sys.q_with_circulation_w/1000:.1f}",
                f"{sys.q_heater_size_w/1000:.1f}",
                f"{sys.storage_recommended_m3:.2f}",
                "да" if sys.has_circulation else "нет",
                f"{sys.efficiency:.2f}",
            ))

    def on_edit_system(self, evt):
        sel = self.tree.selection()
        if not sel:
            return
        sys_name = sel[0]
        sys = self.project.dhw_systems.get(sys_name)
        if not sys:
            return
        DHWSystemEditDialog(self, sys, on_save=self.refresh)


class DHWSystemEditDialog(tk.Toplevel):
    """Модальное окно правки параметров одной системы ГВС."""

    def __init__(self, parent, system, on_save):
        super().__init__(parent)
        self.system = system
        self.on_save = on_save
        self.title(f"Параметры ГВС: {system.name}")
        self.resizable(False, False)

        fr = ttk.Frame(self, padding=10)
        fr.pack(fill="both", expand=True)

        self.vars = {}
        rows = [
            ("Тип нагревателя", "heater_type",
             ["boiler_gas", "boiler_electric", "heat_pump",
              "central", "solar"]),
            ("t гор., °C", "t_hot_c", None),
            ("t хол. зимой, °C", "t_cold_winter_c", None),
            ("t хол. летом, °C", "t_cold_summer_c", None),
            ("η нагревателя", "efficiency", None),
            ("Циркуляция", "has_circulation", "bool"),
            ("Потери на циркуляцию (доля)",
             "circulation_loss_fraction", None),
            ("Аккумулирование", "has_storage", "bool"),
        ]
        for i, (label, attr, opts) in enumerate(rows):
            ttk.Label(fr, text=label).grid(row=i, column=0, sticky="e",
                                            padx=4, pady=3)
            val = getattr(system, attr)
            if opts == "bool":
                v = tk.BooleanVar(value=bool(val))
                ttk.Checkbutton(fr, variable=v).grid(row=i, column=1,
                                                       sticky="w", padx=4)
            elif isinstance(opts, list):
                v = tk.StringVar(value=str(val))
                ttk.Combobox(fr, textvariable=v, values=opts,
                              state="readonly", width=20)\
                    .grid(row=i, column=1, sticky="w", padx=4)
            else:
                v = tk.StringVar(value=str(val))
                ttk.Entry(fr, textvariable=v, width=18)\
                    .grid(row=i, column=1, sticky="w", padx=4)
            self.vars[attr] = (v, opts)

        btns = ttk.Frame(fr)
        btns.grid(row=len(rows), column=0, columnspan=2, pady=8)
        ttk.Button(btns, text="Сохранить", command=self.save).pack(side="left",
                                                                     padx=4)
        ttk.Button(btns, text="Отмена",
                   command=self.destroy).pack(side="left", padx=4)

    def save(self):
        try:
            for attr, (var, opts) in self.vars.items():
                value = var.get()
                if opts == "bool":
                    setattr(self.system, attr, bool(value))
                elif isinstance(opts, list):
                    setattr(self.system, attr, str(value))
                else:
                    setattr(self.system, attr, float(value))
            # Пересчёт системы с новыми параметрами
            from hvac.dhw import (
                calculate_demands, aggregate_to_system,
            )
            # При сохранении достаточно вызвать calculate_dhw заново
            # — но проще не пересчитывать, а просто обновить вид
            if self.on_save:
                self.on_save()
            self.destroy()
        except ValueError as e:
            messagebox.showerror("Ошибка ввода", str(e), parent=self)


# ===========================================================================
#  3. Энергопаспорт
# ===========================================================================


class EnergySubTab(BaseTab):
    title = "Энергопаспорт"

    def build(self):
        fr = ttk.LabelFrame(self, text="Параметры расчёта")
        fr.pack(fill="x", padx=8, pady=8)

        # Тип здания
        ttk.Label(fr, text="Тип здания:").grid(row=0, column=0, sticky="e",
                                                padx=4, pady=3)
        self.var_btype = tk.StringVar(value="(автоопределение)")
        from hvac.energy import BASE_HEATING_NORMS_KWH_M2
        types = ["(автоопределение)"] + list(BASE_HEATING_NORMS_KWH_M2.keys())
        ttk.Combobox(fr, textvariable=self.var_btype, values=types,
                      state="readonly", width=25)\
            .grid(row=0, column=1, sticky="w", padx=4)

        ttk.Label(fr, text="Коэф. регулирования k_рег:")\
            .grid(row=1, column=0, sticky="e", padx=4, pady=3)
        self.var_kreg = tk.StringVar(value="1.0")
        ttk.Entry(fr, textvariable=self.var_kreg, width=10)\
            .grid(row=1, column=1, sticky="w", padx=4)
        ttk.Label(fr, text="(0.85 при ИТП с погодной автоматикой)",
                  foreground="#555").grid(row=1, column=2, sticky="w")

        ttk.Label(fr, text="Коэф. использования внутр. тепл. k_внутр:")\
            .grid(row=2, column=0, sticky="e", padx=4, pady=3)
        self.var_kint = tk.StringVar(value="0.8")
        ttk.Entry(fr, textvariable=self.var_kint, width=10)\
            .grid(row=2, column=1, sticky="w", padx=4)
        ttk.Label(fr, text="(СП 50: 0.8 для типовых режимов)",
                  foreground="#555").grid(row=2, column=2, sticky="w")

        ttk.Label(fr, text="Внутренние теплопост., Вт/м²:")\
            .grid(row=3, column=0, sticky="e", padx=4, pady=3)
        self.var_gain = tk.StringVar(value="10.0")
        ttk.Entry(fr, textvariable=self.var_gain, width=10)\
            .grid(row=3, column=1, sticky="w", padx=4)
        ttk.Label(fr, text="(17 для жилья, 10 для общественных)",
                  foreground="#555").grid(row=3, column=2, sticky="w")

        ttk.Button(fr, text="▶ Построить энергопаспорт",
                   command=self.do_calc).grid(row=4, column=0, padx=4, pady=8,
                                               sticky="w")
        self.status_var = tk.StringVar(value="")
        ttk.Label(fr, textvariable=self.status_var, foreground="#1F4E78")\
            .grid(row=4, column=1, columnspan=2, sticky="w", padx=8)

        # Результат
        self.result_text = tk.Text(self, height=25, wrap="word",
                                    font=("TkDefaultFont", 10))
        self.result_text.pack(fill="both", expand=True, padx=8, pady=4)
        self.result_text.insert("end",
                                 "Расчёт не выполнен. Сначала запустите "
                                 "теплопотери и (желательно) нагрузки от AHU.")
        self.result_text.config(state="disabled")

    def subscribe_events(self):
        self.project.subscribe("energy_passport_calculated", self.refresh)

    def do_calc(self):
        if not self.project.spaces:
            messagebox.showwarning("Нет данных", "Сначала загрузите CSV.")
            return
        try:
            btype = self.var_btype.get()
            btype = None if btype == "(автоопределение)" else btype
            self.project.calculate_energy_passport(
                building_type=btype,
                k_regulation=float(self.var_kreg.get().replace(",", ".")),
                k_internal_use=float(self.var_kint.get().replace(",", ".")),
                internal_gain_w_m2=float(self.var_gain.get().replace(",", ".")),
            )
            self.status_var.set("Энергопаспорт построен.")
        except Exception as e:
            messagebox.showerror("Ошибка",
                                  f"{e}\n{traceback.format_exc()}")

    def refresh(self):
        ep = self.project.energy_passport
        self.result_text.config(state="normal")
        self.result_text.delete("1.0", "end")
        if not ep:
            self.result_text.insert("end", "Расчёт не выполнен.")
            self.result_text.config(state="disabled")
            return
        text = (
            f"═══ ЭНЕРГЕТИЧЕСКИЙ ПАСПОРТ ═══\n"
            f"\n"
            f"Объект: {ep.project_name}\n"
            f"Город: {ep.city}    Тип здания: {ep.building_type}\n"
            f"ГСОП (база +18°C): {ep.gsop_18:.0f} °C·сут\n"
            f"Расчётная зимняя tн: {ep.t_out_heating}°C\n"
            f"Отапливаемая площадь: {ep.total_area_m2:,.0f} м²\n"
            f"Объём: {ep.total_volume_m3:,.0f} м³,    Помещений: {ep.n_spaces}\n"
            f"\n"
            f"--- ПИКОВЫЕ НАГРУЗКИ ---\n"
            f"Q отопления:           {ep.q_peak_heating_w/1000:.1f} кВт\n"
            f"Q охлаждения:          {ep.q_peak_cooling_w/1000:.1f} кВт\n"
            f"Q нагрев приточек:     {ep.q_peak_ventilation_heating_w/1000:.1f} кВт\n"
            f"Q ГВС:                 {ep.q_peak_dhw_w/1000:.1f} кВт\n"
            f"\n"
            f"--- ОТОПИТЕЛЬНЫЙ СЕЗОН ---\n"
            f"Длительность:          {ep.z_heating_days:.0f} сут\n"
            f"Средняя tн за сезон:   {ep.t_avg_heating}°C\n"
            f"Коэф. регулирования:   {ep.k_regulation}\n"
            f"Внутр. теплопост.:     {ep.internal_gain_w_m2} Вт/м²\n"
            f"\n"
            f"--- ГОДОВОЕ ПОТРЕБЛЕНИЕ ---\n"
            f"Отопление:             {ep.e_heating_kwh_year/1000:.1f} МВт·ч/год\n"
            f"Нагрев приточек:       {ep.e_ventilation_kwh_year/1000:.1f} МВт·ч/год\n"
            f"Охлаждение (электр.):  {ep.e_cooling_kwh_year/1000:.1f} МВт·ч/год\n"
            f"ГВС:                   {ep.e_dhw_kwh_year/1000:.1f} МВт·ч/год\n"
            f"Внутр. теплопост.:     "
            f"{ep.e_internal_gains_kwh_year*ep.k_internal_use/1000:.1f} "
            f"МВт·ч/год\n"
            f"\n"
            f"--- УДЕЛЬНЫЕ ПОКАЗАТЕЛИ ---\n"
            f"qh у удельный:         {ep.qh_specific_kwh_m2:.1f} кВт·ч/(м²·год)\n"
            f"qh н нормативный:      {ep.qh_normative_kwh_m2:.1f} кВт·ч/(м²·год)\n"
            f"Отклонение от нормы:   {ep.deviation_percent:+.1f} %\n"
            f"\n"
            f"╔═══════════════════════════════════════════════════════╗\n"
            f"║  КЛАСС ЭНЕРГОЭФФЕКТИВНОСТИ:  {ep.energy_class:<8}                ║\n"
            f"║  {ep.energy_class_description:<54}║\n"
            f"╚═══════════════════════════════════════════════════════╝\n"
        )
        self.result_text.insert("end", text)
        self.result_text.config(state="disabled")


# ===========================================================================
#  4. Воздуховоды
# ===========================================================================


class DuctsSubTab(BaseTab):
    title = "Воздуховоды"

    def build(self):
        fr = ttk.LabelFrame(self, text="Параметры подбора")
        fr.pack(fill="x", padx=8, pady=8)

        ttk.Label(fr, text="Форма:").grid(row=0, column=0, sticky="e",
                                           padx=4, pady=3)
        self.var_shape = tk.StringVar(value="round")
        ttk.Combobox(fr, textvariable=self.var_shape,
                      values=["round", "rect"], state="readonly", width=10)\
            .grid(row=0, column=1, sticky="w", padx=4)
        ttk.Label(fr, text="(круглые / прямоугольные)",
                  foreground="#555").grid(row=0, column=2, sticky="w")

        ttk.Label(fr, text="Тип здания:").grid(row=1, column=0, sticky="e",
                                                padx=4, pady=3)
        self.var_btype = tk.StringVar(value="public")
        ttk.Combobox(fr, textvariable=self.var_btype,
                      values=["public", "residential", "industrial"],
                      state="readonly", width=15)\
            .grid(row=1, column=1, sticky="w", padx=4)
        ttk.Label(fr, text="(для выбора рекоменд. скоростей)",
                  foreground="#555").grid(row=1, column=2, sticky="w")

        ttk.Button(fr, text="▶ Подобрать сечения",
                   command=self.do_calc).grid(row=2, column=0, padx=4, pady=6,
                                               sticky="w")
        self.status_var = tk.StringVar(value="")
        ttk.Label(fr, textvariable=self.status_var, foreground="#1F4E78")\
            .grid(row=2, column=1, columnspan=2, sticky="w", padx=8)

        sum_fr = ttk.LabelFrame(self, text="Сводка")
        sum_fr.pack(fill="x", padx=8, pady=4)
        self.summary_var = tk.StringVar(value="Расчёт не выполнен.")
        ttk.Label(sum_fr, textvariable=self.summary_var, wraplength=900,
                  padding=8).pack(fill="x")

        cols = ("Система", "Тип", "Q, м³/ч", "Размер",
                "v, м/с", "d_гидр", "Δp_тр", "Δp_мест", "Δp_сум", "Комм.")
        widths = {"Система": 220, "Тип": 80, "Q, м³/ч": 80,
                  "Размер": 110, "v, м/с": 60, "d_гидр": 70,
                  "Δp_тр": 70, "Δp_мест": 70, "Δp_сум": 70,
                  "Комм.": 200}
        self.tree = ttk.Treeview(self, columns=cols, show="headings",
                                  height=20)
        for c in cols:
            self.tree.heading(c, text=c)
            self.tree.column(c, anchor=("w" if c in ("Система", "Тип",
                                                      "Размер", "Комм.")
                                          else "e"),
                              width=widths.get(c, 80))
        # Цветовая разметка
        self.tree.tag_configure("trunk", background="#DCE6F1")
        self.tree.tag_configure("branch", background="#EAF1F8")
        self.tree.tag_configure("syshead", background="#1F4E78",
                                  foreground="white")
        self.tree.pack(fill="both", expand=True, padx=8, pady=4)

    def subscribe_events(self):
        self.project.subscribe("ducts_sized", self.refresh)

    def do_calc(self):
        if not self.project.spaces:
            messagebox.showwarning("Нет данных", "Сначала загрузите CSV.")
            return
        if not any(s.supply_m3h or s.exhaust_m3h for s in self.project.spaces):
            messagebox.showwarning("Нет расходов",
                                    "Сначала рассчитайте вентиляцию.")
            return
        try:
            n = len(self.project.size_ducts(
                shape=self.var_shape.get(),
                building_type=self.var_btype.get(),
            ))
            self.status_var.set(f"Рассчитано {n} сетей воздуховодов.")
        except Exception as e:
            messagebox.showerror("Ошибка",
                                  f"{e}\n{traceback.format_exc()}")

    def refresh(self):
        for i in self.tree.get_children():
            self.tree.delete(i)
        nets = self.project.duct_networks
        if not nets:
            self.summary_var.set("Расчёт не выполнен.")
            return
        # Сводка
        total_q = sum(n.total_flow_m3h for n in nets.values())
        max_dp = max((n.total_pressure_loss_pa for n in nets.values()),
                      default=0)
        self.summary_var.set(
            f"Сетей: {len(nets)},  Σ расход = {total_q:,.0f} м³/ч,  "
            f"Макс. Δp для AHU = {max_dp:.0f} Па.".replace(",", " ")
        )
        for sys_name, net in sorted(nets.items()):
            # Заголовок системы
            self.tree.insert("", "end", tags=("syshead",), values=(
                sys_name,
                f"Σ {net.n_terminals} точек",
                f"{net.total_flow_m3h:,.0f}".replace(",", " "),
                "", "", "", "", "",
                f"{net.total_pressure_loss_pa:.0f} Па",
                "← подбор AHU",
            ))
            for sec in net.sections:
                size_str = (f"Ø{int(sec.diameter_mm)}" if sec.shape == "round"
                            else f"{int(sec.width_mm)}×{int(sec.height_mm)}")
                tag = sec.section_type if sec.section_type in (
                    "trunk", "branch") else ""
                self.tree.insert("", "end", tags=(tag,), values=(
                    sec.id, sec.section_type,
                    f"{sec.flow_m3h:,.0f}".replace(",", " "),
                    size_str,
                    f"{sec.velocity_m_s:.2f}",
                    f"{sec.hydraulic_diameter_mm:.0f}",
                    f"{sec.pressure_loss_friction_pa:.1f}",
                    f"{sec.pressure_loss_local_pa:.1f}",
                    f"{sec.pressure_loss_total_pa:.1f}",
                    sec.note,
                ))


# ===========================================================================
#  5. Трубы отопления
# ===========================================================================


class PipesSubTab(BaseTab):
    title = "Трубы отопления"

    def build(self):
        fr = ttk.LabelFrame(self, text="Параметры подбора")
        fr.pack(fill="x", padx=8, pady=8)

        ttk.Label(fr, text="Материал труб:").grid(row=0, column=0, sticky="e",
                                                   padx=4, pady=3)
        self.var_mat = tk.StringVar(value="steel")
        ttk.Combobox(fr, textvariable=self.var_mat,
                      values=["steel", "pex"], state="readonly", width=10)\
            .grid(row=0, column=1, sticky="w", padx=4)
        ttk.Label(fr, text="(сталь ГОСТ 3262 / PEX-Al-PEX)",
                  foreground="#555").grid(row=0, column=2, sticky="w")

        ttk.Button(fr, text="▶ Подобрать трубы",
                   command=self.do_calc).grid(row=1, column=0, padx=4, pady=6,
                                               sticky="w")
        self.status_var = tk.StringVar(value="")
        ttk.Label(fr, textvariable=self.status_var, foreground="#1F4E78")\
            .grid(row=1, column=1, columnspan=2, sticky="w", padx=8)

        sum_fr = ttk.LabelFrame(self, text="Сводка")
        sum_fr.pack(fill="x", padx=8, pady=4)
        self.summary_var = tk.StringVar(value="Расчёт не выполнен.")
        ttk.Label(sum_fr, textvariable=self.summary_var, wraplength=900,
                  padding=8).pack(fill="x")

        cols = ("Участок", "Тип", "Q, Вт", "G, кг/ч", "V, м³/ч",
                "DN", "d_вн", "v, м/с",
                "Δp_тр", "Δp_мест", "Δp_сум", "Комм.")
        widths = {"Участок": 200, "Тип": 80, "Q, Вт": 70,
                  "G, кг/ч": 70, "V, м³/ч": 65,
                  "DN": 45, "d_вн": 55, "v, м/с": 60,
                  "Δp_тр": 70, "Δp_мест": 70, "Δp_сум": 70,
                  "Комм.": 200}
        self.tree = ttk.Treeview(self, columns=cols, show="headings",
                                  height=20)
        for c in cols:
            self.tree.heading(c, text=c)
            self.tree.column(c, anchor=("w" if c in ("Участок", "Тип",
                                                      "Комм.") else "e"),
                              width=widths.get(c, 70))
        self.tree.tag_configure("main", background="#DCE6F1")
        self.tree.tag_configure("branch", background="#EAF1F8")
        self.tree.tag_configure("syshead", background="#1F4E78",
                                  foreground="white")
        self.tree.pack(fill="both", expand=True, padx=8, pady=4)

    def subscribe_events(self):
        self.project.subscribe("pipes_sized", self.refresh)

    def do_calc(self):
        if not self.project.spaces:
            messagebox.showwarning("Нет данных", "Сначала загрузите CSV.")
            return
        if not any(s.heat_loss_w for s in self.project.spaces):
            messagebox.showwarning("Нет теплопотерь",
                                    "Сначала рассчитайте теплопотери.")
            return
        try:
            n = len(self.project.size_pipes(
                pipe_material=self.var_mat.get(),
            ))
            self.status_var.set(f"Рассчитано {n} сетей труб.")
        except Exception as e:
            messagebox.showerror("Ошибка",
                                  f"{e}\n{traceback.format_exc()}")

    def refresh(self):
        from hvac.pipe_sizing import WATER_DENSITY_70C
        for i in self.tree.get_children():
            self.tree.delete(i)
        nets = self.project.pipe_networks
        if not nets:
            self.summary_var.set("Расчёт не выполнен.")
            return
        total_q = sum(n.total_heat_load_w for n in nets.values())
        max_dp = max((n.total_pressure_loss_pa for n in nets.values()),
                      default=0)
        self.summary_var.set(
            f"Сетей: {len(nets)},  Σ нагрузка = {total_q/1000:.1f} кВт,  "
            f"Макс. Δp = {max_dp/1000:.1f} кПа,  "
            f"Макс. напор насоса ≈ {max_dp/(WATER_DENSITY_70C*9.81):.1f} м."
        )
        for sys_name, net in sorted(nets.items()):
            pump_m = net.total_pressure_loss_pa / (WATER_DENSITY_70C * 9.81)
            self.tree.insert("", "end", tags=("syshead",), values=(
                sys_name,
                f"Σ {net.n_terminals} приб.",
                f"{net.total_heat_load_w:,.0f}".replace(",", " "),
                f"{net.total_flow_kg_h:,.0f}".replace(",", " "),
                f"{net.total_flow_kg_h/WATER_DENSITY_70C:.2f}",
                "", "", "",
                "", "",
                f"{net.total_pressure_loss_pa/1000:.1f} кПа",
                f"насос ≈ {pump_m:.1f} м",
            ))
            for sec in net.sections:
                tag = sec.section_type if sec.section_type in (
                    "main", "branch") else ""
                self.tree.insert("", "end", tags=(tag,), values=(
                    sec.id, sec.section_type,
                    f"{sec.heat_load_w:,.0f}".replace(",", " "),
                    f"{sec.flow_kg_h:,.0f}".replace(",", " "),
                    f"{sec.flow_m3_h:.3f}",
                    f"{int(sec.dn_mm)}",
                    f"{sec.inner_diameter_mm:.1f}",
                    f"{sec.velocity_m_s:.2f}",
                    f"{sec.pressure_loss_friction_pa:.1f}",
                    f"{sec.pressure_loss_local_pa:.1f}",
                    f"{sec.pressure_loss_total_pa:.1f}",
                    sec.note,
                ))


# ===========================================================================
#  6. PDF-отчёт
# ===========================================================================


class PDFSubTab(BaseTab):
    title = "PDF-отчёт"

    def build(self):
        info = ttk.Label(self, text=(
            "Сводный PDF-отчёт «Пояснительная записка» по всем выполненным "
            "расчётам. Включаются только те разделы, по которым есть данные. "
            "Можно отметить нужные разделы:"
        ), wraplength=900, padding=(10, 8))
        info.pack(fill="x")

        # Список разделов
        self.sections = [
            ("cover",         "Титульный лист"),
            ("inputs",        "1. Исходные данные"),
            ("constructions", "2. Каталог конструкций"),
            ("heat_loss",     "3. Теплопотери"),
            ("heat_gain",     "4. Теплопоступления"),
            ("ventilation",   "5. Вентиляция"),
            ("dhw",           "6. ГВС"),
            ("equipment",     "7. Системы оборудования"),
            ("smoke",         "8. Дымоудаление"),
            ("ducts",         "9. Воздуховоды"),
            ("pipes",         "10. Трубы отопления"),
            ("energy",        "11. Энергопаспорт"),
            ("condensation",  "12. Точка росы"),
        ]
        self.section_vars = {}
        cb_fr = ttk.LabelFrame(self, text="Разделы")
        cb_fr.pack(fill="x", padx=10, pady=4)
        # В 2 колонки
        for i, (key, label) in enumerate(self.sections):
            v = tk.BooleanVar(value=True)
            self.section_vars[key] = v
            row = i // 2
            col = i % 2
            ttk.Checkbutton(cb_fr, text=label, variable=v)\
                .grid(row=row, column=col, sticky="w", padx=10, pady=2)

        ttk.Button(self, text="📄 Сгенерировать PDF и сохранить…",
                   command=self.do_export).pack(padx=10, pady=8, anchor="w")

        self.status_var = tk.StringVar(value="")
        ttk.Label(self, textvariable=self.status_var, foreground="#1F4E78",
                  wraplength=900, padding=(10, 4)).pack(fill="x")

        ttk.Label(self, text=(
            "Совет: запустите все нужные расчёты (теплопотери, вентиляция, "
            "ГВС, энергопаспорт и т.д.) перед формированием отчёта."
        ), wraplength=900, foreground="#555", padding=(10, 4)).pack(fill="x")

    def do_export(self):
        path = filedialog.asksaveasfilename(
            defaultextension=".pdf", filetypes=[("PDF", "*.pdf")],
            initialfile=f"Отчёт_{self.project.params.project_name}.pdf")
        if not path:
            return
        sections = [k for k, v in self.section_vars.items() if v.get()]
        if not sections:
            messagebox.showwarning("Нет разделов",
                                    "Выберите хотя бы один раздел.")
            return
        try:
            from hvac.io_pdf import export_to_pdf
            export_to_pdf(self.project, path, include_sections=sections)
            self.status_var.set(f"PDF сохранён: {path}")
            messagebox.showinfo("Готово", f"PDF сохранён:\n{path}")
        except Exception as e:
            messagebox.showerror("Ошибка PDF",
                                  f"{e}\n{traceback.format_exc()}")
