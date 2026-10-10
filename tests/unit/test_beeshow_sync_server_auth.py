# tests/unit/test_beeshow_sync_server_auth.py
"""
蜜演同步服务器加固回归（优化规划 §1.4）。

原状态（BeeOffice-分析报告.md §4.2）：
  * `SyncServer(host="0.0.0.0")` —— 绑定所有网卡；UI 还会把
    `http://<局域网IP>:8765/sync` 直接展示给用户去扫码。
  * HTTP 与 WebSocket 都**没有任何鉴权**。
  * 三个响应都带 `Access-Control-Allow-Origin: *`。
  * WebSocket 握手不校验 Origin → 演示者本机浏览器中的任意网页都能连上
    广播通道（跨站 WebSocket 劫持）。

加固后：
  * 默认只监听 127.0.0.1，需要观众时必须显式 allow_lan=True。
  * 一次性令牌（secrets.token_urlsafe）同时保护 HTTP 接口与 WS 握手。
  * 去掉通配 CORS 头；握手校验 Origin。
"""
import http.client
import socket
import time
import urllib.error
import urllib.request

import pytest


def _free_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _get(url, timeout=3):
    try:
        with urllib.request.urlopen(url, timeout=timeout) as resp:
            return resp.status, resp.read(), dict(resp.headers)
    except urllib.error.HTTPError as e:
        return e.code, e.read(), dict(e.headers)


# ==================== 绑定地址 ====================

class TestBinding:
    def test_default_host_is_loopback(self):
        """默认绝不允许绑定 0.0.0.0。"""
        from beeoffice.plugins.beeshow_sync_server import SyncServer

        assert SyncServer().host == "127.0.0.1"

    def test_allow_lan_binds_all_interfaces(self):
        from beeoffice.plugins.beeshow_sync_server import SyncServer

        assert SyncServer(allow_lan=True).host == "0.0.0.0"

    def test_explicit_host_override_still_works(self):
        """为兼容旧调用保留 host 覆盖能力。"""
        from beeoffice.plugins.beeshow_sync_server import SyncServer

        assert SyncServer(host="10.0.0.5").host == "10.0.0.5"


# ==================== 令牌 ====================

class TestToken:
    def test_token_is_random_per_instance(self):
        from beeoffice.plugins.beeshow_sync_server import SyncServer

        a, b = SyncServer(), SyncServer()
        assert a.token and b.token and a.token != b.token
        assert len(a.token) >= 16

    def test_viewer_url_contains_token(self):
        from beeoffice.plugins.beeshow_sync_server import SyncServer

        server = SyncServer()
        url = server.get_viewer_url()
        assert server.token in url
        assert url.startswith("http://127.0.0.1:"), (
            "未开启局域网时应展示回环地址"
        )


# ==================== 握手鉴权 ====================

class TestHandshakeAuth:
    @staticmethod
    def _server():
        from beeoffice.plugins.beeshow_sync_server import SyncServer

        s = SyncServer()
        s.http_port = 8765
        return s

    def test_valid_token_and_matching_origin(self):
        s = self._server()
        headers = [
            "GET /?t=" + s.token + " HTTP/1.1",
            "Origin: http://127.0.0.1:8765",
        ]
        assert s._handshake_allowed("/?t=" + s.token, headers) is True

    def test_missing_token_rejected(self):
        s = self._server()
        headers = ["GET / HTTP/1.1", "Origin: http://127.0.0.1:8765"]
        assert s._handshake_allowed("/", headers) is False

    def test_wrong_token_rejected(self):
        s = self._server()
        headers = ["GET /?t=nope HTTP/1.1"]
        assert s._handshake_allowed("/?t=nope", headers) is False

    def test_foreign_origin_rejected(self):
        """跨站 WebSocket 劫持：别的网站不能借用演示者的浏览器连上来。"""
        s = self._server()
        path = "/?t=" + s.token
        headers = ["GET " + path + " HTTP/1.1", "Origin: http://evil.example"]
        assert s._handshake_allowed(path, headers) is False

    def test_bearer_header_accepted(self):
        s = self._server()
        path = "/"
        headers = [
            "GET / HTTP/1.1",
            "Authorization: Bearer " + s.token,
            "Origin: http://localhost:8765",
        ]
        assert s._handshake_allowed(path, headers) is True

    def test_no_origin_allowed_when_token_ok(self):
        """非浏览器客户端没有 Origin，令牌正确即可。"""
        s = self._server()
        path = "/?t=" + s.token
        assert s._handshake_allowed(path, ["GET " + path + " HTTP/1.1"]) is True


# ==================== HTTP 接口 ====================

@pytest.fixture
def http_server():
    from beeoffice.plugins.beeshow_sync_server import SyncServer

    server = SyncServer()
    server.http_port = _free_port()
    server.set_slides_html(["<p>第一页</p>", "<p>第二页</p>"])
    server._start_http_server()

    for _ in range(20):
        try:
            _get(f"http://127.0.0.1:{server.http_port}/api/info", timeout=1)
            break
        except Exception:
            time.sleep(0.05)

    yield server
    server.stop()


class TestHttpApi:
    def test_info_requires_token(self, http_server):
        status, _, _ = _get(
            f"http://127.0.0.1:{http_server.http_port}/api/info"
        )
        assert status == 403

    def test_info_ok_with_token(self, http_server):
        status, body, headers = _get(
            f"http://127.0.0.1:{http_server.http_port}"
            f"/api/info?t={http_server.token}"
        )
        assert status == 200
        assert "Access-Control-Allow-Origin" not in headers, (
            "通配 CORS 必须移除"
        )

    def test_viewer_page_requires_token(self, http_server):
        status, _, _ = _get(
            f"http://127.0.0.1:{http_server.http_port}/sync"
        )
        assert status == 403

    def test_slide_content_served_with_token(self, http_server):
        """顺带验证 §2.7：设置了幻灯片后观众端确实能拿到画面。"""
        url = (
            f"http://127.0.0.1:{http_server.http_port}"
            f"/api/slide/1?t={http_server.token}"
        )
        status, body, headers = _get(url)
        assert status == 200
        assert "第二页" in body.decode("utf-8")
        assert "Access-Control-Allow-Origin" not in headers

    def test_head_is_rejected(self, http_server):
        conn = http.client.HTTPConnection(
            "127.0.0.1", http_server.http_port, timeout=3
        )
        conn.request("HEAD", f"/api/info?t={http_server.token}")
        resp = conn.getresponse()
        assert resp.status == 403
        conn.close()


# ==================== 观众页面注入令牌 ====================

class TestViewerTemplate:
    def test_viewer_html_embeds_token(self):
        from beeoffice.plugins.beeshow_sync_viewer import get_viewer_html

        html = get_viewer_html(8766, "tok123")
        assert "tok123" in html, "观众页必须带上令牌才能完成握手"

    def test_viewer_html_without_token_still_renders(self):
        from beeoffice.plugins.beeshow_sync_viewer import get_viewer_html

        assert "WebSocket" in get_viewer_html(8766)
