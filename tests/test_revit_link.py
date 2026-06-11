# -*- coding: utf-8 -*-
"""Тесты живого моста с Revit (hvac/revit_link.py).

Revit в тестах не нужен: протокол проверяется фейковым сокет-сервером,
который ведёт себя как плагин (ответ без разделителя, сокет не
закрывается), обёртки — подменой send_code, а C#-шаблоны — проверками
согласованности с форматом CSV, который читает data_loader.
"""

import json
import socket
import threading

import pytest

from hvac import revit_link
from hvac.models import Space
from hvac.project import HVACProject


# ============================================================================
# Фейковый плагин Revit
# ============================================================================

class FakeRevitPlugin:
    """Однопоточный сервер: принимает 1 запрос, отвечает как плагин."""

    def __init__(self, response: dict):
        self.response = response
        self.received = None
        self._srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._srv.bind(("127.0.0.1", 0))
        self._srv.listen(1)
        self.port = self._srv.getsockname()[1]
        self._thread = threading.Thread(target=self._serve, daemon=True)
        self._thread.start()

    def _serve(self):
        conn, _ = self._srv.accept()
        conn.settimeout(5)
        buf = b""
        while True:
            try:
                chunk = conn.recv(65536)
            except OSError:
                break
            if not chunk:
                break
            buf += chunk
            try:
                self.received = json.loads(buf.decode("utf-8"))
                break
            except json.JSONDecodeError:
                continue
        # Как настоящий плагин: ответ одним куском, без \n, сокет открыт
        conn.sendall(json.dumps(self.response, ensure_ascii=False)
                     .encode("utf-8"))
        self._thread_done = True

    def close(self):
        self._srv.close()


def _ok_response(payload) -> dict:
    """Ответ плагина: ExecutionResultInfo с JSON-строкой в result."""
    return {"jsonrpc": "2.0", "id": "1",
            "result": {"success": True,
                       "result": json.dumps(payload, ensure_ascii=False)}}


@pytest.fixture
def plugin(monkeypatch):
    def make(response):
        srv = FakeRevitPlugin(response)
        monkeypatch.setattr(revit_link, "REVIT_PORT", srv.port)
        return srv
    return make


# ============================================================================
# Протокол
# ============================================================================

class TestProtocol:
    def test_send_code_roundtrip(self, plugin):
        srv = plugin(_ok_response({"ok": 1, "title": "Модель"}))
        out = revit_link.send_code("return 1;", timeout=5)
        srv.close()
        assert out == {"ok": 1, "title": "Модель"}
        assert srv.received["method"] == "send_code_to_revit"
        assert srv.received["params"]["code"] == "return 1;"
        assert srv.received["params"]["transactionMode"] == "auto"

    def test_send_code_error_raises(self, plugin):
        srv = plugin({"jsonrpc": "2.0", "id": "1",
                      "result": {"success": False,
                                 "errorMessage": "CS0103: ..."}})
        with pytest.raises(RuntimeError, match="CS0103"):
            revit_link.send_code("bad code;", timeout=5)
        srv.close()

    def test_jsonrpc_error_raises(self, plugin):
        srv = plugin({"jsonrpc": "2.0", "id": "1",
                      "error": {"code": -32601, "message": "no method"}})
        with pytest.raises(RuntimeError, match="no method"):
            revit_link.call("nope", timeout=5)
        srv.close()

    def test_not_connected(self, monkeypatch):
        # Свободный порт без слушателя
        s = socket.socket()
        s.bind(("127.0.0.1", 0))
        free_port = s.getsockname()[1]
        s.close()
        monkeypatch.setattr(revit_link, "REVIT_PORT", free_port)
        with pytest.raises(revit_link.RevitNotConnected):
            revit_link.call("ping", timeout=2)
        assert revit_link.ping(timeout=2) is False


# ============================================================================
# Обёртки import / writeback
# ============================================================================

def _project_with_results() -> HVACProject:
    p = HVACProject()
    p.params.apply_city("Ташкент")
    sp = Space(space_id="100500", number="R1", name="Офис", level="L1",
               area_m2=25, volume_m3=75, height_m=3,
               heat_loss_w=1500, heat_gain_w=2000)
    p.spaces.append(sp)
    p._space_by_id[sp.space_id] = sp
    return p


