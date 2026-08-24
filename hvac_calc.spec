# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec для HVAC Calculator.

Сборка:
    .venv\\Scripts\\python -m pip install pyinstaller
    .venv\\Scripts\\python -m PyInstaller hvac_calc.spec

Результат: dist/HVAC Calculator/HVAC Calculator.exe.
Для single-file бандла см. BUILD.md.

Совместимо с PyInstaller 6+: параметры cipher/zipped_data (шифрование
байт-кода) в 6-й версии удалены и здесь не используются.
"""
from pathlib import Path

from PyInstaller.utils.hooks import collect_submodules

project_root = Path(SPECPATH)

# QSS-темы и иконки: читаются через __file__ / рядом с .exe, анализатор их
# не видит — подключаем как data-файлы.
data_files = [
    (str(p), "hvac/ui_qt/theme")
    for p in (project_root / "hvac" / "ui_qt" / "theme").glob("*.qss")
]
data_files += [
    (str(project_root / "resources" / name), "resources")
    for name in ("app.ico", "app.png")
    if (project_root / "resources" / name).exists()
]

# Каталоги-данные (климат, типы помещений, оборудование) — внешние JSON,
# читаются через importlib.resources. Берём все файлы папки, чтобы спек не
# отставал при добавлении новых каталогов (ручной список уже терял
# добавленные на другой машине water_heaters/…).
data_files += [
    (str(p), "hvac/catalogs/data")
    for p in sorted((project_root / "hvac" / "catalogs" / "data").glob("*.json"))
]

# Панели интерфейса грузятся лениво через importlib.import_module() с
# вычисляемым именем (main_window._panel_factories) — статический анализатор
# их не видит и вместе с ними теряет половину пакета. Поэтому берём ВСЕ
# подмодули hvac целиком: спек не отстаёт при добавлении новых панелей.
hidden = collect_submodules("hvac")
hidden += [
    "matplotlib.backends.backend_qtagg",
    "openpyxl",
    "reportlab",
    "docx",        # python-docx — импортируется лениво в io_docx
]


a = Analysis(
    ["hvac_calc.py"],
    pathex=[str(project_root)],
    binaries=[],
    datas=data_files,
    hiddenimports=hidden,
    hookspath=[],
    runtime_hooks=[],
    excludes=[
        # Урезаем — PySide6 тянет много чего не нужного
        "PySide6.QtQml",
        "PySide6.QtQuick",
        "PySide6.Qt3DCore",
        "PySide6.Qt3DRender",
        "PySide6.QtWebEngineCore",
        "PySide6.QtWebEngineWidgets",
        "PySide6.QtMultimedia",
        "PySide6.QtMultimediaWidgets",
        "PySide6.QtBluetooth",
        "PySide6.QtSensors",
        "PySide6.QtPositioning",
        "PySide6.QtNfc",
        "tkinter",      # Tk больше не нужен
        "test",
        "unittest",
    ],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="HVAC Calculator",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,       # GUI-приложение, без чёрного окна
    disable_windowed_traceback=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=str(project_root / "resources" / "app.ico"),
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="HVAC Calculator",
)
