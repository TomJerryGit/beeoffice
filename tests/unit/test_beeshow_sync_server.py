"""BeeShow 同步服务器无网络依赖补测。"""
from beeoffice.plugins.beeshow_sync_server import (
    SyncServer, ViewerConnection, WebSocketFrame,
)


class FakeSocket:
    def __init__(self):
        self.data = []
    def sendall(self, frame):
        self.data.append(frame)


class FakeViewer:
    def __init__(self):
        self.messages = []
    def send(self, message):
        self.messages.append(message)
        return True


def test_token_check():
    s = SyncServer(http_port=0, ws_port=0, token="abc")
    assert s._ws_token_ok("GET /?t=abc HTTP/1.1\r\nHost: x") is True
    assert s._ws_token_ok("GET /?t=no HTTP/1.1\r\nHost: x") is False
    assert s._ws_token_ok("GET / HTTP/1.1\r\nHost: x") is False
    assert s._ws_token_ok("") is False


def test_slides_and_state():
    s = SyncServer(http_port=0, ws_port=0, token="t")
    assert s.is_running is False
    assert s.viewer_count == 0
    s.set_slides_html(["<h1>a</h1>", "<h1>b</h1>"])
    assert s.get_slides_html() == ["<h1>a</h1>", "<h1>b</h1>"]
    url = s.get_viewer_url()
    assert "t=" in url and ":" in url


def test_broadcast_messages():
    s = SyncServer(http_port=0, ws_port=0, token="t")
    s._running = True
    v1, v2 = FakeViewer(), FakeViewer()
    s._viewers = [v1, v2]
    s.broadcast_slide(2, 5)
    s.broadcast_laser(0.5, 0.25, visible=True)
    s.broadcast_draw("move", 0.1, 0.2)
    s.broadcast_black_screen(True)
    s.broadcast_theme("dark")
    assert v1.messages[0]["type"] == "slide_change"
    assert v1.messages[0]["index"] == 2
    assert any(m["type"] == "laser" for m in v1.messages)
    assert any(m["type"] == "draw" for m in v1.messages)
    assert any(m["type"] == "black_screen" for m in v1.messages)
    assert any(m["type"] == "theme_change" for m in v1.messages)
    assert len(v2.messages) == len(v1.messages)
    # 未运行时广播不发送
    s._running = False
    s.broadcast_slide(9, 9)
    assert len(v1.messages) == 5


def test_viewer_connection_send():
    sock = FakeSocket()
    v = ViewerConnection(sock, ("127.0.0.1", 1234))
    assert v.send({"type": "hi"}) is True
    assert sock.data and sock.data[0][0] == 0x81
    # 编码失败/连接失败
    class Bad:
        def sendall(self, data):
            raise OSError("closed")
    assert ViewerConnection(Bad(), ("x", 1)).send({"a": 1}) is False


def test_broadcast_state_updates():
    s = SyncServer(http_port=0, ws_port=0, token="t")
    s._running = True
    s._viewers = []
    s.broadcast_slide(1, 3)
    assert s._current_state["type"] == "slide_change"
    s.broadcast_theme("dark")
    assert s._current_state["type"] == "theme_change"