def _fake_pass_send(calls):
    """Фейковый send_code: отвечает по шаблону каждого прохода."""
    def fake_send(code, parameters=None, transaction_mode="auto",
                  timeout=120.0):
        calls.append((code, parameters, transaction_mode))
        if code is revit_link.EXPORT_CS_SPACES:
            return {"spaces_rows": 10, "bsc_keys": 55,
                    "source": "Spaces (MEP)"}
        if code is revit_link.EXPORT_CS_THERMAL:
            return {"thermal_rows": 80}
        if code is revit_link.EXPORT_CS_ORPHANS:
            return {"orphan_rows": 2}
        return {}
    return fake_send


class TestWrappers:
    def test_import_runs_three_passes(self, monkeypatch, tmp_path):
        calls = []
        monkeypatch.setattr(revit_link, "send_code", _fake_pass_send(calls))
        res = revit_link.import_from_revit(str(tmp_path))
        assert [c[0] for c in calls] == [
            revit_link.EXPORT_CS_SPACES,
            revit_link.EXPORT_CS_THERMAL,
            revit_link.EXPORT_CS_ORPHANS,
        ]
        # все проходы read-only и получают папку
        assert all(c[2] == "none" for c in calls)
        assert all(c[1] == [str(tmp_path)] for c in calls)
        assert res["spaces_rows"] == 10
        assert res["thermal_rows"] == 82        # 80 + 2 orphan
        assert res["orphan_rows"] == 2
        assert res["source"] == "Spaces (MEP)"
        assert res["spaces_csv"].endswith("spaces.csv")

    def test_import_no_orphans_two_passes(self, monkeypatch, tmp_path):
        calls = []
        monkeypatch.setattr(revit_link, "send_code", _fake_pass_send(calls))
        res = revit_link.import_from_revit(str(tmp_path),
                                           collect_orphans=False)
        assert len(calls) == 2
        assert res["thermal_rows"] == 80
        assert res["orphan_rows"] == 0

    def test_import_cleans_temp_files(self, monkeypatch, tmp_path):
        for name in revit_link._IMPORT_TEMP_FILES:
            (tmp_path / name).write_text("x", encoding="utf-8")
        monkeypatch.setattr(revit_link, "send_code", _fake_pass_send([]))
        revit_link.import_from_revit(str(tmp_path))
        for name in revit_link._IMPORT_TEMP_FILES:
            assert not (tmp_path / name).exists(), f"{name} не удалён"

    def test_write_results_creates_csv_and_sends(self, monkeypatch, tmp_path):
        calls = {}

        def fake_send(code, parameters=None, transaction_mode="auto",
                      timeout=120.0):
            calls["parameters"] = parameters
            calls["mode"] = transaction_mode
            return {"updated_spaces": 1, "written_params": 5,
                    "missing_spaces": 0, "model_spaces": 1,
                    "csv_rows": 1, "skipped_columns": []}

        monkeypatch.setattr(revit_link, "send_code", fake_send)
        out_csv = tmp_path / "results.csv"
        res = revit_link.write_results_to_revit(
            _project_with_results(), str(out_csv))
        assert res["updated_spaces"] == 1
        assert calls["mode"] == "auto"          # запись — в транзакции
        assert calls["parameters"] == [str(out_csv)]
        # CSV-артефакт реально создан и содержит данные помещения
        text = out_csv.read_text(encoding="utf-8-sig")
        assert "space_id" in text and "100500" in text


# ============================================================================
# Согласованность C#-шаблонов с контрактом данных
# ============================================================================

_EXPORT_TEMPLATES = ("EXPORT_CS_SPACES", "EXPORT_CS_THERMAL",
                     "EXPORT_CS_ORPHANS")
_ALL_TEMPLATES = _EXPORT_TEMPLATES + (
    "WRITEBACK_CS", "SNAPSHOT_CS", "COLOR_CS", "CLEAR_COLOR_CS",
    "EQUIPMENT_CS", "FACADE_PROBE_CS")


