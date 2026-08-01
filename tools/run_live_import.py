# -*- coding: utf-8 -*-
"""Прогон производственного import_from_revit (как кнопка в приложении)
на живой модели в отдельную папку — для проверки интеграции чистого витража."""
import json
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
sys.path.insert(0, _ROOT)

from hvac import revit_link as rl  # noqa: E402

OUT = sys.argv[1] if len(sys.argv) > 1 else os.path.join(_HERE, "out", "live_test")
res = rl.import_from_revit(OUT)   # clean_glazing=True по умолчанию
print(json.dumps(res, ensure_ascii=False, indent=2))
