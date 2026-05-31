# -*- coding: utf-8 -*-
"""Вкладки UI для работы с контурами ИТП и участками трубопроводов.

CircuitsTab    — CRUD контуров отопления / холодоснабжения, привязка помещений.
PipeSectionsTab — редактирование длин участков, пересчёт Δp.

Подключаются в hvac/ui/tabs.py через TABS_REGISTRY.
"""

from __future__ import annotations
import tkinter as tk
from tkinter import ttk, messagebox
from typing import List, Optional

from hvac.ui.tabs import BaseTab
from hvac.equipment import (
    HeatingCircuit, CoolingCircuit,
    HEATING_CIRCUIT_TYPES, HEATING_CIRCUIT_DEFAULTS,
    COOLING_CIRCUIT_TYPES, COOLING_CIRCUIT_DEFAULTS,
)


# ============================================================================
# Вкладка "Контуры ИТП"
# ============================================================================

class CircuitsTab(BaseTab):
    """Управление контурами ИТП.

    Левая колонка: список HeatingCircuit + CoolingCircuit (с возможностью
    создать, удалить, изменить параметры).
    Правая колонка: помещения, которые можно привязать к выбранному контуру
    через combobox в столбце «Контур».
    """
    title = "9. Контуры ИТП"

    def build(self):
        # Верхняя панель действий
        fr_top = ttk.LabelFrame(self, text="Действия")
        fr_top.pack(fill="x", padx=10, pady=6)

        ttk.Button(fr_top, text="+ Контур отопл.",
                   command=lambda: self._add_circuit("heating")
                   ).pack(side="left", padx=4, pady=4)
        ttk.Button(fr_top, text="+ Контур холода",
                   command=lambda: self._add_circuit("cooling")
                   ).pack(side="left", padx=4, pady=4)
        ttk.Button(fr_top, text="Удалить выбранный",
                   command=self._delete_selected
                   ).pack(side="left", padx=4, pady=4)
        ttk.Separator(fr_top, orient="vertical").pack(side="left",
                                                       fill="y", padx=8)
        ttk.Button(fr_top, text="Авто-создать типовые (рад/ТП/AHU)",
                   command=self._auto_create_typical
                   ).pack(side="left", padx=4, pady=4)
        ttk.Separator(fr_top, orient="vertical").pack(side="left",
                                                       fill="y", padx=8)
        ttk.Button(fr_top, text="Пересчитать гидравлику",
                   command=self._recalc_hydraulics
                   ).pack(side="left", padx=4, pady=4)

        # Сплит-окно
        paned = ttk.PanedWindow(self, orient="horizontal")
        paned.pack(fill="both", expand=True, padx=10, pady=4)

        # Левая часть — список контуров
        left_fr = ttk.LabelFrame(paned, text="Контуры")
        paned.add(left_fr, weight=2)

        from hvac.ui.tree_sort import make_scrollable_tree
        cols = ("Среда", "Имя", "ИТП", "Тип", "t_под", "t_обр",
                "Q, кВт", "G, м³/ч", "Насос")
        widths = {"Среда": 60, "Имя": 100, "ИТП": 90, "Тип": 100,
                  "t_под": 50, "t_обр": 50, "Q, кВт": 60,
                  "G, м³/ч": 70, "Насос": 220}
        right_align = ("t_под", "t_обр", "Q, кВт", "G, м³/ч")
        self.circuits_tree, self._circ_sort, circ_frame = \
            make_scrollable_tree(
                left_fr, columns=cols, widths=widths,
                right_align=right_align, height=14, select_mode="browse",
            )
        circ_frame.pack(fill="both", expand=True, padx=4, pady=4)
        self.circuits_tree.bind("<Double-1>", self._edit_selected)
        self.circuits_tree.bind("<<TreeviewSelect>>", self._on_circuit_select)

        ttk.Label(left_fr, text="Двойной клик — редактировать параметры контура",
                  foreground="gray").pack(anchor="w", padx=6, pady=(0, 4))

        # Правая часть — помещения и их привязки
        right_fr = ttk.LabelFrame(paned, text="Помещения и привязки")
        paned.add(right_fr, weight=3)

        # Mass-edit: привязать выделенные к контуру
        fr_bulk = ttk.Frame(right_fr)
        fr_bulk.pack(fill="x", padx=4, pady=4)
        ttk.Label(fr_bulk, text="Среда:").pack(side="left", padx=2)
        self.bulk_medium = tk.StringVar(value="heating")
        ttk.Combobox(fr_bulk, textvariable=self.bulk_medium,
                     values=["heating", "cooling"], state="readonly",
                     width=10).pack(side="left", padx=2)

        ttk.Label(fr_bulk, text="Контур:").pack(side="left", padx=2)
        self.bulk_circuit = tk.StringVar()
        self.bulk_combo = ttk.Combobox(fr_bulk,
                                        textvariable=self.bulk_circuit,
                                        state="readonly", width=20)
        self.bulk_combo.pack(side="left", padx=2)
        ttk.Button(fr_bulk, text="Применить к выделенным",
                   command=self._bulk_assign
                   ).pack(side="left", padx=4)
        ttk.Button(fr_bulk, text="Очистить привязку",
                   command=self._bulk_clear
                   ).pack(side="left", padx=4)

        # Поиск над таблицей помещений
        from hvac.ui.tree_sort import make_search_bar
        search_fr, self.search_var = make_search_bar(
            right_fr, on_change=lambda q: self._refresh_spaces(),
            placeholder="(№, имя, уровень)")
        search_fr.pack(fill="x", padx=4, pady=2)

        rcols = ("№", "Имя", "Уровень", "Q отопл.", "Q охл.",
                 "Контур отопл.", "Контур охл.")
        wd = {"№": 70, "Имя": 130, "Уровень": 75, "Q отопл.": 75,
              "Q охл.": 75, "Контур отопл.": 110, "Контур охл.": 110}
        right_align = ("Q отопл.", "Q охл.")
        self.spaces_tree, self._sp_sort, sp_frame = make_scrollable_tree(
            right_fr, columns=rcols, widths=wd, right_align=right_align,
            height=18, select_mode="extended",
        )
        sp_frame.pack(fill="both", expand=True, padx=4, pady=4)

        self.status = ttk.Label(self, text="", foreground="green")
        self.status.pack(fill="x", padx=10, pady=4)

        self.refresh()

    def subscribe_events(self):
        for ev in ("project_loaded", "calculation_done", "pipes_sized",
                    "cooling_pipes_sized"):
            self.project.subscribe(ev, lambda **kw: self.refresh())

    def on_show(self):
        self.refresh()

    # -------- наполнение таблиц --------
    def refresh(self):
        self.circuits_tree.delete(*self.circuits_tree.get_children())
        # Heating
        for cname, circ in sorted(self.project.heating_circuits.items()):
            net = self.project.pipe_networks.get(cname)
            q_kw = (net.total_heat_load_w / 1000) if net else 0
            g = (net.pump_flow_m3_h if net
                 else (net.total_flow_kg_h / 1000) if net else 0)
            pump = (net.pump_model if net else circ.pump_model) or "—"
            self.circuits_tree.insert("", "end", iid=f"H/{cname}",
                values=("Отопл.", cname, circ.parent_system,
                        circ.circuit_type, circ.t_supply, circ.t_return,
                        f"{q_kw:.1f}", f"{g:.2f}", pump))
        # Cooling
        for cname, circ in sorted(self.project.cooling_circuits.items()):
            net = self.project.cooling_pipe_networks.get(cname)
            q_kw = (net.total_heat_load_w / 1000) if net else 0
            g = (net.pump_flow_m3_h if net else 0)
            pump = (net.pump_model if net else circ.pump_model) or "—"
            self.circuits_tree.insert("", "end", iid=f"C/{cname}",
                values=("Холод", cname, circ.parent_system,
                        circ.circuit_type, circ.t_supply, circ.t_return,
                        f"{q_kw:.1f}", f"{g:.2f}", pump))
        if hasattr(self, "_circ_sort"):
            self._circ_sort()
        self._refresh_combobox()
        self._refresh_spaces()

    def _refresh_combobox(self):
        medium = self.bulk_medium.get()
        if medium == "heating":
            names = sorted(self.project.heating_circuits.keys())
        else:
            names = sorted(self.project.cooling_circuits.keys())
        self.bulk_combo.configure(values=names)

    def _refresh_spaces(self):
        query = (self.search_var.get().strip().lower()
                 if hasattr(self, "search_var") else "")
        self.spaces_tree.delete(*self.spaces_tree.get_children())
        for sp in self.project.spaces:
            if query:
                hay = f"{sp.number} {sp.name} {sp.level}".lower()
                if query not in hay:
                    continue
            self.spaces_tree.insert("", "end", iid=sp.space_id, values=(
                sp.number, sp.name, sp.level,
                f"{sp.heat_loss_w:.0f}", f"{sp.heat_gain_w:.0f}",
                sp.circuit_heating, sp.circuit_cooling,
            ))
        if hasattr(self, "_sp_sort"):
            self._sp_sort()

    # -------- действия --------
    def _on_circuit_select(self, _evt=None):
        sel = self.circuits_tree.selection()
        if not sel:
            return
        iid = sel[0]
        medium = "heating" if iid.startswith("H/") else "cooling"
        cname = iid.split("/", 1)[1]
        self.bulk_medium.set(medium)
        self.bulk_circuit.set(cname)
        self._refresh_combobox()

    def _add_circuit(self, medium: str):
        """Создать новый контур через простой диалог."""
        if medium == "heating":
            dialog = _CircuitDialog(self, medium="heating",
                                    project=self.project)
        else:
            dialog = _CircuitDialog(self, medium="cooling",
                                    project=self.project)
        self.wait_window(dialog.top)
        if dialog.result:
            self.refresh()
            self._set_status(f"Контур '{dialog.result}' создан")

    def _edit_selected(self, _evt=None):
        sel = self.circuits_tree.selection()
        if not sel:
            return
        iid = sel[0]
        medium = "heating" if iid.startswith("H/") else "cooling"
        cname = iid.split("/", 1)[1]
        circ = (self.project.heating_circuits.get(cname) if medium == "heating"
                else self.project.cooling_circuits.get(cname))
        if not circ:
            return
        dialog = _CircuitDialog(self, medium=medium, project=self.project,
                                existing=circ)
        self.wait_window(dialog.top)
        self.refresh()

    def _delete_selected(self):
        sel = self.circuits_tree.selection()
        if not sel:
            return
        iid = sel[0]
        medium = "heating" if iid.startswith("H/") else "cooling"
        cname = iid.split("/", 1)[1]
        if not messagebox.askyesno("Удаление",
                                    f"Удалить контур '{cname}'?\n"
                                    "Привязки помещений также будут очищены."):
            return
        container = (self.project.heating_circuits if medium == "heating"
                     else self.project.cooling_circuits)
        container.pop(cname, None)
        # Очищаем привязки помещений
        attr = "circuit_heating" if medium == "heating" else "circuit_cooling"
        for sp in self.project.spaces:
            if getattr(sp, attr) == cname:
                setattr(sp, attr, "")
        self.refresh()
        self._set_status(f"Контур '{cname}' удалён")

    def _auto_create_typical(self):
        """Создаёт типовой набор контуров для одного ИТП."""
        from tkinter.simpledialog import askstring
        itp = askstring("Имя ИТП", "Имя источника тепла (например 'ИТП-1'):",
                        parent=self)
        if not itp:
            return
        created = []
        templates = [
            ("Рад", "radiator"),
            ("ТП", "floor"),
            ("ФК-теп", "fancoil"),
            ("AHU-кал", "ahu_heater"),
        ]
        for suffix, ctype in templates:
            name = f"{suffix}-{itp.split('-')[-1] if '-' in itp else itp}"
            if name in self.project.heating_circuits:
                continue
            t_sup, t_ret = HEATING_CIRCUIT_DEFAULTS.get(ctype, (80, 60))
            self.project.heating_circuits[name] = HeatingCircuit(
                name=name, parent_system=itp, circuit_type=ctype,
                t_supply=t_sup, t_return=t_ret,
                has_mixing_node=(ctype == "floor"),
            )
            created.append(name)
        # Холодильный контур
        cool_name = f"ФК-хол-{itp.split('-')[-1] if '-' in itp else itp}"
        if cool_name not in self.project.cooling_circuits:
            self.project.cooling_circuits[cool_name] = CoolingCircuit(
                name=cool_name, parent_system="Чиллер",
                circuit_type="fancoil", t_supply=7, t_return=12,
                insulated=True,
            )
            created.append(cool_name)
        self.refresh()
        self._set_status(f"Создано {len(created)} контуров: "
                          + ", ".join(created))

    def _bulk_assign(self):
        sel = self.spaces_tree.selection()
        if not sel:
            messagebox.showinfo("Нет выделения",
                                 "Выделите помещения в правой таблице.")
            return
        medium = self.bulk_medium.get()
        cname = self.bulk_circuit.get()
        if not cname:
            messagebox.showinfo("Нет контура",
                                 "Выберите контур из списка.")
            return
        attr = "circuit_heating" if medium == "heating" else "circuit_cooling"
        n = 0
        for sid in sel:
            sp = self.project.get_space(sid)
            if sp:
                setattr(sp, attr, cname)
                n += 1
        self.refresh()
        self._set_status(f"Привязано {n} помещений к контуру '{cname}'")

    def _bulk_clear(self):
        sel = self.spaces_tree.selection()
        if not sel:
            return
        medium = self.bulk_medium.get()
        attr = "circuit_heating" if medium == "heating" else "circuit_cooling"
        n = 0
        for sid in sel:
            sp = self.project.get_space(sid)
            if sp:
                setattr(sp, attr, "")
                n += 1
        self.refresh()
        self._set_status(f"Очищена привязка у {n} помещений")

    def _recalc_hydraulics(self):
        try:
            heat_nets = self.project.size_pipes()
            cool_nets = self.project.size_cooling_pipes()
            self._set_status(f"Рассчитано: {len(heat_nets)} отопл. + "
                              f"{len(cool_nets)} холод. контуров")
            self.refresh()
        except Exception as e:
            messagebox.showerror("Ошибка", f"Ошибка расчёта: {e}")

    def _set_status(self, msg: str):
        self.status.configure(text=msg)


