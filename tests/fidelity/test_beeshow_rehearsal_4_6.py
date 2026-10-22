# tests/fidelity/test_beeshow_rehearsal_4_6.py
"""
蜜演排练计时按页保存 4.6 回归（2026-10-22）。

- `.beshow` 文稿内嵌隐藏元数据 `<!-- beeshow-rehearsal: {...} -->`，
  渲染/编辑器不显示，保存/重开后恢复；
- 排练中翻页把当前页耗时累计到 `_rehearsal_page_seconds`，
  停止时按分页之和显示总时长；
- 不改变正文：`load_deck` 返回纯 Markdown（不带 marker/meta）。
"""
import time

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QLabel, QPlainTextEdit

from beeoffice.plugins import beeshow_doc
from beeoffice.plugins.beeshow import BeeShowView
from beeoffice.plugins.beeshow_play_mixin import PlayMixin


TEXT = "# 第一页\n\n内容一\n\n---\n\n## 第二页\n\n内容二"


def test_deck_rehearsal_roundtrip(tmp_path):
    path = tmp_path / "demo.beshow"
    assert beeshow_doc.save_deck(path, TEXT, rehearsal={0: 12.5, 1: 3.25})
    assert beeshow_doc.load_deck(path) == TEXT
    assert beeshow_doc.load_rehearsal(path) == {0: 12.5, 1: 3.25}

    # 再次保存会替换旧 meta，不重复叠加
    assert beeshow_doc.save_deck(path, TEXT, rehearsal={0: 1.0})
    assert beeshow_doc.load_rehearsal(path) == {0: 1.0}
    raw = path.read_text(encoding="utf-8")
    assert raw.count(beeshow_doc.REHEARSAL_PREFIX) == 1


class _FakePlay(PlayMixin):
    def __init__(self):
        self._rehearsal_timer = QTimer()
        self._rehearsal_start_time = None
        self._rehearsal_page_start = None
        self._rehearsal_elapsed = 0
        self._rehearsal_page_seconds = {}
        self._rehearsal_label = QLabel()
        self.rehearsal_start_time = None
        self._current_slide = 0
        self._status = []

    def _set_status(self, text, *_args):
        self._status.append(text)


def test_per_page_accumulation(qapp):
    fake = _FakePlay()
    fake.start_rehearsal()
    assert fake._rehearsal_timer.isActive()
    fake._rehearsal_page_start = time.time() - 2.0
    fake._record_rehearsal_page(0)
    fake._current_slide = 1
    fake._rehearsal_page_start = time.time() - 1.0
    fake._record_rehearsal_page(1)
    fake.stop_rehearsal()

    seconds = fake._rehearsal_page_seconds
    assert seconds[0] >= 1.5, seconds
    assert seconds[1] >= 0.5, seconds
    assert not fake._rehearsal_timer.isActive()
    assert fake._rehearsal_page_start is None
    assert any("排练总时长" in s for s in fake._status)


def test_write_and_open_deck_restores_rehearsal(tmp_path, qapp):
    path = tmp_path / "rehearsed.beshow"
    fake = type("FakeDeck", (), {})()
    fake._rehearsal_page_seconds = {0: 7.5, 2: 4.0}
    fake._sync_tab_title = lambda _p: None
    fake.content = lambda: TEXT
    fake._current_file_path = str(path)

    assert BeeShowView._write_deck(fake, str(path)) is True
    assert beeshow_doc.load_rehearsal(path) == {0: 7.5, 2: 4.0}

    opened = type("FakeOpen", (), {})()
    opened._editor = QPlainTextEdit()
    opened._update_preview = lambda: None
    opened._sync_tab_title = lambda _p: None
    opened._rehearsal_page_seconds = {}
    assert BeeShowView.open_deck(opened, str(path)) is True
    assert opened._editor.toPlainText() == TEXT
    assert opened._rehearsal_page_seconds == {0: 7.5, 2: 4.0}
