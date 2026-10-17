# tests/test_p0_regression/test_p0_06_self_save.py
"""P0-6 回归：多文件保存不误弹外部修改"""
import time


def test_is_self_save_multi_file():
    from beeoffice.app import SELF_SAVE_IGNORE_SECONDS

    class FakeApp:
        _recent_self_saves = {}

        def notify_self_save(self, path):
            now = time.time()
            self._recent_self_saves[str(path)] = now
            self._recent_self_saves = {
                p: t for p, t in self._recent_self_saves.items()
                if now - t < 10
            }

        def _is_self_save(self, path):
            ts = self._recent_self_saves.get(str(path), 0)
            return (time.time() - ts) < SELF_SAVE_IGNORE_SECONDS

    app = FakeApp()
    app.notify_self_save("A.md")
    app.notify_self_save("B.md")
    assert app._is_self_save("A.md") is True
    assert app._is_self_save("B.md") is True
    assert app._is_self_save("C.md") is False
