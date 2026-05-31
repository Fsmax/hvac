# -*- coding: utf-8 -*-
"""Вкладки GUI. Каждая вкладка — свой класс, наследник BaseTab.

Это позволяет:
- редактировать одну вкладку, не влияя на другие;
- легко добавлять новые вкладки (наследовать BaseTab, добавить в TABS_REGISTRY);
- тестировать UI-логику отдельно от рендеринга.
"""

from __future__ import annotations
import os
import tkinter as tk
import traceback
from tkinter import ttk, filedialog, messagebox
from typing import Dict, Optional

from hvac.project import HVACProject
from hvac.catalogs.climate import CLIMATE_DB
from hvac.catalogs.room_types import (
    ROOM_TYPE_PRESETS, apply_room_type_defaults, get_all_room_types,
)
from hvac.engine import list_engines
from hvac.reports import list_charts, draw_chart


# Проверка наличия matplotlib (для вкладки графиков)
_MPL_AVAILABLE = False
try:
    import matplotlib
    matplotlib.use("TkAgg")
    from matplotlib.figure import Figure
    from matplotlib.backends.backend_tkagg import (
        FigureCanvasTkAgg, NavigationToolbar2Tk
    )
    _MPL_AVAILABLE = True
except Exception:
    pass


# ===========================================================================
#  Базовый класс вкладки
# ===========================================================================


class BaseTab(ttk.Frame):
    """Каждая вкладка — Frame с привязкой к HVACProject."""

    title = "Вкладка"

    def __init__(self, parent, project: HVACProject, app):
        super().__init__(parent)
        self.project = project
        self.app = app
        self.build()
        self.subscribe_events()

    def build(self) -> None:
        """Создаёт виджеты вкладки."""

    def subscribe_events(self) -> None:
        """Подписка на события проекта (override в подклассах)."""

    def on_show(self) -> None:
        """Вызывается при переключении на вкладку."""


# ===========================================================================
#  Вкладка 1. Данные
# ===========================================================================


class DataTab(BaseTab):
    title = "1. Данные"

    def build(self):
        self.var_spaces = tk.StringVar()
        self.var_thermal = tk.StringVar()
        self.info_var = tk.StringVar(value="Файлы не загружены.")

        fr = ttk.LabelFrame(self, text="Файлы CSV из Revit/Dynamo")
        fr.pack(fill="x", padx=10, pady=10)

        def browse(var):
            path = filedialog.askopenfilename(
                filetypes=[("CSV", "*.csv"), ("Все файлы", "*.*")])
            if path:
                var.set(path)

        ttk.Label(fr, text="spaces.csv:").grid(row=0, column=0, sticky="w", padx=5, pady=4)
        ttk.Entry(fr, textvariable=self.var_spaces, width=80).grid(row=0, column=1, padx=5)
        ttk.Button(fr, text="Обзор…",
                   command=lambda: browse(self.var_spaces)).grid(row=0, column=2, padx=5)

        ttk.Label(fr, text="thermal_all.csv:").grid(row=1, column=0, sticky="w", padx=5, pady=4)
        ttk.Entry(fr, textvariable=self.var_thermal, width=80).grid(row=1, column=1, padx=5)
        ttk.Button(fr, text="Обзор…",
                   command=lambda: browse(self.var_thermal)).grid(row=1, column=2, padx=5)

        ttk.Label(self, textvariable=self.info_var, foreground="#1F4E78",
                  font=("Segoe UI", 10, "bold"), wraplength=1100,
                  justify="left").pack(pady=6, anchor="w", padx=10)

        ttk.Button(self, text="Загрузить CSV", command=self.do_load).pack(pady=6)
        ttk.Button(self, text="🔍 Проверить данные…",
                   command=self.show_validation).pack(pady=2)

        legend = (
            "Возможности программы v3.0:\n"
            "  •  Расчётный движок: СП 50.13330 (расширяется новыми методиками)\n"
            "  •  Встроенная БД климата (>100 городов СНГ)\n"
            "  •  Сохранение проекта в JSON, экспорт в Excel, обратно в Revit\n"
            "  •  Поиск/фильтр, массовое редактирование, графики\n"
            "  •  Валидация данных (предупреждения о пустых U, нулевых объёмах)\n\n"
            "Порядок работы: 1) Загрузить CSV → 2) Выбрать город → 3) U-значения →\n"
            "→ 4) Уточнить помещения → 5) Расчёт → 6) Графики / Excel / в Revit."
        )
        ttk.Label(self, text=legend, justify="left",
                  foreground="#555555").pack(anchor="w", padx=10, pady=10)

    def show_validation(self):
        """Окно со списком всех предупреждений валидации."""
        if not self.project.spaces:
            messagebox.showinfo("Информация", "Сначала загрузите данные.")
            return
        results = self.project.validate_detailed()
        if not results:
            messagebox.showinfo("Проверка", "Проблем не обнаружено ✓")
            return

        win = tk.Toplevel(self)
        win.title("Проверка данных проекта")
        win.geometry("900x500")

        from collections import Counter
        by_sev = Counter(r["severity"] for r in results)
        summary = f"Всего: {len(results)}"
        if by_sev.get("error"):
            summary += f"   |   Ошибок: {by_sev['error']}"
        if by_sev.get("warning"):
            summary += f"   |   Предупреждений: {by_sev['warning']}"
        if by_sev.get("info"):
            summary += f"   |   Информации: {by_sev['info']}"
        ttk.Label(win, text=summary, font=("Segoe UI", 10, "bold"),
                  foreground="#1F4E78").pack(anchor="w", padx=10, pady=8)

        cols = ("Серьёзность", "Категория", "Сообщение", "Помещение")
        tree = ttk.Treeview(win, columns=cols, show="headings", height=18)
        widths = {"Серьёзность": 90, "Категория": 110, "Сообщение": 500,
                  "Помещение": 150}
        for c in cols:
            tree.heading(c, text=c)
            tree.column(c, anchor="w", width=widths[c])
        tree.pack(fill="both", expand=True, padx=10, pady=4)

        tree.tag_configure("error", background="#FCE5E5")
        tree.tag_configure("warning", background="#FFF4D6")
        tree.tag_configure("info", background="#E8F0F8")

        sev_text = {"error": "Ошибка", "warning": "Внимание", "info": "Инфо"}
        for r in results:
            sp = self.project.get_space(r.get("space_id", ""))
            sp_label = f"{sp.number} {sp.name}" if sp else "—"
            tree.insert("", "end", tags=(r["severity"],), values=(
                sev_text.get(r["severity"], r["severity"]),
                r["category"], r["msg"], sp_label))

        ttk.Button(win, text="Закрыть", command=win.destroy).pack(pady=8)

    def do_load(self):
        try:
            keep = bool(self.project.spaces)
            self.project.load(self.var_spaces.get(), self.var_thermal.get(),
                              keep_user_settings=keep)
        except Exception as e:
            messagebox.showerror("Ошибка загрузки",
                                 f"{e}\n\n{traceback.format_exc()}")
            return

        has_or = sum(1 for e in self.project.elements
                     if e.is_exterior and e.orientation_deg is not None)
        total = sum(1 for e in self.project.elements if e.is_exterior)
        status = ""
        if total:
            pct = 100.0 * has_or / total
            if pct > 80:
                status = f" ✓ Ориентация определена ({pct:.0f}%)."
            elif pct > 0:
                status = f" ⚠ Ориентация частично ({pct:.0f}%)."
            else:
                status = " ⚠ Ориентация не определена — обновите Dynamo-скрипт."

        warns = self.project.validate()
        warn_str = ""
        if warns:
            warn_str = "\n⚠ " + "; ".join(warns)

        self.info_var.set(
            f"Загружено: помещений — {len(self.project.spaces)}, "
            f"элементов ограждений — {len(self.project.elements)}, "
            f"конструкций — {len(self.project.constructions)}.{status}{warn_str}"
        )


# ===========================================================================
#  Вкладка 2. Параметры
# ===========================================================================


class ParamsTab(BaseTab):
    title = "2. Параметры"

    def build(self):
        # --- БД климата ---
        fr1 = ttk.LabelFrame(self, text="База климата СП 131.13330")
        fr1.pack(fill="x", padx=10, pady=10)

        ttk.Label(fr1, text="Город:").grid(row=0, column=0, sticky="w", padx=5)
        self.city_var = tk.StringVar()
        ttk.Combobox(fr1, textvariable=self.city_var, width=35,
                     values=sorted(CLIMATE_DB.keys())).grid(row=0, column=1, padx=5)
        ttk.Button(fr1, text="Применить",
                   command=self._apply_city).grid(row=0, column=2, padx=5)

        self.climate_info = tk.StringVar(
            value="(выберите город — климат подставится автоматически)")
        ttk.Label(fr1, textvariable=self.climate_info,
                  foreground="#1F4E78", wraplength=900, justify="left"
                  ).grid(row=1, column=0, columnspan=3, sticky="w", padx=5)

        # --- Ручные параметры ---
        fr2 = ttk.LabelFrame(self, text="Параметры (можно вводить вручную)")
        fr2.pack(fill="x", padx=10, pady=10)

        # Основные климатические/расчётные параметры
        self.fields = [
            ("project_name", "Название проекта", "str", None),
            ("t_out_heating", "Расч. наружная зимой, °C", "float", None),
            ("t_out_cooling", "Расч. наружная летом, °C", "float", None),
            ("daily_amplitude", "Суточная амплитуда летом, K", "float", None),
            ("solar_intensity_w_m2", "Пиковая солнечная радиация, Вт/м²", "float", None),
            ("gsop_18", "ГСОП (база 18°C)", "float", None),
            ("inf_correction_k", "Коэф. инфильтрации k", "float", None),
            ("safety_margin_heating", "Запас на отопление (×)", "float", None),
            ("safety_margin_cooling", "Запас на охлаждение (×)", "float", None),
            # Влагосодержание для скрытой нагрузки осушения
            ("w_in_summer_g_kg", "Влагосод. внутр. летом, г/кг", "float",
                "Цель в помещении: ~9.3 при 24°C/50% RH"),
            ("w_out_summer_g_kg", "Влагосод. наружн. летом, г/кг", "float",
                "Сухой климат (Ташкент) ≈ 7-8;  влажный (Сочи) ≈ 16-20"),
            # ----- Солнце и окна (КРИТИЧНО для летнего пика!) -----
            ("solar_shading_factor", "Затенение солнца (× к радиации)", "float",
                "1.0 = без затенения, 0.7 = жалюзи/тонировка, "
                "0.5 = маркизы/козырьки/балконы, 0.3 = глубокие ниши + жалюзи"),
            ("true_north_offset_deg", "Поворот True North, °",  "float",
                "0 = ориентации из Revit как есть. +45 = стрелка N на плане "
                "в верх-лево (против часовой). Применяется к солнечному расчёту."),
            ("wwr_estimate", "WWR — доля окон в стене (если нет реальных)", "float",
                "0 = только реальные окна из Revit. 0.3 = моделировать 30% "
                "стены как окно. Если есть реальные окна — оставьте 0!"),
            ("wwr_u_window", "WWR: U виртуального окна", "float",
                "Только при wwr_estimate>0. Типично 1.5-2.5"),
            ("wwr_shgc", "WWR: SHGC виртуального окна", "float",
                "Только при wwr_estimate>0. Типично 0.3-0.6"),
        ]
        self.p_vars: Dict[str, tk.Variable] = {}
        # Разделители между блоками (по индексам полей)
        section_breaks = {9, 11}  # перед влагосод. / перед солнцем
        section_titles = {
            9: "─── Влажность (для летней скрытой нагрузки) ───",
            11: "─── Солнце и WWR (часто причина завышения!) ───",
        }
        row_offset = 0
        for i, item in enumerate(self.fields):
            key, label, kind, tooltip = item
            if i in section_breaks:
                ttk.Label(fr2, text=section_titles[i],
                          foreground="#A00000",
                          font=("Segoe UI", 9, "bold")
                          ).grid(row=i + row_offset, column=0, columnspan=3,
                                  sticky="w", padx=5, pady=(8, 2))
                row_offset += 1
            r = i + row_offset
            ttk.Label(fr2, text=label).grid(row=r, column=0, sticky="w",
                                              padx=5, pady=2)
            v = tk.StringVar(value=str(getattr(self.project.params, key)))
            ttk.Entry(fr2, textvariable=v, width=18).grid(row=r, column=1,
                                                            padx=5, pady=2,
                                                            sticky="w")
            if tooltip:
                ttk.Label(fr2, text=tooltip, foreground="#666",
                          font=("Segoe UI", 8)
                          ).grid(row=r, column=2, sticky="w", padx=8)
            self.p_vars[key] = v

        last_row = len(self.fields) + len(section_breaks)
        ttk.Label(fr2, text="Методика:").grid(row=last_row, column=0,
                                                sticky="w", padx=5,
                                                pady=(8, 2))
        self.method_var = tk.StringVar(value=self.project.params.methodology)
        ttk.Combobox(fr2, textvariable=self.method_var, width=28,
                     state="readonly", values=list_engines()
                     ).grid(row=last_row, column=1, sticky="w", padx=5, pady=2)

        ttk.Button(fr2, text="Применить параметры",
                   command=self._apply_params
                   ).grid(row=last_row + 1, column=0, columnspan=3, pady=8)

        # --- Сводка ---
        fr3 = ttk.LabelFrame(self, text="Сводка")
        fr3.pack(fill="both", expand=True, padx=10, pady=5)
        self.summary = tk.Text(fr3, height=12, font=("Consolas", 10))
        self.summary.pack(fill="both", expand=True)

    def subscribe_events(self):
        self.project.subscribe("data_loaded", self._refresh_summary)
        self.project.subscribe("project_loaded", self._on_project_loaded)
        self.project.subscribe("calculation_done", self._refresh_summary)

    def _apply_city(self):
        c = self.city_var.get().strip()
        if not c:
            return
        if not self.project.params.apply_city(c):
            messagebox.showwarning("Не найдено",
                                   f"Город «{c}» не в БД. Введите параметры вручную.")
            return
        self._sync_fields()
        p = self.project.params
        self.climate_info.set(
            f"{c}: tн зим={p.t_out_heating}°C, tн лет={p.t_out_cooling}°C, "
            f"амплитуда={p.daily_amplitude}K, I_солн={p.solar_intensity_w_m2} Вт/м², "
            f"ГСОП={p.gsop_18}"
        )

    def _apply_params(self):
        try:
            for key, _, kind, _ in self.fields:
                val = self.p_vars[key].get()
                if kind == "float":
                    val = float(val.replace(",", "."))
                setattr(self.project.params, key, val)
            self.project.params.methodology = self.method_var.get()
            messagebox.showinfo("OK", "Параметры применены.")
            self._refresh_summary()
        except Exception as e:
            messagebox.showerror("Ошибка", str(e))

    def _sync_fields(self):
        for key, _, _, _ in self.fields:
            self.p_vars[key].set(str(getattr(self.project.params, key)))
        self.method_var.set(self.project.params.methodology)
        self.city_var.set(self.project.params.city)

    def _on_project_loaded(self):
        self._sync_fields()
        self._refresh_summary()

    def _refresh_summary(self):
        self.summary.delete("1.0", "end")
        ps = self.project.params
        self.summary.insert("end", f"Проект:               {ps.project_name}\n")
        self.summary.insert("end", f"Город:                {ps.city}\n")
        self.summary.insert("end", f"tн зимой / летом:     {ps.t_out_heating} / {ps.t_out_cooling} °C\n")
        self.summary.insert("end", f"Методика:             {ps.methodology}\n")
        self.summary.insert("end", f"Помещений:            {len(self.project.spaces)}\n")
        self.summary.insert("end", f"Конструкций:          {len(self.project.constructions)}\n")
        if self.project.spaces:
            a = sum(s.area_m2 for s in self.project.spaces)
            self.summary.insert("end", f"Общая площадь:        {a:.1f} м²\n")
            tl = sum(s.heat_loss_w for s in self.project.spaces)
            tg = sum(s.heat_gain_w for s in self.project.spaces)
            if tl or tg:
                self.summary.insert("end", "\n--- Результаты ---\n")
                self.summary.insert("end", f"Σ Теплопотери:        {tl/1000:.2f} кВт   ({tl/a if a else 0:.1f} Вт/м²)\n")
                self.summary.insert("end", f"Σ Теплопоступления:   {tg/1000:.2f} кВт   ({tg/a if a else 0:.1f} Вт/м²)\n")


# ===========================================================================
#  Вкладка 3. Конструкции
# ===========================================================================


