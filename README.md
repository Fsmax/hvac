<p align="center">
  <img src="resources/icon_128.png" alt="HVAC Calculator" width="96" height="96">
</p>

<h1 align="center">HVAC Calculator v4.0</h1>

Расчёт теплопотерь, теплопоступлений, **вентиляции**, **дымоудаления**,
**ГВС**, **энергопаспорта**, **подбора воздуховодов и труб отопления**
и **проверки точки росы** по данным Revit (СП 50, СП 60, СП 7, СП 44,
СП 113, СП 30, СП 131, КМК Узбекистана).

## Что нового в v4.0

Полностью переписанный UI на **PySide6** с собственной dark/light темой.
Расчётное ядро без изменений — все ваши проекты v3.x открываются.

```bash
pip install PySide6 matplotlib openpyxl reportlab python-docx
python hvac_calc.py
```

- 12 разделов в боковой панели: Главная, Данные, Помещения, Конструкции,
  Расчёт, Вентиляция, Зоны, Оборудование, Оборуд. в комнатах,
  Дымоудаление, Графики, Расширения
- Командная палитра по `Ctrl+K` (24 команды: навигация, файл, расчёт, вид)
- Чек-лист готовности проекта справа — 6 шагов с реальными значениями
- Асинхронный расчёт в `QThread` — UI не блокируется на 600+ помещениях
- Inline-edit прямо в таблице помещений с цветовой подсветкой аномалий
- Реактивные панели через `ProjectBridge` — расчёт обновляет всё сразу
- Export Center: единое окно вместо 4 пунктов меню
- Auto-save каждые 5 минут в `~/.hvac_calc/autosave/`
- Recent files в меню «Файл»
- Переключение темы `Ctrl+T`, F5 — пересчёт, Ctrl+S — сохранение

См. [BUILD.md](BUILD.md) для сборки .exe через PyInstaller.

## Что нового в v3.7

Шесть новых функциональных модулей:

| # | Модуль | Что делает | Норматив |
|---|--------|-----------|----------|
| 1 | `hvac.dew_point` | Проверка ограждений на конденсацию (τ_int vs t_d) | СП 50.13330 Прил. Е |
| 2 | `hvac.dhw` | Расчёт ГВС (V_сут, Q_пик, Q_нагревателя, бак) | СП 30.13330 Прил. А |
| 3 | `hvac.energy` | Энергопаспорт (год. потребление, класс A++…E) | СП 50.13330 Прил. Г |
| 4 | `hvac.duct_sizing` | Подбор сечений воздуховодов (Ø, AxB, Δp) | СП 60, АВОК 7.6 |
| 5 | `hvac.pipe_sizing` | Гидравлика труб отопления (DN, v, Δp) | СП 60, Альтшуль |
| 6 | `hvac.io_pdf` | PDF-отчёт «Пояснительная записка» (12 разделов) | reportlab |

Плюс:
- 5 новых листов в Excel-экспорте: ГВС, Энергопаспорт, Точка росы,
  Воздуховоды, Трубы отопления (всего 14 листов)
- 98 новых unit-тестов (формулы Магнуса, Дарси, Альтшуля, калибровка
  отопительного сезона на 7 справочных городах СП 131)
- Save/load всех новых данных в JSON
- 5 фасадных методов в `HVACProject`:
  `check_condensation_risk()`, `calculate_dhw()`,
  `calculate_energy_passport()`, `size_ducts()`, `size_pipes()`

## Быстрый старт v3.7

```python
from hvac import HVACProject
from hvac.io_excel import export_to_excel
from hvac.io_pdf import export_to_pdf

p = HVACProject()
p.params.apply_city("Ташкент")
p.load("spaces.csv", "thermal.csv")
p.recalculate()                 # теплопотери / теплопоступления
p.calculate_ventilation()       # Supply / Exhaust / Hood
p.auto_assign_zones()           # назначить системы помещениям
p.calculate_ahu_loads()         # нагрузка калориферов / охладителей

# Расширения v3.7:
p.check_condensation_risk()     # СП 50 Прил. Е
p.calculate_dhw(strategy="by_type")   # СП 30.13330
p.calculate_energy_passport()   # СП 50 Прил. Г, кВт·ч/(м²·год), класс
p.size_ducts(shape="round")     # подбор Ø воздуховодов
p.size_pipes(pipe_material="steel")   # подбор DN труб отопления

export_to_excel(p, "report.xlsx")     # 14 листов
export_to_pdf(p, "report.pdf")        # пояснительная записка
```

## Что нового в v3.1

**Расчёт вентиляции** по СП 60.13330.2020 (+ СП 44 для гостиниц, СП 113
для парковок):
- Supply (приток), Exhaust (вытяжка), Hood (зонт кухонь) для каждого помещения
- Норма свежего воздуха по числу людей / площади / кратности — берётся максимум
- Особые случаи: только вытяжка для туалетов, NC для лифтов и лестниц,
  расчёт по тепловыделениям для серверных и техпомещений
- Дисбаланс (отрицательное давление) для кухонь и складов
- Новая вкладка «6. Вентиляция» в GUI
- Новый лист «Вентиляция» в Excel-экспорте
- Сохраняется в проектном JSON

