# -*- coding: utf-8 -*-
"""Реестр графиков (Registry Pattern).

Каждый график — отдельная функция, регистрируемая через @register_chart.
Добавление нового графика = создание новой функции без правки реестра
или вкладки графиков.
"""

from __future__ import annotations
from typing import Callable, Dict, List
from hvac.project import HVACProject

# Тип функции графика: (project, fig) → None
ChartFunc = Callable[[HVACProject, "Figure"], None]


_CHARTS: Dict[str, ChartFunc] = {}


def register_chart(label: str):
    """Декоратор регистрации функции-графика под именем label."""
    def decorator(func: ChartFunc) -> ChartFunc:
        _CHARTS[label] = func
        return func
    return decorator


def list_charts() -> List[str]:
    """Имена всех зарегистрированных графиков (в порядке регистрации)."""
    return list(_CHARTS.keys())


def draw_chart(label: str, project: HVACProject, fig) -> None:
    """Рисует график label в matplotlib Figure."""
    func = _CHARTS.get(label)
    if func is None:
        raise KeyError(f"График '{label}' не найден")
    func(project, fig)


# ---------- Реализации графиков ----------
# Все графики используют только matplotlib API через fig — это
# позволяет использовать их и в Tk-GUI, и при сохранении в PDF.


@register_chart("Топ-20 по теплопотерям")
def _chart_top_losses(project, fig):
    ax = fig.add_subplot(111)
    top = sorted(project.spaces, key=lambda s: -s.heat_loss_w)[:20]
    names = [f"{s.number}\n{s.name[:18]}" for s in top]
    vals = [s.heat_loss_w / 1000 for s in top]
    ax.barh(range(len(top)), vals, color="#1F77B4")
    ax.set_yticks(range(len(top)))
    ax.set_yticklabels(names, fontsize=8)
    ax.invert_yaxis()
    ax.set_xlabel("Теплопотери, кВт")
    ax.set_title("Топ-20 помещений по теплопотерям")
    ax.grid(True, axis="x", alpha=0.3)
    fig.tight_layout()


@register_chart("Топ-20 по теплопоступлениям")
def _chart_top_gains(project, fig):
    ax = fig.add_subplot(111)
    top = sorted(project.spaces, key=lambda s: -s.heat_gain_w)[:20]
    names = [f"{s.number}\n{s.name[:18]}" for s in top]
    vals = [s.heat_gain_w / 1000 for s in top]
    ax.barh(range(len(top)), vals, color="#D62728")
    ax.set_yticks(range(len(top)))
    ax.set_yticklabels(names, fontsize=8)
    ax.invert_yaxis()
    ax.set_xlabel("Теплопоступления, кВт")
    ax.set_title("Топ-20 помещений по теплопоступлениям")
    ax.grid(True, axis="x", alpha=0.3)
    fig.tight_layout()


@register_chart("Сводка по уровням")
def _chart_levels(project, fig):
    ax = fig.add_subplot(111)
    by_level = {}
    for sp in project.spaces:
        by_level.setdefault(sp.level, []).append(sp)
    lvls = sorted(by_level.keys())
    losses = [sum(s.heat_loss_w for s in by_level[l]) / 1000 for l in lvls]
    gains = [sum(s.heat_gain_w for s in by_level[l]) / 1000 for l in lvls]
    x = list(range(len(lvls)))
    w = 0.4
    ax.bar([i - w/2 for i in x], losses, width=w,
           label="Теплопотери", color="#1F77B4")
    ax.bar([i + w/2 for i in x], gains, width=w,
           label="Теплопоступления", color="#D62728")
    ax.set_xticks(x)
    ax.set_xticklabels(lvls, rotation=15, fontsize=9)
    ax.set_ylabel("Мощность, кВт")
    ax.set_title("Σ нагрузки по уровням")
    ax.legend()
    ax.grid(True, axis="y", alpha=0.3)
    fig.tight_layout()


@register_chart("Разбивка теплопотерь по статьям")
def _chart_loss_breakdown(project, fig):
    ax = fig.add_subplot(111)
    buckets = {"Стены": 0, "Проёмы": 0, "Покрытие": 0,
               "Пол по грунту": 0, "Инфильтрация": 0}
    for sp in project.spaces:
        for k, v in sp.heat_loss_breakdown.items():
            if k in buckets:
                buckets[k] += v
    pos = [(l, v / 1000) for l, v in buckets.items() if v > 1]
    if pos:
        ax.pie([v for _, v in pos],
               labels=[f"{l}\n{v:.1f} кВт" for l, v in pos],
               autopct="%1.1f%%", startangle=90)
    ax.set_title(f"Распределение теплопотерь "
                 f"(Σ = {sum(v for _,v in pos):.1f} кВт)")
    fig.tight_layout()