class ConstructionsTab(BaseTab):
    title = "3. Конструкции (U)"

    # Категории, для которых SHGC обязателен
    GLAZED_CATEGORIES = ("Окна", "Витраж")

    def build(self):
        # Баннер предупреждения о пропущенных SHGC (заполняется в refresh)
        self.warn_frame = tk.Frame(self, bg="#FFF3CD", bd=1, relief="solid")
        self.warn_label = tk.Label(self.warn_frame, bg="#FFF3CD",
                                    fg="#856404", justify="left",
                                    font=("Segoe UI", 9, "bold"),
                                    wraplength=900, anchor="w")
        self.warn_label.pack(side="left", fill="x", expand=True,
                              padx=8, pady=6)
        self.warn_btn = ttk.Button(self.warn_frame,
                                    text="Заполнить типовыми SHGC",
                                    command=self._fill_typical_shgc)
        self.warn_btn.pack(side="right", padx=8, pady=4)
        # warn_frame по умолчанию скрыт, появляется только при наличии проблем

        ttk.Label(self, text="Двойной клик по строке — редактировать U и SHGC. "
                              "Светопрозрачные конструкции с SHGC=0 подсвечены "
                              "красным — солнце не учитывается!",
                  foreground="#555555").pack(anchor="w", padx=10, pady=4)

        cols = ("Категория", "Семейство", "Тип", "Толщ., мм",
                "U, Вт/(м²·К)", "SHGC")
        self.tree = ttk.Treeview(self, columns=cols, show="headings", height=20)
        for c in cols:
            self.tree.heading(c, text=c)
            self.tree.column(c, anchor="w", width=140)
        # Цветовые теги для подсветки строк
        self.tree.tag_configure("shgc_missing",
                                 background="#FFD6D6", foreground="#A00000")
        self.tree.tag_configure("u_missing",
                                 background="#FFE6CC", foreground="#A05000")
        self.tree.pack(fill="both", expand=True, padx=10, pady=4)
        self.tree.bind("<Double-1>", self._edit)

        scroll = ttk.Scrollbar(self, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscroll=scroll.set)
        scroll.place(in_=self.tree, relx=1, rely=0, relheight=1, anchor="ne")

        # Bulk
        fr = ttk.LabelFrame(self, text="Групповое присвоение U / SHGC")
        fr.pack(fill="x", padx=10, pady=6)
        self.bulk_cat = tk.StringVar(value="Стены")
        self.bulk_u = tk.StringVar(value="0.45")
        self.bulk_shgc = tk.StringVar(value="0.5")
        ttk.Label(fr, text="Категория:").grid(row=0, column=0, padx=5)
        ttk.Combobox(fr, textvariable=self.bulk_cat, state="readonly",
                     values=["Стены", "Двери", "Окна", "Витраж", "Покрытие", "Пол"]
                     ).grid(row=0, column=1, padx=5)
        ttk.Label(fr, text="U, Вт/(м²·К):").grid(row=0, column=2, padx=5)
        ttk.Entry(fr, textvariable=self.bulk_u, width=10).grid(row=0, column=3, padx=5)
        ttk.Button(fr, text="Присвоить U",
                   command=self._bulk).grid(row=0, column=4, padx=5)
        ttk.Label(fr, text="SHGC:").grid(row=0, column=5, padx=5)
        ttk.Entry(fr, textvariable=self.bulk_shgc, width=8).grid(row=0, column=6, padx=5)
        ttk.Button(fr, text="Присвоить SHGC",
                   command=self._bulk_shgc).grid(row=0, column=7, padx=5)

        # Кнопка авто-детекции витражей по имени
        ttk.Separator(fr, orient="vertical").grid(row=0, column=8,
                                                    sticky="ns", padx=8)
        ttk.Button(fr, text="🔍 Найти витражи (Curtain Walls)",
                   command=self._detect_curtain_walls
                   ).grid(row=0, column=9, padx=5)

    def subscribe_events(self):
        self.project.subscribe("data_loaded", self.refresh)
        self.project.subscribe("project_loaded", self.refresh)

    def refresh(self, **_):
        for i in self.tree.get_children():
            self.tree.delete(i)
        missing_shgc: list[str] = []
        missing_u: list[str] = []
        for con in sorted(self.project.constructions.values(),
                          key=lambda x: (x.category, x.key)):
            tags = ()
            is_glazed = con.category in self.GLAZED_CATEGORIES
            if is_glazed and (not con.shgc or con.shgc <= 0):
                tags = ("shgc_missing",)
                missing_shgc.append(f"{con.category}/{con.type_name}")
            elif con.u_value <= 0:
                tags = ("u_missing",)
                missing_u.append(f"{con.category}/{con.type_name}")
            self.tree.insert("", "end", iid=con.key, values=(
                con.category, con.family, con.type_name,
                int(con.thickness_mm), con.u_value, con.shgc), tags=tags)

        # Баннер предупреждения
        self._update_warning_banner(missing_shgc, missing_u)

    def _update_warning_banner(self, missing_shgc, missing_u):
        msgs = []
        if missing_shgc:
            msgs.append(
                f"⚠ У {len(missing_shgc)} светопрозрачных конструкций НЕ задан SHGC — "
                f"солнечные теплопоступления не будут учтены! "
                f"Типовые значения: однокамерный стеклопакет — 0.75, "
                f"двухкамерный — 0.60, тонированное — 0.40, "
                f"с солнцезащ. покрытием — 0.30.")
        if missing_u:
            msgs.append(
                f"⚠ У {len(missing_u)} конструкций НЕ задано U-значение.")
        if msgs:
            self.warn_label.configure(text="\n".join(msgs))
            self.warn_frame.pack(fill="x", padx=10, pady=(8, 0),
                                  before=self.warn_frame.master.winfo_children()[1]
                                  if len(self.warn_frame.master.winfo_children()) > 1
                                  else None)
            # Показать кнопку только если есть пропуски SHGC
            if missing_shgc:
                self.warn_btn.pack(side="right", padx=8, pady=4)
            else:
                self.warn_btn.pack_forget()
        else:
            self.warn_frame.pack_forget()

    def _fill_typical_shgc(self):
        """Заполняет SHGC=0.6 для всех светопрозрачных конструкций, у которых
        он не задан. 0.6 — типичный двухкамерный стеклопакет."""
        n = 0
        for con in self.project.constructions.values():
            if con.category in self.GLAZED_CATEGORIES and (
                    not con.shgc or con.shgc <= 0):
                con.shgc = 0.6
                n += 1
        if n:
            messagebox.showinfo("Готово",
                f"SHGC=0.6 присвоено {n} конструкциям. "
                f"При необходимости откорректируйте вручную (двойной клик).")
        self.refresh()

    def _edit(self, event):
        sel = self.tree.selection()
        if not sel:
            return
        key = sel[0]
        con = self.project.constructions.get(key)
        if not con:
            return
        win = tk.Toplevel(self)
        win.title(f"Конструкция: {key}")
        win.geometry("420x260")
        ttk.Label(win, text=f"Категория: {con.category}").pack(anchor="w", padx=10, pady=4)
        ttk.Label(win, text=f"Семейство / тип:\n   {con.family} / {con.type_name}",
                  justify="left").pack(anchor="w", padx=10, pady=4)
        ttk.Label(win, text=f"Толщина: {int(con.thickness_mm)} мм").pack(anchor="w", padx=10)
        ttk.Label(win, text="U-значение, Вт/(м²·К):").pack(anchor="w", padx=10, pady=(10, 0))
        u_var = tk.StringVar(value=str(con.u_value))
        ttk.Entry(win, textvariable=u_var).pack(anchor="w", padx=10)
        ttk.Label(win, text="SHGC (для светопрозрачных):").pack(anchor="w", padx=10, pady=(10, 0))
        s_var = tk.StringVar(value=str(con.shgc))
        ttk.Entry(win, textvariable=s_var).pack(anchor="w", padx=10)

        def save():
            try:
                con.u_value = float(u_var.get().replace(",", "."))
                con.shgc = float(s_var.get().replace(",", "."))
            except ValueError:
                messagebox.showerror("Ошибка", "Введите числовые значения.")
                return
            self.refresh()
            win.destroy()

        ttk.Button(win, text="Сохранить", command=save).pack(pady=10)

    def _bulk(self):
        try:
            u = float(self.bulk_u.get().replace(",", "."))
        except ValueError:
            return
        cat = self.bulk_cat.get()
        n = 0
        for con in self.project.constructions.values():
            if con.category == cat:
                con.u_value = u
                n += 1
        self.refresh()
        messagebox.showinfo("OK", f"U={u} присвоено для {n} конструкций ({cat}).")

    def _detect_curtain_walls(self):
        """Находит конструкции с признаками витража (по имени family/type)
        и предлагает перевести их в категорию 'Витраж' с SHGC=0.5.

        Полезно когда Revit-выгрузка определила Curtain Wall как обычную
        стену (Стены), из-за чего солнце не учитывается."""
        from hvac.catalogs.constructions import (
            _CURTAIN_WALL_KEYWORDS, DEFAULT_U_BY_CATEGORY)
        from hvac.models import Construction

        # Ищем «подозрительные» — категория = Стены, но имя содержит keywords
        candidates = []
        for con in self.project.constructions.values():
            if con.category in self.GLAZED_CATEGORIES:
                continue
            combined = (con.family + " " + con.type_name).lower()
            for kw in _CURTAIN_WALL_KEYWORDS:
                if kw in combined:
                    candidates.append((con, kw))
                    break

        if not candidates:
            messagebox.showinfo(
                "Витражи не найдены",
                "Не нашлось конструкций с признаками витража "
                "(curtain / витраж / glass / balcony / facade и т.п.) "
                "среди не-светопрозрачных.\n\n"
                "Все витражи уже корректно классифицированы.")
            return

        # Показываем что нашли и спрашиваем
        preview = "\n".join(
            f"  • [{con.category}] {con.family} / {con.type_name}  "
            f"(совпало '{kw}')"
            for con, kw in candidates[:15]
        )
        if len(candidates) > 15:
            preview += f"\n  … и ещё {len(candidates) - 15}"

        if not messagebox.askyesno(
                "Найдены витражи",
                f"Найдено {len(candidates)} конструкций с признаками "
                f"витража:\n\n{preview}\n\n"
                f"Перевести их в категорию 'Витраж' с U={DEFAULT_U_BY_CATEGORY['Витраж']} "
                f"и SHGC=0.5?\n\n"
                f"(SHGC можно потом изменить вручную для каждой)"):
            return

        # Преобразуем: создаём новые конструкции с новой категорией
        # и обновляем ссылки в элементах
        from hvac.catalogs.constructions import construction_key
        n_updated = 0
        new_constructions = {}
        old_to_new_key: Dict[str, str] = {}
        for con, _kw in candidates:
            new_cat = "Витраж"
            new_key = construction_key(new_cat, con.family,
                                        con.type_name, con.thickness_mm)
            new_constructions[new_key] = Construction(
                key=new_key,
                category=new_cat,
                family=con.family,
                type_name=con.type_name,
                thickness_mm=con.thickness_mm,
                u_value=(con.u_value
                          if con.u_value > 0
                          else DEFAULT_U_BY_CATEGORY["Витраж"]),
                shgc=(con.shgc if con.shgc > 0 else 0.5),
            )
            old_to_new_key[con.key] = new_key

        # Удаляем старые конструкции
        for old_key in old_to_new_key.keys():
            self.project.constructions.pop(old_key, None)
        # Добавляем новые
        for k, c in new_constructions.items():
            if k not in self.project.constructions:
                self.project.constructions[k] = c

        # Обновляем construction_key в элементах
        for el in self.project.elements:
            if el.construction_key in old_to_new_key:
                el.construction_key = old_to_new_key[el.construction_key]
                n_updated += 1

        self.refresh()
        messagebox.showinfo(
            "Готово",
            f"Переведено {len(candidates)} конструкций в 'Витраж'.\n"
            f"Обновлено {n_updated} ссылок в элементах.\n\n"
            f"Запустите расчёт заново для учёта солнца через витражи.")

    def _bulk_shgc(self):
        try:
            s = float(self.bulk_shgc.get().replace(",", "."))
        except ValueError:
            messagebox.showerror("Ошибка", "Введите числовое SHGC (0..1).")
            return
        if not (0 <= s <= 1):
            messagebox.showerror("Ошибка", "SHGC должен быть в диапазоне 0..1.")
            return
        cat = self.bulk_cat.get()
        if cat not in self.GLAZED_CATEGORIES:
            messagebox.showwarning(
                "Не светопрозрачная",
                f"SHGC присваивается только для категорий "
                f"{', '.join(self.GLAZED_CATEGORIES)}. "
                f"Выбрано: {cat}.")
            return
        n = 0
        for con in self.project.constructions.values():
            if con.category == cat:
                con.shgc = s
                n += 1
        self.refresh()
        messagebox.showinfo("OK", f"SHGC={s} присвоено для {n} конструкций ({cat}).")


# ===========================================================================
#  Вкладка 4. Помещения
# ===========================================================================


class SpacesTab(BaseTab):
    title = "4. Помещения"

    def build(self):
        # Фильтры
        fr = ttk.LabelFrame(self, text="Поиск и фильтры")
        fr.pack(fill="x", padx=10, pady=6)

        ttk.Label(fr, text="Поиск:").grid(row=0, column=0, padx=4)
        self.search_var = tk.StringVar()
        ttk.Entry(fr, textvariable=self.search_var, width=22).grid(row=0, column=1, padx=4)

        ttk.Label(fr, text="Уровень:").grid(row=0, column=2, padx=8)
        self.level_var = tk.StringVar(value="все")
        self.level_combo = ttk.Combobox(fr, textvariable=self.level_var,
                                        width=22, state="readonly")
        self.level_combo.grid(row=0, column=3, padx=4)

        ttk.Label(fr, text="Тип:").grid(row=0, column=4, padx=8)
        self.type_filter_var = tk.StringVar(value="все")
        self.type_filter_combo = ttk.Combobox(fr, textvariable=self.type_filter_var,
                                              width=20, state="readonly")
        self.type_filter_combo.grid(row=0, column=5, padx=4)

        self.info_filter = ttk.Label(fr, text="", foreground="#555555")
        self.info_filter.grid(row=0, column=6, padx=12)

        # Дерево с ползунками и сортировкой
        from hvac.ui.tree_sort import make_scrollable_tree
        cols = ("№", "Имя", "Уровень", "Тип", "S, м²", "V, м³",
                "tв зим", "tв лет", "Чел.", "ACH", "Угл.")
        widths = {"№": 80, "Имя": 240, "Уровень": 150, "Тип": 160,
                  "S, м²": 70, "V, м³": 80, "tв зим": 60, "tв лет": 60,
                  "Чел.": 60, "ACH": 60, "Угл.": 50}
        right_align = ("S, м²", "V, м³", "tв зим", "tв лет", "Чел.", "ACH")
        self.tree, self._sort_snapshot, tree_frame = make_scrollable_tree(
            self, columns=cols, widths=widths, right_align=right_align,
            height=20, select_mode="extended",
        )
        tree_frame.pack(fill="both", expand=True, padx=10, pady=4)
        self.tree.bind("<Double-1>", self._edit)

        # Bulk
        fr2 = ttk.LabelFrame(self, text="Массовое редактирование (Ctrl/Shift+клик)")
        fr2.pack(fill="x", padx=10, pady=6)

        # Строка 1: смена типа помещения
        ttk.Label(fr2, text="Новый тип:").grid(row=0, column=0, padx=4, pady=3)
        self.bulk_type = tk.StringVar(value="Офис")
        self._bulk_type_combo = ttk.Combobox(
            fr2, textvariable=self.bulk_type,
            values=get_all_room_types(),
            state="readonly", width=22)
        self._bulk_type_combo.grid(row=0, column=1, padx=4)
        ttk.Button(fr2, text="Применить ко всем выделенным",
                   command=self._bulk_type).grid(row=0, column=2, padx=8)

        # Строка 2: пометить все стены/проёмы наружными или внутренними.
        # Полезно когда Revit ошибочно дал «наружные» стены помещению,
        # которое полностью окружено другими помещениями (внутренний
        # коридор, технические, санузлы в ядре здания и т.п.).
        ttk.Label(fr2, text="Все стены и проёмы выделенных помещений:",
                  foreground="#444"
                  ).grid(row=1, column=0, columnspan=2,
                         padx=4, pady=(10, 3), sticky="w")
        ttk.Button(fr2, text="🏠 Сделать внутренними",
                   command=lambda: self._bulk_set_exterior(False)
                   ).grid(row=1, column=2, padx=4, pady=3, sticky="w")
        ttk.Button(fr2, text="🌤 Сделать наружными",
                   command=lambda: self._bulk_set_exterior(True)
                   ).grid(row=1, column=3, padx=4, pady=3, sticky="w")

        self.search_var.trace_add("write", lambda *_: self.refresh())
        self.level_var.trace_add("write", lambda *_: self.refresh())
        self.type_filter_var.trace_add("write", lambda *_: self.refresh())

    def subscribe_events(self):
        self.project.subscribe("data_loaded", self.refresh)
        self.project.subscribe("project_loaded", self.refresh)

    def refresh(self):
        levels = sorted({s.level for s in self.project.spaces})
        types = sorted({s.room_type for s in self.project.spaces})
        self.level_combo["values"] = ["все"] + levels
        self.type_filter_combo["values"] = ["все"] + types

        q = self.search_var.get().strip().lower()
        sel_lvl = self.level_var.get()
        sel_t = self.type_filter_var.get()

        for i in self.tree.get_children():
            self.tree.delete(i)
        shown = 0
        for sp in self.project.spaces:
            if q and (q not in sp.number.lower() and q not in sp.name.lower()):
                continue
            if sel_lvl != "все" and sp.level != sel_lvl:
                continue
            if sel_t != "все" and sp.room_type != sel_t:
                continue
            self.tree.insert("", "end", iid=sp.space_id, values=(
                sp.number, sp.name, sp.level, sp.room_type,
                round(sp.area_m2, 1), round(sp.volume_m3, 1),
                sp.t_in_heat, sp.t_in_cool, sp.occupancy_people,
                sp.ach_inf, "да" if sp.is_corner else "—"))
            shown += 1
        self.info_filter.config(text=f"Показано: {shown} из {len(self.project.spaces)}")
        if hasattr(self, "_sort_snapshot"):
            self._sort_snapshot()

    def _bulk_type(self):
        sel = self.tree.selection()
        if not sel:
            messagebox.showinfo("Информация", "Выделите строки (Ctrl+клик).")
            return
        new_t = self.bulk_type.get()
        n = 0
        for iid in sel:
            sp = self.project.get_space(iid)
            if not sp:
                continue
            sp.room_type = new_t
            apply_room_type_defaults(sp)
            sp.user_modified = True
            n += 1
        self.refresh()
        messagebox.showinfo("OK", f"Тип «{new_t}» применён к {n} помещ.")

    def _bulk_set_exterior(self, new_state: bool):
        """Массово помечает все стены и проёмы выделенных помещений
        как наружные (True) или внутренние (False).

        Используется когда CSV из Revit ошибочно показывает стены
        как наружные у помещений, которые на самом деле полностью
        окружены другими помещениями (внутренние коридоры, технические,
        санузлы в ядре здания и т.п.).

        Параметр new_state:
            False — пометить внутренними (теплопотери только от инфильтрации)
            True  — пометить наружными (полный расчёт через ограждение)
        """
        sel = self.tree.selection()
        if not sel:
            messagebox.showinfo(
                "Не выделено",
                "Выделите помещения в таблице (Ctrl/Shift+клик).")
            return

        spaces_affected = [self.project.get_space(iid) for iid in sel]
        spaces_affected = [sp for sp in spaces_affected if sp is not None]
        if not spaces_affected:
            return

        # Целевые элементы: только стены и проёмы выделенных помещений,
        # у которых текущий флаг не совпадает с желаемым.
        space_ids = {sp.space_id for sp in spaces_affected}
        target_elements = [
            e for e in self.project.elements
            if e.space_id in space_ids
            and e.row_type in ("external_wall", "opening")
            and e.is_exterior != new_state
        ]

        label = "наружными" if new_state else "внутренними"
        if not target_elements:
            messagebox.showinfo(
                "Нечего менять",
                f"У выделенных помещений ({len(spaces_affected)} шт.) "
                f"все стены и проёмы уже помечены {label}.")
            return

        # Сводка по помещениям с >0 затрагиваемых элементов
        affected_by_space: Dict[str, int] = {}
        for e in target_elements:
            affected_by_space[e.space_id] = affected_by_space.get(
                e.space_id, 0) + 1
        # Топ-5 помещений для превью
        preview_lines = []
        for sp in spaces_affected:
            n = affected_by_space.get(sp.space_id, 0)
            if n > 0:
                preview_lines.append(f"  • {sp.number} {sp.name}: {n} эл.")
        preview = "\n".join(preview_lines[:5])
        if len(preview_lines) > 5:
            preview += f"\n  …и ещё {len(preview_lines) - 5} помещений"

        if not messagebox.askyesno(
                "Подтверждение",
                f"Помещений выделено: {len(spaces_affected)}\n"
                f"Из них с изменениями: {len(preview_lines)}\n"
                f"Всего элементов будет помечено {label}: "
                f"{len(target_elements)}\n\n"
                f"{preview}\n\n"
                f"После этого автоматически выполнится пересчёт.\n"
                f"Продолжить?"):
            return

        for el in target_elements:
            el.is_exterior = new_state

        # Помечаем помещения как user_modified, чтобы при следующей
        # загрузке CSV (keep_user_settings=True) правки сохранились.
        for sp in spaces_affected:
            sp.user_modified = True

        # Пересчёт и уведомление UI
        self.project.recalculate()
        self.project.emit("elements_changed")

        messagebox.showinfo(
            "Готово",
            f"Изменено элементов: {len(target_elements)}\n"
            f"Помещений: {len(spaces_affected)}\n"
            f"Пересчёт выполнен.")

    def _edit(self, event):
        sel = self.tree.selection()
        if not sel:
            return
        sp = self.project.get_space(sel[0])
        if not sp:
            return
        win = tk.Toplevel(self)
        win.title(f"Помещение {sp.number} — {sp.name}")
        win.geometry("450x520")

        ttk.Label(win, text=f"Площадь: {sp.area_m2:.2f} м², объём: {sp.volume_m3:.2f} м³,"
                  f" высота {sp.height_m:.2f} м",
                  foreground="#1F4E78").pack(anchor="w", padx=10, pady=8)

        ttk.Label(win, text="Тип помещения:").pack(anchor="w", padx=10)
        type_var = tk.StringVar(value=sp.room_type)
        ttk.Combobox(win, textvariable=type_var, state="readonly", width=35,
                     values=get_all_room_types()).pack(anchor="w", padx=10)

        rows = [
            ("Темп. внутри зимой, °C", "t_in_heat"),
            ("Темп. внутри летом, °C", "t_in_cool"),
            ("Кол-во людей", "occupancy_people"),
            ("Освещение, Вт/м²", "lighting_w_m2"),
            ("Оборудование, Вт/м²", "equipment_w_m2"),
            ("Кратность инфильтрации (1/ч)", "ach_inf"),
        ]
        vars_ = {}
        for label, key in rows:
            ttk.Label(win, text=label).pack(anchor="w", padx=10, pady=(8, 0))
            v = tk.StringVar(value=str(getattr(sp, key)))
            ttk.Entry(win, textvariable=v, width=20).pack(anchor="w", padx=10)
            vars_[key] = v

        var_c = tk.BooleanVar(value=sp.is_corner)
        ttk.Checkbutton(win, text="Угловое помещение",
                        variable=var_c).pack(anchor="w", padx=10, pady=6)
        var_f = tk.BooleanVar(value=sp.has_floor_to_ground)
        ttk.Checkbutton(win, text="Пол по грунту / над неотапливаемым подвалом",
                        variable=var_f).pack(anchor="w", padx=10)
        var_r = tk.BooleanVar(value=sp.has_roof or sp.is_top_floor)
        ttk.Checkbutton(win, text="Имеет совмещённое покрытие (последний этаж)",
                        variable=var_r).pack(anchor="w", padx=10)

        def on_type(*_):
            sp.room_type = type_var.get()
            apply_room_type_defaults(sp)
            for label, key in rows:
                vars_[key].set(str(getattr(sp, key)))

        type_var.trace_add("write", on_type)

        def save():
            try:
                sp.room_type = type_var.get()
                for _, key in rows:
                    setattr(sp, key, float(vars_[key].get().replace(",", ".")))
                sp.is_corner = var_c.get()
                sp.has_floor_to_ground = var_f.get()
                sp.has_roof = var_r.get()
                sp.is_top_floor = var_r.get()
                sp.user_modified = True
            except ValueError:
                messagebox.showerror("Ошибка", "Введите числовые значения.")
                return
            self.refresh()
            win.destroy()

        ttk.Button(win, text="Сохранить", command=save).pack(pady=10)


