# -*- coding: utf-8 -*-
"""Вкладка «Оборудование помещений».

Позволяет для каждого помещения назначить:
- Отопительный прибор (радиатор / фанкойл / тёплый пол) с моделью и мощностью.
- Охладительный прибор (фанкойл / VRF / сплит) с моделью и мощностью.
- Воздухораспределители: приточные и вытяжные.

Колонки таблицы:
№ | Имя | Q_от расч. | Что стоит | Кол-во | Покрытие % | Q_охл расч. |
   Что стоит | Кол-во | Покрытие % | Приток | Вытяжка

Двойной клик по строке → диалог редактирования.

Кнопка "Экспорт сводной таблицы в Excel" → отдельный файл со всеми
устройствами в виде ведомости.
"""

from __future__ import annotations
import tkinter as tk
from tkinter import ttk, messagebox, filedialog

from hvac.project import HVACProject
from hvac.room_equipment import (
    RoomEquipment,
    HEATING_TERMINAL_TYPES, COOLING_TERMINAL_TYPES,
    SUPPLY_TERMINAL_TYPES, EXHAUST_TERMINAL_TYPES,
    TYPICAL_RADIATOR_POWER_W, TYPICAL_FANCOIL_COOLING_W,
    TYPICAL_DIFFUSER_FLOW_M3H,
)


