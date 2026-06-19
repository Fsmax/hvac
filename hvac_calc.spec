# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec для HVAC Calculator.

Сборка:
    pip install pyinstaller
    pyinstaller hvac_calc.spec

Результат: dist/HVAC Calculator/HVAC Calculator.exe (~120 МБ с PySide6).
Для single-file бандла поменяйте onedir на onefile в EXE() ниже —
будет один .exe ~80 МБ с медленным первым стартом (распаковка).
"""
from pathlib import Path

block_cipher = None

# Папка с проектом (где лежит .spec)
project_root = Path(SPECPATH)

# Подключаем QSS-темы как data-файлы (PyInstaller не видит их через __file__
# в обычной сборке)
qss_files = [
    (str(project_root / "hvac" / "ui_qt" / "theme" / "dark.qss"),
     "hvac/ui_qt/theme"),
    (str(project_root / "hvac" / "ui_qt" / "theme" / "light.qss"),
     "hvac/ui_qt/theme"),
    # Иконка приложения — рядом с .exe в подпапке resources/
    (str(project_root / "resources" / "app.ico"), "resources"),
    (str(project_root / "resources" / "app.png"), "resources"),
]

# Каталоги-данные (климат, типы помещений) — внешние JSON, читаются
# через importlib.resources. В сборке должны лежать в hvac/catalogs/data.
catalog_files = [
    (str(project_root / "hvac" / "catalogs" / "data" / "climate.json"),
     "hvac/catalogs/data"),
    (str(project_root / "hvac" / "catalogs" / "data" / "room_types.json"),
     "hvac/catalogs/data"),
    (str(project_root / "hvac" / "catalogs" / "data" / "shnq_energy.json"),
     "hvac/catalogs/data"),
    (str(project_root / "hvac" / "catalogs" / "data" / "kmk_thermal.json"),
     "hvac/catalogs/data"),
    (str(project_root / "hvac" / "catalogs" / "data" / "radiators.json"),
     "hvac/catalogs/data"),
    (str(project_root / "hvac" / "catalogs" / "data" / "fancoils.json"),
     "hvac/catalogs/data"),
    (str(project_root / "hvac" / "catalogs" / "data" / "fans.json"),
     "hvac/catalogs/data"),
    (str(project_root / "hvac" / "catalogs" / "data" / "grilles.json"),
     "hvac/catalogs/data"),
]

# Скрытые импорты, которые анализатор может пропустить
hidden = [
    "hvac.ui_qt",
    "hvac.engine.sp50",
    "hvac.engine.ventilation",
    "matplotlib.backends.backend_qtagg",
    "openpyxl",
    "reportlab",
    "docx",        # python-docx — импортируется лениво в io_docx
]


a = Analysis(
    ["hvac_calc.py"],
    pathex=[str(project_root)],
    binaries=[],
    datas=qss_files + catalog_files,
    hiddenimports=hidden,
    hookspath=[],
    runtime_hooks=[],
    excludes=[
        # Урезаем — PySide6 тянет много чего не нужного
        "PySide6.QtNetwork",
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
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

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
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="HVAC Calculator",
)