# ============================================================================
# Диалог создания/редактирования контура
# ============================================================================

class _CircuitDialog:
    """Простой модальный диалог с полями HeatingCircuit/CoolingCircuit."""

    def __init__(self, parent, medium: str, project,
                 existing: Optional[object] = None):
        self.medium = medium
        self.project = project
        self.existing = existing
        self.result: Optional[str] = None

        self.top = tk.Toplevel(parent)
        self.top.title(("Контур отопления" if medium == "heating"
                        else "Контур холода"))
        self.top.transient(parent)
        self.top.grab_set()
        self.top.resizable(False, False)

        types = (HEATING_CIRCUIT_TYPES if medium == "heating"
                 else COOLING_CIRCUIT_TYPES)
        defaults = (HEATING_CIRCUIT_DEFAULTS if medium == "heating"
                    else COOLING_CIRCUIT_DEFAULTS)

        # Поля
        self.var_name = tk.StringVar(value=existing.name if existing else "")
        self.var_parent = tk.StringVar(
            value=existing.parent_system if existing else "")
        self.var_type = tk.StringVar(
            value=existing.circuit_type if existing else types[0])
        t_sup_def, t_ret_def = defaults.get(self.var_type.get(), (60, 40))
        self.var_t_sup = tk.DoubleVar(
            value=existing.t_supply if existing else t_sup_def)
        self.var_t_ret = tk.DoubleVar(
            value=existing.t_return if existing else t_ret_def)
        self.var_mixing = tk.BooleanVar(
            value=getattr(existing, "has_mixing_node", False)
            if existing else False)
        self.var_insulated = tk.BooleanVar(
            value=getattr(existing, "insulated", True)
            if existing else True)
        self.var_serves_ahu = tk.StringVar(
            value=existing.serves_ahu if existing else "")
        self.var_material = tk.StringVar(
            value=existing.pipe_material if existing else "steel")
        self.var_note = tk.StringVar(value=existing.note if existing else "")

        row = 0
        ttk.Label(self.top, text="Имя контура:").grid(
            row=row, column=0, padx=6, pady=4, sticky="e")
        name_entry = ttk.Entry(self.top, textvariable=self.var_name, width=24)
        name_entry.grid(row=row, column=1, padx=6, pady=4, sticky="w")
        if existing:
            name_entry.configure(state="disabled")
        row += 1

        ttk.Label(self.top,
                  text="ИТП/источник:" if medium == "heating"
                       else "Чиллер/источник:").grid(
            row=row, column=0, padx=6, pady=4, sticky="e")
        ttk.Entry(self.top, textvariable=self.var_parent, width=24
                  ).grid(row=row, column=1, padx=6, pady=4, sticky="w")
        row += 1

        ttk.Label(self.top, text="Тип:").grid(
            row=row, column=0, padx=6, pady=4, sticky="e")
        cb = ttk.Combobox(self.top, textvariable=self.var_type,
                          values=types, state="readonly", width=22)
        cb.grid(row=row, column=1, padx=6, pady=4, sticky="w")
        cb.bind("<<ComboboxSelected>>", lambda e: self._on_type_change(
            defaults))
        row += 1

        ttk.Label(self.top, text="t подачи, °C:").grid(
            row=row, column=0, padx=6, pady=4, sticky="e")
        ttk.Entry(self.top, textvariable=self.var_t_sup, width=10
                  ).grid(row=row, column=1, padx=6, pady=4, sticky="w")
        row += 1

        ttk.Label(self.top, text="t обратки, °C:").grid(
            row=row, column=0, padx=6, pady=4, sticky="e")
        ttk.Entry(self.top, textvariable=self.var_t_ret, width=10
                  ).grid(row=row, column=1, padx=6, pady=4, sticky="w")
        row += 1

        if medium == "heating":
            ttk.Checkbutton(self.top, text="Смесительный узел",
                            variable=self.var_mixing).grid(
                row=row, column=1, padx=6, pady=4, sticky="w")
            row += 1
        else:
            ttk.Checkbutton(self.top, text="Изоляция трубопровода",
                            variable=self.var_insulated).grid(
                row=row, column=1, padx=6, pady=4, sticky="w")
            row += 1

        ttk.Label(self.top, text="AHU (если AHU-кал/охл.):").grid(
            row=row, column=0, padx=6, pady=4, sticky="e")
        ahu_names = list(self.project.ventilation_systems.keys())
        ttk.Combobox(self.top, textvariable=self.var_serves_ahu,
                     values=[""] + ahu_names, width=22
                     ).grid(row=row, column=1, padx=6, pady=4, sticky="w")
        row += 1

        ttk.Label(self.top, text="Материал труб:").grid(
            row=row, column=0, padx=6, pady=4, sticky="e")
        ttk.Combobox(self.top, textvariable=self.var_material,
                     values=["steel", "pex", "ppr"], state="readonly",
                     width=10).grid(row=row, column=1, padx=6, pady=4,
                                    sticky="w")
        row += 1

        ttk.Label(self.top, text="Примечание:").grid(
            row=row, column=0, padx=6, pady=4, sticky="e")
        ttk.Entry(self.top, textvariable=self.var_note, width=32
                  ).grid(row=row, column=1, padx=6, pady=4, sticky="w")
        row += 1

        # Кнопки
        btn_fr = ttk.Frame(self.top)
        btn_fr.grid(row=row, column=0, columnspan=2, pady=8)
        ttk.Button(btn_fr, text="OK", command=self._ok, width=10
                   ).pack(side="left", padx=4)
        ttk.Button(btn_fr, text="Отмена", command=self.top.destroy, width=10
                   ).pack(side="left", padx=4)

    def _on_type_change(self, defaults):
        t = self.var_type.get()
        if t in defaults:
            t_sup, t_ret = defaults[t]
            self.var_t_sup.set(t_sup)
            self.var_t_ret.set(t_ret)
            if t == "floor":
                self.var_mixing.set(True)

    def _ok(self):
        name = self.var_name.get().strip()
        if not name:
            messagebox.showerror("Ошибка", "Укажите имя контура.",
                                  parent=self.top)
            return
        if self.medium == "heating":
            container = self.project.heating_circuits
            cls = HeatingCircuit
        else:
            container = self.project.cooling_circuits
            cls = CoolingCircuit
        if self.existing is None and name in container:
            messagebox.showerror("Ошибка",
                                  f"Контур '{name}' уже существует.",
                                  parent=self.top)
            return

        kwargs = dict(
            name=name,
            parent_system=self.var_parent.get().strip(),
            circuit_type=self.var_type.get(),
            t_supply=self.var_t_sup.get(),
            t_return=self.var_t_ret.get(),
            serves_ahu=self.var_serves_ahu.get().strip(),
            pipe_material=self.var_material.get(),
            note=self.var_note.get().strip(),
        )
        if self.medium == "heating":
            kwargs["has_mixing_node"] = self.var_mixing.get()
        else:
            kwargs["insulated"] = self.var_insulated.get()

        # Сохраняем подобранные ранее значения насоса, если редактировали
        if self.existing:
            kwargs["pump_model"] = getattr(self.existing, "pump_model", "")
            kwargs["pump_flow_m3_h"] = getattr(self.existing,
                                                "pump_flow_m3_h", 0.0)
            kwargs["pump_head_m"] = getattr(self.existing, "pump_head_m", 0.0)

        container[name] = cls(**kwargs)
        self.result = name
        self.top.destroy()