class TestCSharpTemplates:
    def test_braces_balanced(self):
        for name in _ALL_TEMPLATES:
            cs = getattr(revit_link, name)
            assert cs.count("{") == cs.count("}"), f"{name}: несбаланс. {{}}"
            assert cs.count("(") == cs.count(")"), f"{name}: несбаланс. ()"

    def test_requests_fit_plugin_buffer(self):
        """КРИТИЧНО: плагин читает запрос одним буфером 8192 байта
        (проверено на живом Revit). Каждый проход после минификации
        обязан влезать вместе с JSON-обвязкой."""
        for name in _ALL_TEMPLATES:
            code = revit_link.minify_cs(getattr(revit_link, name))
            req = json.dumps(
                {"jsonrpc": "2.0", "id": "1",
                 "method": "send_code_to_revit",
                 "params": {"code": code,
                            "parameters": ["D:\\some\\folder\\path", "1"],
                            "transactionMode": "auto"}},
                ensure_ascii=False).encode("utf-8")
            assert len(req) <= 8192, \
                f"{name}: запрос {len(req)} байт > буфера плагина 8192"

    def test_minify_strips_comments_keeps_strings(self):
        src = ('// комментарий\n'
                '    string s = "a // not comment";\n'
                '\n'
                '    return s;\n')
        out = revit_link.minify_cs(src)
        assert "комментарий" not in out
        assert '"a // not comment"' in out
        assert out == 'string s = "a // not comment";\nreturn s;'

    def test_export_emits_loader_columns(self):
        """Заголовки CSV в C# совпадают с колонками, которые читает
        data_loader (load_spaces / load_thermal)."""
        cs = "\n".join(getattr(revit_link, n) for n in _EXPORT_TEMPLATES)
        spaces_header = ("id,category,number,name,level,area,volume,"
                         "height,zone,heating_load,cooling_load")
        assert spaces_header in cs, "spaces.csv: заголовок не совпадает"
        thermal_header = (
            "space_id,space_number,space_name,space_level,row_type,"
            "is_exterior_wall,element_id,link_model,category,family,type,"
            "element_level,boundary_length_m,space_height_m,approx_area_m2,"
            "element_area,thickness,function,thermal_value,host_element_id,"
            "boundary_space_count,orientation_deg")
        assert thermal_header in cs, "thermal_all.csv: заголовок не совпадает"

    def test_export_row_types_match_loader(self):
        """data_loader различает external_wall / opening — оба есть."""
        cs = "\n".join(getattr(revit_link, n) for n in _EXPORT_TEMPLATES)
        assert '"external_wall"' in cs
        assert '"opening"' in cs
        assert '"hosted by exterior wall"' in cs
        assert '"curtain (orphan)"' in cs

    def test_writeback_covers_io_revit_columns(self):
        """Каждая колонка результата io_revit обрабатывается в C#-записи."""
        from hvac.io_revit import REVIT_FIELDS
        for col, _param, _kind, _acc in REVIT_FIELDS:
            assert f'"{col}"' in revit_link.WRITEBACK_CS, \
                f"writeback не обрабатывает колонку {col}"

    def test_writeback_targets_documented_params(self):
        """Имена параметров Revit согласованы с io_revit.REVIT_FIELDS."""
        from hvac.io_revit import REVIT_FIELDS
        for _col, param, _kind, _acc in REVIT_FIELDS:
            assert f'"{param}"' in revit_link.WRITEBACK_CS, \
                f"writeback не знает параметр {param}"

    def test_no_bare_io_or_newtonsoft_usings(self):
        """System.IO/Newtonsoft доступны только с полным именем —
        проверяем, что нет коротких обращений File./Path. без префикса."""
        import re
        for name in _ALL_TEMPLATES:
            cs = getattr(revit_link, name)
            assert not re.search(r"(?<![\w.])File\.", cs), \
                f"{name}: File. без префикса System.IO"
            assert not re.search(r"(?<![\w.])Directory\.", cs), \
                f"{name}: Directory. без префикса System.IO"
            assert not re.search(r"(?<![\w.])JsonConvert\.", cs), \
                f"{name}: JsonConvert. без префикса Newtonsoft.Json"


# ============================================================================
# Снимок модели и дифф
# ============================================================================

_SNAPSHOT_DATA = ("101\tR1\tОфис\tL1\t25.5\t76.5\n"
                  "102\tR2\tХолл\tL1\t40.0\t120.0\n")


