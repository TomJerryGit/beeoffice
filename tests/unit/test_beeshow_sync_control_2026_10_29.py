"""投屏遥控：控制帧解码 + 桌面动作分发。"""
import json

from beeoffice.plugins.beeshow_sync_server import SyncServer


def _masked(text: str) -> bytes:
    payload = text.encode()
    mask = b"abcd"
    data = bytes(b ^ mask[i % 4] for i, b in enumerate(payload))
    return bytes([0x81, 0x80 | len(payload)]) + mask + data


def test_decode_control_frame():
    frame = _masked(json.dumps({"type": "control", "action": "next"}))
    assert SyncServer.decode_text_frame(frame)["action"] == "next"


def test_remote_control_dispatch():
    class View:
        _current_slide = 1
        _slides_html = ["a", "b", "c"]
        actions = []

        def _show_slide(self, i):
            self.actions.append(("slide", i))

        def _broadcast_black_screen(self, v):
            self.actions.append(("black", v))

        def _stop_sync_mode(self):
            self.actions.append(("end", None))

    from beeoffice.plugins.beeshow_sync_mixin import SyncMixin

    v = View()
    SyncMixin._remote_control(v, "next")
    SyncMixin._remote_control(v, "prev")
    SyncMixin._remote_control(v, "black")
    assert v.actions == [("slide", 2), ("slide", 0), ("black", True)]
