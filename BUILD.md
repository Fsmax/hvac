# Сборка дистрибутива

## Windows (.exe)

```bash
pip install pyinstaller
pyinstaller hvac_calc.spec
```

Готовый дистрибутив: `dist/HVAC Calculator/`.
Запуск: `dist/HVAC Calculator/HVAC Calculator.exe`.

Размер ~120 МБ (PySide6 + matplotlib + openpyxl + reportlab + python-docx).

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