class RoomEquipmentTab(ttk.Frame):
    """Вкладка назначения оборудования в помещениях."""

    title = "9. Оборудование помещ."

    def __init__(self, parent, project: HVACProject, app):
        super().__init__(parent)
        self.project = project
        self.app = app
        self.build()
        self.subscribe_events()

    def build(self):
        # Верхняя панель
        top = ttk.Frame(self)
        top.pack(fill="x", padx=10, pady=6)

        ttk.Label(top, text="Назначение оборудования в помещениях",
                  font=("Segoe UI", 10, "bold")).pack(side="left")

        ttk.Button(top, text="🔄 Обновить",
                   command=self.refresh).pack(side="right", padx=4)
        ttk.Button(top, text="📊 Экспорт сводной таблицы в Excel…",
                   command=self.export_summary).pack(side="right", padx=4)
        ttk.Button(top, text="🧹 Очистить всё оборудование",
                   command=self.clear_all).pack(side="right", padx=4)

        # Фильтр
        fr = ttk.Frame(self)
        fr.pack(fill="x", padx=10, pady=2)
        ttk.Label(fr, text="Поиск:").pack(side="left", padx=4)
        self.search_var = tk.StringVar()
        ttk.Entry(fr, textvariable=self.search_var, width=20).pack(side="left", padx=4)
        self.search_var.trace_add("write", lambda *_: self.refresh())

        self.info_label = ttk.Label(fr, text="", foreground="#555")
        self.info_label.pack(side="left", padx=20)

        # Дерево
        cols = ("№", "Имя", "S м²",
                "Q_от Вт", "Отопит. прибор", "Кол", "Пок.%",
                "Q_охл Вт", "Охлад. прибор", "Кол", "Пок.%",
                "Приток", "Вытяж.")
        widths = {
            "№": 70, "Имя": 130, "S м²": 50,
            "Q_от Вт": 70, "Отопит. прибор": 150, "Кол": 35, "Пок.%": 55,
            "Q_охл Вт": 70, "Охлад. прибор": 150, "Кол": 35, "Пок.%": 55,
            "Приток": 90, "Вытяж.": 90
        }
        self.tree = ttk.Treeview(self, columns=cols, show="headings",
                                 height=22, selectmode="browse")
        for c in cols:
            self.tree.heading(c, text=c)
            self.tree.column(c, anchor="w", width=widths.get(c, 80))
        self.tree.pack(fill="both", expand=True, padx=10, pady=6)
        self.tree.bind("<Double-1>", self._edit)

        # Цветовая разметка по покрытию
        self.tree.tag_configure("under", background="#FCE5E5")   # < 80%
        self.tree.tag_configure("ok", background="#E5F4E5")      # 80-130%
        self.tree.tag_configure("over", background="#FFF4D6")    # > 130%
        self.tree.tag_configure("none", background="#F0F0F0")    # не назначено

        legend = ("Цвета строк (по отоплению):  "
                  "🟥 < 80% (недостаточно)  |  "
                  "🟩 80–130% (норма)  |  "
                  "🟨 > 130% (запас)  |  "
                  "⬜ не назначено.  "
                  "Двойной клик — назначить / изменить оборудование.")
        ttk.Label(self, text=legend, foreground="#555555",
                  wraplength=1300).pack(anchor="w", padx=10, pady=4)

    def subscribe_events(self):
        self.project.subscribe("data_loaded", self.refresh)
        self.project.subscribe("project_loaded", self.refresh)
        self.project.subscribe("calculation_done", self.refresh)
        self.project.subscribe("spaces_changed", self.refresh)
        self.project.subscribe("equipment_changed", self.refresh)

    def refresh(self, **kwargs):
        q = self.search_var.get().strip().lower()
        for i in self.tree.get_children():
            self.tree.delete(i)

        n_set = n_total = 0
        for sp in self.project.spaces:
            n_total += 1
            if q and (q not in sp.number.lower() and q not in sp.name.lower()):
                continue
            eq = sp.room_equipment

            if eq is None or not eq.has_any:
                tag = "none"
                heat_descr, heat_qty, heat_cov = "—", "", ""
                cool_descr, cool_qty, cool_cov = "—", "", ""
                sup_descr, exh_descr = "—", "—"
            else:
                n_set += 1
                # Отопление
                if eq.heating_terminal_qty > 0 and eq.heating_terminal_type != "—":
                    heat_descr = f"{eq.heating_terminal_type}"
                    if eq.heating_terminal_model:
                        heat_descr += f" / {eq.heating_terminal_model}"
                    heat_qty = str(eq.heating_terminal_qty)
                    cov = eq.coverage_heating(sp.heat_loss_w)
                    heat_cov = f"{cov:.0f}" if cov > 0 else "—"
                else:
                    heat_descr, heat_qty, heat_cov = "—", "", ""

                # Охлаждение
                if eq.cooling_terminal_qty > 0 and eq.cooling_terminal_type != "—":
                    cool_descr = f"{eq.cooling_terminal_type}"
                    if eq.cooling_terminal_model:
                        cool_descr += f" / {eq.cooling_terminal_model}"
                    cool_qty = str(eq.cooling_terminal_qty)
                    cov = eq.coverage_cooling(sp.heat_gain_w)
                    cool_cov = f"{cov:.0f}" if cov > 0 else "—"
                else:
                    cool_descr, cool_qty, cool_cov = "—", "", ""

                # Приток / вытяжка
                if eq.supply_terminal_qty > 0 and eq.supply_terminal_type != "—":
                    sup_descr = f"{eq.supply_terminal_type} ×{eq.supply_terminal_qty}"
                else:
                    sup_descr = "—"
                if eq.exhaust_terminal_qty > 0 and eq.exhaust_terminal_type != "—":
                    exh_descr = f"{eq.exhaust_terminal_type} ×{eq.exhaust_terminal_qty}"
                else:
                    exh_descr = "—"

                # Тег по покрытию отопления
                try:
                    cov_h = float(heat_cov)
                    if cov_h < 80:
                        tag = "under"
                    elif cov_h <= 130:
                        tag = "ok"
                    else:
                        tag = "over"
                except (ValueError, TypeError):
                    tag = "none"

            self.tree.insert("", "end", iid=sp.space_id, tags=(tag,), values=(
                sp.number, sp.name, round(sp.area_m2, 1),
                round(sp.heat_loss_w, 0) if sp.heat_loss_w else "—",
                heat_descr, heat_qty, heat_cov,
                round(sp.heat_gain_w, 0) if sp.heat_gain_w else "—",
                cool_descr, cool_qty, cool_cov,
                sup_descr, exh_descr,
            ))

        self.info_label.config(
            text=f"Помещений: {n_total},  с оборудованием: {n_set}")

    def _edit(self, event=None):
        sel = self.tree.selection()
        if not sel:
            return
        sp = self.project.get_space(sel[0])
        if not sp:
            return
        EquipmentEditDialog(self, sp, self.project, on_save=self.refresh)

    def clear_all(self):
        if not messagebox.askyesno(
                "Очистить?",
                "Удалить оборудование из ВСЕХ помещений?\n"
                "Это действие необратимо."):
            return
        n = 0
        for sp in self.project.spaces:
            if sp.room_equipment is not None:
                sp.room_equipment = None
                n += 1
        self.refresh()
        messagebox.showinfo("Готово", f"Оборудование удалено из {n} помещений.")

    def export_summary(self):
        """Экспорт сводной таблицы оборудования в отдельный Excel-файл."""
        if not self.project.spaces:
            messagebox.showwarning("Нет данных", "Сначала создайте проект.")
            return
        path = filedialog.asksaveasfilename(
            defaultextension=".xlsx",
            filetypes=[("Excel", "*.xlsx")],
            initialfile=f"Оборудование_{self.project.params.project_name}.xlsx")
        if not path:
            return
        try:
            from hvac.io_excel_equipment import export_equipment_summary
            export_equipment_summary(self.project, path)
            messagebox.showinfo("Готово",
                                 f"Сводная таблица сохранена:\n{path}")
        except Exception as e:
            import traceback
            messagebox.showerror("Ошибка",
                                  f"{e}\n\n{traceback.format_exc()}")