# ===========================================================================
#  Вкладка 5. Расчёт
# ===========================================================================


class CalculateTab(BaseTab):
    title = "5. Расчёт"

    def build(self):
        # Баннер предупреждения о пропущенных SHGC (скрыт по умолчанию)
        self.warn_frame = tk.Frame(self, bg="#FFE0E0", bd=1, relief="solid")
        self.warn_label = tk.Label(self.warn_frame, bg="#FFE0E0",
                                    fg="#A00000", justify="left",
                                    font=("Segoe UI", 9, "bold"),
                                    wraplength=900, anchor="w")
        self.warn_label.pack(side="left", fill="x", expand=True,
                              padx=8, pady=6)

        # ===== Панель поиска и фильтров =====
        fr_search = ttk.Frame(self)
        fr_search.pack(fill="x", padx=10, pady=(8, 2))
        ttk.Label(fr_search, text="🔍 Поиск:",
                  font=("Segoe UI", 9, "bold")).pack(side="left", padx=4)
        self.search_var = tk.StringVar()
        self.search_var.trace_add("write", lambda *a: self.refresh())
        ent = ttk.Entry(fr_search, textvariable=self.search_var, width=30)
        ent.pack(side="left", padx=4)
        ent.bind("<Escape>", lambda e: self.search_var.set(""))

        ttk.Label(fr_search, text="(№, имя, уровень)",
                  foreground="#888").pack(side="left", padx=2)

        # Фильтр по уровню
        ttk.Separator(fr_search, orient="vertical").pack(side="left",
                                                          fill="y", padx=8)
        ttk.Label(fr_search, text="Уровень:").pack(side="left", padx=2)
        self.level_var = tk.StringVar(value="(все)")
        self.level_combo = ttk.Combobox(fr_search,
                                         textvariable=self.level_var,
                                         state="readonly", width=14,
                                         values=["(все)"])
        self.level_combo.pack(side="left", padx=2)
        self.level_combo.bind("<<ComboboxSelected>>",
                               lambda e: self.refresh())

        # Фильтр «только с нагрузкой»
        self.only_loaded = tk.BooleanVar(value=False)
        ttk.Checkbutton(fr_search, text="только с расчётной нагрузкой",
                        variable=self.only_loaded,
                        command=self.refresh
                        ).pack(side="left", padx=8)

        # Сводка по отфильтрованным строкам
        self.summary_var = tk.StringVar(value="")
        ttk.Label(fr_search, textvariable=self.summary_var,
                  foreground="#0066AA",
                  font=("Segoe UI", 9, "bold")
                  ).pack(side="right", padx=8)

        # ===== Таблица со ползунками =====
        # Контейнер с grid-раскладкой: дерево + 2 скроллбара
        tree_frame = ttk.Frame(self)
        tree_frame.pack(fill="both", expand=True, padx=10, pady=4)
        tree_frame.rowconfigure(0, weight=1)
        tree_frame.columnconfigure(0, weight=1)

        cols = ("№", "Имя", "Уровень", "S, м²", "Через огражд., Вт",
                "Инфильтр., Вт", "Q зимой, Вт", "Уд. зимой",
                "Солнце, Вт", "Люди+Об+Осв, Вт", "Q летом, Вт", "Уд. летом")
        self.tree = ttk.Treeview(tree_frame, columns=cols, show="headings",
                                  height=24)
        widths = {"№": 70, "Имя": 200, "Уровень": 140, "S, м²": 70,
                  "Через огражд., Вт": 110, "Инфильтр., Вт": 95,
                  "Q зимой, Вт": 95, "Уд. зимой": 75,
                  "Солнце, Вт": 80, "Люди+Об+Осв, Вт": 120,
                  "Q летом, Вт": 95, "Уд. летом": 75}
        for c in cols:
            self.tree.heading(c, text=c)
            self.tree.column(c, anchor="e" if "Вт" in c or "Уд" in c else "w",
                             width=widths.get(c, 90),
                             stretch=False)  # фиксируем ширины, чтобы H-скролл работал

        # Вертикальный и горизонтальный ползунки
        vsb = ttk.Scrollbar(tree_frame, orient="vertical",
                             command=self.tree.yview)
        hsb = ttk.Scrollbar(tree_frame, orient="horizontal",
                             command=self.tree.xview)
        self.tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)

        self.tree.grid(row=0, column=0, sticky="nsew")
        vsb.grid(row=0, column=1, sticky="ns")
        hsb.grid(row=1, column=0, sticky="ew")

        # Прокрутка колёсиком мыши — стандартная, ttk уже поддерживает.
        # Shift+колесо — горизонтально.
        def _on_shift_wheel(event):
            self.tree.xview_scroll(int(-event.delta / 120), "units")
            return "break"
        self.tree.bind("<Shift-MouseWheel>", _on_shift_wheel)

        # Подключаем сортировку по клику на заголовок
        from hvac.ui.tree_sort import attach_sort
        self._sort_snapshot = attach_sort(self.tree, cols)

        fr = ttk.Frame(self)
        fr.pack(fill="x", padx=10, pady=6)
        ttk.Button(fr, text="▶ Выполнить расчёт",
                   command=self.do_calc).pack(side="left", padx=5)
        ttk.Button(fr, text="📊 Экспорт в Excel",
                   command=self.do_export).pack(side="left", padx=5)
        ttk.Button(fr, text="🔄 Экспорт CSV для Revit",
                   command=self.app.menu_export_revit).pack(side="left", padx=5)
        ttk.Button(fr, text="📋 Заполнить HLGC Design Table",
                   command=self._export_to_hlgc
                   ).pack(side="left", padx=5)
        ttk.Button(fr, text="🧭 Роза ориентаций",
                   command=self._show_orientation_rose
                   ).pack(side="left", padx=5)
        ttk.Button(fr, text="🔎 Диагностика помещения",
                   command=self._show_room_diagnostics
                   ).pack(side="left", padx=5)

    def _show_room_diagnostics(self):
        """Показывает ВСЕ граничные элементы выбранного помещения с
        пошаговым разбором как считается солнце / трансмиссия.

        Помогает понять почему Q_солнца=0, какая ориентация применена,
        какой SHGC и т.д. — без необходимости открывать Excel."""
        sel = self.tree.selection()
        if not sel:
            messagebox.showinfo(
                "Выберите помещение",
                "Выделите строку помещения в таблице (одним кликом).")
            return
        sid = sel[0]
        sp = self.project.get_space(sid)
        if not sp:
            return

        from hvac.parsers import effective_orientation
        from hvac.engine.sp50 import SOLAR_ORIENTATION_FACTOR
        p = self.project.params
        tn = p.true_north_offset_deg or 0.0

        elements = [e for e in self.project.elements
                    if e.space_id == sid]
        exterior = [e for e in elements if e.is_exterior]

        win = tk.Toplevel(self)
        win.title(f"🔎 Диагностика {sp.number} — {sp.name}")
        win.geometry("1100x650")

        # Резюме
        head = tk.Frame(win, bg="#EAF4FB")
        head.pack(fill="x", padx=10, pady=8)
        tk.Label(head, bg="#EAF4FB", justify="left", anchor="w",
                 wraplength=1050, font=("Segoe UI", 9),
                 text=(
            f"Помещение: {sp.number} «{sp.name}», уровень {sp.level}\n"
            f"Площадь: {sp.area_m2} м²   Высота: {sp.height_m} м   "
            f"Объём: {sp.volume_m3} м³\n"
            f"Всего граничных элементов: {len(elements)}, "
            f"наружных: {len(exterior)}\n"
            f"Q_солнца = {sp.heat_gain_breakdown.get('Солнечная радиация', 0):.0f} Вт   "
            f"Q_охл = {sp.heat_gain_w:.0f} Вт   "
            f"Q_отоп = {sp.heat_loss_w:.0f} Вт"
        )).pack(anchor="w", padx=8, pady=6)

        if not exterior and not elements:
            tk.Label(win, foreground="red", font=("Segoe UI", 11, "bold"),
                     text="⚠ У помещения НЕТ граничных элементов вообще!"
                     ).pack(padx=10, pady=20)
            return

        # Чекбокс «показать внутренние» — по умолчанию ВКЛ если нет наружных
        show_interior_var = tk.BooleanVar(value=(len(exterior) == 0))
        fr_filter = ttk.Frame(win)
        fr_filter.pack(fill="x", padx=10, pady=2)
        ttk.Checkbutton(fr_filter,
                        text="Показать внутренние элементы тоже "
                             "(чтобы пометить как наружные)",
                        variable=show_interior_var,
                        command=lambda: _populate_tree()
                        ).pack(side="left")

        # Таблица всех элементов
        cols = ("Снаружи", "Тип", "Категория", "Конструкция", "Площадь",
                "U", "SHGC", "Raw ориент.", "Эфф. ориент.",
                "f_solar", "Q_солн., Вт")
        tree = ttk.Treeview(win, columns=cols, show="headings", height=16,
                             selectmode="extended")
        widths = {"Снаружи": 60, "Тип": 80, "Категория": 75,
                  "Конструкция": 240,
                  "Площадь": 65, "U": 55, "SHGC": 55,
                  "Raw ориент.": 100, "Эфф. ориент.": 100,
                  "f_solar": 60, "Q_солн., Вт": 80}
        for c in cols:
            tree.heading(c, text=c)
            anchor = "e" if c in ("Площадь", "U", "SHGC", "f_solar",
                                  "Q_солн., Вт") else "w"
            tree.column(c, anchor=anchor, width=widths.get(c, 80))
        tree.pack(fill="both", expand=True, padx=10, pady=6)
        tree.tag_configure("solar_zero",
                            background="#FFE0E0", foreground="#A00000")
        tree.tag_configure("interior",
                            background="#F0F0F0", foreground="#888888")

        # Сохраняем элементы в порядке вставки для последующего доступа
        # через iid дерева
        element_by_iid = {}

        def _populate_tree():
            for i in tree.get_children():
                tree.delete(i)
            element_by_iid.clear()
            show_int = show_interior_var.get()
            total_solar = 0.0
            # Сортируем: сначала наружные, потом по площади убывания
            items = sorted(elements,
                            key=lambda e: (not e.is_exterior,
                                            -(e.net_area_m2 or 0)))
            for el in items:
                if not el.is_exterior and not show_int:
                    continue
                con = self.project.constructions.get(el.construction_key)
                shgc = con.shgc if con else 0
                cat = con.category if con else el.category
                constr = (f"[{cat}] "
                          f"{el.family}/{el.type_name}/{int(el.thickness_mm)}")
                eff = effective_orientation(el.orientation,
                                             el.orientation_deg, tn)
                f_solar = SOLAR_ORIENTATION_FACTOR.get(eff, 0.65)
                q_sol = 0.0
                if (el.is_exterior and el.u_value > 0
                        and el.net_area_m2 > 0 and shgc > 0):
                    q_sol = (shgc * el.net_area_m2 * p.solar_intensity_w_m2
                             * f_solar * p.solar_shading_factor)
                    total_solar += q_sol
                tags = ()
                if not el.is_exterior:
                    tags = ("interior",)
                elif q_sol == 0 and el.net_area_m2 > 1:
                    tags = ("solar_zero",)

                raw_str = el.orientation or "—"
                if el.orientation_deg is not None:
                    raw_str = f"{el.orientation} ({el.orientation_deg:.0f}°)"
                iid = tree.insert("", "end", tags=tags, values=(
                    "✓" if el.is_exterior else "—",
                    el.row_type, cat[:16] if cat else "—",
                    constr[:50],
                    f"{el.net_area_m2:.2f}",
                    f"{el.u_value:.2f}" if el.u_value > 0 else "0 ⚠",
                    f"{shgc:.2f}" if shgc > 0 else "0 ⚠",
                    raw_str, eff or "—",
                    f"{f_solar:.2f}",
                    f"{q_sol:.0f}",
                ))
                element_by_iid[iid] = el
            # Обновим строку Σ solar
            summary_label.configure(
                text=f"Σ Q_солнца (расчётно по показанным элементам): "
                     f"{total_solar:.0f} Вт")

        # Метка под кнопками
        summary_label = ttk.Label(win, foreground="#0066AA",
                                    font=("Segoe UI", 9, "bold"))
        # Запоминаем чтобы можно было обновлять; раскладку ниже
        _populate_tree()

        # Кнопки массовых действий над выделенными элементами
        fr_actions = ttk.Frame(win)
        fr_actions.pack(fill="x", padx=10, pady=4)
        ttk.Label(fr_actions,
                  text="Выделите элементы (Ctrl+клик), затем действие:",
                  foreground="#666").pack(side="left", padx=4)

        def _mark_as_glazing():
            sel_iids = tree.selection()
            if not sel_iids:
                messagebox.showinfo(
                    "Не выделено", "Выделите элементы в таблице "
                    "(Ctrl+клик для нескольких).", parent=win)
                return
            from tkinter.simpledialog import askfloat
            shgc_val = askfloat(
                "SHGC витража",
                "Введите SHGC (0.3 = тонир., 0.5 = двухкам., 0.7 = одинар.):",
                parent=win, initialvalue=0.5, minvalue=0.1, maxvalue=0.9)
            if shgc_val is None:
                return
            u_val = askfloat(
                "U витража",
                "Введите U-значение, Вт/(м²·К) (типично 1.5-2.5):",
                parent=win, initialvalue=1.8, minvalue=0.5, maxvalue=10)
            if u_val is None:
                return

            from hvac.catalogs.constructions import construction_key
            from hvac.models import Construction
            n_done = 0
            for iid in sel_iids:
                el = element_by_iid.get(iid)
                if el is None:
                    continue
                # Новая Витраж-конструкция: фиксированный type_name + thickness
                new_key = construction_key(
                    "Витраж",
                    el.family or "Витраж",
                    el.type_name or f"Витраж_{int(el.thickness_mm) or 0}",
                    el.thickness_mm,
                )
                if new_key not in self.project.constructions:
                    self.project.constructions[new_key] = Construction(
                        key=new_key, category="Витраж",
                        family=el.family or "Витраж",
                        type_name=(el.type_name
                                   or f"Витраж_{int(el.thickness_mm) or 0}"),
                        thickness_mm=el.thickness_mm,
                        u_value=u_val, shgc=shgc_val,
                    )
                else:
                    # Обновляем U/SHGC если конструкция уже есть
                    c = self.project.constructions[new_key]
                    c.u_value = u_val
                    c.shgc = shgc_val
                el.construction_key = new_key
                el.u_value = u_val
                n_done += 1
            # Запуск пересчёта
            self.project.recalculate()
            messagebox.showinfo(
                "Готово",
                f"Переведено в витраж: {n_done} элементов.\n"
                f"Пересчёт выполнен. Закройте окно и обновите таблицу "
                f"Расчёта.", parent=win)
            win.destroy()
            self.refresh()

        ttk.Button(fr_actions, text="✨ Преобразовать в витраж",
                   command=_mark_as_glazing
                   ).pack(side="left", padx=8)

        def _toggle_exterior():
            """Помечает выделенные элементы как наружные (или внутренние)."""
            sel_iids = tree.selection()
            if not sel_iids:
                messagebox.showinfo("Не выделено",
                                     "Выделите элементы в таблице.",
                                     parent=win)
                return
            # Считаем сколько из выделенных уже наружные
            sel_els = [element_by_iid[i] for i in sel_iids
                       if i in element_by_iid]
            n_ext = sum(1 for e in sel_els if e.is_exterior)
            n_int = len(sel_els) - n_ext
            # Если все одного типа — переключаем; смешанные → делаем все наружными
            if n_int == 0:
                new_state = False   # все были наружные → делаем внутренними
                label = "внутренних"
            else:
                new_state = True    # есть внутренние → все станут наружными
                label = "наружных"
            if not messagebox.askyesno(
                    "Подтверждение",
                    f"Пометить {len(sel_els)} элементов как {label}?\n\n"
                    f"После этого нужно нажать «Выполнить расчёт».",
                    parent=win):
                return
            for el in sel_els:
                el.is_exterior = new_state
            # Каталог нужно перестроить чтобы новые наружные попали в него
            self.project.recalculate()
            _populate_tree()
            messagebox.showinfo(
                "Готово",
                f"Помечено {len(sel_els)} элементов как {label}. "
                f"Пересчёт выполнен.", parent=win)

        ttk.Button(fr_actions, text="🔁 Пометить наружн./внутр.",
                   command=_toggle_exterior
                   ).pack(side="left", padx=4)

        def _set_shgc():
            sel_iids = tree.selection()
            if not sel_iids:
                return
            from tkinter.simpledialog import askfloat
            shgc_val = askfloat(
                "SHGC", "Новое SHGC для конструкций выделенных элементов:",
                parent=win, initialvalue=0.5, minvalue=0, maxvalue=1)
            if shgc_val is None:
                return
            updated_keys = set()
            for iid in sel_iids:
                el = element_by_iid.get(iid)
                if el is None:
                    continue
                con = self.project.constructions.get(el.construction_key)
                if con and con.key not in updated_keys:
                    con.shgc = shgc_val
                    updated_keys.add(con.key)
            self.project.recalculate()
            messagebox.showinfo(
                "Готово",
                f"SHGC={shgc_val} установлен для {len(updated_keys)} "
                f"конструкций. Пересчитано.", parent=win)
            win.destroy()
            self.refresh()

        ttk.Button(fr_actions, text="SHGC = …",
                   command=_set_shgc).pack(side="left", padx=4)

        # Размещаем summary под кнопками
        summary_label.pack(anchor="w", padx=12, pady=4)

        # Подсказки (если есть проблемы)
        diag_lines = []
        if not exterior:
            diag_lines.append(
                "⚠ Наружных элементов нет — солнце = 0!\n"
                "Возможно балкон/двор в Revit смоделирован как Space "
                "(делает стены 'внутренними'). Включите чекбокс "
                "выше и пометьте нужные стены как наружные.")
        no_u = [e for e in exterior if e.u_value <= 0]
        if no_u:
            diag_lines.append(
                f"⚠ {len(no_u)} наружных элементов без U-значения "
                f"(пропускаются в расчёте!).")
        if diag_lines:
            tk.Label(win, justify="left", anchor="w",
                     foreground="#A00000", font=("Segoe UI", 9, "bold"),
                     wraplength=1050,
                     text="\n".join(diag_lines)
                     ).pack(anchor="w", padx=12, pady=4)

    def _export_to_hlgc(self):
        """Записывает результаты расчёта в master-таблицу проекта (HLGC)."""
        if not self.project.spaces:
            messagebox.showwarning("Нет данных",
                                    "Сначала загрузите проект и выполните расчёт.")
            return
        # Проверка что расчёт выполнен
        if all(sp.heat_loss_w == 0 and sp.heat_gain_w == 0
               for sp in self.project.spaces):
            if not messagebox.askyesno(
                    "Нет результатов расчёта",
                    "У всех помещений Q=0 — похоже расчёт не выполнен.\n"
                    "Продолжить экспорт всё равно (запишутся только "
                    "геометрия и параметры)?"):
                return

        path = filedialog.askopenfilename(
            title="Выберите HLGC Design Table (.xls/.xlsx)",
            filetypes=[("Excel", "*.xls *.xlsx")],
        )
        if not path:
            return

        # Спросим режим заполнения
        mode_win = tk.Toplevel(self)
        mode_win.title("Режим экспорта")
        mode_win.geometry("560x320")
        mode_win.transient(self.winfo_toplevel())
        mode_win.grab_set()
        mode_win.resizable(False, False)

        ttk.Label(mode_win, text="Как заполнить таблицу?",
                  font=("Segoe UI", 10, "bold")
                  ).pack(anchor="w", padx=12, pady=(12, 6))

        mode_var = tk.StringVar(value="append")
        options = [
            ("match",
              "Только совпадения",
              "Обновить только те строки в таблице, чей № комнаты "
              "совпадает с проектом. Помещения проекта без пары — "
              "пропускаются."),
            ("append",
              "Совпадения + добавить новые",
              "Обновить совпадения, а помещения из проекта, которых нет "
              "в таблице, ДОБАВИТЬ в конец (со стилем и формулами как у "
              "первой строки шаблона)."),
            ("rebuild",
              "Полная перезапись (шаблон)",
              "Использовать таблицу как СТИЛЕВОЙ ШАБЛОН: очистить все "
              "строки данных и записать ВСЕ помещения проекта по порядку. "
              "Заголовки, форматирование и формулы (например =Y/F) — "
              "сохраняются."),
        ]
        for val, label, desc in options:
            fr = ttk.Frame(mode_win)
            fr.pack(fill="x", padx=12, pady=4, anchor="w")
            ttk.Radiobutton(fr, text=label, variable=mode_var, value=val
                            ).pack(anchor="w")
            ttk.Label(fr, text=desc, foreground="#666",
                      wraplength=520, justify="left"
                      ).pack(anchor="w", padx=24)

        only_empty_var = tk.BooleanVar(value=False)
        ttk.Separator(mode_win).pack(fill="x", pady=6)
        ttk.Checkbutton(mode_win,
                        text="Записывать только в пустые ячейки "
                             "(сохранить ручные правки инженера)",
                        variable=only_empty_var
                        ).pack(anchor="w", padx=12)

        ok_clicked = {"ok": False}
        btn_fr = ttk.Frame(mode_win)
        btn_fr.pack(fill="x", pady=10)
        ttk.Button(btn_fr, text="OK",
                   command=lambda: (ok_clicked.update(ok=True),
                                     mode_win.destroy())
                   ).pack(side="right", padx=10)
        ttk.Button(btn_fr, text="Отмена",
                   command=mode_win.destroy
                   ).pack(side="right", padx=4)

        self.wait_window(mode_win)
        if not ok_clicked["ok"]:
            return

        mode = mode_var.get()
        only_empty = only_empty_var.get()

        # Куда сохранить. Сохраняем в тот же формат что исходник
        # (через Excel COM .xls сохраняется корректно со всеми ссылками).
        base, ext = os.path.splitext(path)
        default_out = base + "_filled" + ext
        out = filedialog.asksaveasfilename(
            title="Сохранить заполненную таблицу как…",
            defaultextension=ext,
            initialfile=os.path.basename(default_out),
            initialdir=os.path.dirname(default_out),
            filetypes=[("Excel 97-2003", "*.xls"),
                       ("Excel", "*.xlsx")],
        )
        if not out:
            return

        try:
            from hvac.io_hlgc import export_to_hlgc
            stats = export_to_hlgc(self.project, path, out,
                                    overwrite_only_empty=only_empty,
                                    mode=mode)
        except Exception as e:
            messagebox.showerror("Ошибка экспорта HLGC",
                                  f"{e}\n\n{traceback.format_exc()}")
            return

        # Подробный отчёт
        mode_label = {"match": "Только совпадения",
                      "append": "Совпадения + добавление",
                      "rebuild": "Полная перезапись"}.get(
                          stats.get("mode", ""), stats.get("mode", ""))
        msg = (f"Файл сохранён:\n  {stats['output_path']}\n\n"
               f"Режим:                  {mode_label}\n"
               f"Движок:                 {stats.get('engine', '?')}\n"
               f"Строк в шаблоне:        {stats['rows_total']}\n"
               f"Обновлено по совпадению:{stats['rows_matched']}\n")
        if stats.get("rows_appended", 0) > 0:
            msg += f"Добавлено новых:        {stats['rows_appended']}\n"
        if stats.get("rows_cleared", 0) > 0:
            msg += f"Очищено лишних:         {stats['rows_cleared']}\n"
        msg += f"Всего ячеек записано:   {stats['cells_written']}\n"
        if stats["rows_unmatched"]:
            n = len(stats["rows_unmatched"])
            preview = ", ".join(stats["rows_unmatched"][:10])
            if n > 10:
                preview += f", … и ещё {n - 10}"
            msg += (f"\n⚠ В шаблоне нет в проекте ({n}):\n  {preview}")
        messagebox.showinfo("Экспорт в HLGC завершён", msg)

        ttk.Label(fr, text="Клик по заголовку — сортировка ▲/▼/сброс",
                  foreground="#888").pack(side="right", padx=8)

    def _show_orientation_rose(self):
        """Окно с розой ориентаций — таблица площадей по сторонам света.

        Учитывает текущее true_north_offset_deg из ProjectParameters.
        Позволяет визуально проверить, правильно ли назначены стороны
        света после поворота. Если ваш дом по плану смотрит на «юг», но
        в розе видно много северных стен — значит поворот не задан или
        задан с обратным знаком.
        """
        from hvac.parsers import effective_orientation
        from collections import defaultdict

        tn = self.project.params.true_north_offset_deg or 0.0
        # Накапливаем площади
        walls_by_sector: Dict[str, float] = defaultdict(float)
        windows_by_sector: Dict[str, float] = defaultdict(float)
        for el in self.project.elements:
            if not el.is_exterior or el.net_area_m2 <= 0:
                continue
            sector = effective_orientation(el.orientation,
                                            el.orientation_deg, tn)
            if not sector:
                continue
            con = self.project.constructions.get(el.construction_key)
            is_glazed = (con is not None and con.shgc > 0) or (
                el.row_type == "opening")
            if is_glazed:
                windows_by_sector[sector] += el.net_area_m2
            else:
                walls_by_sector[sector] += el.net_area_m2

        # Окно
        win = tk.Toplevel(self)
        win.title(f"🧭 Роза ориентаций (поворот True North = {tn:.0f}°)")
        win.geometry("760x520")

        # Подсказка
        header = tk.Frame(win, bg="#EAF4FB")
        header.pack(fill="x", padx=10, pady=8)
        tk.Label(header, bg="#EAF4FB", justify="left", wraplength=720, text=(
            f"Накопленная площадь наружных стен и окон по сторонам света "
            f"(с учётом поворота True North = {tn:+.0f}°).\n"
            f"Подсказка: посмотрите на план — если здание явно вытянуто/"
            f"смотрит на юг, в строке S должна быть наибольшая площадь."
        )).pack(anchor="w", padx=8, pady=6)

        # Таблица
        cols = ("Сторона", "Угол",
                "Стены, м²", "Окна, м²", "Всего, м²", "")
        tree = ttk.Treeview(win, columns=cols, show="headings", height=10)
        widths = {"Сторона": 80, "Угол": 70, "Стены, м²": 90,
                  "Окна, м²": 90, "Всего, м²": 90, "": 320}
        for c in cols:
            tree.heading(c, text=c)
            tree.column(c, anchor="e" if c != "" else "w",
                        width=widths.get(c, 100))
        tree.column("Сторона", anchor="center")
        tree.column("Угол", anchor="center")
        tree.pack(fill="both", expand=True, padx=10, pady=4)

        sectors = ["N", "NE", "E", "SE", "S", "SW", "W", "NW"]
        sector_angle = {"N": "0°", "NE": "45°", "E": "90°",
                        "SE": "135°", "S": "180°", "SW": "225°",
                        "W": "270°", "NW": "315°"}
        # Для ASCII-бара
        total_areas = {s: walls_by_sector[s] + windows_by_sector[s]
                       for s in sectors}
        max_area = max(total_areas.values()) if total_areas else 0
        for s in sectors:
            walls = walls_by_sector[s]
            windows = windows_by_sector[s]
            total = walls + windows
            # ASCII бар (40 символов max)
            bar = ""
            if max_area > 0 and total > 0:
                n = int(round(total / max_area * 40))
                bar = "█" * n
            tree.insert("", "end", values=(
                s, sector_angle[s],
                f"{walls:.1f}", f"{windows:.1f}", f"{total:.1f}", bar,
            ))

        # Итоги
        ttk.Separator(win, orient="horizontal").pack(fill="x", padx=10,
                                                      pady=4)
        total_walls = sum(walls_by_sector.values())
        total_windows = sum(windows_by_sector.values())
        wwr = (100 * total_windows / (total_walls + total_windows)
               if (total_walls + total_windows) > 0 else 0)
        tk.Label(win, text=(
            f"Σ наружных стен: {total_walls:.1f} м²   |   "
            f"Σ окон: {total_windows:.1f} м²   |   "
            f"факт. WWR = {wwr:.1f}%"),
            font=("Segoe UI", 10, "bold"), fg="#1F4E78"
        ).pack(anchor="w", padx=12, pady=4)

        # Кнопка для быстрого изменения поворота
        fr_btn = ttk.Frame(win)
        fr_btn.pack(fill="x", padx=10, pady=8)
        ttk.Label(fr_btn, text="Изменить поворот True North, °:"
                  ).pack(side="left", padx=4)
        offset_var = tk.StringVar(value=str(int(tn)))
        ttk.Entry(fr_btn, textvariable=offset_var, width=8
                  ).pack(side="left", padx=4)

        def _apply_offset():
            try:
                new_tn = float(offset_var.get().replace(",", "."))
            except ValueError:
                return
            self.project.params.true_north_offset_deg = new_tn
            win.destroy()
            self._show_orientation_rose()

        ttk.Button(fr_btn, text="Применить и пересмотреть",
                   command=_apply_offset).pack(side="left", padx=8)
        ttk.Button(fr_btn, text="Закрыть",
                   command=win.destroy).pack(side="right", padx=4)

    def subscribe_events(self):
        self.project.subscribe("calculation_done", self.refresh)
        self.project.subscribe("data_loaded",
                                lambda **kw: (self._check_shgc(),
                                              self.refresh()))
        self.project.subscribe("project_loaded",
                                lambda **kw: (self._check_shgc(),
                                              self.refresh()))
        self.project.subscribe("spaces_changed", lambda **kw: self.refresh())

    def on_show(self):
        self._check_shgc()

    def _check_shgc(self):
        """Показывает баннер если у светопрозрачных конструкций SHGC=0."""
        missing = []
        for con in self.project.constructions.values():
            if con.category in ("Окна", "Витраж") and (
                    not con.shgc or con.shgc <= 0):
                missing.append(f"{con.category}/{con.type_name}")
        if missing:
            n = len(missing)
            preview = ", ".join(missing[:3])
            if n > 3:
                preview += f" … и ещё {n - 3}"
            self.warn_label.configure(text=(
                f"⚠ ВНИМАНИЕ: у {n} светопрозрачных конструкций SHGC=0 — "
                f"солнечные теплопоступления НЕ учитываются в расчёте! "
                f"Откройте вкладку «3. Конструкции (U)» и задайте SHGC. "
                f"Типовые значения: 0.75 (одно-камер.), 0.60 (двух-камер.), "
                f"0.40 (тонир.), 0.30 (солнцезащ. покрытие).\n"
                f"Конструкции: {preview}"
            ))
            self.warn_frame.pack(fill="x", padx=10, pady=(8, 0),
                                  before=self.tree)
        else:
            self.warn_frame.pack_forget()

    def do_calc(self):
        if not self.project.spaces:
            messagebox.showwarning("Нет данных", "Сначала загрузите CSV.")
            return
        # Проверка SHGC перед расчётом
        missing_shgc = [con for con in self.project.constructions.values()
                        if con.category in ("Окна", "Витраж")
                        and (not con.shgc or con.shgc <= 0)]
        if missing_shgc:
            ok = messagebox.askyesno(
                "Не задан SHGC",
                f"У {len(missing_shgc)} светопрозрачных конструкций "
                f"не задан SHGC — солнечные теплопоступления НЕ будут "
                f"учтены в расчёте.\n\n"
                f"Рекомендуется открыть вкладку «3. Конструкции (U)» "
                f"и задать SHGC (типичное значение 0.5-0.6).\n\n"
                f"Продолжить расчёт без учёта солнца?")
            if not ok:
                return
        try:
            self.project.recalculate()
        except Exception as e:
            messagebox.showerror("Ошибка расчёта", f"{e}\n{traceback.format_exc()}")
            return
        self._check_shgc()
        messagebox.showinfo("Готово", f"Расчёт выполнен для {len(self.project.spaces)} помещений.")

    def refresh(self, **_):
        # Обновляем список уровней в combobox (если уровни изменились)
        levels = sorted({sp.level for sp in self.project.spaces if sp.level})
        new_vals = ["(все)"] + levels
        if list(self.level_combo.cget("values")) != new_vals:
            self.level_combo.configure(values=new_vals)
        if self.level_var.get() not in new_vals:
            self.level_var.set("(все)")

        # Получаем параметры фильтрации
        query = self.search_var.get().strip().lower()
        level_filter = self.level_var.get()
        only_loaded = self.only_loaded.get()

        # Очищаем дерево
        for i in self.tree.get_children():
            self.tree.delete(i)

        # Счётчики для сводки
        sum_q_heat = sum_q_cool = total_area = n_shown = 0

        for sp in self.project.spaces:
            # Фильтр по уровню
            if level_filter != "(все)" and sp.level != level_filter:
                continue
            # Фильтр «только с нагрузкой»
            if only_loaded and sp.heat_loss_w == 0 and sp.heat_gain_w == 0:
                continue
            # Поиск по №, имени, уровню (case-insensitive substring)
            if query:
                hay = f"{sp.number} {sp.name} {sp.level}".lower()
                if query not in hay:
                    continue

            bl = sp.heat_loss_breakdown
            bg = sp.heat_gain_breakdown
            ud_l = sp.heat_loss_w / sp.area_m2 if sp.area_m2 else 0
            ud_g = sp.heat_gain_w / sp.area_m2 if sp.area_m2 else 0
            interior = (bg.get("Люди", 0) + bg.get("Освещение", 0)
                        + bg.get("Оборудование", 0))
            self.tree.insert("", "end", iid=sp.space_id, values=(
                sp.number, sp.name, sp.level,
                round(sp.area_m2, 1),
                round(bl.get("Через ограждения", 0), 1),
                round(bl.get("Инфильтрация", 0), 1),
                round(sp.heat_loss_w, 1), round(ud_l, 1),
                round(bg.get("Солнечная радиация", 0), 1),
                round(interior, 1),
                round(sp.heat_gain_w, 1), round(ud_g, 1),
            ))
            n_shown += 1
            sum_q_heat += sp.heat_loss_w
            sum_q_cool += sp.heat_gain_w
            total_area += sp.area_m2

        # Сводка по показанным
        total = len(self.project.spaces)
        if n_shown == total:
            count_str = f"Всего: {total} помещ."
        else:
            count_str = f"Показано: {n_shown} из {total}"
        self.summary_var.set(
            f"{count_str}  |  S = {total_area:.0f} м²  |  "
            f"Σ Q зимой = {sum_q_heat / 1000:.1f} кВт  |  "
            f"Σ Q летом = {sum_q_cool / 1000:.1f} кВт"
        )

        # Сохраняем порядок строк как «исходный» для сброса сортировки
        if hasattr(self, "_sort_snapshot"):
            self._sort_snapshot()

    def do_export(self):
        if not self.project.spaces or not self.project.spaces[0].heat_loss_breakdown:
            messagebox.showwarning("Нет результатов", "Сначала выполните расчёт.")
            return
        path = filedialog.asksaveasfilename(
            defaultextension=".xlsx", filetypes=[("Excel", "*.xlsx")],
            initialfile=f"HVAC_{self.project.params.project_name}.xlsx")
        if not path:
            return
        try:
            from hvac.io_excel import export_to_excel
            export_to_excel(self.project, path)
        except Exception as e:
            messagebox.showerror("Ошибка", f"{e}\n{traceback.format_exc()}")
            return
        messagebox.showinfo("Готово", f"Файл сохранён:\n{path}")


