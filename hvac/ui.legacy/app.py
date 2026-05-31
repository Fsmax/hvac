# -*- coding: utf-8 -*-
"""Главное окно приложения. Собирает вкладки из TABS_REGISTRY."""

from __future__ import annotations
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import traceback

from hvac.project import HVACProject
from hvac.io_json import save_project, load_project
from hvac.io_revit import export_results_for_revit
from hvac.ui.tabs import TABS_REGISTRY
from hvac.ui.extensions_tab import ExtensionsTab
from hvac.ui.building_tab import BuildingTab
from hvac.ui.room_equipment_tab import RoomEquipmentTab


# Расширенный реестр вкладок:
# - BuildingTab — первая (ручной ввод проекта без Revit, v3.8)
# - TABS_REGISTRY — стандартные вкладки v3.7 (1. Данные, ..., 10. Графики)
# - RoomEquipmentTab — назначение конечного оборудования в помещениях (v3.8)
# - ExtensionsTab — расширения v3.7 (ГВС, энергопаспорт, точка росы, ...)
EXTENDED_TABS_REGISTRY = (
    [BuildingTab] + TABS_REGISTRY + [RoomEquipmentTab, ExtensionsTab]
)


class HVACApp:
    """Главное приложение Tkinter."""

    def __init__(self):
        self.project = HVACProject()
        self.root = tk.Tk()
        self.root.title(
            "HVAC Calculator v3.7 — расчёт ОВиК + ГВС + энергопаспорт (Revit)"
        )
        self.root.geometry("1320x820")

        style = ttk.Style()
        try:
            style.theme_use("clam")
        except Exception:
            pass
        style.configure("Treeview", rowheight=22)
        style.configure("Treeview.Heading", font=("Segoe UI", 9, "bold"))

        self._build_menu()
        self._build_tabs()

    def _build_menu(self):
        menubar = tk.Menu(self.root)
        self.root.config(menu=menubar)
        filemenu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="Файл", menu=filemenu)
        filemenu.add_command(label="🆕 Новый пустой проект…",
                             command=self.menu_new_empty)
        filemenu.add_separator()
        filemenu.add_command(label="Открыть проект…", command=self.menu_open)
        filemenu.add_command(label="Сохранить проект…", command=self.menu_save)
        filemenu.add_command(label="Сохранить проект КАК самодостаточный…",
                             command=self.menu_save_self_contained)
        filemenu.add_separator()
        filemenu.add_command(label="Экспорт результатов для Revit (CSV)…",
                             command=self.menu_export_revit)
        filemenu.add_command(label="Экспорт в Excel (полный отчёт)…",
                             command=self.menu_export_excel)
        filemenu.add_command(label="📊 Экспорт сводной таблицы оборудования…",
                             command=self.menu_export_equipment)
        filemenu.add_command(label="Экспорт в PDF (пояснит. записка)…",
                             command=self.menu_export_pdf)
        filemenu.add_separator()
        filemenu.add_command(label="Выход", command=self.root.quit)

    def _build_tabs(self):
        notebook = ttk.Notebook(self.root)
        notebook.pack(fill="both", expand=True, padx=6, pady=6)
        self.tabs = []
        for tab_cls in EXTENDED_TABS_REGISTRY:
            tab = tab_cls(notebook, self.project, self)
            notebook.add(tab, text=tab_cls.title)
            self.tabs.append(tab)

    # ---------- меню ----------
    def menu_new_empty(self):
        """Создать новый пустой проект (без Revit)."""
        if self.project.spaces:
            if not messagebox.askyesno(
                    "Новый проект",
                    "Текущий проект будет очищен.\nПродолжить?"):
                return
        self.project.new_empty_project()
        messagebox.showinfo(
            "Готово",
            "Создан пустой проект.\n\n"
            "Перейдите на вкладку «0. Здание (ручной ввод)»,\n"
            "чтобы добавить помещения и ограждения.")

    def menu_save_self_contained(self):
        """Сохранение в полностью самодостаточный JSON (без CSV)."""
        if not self.project.spaces:
            messagebox.showwarning("Нет данных",
                                    "Проект пуст. Нечего сохранять.")
            return
        path = filedialog.asksaveasfilename(
            defaultextension=".hvac.json",
            filetypes=[("Проект HVAC (полный)", "*.hvac.json")],
            initialfile=f"{self.project.params.project_name}_полный.hvac.json")
        if not path:
            return
        try:
            save_project(self.project, path, force_self_contained=True)
            messagebox.showinfo(
                "OK",
                f"Сохранён полный проект:\n{path}\n\n"
                "Этот файл содержит ВСЮ геометрию и оборудование — "
                "его можно открыть на любом компьютере без CSV-файлов.")
        except Exception as e:
            messagebox.showerror("Ошибка", str(e))

    def menu_export_equipment(self):
        """Экспорт сводной таблицы оборудования."""
        if not self.project.spaces:
            messagebox.showwarning("Нет данных", "Проект пуст.")
            return
        path = filedialog.asksaveasfilename(
            defaultextension=".xlsx", filetypes=[("Excel", "*.xlsx")],
            initialfile=f"Оборудование_{self.project.params.project_name}.xlsx")
        if not path:
            return
        try:
            from hvac.io_excel_equipment import export_equipment_summary
            export_equipment_summary(self.project, path)
            messagebox.showinfo(
                "Готово",
                f"Сводная таблица сохранена:\n{path}\n\n"
                "Содержит листы:\n"
                "  • Сводная по помещениям (главная таблица)\n"
                "  • Радиаторы и фанкойлы (спецификация)\n"
                "  • Охлаждение (спецификация)\n"
                "  • Воздухораспределители\n"
                "  • По системам (агрегация)")
        except Exception as e:
            messagebox.showerror("Ошибка", f"{e}\n{traceback.format_exc()}")

    def menu_save(self):
        path = filedialog.asksaveasfilename(
            defaultextension=".hvac.json",
            filetypes=[("Проект HVAC", "*.hvac.json"), ("JSON", "*.json")])
        if not path:
            return
        try:
            save_project(self.project, path)
            messagebox.showinfo("OK", f"Проект сохранён:\n{path}")
        except Exception as e:
            messagebox.showerror("Ошибка", str(e))

    def menu_open(self):
        path = filedialog.askopenfilename(
            filetypes=[("Проект HVAC", "*.hvac.json"), ("JSON", "*.json")])
        if not path:
            return
        try:
            load_project(self.project, path)
            messagebox.showinfo("OK", f"Проект загружен:\n{path}")
        except Exception as e:
            messagebox.showerror("Ошибка", f"{e}\n\n{traceback.format_exc()}")

    def menu_export_revit(self):
        if not self.project.spaces:
            messagebox.showwarning("Нет данных", "Сначала выполните расчёт.")
            return
        if self.project.spaces[0].heat_loss_w == 0 and self.project.spaces[0].heat_gain_w == 0:
            messagebox.showwarning("Нет результатов",
                                   "Сначала запустите расчёт во вкладке 5.")
            return
        path = filedialog.asksaveasfilename(
            defaultextension=".csv", filetypes=[("CSV для Revit", "*.csv")],
            initialfile="results_for_revit.csv")
        if not path:
            return
        try:
            export_results_for_revit(self.project, path)
            messagebox.showinfo(
                "Готово",
                f"CSV сохранён:\n{path}\n\n"
                "В Revit-Dynamo:\n"
                "  • запустите скрипт revit_dynamo_apply_results.py\n"
                "  • IN[0] = путь к этому CSV\n"
                "  • IN[1] = имя параметра Heating Load\n"
                "  • IN[2] = имя параметра Cooling Load")
        except Exception as e:
            messagebox.showerror("Ошибка", str(e))

    def menu_export_excel(self):
        """Экспорт результатов в Excel (14 листов)."""
        if not self.project.spaces:
            messagebox.showwarning("Нет данных", "Сначала загрузите CSV.")
            return
        path = filedialog.asksaveasfilename(
            defaultextension=".xlsx", filetypes=[("Excel", "*.xlsx")],
            initialfile=f"HVAC_{self.project.params.project_name}.xlsx")
        if not path:
            return
        try:
            from hvac.io_excel import export_to_excel
            export_to_excel(self.project, path)
            messagebox.showinfo("Готово", f"Excel сохранён:\n{path}")
        except Exception as e:
            messagebox.showerror("Ошибка",
                                  f"{e}\n{traceback.format_exc()}")

    def menu_export_pdf(self):
        """Экспорт сводного PDF-отчёта «Пояснительная записка»."""
        if not self.project.spaces:
            messagebox.showwarning("Нет данных", "Сначала загрузите CSV.")
            return
        path = filedialog.asksaveasfilename(
            defaultextension=".pdf", filetypes=[("PDF", "*.pdf")],
            initialfile=f"Отчёт_{self.project.params.project_name}.pdf")
        if not path:
            return
        try:
            from hvac.io_pdf import export_to_pdf
            export_to_pdf(self.project, path)
            messagebox.showinfo("Готово",
                                 f"PDF сохранён:\n{path}\n\n"
                                 "Документ содержит до 12 разделов "
                                 "(только те, по которым есть данные).")
        except Exception as e:
            messagebox.showerror("Ошибка PDF",
                                  f"{e}\n{traceback.format_exc()}")

    def run(self):
        self.root.mainloop()


def run_gui():
    """Точка входа GUI."""
    HVACApp().run()