# ============================================================================
# Вкладка "Участки труб"
# ============================================================================

class PipeSectionsTab(BaseTab):
    """Редактирование длин и Σζ участков труб + пересчёт Δp.

    Слева — список сетей (контуров) отопления + холода.
    Справа — таблица участков выбранной сети, столбцы L, Σζ, ΔH редактируемые.
    Внизу — кнопка «Пересчитать Δp и насос».
    """
    title = "10. Участки труб"

    def build(self):
        # Верхняя панель
        fr_top = ttk.Frame(self)
        fr_top.pack(fill="x", padx=10, pady=6)

        ttk.Label(fr_top, text="Сеть:", font=("Segoe UI", 9, "bold")
                  ).pack(side="left", padx=4)
        self.net_var = tk.StringVar()
        self.net_combo = ttk.Combobox(fr_top, textvariable=self.net_var,
                                       state="readonly", width=40)
        self.net_combo.pack(side="left", padx=4)
        self.net_combo.bind("<<ComboboxSelected>>",
                             lambda e: self._refresh_sections())

        ttk.Button(fr_top, text="Обновить список",
                   command=self._refresh_nets
                   ).pack(side="left", padx=8)
        ttk.Button(fr_top, text="Пересчитать Δp и насос",
                   command=self._recompute
                   ).pack(side="right", padx=4)

        # Таблица участков с ползунками и сортировкой
        from hvac.ui.tree_sort import make_scrollable_tree
        cols = ("ID", "Тип", "Q, Вт", "G, кг/ч", "DN", "v, м/с",
                "L, м", "Σζ", "ΔH, м",
                "Δp_тр", "Δp_мест", "Δp_сум, Па", "Примечание")
        widths = {"ID": 130, "Тип": 80, "Q, Вт": 70, "G, кг/ч": 70,
                  "DN": 50, "v, м/с": 60, "L, м": 60, "Σζ": 50,
                  "ΔH, м": 60, "Δp_тр": 70, "Δp_мест": 70,
                  "Δp_сум, Па": 80, "Примечание": 200}
        right_align = ("Q, Вт", "G, кг/ч", "DN", "v, м/с", "L, м", "Σζ",
                       "ΔH, м", "Δp_тр", "Δp_мест", "Δp_сум, Па")
        self.tree, self._sec_sort, tree_frame = make_scrollable_tree(
            self, columns=cols, widths=widths, right_align=right_align,
            height=22, select_mode="browse",
        )
        tree_frame.pack(fill="both", expand=True, padx=10, pady=4)
        self.tree.bind("<Double-1>", self._edit_cell)

        # Подсказка
        hint = ttk.Label(
            self,
            text="Двойной клик по ячейкам L, Σζ, ΔH — редактирование. "
                 "После правки нажмите «Пересчитать Δp и насос».",
            foreground="gray")
        hint.pack(anchor="w", padx=12, pady=2)

        # Статус — сводка по выбранной сети
        self.summary = ttk.Label(self, text="—", font=("Segoe UI", 9, "bold"))
        self.summary.pack(fill="x", padx=10, pady=4)

        self.status = ttk.Label(self, text="", foreground="green")
        self.status.pack(fill="x", padx=10, pady=2)

        self._refresh_nets()

    def subscribe_events(self):
        for ev in ("pipes_sized", "cooling_pipes_sized", "pipes_recomputed"):
            self.project.subscribe(ev, lambda **kw: self._refresh_nets())

    def on_show(self):
        self._refresh_nets()

    def _all_networks(self):
        """Возвращает [(метка, ключ_в_словаре, контейнер)]."""
        out = []
        for k in sorted(self.project.pipe_networks.keys()):
            out.append((f"Отопление: {k}", k, "heating"))
        for k in sorted(self.project.cooling_pipe_networks.keys()):
            out.append((f"Холод: {k}", k, "cooling"))
        return out

    def _refresh_nets(self):
        nets = self._all_networks()
        labels = [n[0] for n in nets]
        self.net_combo.configure(values=labels)
        if labels and self.net_var.get() not in labels:
            self.net_var.set(labels[0])
        self._refresh_sections()

    def _current_net(self):
        label = self.net_var.get()
        for lbl, key, mode in self._all_networks():
            if lbl == label:
                if mode == "heating":
                    return self.project.pipe_networks.get(key)
                return self.project.cooling_pipe_networks.get(key)
        return None

    def _refresh_sections(self):
        self.tree.delete(*self.tree.get_children())
        net = self._current_net()
        if not net:
            self.summary.configure(text="—")
            return
        for s in net.sections:
            self.tree.insert("", "end", iid=s.id, values=(
                s.id, s.section_type,
                f"{s.heat_load_w:.0f}",
                f"{s.flow_kg_h:.1f}",
                int(s.dn_mm),
                f"{s.velocity_m_s:.2f}",
                f"{s.length_m:.1f}",
                f"{s.local_zeta_sum:.2f}",
                f"{s.elevation_m:.1f}",
                f"{s.pressure_loss_friction_pa:.1f}",
                f"{s.pressure_loss_local_pa:.1f}",
                f"{s.pressure_loss_total_pa:.1f}",
                s.note,
            ))
        pump = getattr(net, "pump_model", "") or "—"
        self.summary.configure(text=(
            f"{net.system_name}: Q = {net.total_heat_load_w / 1000:.1f} кВт  |  "
            f"t = {net.t_supply_c:.0f}/{net.t_return_c:.0f} °C  |  "
            f"Δp = {net.total_pressure_loss_pa / 1000:.1f} кПа  |  "
            f"Насос: {pump} (H = {net.pump_head_m:.1f} м)"
        ))
        if hasattr(self, "_sec_sort"):
            self._sec_sort()

    def _edit_cell(self, event):
        """Редактирование L, Σζ, ΔH в ячейке."""
        col = self.tree.identify_column(event.x)
        row = self.tree.identify_row(event.y)
        if not row or not col:
            return
        # Колонки 7, 8, 9 — L, Σζ, ΔH (1-индексация)
        col_idx = int(col.replace("#", ""))
        if col_idx not in (7, 8, 9):
            return
        col_attr = {7: "length_m", 8: "local_zeta_sum", 9: "elevation_m"}[col_idx]

        net = self._current_net()
        if not net:
            return
        sec = next((s for s in net.sections if s.id == row), None)
        if not sec:
            return

        # Создаём временный Entry поверх ячейки
        x, y, w, h = self.tree.bbox(row, col)
        entry = ttk.Entry(self.tree)
        entry.place(x=x, y=y, width=w, height=h)
        entry.insert(0, str(getattr(sec, col_attr)))
        entry.select_range(0, "end")
        entry.focus_set()

        def commit(_evt=None):
            try:
                val = float(entry.get().replace(",", "."))
                setattr(sec, col_attr, val)
                self._refresh_sections()
            except ValueError:
                pass
            entry.destroy()

        entry.bind("<Return>", commit)
        entry.bind("<FocusOut>", commit)
        entry.bind("<Escape>", lambda e: entry.destroy())

    def _recompute(self):
        net = self._current_net()
        if not net:
            return
        from hvac.pipe_sizing import recompute_pipe_network
        recompute_pipe_network(net)
        self._refresh_sections()
        self.status.configure(
            text=f"Пересчитано: Δp = {net.total_pressure_loss_pa / 1000:.1f} кПа, "
                 f"насос {net.pump_model}, H = {net.pump_head_m:.1f} м"
        )
