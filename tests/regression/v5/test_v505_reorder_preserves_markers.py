# tests/regression/v5/test_v505_reorder_preserves_markers.py
"""
优化规划 §2.7 回归：拖动排序（以及任何从 `_slides_md` 重建编辑器的操作）
不得丢失 `<!-- comments: -->` / `<!-- beeoffice-style: -->` /
`<!-- beeoffice-image: -->` 这些**特殊标记**。

原缺陷（数据丢失）
------------------
`_update_preview()` 把每页 Markdown 里的三类特殊注释**剥掉之后**才存进
`_slides_md`：

    part = re.sub(r'<!--\\s*comments:.*?-->', '', part)          # 页评论
    part = re.sub(r'<!--\\s*beeoffice-(style|image):.*?-->', '', part)

而 `_on_slides_reordered()` 用 `_slides_md` 重新 `setPlainText()` 整个文档，
于是**任何一次拖动排序都会永久删掉**这些标记：每页的评论、样式覆盖、图片位置。

更矛盾的是：`beeshow_notes_mixin._remove_plain_comment()` 的 docstring 明确写着
这些前缀**必须保留**（还专门用占位符避免误删），说明 `_slides_md` 的设计意图
就是保留标记 —— `_update_preview()` 的剥离才是 bug。

另一个相关缺陷：提取演讲备注的正则 `<!--\\s*(.*?)\\s*-->` 匹配**第一个**注释，
不管它是不是备注。于是 `<!-- beeoffice-style: {...} -->` 会被当成演讲备注
（备注里塞进一段 JSON），同时该标记也被一并删除。

修复：
  - 备注正则排除四类特殊前缀（只有真正的普通注释才算备注）；
  - `_slides_md` 存**保留标记**的原文（供重排/保存无损往返）；
  - 预览用的 `_slides_html` 仍剥离标记，行为不变。

测试用轻量宿主（只挂 `SlideMixin` + 真实 QPlainTextEdit），不构造
`BeeShowView`，因此不触碰 QtWebEngine（那会引入 offscreen 下的退出期崩溃）。
"""
import pytest
from PySide6.QtWidgets import QLabel, QPlainTextEdit, QWidget

from beeoffice.plugins.beeshow_slide_mixin import SlideMixin


COMMENT_MARKER = '<!-- comments: [{"id": 1, "text": "这里要改"}] -->'
STYLE_MARKER = '<!-- beeoffice-style: {"path": ".slide > h1", "color": "red"} -->'
IMAGE_MARKER = '<!-- beeoffice-image: {"path": ".slide > img", "width": 300} -->'


class _Host(SlideMixin, QWidget):
    """只提供 SlideMixin 解析所需的最小状态与桩。"""

    def __init__(self):
        QWidget.__init__(self)
        self._editor = QPlainTextEdit()
        self._slides_html = []
        self._slides_md = []
        self._speaker_notes = []
        self._slide_titles = []
        self._current_slide = 0
        self._slide_label = QLabel()
        self.thumb_refreshes = 0

    # 桩：不碰 WebEngine / 缩略图列表
    def _update_thumbnails(self):
        self.thumb_refreshes += 1

    def _show_slide(self, index: int):
        self._current_slide = index

    def set_content(self, text: str):
        self._editor.setPlainText(text)
        self._update_preview()


@pytest.fixture
def host(qtbot):
    h = _Host()
    qtbot.addWidget(h)
    return h


def _set_slides(host, parts):
    host.set_content("\n---\n".join(parts))
    return host


# ==================== 解析阶段：标记必须留在源里 ====================

def test_special_markers_are_kept_in_slides_md(host):
    _set_slides(host, [
        f"# 第一页\n\n正文\n\n{COMMENT_MARKER}",
        f"# 第二页\n\n{STYLE_MARKER}",
    ])
    assert len(host._slides_md) == 2
    assert "comments:" in host._slides_md[0], (
        "评论标记被剥离了，重排时会永久丢失"
    )
    assert "beeoffice-style:" in host._slides_md[1], (
        "样式标记被剥离了"
    )


def test_special_markers_are_not_taken_as_speaker_notes(host):
    """只有普通注释才算演讲备注；特殊标记不能被当成备注内容。"""
    _set_slides(host, [f"# 标题\n\n{STYLE_MARKER}\n\n正文"])
    assert host._speaker_notes[0] == "", (
        f"样式标记被当成了演讲备注: {host._speaker_notes[0]!r}"
    )