# ===========================================================================
#  Вкладка 6. Вентиляция
# ===========================================================================


class VentilationTab(BaseTab):
    title = "6. Вентиляция"

    def build(self):
        # Кнопка запуска + сводка
        fr_top = ttk.Frame(self)
        fr_top.pack(fill="x", padx=10, pady=6)
        ttk.Button(fr_top, text="▶ Рассчитать вентиляцию",
                   command=self.do_calc).pack(side="left", padx=5)
        ttk.Button(fr_top, text="📝 Редактировать нормы…",
                   command=self._open_norms_editor).pack(side="left", padx=5)
        self.summary_var = tk.StringVar(value="")
        ttk.Label(fr_top, textvariable=self.summary_var,
                  foreground="#1F4E78",
                  font=("Segoe UI", 10, "bold")).pack(side="left", padx=12)

        # Панель поиска + фильтра по уровню
        fr_search = ttk.Frame(self)
        fr_search.pack(fill="x", padx=10, pady=(4, 2))
        from hvac.ui.tree_sort import make_search_bar, make_scrollable_tree
        search_fr, self.search_var = make_search_bar(
            fr_search, on_change=lambda q: self.refresh(),
            placeholder="(№, имя, уровень, тип)")
        search_fr.pack(side="left")
        ttk.Separator(fr_search, orient="vertical").pack(side="left",
                                                          fill="y", padx=8)
        ttk.Label(fr_search, text="Уровень:").pack(side="left", padx=2)
        self.level_var = tk.StringVar(value="(все)")
        self.level_combo = ttk.Combobox(fr_search,
                                         textvariable=self.level_var,
                                         state="readonly", width=14,
                                         values=["(все)"])
        self.level_combo.pack(side="left", padx=2)
        self.level_combo.bind("<<ComboboxSelected>>",
                               lambda e: self.refresh())

        # Таблица с ползунками и сортировкой
        cols = ("№", "Имя", "Уровень", "Тип", "S, м²", "V, м³", "Чел.",
                "Норма", "Supply", "Exhaust", "Hood", "ACH", "Метод", "Изм.")
        widths = {"№": 70, "Имя": 170, "Уровень": 120, "Тип": 130,
                  "S, м²": 55, "V, м³": 65, "Чел.": 45,
                  "Норма": 65, "Supply": 75, "Exhaust": 75,
                  "Hood": 60, "ACH": 50, "Метод": 200, "Изм.": 40}
        right_align = ("Supply", "Exhaust", "Hood", "ACH", "Норма",
                       "S, м²", "V, м³", "Чел.")
        self.tree, self._sort_snapshot, tree_frame = make_scrollable_tree(
            self, columns=cols, widths=widths, right_align=right_align,
            height=22, select_mode="extended",
        )
        tree_frame.pack(fill="both", expand=True, padx=10, pady=4)
        self.tree.bind("<Double-1>", self._edit_one)

        # Цветовая разметка: подсвечивать изменённые помещения
        self.tree.tag_configure("modified", background="#FFF4D6")

        # Массовое редактирование
        fr_bulk = ttk.LabelFrame(
            self,
            text="Массовое редактирование (Ctrl/Shift+клик для выделения)")
        fr_bulk.pack(fill="x", padx=10, pady=6)

        ttk.Label(fr_bulk, text="Поле:").grid(row=0, column=0, padx=4, pady=4)
        self.bulk_field = tk.StringVar(value="Supply")
        ttk.Combobox(fr_bulk, textvariable=self.bulk_field,
                     values=["Supply", "Exhaust", "Hood",
                             "Supply+Exhaust (баланс)"],
                     state="readonly", width=22).grid(row=0, column=1, padx=4)

        ttk.Label(fr_bulk, text="Значение, м³/ч:").grid(row=0, column=2, padx=4)
        self.bulk_value = tk.StringVar(value="0")
        ttk.Entry(fr_bulk, textvariable=self.bulk_value, width=10).grid(row=0, column=3, padx=4)

        ttk.Button(fr_bulk, text="Применить к выделенным",
                   command=self._bulk_apply).grid(row=0, column=4, padx=8)
        ttk.Button(fr_bulk, text="Сбросить выделенные к авто",
                   command=self._bulk_reset).grid(row=0, column=5, padx=4)

        # Подсказка
        ttk.Label(self,
                  text="Двойной клик — редактировать одно помещение. "
                       "Жёлтые строки изменены вручную и не пересчитываются.",
                  foreground="#666666").pack(anchor="w", padx=10, pady=4)

    def subscribe_events(self):
        self.project.subscribe("ventilation_done", self.refresh)
        self.project.subscribe("project_loaded", self.refresh)

    def do_calc(self):
        if not self.project.spaces:
            messagebox.showwarning("Нет данных", "Сначала загрузите CSV.")
            return
        try:
            self.project.calculate_ventilation()
        except Exception as e:
            messagebox.showerror("Ошибка расчёта",
                                 f"{e}\n{traceback.format_exc()}")
            return
        skipped = sum(1 for s in self.project.spaces if s.vent_user_modified)
        msg = f"Вентиляция рассчитана для {len(self.project.spaces) - skipped} помещ."
        if skipped:
            msg += f"\n{skipped} помещ. пропущено (изменены вручную)."
        messagebox.showinfo("Готово", msg)

    def refresh(self, **kwargs):
        # Обновляем список уровней
        levels = sorted({sp.level for sp in self.project.spaces if sp.level})
        new_vals = ["(все)"] + levels
        if list(self.level_combo.cget("values")) != new_vals:
            self.level_combo.configure(values=new_vals)
        if self.level_var.get() not in new_vals:
            self.level_var.set("(все)")

        query = self.search_var.get().strip().lower()
        level_filter = self.level_var.get()

        for i in self.tree.get_children():
            self.tree.delete(i)

        total_s = total_e = total_h = 0.0
        n_modified = n_shown = 0
        for sp in self.project.spaces:
            if level_filter != "(все)" and sp.level != level_filter:
                continue
            if query:
                hay = f"{sp.number} {sp.name} {sp.level} {sp.room_type}".lower()
                if query not in hay:
                    continue

            br = sp.ventilation_breakdown or {}
            total_s += sp.supply_m3h
            total_e += sp.exhaust_m3h
            total_h += sp.hood_m3h
            if sp.vent_user_modified:
                n_modified += 1
            tags = ("modified",) if sp.vent_user_modified else ()
            self.tree.insert("", "end", iid=sp.space_id, tags=tags, values=(
                sp.number, sp.name, sp.level, sp.room_type,
                round(sp.area_m2, 1), round(sp.volume_m3, 1),
                sp.occupancy_people,
                br.get("fresh_air_per_person", 0),
                round(sp.supply_m3h, 0), round(sp.exhaust_m3h, 0),
                round(sp.hood_m3h, 0) if sp.hood_m3h else "—",
                f"{sp.ach_calculated:.2f}" if sp.ach_calculated else "—",
                br.get("method", ""),
                "✓" if sp.vent_user_modified else "",
            ))
            n_shown += 1

        s = (f"Показ.: {n_shown}/{len(self.project.spaces)}   |   "
             f"Σ Supply: {total_s:,.0f}   |   "
             f"Σ Exhaust: {total_e:,.0f}   |   "
             f"Σ Hood: {total_h:,.0f} м³/ч").replace(",", " ")
        if n_modified:
            s += f"   |   ручн.: {n_modified}"
        self.summary_var.set(s)
        if hasattr(self, "_sort_snapshot"):
            self._sort_snapshot()

    def _edit_one(self, event):
        """Окно редактирования одного помещения."""
        sel = self.tree.selection()
        if not sel:
            return
        sp = self.project.get_space(sel[0])
        if not sp:
            return

        win = tk.Toplevel(self)
        win.title(f"Вентиляция {sp.number} — {sp.name}")
        win.geometry("520x520")
        win.transient(self.winfo_toplevel())

        # Информация
        info_fr = ttk.LabelFrame(win, text="Информация")
        info_fr.pack(fill="x", padx=10, pady=8)
        for line in [
            f"Тип:     {sp.room_type}",
            f"S / V:   {sp.area_m2:.1f} м² / {sp.volume_m3:.1f} м³",
            f"Людей:   {sp.occupancy_people}",
        ]:
            ttk.Label(info_fr, text=line).pack(anchor="w", padx=8, pady=2)

        # Текущий расчёт
        br = sp.ventilation_breakdown or {}
        calc_fr = ttk.LabelFrame(win, text="Авторасчёт (СП 60.13330)")
        calc_fr.pack(fill="x", padx=10, pady=4)
        ttk.Label(calc_fr, text=f"Метод: {br.get('method', '—')}",
                  foreground="#555").pack(anchor="w", padx=8, pady=2)
        ttk.Label(calc_fr, text=f"Норма: {br.get('note', '—')}",
                  foreground="#555").pack(anchor="w", padx=8, pady=2)

        # Редактируемые поля
        edit_fr = ttk.LabelFrame(win, text="Значения (можно править)")
        edit_fr.pack(fill="x", padx=10, pady=8)

        rows = [
            ("Supply, м³/ч (приток):", "supply_m3h"),
            ("Exhaust, м³/ч (вытяжка):", "exhaust_m3h"),
            ("Hood, м³/ч (зонт):", "hood_m3h"),
        ]
        vars_ = {}
        for i, (label, attr) in enumerate(rows):
            ttk.Label(edit_fr, text=label).grid(row=i, column=0, sticky="w",
                                                padx=8, pady=4)
            v = tk.StringVar(value=f"{getattr(sp, attr):.1f}")
            ttk.Entry(edit_fr, textvariable=v, width=15).grid(row=i, column=1,
                                                              padx=8, pady=4)
            vars_[attr] = v

        # Статус
        status_var = tk.StringVar(
            value=("✓ Изменено вручную — при расчёте не перезаписывается"
                   if sp.vent_user_modified
                   else "○ Автоматически — будет пересчитано при обновлении"))
        ttk.Label(win, textvariable=status_var,
                  foreground="#1F4E78" if sp.vent_user_modified else "#666",
                  font=("Segoe UI", 9, "italic")
                  ).pack(anchor="w", padx=15, pady=4)

        # Кнопки
        btn_fr = ttk.Frame(win)
        btn_fr.pack(fill="x", padx=10, pady=10)

        def save():
            try:
                for attr, v in vars_.items():
                    setattr(sp, attr, float(v.get().replace(",", ".")))
                sp.vent_user_modified = True
                # Пересчитываем фактическую кратность
                if sp.volume_m3 > 0:
                    sp.ach_calculated = sp.supply_m3h / sp.volume_m3
            except ValueError:
                messagebox.showerror("Ошибка", "Введите числовые значения.")
                return
            self.refresh()
            win.destroy()

        def reset_auto():
            """Сбросить к автоматическому расчёту."""
            from hvac.engine.ventilation import get_ventilation_engine
            engine = get_ventilation_engine()
            br = engine.calculate(sp, self.project)
            sp.ventilation_breakdown = br
            sp.supply_m3h = br.get("supply_m3h", 0.0)
            sp.exhaust_m3h = br.get("exhaust_m3h", 0.0)
            sp.hood_m3h = br.get("hood_m3h", 0.0)
            sp.ach_calculated = br.get("ach_calculated", 0.0)
            sp.vent_user_modified = False
            self.refresh()
            win.destroy()

        ttk.Button(btn_fr, text="Сохранить",
                   command=save).pack(side="right", padx=5)
        ttk.Button(btn_fr, text="Сбросить к авто",
                   command=reset_auto).pack(side="right", padx=5)
        ttk.Button(btn_fr, text="Отмена",
                   command=win.destroy).pack(side="right", padx=5)

    def _bulk_apply(self):
        """Применить значение ко всем выделенным."""
        sel = self.tree.selection()
        if not sel:
            messagebox.showinfo("Информация",
                                "Выделите строки (Ctrl/Shift+клик).")
            return
        try:
            val = float(self.bulk_value.get().replace(",", "."))
        except ValueError:
            messagebox.showerror("Ошибка", "Введите числовое значение.")
            return
        if val < 0:
            messagebox.showerror("Ошибка", "Значение не может быть отрицательным.")
            return

        field = self.bulk_field.get()
        n = 0
        for iid in sel:
            sp = self.project.get_space(iid)
            if not sp:
                continue
            if field == "Supply":
                sp.supply_m3h = val
            elif field == "Exhaust":
                sp.exhaust_m3h = val
            elif field == "Hood":
                sp.hood_m3h = val
            elif field == "Supply+Exhaust (баланс)":
                sp.supply_m3h = val
                sp.exhaust_m3h = val
            sp.vent_user_modified = True
            if sp.volume_m3 > 0:
                sp.ach_calculated = sp.supply_m3h / sp.volume_m3
            n += 1
        self.refresh()
        messagebox.showinfo("OK",
                            f"{field} = {val} м³/ч применено к {n} помещ.")

    def _bulk_reset(self):
        """Сбросить выделенные к автоматическому расчёту."""
        sel = self.tree.selection()
        if not sel:
            messagebox.showinfo("Информация",
                                "Выделите строки (Ctrl/Shift+клик).")
            return
        from hvac.engine.ventilation import get_ventilation_engine
        engine = get_ventilation_engine()
        n = 0
        for iid in sel:
            sp = self.project.get_space(iid)
            if not sp:
                continue
            br = engine.calculate(sp, self.project)
            sp.ventilation_breakdown = br
            sp.supply_m3h = br.get("supply_m3h", 0.0)
            sp.exhaust_m3h = br.get("exhaust_m3h", 0.0)
            sp.hood_m3h = br.get("hood_m3h", 0.0)
            sp.ach_calculated = br.get("ach_calculated", 0.0)
            sp.vent_user_modified = False
            n += 1
        self.refresh()
        messagebox.showinfo("OK", f"Сброшено к автоматическому расчёту: {n} помещ.")

    def _show_details(self, event):
        """Старая функция оставлена для совместимости (не используется)."""
        pass

    # -------------------------------------------------------------------
    #  Редактор норм вентиляции (по типам помещений)
    # -------------------------------------------------------------------
    def _open_norms_editor(self):
        """Окно редактирования норм вентиляции для типов помещений.

        Изменения сохраняются глобально (в %APPDATA%/HVAC/user_norms.json
        на Windows или ~/.config/HVAC/user_norms.json на Linux) и
        применяются ко всем проектам. После сохранения автоматически
        предлагается пересчитать вентиляцию текущего проекта.
        """
        from hvac.catalogs import user_norms as un
        from hvac.catalogs.ventilation_norms import VENTILATION_NORMS

        win = tk.Toplevel(self)
        win.title("Нормы вентиляции — редактор")
        win.geometry("960x680")
        win.transient(self.winfo_toplevel())

        # Подсказка про область действия
        hint = (f"Изменения сохраняются глобально для всех проектов:\n"
                f"  {un._user_norms_path()}\n"
                f"Применяются к помещениям соответствующего типа при "
                f"следующем расчёте вентиляции.")
        ttk.Label(win, text=hint, foreground="#666",
                  font=("Segoe UI", 8), justify="left"
                  ).pack(anchor="w", padx=10, pady=(8, 4))

        # ===== Сплит: слева список типов, справа форма =====
        paned = ttk.PanedWindow(win, orient="horizontal")
        paned.pack(fill="both", expand=True, padx=10, pady=4)

        # --- Левая панель: список типов ---
        left = ttk.LabelFrame(paned, text="Типы помещений")
        paned.add(left, weight=1)

        types_tree = ttk.Treeview(left, columns=("kind",),
                                   show="tree headings", height=22,
                                   selectmode="browse")
        types_tree.heading("#0", text="Тип")
        types_tree.heading("kind", text="Источник")
        types_tree.column("#0", width=180, anchor="w")
        types_tree.column("kind", width=80, anchor="center")
        types_tree.pack(fill="both", expand=True, padx=4, pady=4)
        types_tree.tag_configure("overridden", foreground="#0066AA")
        types_tree.tag_configure("custom", foreground="#9933CC")

        # Кнопки управления типами
        btn_left = ttk.Frame(left)
        btn_left.pack(fill="x", padx=4, pady=4)
        ttk.Button(btn_left, text="+ Новый тип",
                   command=lambda: _add_new_type()
                   ).pack(side="left", padx=2)
        ttk.Button(btn_left, text="🗑 Удалить",
                   command=lambda: _delete_type()
                   ).pack(side="left", padx=2)

        # --- Правая панель: форма редактирования ---
        right = ttk.LabelFrame(paned, text="Параметры нормы")
        paned.add(right, weight=2)

        current_type_var = tk.StringVar(value="")
        ttk.Label(right, textvariable=current_type_var,
                  font=("Segoe UI", 11, "bold"),
                  foreground="#1F4E78"
                  ).pack(anchor="w", padx=10, pady=(8, 2))

        status_var = tk.StringVar(value="")
        ttk.Label(right, textvariable=status_var, foreground="#888",
                  font=("Segoe UI", 9, "italic")
                  ).pack(anchor="w", padx=10, pady=(0, 8))

        # Все поля нормы (label, ключ, тип)
        # Boolean: чекбоксы; float: текстовые поля
        FIELD_DEFS = [
            ("__bool__", "is_NC",
             "Без принудительной вентиляции (NC) — лестницы, лифты"),
            ("__bool__", "exhaust_only",
             "Только вытяжка (туалеты) — приток из перетока"),
            ("__bool__", "has_hood",
             "С зонтом (кухня) — часть вытяжки через зонт"),
            ("__bool__", "has_co_control",
             "Управление по CO (парковки)"),
            ("__sep__", "Приток (бóльшее из критериев)", ""),
            ("float", "m3_per_person",
             "На человека, м³/ч"),
            ("float", "m3_per_m2",
             "На м² площади, м³/ч·м²"),
            ("float", "min_ach",
             "Минимальная кратность, 1/ч"),
            ("float", "m3_per_kw_equipment",
             "На кВт тепловыделений, м³/ч·кВт"),
            ("__sep__", "Вытяжка", ""),
            ("float", "balance",
             "Дисбаланс, % (отриц. → вытяжка > приток)"),
            ("float", "exhaust_per_m2",
             "Удельная вытяжка (туалеты), м³/ч·м²"),
            ("float", "exhaust_min",
             "Минимальная вытяжка, м³/ч"),
            ("__sep__", "Зонт", ""),
            ("float", "hood_factor",
             "Доля вытяжки через зонт (0..1)"),
            ("__sep__", "Описание", ""),
            ("text", "note",
             "Норматив / комментарий"),
        ]

        # Контейнер с формой (Canvas + Frame для прокрутки)
        form_canvas = tk.Canvas(right, highlightthickness=0)
        form_scroll = ttk.Scrollbar(right, orient="vertical",
                                     command=form_canvas.yview)
        form_canvas.configure(yscrollcommand=form_scroll.set)
        form_canvas.pack(side="left", fill="both", expand=True,
                         padx=(10, 0), pady=4)
        form_scroll.pack(side="right", fill="y", pady=4)
        form_inner = ttk.Frame(form_canvas)
        form_canvas.create_window((0, 0), window=form_inner, anchor="nw")

        def _on_form_config(event=None):
            form_canvas.configure(scrollregion=form_canvas.bbox("all"))
        form_inner.bind("<Configure>", _on_form_config)

        # Создаём виджеты формы один раз
        form_vars: Dict[str, tk.Variable] = {}
        row_idx = 0
        for kind, key, label in FIELD_DEFS:
            if kind == "__sep__":
                ttk.Separator(form_inner, orient="horizontal").grid(
                    row=row_idx, column=0, columnspan=2, sticky="ew",
                    padx=4, pady=(8, 2))
                row_idx += 1
                ttk.Label(form_inner, text=key, font=("Segoe UI", 9, "bold"),
                          foreground="#444"
                          ).grid(row=row_idx, column=0, columnspan=2,
                                 sticky="w", padx=4, pady=(0, 4))
                row_idx += 1
                continue
            ttk.Label(form_inner, text=label, wraplength=320,
                      justify="left"
                      ).grid(row=row_idx, column=0, sticky="w",
                             padx=4, pady=2)
            if kind == "__bool__":
                v = tk.BooleanVar(value=False)
                ttk.Checkbutton(form_inner, variable=v).grid(
                    row=row_idx, column=1, sticky="w", padx=4, pady=2)
            elif kind == "text":
                v = tk.StringVar(value="")
                ttk.Entry(form_inner, textvariable=v, width=35).grid(
                    row=row_idx, column=1, sticky="w", padx=4, pady=2)
            else:  # float
                v = tk.StringVar(value="")
                ttk.Entry(form_inner, textvariable=v, width=12).grid(
                    row=row_idx, column=1, sticky="w", padx=4, pady=2)
            form_vars[key] = v
            row_idx += 1

        # ===== Загрузка/сохранение значений в форме =====
        current = {"type": None}   # mutable closure

        def _load_form(room_type: str):
            """Заполнить форму значениями для типа."""
            current["type"] = room_type
            norms = un.get_ventilation_norms(room_type)
            # Заголовок и статус
            current_type_var.set(room_type)
            if un.is_custom_type(room_type):
                status_var.set(
                    "⊕ Пользовательский тип — все поля сохраняются как есть.")
            elif un.has_ventilation_override(room_type):
                ovr = un.get_raw_override(room_type)
                fields = ", ".join(sorted(ovr.keys()))
                status_var.set(
                    f"✓ Переопределены поля: {fields}. "
                    f"СП-значения остальных полей сохраняются.")
            else:
                status_var.set(
                    f"○ Без правок — используются значения по СП.")

            for kind, key, _label in FIELD_DEFS:
                if kind == "__sep__":
                    continue
                v = form_vars[key]
                val = norms.get(key)
                if kind == "__bool__":
                    v.set(bool(val))
                elif kind == "text":
                    v.set(str(val) if val is not None else "")
                else:
                    if val is None or val == 0:
                        v.set("")
                    else:
                        v.set(f"{val:g}")

        def _collect_form() -> Dict:
            """Собрать значения формы в dict, пропустить пустые."""
            result: Dict = {}
            for kind, key, _label in FIELD_DEFS:
                if kind == "__sep__":
                    continue
                v = form_vars[key]
                if kind == "__bool__":
                    if v.get():
                        result[key] = True
                    # False = не сохраняем (СП-дефолт = отсутствие флага)
                elif kind == "text":
                    s = v.get().strip()
                    if s:
                        result[key] = s
                else:  # float
                    s = v.get().strip().replace(",", ".")
                    if not s:
                        continue
                    try:
                        result[key] = float(s)
                    except ValueError:
                        raise ValueError(
                            f"Поле '{_label}' не число: {s!r}")
            return result

        # ===== Заполнение списка типов =====
        def _refresh_types_list(select: Optional[str] = None):
            for i in types_tree.get_children():
                types_tree.delete(i)
            # Сначала встроенные
            for t in un.get_builtin_room_types():
                if un.has_ventilation_override(t):
                    types_tree.insert("", "end", iid=t, text=t,
                                       values=("СП ✓",), tags=("overridden",))
                else:
                    types_tree.insert("", "end", iid=t, text=t,
                                       values=("СП",))
            # Потом пользовательские
            for t in un.get_custom_room_types():
                types_tree.insert("", "end", iid=t, text=t,
                                   values=("польз.",), tags=("custom",))
            if select and select in types_tree.get_children(""):
                types_tree.selection_set(select)
                types_tree.see(select)

        def _on_type_select(event=None):
            sel = types_tree.selection()
            if not sel:
                return
            # Перед переключением — если в текущем есть несохранённые изменения,
            # автоприменяем их в кэш (диск пишется только по Сохранить).
            if current["type"] and current["type"] != sel[0]:
                try:
                    new_vals = _collect_form()
                    un.set_ventilation_override(
                        current["type"], new_vals, autosave=False)
                    _refresh_types_list(select=sel[0])
                except (ValueError, KeyError):
                    pass   # некорректное число — просто переключаемся
            _load_form(sel[0])

        types_tree.bind("<<TreeviewSelect>>", _on_type_select)

        # ===== Действия кнопок =====
        def _add_new_type():
            from tkinter.simpledialog import askstring
            name = askstring(
                "Новый тип",
                "Имя нового типа помещения\n(например: «СПА-зона», "
                "«Кинозал», «Бассейн»):",
                parent=win)
            if not name:
                return
            name = name.strip()
            try:
                un.add_custom_type(name, ventilation={}, thermal={},
                                    autosave=False)
            except ValueError as e:
                messagebox.showerror("Ошибка", str(e), parent=win)
                return
            _refresh_types_list(select=name)
            _load_form(name)

        def _delete_type():
            t = current["type"]
            if not t:
                return
            if not un.is_custom_type(t):
                messagebox.showinfo(
                    "Нельзя удалить",
                    f"Тип «{t}» встроенный (СП). Можно только сбросить "
                    f"его override.",
                    parent=win)
                return
            # Проверка: есть ли помещения этого типа в текущем проекте
            in_use = sum(1 for sp in self.project.spaces
                         if sp.room_type == t)
            extra = ""
            if in_use:
                extra = (f"\n\n⚠ В текущем проекте {in_use} помещений "
                         f"имеют этот тип. После удаления они станут "
                         f"использовать дефолт «Прочее».")
            if not messagebox.askyesno(
                    "Удалить тип?",
                    f"Удалить пользовательский тип «{t}»?{extra}",
                    parent=win):
                return
            un.delete_custom_type(t, autosave=False)
            current["type"] = None
            current_type_var.set("")
            status_var.set("")
            _refresh_types_list()

        def _reset_current():
            t = current["type"]
            if not t:
                return
            if un.is_custom_type(t):
                messagebox.showinfo(
                    "Информация",
                    "Пользовательский тип нельзя «сбросить к СП» — "
                    "только удалить.",
                    parent=win)
                return
            if not un.has_ventilation_override(t):
                messagebox.showinfo(
                    "Информация",
                    f"У типа «{t}» нет правок — значения уже из СП.",
                    parent=win)
                return
            un.reset_ventilation_override(t, autosave=False)
            _refresh_types_list(select=t)
            _load_form(t)

        def _save_and_close(recalc: bool):
            # Применяем форму к текущему типу
            t = current["type"]
            if t:
                try:
                    new_vals = _collect_form()
                except ValueError as e:
                    messagebox.showerror("Ошибка", str(e), parent=win)
                    return
                try:
                    un.set_ventilation_override(t, new_vals, autosave=False)
                except ValueError as e:
                    messagebox.showerror("Ошибка", str(e), parent=win)
                    return
            # Сохраняем на диск (один раз)
            try:
                path = un.save_to_disk()
            except OSError as e:
                messagebox.showerror(
                    "Ошибка записи",
                    f"Не удалось сохранить нормы:\n{e}", parent=win)
                return
            win.destroy()
            if recalc and self.project.spaces:
                # Сбрасываем флаг vent_user_modified, чтобы новые нормы
                # реально пересчитались. (По умолчанию — нет, чтобы не
                # затереть ручные правки. Тут спрашиваем.)
                manual = [sp for sp in self.project.spaces
                          if sp.vent_user_modified]
                if manual and messagebox.askyesno(
                        "Сбросить ручные правки?",
                        f"В проекте {len(manual)} помещений с ручными "
                        f"правками вентиляции. Сбросить их, чтобы пересчёт "
                        f"применил новые нормы?\n\n"
                        f"«Нет» — пересчитать только помещения без ручных "
                        f"правок.",
                        parent=self.winfo_toplevel()):
                    for sp in manual:
                        sp.vent_user_modified = False
                try:
                    self.project.calculate_ventilation()
                    messagebox.showinfo(
                        "Готово",
                        f"Нормы сохранены: {path}\n"
                        f"Вентиляция пересчитана.")
                except Exception as e:
                    messagebox.showerror(
                        "Ошибка расчёта",
                        f"{e}\n{traceback.format_exc()}")
            else:
                messagebox.showinfo(
                    "Сохранено",
                    f"Нормы сохранены: {path}\n"
                    f"Они применятся при следующем расчёте вентиляции.")

        # ===== Нижняя панель кнопок =====
        btn_bottom = ttk.Frame(win)
        btn_bottom.pack(fill="x", padx=10, pady=8)
        ttk.Button(btn_bottom, text="↺ Сбросить тип к СП",
                   command=_reset_current).pack(side="left", padx=4)
        ttk.Button(btn_bottom, text="Отмена",
                   command=win.destroy).pack(side="right", padx=4)
        ttk.Button(btn_bottom, text="💾 Сохранить",
                   command=lambda: _save_and_close(recalc=False)
                   ).pack(side="right", padx=4)
        ttk.Button(btn_bottom, text="💾 Сохранить и пересчитать",
                   command=lambda: _save_and_close(recalc=True)
                   ).pack(side="right", padx=4)

        # Первичное заполнение
        _refresh_types_list()
        # Выбрать тип из текущего выделения в основной таблице, если есть,
        # иначе первый
        sel_in_main = self.tree.selection() if hasattr(self, "tree") else ()
        initial = "Офис"
        if sel_in_main:
            sp0 = self.project.get_space(sel_in_main[0])
            if sp0 and sp0.room_type in types_tree.get_children(""):
                initial = sp0.room_type
        types_tree.selection_set(initial)
        types_tree.see(initial)
        _load_form(initial)


