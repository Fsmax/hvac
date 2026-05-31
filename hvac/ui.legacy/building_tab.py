# -*- coding: utf-8 -*-
"""Вкладка «0. Здание» — ручной ввод помещений и ограждений (без Revit).

Позволяет создать проект полностью с нуля:
1. Создать пустой проект.
2. Добавить помещения (этаж, номер, имя, площадь, высота, тип).
3. Для каждого помещения добавить ограждения:
   - Наружная стена / Перекрытие пола / Покрытие
   - Окно / Витраж
   - Дверь наружная
   - Внутренняя стена (в неотапливаемое помещение)
4. Получившийся проект сохраняется в JSON полностью (без CSV).
"""

from __future__ import annotations
import tkinter as tk
from tkinter import ttk, messagebox, filedialog

from hvac.project import HVACProject
from hvac.catalogs.room_types import ROOM_TYPE_PRESETS, get_all_room_types
from hvac.catalogs.climate import CLIMATE_DB
from hvac.ui.tree_sort import attach_sort


# Категории ограждений для ручного ввода — упрощённый словарь
# (категория, семейство по умолчанию, толщина мм, U Вт/м²К, SHGC)
ELEMENT_PRESETS = {
    "Наружная стена (кирпич 380мм + утеплитель)":
        ("external_wall", "Стены", "Несущие", "Стена_380_утепл", 380, 0.35, 0.6),
    "Наружная стена (газобетон 400мм)":
        ("external_wall", "Стены", "Несущие", "Стена_газобетон_400", 400, 0.30, 0.6),
    "Наружная стена (сэндвич-панель 150мм)":
        ("external_wall", "Стены", "Сэндвич", "Сэндвич_150", 150, 0.28, 0.6),
    "Перекрытие пола по грунту":
        ("external_wall", "Перекрытия", "Пол по грунту", "Пол_грунт", 300, 0.40, 0.6),
    "Покрытие (кровля)":
        ("external_wall", "Перекрытия", "Кровля", "Кровля_утепл", 350, 0.25, 0.6),
    "Окно одностекольное":
        ("opening", "Окна", "Стандарт", "Окно_1ст", 4, 5.80, 0.85),
    "Окно двухкамерный стеклопакет":
        ("opening", "Окна", "Стандарт", "Окно_2кам", 32, 1.80, 0.65),
    "Окно энергосберегающее":
        ("opening", "Окна", "Энерго", "Окно_энерго", 36, 1.20, 0.50),
    "Витраж алюминиевый":
        ("opening", "Витражи", "Алюминий", "Витраж_алюм", 32, 2.20, 0.60),
    "Дверь наружная металлическая":
        ("opening", "Двери", "Металл", "Дверь_металл", 70, 2.50, 0.0),
    "Дверь наружная утеплённая":
        ("opening", "Двери", "Утеплённая", "Дверь_утепл", 80, 1.80, 0.0),
}

ORIENTATIONS = ["", "N", "NE", "E", "SE", "S", "SW", "W", "NW"]
ORIENTATION_LABELS = {
    "": "—",
    "N": "С (Север)",
    "NE": "СВ",
    "E": "В (Восток)",
    "SE": "ЮВ",
    "S": "Ю (Юг)",
    "SW": "ЮЗ",
    "W": "З (Запад)",
    "NW": "СЗ",
}


