# -*- coding: utf-8 -*-
"""Каталог типовых конструкций (пресеты).

Каждый пресет — это уже готовый список слоёв с λ по СП 50 Прил. С.
Применение пресета к Construction записывает в неё `layers` и пересчитывает
`u_value` через Construction.compute_u(). SHGC задаётся для остеклённых.
"""

from __future__ import annotations
from dataclasses import dataclass
from typing import Dict, List, Optional

from hvac.models import Construction, Layer


@dataclass
class ConstructionPreset:
    name: str
    category: str           # "Стены"/"Окна"/...
    description: str
    layers: List[Layer]
    shgc: float = 0.0
    u_override: float = 0.0  # для светопрозрачных задаём U напрямую


def _make(material: str, thickness_mm: float, lam: float,
          density: float = 0.0) -> Layer:
    return Layer(material=material, thickness_mm=thickness_mm,
                 lambda_w_mk=lam, density_kg_m3=density)


def _air(r: float, note: str = "") -> Layer:
    return Layer(material="Воздушная прослойка", r_m2k_w=r, note=note)


# ===== Каталог =====
PRESETS: Dict[str, ConstructionPreset] = {

    # ---------- СТЕНЫ ----------
    "Кирпич 380 мм без утепления": ConstructionPreset(
        name="Кирпич 380 мм без утепления",
        category="Стены",
        description="Сплошная кирпичная кладка, штукатурка с двух сторон. Для тёплого климата без нормирования.",
        layers=[
            _make("Цементно-песчаный раствор", 20, 0.93, 1800),
            _make("Кирпич керамический полнотелый", 380, 0.81, 1800),
            _make("Цементно-песчаный раствор", 20, 0.93, 1800),
        ],
    ),

    "Кирпич 380 + минвата 100 мм": ConstructionPreset(
        name="Кирпич 380 + минвата 100 мм",
        category="Стены",
        description="Кирпичная кладка с наружным утеплением, вентилируемый фасад.",
        layers=[
            _make("Гипсовая штукатурка", 15, 0.35, 1000),
            _make("Кирпич керамический полнотелый", 380, 0.81, 1800),
            _make("Минвата плотная (URSA, ROCKWOOL)", 100, 0.045, 100),
            _make("Облицовочный кирпич", 120, 0.70, 1700),
        ],
    ),

    "Газобетон 400 мм": ConstructionPreset(
        name="Газобетон 400 мм",
        category="Стены",
        description="Несущая стена из газобетона D500 без дополнительного утепления.",
        layers=[
            _make("Гипсовая штукатурка", 15, 0.35, 1000),
            _make("Газобетон D500", 400, 0.17, 500),
            _make("Цементно-песчаный раствор", 20, 0.93, 1800),
        ],
    ),

    "Газобетон 300 + XPS 80 мм": ConstructionPreset(
        name="Газобетон 300 + XPS 80 мм",
        category="Стены",
        description="Газобетон D500 с наружным утеплением XPS под штукатурку.",
        layers=[
            _make("Гипсовая штукатурка", 15, 0.35, 1000),
            _make("Газобетон D500", 300, 0.17, 500),
            _make("Пенополистирол экструдированный XPS", 80, 0.034, 35),
            _make("Цементно-песчаный раствор", 8, 0.93, 1800),
        ],
    ),

    "Сэндвич-панель 150 мм минвата": ConstructionPreset(
        name="Сэндвич-панель 150 мм минвата",
        category="Стены",
        description="Стальная сэндвич-панель с минватной серединой (промздания).",
        layers=[
            _make("Сталь", 0.5, 58.0, 7850),
            _make("Минвата плотная (URSA, ROCKWOOL)", 150, 0.045, 100),
            _make("Сталь", 0.5, 58.0, 7850),
        ],
    ),

    "Монолит 200 + PIR 100 мм": ConstructionPreset(
        name="Монолит 200 + PIR 100 мм",
        category="Стены",
        description="Монолитный железобетон с эффективным утеплением PIR.",
        layers=[
            _make("Гипсовая штукатурка", 15, 0.35, 1000),
            _make("Железобетон", 200, 2.04, 2500),
            _make("PIR-плита", 100, 0.024, 35),
            _make("Цементно-песчаный раствор", 8, 0.93, 1800),
        ],
    ),

    # ---------- ПОКРЫТИЕ ----------
    "Плоская кровля + минвата 200 мм": ConstructionPreset(
        name="Плоская кровля + минвата 200 мм",
        category="Покрытие",
        description="Монолитная плита, минвата 200 мм, ПВХ-мембрана.",
        layers=[
            _make("Железобетон", 200, 2.04, 2500),
            _make("Битумная гидроизоляция", 4, 0.27, 1000),
            _make("Минвата плотная (URSA, ROCKWOOL)", 200, 0.045, 100),
            _make("ПВХ-мембрана", 2, 0.17, 1300),
        ],
    ),

    "Скатная кровля + минвата 250 мм": ConstructionPreset(
        name="Скатная кровля + минвата 250 мм",
        category="Покрытие",
        description="Стропильная скатная кровля с межстропильным утеплением.",
        layers=[
            _make("Гипсокартон", 12, 0.21, 800),
            _make("Минвата лёгкая", 250, 0.041, 50),
            _make("ОСП / фанера", 18, 0.18, 700),
        ],
    ),

    # ---------- ПОЛ ----------
    "Пол по грунту + XPS 100 мм": ConstructionPreset(
        name="Пол по грунту + XPS 100 мм",
        category="Пол",
        description="Бетонная стяжка по утеплителю XPS на песчаной подготовке.",
        layers=[
            _make("Керамогранит", 10, 1.50, 2400),
            _make("Цементно-песчаный раствор", 50, 0.93, 1800),
            _make("Пенополистирол экструдированный XPS", 100, 0.034, 35),
            _make("Бетон тяжёлый", 100, 1.86, 2400),
        ],
    ),

    "Перекрытие над парковкой + минвата 150 мм": ConstructionPreset(
        name="Перекрытие над парковкой + минвата 150 мм",
        category="Пол",
        description="Монолитная плита с подвесным утеплением снизу.",
        layers=[
            _make("Цементно-песчаный раствор", 50, 0.93, 1800),
            _make("Железобетон", 200, 2.04, 2500),
            _make("Минвата плотная (URSA, ROCKWOOL)", 150, 0.045, 100),
        ],
    ),

    # ---------- ОКНА / ВИТРАЖИ ----------
    # Светопрозрачные конструкции — задаём U напрямую: тонкие слои стекла
    # и газового заполнения по СП 50 считают сводными.
    "Однокамерный стеклопакет 4-16-4": ConstructionPreset(
        name="Однокамерный стеклопакет 4-16-4",
        category="Окна",
        description="Обычный одинарный стеклопакет в ПВХ-профиле.",
        layers=[],
        u_override=2.70,
        shgc=0.65,
    ),

    "Двухкамерный стеклопакет 4-12-4-12-4": ConstructionPreset(
        name="Двухкамерный стеклопакет 4-12-4-12-4",
        category="Окна",
        description="Двухкамерный СП без покрытий, ПВХ или Al с термомостом.",
        layers=[],
        u_override=1.80,
        shgc=0.55,
    ),

    "Двухкамерный СП с Low-E + Ar": ConstructionPreset(
        name="Двухкамерный СП с Low-E + Ar",
        category="Окна",
        description="Энергоэффективный СП: i-стекло + аргон.",
        layers=[],
        u_override=1.20,
        shgc=0.40,
    ),

    "Тёплый витраж (структурное остекление)": ConstructionPreset(
        name="Тёплый витраж (структурное остекление)",
        category="Витраж",
        description="Алюминиевый витраж с термомостами и двухкамерным СП.",
        layers=[],
        u_override=1.80,
        shgc=0.40,
    ),

    "Холодный витраж (фасадная стойка)": ConstructionPreset(
        name="Холодный витраж (фасадная стойка)",
        category="Витраж",
        description="Алюминиевый витраж без термомоста, одинарный СП.",
        layers=[],
        u_override=3.20,
        shgc=0.60,
    ),

    # ---------- ДВЕРИ ----------
    "Дверь утеплённая металлическая": ConstructionPreset(
        name="Дверь утеплённая металлическая",
        category="Двери",
        description="Стандартная входная стальная дверь с минватой 50 мм.",
        layers=[
            _make("Сталь", 1.5, 58.0, 7850),
            _make("Минвата плотная (URSA, ROCKWOOL)", 50, 0.045, 100),
            _make("Сталь", 1.5, 58.0, 7850),
        ],
    ),

    "Дверь деревянная": ConstructionPreset(
        name="Дверь деревянная",
        category="Двери",
        description="Стандартная деревянная входная дверь 50 мм.",
        layers=[
            _make("Сосна / ель поперёк волокон", 50, 0.18, 500),
        ],
    ),
}