# ===========================================================================
#  Вкладка 7. Зоны и системы
# ===========================================================================


class ZonesTab(BaseTab):
    title = "7. Зоны и системы"

    def build(self):
        # Верхняя панель: авто-присвоение
        fr_top = ttk.LabelFrame(self, text="Авто-присвоение зон")
        fr_top.pack(fill="x", padx=10, pady=6)

        ttk.Label(fr_top, text="Логика:").grid(row=0, column=0, padx=4, pady=4)
        self.auto_mode = tk.StringVar(value="by_prefix")
        ttk.Radiobutton(fr_top, text="По префиксу номера (B01-, OFC-)",
                        variable=self.auto_mode, value="by_prefix"
                        ).grid(row=0, column=1, padx=4, sticky="w")
        ttk.Radiobutton(fr_top, text="По уровню",
                        variable=self.auto_mode, value="by_level"
                        ).grid(row=0, column=2, padx=4, sticky="w")
        ttk.Radiobutton(fr_top, text="По группе типов",
                        variable=self.auto_mode, value="by_type_family"
                        ).grid(row=0, column=3, padx=4, sticky="w")

        self.overwrite_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(fr_top, text="Перезаписать существующие",
                        variable=self.overwrite_var
                        ).grid(row=1, column=1, padx=4, sticky="w")

        ttk.Button(fr_top, text="Применить",
                   command=self._do_auto_assign).grid(row=1, column=3, padx=4)

        # Выбор системы для просмотра
        fr_sys = ttk.Frame(self)
        fr_sys.pack(fill="x", padx=10, pady=4)
        ttk.Label(fr_sys, text="Показать систему:",
                  font=("Segoe UI", 9, "bold")).pack(side="left", padx=4)
        self.system_var = tk.StringVar(value="heating")
        for label, val in [("Отопление", "heating"),
                           ("Охлаждение", "cooling"),
                           ("Вентиляция", "ventilation")]:
            ttk.Radiobutton(fr_sys, text=label, variable=self.system_var,
                            value=val, command=self.refresh
                            ).pack(side="left", padx=4)

        # Сплит: слева помещения, справа сводка
        paned = ttk.PanedWindow(self, orient="horizontal")
        paned.pack(fill="both", expand=True, padx=10, pady=4)

        # Левая часть: список помещений
        left_fr = ttk.LabelFrame(paned, text="Помещения и их зоны")
        paned.add(left_fr, weight=3)

        # Поиск над таблицей
        from hvac.ui.tree_sort import make_search_bar, make_scrollable_tree
        search_fr, self.search_var = make_search_bar(
            left_fr, on_change=lambda q: self.refresh(),
            placeholder="(№, имя, уровень, тип, зона)")
        search_fr.pack(fill="x", padx=4, pady=2)

        cols = ("№", "Имя", "Уровень", "Тип", "Q отопл.", "Q охл.",
                "Supply", "Зона отопл.", "Зона охл.", "Зона вент.")
        widths = {"№": 75, "Имя": 150, "Уровень": 90, "Тип": 100,
                  "Q отопл.": 70, "Q охл.": 70, "Supply": 70,
                  "Зона отопл.": 95, "Зона охл.": 95, "Зона вент.": 95}
        right_align = ("Q отопл.", "Q охл.", "Supply")
        self.tree, self._sort_snapshot, tree_frame = make_scrollable_tree(
            left_fr, columns=cols, widths=widths, right_align=right_align,
            height=20, select_mode="extended",
        )
        tree_frame.pack(fill="both", expand=True, padx=4, pady=4)

        # Mass edit под таблицей
        fr_bulk = ttk.LabelFrame(left_fr,
                                  text="Массовое назначение (Ctrl+клик)")
        fr_bulk.pack(fill="x", padx=4, pady=4)

        ttk.Label(fr_bulk, text="Применить к системе:").grid(row=0, column=0, padx=4, pady=4)
        self.bulk_system = tk.StringVar(value="all")
        ttk.Combobox(fr_bulk, textvariable=self.bulk_system,
                     values=["all", "heating", "cooling", "ventilation"],
                     state="readonly", width=12).grid(row=0, column=1, padx=4)

        ttk.Label(fr_bulk, text="Имя зоны:").grid(row=0, column=2, padx=4)
        self.bulk_zone_name = tk.StringVar(value="")
        ttk.Entry(fr_bulk, textvariable=self.bulk_zone_name, width=20
                  ).grid(row=0, column=3, padx=4)

        ttk.Button(fr_bulk, text="Применить к выделенным",
                   command=self._bulk_assign).grid(row=0, column=4, padx=4)
        ttk.Button(fr_bulk, text="Очистить",
                   command=self._bulk_clear).grid(row=0, column=5, padx=4)

        # Правая часть: сводка по зонам
        right_fr = ttk.LabelFrame(paned, text="Сводка по зонам")
        paned.add(right_fr, weight=2)

        summary_cols = ("Зона", "Помещ.", "Площадь", "Нагрузка",
                        "Sens / Lat", "Типовое оборуд.")
        widths_s = {"Зона": 130, "Помещ.": 55, "Площадь": 75,
                    "Нагрузка": 85, "Sens / Lat": 100,
                    "Типовое оборуд.": 110}
        self.summary_tree, self._sum_sort_snapshot, sum_frame = \
            make_scrollable_tree(
                right_fr, columns=summary_cols, widths=widths_s,
                right_align=("Помещ.", "Площадь", "Нагрузка"),
                height=15, select_mode="browse",
            )
        sum_frame.pack(fill="both", expand=True, padx=4, pady=4)

        self.totals_label = tk.StringVar(value="")
        ttk.Label(right_fr, textvariable=self.totals_label,
                  foreground="#1F4E78",
                  font=("Segoe UI", 9, "bold")).pack(anchor="w", padx=8, pady=4)

    def subscribe_events(self):
        self.project.subscribe("calculation_done", self.refresh)
        self.project.subscribe("ventilation_done", self.refresh)
        self.project.subscribe("zones_changed", self.refresh)
        self.project.subscribe("project_loaded", self.refresh)

    def _do_auto_assign(self):
        if not self.project.spaces:
            messagebox.showwarning("Нет данных", "Сначала загрузите CSV.")
            return
        n = self.project.auto_assign_zones(
            mode=self.auto_mode.get(),
            overwrite=self.overwrite_var.get())
        messagebox.showinfo("OK", f"Зоны присвоены для {n} помещений.")

    def _bulk_assign(self):
        sel = self.tree.selection()
        if not sel:
            messagebox.showinfo("Информация",
                                "Выделите строки (Ctrl/Shift+клик).")
            return
        zone = self.bulk_zone_name.get().strip()
        if not zone:
            messagebox.showerror("Ошибка", "Введите имя зоны.")
            return
        system = self.bulk_system.get()
        n = 0
        for iid in sel:
            sp = self.project.get_space(iid)
            if not sp:
                continue
            if system in ("heating", "all"):
                sp.system_heating = zone
            if system in ("cooling", "all"):
                sp.system_cooling = zone
            if system in ("ventilation", "all"):
                sp.system_ventilation = zone
            n += 1
        self.refresh()
        messagebox.showinfo("OK", f"Зона «{zone}» применена к {n} помещ.")

    def _bulk_clear(self):
        sel = self.tree.selection()
        if not sel:
            messagebox.showinfo("Информация",
                                "Выделите строки (Ctrl/Shift+клик).")
            return
        system = self.bulk_system.get()
        n = 0
        for iid in sel:
            sp = self.project.get_space(iid)
            if not sp:
                continue
            if system in ("heating", "all"):
                sp.system_heating = ""
            if system in ("cooling", "all"):
                sp.system_cooling = ""
            if system in ("ventilation", "all"):
                sp.system_ventilation = ""
            n += 1
        self.refresh()

    def refresh(self, **kwargs):
        # Авто-синхронизация: при переключении просмотра системы
        # массовое назначение тоже переключается на эту систему
        system = self.system_var.get()
        if self.bulk_system.get() == "all":
            self.bulk_system.set(system)

        # Таблица помещений (с поиском)
        query = self.search_var.get().strip().lower()
        for i in self.tree.get_children():
            self.tree.delete(i)
        for sp in self.project.spaces:
            if query:
                hay = (f"{sp.number} {sp.name} {sp.level} {sp.room_type} "
                       f"{sp.system_heating} {sp.system_cooling} "
                       f"{sp.system_ventilation}").lower()
                if query not in hay:
                    continue
            self.tree.insert("", "end", iid=sp.space_id, values=(
                sp.number, sp.name, sp.level, sp.room_type,
                round(sp.heat_loss_w, 0),
                round(sp.heat_gain_w, 0),
                round(sp.supply_m3h, 0),
                sp.system_heating, sp.system_cooling, sp.system_ventilation,
            ))
        if hasattr(self, "_sort_snapshot"):
            self._sort_snapshot()

        # Сводка по выбранной системе
        for i in self.summary_tree.get_children():
            self.summary_tree.delete(i)
        from hvac.project import (suggest_ahu_size, suggest_boiler_size,
                                   suggest_chiller_size)
        summary = self.project.get_zone_summary(system)

        sort_key = {"heating": "q_heating_w",
                    "cooling": "q_cooling_w",
                    "ventilation": "supply_m3h"}[system]

        total_q = total_sup = total_a = total_n = 0
        for zone, d in sorted(summary.items(), key=lambda x: -x[1][sort_key]):
            if system == "heating":
                q_text = f"{d['q_heating_w']/1000:.1f} кВт"
                sens_lat = "—"
                equip = suggest_boiler_size(d["q_heating_w"])
            elif system == "cooling":
                q_text = f"{d['q_cooling_w']/1000:.1f} кВт"
                sens_lat = f"{d['q_sensible_w']/1000:.0f} / {d['q_latent_w']/1000:+.0f}"
                equip = suggest_chiller_size(d["q_cooling_w"])
            else:  # ventilation
                q_text = f"{d['supply_m3h']:,.0f}".replace(",", " ")
                sens_lat = f"E: {d['exhaust_m3h']:,.0f}".replace(",", " ")
                equip = suggest_ahu_size(d["supply_m3h"]) + " м³/ч"
            self.summary_tree.insert("", "end", values=(
                zone, d["n_spaces"], f"{d['area_m2']:.0f}",
                q_text, sens_lat, equip,
            ))
            total_q += d['q_heating_w'] if system == "heating" else d['q_cooling_w']
            total_sup += d['supply_m3h']
            total_a += d['area_m2']
            total_n += d['n_spaces']

        if system == "heating":
            self.totals_label.set(
                f"Σ для подбора котлов: {total_q/1000:.1f} кВт   "
                f"({total_n} помещ., {total_a:.0f} м²)")
        elif system == "cooling":
            self.totals_label.set(
                f"Σ для подбора чиллеров: {total_q/1000:.1f} кВт   "
                f"({total_n} помещ., {total_a:.0f} м²)")
        else:
            self.totals_label.set(
                f"Σ для подбора AHU: {total_sup:,.0f} м³/ч приток".replace(",", " "))
        if hasattr(self, "_sum_sort_snapshot"):
            self._sum_sort_snapshot()