class BuildingTab(ttk.Frame):
    """Вкладка ручного ввода здания."""

    title = "0. Здание (ручной ввод)"

    def __init__(self, parent, project: HVACProject, app):
        super().__init__(parent)
        self.project = project
        self.app = app
        self.current_space_id = None  # текущее выбранное помещение
        self.build()
        self.subscribe_events()

    def build(self):
        # ---- Верхняя панель: проект ----
        top = ttk.LabelFrame(self, text="Проект")
        top.pack(fill="x", padx=10, pady=6)

        ttk.Button(top, text="🆕 Новый пустой проект…",
                   command=self.new_empty_project).grid(row=0, column=0, padx=6, pady=6)
        ttk.Button(top, text="📁 Открыть проект (.json)…",
                   command=self.open_project).grid(row=0, column=1, padx=6, pady=6)
        ttk.Button(top, text="💾 Сохранить проект (.json)…",
                   command=self.save_project).grid(row=0, column=2, padx=6, pady=6)

        self.info_var = tk.StringVar(value="Создайте новый проект или откройте существующий.")
        ttk.Label(top, textvariable=self.info_var, foreground="#1F4E78",
                  font=("Segoe UI", 9, "bold")).grid(row=1, column=0, columnspan=4,
                                                    padx=8, pady=4, sticky="w")

        # ---- Разделение: слева помещения, справа ограждения ----
        paned = ttk.PanedWindow(self, orient="horizontal")
        paned.pack(fill="both", expand=True, padx=10, pady=4)

        # ===== Левая панель: помещения =====
        left = ttk.LabelFrame(paned, text="Помещения")
        paned.add(left, weight=1)

        toolbar_l = ttk.Frame(left)
        toolbar_l.pack(fill="x", padx=4, pady=4)
        ttk.Button(toolbar_l, text="➕ Добавить",
                   command=self.add_space_dialog).pack(side="left", padx=2)
        ttk.Button(toolbar_l, text="✏️ Изменить",
                   command=self.edit_space_dialog).pack(side="left", padx=2)
        ttk.Button(toolbar_l, text="🗑 Удалить",
                   command=self.delete_space).pack(side="left", padx=2)

        # Строка поиска (фильтр по №, имени, уровню, типу)
        search_fr = ttk.Frame(left)
        search_fr.pack(fill="x", padx=4, pady=(0, 4))
        ttk.Label(search_fr, text="🔍 Поиск:").pack(side="left", padx=(0, 4))
        self.search_var = tk.StringVar()
        self.search_var.trace_add("write", lambda *_: self._apply_filter())
        search_entry = ttk.Entry(search_fr, textvariable=self.search_var)
        search_entry.pack(side="left", fill="x", expand=True)
        ttk.Button(search_fr, text="✕", width=3,
                   command=lambda: self.search_var.set("")).pack(
                       side="left", padx=(2, 0))

        cols_l = ("№", "Имя", "Уровень", "Тип", "S, м²", "h, м")
        # Контейнер для дерева + скроллбары (grid даёт «прилипшие» полосы)
        tree_fr_l = ttk.Frame(left)
        tree_fr_l.pack(fill="both", expand=True, padx=4, pady=4)
        tree_fr_l.rowconfigure(0, weight=1)
        tree_fr_l.columnconfigure(0, weight=1)
        self.tree_spaces = ttk.Treeview(tree_fr_l, columns=cols_l,
                                        show="headings", height=15,
                                        selectmode="extended")
        widths_l = {"№": 70, "Имя": 130, "Уровень": 90,
                    "Тип": 120, "S, м²": 60, "h, м": 50}
        for c in cols_l:
            self.tree_spaces.heading(c, text=c)
            self.tree_spaces.column(c, anchor="w", width=widths_l[c])
        vsb_l = tk.Scrollbar(tree_fr_l, orient="vertical", width=18,
                             command=self.tree_spaces.yview)
        hsb_l = tk.Scrollbar(tree_fr_l, orient="horizontal", width=18,
                             command=self.tree_spaces.xview)
        self.tree_spaces.configure(yscrollcommand=vsb_l.set,
                                   xscrollcommand=hsb_l.set)
        self.tree_spaces.grid(row=0, column=0, sticky="nsew")
        vsb_l.grid(row=0, column=1, sticky="ns")
        hsb_l.grid(row=1, column=0, sticky="ew")
        self.tree_spaces.bind("<<TreeviewSelect>>", self.on_space_select)
        self.tree_spaces.bind("<Double-1>", lambda e: self.edit_space_dialog())
        # Сортировка по клику на заголовок столбца (▲ asc / ▼ desc / сброс)
        self._snapshot_spaces_order = attach_sort(self.tree_spaces, cols_l)

        # ===== Правая панель: ограждения =====
        right = ttk.LabelFrame(paned, text="Ограждения выбранного помещения")
        paned.add(right, weight=2)

        toolbar_r = ttk.Frame(right)
        toolbar_r.pack(fill="x", padx=4, pady=4)
        ttk.Button(toolbar_r, text="➕ Добавить ограждение",
                   command=self.add_element_dialog).pack(side="left", padx=2)
        ttk.Button(toolbar_r, text="✏️ Изменить",
                   command=self.edit_element_dialog).pack(side="left", padx=2)
        ttk.Button(toolbar_r, text="🗑 Удалить",
                   command=self.delete_element).pack(side="left", padx=2)
        self.elem_info = ttk.Label(toolbar_r, text="", foreground="#555")
        self.elem_info.pack(side="left", padx=12)

        cols_r = ("Тип строки", "Категория", "Тип/семейство",
                  "Площадь, м²", "Толщ., мм", "U, Вт/м²К", "Ориент.", "Наруж.")
        tree_fr_r = ttk.Frame(right)
        tree_fr_r.pack(fill="both", expand=True, padx=4, pady=4)
        tree_fr_r.rowconfigure(0, weight=1)
        tree_fr_r.columnconfigure(0, weight=1)
        self.tree_elems = ttk.Treeview(tree_fr_r, columns=cols_r,
                                       show="headings", height=15,
                                       selectmode="browse")
        widths_r = {"Тип строки": 80, "Категория": 90, "Тип/семейство": 200,
                    "Площадь, м²": 80, "Толщ., мм": 70, "U, Вт/м²К": 80,
                    "Ориент.": 70, "Наруж.": 60}
        for c in cols_r:
            self.tree_elems.heading(c, text=c)
            self.tree_elems.column(c, anchor="w", width=widths_r[c])
        vsb_r = tk.Scrollbar(tree_fr_r, orient="vertical", width=18,
                             command=self.tree_elems.yview)
        hsb_r = tk.Scrollbar(tree_fr_r, orient="horizontal", width=18,
                             command=self.tree_elems.xview)
        self.tree_elems.configure(yscrollcommand=vsb_r.set,
                                  xscrollcommand=hsb_r.set)
        self.tree_elems.grid(row=0, column=0, sticky="nsew")
        vsb_r.grid(row=0, column=1, sticky="ns")
        hsb_r.grid(row=1, column=0, sticky="ew")
        self.tree_elems.bind("<Double-1>", lambda e: self.edit_element_dialog())
        # Сортировка по клику на заголовок столбца
        self._snapshot_elems_order = attach_sort(self.tree_elems, cols_r)

        # Подсказка внизу
        hint = ("Порядок работы:  1) Новый пустой проект  →  "
                "2) Добавьте помещения (➕ слева)  →  "
                "3) Для каждого помещения добавьте ограждения (➕ справа)  →  "
                "4) Переходите на вкладку «5. Расчёт» для запуска расчёта.")
        ttk.Label(self, text=hint, foreground="#555555", wraplength=1200,
                  justify="left").pack(anchor="w", padx=10, pady=6)

    def subscribe_events(self):
        self.project.subscribe("spaces_changed", self.refresh)
        self.project.subscribe("elements_changed", self.refresh_elements)
        self.project.subscribe("project_loaded", self.refresh)
        self.project.subscribe("data_loaded", self.refresh)

    # ----- Действия с проектом -----

    def new_empty_project(self):
        """Создаёт новый пустой проект."""
        if self.project.spaces:
            if not messagebox.askyesno(
                "Новый проект",
                "Текущий проект будет очищен. Продолжить?"):
                return
        # Диалог: имя проекта + город
        win = tk.Toplevel(self)
        win.title("Новый пустой проект")
        win.geometry("400x180")
        win.transient(self)
        win.grab_set()

        ttk.Label(win, text="Имя проекта:").grid(row=0, column=0, sticky="w",
                                                  padx=10, pady=8)
        name_var = tk.StringVar(value="Новый проект")
        ttk.Entry(win, textvariable=name_var, width=30).grid(row=0, column=1,
                                                              padx=10, pady=8)

        ttk.Label(win, text="Город:").grid(row=1, column=0, sticky="w",
                                            padx=10, pady=8)
        city_var = tk.StringVar(value="Ташкент")
        cities = sorted(CLIMATE_DB.keys())
        ttk.Combobox(win, textvariable=city_var, values=cities,
                     width=28).grid(row=1, column=1, padx=10, pady=8)

        def ok():
            self.project.new_empty_project(name_var.get().strip() or "Новый проект",
                                            city_var.get().strip() or "Ташкент")
            win.destroy()
            self.refresh()
            messagebox.showinfo("Готово", "Пустой проект создан.\n"
                                "Теперь добавьте помещения кнопкой ➕.")

        ttk.Button(win, text="Создать", command=ok).grid(row=2, column=0,
                                                          columnspan=2, pady=14)

    def open_project(self):
        """Открыть проект из JSON."""
        path = filedialog.askopenfilename(
            filetypes=[("Проект HVAC", "*.hvac.json"),
                       ("JSON", "*.json")])
        if not path:
            return
        try:
            from hvac.io_json import load_project
            load_project(self.project, path)
            self.refresh()
            messagebox.showinfo("OK", f"Проект загружен:\n{path}")
        except Exception as e:
            import traceback
            messagebox.showerror("Ошибка", f"{e}\n\n{traceback.format_exc()}")

    def save_project(self):
        """Сохранить проект в JSON (полная геометрия)."""
        if not self.project.spaces:
            messagebox.showwarning("Внимание", "Проект пуст.")
            return
        path = filedialog.asksaveasfilename(
            defaultextension=".hvac.json",
            filetypes=[("Проект HVAC", "*.hvac.json"), ("JSON", "*.json")],
            initialfile=f"{self.project.params.project_name}.hvac.json")
        if not path:
            return
        try:
            from hvac.io_json import save_project
            save_project(self.project, path, force_self_contained=True)
            messagebox.showinfo("OK", f"Проект сохранён:\n{path}")
        except Exception as e:
            messagebox.showerror("Ошибка", str(e))

    # ----- Помещения -----

    def refresh(self, **kwargs):
        """Обновляет дерево помещений (с учётом поиска)."""
        self._apply_filter()
        # Сбросим выделение элементов
        self.current_space_id = None
        for i in self.tree_elems.get_children():
            self.tree_elems.delete(i)
        self.elem_info.config(text="")
        # Запомнить исходный порядок для сброса сортировки
        self._snapshot_elems_order()

    def _apply_filter(self, *_):
        """Перезаливает tree_spaces, оставляя только подходящие под поиск.

        Поиск ищет подстроку (без учёта регистра) в склейке номера, имени,
        уровня и типа помещения. Пустой поиск показывает все помещения.
        """
        q = ""
        if hasattr(self, "search_var"):
            q = self.search_var.get().strip().lower()
        self.tree_spaces.delete(*self.tree_spaces.get_children())
        n_total = len(self.project.spaces)
        n_shown = 0
        for sp in self.project.spaces:
            if q:
                haystack = (f"{sp.number} {sp.name} {sp.level} "
                            f"{sp.room_type}").lower()
                if q not in haystack:
                    continue
            self.tree_spaces.insert("", "end", iid=sp.space_id, values=(
                sp.number, sp.name, sp.level, sp.room_type,
                round(sp.area_m2, 1), round(sp.height_m, 2)))
            n_shown += 1
        n_el = len(self.project.elements)
        base = (f"Проект «{self.project.params.project_name}» — "
                f"город {self.project.params.city} "
                f"({self.project.params.t_out_heating:+.0f}/"
                f"{self.project.params.t_out_cooling:+.0f}°C).  ")
        if q and n_shown < n_total:
            self.info_var.set(
                base + f"Показано {n_shown} из {n_total} "
                f"(фильтр: «{q}»). Ограждений: {n_el}.")
        else:
            self.info_var.set(
                base + f"Помещений: {n_total}, ограждений: {n_el}.")
        # Запомнить исходный порядок для сброса сортировки
        self._snapshot_spaces_order()

    def refresh_elements(self, **kwargs):
        """Обновляет дерево ограждений для текущего помещения."""
        if not self.current_space_id:
            return
        for i in self.tree_elems.get_children():
            self.tree_elems.delete(i)
        elems = self.project.get_room_elements(self.current_space_id)
        for el in elems:
            type_full = f"{el.family} / {el.type_name}" if el.family else el.type_name
            self.tree_elems.insert("", "end", iid=el.element_id, values=(
                "проём" if el.row_type == "opening" else "огражд.",
                el.category, type_full,
                round(max(el.net_area_m2, el.approx_area_m2, el.element_area_m2), 2),
                round(el.thickness_mm, 0),
                round(el.u_value, 3) if el.u_value > 0 else "?",
                ORIENTATION_LABELS.get(el.orientation, el.orientation or "—"),
                "✓" if el.is_exterior else "—"))
        n = len(elems)
        sp = self.project.get_space(self.current_space_id)
        if sp:
            self.elem_info.config(
                text=f"Помещение: {sp.number} {sp.name}   |   ограждений: {n}")
        # Запомнить исходный порядок для сброса сортировки
        self._snapshot_elems_order()

    def on_space_select(self, event=None):
        sel = self.tree_spaces.selection()
        if len(sel) == 1:
            self.current_space_id = sel[0]
            self.refresh_elements()
        else:
            # 0 или 2+ — правая панель не привязана к конкретной комнате
            self.current_space_id = None
            self.tree_elems.delete(*self.tree_elems.get_children())
            if sel:
                # Сводка по выделенным помещениям
                spaces = [self.project.get_space(s) for s in sel]
                spaces = [s for s in spaces if s]
                total_s = sum(s.area_m2 for s in spaces)
                avg_s = total_s / len(spaces) if spaces else 0
                self.elem_info.config(
                    text=f"Выделено помещений: {len(spaces)}   |   "
                         f"общая S = {total_s:.1f} м², ср. {avg_s:.1f} м²   |   "
                         f"✏️ Изменить → массовое редактирование, "
                         f"🗑 Удалить → массовое удаление")
            else:
                self.elem_info.config(text="")

    def add_space_dialog(self):
        """Диалог добавления нового помещения."""
        self._space_dialog(None)

    def edit_space_dialog(self):
        sel = self.tree_spaces.selection()
        if not sel:
            messagebox.showinfo("Информация", "Выберите помещение из списка.")
            return
        if len(sel) == 1:
            self._space_dialog(sel[0])
        else:
            self._bulk_edit_dialog(sel)

    def _bulk_edit_dialog(self, space_ids):
        """Массовое редактирование нескольких помещений.

        Принцип: у каждого поля есть галочка «Применить». Применяются только
        отмеченные поля — остальные у выбранных помещений остаются как были.
        """
        win = tk.Toplevel(self)
        win.title(f"Массовое редактирование — {len(space_ids)} помещ.")
        win.geometry("520x540")
        win.transient(self)
        win.grab_set()

        ttk.Label(win, text=f"Изменение применится к {len(space_ids)} "
                            f"выделенным помещениям.",
                  foreground="#555").grid(row=0, column=0, columnspan=3,
                                          padx=10, pady=(10, 4), sticky="w")
        ttk.Label(win, text="Отметьте галочкой поля, которые нужно изменить.",
                  foreground="#555").grid(row=1, column=0, columnspan=3,
                                          padx=10, pady=(0, 10), sticky="w")

        # Заголовок колонок
        ttk.Label(win, text="✓", font=("Segoe UI", 9, "bold")).grid(
            row=2, column=0, padx=(10, 2))
        ttk.Label(win, text="Поле", font=("Segoe UI", 9, "bold")).grid(
            row=2, column=1, sticky="w", padx=4)
        ttk.Label(win, text="Новое значение",
                  font=("Segoe UI", 9, "bold")).grid(
            row=2, column=2, sticky="w", padx=4)

        # Список редактируемых полей: (метка, имя_поля, виджет, default)
        # widget: "entry_float" | "combo_room_type" | "checkbox"
        rows = [
            ("Тип помещения", "room_type", "combo_room_type", "Офис"),
            ("Уровень / этаж", "level", "entry_str", "1 этаж"),
            ("Tв зимой, °C", "t_in_heat", "entry_float", "20"),
            ("Tв летом, °C", "t_in_cool", "entry_float", "24"),
            ("Освещение, Вт/м²", "lighting_w_m2", "entry_float", "10"),
            ("Оборудование, Вт/м²", "equipment_w_m2", "entry_float", "8"),
            ("ACH инфильтрация, 1/ч", "ach_inf", "entry_float", "0.5"),
            ("Угловое помещение", "is_corner", "checkbox", False),
            ("Пол по грунту", "has_floor_to_ground", "checkbox", False),
            ("Имеет покрытие (верх. этаж)", "has_roof", "checkbox", False),
        ]
        apply_vars = {}  # field -> BooleanVar (галочка «применить»)
        value_vars = {}  # field -> StringVar/BooleanVar (значение)

        for i, (lbl, key, widget, default) in enumerate(rows):
            r = i + 3
            apply_vars[key] = tk.BooleanVar(value=False)
            ttk.Checkbutton(win, variable=apply_vars[key]).grid(
                row=r, column=0, padx=(10, 2))
            ttk.Label(win, text=lbl).grid(row=r, column=1, sticky="w",
                                          padx=4, pady=3)
            if widget == "combo_room_type":
                v = tk.StringVar(value=default)
                ttk.Combobox(win, textvariable=v,
                             values=get_all_room_types(),
                             state="readonly", width=28).grid(
                    row=r, column=2, sticky="w", padx=4)
                value_vars[key] = v
            elif widget == "checkbox":
                v = tk.BooleanVar(value=default)
                ttk.Checkbutton(win, variable=v,
                                text="(включено)").grid(
                    row=r, column=2, sticky="w", padx=4)
                value_vars[key] = v
            else:  # entry_float, entry_str
                v = tk.StringVar(value=str(default))
                ttk.Entry(win, textvariable=v, width=28).grid(
                    row=r, column=2, sticky="w", padx=4)
                value_vars[key] = v

        def apply_changes():
            # Собираем словарь полей для update_space
            updates = {}
            for key, av in apply_vars.items():
                if not av.get():
                    continue
                vv = value_vars[key]
                widget_kind = next(w for lbl, k, w, d in rows if k == key)
                try:
                    if widget_kind == "entry_float":
                        updates[key] = float(vv.get().replace(",", "."))
                    elif widget_kind == "checkbox":
                        updates[key] = bool(vv.get())
                        # has_roof и is_top_floor синхронизируем
                        if key == "has_roof":
                            updates["is_top_floor"] = bool(vv.get())
                    else:  # entry_str, combo_room_type
                        updates[key] = vv.get().strip()
                except ValueError as e:
                    messagebox.showerror("Ошибка",
                                         f"Поле «{key}»: введите корректное число.\n{e}")
                    return

            if not updates:
                messagebox.showinfo("Информация",
                                    "Не отмечено ни одного поля для изменения.")
                return

            # Подтверждение
            field_list = "\n".join(f"  • {k} = {v}" for k, v in updates.items())
            if not messagebox.askyesno(
                "Подтверждение",
                f"Применить к {len(space_ids)} помещениям:\n\n"
                f"{field_list}"):
                return

            for sid in space_ids:
                self.project.update_space(sid, **updates)
            win.destroy()
            self.refresh()

        btn_fr = ttk.Frame(win)
        btn_fr.grid(row=len(rows) + 3, column=0, columnspan=3, pady=16)
        ttk.Button(btn_fr, text="Применить",
                   command=apply_changes).pack(side="left", padx=4)
        ttk.Button(btn_fr, text="Отмена",
                   command=win.destroy).pack(side="left", padx=4)

    def _space_dialog(self, space_id):
        """Универсальный диалог: создание (space_id=None) или редактирование."""
        sp = self.project.get_space(space_id) if space_id else None
        win = tk.Toplevel(self)
        win.title("Редактирование помещения" if sp else "Новое помещение")
        win.geometry("420x500")
        win.transient(self)
        win.grab_set()

        # Поля
        fields = [
            ("Номер", "number", sp.number if sp else ""),
            ("Имя", "name", sp.name if sp else ""),
            ("Уровень / этаж", "level", sp.level if sp else "1 этаж"),
            ("Площадь, м²", "area_m2", str(sp.area_m2) if sp else "20"),
            ("Высота, м", "height_m", str(sp.height_m) if sp else "3.0"),
        ]
        vars_ = {}
        for i, (lbl, key, val) in enumerate(fields):
            ttk.Label(win, text=lbl).grid(row=i, column=0, sticky="w",
                                          padx=10, pady=6)
            v = tk.StringVar(value=val)
            ttk.Entry(win, textvariable=v, width=30).grid(row=i, column=1,
                                                          padx=10, pady=6)
            vars_[key] = v

        # Тип помещения
        i = len(fields)
        ttk.Label(win, text="Тип помещения").grid(row=i, column=0, sticky="w",
                                                   padx=10, pady=6)
        type_var = tk.StringVar(value=sp.room_type if sp else "Офис")
        ttk.Combobox(win, textvariable=type_var,
                     values=get_all_room_types(),
                     state="readonly", width=27).grid(row=i, column=1,
                                                       padx=10, pady=6)

        # Чекбоксы
        i += 1
        var_corner = tk.BooleanVar(value=sp.is_corner if sp else False)
        ttk.Checkbutton(win, text="Угловое помещение",
                        variable=var_corner).grid(row=i, column=0,
                                                   columnspan=2,
                                                   sticky="w", padx=10, pady=4)
        i += 1
        var_floor = tk.BooleanVar(value=sp.has_floor_to_ground if sp else False)
        ttk.Checkbutton(win, text="Пол по грунту / над неотап. подвалом",
                        variable=var_floor).grid(row=i, column=0,
                                                  columnspan=2,
                                                  sticky="w", padx=10, pady=4)
        i += 1
        var_roof = tk.BooleanVar(value=(sp.has_roof or sp.is_top_floor) if sp else False)
        ttk.Checkbutton(win, text="Имеет покрытие (верхний этаж)",
                        variable=var_roof).grid(row=i, column=0,
                                                 columnspan=2,
                                                 sticky="w", padx=10, pady=4)

        def save():
            try:
                area = float(vars_["area_m2"].get().replace(",", "."))
                height = float(vars_["height_m"].get().replace(",", "."))
                if area <= 0 or height <= 0:
                    raise ValueError("Площадь и высота должны быть > 0")
            except ValueError as e:
                messagebox.showerror("Ошибка", f"Введите корректные числа.\n{e}")
                return

            number = vars_["number"].get().strip() or "—"
            name = vars_["name"].get().strip() or "Без имени"
            level = vars_["level"].get().strip() or "1 этаж"

            if sp is None:
                # Создаём новое
                new_sp = self.project.add_space(
                    number=number, name=name, level=level,
                    area_m2=area, height_m=height,
                    room_type=type_var.get())
                new_sp.is_corner = var_corner.get()
                new_sp.has_floor_to_ground = var_floor.get()
                new_sp.has_roof = var_roof.get()
                new_sp.is_top_floor = var_roof.get()
            else:
                # Изменяем
                self.project.update_space(
                    sp.space_id,
                    number=number, name=name, level=level,
                    area_m2=area, height_m=height,
                    room_type=type_var.get(),
                    is_corner=var_corner.get(),
                    has_floor_to_ground=var_floor.get(),
                    has_roof=var_roof.get(),
                    is_top_floor=var_roof.get())
            win.destroy()
            self.refresh()

        ttk.Button(win, text="Сохранить", command=save).grid(
            row=i + 1, column=0, columnspan=2, pady=14)

    def delete_space(self):
        sel = self.tree_spaces.selection()
        if not sel:
            messagebox.showinfo("Информация", "Выберите помещение.")
            return
        if len(sel) == 1:
            sp = self.project.get_space(sel[0])
            if not sp:
                return
            n_el = len(self.project.get_room_elements(sp.space_id))
            msg = f"Удалить помещение «{sp.number} {sp.name}»?"
            if n_el:
                msg += f"\n\nВместе с ним будут удалены {n_el} ограждений."
            if messagebox.askyesno("Удалить?", msg):
                self.project.remove_space(sp.space_id)
                self.refresh()
        else:
            # Массовое удаление
            n_el_total = sum(len(self.project.get_room_elements(sid))
                             for sid in sel)
            msg = f"Удалить {len(sel)} выделенных помещений?"
            if n_el_total:
                msg += (f"\n\nВместе с ними будут удалены "
                        f"{n_el_total} ограждений.")
            msg += "\n\nДействие необратимо."
            if messagebox.askyesno("Массовое удаление", msg):
                for sid in sel:
                    self.project.remove_space(sid)
                self.refresh()

    # ----- Ограждения -----

    def add_element_dialog(self):
        """Диалог добавления нового ограждения."""
        if not self.current_space_id:
            messagebox.showinfo("Информация",
                                 "Сначала выберите помещение в списке слева.")
            return
        self._element_dialog(None)

    def edit_element_dialog(self):
        sel = self.tree_elems.selection()
        if not sel:
            messagebox.showinfo("Информация", "Выберите ограждение.")
            return
        self._element_dialog(sel[0])

    def _element_dialog(self, element_id):
        """Универсальный диалог добавления/редактирования ограждения."""
        el = None
        if element_id:
            el = next((e for e in self.project.elements
                       if e.element_id == element_id), None)
            if el is None:
                return

        win = tk.Toplevel(self)
        win.title("Редактирование ограждения" if el else "Новое ограждение")
        win.geometry("500x540")
        win.transient(self)
        win.grab_set()

        # Шаблон конструкции
        ttk.Label(win, text="Шаблон конструкции:",
                  font=("Segoe UI", 9, "bold")).grid(row=0, column=0,
                                                     sticky="w", padx=10, pady=(10, 2))
        preset_var = tk.StringVar(value="(выберите из списка)")
        preset_cb = ttk.Combobox(win, textvariable=preset_var,
                                  values=["(выберите из списка)"] + list(ELEMENT_PRESETS.keys()),
                                  state="readonly", width=50)
        preset_cb.grid(row=1, column=0, columnspan=2, sticky="w",
                        padx=10, pady=(0, 10))

        # Поля
        ttk.Separator(win, orient="horizontal").grid(row=2, column=0,
                                                      columnspan=2, sticky="ew",
                                                      padx=10, pady=4)

        fields = [
            ("Тип строки",        "row_type",    el.row_type if el else "external_wall"),
            ("Категория",         "category",    el.category if el else "Стены"),
            ("Семейство",         "family",      el.family if el else ""),
            ("Тип / название",    "type_name",   el.type_name if el else ""),
            ("Площадь, м²",       "area_m2",     str(round(max(el.approx_area_m2,
                                                                el.element_area_m2), 2)) if el else "10"),
            ("Толщина, мм",       "thickness",   str(el.thickness_mm) if el else "200"),
            ("U-значение, Вт/м²К", "u_value",    str(el.u_value) if el else "0.35"),
        ]
        vars_ = {}
        for i, (lbl, key, val) in enumerate(fields, start=3):
            ttk.Label(win, text=lbl).grid(row=i, column=0, sticky="w",
                                          padx=10, pady=4)
            v = tk.StringVar(value=val)
            if key == "row_type":
                ttk.Combobox(win, textvariable=v,
                             values=["external_wall", "opening"],
                             state="readonly", width=30).grid(row=i, column=1,
                                                               padx=10, pady=4)
            else:
                ttk.Entry(win, textvariable=v, width=33).grid(row=i, column=1,
                                                               padx=10, pady=4)
            vars_[key] = v

        # Ориентация
        i = len(fields) + 3
        ttk.Label(win, text="Ориентация").grid(row=i, column=0, sticky="w",
                                                padx=10, pady=4)
        orient_var = tk.StringVar(value=el.orientation if el else "")
        ttk.Combobox(win, textvariable=orient_var,
                     values=list(ORIENTATION_LABELS.keys()),
                     state="readonly", width=30).grid(row=i, column=1,
                                                       padx=10, pady=4)

        # Наружное
        i += 1
        var_ext = tk.BooleanVar(value=el.is_exterior if el else True)
        ttk.Checkbutton(win, text="Граничит с улицей (учитывать в расчёте)",
                        variable=var_ext).grid(row=i, column=0,
                                                columnspan=2, sticky="w",
                                                padx=10, pady=6)

        # SHGC (только для проёмов)
        i += 1
        ttk.Label(win, text="SHGC (для окон/витражей)").grid(row=i, column=0,
                                                              sticky="w",
                                                              padx=10, pady=4)
        shgc_var = tk.StringVar(value="0.6" if el is None or
                                el.row_type != "opening" else "0.65")
        ttk.Entry(win, textvariable=shgc_var, width=33).grid(row=i, column=1,
                                                              padx=10, pady=4)

        def on_preset(*_):
            choice = preset_var.get()
            if choice in ELEMENT_PRESETS:
                row_type, cat, fam, type_n, thk, u, shgc = ELEMENT_PRESETS[choice]
                vars_["row_type"].set(row_type)
                vars_["category"].set(cat)
                vars_["family"].set(fam)
                vars_["type_name"].set(type_n)
                vars_["thickness"].set(str(thk))
                vars_["u_value"].set(str(u))
                shgc_var.set(str(shgc))

        preset_var.trace_add("write", on_preset)

        def save():
            try:
                area = float(vars_["area_m2"].get().replace(",", "."))
                thk = float(vars_["thickness"].get().replace(",", "."))
                u_val = float(vars_["u_value"].get().replace(",", "."))
                shgc = float(shgc_var.get().replace(",", ".") or "0.6")
            except ValueError:
                messagebox.showerror("Ошибка",
                                      "Введите корректные числа для площади, "
                                      "толщины, U и SHGC.")
                return

            if el is None:
                # Создаём новый
                self.project.add_element(
                    space_id=self.current_space_id,
                    row_type=vars_["row_type"].get(),
                    category=vars_["category"].get(),
                    family=vars_["family"].get(),
                    type_name=vars_["type_name"].get(),
                    area_m2=area,
                    thickness_mm=thk,
                    u_value=u_val,
                    shgc=shgc,
                    is_exterior=var_ext.get(),
                    orientation=orient_var.get(),
                )
            else:
                # Обновляем существующий
                self.project.update_element(
                    el.element_id,
                    row_type=vars_["row_type"].get(),
                    category=vars_["category"].get(),
                    family=vars_["family"].get(),
                    type_name=vars_["type_name"].get(),
                    approx_area_m2=area,
                    element_area_m2=area,
                    thickness_mm=thk,
                    u_value=u_val,
                    is_exterior=var_ext.get(),
                    orientation=orient_var.get(),
                )
                # Обновим SHGC в каталоге конструкций (если это окно)
                con_key = el.construction_key
                if con_key and con_key in self.project.constructions:
                    self.project.constructions[con_key].u_value = u_val
                    if vars_["category"].get() in ("Окна", "Витраж", "Витражи"):
                        self.project.constructions[con_key].shgc = shgc

            win.destroy()
            self.refresh_elements()
            self.refresh()  # обновим счётчик

        ttk.Button(win, text="Сохранить", command=save).grid(
            row=i + 1, column=0, columnspan=2, pady=14)

    def delete_element(self):
        sel = self.tree_elems.selection()
        if not sel:
            messagebox.showinfo("Информация", "Выберите ограждение.")
            return
        if messagebox.askyesno("Удалить?",
                                f"Удалить ограждение «{sel[0]}»?"):
            self.project.remove_element(sel[0])
            self.refresh_elements()
            self.refresh()