| Аспект                       | v2.0               | v3.0               |
|------------------------------|--------------------|--------------------|
| Файлов Python                | 4                  | 19 + 4 теста       |
| Самый большой файл           | 1762 строки        | 712 строк (UI)     |
| Юнит-тестов                  | 0                  | 65                 |
| Добавить новую методику      | Редактировать switch | Создать класс с декоратором |
| Добавить новый график        | Редактировать switch | Создать функцию с декоратором |
| Использовать ядро без GUI    | Невозможно         | `from hvac import HVACProject` |
| Валидация данных             | Нет                | `project.validate()` |
| Связь UI ↔ модель            | Прямые вызовы      | Event bus |

**См. подробное описание в `ARCHITECTURE.md`.**

## Запуск

```bash
# С GUI
python hvac_calc.py

# Командный режим
python hvac_calc.py cli spaces.csv thermal.csv result.xlsx -16 36 "Ташкент"

# Только ядро в своём скрипте
python -c "
from hvac import HVACProject
p = HVACProject()
p.params.apply_city('Москва')
p.load('spaces.csv', 'thermal.csv')
p.recalculate()
print(f'Σ Q зима = {sum(s.heat_loss_w for s in p.spaces)/1000:.2f} кВт')
"

# Запуск тестов
python -m pytest tests/ -v
```

## Структура пакета (кратко)

```
hvac_v4/
├── hvac_calc.py             # Точка входа (27 строк): GUI или CLI
├── ARCHITECTURE.md          # Подробное описание архитектуры
│
├── hvac/                    # Главный пакет (~99 .py файлов)
│   ├── models.py            # Структуры данных (Space, BoundaryElement, ...)
│   ├── parsers.py           # Утилиты парсинга строк
│   ├── data_loader.py       # Загрузка CSV из Revit
│   ├── project.py           # HVACProject — оркестратор + event bus
│   ├── _project_*.py        # Mixin'ы: ручной ввод, дымоудаление, расширения, валидация
│   ├── catalogs/            # Справочники (климат, типы помещений, конструкции, нормы)
│   ├── engine/              # Расчётные движки (Strategy): base / sp50 / ventilation
│   ├── psychro*.py · ahu_*.py · duct_*.py · pipe_sizing.py · heating_hydraulics.py
│   │                        # Психрометрия, AHU, воздуховоды, гидравлика
│   ├── dew_point.py · dhw.py · energy*.py · smoke*.py · acoustics.py · specification.py
│   │                        # Точка росы, ГВС, энергопаспорт, дымоудаление, акустика
│   ├── reports.py           # Графики (Registry Pattern)
│   ├── i18n/                # Локализация RU/UZ (ru.py + uz.py + API)
│   ├── io_excel/            # Экспорт в Excel (пакет: _core/_extensions/_detailed/_common)
│   ├── io_pdf.py · io_json.py · io_revit.py · io_hlgc.py
│   │                        # PDF-записка, save/load, CSV в Revit, HLGC-таблицы
│   ├── cli.py               # Командный режим
│   └── ui_qt/               # GUI на PySide6
│       ├── main_window.py · bridge.py · commands.py · export_center.py
│       ├── panels/          # 16 функциональных панелей
│       ├── widgets/         # Карточки, чек-лист, sidebar, диалоги
│       └── theme/           # dark.qss / light.qss
│
├── tests/                   # Юнит-тесты (659 шт.)
│
├── revit_dynamo_hvac_write_csv.py    # Dynamo: выгрузка из Revit
├── revit_dynamo_apply_results.py     # Dynamo: запись результатов в Space/Room
└── revit_dynamo_distribute_loads_to_fancoils.py  # Dynamo: нагрузка Space → фанкойлы
```

## Зависимости

```bash
pip install -r requirements.txt
# или вручную:
pip install PySide6 matplotlib openpyxl reportlab python-docx
```

| Пакет         | Версия | Зачем                                        |
|---------------|--------|----------------------------------------------|
| `PySide6`     | ≥6.10  | GUI на Qt6 — обязательно для оконного режима  |
| `matplotlib`  | ≥3.10  | Вкладка «Графики», i-d диаграмма              |
| `openpyxl`    | ≥3.1   | Экспорт в Excel (14 листов)                  |
| `reportlab`   | ≥4.5   | PDF-отчёт «Пояснительная записка»            |
| `python-docx` | ≥1.1   | Экспорт в Word (.docx)                        |

Инструменты разработки (`pytest`, `ruff`, `mypy`) — в `requirements-dev.txt`,
для работы программы не нужны. Регенерация каталога решёток
(`tools/arktika_grilles`) дополнительно требует `PyMuPDF` (`fitz`).

## Как добавить новую функцию

### Новая методика расчёта (например EN 12831)

1. Создайте `hvac/engine/en12831.py`:
   ```python
   from hvac.engine.base import CalculationEngine, register_engine

   @register_engine
   class EN12831Engine(CalculationEngine):
       @property
       def name(self): return "EN 12831"
       def heat_loss(self, space, project): ...
       def heat_gain(self, space, project): ...
   ```