# ---------------------------------------------------------------------------
# Диалог редактирования оборудования
# ---------------------------------------------------------------------------


class EquipmentEditDialog(tk.Toplevel):
    """Окно редактирования оборудования одного помещения."""

    def __init__(self, parent, space, project, on_save=None):
        super().__init__(parent)
        self.sp = space
        self.project = project
        self.on_save = on_save
        self.title(f"Оборудование: {space.number} {space.name}")
        self.geometry("680x680")
        self.transient(parent)
        self.grab_set()
        self.build()

    def build(self):
        # Шапка
        head = (f"Помещение  {self.sp.number}  {self.sp.name}   "
                f"|  S = {self.sp.area_m2:.1f} м²,  V = {self.sp.volume_m3:.1f} м³")
        ttk.Label(self, text=head, font=("Segoe UI", 9, "bold"),
                  foreground="#1F4E78").pack(anchor="w", padx=12, pady=8)

        loads = (f"Расчётная нагрузка:  отопление = {self.sp.heat_loss_w:,.0f} Вт,  "
                 f"охлаждение = {self.sp.heat_gain_w:,.0f} Вт,  "
                 f"приток = {self.sp.supply_m3h:,.0f} м³/ч,  "
                 f"вытяжка = {self.sp.exhaust_m3h:,.0f} м³/ч").replace(",", " ")
        ttk.Label(self, text=loads, foreground="#444",
                  font=("Segoe UI", 9)).pack(anchor="w", padx=12, pady=2)

        eq = self.sp.get_or_create_equipment()

        # ===== Notebook с разделами =====
        nb = ttk.Notebook(self)
        nb.pack(fill="both", expand=True, padx=10, pady=6)

        # --- Отопление ---
        tab_h = ttk.Frame(nb)
        nb.add(tab_h, text="Отопление")
        self._build_terminal_section(
            tab_h, eq,
            type_field="heating_terminal_type",
            model_field="heating_terminal_model",
            power_field="heating_terminal_power_w",
            qty_field="heating_terminal_qty",
            type_options=HEATING_TERMINAL_TYPES,
            power_label="Мощность ОДНОГО прибора, Вт",
            typical_models=list(TYPICAL_RADIATOR_POWER_W.keys()),
            typical_powers=TYPICAL_RADIATOR_POWER_W,
            design_load=self.sp.heat_loss_w,
            design_label="расчётной теплопотери",
        )

        # --- Охлаждение ---
        tab_c = ttk.Frame(nb)
        nb.add(tab_c, text="Охлаждение")
        self._build_terminal_section(
            tab_c, eq,
            type_field="cooling_terminal_type",
            model_field="cooling_terminal_model",
            power_field="cooling_terminal_power_w",
            qty_field="cooling_terminal_qty",
            type_options=COOLING_TERMINAL_TYPES,
            power_label="Холодопроизводительность ОДНОГО блока, Вт",
            typical_models=list(TYPICAL_FANCOIL_COOLING_W.keys()),
            typical_powers=TYPICAL_FANCOIL_COOLING_W,
            design_load=self.sp.heat_gain_w,
            design_label="расчётного теплопоступления",
        )

        # --- Приток ---
        tab_s = ttk.Frame(nb)
        nb.add(tab_s, text="Приток")
        self._build_terminal_section(
            tab_s, eq,
            type_field="supply_terminal_type",
            model_field="supply_terminal_model",
            power_field="supply_terminal_flow_m3h",
            qty_field="supply_terminal_qty",
            type_options=SUPPLY_TERMINAL_TYPES,
            power_label="Расход через ОДИН диффузор, м³/ч",
            typical_models=list(TYPICAL_DIFFUSER_FLOW_M3H.keys()),
            typical_powers=TYPICAL_DIFFUSER_FLOW_M3H,
            design_load=self.sp.supply_m3h,
            design_label="расчётного притока",
            is_flow=True,
        )

        # --- Вытяжка ---
        tab_e = ttk.Frame(nb)
        nb.add(tab_e, text="Вытяжка")
        self._build_terminal_section(
            tab_e, eq,
            type_field="exhaust_terminal_type",
            model_field="exhaust_terminal_model",
            power_field="exhaust_terminal_flow_m3h",
            qty_field="exhaust_terminal_qty",
            type_options=EXHAUST_TERMINAL_TYPES,
            power_label="Расход через ОДНУ решётку, м³/ч",
            typical_models=list(TYPICAL_DIFFUSER_FLOW_M3H.keys()),
            typical_powers=TYPICAL_DIFFUSER_FLOW_M3H,
            design_load=self.sp.exhaust_m3h,
            design_label="расчётной вытяжки",
            is_flow=True,
        )

        # --- Примечание ---
        ttk.Label(self, text="Примечание:").pack(anchor="w", padx=12, pady=(8, 2))
        self.notes_var = tk.StringVar(value=eq.notes)
        ttk.Entry(self, textvariable=self.notes_var,
                  width=80).pack(fill="x", padx=12)

        # --- Кнопки ---
        fr = ttk.Frame(self)
        fr.pack(fill="x", padx=12, pady=10)
        ttk.Button(fr, text="💾 Сохранить",
                   command=self.save).pack(side="right", padx=4)
        ttk.Button(fr, text="Отмена",
                   command=self.destroy).pack(side="right", padx=4)
        ttk.Button(fr, text="🗑 Удалить всё",
                   command=self.clear).pack(side="left", padx=4)

    def _build_terminal_section(self, parent, eq, type_field, model_field,
                                 power_field, qty_field, type_options,
                                 power_label, typical_models, typical_powers,
                                 design_load, design_label, is_flow=False):
        """Универсальный конструктор для секции типа оборудования."""
        # Type
        ttk.Label(parent, text="Тип:").grid(row=0, column=0, sticky="w",
                                            padx=8, pady=6)
        type_var = tk.StringVar(value=getattr(eq, type_field))
        ttk.Combobox(parent, textvariable=type_var, values=type_options,
                     state="readonly", width=40).grid(row=0, column=1,
                                                       padx=8, pady=6, sticky="w")

        # Model (с подсказкой)
        ttk.Label(parent, text="Модель / маркировка:").grid(row=1, column=0,
                                                             sticky="w",
                                                             padx=8, pady=6)
        model_var = tk.StringVar(value=getattr(eq, model_field))
        ttk.Combobox(parent, textvariable=model_var,
                     values=[""] + typical_models, width=40).grid(
            row=1, column=1, padx=8, pady=6, sticky="w")

        # Power / Flow
        ttk.Label(parent, text=power_label).grid(row=2, column=0,
                                                  sticky="w", padx=8, pady=6)
        power_var = tk.StringVar(value=str(getattr(eq, power_field)))
        ttk.Entry(parent, textvariable=power_var, width=20).grid(
            row=2, column=1, padx=8, pady=6, sticky="w")

        # Quantity
        ttk.Label(parent, text="Количество в помещении:").grid(row=3, column=0,
                                                                sticky="w",
                                                                padx=8, pady=6)
        qty_var = tk.StringVar(value=str(getattr(eq, qty_field)))
        ttk.Spinbox(parent, from_=0, to=100, textvariable=qty_var,
                    width=8).grid(row=3, column=1, padx=8, pady=6, sticky="w")

        # Подсказка по покрытию (динамическая)
        cov_var = tk.StringVar()
        ttk.Label(parent, textvariable=cov_var,
                  foreground="#1F4E78",
                  font=("Segoe UI", 9, "bold"),
                  wraplength=600).grid(row=4, column=0, columnspan=2,
                                       sticky="w", padx=8, pady=12)

        def update_cov(*_):
            try:
                pwr = float(power_var.get().replace(",", "."))
                qty = int(float(qty_var.get()))
                total = pwr * qty
                if design_load > 0:
                    pct = 100 * total / design_load
                    unit = "м³/ч" if is_flow else "Вт"
                    cov_var.set(
                        f"Установлено: {total:,.0f} {unit}.  "
                        f"Покрытие {design_label}: {pct:.0f}%".replace(",", " "))
                else:
                    unit = "м³/ч" if is_flow else "Вт"
                    cov_var.set(f"Установлено: {total:,.0f} {unit}.  "
                                f"(расчёт ещё не выполнен)".replace(",", " "))
            except (ValueError, TypeError):
                cov_var.set("")

        power_var.trace_add("write", update_cov)
        qty_var.trace_add("write", update_cov)

        # Автозаполнение мощности при выборе модели из подсказок
        def on_model_change(*_):
            chosen = model_var.get()
            if chosen in typical_powers:
                power_var.set(str(typical_powers[chosen]))

        model_var.trace_add("write", on_model_change)
        update_cov()

        # Сохраним в объект для save()
        setattr(self, f"_{type_field}", type_var)
        setattr(self, f"_{model_field}", model_var)
        setattr(self, f"_{power_field}", power_var)
        setattr(self, f"_{qty_field}", qty_var)

    def save(self):
        try:
            eq = self.sp.get_or_create_equipment()
            # Heating
            eq.heating_terminal_type = self._heating_terminal_type.get()
            eq.heating_terminal_model = self._heating_terminal_model.get().strip()
            eq.heating_terminal_power_w = float(
                self._heating_terminal_power_w.get().replace(",", ".") or "0")
            eq.heating_terminal_qty = int(float(
                self._heating_terminal_qty.get() or "0"))
            # Cooling
            eq.cooling_terminal_type = self._cooling_terminal_type.get()
            eq.cooling_terminal_model = self._cooling_terminal_model.get().strip()
            eq.cooling_terminal_power_w = float(
                self._cooling_terminal_power_w.get().replace(",", ".") or "0")
            eq.cooling_terminal_qty = int(float(
                self._cooling_terminal_qty.get() or "0"))
            # Supply
            eq.supply_terminal_type = self._supply_terminal_type.get()
            eq.supply_terminal_model = self._supply_terminal_model.get().strip()
            eq.supply_terminal_flow_m3h = float(
                self._supply_terminal_flow_m3h.get().replace(",", ".") or "0")
            eq.supply_terminal_qty = int(float(
                self._supply_terminal_qty.get() or "0"))
            # Exhaust
            eq.exhaust_terminal_type = self._exhaust_terminal_type.get()
            eq.exhaust_terminal_model = self._exhaust_terminal_model.get().strip()
            eq.exhaust_terminal_flow_m3h = float(
                self._exhaust_terminal_flow_m3h.get().replace(",", ".") or "0")
            eq.exhaust_terminal_qty = int(float(
                self._exhaust_terminal_qty.get() or "0"))
            # Notes
            eq.notes = self.notes_var.get().strip()
        except ValueError as e:
            messagebox.showerror("Ошибка",
                                  f"Введите корректные числа.\n{e}")
            return

        self.project.emit("equipment_changed")
        if self.on_save:
            self.on_save()
        self.destroy()

    def clear(self):
        if messagebox.askyesno("Удалить?",
                                "Удалить оборудование из этого помещения?"):
            self.sp.room_equipment = None
            self.project.emit("equipment_changed")
            if self.on_save:
                self.on_save()
            self.destroy()
