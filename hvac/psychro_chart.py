# -*- coding: utf-8 -*-
"""Построение i-d диаграммы влажного воздуха (диаграмма Молье).

Координаты:
    X — влагосодержание W, г/кг сухого воздуха
    Y — энтальпия H, кДж/кг сухого воздуха

Сетка:
    • Изотермы T = −20…60°C через 5°C (косые линии H ≈ 1.006·T + W·(2501+1.86·T))
    • Изовлажности W = 0…25 г/кг через 1 г/кг (вертикальные)
    • Изоэнтальпии H = −10…120 кДж/кг (горизонтальные, по факту параллельные T_db)
    • Кривые относительной влажности RH = 10/20/.../100%

Используется для:
    1. UI-таб «i-d диаграмма» в EngineeringPanel
    2. PDF-отчёта (раздел «Психрометрика AHU»)

API
---
    fig = build_id_chart(processes=None, mode="winter",
                          t_range=(-20, 60), w_range=(0, 25))
    save_id_chart(fig, path)
    add_process_to_chart(ax, process, label="Зима")

Зависит от matplotlib; если не установлен — функции бросают ImportError.
"""

from __future__ import annotations

from typing import Iterable, List, Optional, Sequence, Tuple, TYPE_CHECKING

from hvac.psychro import (
    AirState, P_ATM, enthalpy, humidity_ratio_from_rh,
    saturation_pressure_pa, to_g_kg,
)

if TYPE_CHECKING:
    from hvac.ahu_process import AHUProcess


# Цвета для точек процесса по режиму
MODE_COLORS = {
    "winter":       "#1F77B4",   # синий
    "summer":       "#D62728",   # красный
    "transitional": "#2CA02C",   # зелёный
}

# Цвета сетки
COLOR_ISOTHERM = "#888888"
COLOR_RH = "#A33"
COLOR_RH_SAT = "#700"
COLOR_W = "#CCCCCC"
COLOR_H = "#BBBBBB"


def _require_matplotlib():
    try:
        import matplotlib
        matplotlib.use("Agg")
        from matplotlib import pyplot as plt
        return matplotlib, plt
    except ImportError as e:
        raise ImportError(
            "Для построения i-d диаграммы нужен matplotlib. "
            "Установите: pip install matplotlib"
        ) from e


def build_id_chart(
    processes: Optional[Iterable["AHUProcess"]] = None,
    *,
    t_range: Tuple[float, float] = (-20.0, 50.0),
    w_range: Tuple[float, float] = (0.0, 25.0),
    rh_lines: Sequence[float] = (0.10, 0.20, 0.40, 0.60, 0.80, 1.00),
    title: str = "i-d диаграмма влажного воздуха",
):
    """Создаёт matplotlib Figure с диаграммой Молье.

    Параметры
    ---------
    processes : итерируемое из AHUProcess. Если задано, точки процесса
                наносятся на диаграмму со стрелками между ними.
    t_range   : диапазон температур по оси (°C). Влияет на сетку.
    w_range   : диапазон W по оси (г/кг). Влияет на масштаб.
    rh_lines  : уровни RH для кривых (0..1).
    title     : заголовок графика.

    Возвращает matplotlib.figure.Figure.
    """
    _, plt = _require_matplotlib()
    fig, ax = plt.subplots(figsize=(10.0, 7.5))

    w_min_g, w_max_g = w_range
    t_min, t_max = t_range

    # ===== Сетка изовлажности (вертикали W = const) =====
    for w_g in range(int(w_min_g), int(w_max_g) + 1):
        ax.axvline(x=w_g, color=COLOR_W, linewidth=0.3, zorder=1)

    # ===== Изотермы T = const =====
    for t in range(int(t_min), int(t_max) + 1, 5):
        ws_g = []
        hs = []
        for w_g in [w_min_g + i * (w_max_g - w_min_g) / 50
                    for i in range(51)]:
            W = w_g / 1000.0
            # Проверка: точка не должна быть выше кривой насыщения
            W_sat = humidity_ratio_from_rh(t, 1.0)
            if W > W_sat * 1.02:
                continue
            ws_g.append(w_g)
            hs.append(enthalpy(t, W))
        if ws_g:
            ax.plot(ws_g, hs, color=COLOR_ISOTHERM, linewidth=0.5,
                     linestyle="-", alpha=0.6, zorder=2)
            # Подпись изотермы у правого края
            if hs:
                ax.annotate(f"{t}°C",
                            xy=(ws_g[-1], hs[-1]),
                            xytext=(2, 0), textcoords="offset points",
                            fontsize=7, color=COLOR_ISOTHERM,
                            verticalalignment="center")

    # ===== Кривые постоянной RH =====
    for rh in rh_lines:
        ws_g = []
        hs = []
        for t in [t_min + i * (t_max - t_min) / 200 for i in range(201)]:
            W = humidity_ratio_from_rh(t, rh)
            w_g = to_g_kg(W)
            if w_g > w_max_g:
                continue
            ws_g.append(w_g)
            hs.append(enthalpy(t, W))
        if not ws_g:
            continue
        is_sat = rh >= 0.999
        color = COLOR_RH_SAT if is_sat else COLOR_RH
        lw = 1.5 if is_sat else 0.7
        ax.plot(ws_g, hs, color=color, linewidth=lw, alpha=0.75, zorder=3)
        # Подпись в середине дуги
        mid = len(ws_g) // 2
        label = f"φ={int(rh*100)}%" if not is_sat else "φ=100%"
        ax.annotate(label, xy=(ws_g[mid], hs[mid]),
                    xytext=(2, 2), textcoords="offset points",
                    fontsize=7, color=color, alpha=0.9)

    # ===== Точки процесса =====
    if processes:
        for proc in processes:
            add_process_to_chart(ax, proc)

    # Оси
    ax.set_xlim(w_range)
    h_min = enthalpy(t_min, 0.0) - 5
    h_max = enthalpy(t_max, w_max_g / 1000.0) + 5
    ax.set_ylim(h_min, h_max)
    ax.set_xlabel("Влагосодержание W, г/кг сухого воздуха")
    ax.set_ylabel("Удельная энтальпия H, кДж/кг сухого воздуха")
    ax.set_title(title, fontsize=11)
    ax.grid(False)

    fig.tight_layout()
    return fig