class TestSnapshotAndDiff:
    def _patch_snapshot(self, monkeypatch, data=_SNAPSHOT_DATA, count=2):
        def fake_send(code, parameters=None, transaction_mode="auto",
                      timeout=120.0):
            assert code is revit_link.SNAPSHOT_CS
            assert transaction_mode == "none"      # снимок read-only
            return {"count": count, "source": "Spaces (MEP)", "data": data}
        monkeypatch.setattr(revit_link, "send_code", fake_send)

    def test_snapshot_parses_rows(self, monkeypatch):
        self._patch_snapshot(monkeypatch)
        snap = revit_link.snapshot_spaces()
        assert set(snap) == {"101", "102"}
        assert snap["101"]["name"] == "Офис"
        assert snap["101"]["area_m2"] == pytest.approx(25.5)
        assert snap["102"]["volume_m3"] == pytest.approx(120.0)

    def test_diff_categories(self, monkeypatch):
        """101 изменился (площадь), 102 новый, 103 удалён из Revit."""
        self._patch_snapshot(monkeypatch)
        p = HVACProject()
        p.params.apply_city("Ташкент")
        for sid, num, name, area in (("101", "R1", "Офис", 20.0),
                                     ("103", "R3", "Архив", 15.0)):
            sp = Space(space_id=sid, number=num, name=name, level="L1",
                       area_m2=area, volume_m3=area * 3, height_m=3)
            p.spaces.append(sp)
            p._space_by_id[sid] = sp
        diff = revit_link.diff_with_project(p)
        assert not diff.in_sync
        assert diff.source == "Spaces (MEP)"
        assert [r["id"] for r in diff.added] == ["102"]
        assert [r["id"] for r in diff.removed] == ["103"]
        assert [r["id"] for r in diff.changed] == ["101"]
        assert any("area" in w for w in diff.changed[0]["what"])
        assert diff.unchanged == 0

    def test_diff_in_sync(self, monkeypatch):
        self._patch_snapshot(monkeypatch)
        p = HVACProject()
        p.params.apply_city("Ташкент")
        for sid, num, name, area, vol in (("101", "R1", "Офис", 25.5, 76.5),
                                          ("102", "R2", "Холл", 40.0, 120.0)):
            sp = Space(space_id=sid, number=num, name=name, level="L1",
                       area_m2=area, volume_m3=vol, height_m=3)
            p.spaces.append(sp)
            p._space_by_id[sid] = sp
        diff = revit_link.diff_with_project(p)
        assert diff.in_sync
        assert diff.unchanged == 2

    def test_diff_tolerates_small_drift(self, monkeypatch):
        """Дрейф площади в пределах допуска — не «изменение»
        (AsValueString округляет)."""
        self._patch_snapshot(monkeypatch, data="101\tR1\tОфис\tL1\t25.6\t76.6\n",
                             count=1)
        p = HVACProject()
        p.params.apply_city("Ташкент")
        sp = Space(space_id="101", number="R1", name="Офис", level="L1",
                   area_m2=25.5, volume_m3=76.5, height_m=3)
        p.spaces.append(sp)
        p._space_by_id["101"] = sp
        diff = revit_link.diff_with_project(p)
        assert diff.in_sync


# ============================================================================
# Раскраска результатов
# ============================================================================