def presets_for_category(category: str) -> List[ConstructionPreset]:
    """Все пресеты для категории."""
    return [p for p in PRESETS.values() if p.category == category]


def get_preset(name: str) -> Optional[ConstructionPreset]:
    return PRESETS.get(name)


def apply_preset(construction: Construction, preset_name: str) -> bool:
    """Применяет пресет к существующей конструкции.

    - Записывает в construction.layers копию слоёв пресета
    - Пересчитывает u_value (или ставит u_override для светопрозрачных)
    - Обновляет shgc если задано в пресете
    - Заполняет note ссылкой на имя пресета (если note пуст)

    Возвращает True если применено, False если пресет не найден.
    """
    preset = get_preset(preset_name)
    if preset is None:
        return False
    construction.layers = [
        Layer(material=l.material, thickness_mm=l.thickness_mm,
              lambda_w_mk=l.lambda_w_mk, density_kg_m3=l.density_kg_m3,
              r_m2k_w=l.r_m2k_w, note=l.note)
        for l in preset.layers
    ]
    if preset.u_override > 0:
        construction.u_value = preset.u_override
    else:
        construction.recompute_u_from_layers()
    if preset.shgc > 0:
        construction.shgc = preset.shgc
    if not construction.note:
        construction.note = f"Пресет: {preset.name}"
    return True
