# tests/regression/v5/test_v505_play_window_leak.py
"""
优化规划 §2.7 回归：全屏播放窗口不得泄漏 QtWebEngine 视图。

原缺陷（资源泄漏）
------------------
`_PlayWindow.__init__` 做的是 `super().__init__(owner)` —— 把 BeeShowView 当成了
**Qt 父对象**。而 QObject 子对象只在父对象销毁时才释放，于是：

  - 用户连按两次 F5（第二次不走 `_stop_play`）→ `self._play_window` 被覆盖，
    旧窗口失去 Python 引用，但仍是 self 的子对象 → **永久存活**；
  - 即便正常播放→停止，`_stop_play` 只调 `close()`，而没有
    `WA_DeleteOnClose` 时 `close()` 只是**隐藏**，对象依然存在。

两种路径都会留下一个隐藏但仍存活的 WebEngine 视图 —— 那是一个完整的
**渲染进程**，反复操作会持续吃内存。

修复：
  - `_PlayWindow` 去父（owner 仅用于键盘事件转发，与父子关系无关）；
  - 设置 `WA_DeleteOnClose`，使 `close()` 真正销毁对象；
  - `_start_play()` 新建前先关闭旧窗口，覆盖"连按 F5"的路径。

测试在**独立子进程**里实例化 WebEngine 窗口：既避免 offscreen 下 QtWebEngine
的退出期原生崩溃污染结果，又能在真实对象上断言 parent/属性/销毁。
"""
import json
import subprocess
import sys
import textwrap
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]     # tests/regression/v5/ → 仓库根

_PROBE = textwrap.dedent(
    """
    import json, os, sys
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtCore import QEvent, Qt
    from PySide6.QtWidgets import QApplication, QWidget
    app = QApplication([])

    import shiboken6
    from PySide6.QtWebEngineWidgets import QWebEngineView
    from beeoffice.plugins.beeshow_constants import _PlayWindow

    owner = QWidget()
    window = _PlayWindow(owner)

    result = {
        "is_webengine": isinstance(window, QWebEngineView),
        "parent_is_none": window.parent() is None,
        "delete_on_close": window.testAttribute(Qt.WA_DeleteOnClose),
        "owner_kept": window._owner is owner,
        "valid_before_close": shiboken6.isValid(window),
    }
    print("RESULT1" + json.dumps(result))

    window.close()
    app.processEvents()
    app.sendPostedEvents(None, QEvent.DeferredDelete)
    app.processEvents()
    print("RESULT2" + json.dumps({
        "valid_after_close": shiboken6.isValid(window),
    }))
    """
)


def _run_probe(tmp_path) -> dict:
    """在独立解释器里跑探针；输出写文件（受限环境里管道不可靠）。"""
    out_file = tmp_path / "probe_out.txt"
    with open(out_file, "w", encoding="utf-8") as fh:
        subprocess.run(
            [sys.executable, "-c", _PROBE],
            cwd=str(ROOT),
            stdout=fh,
            stderr=subprocess.STDOUT,
            timeout=300,
        )
    text = out_file.read_text(encoding="utf-8", errors="replace")
    result = {}
    for line in text.splitlines():
        if line.startswith("RESULT1"):
            result.update(json.loads(line[len("RESULT1"):]))
        elif line.startswith("RESULT2"):
            result.update(json.loads(line[len("RESULT2"):]))
    assert result, f"探针未产出结果：\n{text[-3000:]}"
    return result


def test_play_window_is_not_parented(tmp_path):
    """
    核心回归：`_PlayWindow` 不能以 owner 为 Qt 父对象。

    否则每次"再播放"都会留下一个失去引用却仍存活的 WebEngine 视图。
    """
    r = _run_probe(tmp_path)
    assert r["is_webengine"] is True, "应仍是 QWebEngineView"
    assert r["parent_is_none"] is True, (
        "播放窗口仍被挂到 owner 之下 —— 子对象只在父对象销毁时释放，会泄漏"
    )


def test_play_window_deletes_on_close(tmp_path):
    """必须设置 WA_DeleteOnClose，并真的在 close() 后销毁。"""
    r = _run_probe(tmp_path)
    assert r["delete_on_close"] is True, (
        "缺少 WA_DeleteOnClose：close() 只会隐藏，视图不会释放"
    )
    assert r["valid_before_close"] is True
    assert r["valid_after_close"] is False, (
        "close() 之后底层对象仍然有效 —— WebEngine 视图没有被销毁"
    )


def test_owner_still_available_for_key_forwarding(tmp_path):
    """去父不能破坏 P0-2 的键盘转发（owner 仍需保留）。"""
    r = _run_probe(tmp_path)
    assert r["owner_kept"] is True, "owner 引用丢了，键盘转发会失效"


def test_start_play_closes_previous_window_before_creating():
    """`_start_play` 必须先关闭旧窗口，覆盖"连按 F5"的路径。"""
    import inspect

    from beeoffice.plugins.beeshow_play_mixin import PlayMixin

    src = inspect.getsource(PlayMixin._start_play)
    assert "previous" in src and ".close()" in src, (
        "_start_play 没有回收上一次的播放窗口"
    )
    # 顺序：先关闭旧的，再创建新的
    assert src.index("previous") < src.index("_PlayWindow(self)"), (
        "应先关闭旧窗口再新建"
    )
