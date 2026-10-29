"""投屏遥控局域网 loopback：WS 握手 + 控制帧 → 桌面回调。"""
import base64
import json
import os
import socket
import time

from beeoffice.plugins.beeshow_sync_server import SyncServer


def _recv_headers(sock):
    data = b""
    while b"\r\n\r\n" not in data:
        chunk = sock.recv(4096)
        if not chunk:
            break
        data += chunk
    return data


def _masked(text: str) -> bytes:
    payload = text.encode()
    mask = os.urandom(4)
    data = bytes(b ^ mask[i % 4] for i, b in enumerate(payload))
    return bytes([0x81, 0x80 | len(payload)]) + mask + data


def test_sync_loopback_control():
    server = SyncServer(http_port=18765, ws_port=18766, allow_lan=False)
    got = []
    server.on_control = got.append
    server.set_slides_html(["<html><body>A</body></html>"])
    assert server.start()
    try:
        sock = socket.create_connection(("127.0.0.1", 18766), timeout=5)
        key = base64.b64encode(os.urandom(16)).decode()
        req = (
            f"GET /?t={server.token} HTTP/1.1\r\n"
            "Host: 127.0.0.1:18766\r\n"
            "Upgrade: websocket\r\n"
            "Connection: Upgrade\r\n"
            f"Sec-WebSocket-Key: {key}\r\n"
            "Sec-WebSocket-Version: 13\r\n\r\n"
        )
        sock.sendall(req.encode())
        response = _recv_headers(sock)
        assert b" 101 " in response.split(b"\r\n")[0]
        frame = _masked(json.dumps({"type": "control", "action": "next"}))
        sock.sendall(frame)
        deadline = time.time() + 5
        while not got and time.time() < deadline:
            time.sleep(0.05)
        assert got == ["next"]
        sock.close()
    finally:
        server.stop()
