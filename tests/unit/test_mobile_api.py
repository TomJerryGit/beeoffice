# tests/test_mobile_api.py
"""
移动端 HTTP 服务器 API 测试

本次更新（优化规划 §1.4）：原测试自行用 127.0.0.1 建服务器，恰好掩盖了
生产代码绑定 0.0.0.0 的事实；而且没有覆盖"无鉴权即可读取全部文档"。
现在补上：
  - 生产绑定地址断言（默认回环，显式开启才绑 0.0.0.0）
  - 无令牌 / 错误令牌 → 403
  - 响应中不得出现通配 CORS 头
  - Host 头校验（抵御 DNS rebinding）
  - HEAD 被拒绝（继承实现会绕过令牌校验并枚举目录）
  - 首页下发 script-src 'self' 的 CSP，且脚本改为外部文件
"""
import http.client
import json
import socket
import threading
import time
import urllib.error
import urllib.request
import pytest


def _free_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _http_get(url, timeout=3):
    """返回 (status, body, headers)；4xx 也返回而不抛异常。"""
    try:
        with urllib.request.urlopen(url, timeout=timeout) as resp:
            return resp.status, resp.read(), dict(resp.headers)
    except urllib.error.HTTPError as e:
        return e.code, e.read(), dict(e.headers)


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
    # 优化规划 §4.2：**不要**由测试写死地址。原先这里写 `server.ip = "127.0.0.1"`，
    # 结果即使生产代码绑定 0.0.0.0（暴露到整个局域网）测试也照样通过。
    # 改为取生产代码**自己算出来**的绑定地址，并让测试服务器绑到它。
    #
    # 注意：不在这里断言 `server.ip` —— 在那个匿名父对象环境下构造函数会提前
    # 返回（`ip` 保持 None），那是夹具环境的产物，并非生产行为主张；
    # 与安全相关的只有**绑定地址**。
    bind_host = server._bind_host()
    assert bind_host == "127.0.0.1", (
        "移动端默认不得全网卡监听（应只监听回环）"
    )
    server.temp_dir.mkdir(parents=True, exist_ok=True)
    server._generate_index()

    handler = server._create_handler()
    httpd = _ThreadingHTTPServer((bind_host, port), handler)
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


def _docs_url(server, token=None):
    tok = server.token if token is None else token
    return f"http://127.0.0.1:{server.port}/api/docs?t={tok}"


# ==================== 绑定地址：生产路径必须默认回环 ====================

class TestBinding:
    def test_default_bind_is_loopback(self, qapp):
        """
        优化规划 §1.4：默认绝不能绑定 0.0.0.0。

        这是原测试遗漏的关键点——它在测试里自己用 127.0.0.1 起服务，
        于是生产代码的 0.0.0.0 从未被断言过。
        """
        from beeoffice.mobile import MobileServer

        parent = _FakeParent(_FakeTabManager([]))
        server = MobileServer(parent)
        assert server.allow_lan is False
        assert server._bind_host() == "127.0.0.1"

    def test_lan_requires_explicit_opt_in(self, qapp):
        from beeoffice.mobile import MobileServer

        parent = _FakeParent(_FakeTabManager([]))
        server = MobileServer(parent, allow_lan=True)
        assert server._bind_host() == "0.0.0.0"


# ==================== 令牌鉴权 ====================