@register_chart("Разбивка теплопоступлений по статьям")
def _chart_gain_breakdown(project, fig):
    ax = fig.add_subplot(111)
    buckets = {"Через ограждения": 0, "Солнечная радиация": 0,
               "Люди": 0, "Освещение": 0, "Оборудование": 0,
               "Инфильтрация/вентиляция": 0}
    for sp in project.spaces:
        for k in buckets:
            buckets[k] += sp.heat_gain_breakdown.get(k, 0)
    pos = [(l, v / 1000) for l, v in buckets.items() if v > 1]
    if pos:
        ax.pie([v for _, v in pos],
               labels=[f"{l}\n{v:.1f} кВт" for l, v in pos],
               autopct="%1.1f%%", startangle=90)
    ax.set_title(f"Распределение теплопоступлений "
                 f"(Σ = {sum(v for _,v in pos):.1f} кВт)")
    fig.tight_layout()


@register_chart("Удельная нагрузка по типам помещений")
def _chart_by_room_type(project, fig):
    ax = fig.add_subplot(111)
    by_type = {}
    for sp in project.spaces:
        by_type.setdefault(sp.room_type, []).append(sp)
    types_list = sorted(by_type.keys())
    ud_loss, ud_gain = [], []
    for t in types_list:
        items = by_type[t]
        a = sum(s.area_m2 for s in items)
        ud_loss.append(sum(s.heat_loss_w for s in items) / a if a else 0)
        ud_gain.append(sum(s.heat_gain_w for s in items) / a if a else 0)
    x = list(range(len(types_list)))
    w = 0.4
    ax.bar([i - w/2 for i in x], ud_loss, width=w,
           label="Уд. потери, Вт/м²", color="#1F77B4")
    ax.bar([i + w/2 for i in x], ud_gain, width=w,
           label="Уд. поступл., Вт/м²", color="#D62728")
    ax.set_xticks(x)
    ax.set_xticklabels(types_list, rotation=30, ha="right", fontsize=8)
    ax.set_ylabel("Удельная нагрузка, Вт/м²")
    ax.set_title("Удельные нагрузки по типам помещений")
    ax.legend()
    ax.grid(True, axis="y", alpha=0.3)
    fig.tight_layout()


# ---------- Heat map ----------
# Каждое помещение — прямоугольник, размер ∝ площади, цвет = Вт/м².
# Сгруппированы по уровням. Не настоящий план (нет геометрии из Revit),
# а squarified treemap (алгоритм Bruls et al. 2000).


def _squarify(values, x, y, dx, dy):
    """Squarified treemap layout. Возвращает список (x, y, w, h)
    в том же порядке, что values."""
    values = [(i, v) for i, v in enumerate(values) if v > 0]
    if not values:
        return []
    # нормируем к доступной площади
    total_v = sum(v for _, v in values)
    total_a = dx * dy
    scaled = [(i, v * total_a / total_v) for i, v in values]
    # сортируем по убыванию, но запоминаем оригинальный индекс
    scaled.sort(key=lambda t: -t[1])

    rects_by_idx = {}
    _squarify_helper(scaled, [], x, y, dx, dy, rects_by_idx)
    return [rects_by_idx.get(i) for i in range(len(values) + max(rects_by_idx, default=-1) + 1) if i in rects_by_idx]


def _worst_aspect(row_vals, side):
    """Худшее (max) отношение сторон в ряду при заданной короткой стороне."""
    s = sum(v for _, v in row_vals)
    if s == 0 or side == 0:
        return float("inf")
    long_side = s / side
    worst = 0.0
    for _, v in row_vals:
        short = v / long_side
        if short == 0:
            return float("inf")
        ratio = max(long_side / short, short / long_side)
        worst = max(worst, ratio)
    return worst


def _squarify_helper(remaining, current_row, x, y, dx, dy, out):
    """Рекурсивный helper. out[i] = (x, y, w, h) для оригинального индекса i."""
    if not remaining and not current_row:
        return
    short_side = min(dx, dy)
    if not remaining:
        _layout_row(current_row, x, y, dx, dy, out)
        return

    head = remaining[0]
    new_row = current_row + [head]
    if not current_row or _worst_aspect(new_row, short_side) <= _worst_aspect(current_row, short_side):
        _squarify_helper(remaining[1:], new_row, x, y, dx, dy, out)
    else:
        new_x, new_y, new_dx, new_dy = _layout_row(current_row, x, y, dx, dy, out)
        _squarify_helper(remaining, [], new_x, new_y, new_dx, new_dy, out)