2. Добавьте импорт в `hvac/engine/__init__.py`:
   ```python
   from hvac.engine import en12831  # noqa: F401
   ```

3. В UI методика автоматически появится в выпадающем списке. Не нужно
   трогать ничего больше.

### Новый график

```python
# В hvac/reports.py:
@register_chart("Моя новая диаграмма")
def my_chart(project, fig):
    ax = fig.add_subplot(111)
    # ваш код
```

В UI на вкладке «Графики» новый пункт появится автоматически.

### Новая вкладка

В `hvac/ui/tabs.py`:
```python
class MyTab(BaseTab):
    title = "7. Моя вкладка"
    def build(self):
        # ваши виджеты
        ttk.Label(self, text="Hello").pack()

# Добавьте в реестр в конце файла:
TABS_REGISTRY.append(MyTab)
```

## Полный цикл работы Revit → расчёт → Revit

(такой же как в v2.0)

1. **Выгрузить геометрию из Revit** (один раз): запустить
   `revit_dynamo_hvac_write_csv.py` в Dynamo, получить `spaces.csv` и
   `thermal_all.csv`.

2. **Запустить программу** и пройти вкладки 1→6: загрузить CSV → выбрать
   город → задать U → уточнить помещения → выполнить расчёт → экспорт.

3. **Сохранить проект** (Файл → Сохранить) — все правки и параметры
   уйдут в `.hvac.json`.

4. **Записать результаты в Revit**: Файл → Экспорт для Revit → запустить
   `revit_dynamo_apply_results.py` в Dynamo. В CSV уходит полный
   инженерный набор на каждое помещение — нагрузки (отопление,
   охлаждение, явная/скрытая), вентиляция (приток, вытяжка, кратность),
   расчётные температуры, имена систем и контуров.

   Чтобы значения легли в модель, заранее создайте в проекте Revit
   Project Parameters категории Spaces/Rooms:
   - **Числовые:** `Heating Load`, `Cooling Load`, `Cooling Sensible Load`,
     `Cooling Latent Load`, `Supply Airflow`, `Exhaust Airflow`,
     `Air Changes`, `Heating Setpoint`, `Cooling Setpoint`;
   - **Текст:** `Heating System`, `Cooling System`, `Ventilation System`,
     `Heating Circuit`, `Cooling Circuit`, `Duct Zone`.

   Числовые параметры можно завести **двумя способами** — скрипт сам
   определит, как писать: тип «Число» (без единиц) принимает значение как
   есть (Вт, м³/ч, °C), а типизированный параметр (HVAC «Мощность» /
   «Расход воздуха» / «Температура») получает значение, автоматически
   переведённое во внутренние единицы Revit (для температуры — с учётом
   смещения °C→K).

   Создавать нужно только те параметры, что реально нужны в модели —
   колонки без соответствующего параметра скрипт молча пропускает.

5. **(Опц.) Разнести нагрузку на фанкойлы**: запустить
   `revit_dynamo_distribute_loads_to_fancoils.py` в Dynamo. Скрипт находит
   фанкойлы (Mechanical Equipment) в каждом помещении и пишет в их параметры
   `Design Cooling Load` / `Design Heating Load` долю нагрузки помещения.
   Если фанкойлов в помещении несколько — нагрузка делится между ними
   **поровну** (`Q_помещения / N`). Параметры читаются из Space (`Cooling
   Load` / `Heating Load`, заполненные шагом 4), поэтому сначала запускают
   `apply_results.py`, затем этот скрипт.

## Результат на тестовых данных (CHR_MZN, Ташкент)

- 297 помещений, 21 367 м² общей площади.
- Σ Q зимой: **389.75 кВт** (18.2 Вт/м²) при tн = −15°C.
- Σ Q летом: **579.32 кВт** (27.1 Вт/м²) при tн = +36°C.

## Тесты

```bash
pip install -r requirements-dev.txt
python -m pytest tests/ -q
```

**659 тестов** покрывают расчётное ядро: парсеры, движки СП 50/60,
вентиляцию, дымоудаление, ГВС, энергопаспорт, гидравлику, подбор
оборудования, локализацию (RU/UZ) и защиту от хардкода UI-строк.

CI прогоняет весь набор на Python 3.11 и 3.12 при каждом push и
pull request — см. [.github/workflows/ci.yml](.github/workflows/ci.yml).

## Линтер и типы

```bash
ruff check hvac/      # линтер (pyflakes + pycodestyle)
mypy                  # статическая типизация расчётного ядра
```

Конфигурация — в [pyproject.toml](pyproject.toml). `ruff` и `mypy`
покрывают **весь пакет `hvac/`** (86 модулей: ядро + io + UI). Для
`ui_qt` заглушены ложные срабатывания Qt6-стабов (unscoped enum'ы
`Qt.AlignLeft`, строгость override у моделей) — см. `[[tool.mypy.overrides]]`;
реальные ошибки UI вычищены. Оба прогона блокирующие в CI
(job **Lint & types**).

---

**Версия:** 4.0
**Дата:** 2026
**Совместимость:** Revit 2024+, Python 3.10+, PySide6 6.10+