# Заказанный порядок прохождения точек процесса
_PROCESS_POINT_ORDER = [
    "outdoor", "after_recovery", "after_mix",
    "after_cooler", "after_heater", "after_postheat",
    "after_humid", "supply",
]


def add_process_to_chart(ax, process: "AHUProcess",
                          *, label_prefix: str = "",
                          color: Optional[str] = None) -> None:
    """Наносит точки процесса AHU на существующий ax."""
    pts = process.points
    color = color or MODE_COLORS.get(process.mode, "#222222")
    mode_label = {"winter": "Зима", "summer": "Лето",
                  "transitional": "Межсезонье"}.get(process.mode, process.mode)
    name_label = (process.ahu_name + " — "
                   if process.ahu_name else "")
    prefix = label_prefix or f"{name_label}{mode_label}"

    # Упорядочиваем точки по ходу воздуха
    ordered_keys: List[str] = [k for k in _PROCESS_POINT_ORDER if k in pts]
    # Точки, которых нет в _PROCESS_POINT_ORDER, добавляем в конец (extract и т.п.)
    for k in pts:
        if k not in ordered_keys and k != "extract":
            ordered_keys.append(k)

    xs = []
    ys = []
    for k in ordered_keys:
        st = pts[k]
        x = st.w_g_kg
        y = st.h_kj_kg
        xs.append(x); ys.append(y)
        ax.plot(x, y, marker="o", markersize=5, color=color, zorder=5)
        ax.annotate(
            f"{prefix}: {k}", xy=(x, y),
            xytext=(6, 6), textcoords="offset points",
            fontsize=7, color=color,
            bbox=dict(boxstyle="round,pad=0.15", fc="white",
                      ec=color, alpha=0.7, lw=0.5),
            zorder=6,
        )

    # Линии-стрелки между точками
    for i in range(len(xs) - 1):
        ax.annotate(
            "", xy=(xs[i + 1], ys[i + 1]),
            xytext=(xs[i], ys[i]),
            arrowprops=dict(arrowstyle="->", color=color, lw=1.2,
                             alpha=0.85),
            zorder=4,
        )

    # «Вытяжной» воздух — отдельная точка (если есть)
    if "extract" in pts:
        st = pts["extract"]
        ax.plot(st.w_g_kg, st.h_kj_kg, marker="s",
                 markersize=6, color=color, alpha=0.5, zorder=5)
        ax.annotate(
            f"{prefix}: extract",
            xy=(st.w_g_kg, st.h_kj_kg),
            xytext=(6, -10), textcoords="offset points",
            fontsize=7, color=color, alpha=0.7,
            zorder=6,
        )


def save_id_chart(fig, path: str, dpi: int = 150) -> None:
    """Сохраняет диаграмму в PNG/PDF/SVG (по расширению)."""
    fig.savefig(path, dpi=dpi, bbox_inches="tight")


def render_processes_for_ahu(ahu_processes: dict,
                              ahu_name: str,
                              modes: Sequence[str] = ("winter", "summer"),
                              **kwargs):
    """Удобный хелпер: строит диаграмму для одной AHU с несколькими режимами.

    ahu_processes — структура HVACProject.ahu_processes (см. фасад
    compute_ahu_processes). modes — какие режимы наносить на одну диаграмму
    разными цветами.
    """
    by_mode = ahu_processes.get(ahu_name, {})
    procs = [by_mode[m] for m in modes if m in by_mode]
    title = f"i-d диаграмма: {ahu_name}" if ahu_name else "i-d диаграмма"
    return build_id_chart(processes=procs, title=title, **kwargs)
