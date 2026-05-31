# -*- coding: utf-8 -*-
r"""HVAC Calculator v3.0 — точка входа.

Запуск с GUI:
    python hvac_calc.py

Запуск в командном режиме:
    python hvac_calc.py cli spaces.csv thermal.csv result.xlsx [-tхол] [-tтепл] [город]

Пример:
    python hvac_calc.py cli D:\HVAC\spaces.csv D:\HVAC\thermal_all.csv result.xlsx -16 36 "Ташкент"
"""

import sys


if __name__ == "__main__":
    if len(sys.argv) >= 4 and sys.argv[1] == "cli":
        from hvac.cli import run_cli
        run_cli(sys.argv[2], sys.argv[3], sys.argv[4],
                t_out_heating=float(sys.argv[5]) if len(sys.argv) > 5 else -16.0,
                t_out_cooling=float(sys.argv[6]) if len(sys.argv) > 6 else 36.0,
                city=sys.argv[7] if len(sys.argv) > 7 else "")
    else:
        from hvac.ui_qt import run_gui
        sys.exit(run_gui())