class TestColorSpaces:
    def _project(self):
        p = HVACProject()
        p.params.apply_city("Ташкент")
        for i, q in enumerate((100.0, 200.0, 300.0), start=1):
            sp = Space(space_id=str(i), number=f"R{i}", name="Оф",
                       level="L1", area_m2=10, volume_m3=30, height_m=3,
                       heat_loss_w=q, heat_gain_w=q * 1.5)
            sp.ach_calculated = float(i)
            p.spaces.append(sp)
            p._space_by_id[sp.space_id] = sp
        return p

    def test_color_sends_gradient_csv(self, monkeypatch):
        captured = {}

        def fake_send(code, parameters=None, transaction_mode="auto",
                      timeout=120.0):
            captured["code"] = code
            captured["mode"] = transaction_mode
            captured["path"] = parameters[0]
            with open(parameters[0], encoding="utf-8") as f:
                captured["csv"] = f.read().splitlines()
            return {"colored": 3, "missing": 0, "failed": 0,
                    "view": "Level 1"}

        monkeypatch.setattr(revit_link, "send_code", fake_send)
        res = revit_link.color_spaces_in_revit(self._project(),
                                               "heating_w_m2")
        assert captured["code"] is revit_link.COLOR_CS
        assert captured["mode"] == "auto"          # запись — в транзакции
        lines = captured["csv"]
        assert lines[0] == "space_id,r,g,b"
        assert len(lines) == 4
        # Холодное помещение — синий конец градиента, горячее — красный
        assert lines[1] == "1,59,130,246"
        assert lines[3] == "3,239,68,68"
        # Временный CSV удалён после вызова
        import os
        assert not os.path.exists(captured["path"])
        assert res["metric"] == "heating_w_m2"
        assert res["vmin"] == pytest.approx(10.0)
        assert res["vmax"] == pytest.approx(30.0)

    def test_unknown_metric_raises(self):
        with pytest.raises(ValueError, match="метрик"):
            revit_link.color_spaces_in_revit(self._project(), "nope")

    def test_empty_project_raises(self):
        p = HVACProject()
        p.params.apply_city("Ташкент")
        with pytest.raises(ValueError, match="нет помещений"):
            revit_link.color_spaces_in_revit(p)

    def test_clear_colors(self, monkeypatch):
        def fake_send(code, parameters=None, transaction_mode="auto",
                      timeout=120.0):
            assert code is revit_link.CLEAR_COLOR_CS
            return {"cleared": 5, "view": "Level 1"}
        monkeypatch.setattr(revit_link, "send_code", fake_send)
        res = revit_link.clear_space_colors_in_revit()
        assert res["cleared"] == 5

    def test_gradient_endpoints(self):
        assert revit_link._gradient_color(0.0) == (59, 130, 246)
        assert revit_link._gradient_color(0.5) == (250, 204, 21)
        assert revit_link._gradient_color(1.0) == (239, 68, 68)
        # Клиппинг за пределами [0,1]
        assert revit_link._gradient_color(-1.0) == (59, 130, 246)
        assert revit_link._gradient_color(2.0) == (239, 68, 68)


# ============================================================================
# Импорт оборудования помещений
# ============================================================================

# 9 полей: cat, space_id, family, type, flow, sys_class, sys_name, heat, cool
_EQUIP_DATA = (
    "T\t101\tДиффузор вихревой\tDN200\t250\tПриточный воздух\tП1\t\t\n"
    "T\t101\tДиффузор вихревой\tDN200\t250\tПриточный воздух\tП1\t\t\n"
    "T\t101\tРешётка АМН\t300x150\t400\t\tВ2\t\t\n"
    "T\t\tДиффузор\tDN160\t150\tSupply Air\tП1\t\t\n"
    "T\t999\tДиффузор\tDN160\t150\tSupply Air\tП1\t\t\n"
    "M\t101\tРадиатор панельный\tтип 11 500x1000\t\t\t\t1200\t\n"
    "M\t101\tРадиатор панельный\tтип 11 500x800\t\t\t\t960\t\n"
    "M\t102\tФанкойл кассетный\tFCU-600\t\t\t\t\t3500\n"
    "M\t102\tНасос циркуляционный\tUPS 25-40\t\t\t\t\t\n"
    "S\t102\tШкаф\tШ-1\t\t\t\t\t\n"
)


def _equip_project() -> HVACProject:
    p = HVACProject()
    p.params.apply_city("Ташкент")
    for sid, num, name in (("101", "R1", "Офис"), ("102", "R2", "Серверная")):
        sp = Space(space_id=sid, number=num, name=name, level="L1",
                   area_m2=25, volume_m3=75, height_m=3)
        p.spaces.append(sp)
        p._space_by_id[sid] = sp
    return p