# ===========================================================================
#  Вкладка 8. Оборудование
# ===========================================================================


class EquipmentTab(BaseTab):
    """Редактирование параметров приточек, котлов, чиллеров.
    Каждая система имеет индивидуальные параметры."""
    title = "8. Оборудование"

    def build(self):
        # Сверху — выбор типа системы
        fr_top = ttk.Frame(self)
        fr_top.pack(fill="x", padx=10, pady=6)
        ttk.Label(fr_top, text="Тип системы:",
                  font=("Segoe UI", 10, "bold")).pack(side="left", padx=4)
        self.system_kind = tk.StringVar(value="ventilation")
        for label, val in [("Приточные установки", "ventilation"),
                           ("Котлы", "heating"),
                           ("Чиллеры", "cooling")]:
            ttk.Radiobutton(fr_top, text=label, variable=self.system_kind,
                            value=val, command=self.refresh
                            ).pack(side="left", padx=6)

        ttk.Button(fr_top, text="Рассчитать нагрузки от AHU",
                   command=self._calc_ahu).pack(side="right", padx=4)

        # Таблица параметров
        self.tree_frame = ttk.Frame(self)
        self.tree_frame.pack(fill="both", expand=True, padx=10, pady=6)

        self.tree = None
        self._build_tree()

        # Двойной клик — редактирование
        ttk.Label(self, text="Двойной клик по строке — редактировать параметры.",
                  foreground="#666").pack(anchor="w", padx=10, pady=4)

        # Нагрузки AHU отдельно
        self.ahu_label = tk.StringVar(value="")
        ttk.Label(self, textvariable=self.ahu_label,
                  foreground="#1F4E78", font=("Segoe UI", 9, "bold"),
                  justify="left").pack(anchor="w", padx=10, pady=4)

    def _build_tree(self):
        for w in self.tree_frame.winfo_children():
            w.destroy()
        kind = self.system_kind.get()
        if kind == "ventilation":
            cols = ("Имя", "Тип", "Рекуп.", "η зим", "η лет",
                    "tпод зим", "tпод лет", "Примечание")
        elif kind == "heating":
            cols = ("Имя", "Тип", "tпод", "tобр", "Топливо",
                    "КПД", "Примечание")
        else:
            cols = ("Имя", "Тип", "tпод", "tобр", "COP",
                    "Хладагент", "Примечание")

        self.tree = ttk.Treeview(self.tree_frame, columns=cols,
                                  show="headings", height=15)
        for c in cols:
            self.tree.heading(c, text=c)
            self.tree.column(c, anchor="w", width=110)
        self.tree.pack(fill="both", expand=True)
        self.tree.bind("<Double-1>", self._edit)

    def subscribe_events(self):
        self.project.subscribe("zones_changed", self.refresh)
        self.project.subscribe("project_loaded", self.refresh)

    def refresh(self, **kwargs):
        # Перестроить таблицу для нового типа
        self._build_tree()
        kind = self.system_kind.get()
        if kind == "ventilation":
            for name, ahu in sorted(self.project.ventilation_systems.items()):
                self.tree.insert("", "end", iid=name, values=(
                    ahu.name, ahu.system_type,
                    "да" if ahu.has_recovery else "—",
                    f"{ahu.recovery_efficiency_winter*100:.0f}%" if ahu.has_recovery else "—",
                    f"{ahu.recovery_efficiency_summer*100:.0f}%" if ahu.has_recovery else "—",
                    f"{ahu.t_supply_winter}°C",
                    f"{ahu.t_supply_summer}°C",
                    ahu.note,
                ))
        elif kind == "heating":
            for name, h in sorted(self.project.heating_systems.items()):
                self.tree.insert("", "end", iid=name, values=(
                    h.name, h.system_type, f"{h.t_supply}°C",
                    f"{h.t_return}°C", h.fuel,
                    f"{h.efficiency*100:.0f}%", h.note,
                ))
        else:
            for name, c in sorted(self.project.cooling_systems.items()):
                self.tree.insert("", "end", iid=name, values=(
                    c.name, c.system_type, f"{c.t_supply}°C",
                    f"{c.t_return}°C", c.cop,
                    c.refrigerant, c.note,
                ))

    def _edit(self, event):
        sel = self.tree.selection()
        if not sel:
            return
        name = sel[0]
        kind = self.system_kind.get()

        if kind == "ventilation":
            self._edit_ahu(name)
        elif kind == "heating":
            self._edit_heating(name)
        else:
            self._edit_cooling(name)

    def _edit_ahu(self, name):
        ahu = self.project.ventilation_systems.get(name)
        if not ahu:
            return

        win = tk.Toplevel(self)
        win.title(f"Приточная установка: {name}")
        win.geometry("450x540")

        # Тип
        ttk.Label(win, text="Тип установки:").pack(anchor="w", padx=10, pady=(10,0))
        type_var = tk.StringVar(value=ahu.system_type)
        ttk.Combobox(win, textvariable=type_var, state="readonly", width=25,
                     values=["supply", "exhaust", "supply_exhaust"]
                     ).pack(anchor="w", padx=10)

        # Рекуперация
        rec_var = tk.BooleanVar(value=ahu.has_recovery)
        ttk.Checkbutton(win, text="Есть рекуператор",
                        variable=rec_var).pack(anchor="w", padx=10, pady=10)

        # Числовые поля
        fields = [
            ("КПД рекуперации зимой (0..1)", "recovery_efficiency_winter"),
            ("КПД рекуперации летом (0..1)", "recovery_efficiency_summer"),
            ("Температура подачи зимой, °C", "t_supply_winter"),
            ("Температура подачи летом, °C", "t_supply_summer"),
            ("Влагосодержание подачи лет., г/кг", "w_supply_summer"),
        ]
        vars_ = {}
        for label, attr in fields:
            ttk.Label(win, text=label).pack(anchor="w", padx=10, pady=(8,0))
            v = tk.StringVar(value=str(getattr(ahu, attr)))
            ttk.Entry(win, textvariable=v, width=15).pack(anchor="w", padx=10)
            vars_[attr] = v

        # Примечание
        ttk.Label(win, text="Примечание:").pack(anchor="w", padx=10, pady=(8,0))
        note_var = tk.StringVar(value=ahu.note)
        ttk.Entry(win, textvariable=note_var, width=50).pack(anchor="w", padx=10)

        def save():
            try:
                ahu.system_type = type_var.get()
                ahu.has_recovery = rec_var.get()
                for attr, v in vars_.items():
                    setattr(ahu, attr, float(v.get().replace(",", ".")))
                ahu.note = note_var.get()
            except ValueError:
                messagebox.showerror("Ошибка", "Введите числовые значения.")
                return
            self.refresh()
            win.destroy()

        ttk.Button(win, text="Сохранить", command=save).pack(pady=12)

    def _edit_heating(self, name):
        h = self.project.heating_systems.get(name)
        if not h:
            return
        win = tk.Toplevel(self)
        win.title(f"Котёл: {name}")
        win.geometry("420x420")

        ttk.Label(win, text="Тип источника:").pack(anchor="w", padx=10, pady=(10,0))
        type_var = tk.StringVar(value=h.system_type)
        ttk.Combobox(win, textvariable=type_var, state="readonly", width=25,
                     values=["boiler_gas", "boiler_electric",
                             "heat_pump", "central"]).pack(anchor="w", padx=10)

        ttk.Label(win, text="Топливо:").pack(anchor="w", padx=10, pady=(8,0))
        fuel_var = tk.StringVar(value=h.fuel)
        ttk.Combobox(win, textvariable=fuel_var, state="readonly", width=25,
                     values=["gas", "electric", "diesel", "central"]
                     ).pack(anchor="w", padx=10)

        fields = [
            ("Температура подачи, °C", "t_supply"),
            ("Температура обратки, °C", "t_return"),
            ("КПД (0..1)", "efficiency"),
        ]
        vars_ = {}
        for label, attr in fields:
            ttk.Label(win, text=label).pack(anchor="w", padx=10, pady=(8,0))
            v = tk.StringVar(value=str(getattr(h, attr)))
            ttk.Entry(win, textvariable=v, width=15).pack(anchor="w", padx=10)
            vars_[attr] = v

        ttk.Label(win, text="Примечание:").pack(anchor="w", padx=10, pady=(8,0))
        note_var = tk.StringVar(value=h.note)
        ttk.Entry(win, textvariable=note_var, width=50).pack(anchor="w", padx=10)

        def save():
            try:
                h.system_type = type_var.get()
                h.fuel = fuel_var.get()
                for attr, v in vars_.items():
                    setattr(h, attr, float(v.get().replace(",", ".")))
                h.note = note_var.get()
            except ValueError:
                messagebox.showerror("Ошибка", "Введите числовые значения.")
                return
            self.refresh()
            win.destroy()

        ttk.Button(win, text="Сохранить", command=save).pack(pady=12)

    def _edit_cooling(self, name):
        c = self.project.cooling_systems.get(name)
        if not c:
            return
        win = tk.Toplevel(self)
        win.title(f"Чиллер: {name}")
        win.geometry("420x400")

        ttk.Label(win, text="Тип источника:").pack(anchor="w", padx=10, pady=(10,0))
        type_var = tk.StringVar(value=c.system_type)
        ttk.Combobox(win, textvariable=type_var, state="readonly", width=25,
                     values=["chiller_air", "chiller_water", "vrf", "split"]
                     ).pack(anchor="w", padx=10)

        ttk.Label(win, text="Хладагент:").pack(anchor="w", padx=10, pady=(8,0))
        ref_var = tk.StringVar(value=c.refrigerant)
        ttk.Combobox(win, textvariable=ref_var, width=25,
                     values=["R410A", "R32", "R134a", "R407C", "R22"]
                     ).pack(anchor="w", padx=10)

        fields = [
            ("Температура подачи, °C", "t_supply"),
            ("Температура обратки, °C", "t_return"),
            ("COP / EER", "cop"),
        ]
        vars_ = {}
        for label, attr in fields:
            ttk.Label(win, text=label).pack(anchor="w", padx=10, pady=(8,0))
            v = tk.StringVar(value=str(getattr(c, attr)))
            ttk.Entry(win, textvariable=v, width=15).pack(anchor="w", padx=10)
            vars_[attr] = v

        ttk.Label(win, text="Примечание:").pack(anchor="w", padx=10, pady=(8,0))
        note_var = tk.StringVar(value=c.note)
        ttk.Entry(win, textvariable=note_var, width=50).pack(anchor="w", padx=10)

        def save():
            try:
                c.system_type = type_var.get()
                c.refrigerant = ref_var.get()
                for attr, v in vars_.items():
                    setattr(c, attr, float(v.get().replace(",", ".")))
                c.note = note_var.get()
            except ValueError:
                messagebox.showerror("Ошибка", "Введите числовые значения.")
                return
            self.refresh()
            win.destroy()

        ttk.Button(win, text="Сохранить", command=save).pack(pady=12)

    def _calc_ahu(self):
        """Считает и показывает нагрузки от приточных установок."""
        if not self.project.ventilation_systems:
            messagebox.showinfo("Информация",
                                "Сначала назначьте зоны во вкладке «7. Зоны».")
            return
        loads = self.project.calculate_ahu_loads()

        total_h = total_cs = total_cl = 0
        text_lines = ["Нагрузки от приточных установок:"]
        for name, d in sorted(loads.items(), key=lambda x: -x[1]["q_heater_w"]):
            if d["supply_m3h"] < 1:
                continue
            text_lines.append(
                f"  {name}: Q_калор {d['q_heater_w']/1000:.1f} кВт, "
                f"Q_охл total {d['q_cooler_total_w']/1000:.1f} кВт "
                f"(sens {d['q_cooler_sens_w']/1000:.1f}, "
                f"lat {d['q_cooler_lat_w']/1000:+.1f})"
            )
            total_h += d["q_heater_w"]
            total_cs += d["q_cooler_sens_w"]
            total_cl += d["q_cooler_lat_w"]
        text_lines.append(
            f"Σ калориферы: {total_h/1000:.1f} кВт | "
            f"Σ охладители: {(total_cs+total_cl)/1000:.1f} кВт "
            f"(sens {total_cs/1000:.1f})"
        )
        self.ahu_label.set("\n".join(text_lines))


