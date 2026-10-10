# tests/test_mobile_api.py
"""移动端 HTTP 服务器 API 测试"""
import json
import socket
import threading
import time
import urllib.request
import urllib.error
import pytest


def _free_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _http_get(url, timeout=3):
    try:
        with urllib.request.urlopen(url, timeout=timeout) as resp:
            return resp.status, resp.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()


class _FakeWidgetWithContent:
    def content(self):
        return "# 测试标题\n\n正文内容"


class _FakeTabManager:
    def __init__(self, widgets):
        self._widgets = widgets
        self._titles = [f"tab-{i}" for i in range(len(widgets))]

    def count(self):
        return len(self._widgets)

    def widget(self, i):
        if 0 <= i < len(self._widgets):
            return self._widgets[i]
        return None

    def tabText(self, i):
        return self._titles[i]


class _FakeParent:
    def __init__(self, tm):
        self.tab_manager = tm


@pytest.fixture
def mobile_server(qapp):
    from beeoffice.mobile import MobileServer, _ThreadingHTTPServer

    parent = _FakeParent(_FakeTabManager([_FakeWidgetWithContent()]))
    server = MobileServer(parent)
    port = _free_port()
    server.port = port
    server.ip = "127.0.0.1"
    server.temp_dir.mkdir(parents=True, exist_ok=True)
    server._generate_index()

    handler = server._create_handler()
    httpd = _ThreadingHTTPServer(("127.0.0.1", port), handler)
    server.server = httpd
    server.thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    server.thread.start()

    for _ in range(20):
        try:
            _http_get(f"http://127.0.0.1:{port}/api/docs", timeout=1)
            break
        except Exception:
            time.sleep(0.05)

    yield server
    server.stop()


class TestDocsAPI:
    def test_docs_returns_json(self, mobile_server):
        status, body = _http_get(
            f"http://127.0.0.1:{mobile_server.port}/api/docs"
        )
        assert status == 200
        data = json.loads(body.decode("utf-8"))
        assert isinstance(data, list)


class TestNoCwdHijack:
    def test_cwd_unchanged_after_start(self, qapp):
        import os
        from beeoffice.mobile import MobileServer
        before = os.getcwd()
        parent = _FakeParent(_FakeTabManager([_FakeWidgetWithContent()]))
        server = MobileServer(parent)
        server.temp_dir.mkdir(parents=True, exist_ok=True)
        server._generate_index()
        after = os.getcwd()
        assert before == after