class TestEquipmentImport:
    def test_snapshot_parses_rows(self, monkeypatch):
        def fake_send(code, parameters=None, transaction_mode="auto",
                      timeout=120.0):
            assert code is revit_link.EQUIPMENT_CS
            assert transaction_mode == "none"      # снимок read-only
            return {"count": 10, "no_space": 1, "data": _EQUIP_DATA}
        monkeypatch.setattr(revit_link, "send_code", fake_send)
        rows = revit_link.snapshot_equipment()
        assert len(rows) == 10
        assert rows[0] == {"cat": "T", "space_id": "101",
                           "family": "Диффузор вихревой", "type": "DN200",
                           "flow_m3h": 250.0, "sys_class": "Приточный воздух",
                           "sys_name": "П1", "heat_w": 0.0, "cool_w": 0.0}
        assert rows[5]["heat_w"] == pytest.approx(1200.0)
        assert rows[7]["cool_w"] == pytest.approx(3500.0)

    def test_classify_air_terminals(self):
        def t(family, type_="", sys_class="", sys_name=""):
            return revit_link.classify_equipment_row(
                {"cat": "T", "family": family, "type": type_,
                 "sys_class": sys_class, "sys_name": sys_name})
        # Классификация системы важнее имени
        assert t("Решётка", sys_class="Отработанный воздух") == \
            ("exhaust", "Решётка настенная")
        assert t("Решётка потолочная", sys_class="Supply Air") == \
            ("supply", "Решётка потолочная")
        # Фоллбэк — имя системы (П/В), затем имя семейства
        assert t("Диффузор", "DN200", sys_name="P1") == \
            ("supply", "Диффузор круглый")
        assert t("Анемостат", sys_name="В2") == ("exhaust", "Анемостат")
        assert t("Зонт вытяжной", sys_name="В1") == \
            ("exhaust", "Зонт кухонный")
        assert t("Решётка вытяжная") == ("exhaust", "Решётка настенная")
        # Дефолт без признаков — приток
        assert t("Сопло")[0] == "supply"

    def test_classify_mechanical(self):
        def m(family, type_=""):
            return revit_link.classify_equipment_row(
                {"cat": "M", "family": family, "type": type_})
        assert m("Радиатор биметаллический", "500") == \
            ("heating", "Радиатор биметаллический")
        assert m("Конвектор внутрипольный") == \
            ("heating", "Конвектор внутрипольный")
        assert m("Фанкойл канальный", "FCU") == \
            ("cooling", "Фанкойл канальный")
        assert m("Блок VRF настенный") == \
            ("cooling", "Внутр. блок VRF настенный")
        assert m("Сплит-система") == ("cooling", "Сплит-система настенная")
        assert m("Тепловая завеса") == ("heating", "Тепловая завеса")
        # Реальные имена из живой модели: фанкойл «N pipes» без слова
        # «фанкойл», кухонный зонт как механическое оборудование
        assert m("Clint DWX 4 PIPES", "DWX 183") == \
            ("cooling", "Фанкойл (отопл.+охл.)")
        assert m("Carrier 42N 2 pipes") == ("cooling", "Фанкойл кассетный")
        assert m("ADSK_Зонт вытяжной", "Зонт вытяжной") == \
            ("exhaust", "Зонт кухонный")
        assert m("Насос циркуляционный") is None
        assert m("Люк технического обслуживания") is None

    def test_plan_aggregates_by_space_and_slot(self):
        plan = revit_link.plan_equipment_import(
            _equip_project(), rows=self._rows())
        assert plan.total == 8           # без насоса (unrec) и шкафа (S)
        assert plan.no_space == 1
        assert plan.unmatched == 1
        assert plan.skipped_other == 1
        assert plan.by_slot == {"supply": 2, "exhaust": 1,
                                "heating": 2, "cooling": 1}
        up = plan.updates["101"]
        assert up["supply_terminal_type"] == "Диффузор вихревой"
        assert up["supply_terminal_model"] == "Диффузор вихревой DN200"
        assert up["supply_terminal_qty"] == 2
        assert up["supply_terminal_flow_m3h"] == pytest.approx(250.0)
        assert up["exhaust_terminal_type"] == "Решётка настенная"
        assert up["exhaust_terminal_qty"] == 1
        assert up["exhaust_terminal_flow_m3h"] == pytest.approx(400.0)
        assert up["heating_terminal_type"] == "Радиатор стальной"
        assert up["heating_terminal_qty"] == 2
        assert up["heating_terminal_power_w"] == pytest.approx(1080.0)
        up2 = plan.updates["102"]
        assert up2["cooling_terminal_type"] == "Фанкойл кассетный"
        assert up2["cooling_terminal_power_w"] == pytest.approx(3500.0)
        assert plan.unrecognized == ["Насос циркуляционный UPS 25-40"]
        assert plan.has_updates

    @staticmethod
    def _rows():
        """_EQUIP_DATA через тот же парсер, что и снимок."""
        out = []
        for line in _EQUIP_DATA.splitlines():
            parts = line.split("\t")
            out.append({
                "cat": parts[0], "space_id": parts[1],
                "family": parts[2], "type": parts[3],
                "flow_m3h": float(parts[4] or 0),
                "sys_class": parts[5], "sys_name": parts[6],
                "heat_w": float(parts[7] or 0),
                "cool_w": float(parts[8] or 0),
            })
        return out

    def test_apply_fills_room_equipment(self):
        p = _equip_project()
        plan = revit_link.plan_equipment_import(p, rows=self._rows())
        n = revit_link.apply_equipment_import(p, plan)
        assert n == 2
        eq = p.spaces[0].room_equipment
        assert eq is not None
        assert eq.supply_terminal_qty == 2
        assert eq.supply_total_m3h == pytest.approx(500.0)
        assert eq.heating_total_w == pytest.approx(2160.0)
        # Слот охлаждения помещения 101 не затронут
        assert eq.cooling_terminal_type == "—"
        eq2 = p.spaces[1].room_equipment
        assert eq2.cooling_terminal_qty == 1
        assert eq2.supply_terminal_qty == 0

    def test_plan_without_updates(self):
        plan = revit_link.plan_equipment_import(_equip_project(), rows=[])
        assert not plan.has_updates
        assert revit_link.apply_equipment_import(_equip_project(), plan) == 0