# ===========================================================================
#  Вкладка 9. Дымоудаление
# ===========================================================================


class SmokeRemovalTab(BaseTab):
    """Системы дымоудаления и подпора воздуха.
    Аварийные системы по КМК / СП 7.13130."""
    title = "11. Дымоудаление"

    def build(self):
        from hvac.catalogs.smoke_norms import list_smoke_norms, get_smoke_norm

        # ===== Панель выбора норматива =====
        fr_norm = ttk.LabelFrame(self, text="Действующий норматив")
        fr_norm.pack(fill="x", padx=10, pady=(8, 4))

        ttk.Label(fr_norm, text="Норматив противодымной защиты:",
                  font=("Segoe UI", 10, "bold")
                  ).grid(row=0, column=0, padx=6, pady=6, sticky="w")

        # Текущий смок-норм проекта
        current = getattr(self.project.params, "smoke_norm", "SP7_RU")
        self.norm_var = tk.StringVar(value=current)
        norm_titles = {n.code: n.title for n in list_smoke_norms()}
        self.norm_combo = ttk.Combobox(
            fr_norm, textvariable=self.norm_var, state="readonly", width=32,
            values=[norm_titles[c] for c in norm_titles])
        # Установить текущий заголовок
        self.norm_combo.set(norm_titles.get(current, current))
        self.norm_combo.grid(row=0, column=1, padx=6, pady=6, sticky="w")

        # Карта title → code для обратного парсинга
        self._norm_title_to_code = {v: k for k, v in norm_titles.items()}

        # Подсказка по нормативу
        self.norm_hint = tk.StringVar(value="")
        ttk.Label(fr_norm, textvariable=self.norm_hint,
                  foreground="#555", wraplength=600, justify="left"
                  ).grid(row=1, column=0, columnspan=3, padx=6, pady=(0, 6),
                         sticky="w")

        def _on_norm_change(*_):
            title = self.norm_combo.get()
            code = self._norm_title_to_code.get(title, "SP7_RU")
            self.project.params.smoke_norm = code
            norm = get_smoke_norm(code)
            self.norm_hint.set(
                f"📖 {norm.reference}\n{norm.note}"
            )
            self.project.emit("smoke_systems_changed")

        self.norm_combo.bind("<<ComboboxSelected>>", _on_norm_change)
        _on_norm_change()  # инициализация подсказки

        # ===== Верхняя панель: авто + ручное создание + назначения =====
        fr_top = ttk.LabelFrame(
            self, text="Гибридный режим: авто-присвоение, ручное создание, "
                       "точечные назначения")
        fr_top.pack(fill="x", padx=10, pady=6)

        # Строка 1: операции с системами
        ttk.Button(fr_top, text="▶ Авто-присвоение систем",
                   command=self._auto_assign
                   ).grid(row=0, column=0, padx=4, pady=4, sticky="w")
        ttk.Button(fr_top, text="+ Создать систему вручную…",
                   command=self._create_system_dialog
                   ).grid(row=0, column=1, padx=4, pady=4, sticky="w")
        ttk.Button(fr_top, text="🚪 Помещения и назначения…",
                   command=self._open_assignment_dialog
                   ).grid(row=0, column=2, padx=4, pady=4, sticky="w")

        # Строка 2: сценарий пожара
        ttk.Label(fr_top, text="Сценарий пожара:"
                  ).grid(row=1, column=0, padx=4, pady=4, sticky="w")
        self.fire_mode = tk.StringVar(value="single_zone")
        ttk.Radiobutton(fr_top, text="Один пожар в одной зоне (стандарт)",
                        variable=self.fire_mode, value="single_zone",
                        command=self.refresh
                        ).grid(row=1, column=1, padx=4, sticky="w")
        ttk.Radiobutton(fr_top, text="Несколько зон одновременно (запас)",
                        variable=self.fire_mode, value="multiple_zones",
                        command=self.refresh
                        ).grid(row=1, column=2, padx=4, sticky="w")
        ttk.Button(fr_top, text="↻ Пересчитать",
                   command=self.refresh).grid(row=1, column=3, padx=8)

        # Фильтр: СДУ или СПВ
        fr_filter = ttk.Frame(self)
        fr_filter.pack(fill="x", padx=10, pady=4)
        ttk.Label(fr_filter, text="Показать:",
                  font=("Segoe UI", 10, "bold")).pack(side="left", padx=4)
        self.kind_var = tk.StringVar(value="smoke_removal")
        for label, val in [("СДУ — дымоудаление", "smoke_removal"),
                           ("СПВ — подпор воздуха", "air_supply")]:
            ttk.Radiobutton(fr_filter, text=label, variable=self.kind_var,
                            value=val, command=self.refresh
                            ).pack(side="left", padx=6)

        # Таблица
        self.tree_frame = ttk.Frame(self)
        self.tree_frame.pack(fill="both", expand=True, padx=10, pady=6)
        self.tree = None
        self._build_tree()

        ttk.Label(self,
                  text="Двойной клик — редактировать систему. "
                       "Параметры (норматив, площадь зоны, давление) "
                       "можно менять под конкретный проект.",
                  foreground="#666").pack(anchor="w", padx=10, pady=4)

        # Сводка
        self.summary_label = tk.StringVar(value="")
        ttk.Label(self, textvariable=self.summary_label,
                  foreground="#1F4E78",
                  font=("Segoe UI", 10, "bold"), justify="left"
                  ).pack(anchor="w", padx=10, pady=8)

    def _build_tree(self):
        for w in self.tree_frame.winfo_children():
            w.destroy()
        kind = self.kind_var.get()
        if kind == "smoke_removal":
            cols = ("Имя", "Назначение", "Площадь м²", "Зон",
                    "Норма", "L зоны м³/ч", "L сист. м³/ч",
                    "L компенс. м³/ч", "Огнестойк.")
        else:
            cols = ("Имя", "Назначение", "Помещение",
                    "L подпора м³/ч", "Давление Па", "Примечание")
        self.tree = ttk.Treeview(self.tree_frame, columns=cols,
                                  show="headings", height=20)
        for c in cols:
            self.tree.heading(c, text=c)
            anchor = "e" if "м³" in c or "Па" in c or "м²" in c or c == "Зон" else "w"
            self.tree.column(c, anchor=anchor, width=110)
        self.tree.pack(fill="both", expand=True)
        self.tree.bind("<Double-1>", self._edit)

    def subscribe_events(self):
        self.project.subscribe("smoke_systems_changed", self.refresh)
        self.project.subscribe("smoke_loads_calculated", self.refresh)
        self.project.subscribe("project_loaded", self.refresh)

    def _auto_assign(self):
        if not self.project.spaces:
            messagebox.showwarning("Нет данных", "Сначала загрузите CSV.")
            return
        info = self.project.auto_assign_smoke_systems()
        messagebox.showinfo(
            "Готово",
            f"Создано:\n"
            f"  СДУ (дымоудаление):   {info['n_smoke_systems']}\n"
            f"  СПВ (подпор воздуха): {info['n_pressurization']}\n"
            f"Назначено помещений: {info['n_spaces_assigned']}")
        self.refresh()

    def refresh(self, **kwargs):
        self._build_tree()
        loads = self.project.calculate_smoke_loads(fire_mode=self.fire_mode.get())
        kind = self.kind_var.get()

        total_smoke = total_makeup = total_pres = 0
        n_smoke = n_pres = 0

        for name, d in sorted(loads.items()):
            if kind == "smoke_removal" and d["system_type"] == "smoke_removal":
                self.tree.insert("", "end", iid=name, values=(
                    name, d["purpose"],
                    f"{d['served_area_m2']:.0f}",
                    d["n_zones"],
                    f"{d.get('norm_per_m2', '—')} м³/ч·м²",
                    f"{d['L_per_zone_m3h']:,.0f}".replace(",", " "),
                    f"{d['L_smoke_m3h']:,.0f}".replace(",", " "),
                    f"{d['L_makeup_m3h']:,.0f}".replace(",", " "),
                    d["fire_rating"],
                ))
                total_smoke += d["L_smoke_m3h"]
                total_makeup += d["L_makeup_m3h"]
                n_smoke += 1
            elif kind == "air_supply" and d["system_type"] == "air_supply":
                # Найти помещение по имени системы
                sp_label = ""
                for sp in self.project.spaces:
                    if sp.pressurization_system == name:
                        sp_label = f"{sp.number} {sp.name}"
                        break
                self.tree.insert("", "end", iid=name, values=(
                    name, d["purpose"], sp_label,
                    f"{d['L_smoke_m3h']:,.0f}".replace(",", " "),
                    f"{d['pressure_pa']}",
                    d["note"],
                ))
                total_pres += d["L_smoke_m3h"]
                n_pres += 1

        mode_text = ("один пожар в одной зоне" if self.fire_mode.get() == "single_zone"
                     else "все зоны одновременно")
        self.summary_label.set(
            f"Режим расчёта: {mode_text}\n"
            f"СДУ: {n_smoke} систем, Σ дым = {total_smoke:,.0f} м³/ч, "
            f"Σ компенс. = {total_makeup:,.0f} м³/ч\n"
            f"СПВ: {n_pres} систем, Σ подпор = {total_pres:,.0f} м³/ч"
                .replace(",", " "))

    def _edit(self, event):
        sel = self.tree.selection()
        if not sel:
            return
        name = sel[0]
        sm = self.project.smoke_systems.get(name)
        if not sm:
            return

        win = tk.Toplevel(self)
        win.title(f"Система: {name}")
        win.geometry("520x820")

        ttk.Label(win, text=f"Система: {name}",
                  font=("Segoe UI", 11, "bold")).pack(pady=8)

        # Тип и назначение
        ttk.Label(win, text="Назначение:").pack(anchor="w", padx=10, pady=(8, 0))
        purpose_var = tk.StringVar(value=sm.purpose)
        ttk.Combobox(win, textvariable=purpose_var, state="readonly", width=25,
                     values=["parking", "warehouse", "corridor", "atrium",
                             "trading_hall", "stairs", "elevator",
                             "vestibule", "refuge"]).pack(anchor="w", padx=10)

        from hvac.catalogs.smoke_norms import get_smoke_norm
        active_norm = get_smoke_norm(
            getattr(self.project.params, "smoke_norm", "SP7_RU"))

        ttk.Label(win, text=f"Метод расчёта ({active_norm.title}):"
                  ).pack(anchor="w", padx=10, pady=(8, 0))
        method_var = tk.StringVar(value=sm.calc_method)
        all_methods = list(active_norm.available_calc_methods) + [
            "stairs_pressure", "elevator_pressure", "corridor_formula",
        ]
        seen = set()
        unique_methods = [m for m in all_methods
                           if not (m in seen or seen.add(m))]
        # Если у системы метод не из списка — добавим его, чтобы не
        # потерять при редактировании
        if sm.calc_method not in unique_methods:
            unique_methods.append(sm.calc_method)
        ttk.Combobox(win, textvariable=method_var, state="readonly", width=25,
                     values=unique_methods).pack(anchor="w", padx=10)

        # Числовые параметры — базовые + плюм-формулы
        fields = [
            ("Норматив, м³/ч·м²", "norm_per_m2"),
            ("Макс. площадь зоны, м²", "max_zone_area_m2"),
            ("Давление подпора, Па", "pressure_pa"),
            ("Температура дыма, °C", "t_smoke_C"),
            ("Доля компенс. (0..1)", "makeup_ratio"),
            ("L (ручной ввод), м³/ч", "L_smoke_m3h"),
            # Плюм-параметры КМК / NFPA:
            ("P — периметр очага, м (КМК)", "fire_perimeter_m"),
            ("y — высота свободной зоны, м (КМК)", "layer_height_m"),
            ("Ks — спринклеры (1.0/1.2)", "ks_sprinkler"),
            ("n — параметр коридора (КМК)", "n_corridor"),
            ("Kd — коэф. дверей (КМК)", "kd_door"),
            ("Q — мощность пожара, кВт (NFPA)", "hrr_kw"),
            ("α — доля конвективной (NFPA)", "convective_fraction"),
            ("z — высота над очагом, м (NFPA)", "plume_height_m"),
        ]
        vars_ = {}
        for label, attr in fields:
            ttk.Label(win, text=label).pack(anchor="w", padx=10, pady=(4, 0))
            v = tk.StringVar(value=str(getattr(sm, attr, 0)))
            ttk.Entry(win, textvariable=v, width=15).pack(anchor="w", padx=10)
            vars_[attr] = v

        ttk.Label(win, text="Огнестойкость:").pack(anchor="w", padx=10, pady=(8, 0))
        fire_var = tk.StringVar(value=sm.fire_rating)
        ttk.Combobox(win, textvariable=fire_var, width=15,
                     values=["F300-60", "F400-90", "F400-120",
                             "F600-90", "F600-120"]).pack(anchor="w", padx=10)

        ttk.Label(win, text="Примечание:").pack(anchor="w", padx=10, pady=(8, 0))
        note_var = tk.StringVar(value=sm.note)
        ttk.Entry(win, textvariable=note_var, width=50).pack(anchor="w", padx=10)

        def save():
            try:
                sm.purpose = purpose_var.get()
                sm.calc_method = method_var.get()
                for attr, v in vars_.items():
                    setattr(sm, attr, float(v.get().replace(",", ".")))
                sm.fire_rating = fire_var.get()
                sm.note = note_var.get()
            except ValueError:
                messagebox.showerror("Ошибка", "Введите числовые значения.")
                return
            self.refresh()
            win.destroy()

        def delete():
            # Сводка: сколько помещений отвяжется
            n_attached = sum(1 for sp in self.project.spaces
                             if sp.smoke_system == name
                             or sp.pressurization_system == name)
            extra = (f"\n\nС системы будут отвязаны {n_attached} помещений."
                     if n_attached else "")
            if not messagebox.askyesno(
                    "Удалить систему?",
                    f"Удалить систему «{name}»?{extra}",
                    parent=win):
                return
            self.project.delete_smoke_system(name)
            self.refresh()
            win.destroy()

        btn_fr = ttk.Frame(win)
        btn_fr.pack(pady=12, fill="x")
        ttk.Button(btn_fr, text="🗑 Удалить систему",
                   command=delete).pack(side="left", padx=8)
        ttk.Button(btn_fr, text="Отмена",
                   command=win.destroy).pack(side="right", padx=8)
        ttk.Button(btn_fr, text="💾 Сохранить",
                   command=save).pack(side="right", padx=4)

    # -------------------------------------------------------------------
    #  Диалог создания системы вручную
    # -------------------------------------------------------------------
    def _create_system_dialog(self):
        """Открыть форму для ручного создания СДУ или СПВ."""
        from hvac.smoke import (DEFAULT_SMOKE_NORMS,
                                 DEFAULT_PRESSURIZATION_RATES)

        win = tk.Toplevel(self)
        win.title("Новая система дымоудаления / подпора")
        win.geometry("520x780")
        win.transient(self.winfo_toplevel())

        ttk.Label(win, text="Создание системы вручную",
                  font=("Segoe UI", 11, "bold")
                  ).pack(anchor="w", padx=10, pady=8)

        # Имя
        ttk.Label(win, text="Имя системы (уникальное):"
                  ).pack(anchor="w", padx=10, pady=(8, 0))
        name_var = tk.StringVar(value="СДУ-01")
        ttk.Entry(win, textvariable=name_var, width=30
                  ).pack(anchor="w", padx=10)

        # Тип
        ttk.Label(win, text="Тип системы:"
                  ).pack(anchor="w", padx=10, pady=(8, 0))
        type_var = tk.StringVar(value="smoke_removal")
        type_combo = ttk.Combobox(
            win, textvariable=type_var, state="readonly", width=27,
            values=["smoke_removal", "air_supply", "compensation"])
        type_combo.pack(anchor="w", padx=10)

        # Назначение
        ttk.Label(win, text="Назначение:"
                  ).pack(anchor="w", padx=10, pady=(8, 0))
        purpose_var = tk.StringVar(value="parking")
        ttk.Combobox(win, textvariable=purpose_var, state="readonly", width=27,
                     values=["parking", "warehouse", "corridor", "atrium",
                             "trading_hall", "stairs", "elevator",
                             "vestibule", "refuge"]
                     ).pack(anchor="w", padx=10)

        # Активный норматив проекта
        from hvac.catalogs.smoke_norms import get_smoke_norm
        active_norm = get_smoke_norm(
            getattr(self.project.params, "smoke_norm", "SP7_RU"))

        # Метод расчёта — список ограничен активным нормативом
        ttk.Label(win, text=f"Метод расчёта (из {active_norm.title}):"
                  ).pack(anchor="w", padx=10, pady=(8, 0))
        method_var = tk.StringVar(value=active_norm.calc_method_recommended)
        # Все возможные методы (плюс пара для СПВ)
        all_methods = list(active_norm.available_calc_methods) + [
            "stairs_pressure", "elevator_pressure", "corridor_formula",
        ]
        # Дедуп
        seen = set()
        unique_methods = [m for m in all_methods
                           if not (m in seen or seen.add(m))]
        method_combo = ttk.Combobox(
            win, textvariable=method_var, state="readonly", width=27,
            values=unique_methods)
        method_combo.pack(anchor="w", padx=10)

        # Числовые параметры — базовые
        base_fields = [
            ("Норматив, м³/ч·м²", "norm_per_m2",
                str(active_norm.norms_per_m2.get("parking_closed", 24.0))),
            ("Макс. площадь зоны, м²", "max_zone_area_m2",
                str(active_norm.max_zone_area_m2)),
            ("Давление подпора, Па", "pressure_pa",
                str(active_norm.default_pressure_pa)),
            ("Температура дыма, °C", "t_smoke_C",
                str(active_norm.default_t_smoke_C)),
            ("Доля компенс. (0..1)", "makeup_ratio",
                str(active_norm.default_makeup_ratio)),
            ("L (ручной ввод), м³/ч", "L_smoke_m3h", "0"),
        ]
        # Плюм-формулы (КМК / NFPA): дополнительные параметры
        plume_fields = [
            ("P — периметр очага, м (КМК ф.3, max 12)", "fire_perimeter_m", "12"),
            ("y — высота свободной зоны, м (КМК, min 2.5)", "layer_height_m", "2.5"),
            ("Ks — коэф. спринклеров (1.0 / 1.2)", "ks_sprinkler", "1.0"),
            ("n — параметр коридора (КМК ф.1: 0.6…2.4)", "n_corridor", "1.5"),
            ("Kd — коэф. дверей (КМК ф.2)", "kd_door", "1.0"),
            ("Q — мощность пожара, кВт (NFPA)", "hrr_kw", "5000"),
            ("α — доля конвективной (NFPA, 0.7)", "convective_fraction", "0.7"),
            ("z — высота над очагом до слоя дыма, м (NFPA)", "plume_height_m", "6"),
        ]
        all_fields = base_fields + plume_fields

        vars_ = {}
        labels = {}
        entries = {}
        for label, attr, default in all_fields:
            lbl = ttk.Label(win, text=label)
            lbl.pack(anchor="w", padx=10, pady=(4, 0))
            v = tk.StringVar(value=default)
            ent = ttk.Entry(win, textvariable=v, width=15)
            ent.pack(anchor="w", padx=10)
            vars_[attr] = v
            labels[attr] = lbl
            entries[attr] = ent

        ttk.Label(win, text="Огнестойкость:"
                  ).pack(anchor="w", padx=10, pady=(6, 0))
        fire_var = tk.StringVar(value=active_norm.default_fire_rating)
        ttk.Combobox(win, textvariable=fire_var, width=15,
                     values=["F300-60", "F400-90", "F400-120",
                             "F600-90", "F600-120"]
                     ).pack(anchor="w", padx=10)

        ttk.Label(win, text="Примечание:"
                  ).pack(anchor="w", padx=10, pady=(6, 0))
        note_var = tk.StringVar(value="Создано вручную")
        ttk.Entry(win, textvariable=note_var, width=40
                  ).pack(anchor="w", padx=10)

        # Какие поля нужны для каждого метода
        METHOD_FIELDS = {
            "norm_per_m2":        {"norm_per_m2", "max_zone_area_m2"},
            "kmk_zone_perimeter": {"fire_perimeter_m", "layer_height_m",
                                    "ks_sprinkler", "max_zone_area_m2"},
            "kmk_corridor":       {"n_corridor", "kd_door"},
            "nfpa_plume_axi":     {"hrr_kw", "convective_fraction",
                                    "plume_height_m"},
            "manual":             {"L_smoke_m3h", "max_zone_area_m2"},
            "corridor_formula":   {"norm_per_m2"},
            "stairs_pressure":    {"L_smoke_m3h", "pressure_pa"},
            "elevator_pressure":  {"L_smoke_m3h", "pressure_pa"},
        }
        # Поля, которые показываем всегда
        ALWAYS_SHOW = {"t_smoke_C", "makeup_ratio"}

        def _refresh_fields(*_):
            """Показывает/скрывает поля в зависимости от calc_method."""
            method = method_var.get()
            needed = METHOD_FIELDS.get(method, set()) | ALWAYS_SHOW
            for attr in vars_:
                if attr in needed:
                    labels[attr].pack(anchor="w", padx=10, pady=(4, 0))
                    entries[attr].pack(anchor="w", padx=10)
                else:
                    labels[attr].pack_forget()
                    entries[attr].pack_forget()

        # Автоподгрузка дефолтов при смене типа/назначения
        def _on_type_change(*_):
            t = type_var.get()
            p = purpose_var.get()
            if t == "air_supply":
                rate = active_norm.pressurization_rates_m3h.get(p, 5000.0)
                vars_["L_smoke_m3h"].set(str(rate))
                vars_["norm_per_m2"].set("0")
                method_var.set(f"{p}_pressure" if p in ("stairs", "elevator")
                               else "manual")
            else:
                # СДУ — подставить норматив для назначения
                norm_map = {
                    "parking": "parking_closed",
                    "warehouse": "warehouse_low",
                    "corridor": "corridor",
                    "atrium": "office_assembly",
                    "trading_hall": "trading_hall",
                }
                key = norm_map.get(p, "")
                norm_value = active_norm.norms_per_m2.get(key, 24.0)
                vars_["norm_per_m2"].set(str(norm_value))
                vars_["L_smoke_m3h"].set("0")
                # Не переключаем calc_method, если пользователь уже выбрал
                # плюм-метод явно
                if method_var.get() not in (
                        "kmk_zone_perimeter", "kmk_corridor", "nfpa_plume_axi"):
                    method_var.set("norm_per_m2")
            _refresh_fields()

        type_var.trace_add("write", _on_type_change)
        purpose_var.trace_add("write", _on_type_change)
        method_var.trace_add("write", _refresh_fields)
        _refresh_fields()  # инициализация

        # Кнопки
        def create():
            try:
                params = {a: float(v.get().replace(",", "."))
                          for a, v in vars_.items()}
            except ValueError:
                messagebox.showerror("Ошибка",
                                     "Числовые поля должны быть числами.",
                                     parent=win)
                return
            try:
                self.project.create_smoke_system_manual(
                    name=name_var.get(),
                    system_type=type_var.get(),
                    purpose=purpose_var.get(),
                    calc_method=method_var.get(),
                    fire_rating=fire_var.get(),
                    note=note_var.get(),
                    **params,
                )
            except ValueError as e:
                messagebox.showerror("Ошибка", str(e), parent=win)
                return
            win.destroy()
            self.refresh()
            messagebox.showinfo(
                "Готово",
                f"Создана система «{name_var.get()}».\n"
                f"Чтобы привязать к ней помещения, нажмите "
                f"«🚪 Помещения и назначения…».")

        btn_fr = ttk.Frame(win)
        btn_fr.pack(fill="x", padx=10, pady=12)
        ttk.Button(btn_fr, text="Отмена",
                   command=win.destroy).pack(side="right", padx=4)
        ttk.Button(btn_fr, text="Создать",
                   command=create).pack(side="right", padx=4)

    # -------------------------------------------------------------------
    #  Диалог: помещения и их назначения системам СДУ/СПВ
    # -------------------------------------------------------------------
    def _open_assignment_dialog(self):
        """Открывает окно с таблицей помещений: выделить группу и
        точечно назначить им СДУ или СПВ, либо снять, либо проставить
        номер дымовой зоны."""
        if not self.project.spaces:
            messagebox.showwarning("Нет данных", "Сначала загрузите CSV.")
            return

        win = tk.Toplevel(self)
        win.title("Помещения и назначения СДУ / СПВ")
        win.geometry("1100x680")
        win.transient(self.winfo_toplevel())

        # Подсказка
        ttk.Label(
            win, foreground="#444", font=("Segoe UI", 9),
            text="Выделите помещения (Ctrl/Shift+клик), затем выберите "
                 "систему и нажмите «Назначить». Кнопки ниже работают "
                 "над выделенными помещениями."
            ).pack(anchor="w", padx=10, pady=(8, 4))

        # Фильтры
        fr_filter = ttk.Frame(win)
        fr_filter.pack(fill="x", padx=10, pady=4)
        ttk.Label(fr_filter, text="🔍 Поиск:").pack(side="left", padx=4)
        search_var = tk.StringVar()
        ttk.Entry(fr_filter, textvariable=search_var, width=22
                  ).pack(side="left", padx=4)

        ttk.Label(fr_filter, text="Уровень:").pack(side="left", padx=8)
        level_var = tk.StringVar(value="(все)")
        levels = ["(все)"] + sorted({sp.level for sp in self.project.spaces})
        ttk.Combobox(fr_filter, textvariable=level_var, values=levels,
                     state="readonly", width=14
                     ).pack(side="left", padx=2)

        ttk.Label(fr_filter, text="Тип:").pack(side="left", padx=8)
        type_var = tk.StringVar(value="(все)")
        types = ["(все)"] + sorted({sp.room_type
                                     for sp in self.project.spaces})
        ttk.Combobox(fr_filter, textvariable=type_var, values=types,
                     state="readonly", width=18
                     ).pack(side="left", padx=2)

        ttk.Label(fr_filter, text="Статус:").pack(side="left", padx=8)
        status_var = tk.StringVar(value="(все)")
        ttk.Combobox(fr_filter, textvariable=status_var,
                     values=["(все)", "без СДУ",
                             "с СДУ", "без СПВ", "с СПВ"],
                     state="readonly", width=12
                     ).pack(side="left", padx=2)

        info_var = tk.StringVar(value="")
        ttk.Label(fr_filter, textvariable=info_var,
                  foreground="#1F4E78").pack(side="left", padx=12)

        # Таблица
        cols = ("№", "Имя", "Уровень", "Тип", "S, м²",
                "СДУ", "СПВ", "Зона")
        widths = {"№": 80, "Имя": 200, "Уровень": 110, "Тип": 140,
                  "S, м²": 70, "СДУ": 130, "СПВ": 130, "Зона": 50}
        tree_fr = ttk.Frame(win)
        tree_fr.pack(fill="both", expand=True, padx=10, pady=4)
        tree = ttk.Treeview(tree_fr, columns=cols, show="headings",
                             height=18, selectmode="extended")
        for c in cols:
            tree.heading(c, text=c)
            tree.column(c, width=widths[c],
                        anchor=("e" if c in ("S, м²", "Зона") else "w"))
        vsb = ttk.Scrollbar(tree_fr, orient="vertical", command=tree.yview)
        tree.configure(yscrollcommand=vsb.set)
        tree.pack(side="left", fill="both", expand=True)
        vsb.pack(side="right", fill="y")

        tree.tag_configure("has_smoke", background="#FFF4E0")
        tree.tag_configure("has_pres", background="#E0F4FF")
        tree.tag_configure("has_both", background="#FFE0F0")

        def _filter_match(sp) -> bool:
            q = search_var.get().strip().lower()
            if q:
                hay = f"{sp.number} {sp.name} {sp.level} {sp.room_type}".lower()
                if q not in hay:
                    return False
            if level_var.get() != "(все)" and sp.level != level_var.get():
                return False
            if type_var.get() != "(все)" and sp.room_type != type_var.get():
                return False
            st = status_var.get()
            if st == "без СДУ" and sp.smoke_system:
                return False
            if st == "с СДУ" and not sp.smoke_system:
                return False
            if st == "без СПВ" and sp.pressurization_system:
                return False
            if st == "с СПВ" and not sp.pressurization_system:
                return False
            return True

        def _refresh_tree():
            for i in tree.get_children():
                tree.delete(i)
            shown = 0
            for sp in self.project.spaces:
                if not _filter_match(sp):
                    continue
                tags = ()
                if sp.smoke_system and sp.pressurization_system:
                    tags = ("has_both",)
                elif sp.smoke_system:
                    tags = ("has_smoke",)
                elif sp.pressurization_system:
                    tags = ("has_pres",)
                tree.insert("", "end", iid=sp.space_id, tags=tags, values=(
                    sp.number, sp.name, sp.level, sp.room_type,
                    f"{sp.area_m2:.1f}",
                    sp.smoke_system or "—",
                    sp.pressurization_system or "—",
                    sp.smoke_zone_index if sp.smoke_zone_index else "",
                ))
                shown += 1
            info_var.set(
                f"Показано: {shown} / {len(self.project.spaces)}")

        search_var.trace_add("write", lambda *_: _refresh_tree())
        level_var.trace_add("write", lambda *_: _refresh_tree())
        type_var.trace_add("write", lambda *_: _refresh_tree())
        status_var.trace_add("write", lambda *_: _refresh_tree())
        _refresh_tree()

        # Панель действий
        fr_act = ttk.LabelFrame(win, text="Действия с выделенными помещениями")
        fr_act.pack(fill="x", padx=10, pady=6)

        ttk.Label(fr_act, text="Система:").grid(row=0, column=0, padx=4, pady=4)
        sys_var = tk.StringVar()
        sys_combo = ttk.Combobox(fr_act, textvariable=sys_var,
                                  state="readonly", width=28)
        sys_combo.grid(row=0, column=1, padx=4, sticky="w")

        def _refresh_systems_list():
            names = sorted(self.project.smoke_systems.keys())
            sys_combo["values"] = names
            if names and not sys_var.get():
                sys_var.set(names[0])
        _refresh_systems_list()

        def _selected_ids():
            return list(tree.selection())

        def _assign():
            ids = _selected_ids()
            if not ids:
                messagebox.showinfo(
                    "Не выделено",
                    "Выделите помещения в таблице.", parent=win)
                return
            name = sys_var.get()
            if not name:
                messagebox.showinfo(
                    "Не выбрана система",
                    "Выберите систему из списка или создайте новую.",
                    parent=win)
                return
            try:
                n = self.project.assign_spaces_to_smoke_system(ids, name)
            except ValueError as e:
                messagebox.showerror("Ошибка", str(e), parent=win)
                return
            _refresh_tree()
            self.refresh()
            messagebox.showinfo(
                "Готово",
                f"Назначено системе «{name}»: {n} помещений.")

        def _clear_smoke():
            ids = _selected_ids()
            if not ids:
                return
            n = self.project.clear_smoke_assignment(ids, kind="smoke")
            _refresh_tree()
            self.refresh()
            messagebox.showinfo(
                "Готово", f"СДУ снято с {n} помещений.")

        def _clear_pres():
            ids = _selected_ids()
            if not ids:
                return
            n = self.project.clear_smoke_assignment(
                ids, kind="pressurization")
            _refresh_tree()
            self.refresh()
            messagebox.showinfo(
                "Готово", f"СПВ снято с {n} помещений.")

        def _set_zone():
            ids = _selected_ids()
            if not ids:
                messagebox.showinfo("Не выделено",
                                     "Выделите помещения.", parent=win)
                return
            from tkinter.simpledialog import askinteger
            idx = askinteger(
                "Номер дымовой зоны",
                "Номер дымовой зоны (1, 2, 3…) для выделенных помещений.\n"
                "0 — сбросить (одна зона на всю систему):",
                parent=win, minvalue=0, maxvalue=99, initialvalue=1)
            if idx is None:
                return
            try:
                n = self.project.set_smoke_zone_index(ids, idx)
            except ValueError as e:
                messagebox.showerror("Ошибка", str(e), parent=win)
                return
            _refresh_tree()
            messagebox.showinfo(
                "Готово",
                f"Дымовая зона {idx} установлена для {n} помещений.")

        ttk.Button(fr_act, text="✓ Назначить выделенным",
                   command=_assign
                   ).grid(row=0, column=2, padx=8, pady=4)
        ttk.Button(fr_act, text="✕ Снять СДУ",
                   command=_clear_smoke
                   ).grid(row=0, column=3, padx=4, pady=4)
        ttk.Button(fr_act, text="✕ Снять СПВ",
                   command=_clear_pres
                   ).grid(row=0, column=4, padx=4, pady=4)
        ttk.Button(fr_act, text="# Дымовая зона…",
                   command=_set_zone
                   ).grid(row=0, column=5, padx=4, pady=4)

        # Подсказка по цветам
        legend = ttk.Frame(win)
        legend.pack(fill="x", padx=10, pady=(0, 4))
        for color, label in [("#FFF4E0", "СДУ"),
                              ("#E0F4FF", "СПВ"),
                              ("#FFE0F0", "обе")]:
            sw = tk.Label(legend, text="  ", background=color, relief="solid",
                          borderwidth=1)
            sw.pack(side="left", padx=(8, 2))
            ttk.Label(legend, text=label,
                      foreground="#555").pack(side="left")

        # Закрыть
        ttk.Button(win, text="Закрыть",
                   command=win.destroy).pack(pady=8, side="right", padx=10)


