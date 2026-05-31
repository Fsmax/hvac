# -*- coding: utf-8 -*-
"""ValidationMixin — проверки целостности проекта.

`validate()` — простой список строк-предупреждений (старый API).
`validate_detailed()` — структурированные записи с severity и категорией.
"""

from __future__ import annotations
from typing import Dict, List


class ValidationMixin:
    """Проверка данных и результатов расчёта на типичные ошибки."""

    def validate(self) -> List[str]:
        """Простой список предупреждений (для обратной совместимости).
        Для подробных проверок используйте validate_detailed()."""
        detailed = self.validate_detailed()
        return [d["msg"] for d in detailed]

    def validate_detailed(self) -> List[Dict]:
        """Подробные проверки. Возвращает список:
        [{'severity': 'error'|'warning'|'info', 'category': str,
          'msg': str, 'space_id': str (optional)}]"""
        results: List[Dict] = []

        def add(severity, category, msg, space_id=""):
            results.append({"severity": severity, "category": category,
                           "msg": msg, "space_id": space_id})

        # ===== Глобальные проверки =====
        if not self.spaces:
            add("error", "Данные", "Нет загруженных помещений")
            return results

        # ===== Каталог конструкций =====
        for c in self.constructions.values():
            if c.u_value <= 0:
                add("warning", "Конструкции",
                    f"не задано U-значение для '{c.key}' (использует дефолт)")
            elif c.u_value > 5:
                add("warning", "Конструкции",
                    f"Очень высокое U={c.u_value:.2f} для '{c.key}' "
                    f"(возможно опечатка?)")
            elif c.u_value < 0.1:
                add("warning", "Конструкции",
                    f"Подозрительно низкое U={c.u_value:.3f} для '{c.key}'")

            if c.category in ("Окна", "Витраж") and c.shgc <= 0:
                add("warning", "Конструкции",
                    f"SHGC=0 для светопрозрачного '{c.key}' — солнце не учтётся")

        # ===== По помещениям =====
        for sp in self.spaces:
            # Геометрия
            if sp.area_m2 <= 0:
                add("error", "Геометрия",
                    f"Площадь = 0 у '{sp.number} {sp.name}'", sp.space_id)
            if sp.volume_m3 <= 0:
                add("warning", "Геометрия",
                    f"Объём = 0 у '{sp.number} {sp.name}' (инфильтрация = 0)",
                    sp.space_id)
            if sp.area_m2 > 0 and sp.volume_m3 > 0:
                h = sp.volume_m3 / sp.area_m2
                if h < 2.0:
                    add("warning", "Геометрия",
                        f"Очень низкая высота {h:.2f} м у '{sp.number}'",
                        sp.space_id)
                elif h > 8.0:
                    add("info", "Геометрия",
                        f"Большая высота {h:.2f} м у '{sp.number}' — "
                        "учтите надбавку β для высоких помещений", sp.space_id)

            # Угловое без двух наружных стен
            if sp.is_corner:
                ext_count = sum(1 for e in self.elements_for(sp.space_id)
                               if e.is_exterior
                               and e.row_type == "external_wall")
                if ext_count < 2:
                    add("warning", "Геометрия",
                        f"Помещ. '{sp.number}' помечено угловым, но имеет "
                        f"{ext_count} наружных стен", sp.space_id)

            # Параметры
            if sp.t_in_heat < 5 or sp.t_in_heat > 30:
                add("warning", "Параметры",
                    f"Зимняя tв={sp.t_in_heat}°C у '{sp.number}' "
                    f"вне типичного диапазона", sp.space_id)
            if sp.ach_inf < 0:
                add("error", "Параметры",
                    f"Отрицательная кратность ACH у '{sp.number}'", sp.space_id)
            if sp.ach_inf > 10 and sp.room_type != "Гараж / автостоянка":
                add("warning", "Параметры",
                    f"Очень высокая ACH={sp.ach_inf} у '{sp.number}'",
                    sp.space_id)
            if sp.equipment_w_m2 > 300 and sp.room_type not in (
                    "Серверная", "Технич. помещение", "Ресторан / кухня"):
                add("info", "Параметры",
                    f"Высокая мощность оборудования {sp.equipment_w_m2} Вт/м² "
                    f"у '{sp.number}' (тип: {sp.room_type})", sp.space_id)

        # ===== Результаты расчёта =====
        for sp in self.spaces:
            if sp.heat_loss_w == 0 and sp.heat_gain_w == 0:
                continue  # расчёт не выполнялся
            if sp.area_m2 > 0:
                ud_loss = sp.heat_loss_w / sp.area_m2
                ud_gain = sp.heat_gain_w / sp.area_m2
                if ud_loss > 200:
                    add("warning", "Результаты",
                        f"Удельные теплопотери {ud_loss:.0f} Вт/м² у '{sp.number}' "
                        f"— очень высоко (обычно <150)", sp.space_id)
                if ud_gain > 400:
                    add("warning", "Результаты",
                        f"Удельные теплопоступления {ud_gain:.0f} Вт/м² у "
                        f"'{sp.number}' — очень высоко (обычно <300)", sp.space_id)
                ext_count = sum(1 for e in self.elements_for(sp.space_id)
                               if e.is_exterior)
                if ext_count == 0 and sp.heat_loss_w > 500:
                    add("info", "Результаты",
                        f"'{sp.number}' без наружных стен, но Q_отопл={sp.heat_loss_w:.0f} Вт"
                        f" — только инфильтрация?", sp.space_id)

        # ===== Климатические =====
        if abs(self.params.t_out_heating - self.params.t_out_cooling) < 20:
            add("warning", "Климат",
                f"Зимняя ({self.params.t_out_heating}) и летняя "
                f"({self.params.t_out_cooling}) расчётные температуры близки — "
                f"проверьте параметры")

        return results