def _layout_row(row, x, y, dx, dy, out):
    """Размещает row и возвращает оставшийся прямоугольник."""
    s = sum(v for _, v in row)
    if s == 0:
        return x, y, dx, dy
    if dx >= dy:
        # короткая сторона = dy, стэк вертикально
        col_w = s / dy
        cur_y = y
        for idx, v in row:
            h = v / col_w
            out[idx] = (x, cur_y, col_w, h)
            cur_y += h
        return x + col_w, y, dx - col_w, dy
    else:
        # короткая сторона = dx, стэк горизонтально
        row_h = s / dx
        cur_x = x
        for idx, v in row:
            w = v / row_h
            out[idx] = (cur_x, y, w, row_h)
            cur_x += w
        return x, y + row_h, dx, dy - row_h


def _draw_heatmap(project, fig, metric: str, title: str, cmap_name: str):
    """Рисует heat map: subplot для каждого уровня, помещения как treemap."""
    import matplotlib.patches as patches
    import matplotlib.cm as cm
    from matplotlib.colors import Normalize

    # Группируем по уровням
    by_level = {}
    for sp in project.spaces:
        if sp.area_m2 > 0:
            by_level.setdefault(sp.level, []).append(sp)
    levels = sorted(by_level.keys())
    if not levels:
        return

    # Удельная нагрузка по всем помещениям (для общей colorbar)
    all_ud = []
    for items in by_level.values():
        for sp in items:
            val = getattr(sp, metric)
            if sp.area_m2 > 0:
                all_ud.append(val / sp.area_m2)
    if not all_ud:
        return
    vmin = 0
    vmax = max(all_ud) if all_ud else 1
    norm = Normalize(vmin=vmin, vmax=vmax)
    cmap = cm.get_cmap(cmap_name)

    # Layout subplots: квадратная сетка
    import math
    n_cols = math.ceil(math.sqrt(len(levels)))
    n_rows = math.ceil(len(levels) / n_cols)

    # Оставляем место справа для colorbar
    fig.subplots_adjust(right=0.88, wspace=0.15, hspace=0.25)

    for i, lvl in enumerate(levels):
        ax = fig.add_subplot(n_rows, n_cols, i + 1)
        items = sorted(by_level[lvl], key=lambda s: -s.area_m2)
        sizes = [sp.area_m2 for sp in items]
        rects = _squarify(sizes, 0, 0, 100, 100)
        # rects может быть None для нулевых
        for sp, rect in zip(items, rects):
            if rect is None:
                continue
            x, y, w, h = rect
            ud = getattr(sp, metric) / sp.area_m2 if sp.area_m2 else 0
            color = cmap(norm(ud))
            ax.add_patch(patches.Rectangle((x, y), w, h, facecolor=color,
                                            edgecolor="white", linewidth=0.5))
            # подпись внутри если прямоугольник достаточно большой
            if w > 10 and h > 6:
                txt = f"{sp.number}\n{ud:.0f}"
                fs = max(5, min(8, int(min(w, h) / 4)))
                ax.text(x + w/2, y + h/2, txt, ha="center", va="center",
                        fontsize=fs, color="black" if norm(ud) < 0.5 else "white")
        ax.set_xlim(0, 100)
        ax.set_ylim(0, 100)
        ax.set_aspect("equal")
        ax.set_xticks([])
        ax.set_yticks([])
        n_sp = len(items)
        total_a = sum(sp.area_m2 for sp in items)
        ax.set_title(f"{lvl}  ({n_sp} помещ., {total_a:.0f} м²)",
                     fontsize=9)

    # Общая colorbar справа
    cbar_ax = fig.add_axes([0.90, 0.15, 0.02, 0.7])
    sm = cm.ScalarMappable(cmap=cmap, norm=norm)
    sm.set_array([])
    cb = fig.colorbar(sm, cax=cbar_ax)
    cb.set_label(title, fontsize=9)

    fig.suptitle(f"Heat Map по этажам — {title}", fontsize=11, y=0.97)


@register_chart("Heat Map: теплопотери (треемап по этажам)")
def _chart_heatmap_loss(project, fig):
    _draw_heatmap(project, fig,
                  metric="heat_loss_w",
                  title="Удельные теплопотери, Вт/м²",
                  cmap_name="Blues")


@register_chart("Heat Map: теплопоступления (треемап по этажам)")
def _chart_heatmap_gain(project, fig):
    _draw_heatmap(project, fig,
                  metric="heat_gain_w",
                  title="Удельные теплопоступления, Вт/м²",
                  cmap_name="OrRd")