# ===========================================================================
#  Вкладка 10. Графики
# ===========================================================================


class ChartsTab(BaseTab):
    title = "12. Графики"

    def build(self):
        if not _MPL_AVAILABLE:
            ttk.Label(self, text="Графики недоступны: не установлен matplotlib.\n\n"
                      "Установите командой:\n   pip install matplotlib",
                      foreground="#A00000", justify="left",
                      font=("Segoe UI", 11)).pack(padx=20, pady=20)
            return

        self.chart_var = tk.StringVar(value=list_charts()[0] if list_charts() else "")
        fr = ttk.Frame(self)
        fr.pack(fill="x", padx=10, pady=6)
        ttk.Label(fr, text="Диаграмма:").pack(side="left", padx=4)
        ttk.Combobox(fr, textvariable=self.chart_var, values=list_charts(),
                     state="readonly", width=42).pack(side="left", padx=4)
        ttk.Button(fr, text="Построить",
                   command=self._draw).pack(side="left", padx=8)
        ttk.Label(fr, text="(сначала выполните расчёт на вкладке 5)",
                  foreground="#777").pack(side="left", padx=8)

        self.canvas_frame = ttk.Frame(self)
        self.canvas_frame.pack(fill="both", expand=True, padx=10, pady=6)
        self._canvas = None
        self._toolbar = None

    def _draw(self):
        if not self.project.spaces or self.project.spaces[0].heat_loss_w == 0:
            messagebox.showwarning("Нет данных", "Сначала выполните расчёт.")
            return
        if self._toolbar:
            self._toolbar.destroy()
        if self._canvas:
            self._canvas.get_tk_widget().destroy()

        fig = Figure(figsize=(11, 5.5), dpi=100)
        try:
            draw_chart(self.chart_var.get(), self.project, fig)
        except Exception as e:
            messagebox.showerror("Ошибка графика", f"{e}\n{traceback.format_exc()}")
            return

        self._canvas = FigureCanvasTkAgg(fig, master=self.canvas_frame)
        self._canvas.draw()
        self._canvas.get_tk_widget().pack(fill="both", expand=True)
        self._toolbar = NavigationToolbar2Tk(self._canvas, self.canvas_frame)
        self._toolbar.update()


# ===========================================================================
#  Реестр вкладок
# ===========================================================================


def _load_circuits_tabs():
    """Ленивая загрузка вкладок контуров (избегаем циклического импорта,
    т.к. circuits_tab импортирует BaseTab из этого модуля)."""
    try:
        from hvac.ui.circuits_tab import CircuitsTab, PipeSectionsTab
        return [CircuitsTab, PipeSectionsTab]
    except Exception:
        import traceback
        traceback.print_exc()
        return []


TABS_REGISTRY = ([DataTab, ParamsTab, ConstructionsTab,
                  SpacesTab, CalculateTab, VentilationTab,
                  ZonesTab, EquipmentTab]
                 + _load_circuits_tabs()
                 + [SmokeRemovalTab, ChartsTab])