# ============================================================================
# Лучевая проверка фасадов
# ============================================================================

def _boundary(space_id, eid, row_type="external_wall", is_exterior=True,
              host="", orientation=""):
    from hvac.models import BoundaryElement
    return BoundaryElement(
        space_id=space_id, row_type=row_type, is_exterior=is_exterior,
        element_id=eid, category="Стены", family="Базовая стена",
        type_name="BL150", boundary_length_m=3.0, space_height_m=3.0,
        approx_area_m2=9.0, element_area_m2=9.0, thickness_mm=160.0,
        function="Наружные слои", host_element_id=host,
        boundary_space_count=1, orientation=orientation, net_area_m2=9.0)


def _facade_project() -> HVACProject:
    p = HVACProject()
    p.params.apply_city("Ташкент")
    for sid, num, name in (("A", "HTL-1128", "FIRE HALL"),
                           ("B", "HTL-101", "ROOM")):
        sp = Space(space_id=sid, number=num, name=name, level="L1",
                   area_m2=10, volume_m3=30, height_m=3)
        p.spaces.append(sp)
        p._space_by_id[sid] = sp
    p.elements.extend([
        _boundary("A", "W1", orientation="N"),         # к шахте → INTERIOR
        _boundary("A", "D1", row_type="opening", host="W1"),  # дверь в W1
        _boundary("B", "W2", orientation="S"),         # настоящий фасад
        _boundary("A", "W3", orientation="E"),         # NOSPACE — не трогаем
        _boundary("A", "W4", is_exterior=False),       # уже внутренняя
    ])
    # Ложные фасады W1 (N) + W3 (E) дали FIRE HALL признак «угловое»
    p.spaces[0].is_corner = True
    return p


_PROBE_DATA = ("W1\tINTERIOR\tHTL-1129\t3.0\n"
               "W2\tFACADE\t\t\n"
               "W3\tNOSPACE\t\t\n")