class TestAuth:
    def test_docs_returns_json_with_token(self, mobile_server):
        status, body, _ = _http_get(_docs_url(mobile_server))
        assert status == 200
        data = json.loads(body.decode("utf-8"))
        assert isinstance(data, list)

    def test_docs_denied_without_token(self, mobile_server):
        status, _, _ = _http_get(
            f"http://127.0.0.1:{mobile_server.port}/api/docs"
        )
        assert status == 403, "无令牌必须被拒绝"

    def test_docs_denied_with_wrong_token(self, mobile_server):
        status, _, _ = _http_get(_docs_url(mobile_server, token="wrong"))
        assert status == 403, "错误令牌必须被拒绝"

    def test_view_denied_without_token(self, mobile_server):
        status, _, _ = _http_get(
            f"http://127.0.0.1:{mobile_server.port}/api/view/0"
        )
        assert status == 403

    def test_view_allowed_with_token(self, mobile_server):
        url = (
            f"http://127.0.0.1:{mobile_server.port}"
            f"/api/view/0?t={mobile_server.token}"
        )
        status, body, _ = _http_get(url)
        assert status == 200
        assert "正文内容" in json.loads(body.decode("utf-8"))["html"]

    def test_bearer_token_also_accepted(self, mobile_server):
        conn = http.client.HTTPConnection(
            "127.0.0.1", mobile_server.port, timeout=3
        )
        conn.request(
            "GET", "/api/docs",
            headers={"Authorization": f"Bearer {mobile_server.token}"},
        )
        resp = conn.getresponse()
        assert resp.status == 200
        conn.close()

    def test_token_is_random_and_url_contains_it(self, qapp):
        from beeoffice.mobile import MobileServer

        parent = _FakeParent(_FakeTabManager([]))
        a, b = MobileServer(parent), MobileServer(parent)
        assert a.token and b.token
        assert a.token != b.token, "令牌必须是每次启动随机生成"
        assert len(a.token) >= 16
        a.port, a.ip = 8888, "127.0.0.1"
        assert a.token in a.access_url()


# ==================== 响应头加固 ====================

class TestHeaders:
    def test_no_wildcard_cors_header(self, mobile_server):
        """
        优化规划 §1.4：通配 CORS 会让同机浏览器中的任意网页跨域读取
        本服务返回的文档内容，必须彻底移除。
        """
        _, _, headers = _http_get(_docs_url(mobile_server))
        assert "Access-Control-Allow-Origin" not in headers

    def test_index_sends_restrictive_csp(self, mobile_server):
        status, body, headers = _http_get(
            f"http://127.0.0.1:{mobile_server.port}/?t={mobile_server.token}"
        )
        assert status == 200
        csp = headers.get("Content-Security-Policy", "")
        assert "script-src 'self'" in csp, (
            "首页必须下发 script-src 'self'，否则注入的事件属性仍会执行"
        )
        assert "default-src 'none'" in csp

    def test_index_uses_external_script(self, mobile_server):
        """脚本必须外置，否则 CSP 无法用 script-src 'self' 生效。"""
        _, body, _ = _http_get(
            f"http://127.0.0.1:{mobile_server.port}/?t={mobile_server.token}"
        )
        text = body.decode("utf-8")
        assert '<script src="/app.js"></script>' in text
        assert "<script>" not in text, "首页不应再有内联脚本"

        status, js, headers = _http_get(
            f"http://127.0.0.1:{mobile_server.port}/app.js"
        )
        assert status == 200
        assert "TOKEN" in js.decode("utf-8")

    def test_nosniff_header_present(self, mobile_server):
        _, _, headers = _http_get(_docs_url(mobile_server))
        assert headers.get("X-Content-Type-Options") == "nosniff"


# ==================== Host 头 / HEAD ====================

class TestHostAndMethod:
    def test_bad_host_is_rejected(self, mobile_server):
        """抵御 DNS rebinding：只有白名单内的 Host 才被接受。"""
        conn = http.client.HTTPConnection(
            "127.0.0.1", mobile_server.port, timeout=3
        )
        conn.request(
            "GET", f"/api/docs?t={mobile_server.token}",
            headers={"Host": "evil.example.com"},
        )
        resp = conn.getresponse()
        assert resp.status == 403
        conn.close()

    def test_head_is_rejected(self, mobile_server):
        """
        继承的 do_HEAD 会绕过令牌校验，并可枚举 CWD 树下文件/目录的
        存在性、大小与修改时间，因此显式拒绝。
        """
        conn = http.client.HTTPConnection(
            "127.0.0.1", mobile_server.port, timeout=3
        )
        conn.request("HEAD", f"/api/docs?t={mobile_server.token}")
        resp = conn.getresponse()
        assert resp.status == 403
        conn.close()


# ==================== 既有回归：不得劫持工作目录 ====================

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
