# Сборка дистрибутива

## Windows (.exe)

Собирать тем же окружением, в котором работает программа, — `.venv` проекта:

```bash
uv pip install pyinstaller --python .venv/Scripts/python.exe
.venv/Scripts/python.exe -m PyInstaller --noconfirm --clean hvac_calc.spec
```

Готовый дистрибутив: `dist/HVAC Calculator/`.
Запуск: `dist/HVAC Calculator/HVAC Calculator.exe`.
Папку `dist/HVAC Calculator` можно целиком копировать на компьютер без Python.

Размер: .exe ~11 МБ, папка ~182 МБ (PySide6 + matplotlib + numpy + openpyxl +
reportlab + python-docx).

Спек рассчитан на **PyInstaller 6+**: параметры `cipher` и `zipped_data`
(шифрование байт-кода) в 6-й версии удалены, в спеке их нет.

Каталоги-данные подключаются перебором папки `hvac/catalogs/data/*.json`,
темы — перебором `hvac/ui_qt/theme/*.qss`, поэтому при добавлении нового
каталога или темы спек править не нужно.

Модули пакета подключаются через `collect_submodules("hvac")` — целиком.
Так надо: панели интерфейса создаются лениво,
`importlib.import_module(f"hvac.ui_qt.panels.{module}")` в
`main_window._panel_factories`, имя модуля вычисляется в рантайме, и
статический анализатор PyInstaller его не видит. Со списком «руками» в
сборку не попадали все ленивые панели и то, что они тянут за собой
(57 модулей из 160): .exe запускался, но падал при открытии «Помещений»,
«Систем», «Инженерных расчётов» и т. д. Проверка после сборки — сравнить
число модулей `hvac.*` в архиве PYZ с числом `.py` в пакете.

### Опции

**Single-file сборка** (один .exe ~80 МБ, медленный первый запуск из-за
распаковки во временную папку):

В `hvac_calc.spec` поменять блок `EXE(...)`:

```python
exe = EXE(
    pyz,
    a.scripts,
    a.binaries,       # <-- добавить
    a.zipfiles,       # <-- добавить
    a.datas,          # <-- добавить
    name="HVAC Calculator",
    onefile=True,     # <-- добавить
    ...
)
```

И убрать блок `COLLECT(...)`.

**Своя иконка:** положите `app.ico` в корень и раскомментируйте
`icon=...` в `EXE(...)` блоке.

## macOS (.app)

```bash
pyinstaller hvac_calc.spec --windowed
```

Готовый бандл: `dist/HVAC Calculator.app`.

## Linux (AppImage / standalone)

```bash
pyinstaller hvac_calc.spec
```

Готово в `dist/HVAC Calculator/` — запускайте `./HVAC Calculator`.