def test_plain_comment_still_becomes_speaker_note(host):
    """普通注释（真正的备注）行为不变。"""
    _set_slides(host, ["# 标题\n\n<!-- 这是演讲备注 -->\n\n正文"])
    assert host._speaker_notes[0] == "这是演讲备注"


def test_plain_note_and_special_marker_coexist(host):
    _set_slides(host, [
        f"# 标题\n\n<!-- 演讲备注 -->\n\n{COMMENT_MARKER}"
    ])
    assert host._speaker_notes[0] == "演讲备注"
    assert "comments:" in host._slides_md[0]


def test_all_three_marker_kinds_survive_parsing(host):
    _set_slides(host, [
        f"# 甲\n\n{COMMENT_MARKER}\n\n{STYLE_MARKER}\n\n{IMAGE_MARKER}"
    ])
    md = host._slides_md[0]
    assert "comments:" in md
    assert "beeoffice-style:" in md
    assert "beeoffice-image:" in md


# ==================== 重排阶段：标记必须存活 ====================

def test_reorder_keeps_all_special_markers(host):
    """核心回归：拖动排序后，编辑器文本里必须仍有全部三类标记。"""
    _set_slides(host, [
        f"# 甲\n\n{COMMENT_MARKER}",
        f"# 乙\n\n{STYLE_MARKER}",
        f"# 丙\n\n{IMAGE_MARKER}",
    ])

    host._on_slides_reordered(None, 0, 0, None, 3)      # 第 0 页拖到末尾

    text = host._editor.toPlainText()
    assert "comments:" in text, "重排后评论标记丢失"
    assert "beeoffice-style:" in text, "重排后样式标记丢失"
    assert "beeoffice-image:" in text, "重排后图片标记丢失"


def test_reorder_keeps_marker_with_its_own_slide(host):
    """标记必须跟着自己那一页走，而不是留在原位。"""
    _set_slides(host, [
        f"# 甲\n\n{COMMENT_MARKER}",
        "# 乙\n\n普通内容",
    ])

    host._on_slides_reordered(None, 0, 0, None, 2)

    parts = host._editor.toPlainText().split("\n---")
    assert "乙" in parts[0], f"排序结果不对: {parts}"
    assert "comments:" in parts[1], f"标记没有跟着甲页移动: {parts}"
    assert "甲" in parts[1]


def test_reorder_keeps_speaker_notes(host):
    """备注同样不能因为重排而丢失。"""
    _set_slides(host, [
        "# 甲\n\n<!-- 甲的备注 -->",
        "# 乙\n\n<!-- 乙的备注 -->",
    ])

    host._on_slides_reordered(None, 0, 0, None, 2)

    text = host._editor.toPlainText()
    assert "甲的备注" in text and "乙的备注" in text


def test_reorder_preserves_marker_and_notes_together(host):
    """备注与特殊标记同时存在时，两者都要活下来。"""
    _set_slides(host, [
        f"# 甲\n\n<!-- 备注甲 -->\n\n{COMMENT_MARKER}",
        "# 乙",
    ])

    host._on_slides_reordered(None, 0, 0, None, 2)

    text = host._editor.toPlainText()
    assert "备注甲" in text
    assert "comments:" in text


def test_repeated_reorder_does_not_erode_markers(host):
    """来回拖动多次也不能逐步"磨掉"标记。"""
    _set_slides(host, [f"# 甲\n\n{COMMENT_MARKER}", "# 乙"])
    for _ in range(4):
        host._on_slides_reordered(None, 0, 0, None, 2)
        host._on_slides_reordered(None, 1, 1, None, 0)
    assert "comments:" in host._editor.toPlainText()


def test_marker_payload_not_rendered_as_body(host):
    """预览 HTML 必须剥离标记，否则 JSON 会被渲染成正文。"""
    _set_slides(host, [f"# 标题\n\n{COMMENT_MARKER}"])
    assert "这里要改" not in host._slides_html[0]
    assert "beeoffice-style" not in host._slides_html[0]


def test_preview_still_renders_slide_content(host):
    """剥离标记不能把正文一起弄丢。"""
    _set_slides(host, [f"# 我的标题\n\n正文内容\n\n{COMMENT_MARKER}"])
    assert "我的标题" in host._slides_html[0]
    assert "正文内容" in host._slides_html[0]
