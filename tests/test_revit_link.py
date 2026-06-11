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
_ALL_TEMPLATES = _EXPORT_TEMPLATES + ("WRITEBACK_CS",)


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
