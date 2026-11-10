"""BeeShow WebSocket 帧编解码补测。"""
from beeoffice.plugins.beeshow_sync_server import WebSocketFrame


def test_encode_short_frame():
    raw = WebSocketFrame.encode("hello")
    assert raw[0] == 0x81
    assert raw[1] == 5
    assert raw[2:] == b"hello"


def test_encode_long_frame():
    text = "x" * 200
    raw = WebSocketFrame.encode(text)
    assert raw[0] == 0x81
    assert raw[1] == 126
    assert len(raw) == 4 + 200
    assert raw[4:] == text.encode("utf-8")


def test_decode_close_and_ping():
    assert WebSocketFrame.decode_close_frame(b"\x88\x00") is True
    assert WebSocketFrame.decode_ping_frame(b"\x89\x00") is True
    assert WebSocketFrame.decode_close_frame(b"\x81\x00") is False
    assert WebSocketFrame.decode_ping_frame(b"\x81\x00") is False
    assert WebSocketFrame.decode_close_frame(b"") is False
    assert WebSocketFrame.decode_ping_frame(b"") is False