class TestFacadeCheck:
    def test_probe_sends_ids_file_and_parses(self, monkeypatch, tmp_path):
        captured = {}

        def fake_send(code, parameters=None, transaction_mode="auto",
                      timeout=120.0):
            assert code is revit_link.FACADE_PROBE_CS
            assert transaction_mode == "none"      # проба read-only
            with open(parameters[0], encoding="utf-8") as f:
                captured["ids"] = f.read().splitlines()
            captured["path"] = parameters[0]
            return {"walls": 3, "facade": 1, "interior": 1, "nospace": 1,
                    "notfound": 0, "notwall": 0, "data": _PROBE_DATA}

        monkeypatch.setattr(revit_link, "send_code", fake_send)
        out = revit_link.probe_facades(["W1", "W2", "W3"])
        assert captured["ids"] == ["W1", "W2", "W3"]
        # Временный файл со списком id удалён
        import os
        assert not os.path.exists(captured["path"])
        assert out["W1"] == {"verdict": "INTERIOR", "hit": "HTL-1129",
                             "dist_m": 3.0}
        assert out["W2"]["verdict"] == "FACADE"
        assert out["W3"]["verdict"] == "NOSPACE"

    def test_plan_classifies_and_inherits_openings(self):
        verdicts = {
            "W1": {"verdict": "INTERIOR", "hit": "HTL-1129", "dist_m": 3.0},
            "W2": {"verdict": "FACADE", "hit": "", "dist_m": 0.0},
            "W3": {"verdict": "NOSPACE", "hit": "", "dist_m": 0.0},
        }
        plan = revit_link.plan_facade_check(_facade_project(),
                                            verdicts=verdicts)
        # Кандидаты — только наружные стены (W1, W2, W3); W4 внутренняя,
        # D1 — проём (наследует вердикт хозяина W1)
        assert plan.checked == 3
        assert plan.facades == 1
        assert plan.no_geometry == 1
        assert sorted(plan.pairs) == [("A", "D1"), ("A", "W1")]
        assert plan.has_updates
        assert plan.to_interior[0]["hit"] == "HTL-1129"

    def test_apply_flips_and_recalculates(self):
        p = _facade_project()
        verdicts = {
            "W1": {"verdict": "INTERIOR", "hit": "HTL-1129", "dist_m": 3.0},
            "W2": {"verdict": "FACADE", "hit": "", "dist_m": 0.0},
            "W3": {"verdict": "NOSPACE", "hit": "", "dist_m": 0.0},
        }
        plan = revit_link.plan_facade_check(p, verdicts=verdicts)
        n = revit_link.apply_facade_check(p, plan)
        assert n == 2
        by_eid = {(e.space_id, e.element_id): e for e in p.elements}
        assert by_eid[("A", "W1")].is_exterior is False
        assert by_eid[("A", "W1")].user_modified is True   # в element_overrides
        assert by_eid[("A", "D1")].is_exterior is False
        assert by_eid[("B", "W2")].is_exterior is True     # фасад не тронут
        assert by_eid[("A", "W3")].is_exterior is True     # NOSPACE не тронут
        # После снятия W1 у A осталась одна ориентация (E) — «угловое» снято
        assert p.spaces[0].is_corner is False

    def test_plan_empty_project(self):
        p = HVACProject()
        p.params.apply_city("Ташкент")
        plan = revit_link.plan_facade_check(p, verdicts={})
        assert plan.checked == 0
        assert not plan.has_updates


class TestRoundTripThroughLoader:
    """Импортированный CSV (как его пишет C#) понимает data_loader."""

    def test_loader_accepts_csv_in_export_format(self, tmp_path):
        from hvac.data_loader import load_spaces, load_thermal
        spaces_csv = tmp_path / "spaces.csv"
        spaces_csv.write_text(
            "id,category,number,name,level,area,volume,height,zone,"
            "heating_load,cooling_load\r\n"
            "1001,Пространства,R1,Офис,L1,25.5,76.5,3.0,,,\r\n",
            encoding="utf-8-sig")
        thermal_csv = tmp_path / "thermal_all.csv"
        thermal_csv.write_text(
            "space_id,space_number,space_name,space_level,row_type,"
            "is_exterior_wall,element_id,link_model,category,family,type,"
            "element_level,boundary_length_m,space_height_m,approx_area_m2,"
            "element_area,thickness,function,thermal_value,host_element_id,"
            "boundary_space_count,orientation_deg\r\n"
            "1001,R1,Офис,L1,external_wall,yes,2002,,Стены,Basic Wall,"
            "W200,L1,4.0,3.0,12.0,12.0,200.0,Наружные,0.45,,1,180.0\r\n"
            "1001,R1,Офис,L1,opening,yes,3003,,Окна,Окно,1500x1500,L1,"
            ",,,2.25,,hosted by exterior wall,1.8,2002,1,180.0\r\n",
            encoding="utf-8-sig")

        spaces = load_spaces(str(spaces_csv))
        assert len(spaces) == 1
        assert spaces[0].area_m2 == pytest.approx(25.5)
        assert spaces[0].height_m == pytest.approx(3.0)

        elems = load_thermal(str(thermal_csv), spaces)
        assert len(elems) == 2
        wall = next(e for e in elems if e.row_type == "external_wall")
        assert wall.is_exterior
        assert wall.orientation_deg == pytest.approx(180.0)
        opening = next(e for e in elems if e.row_type == "opening")
        assert opening.host_element_id == "2002"
