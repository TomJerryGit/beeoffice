# tests/fidelity/test_beeshow_add_slide.py
"""
蜜演「新增幻灯片」回归（2026-10-21 GUI 实跑发现的 P1 bug）。

## 修的是什么
原 `_add_slide()`：
    self._editor.textCursor().insertText("\\n\\n---\\n\\n## 新幻灯片")
两个问题：
1. 插入串**结尾没有换行** → `## 新幻灯片` 与原有首行 `# 欢迎使用蜜演` 粘成
   `新幻灯片# 欢迎使用蜜演 🎥`；
2. 插入点取**当前光标**（新建演示时光标在文首），新页被插到第 1 页之前且
   与第 1 页标题合并 → 按 `\\n---` 切分后页数仍是 2。

修复：光标移到文末、插入串以换行结尾。

## 测试方式
不实例化完整 BeeShowView（本沙箱 WebEngine 受限），直接对 `SlideMixin._add_slide`
使用带 `_editor`/`_update_preview` 的最小假对象（真实 QPlainTextEdit）。
"""

import re

from PySide6.QtWidgets import QPlainTextEdit

from beeoffice.plugins.beeshow_slide_mixin import SlideMixin


class _FakeShow(SlideMixin):
    def __init__(self, initial="# 欢迎使用蜜演 🎥\n\n功能一览"):
        self._editor = QPlainTextEdit()
        self._editor.setPlainText(initial)
        self.preview_updates = 0

    def _update_preview(self):
        self.preview_updates += 1


def _slide_parts(text):
    return [p for p in re.split(r"\n---", text) if p.strip()]


def test_add_slide_increases_page_count(qtbot):
    fake = _FakeShow()
    assert len(_slide_parts(fake._editor.toPlainText())) == 1

    SlideMixin._add_slide(fake)

    parts = _slide_parts(fake._editor.toPlainText())
    assert len(parts) == 2, f"加页后应 1→2，实际 {len(parts)}: {parts}"
    assert parts[-1].strip().startswith("## 新幻灯片")
    assert fake.preview_updates == 1, "加页后必须刷新预览"


def test_add_slide_does_not_glue_to_previous_title(qtbot):
    fake = _FakeShow()
    SlideMixin._add_slide(fake)
    text = fake._editor.toPlainText()
    assert "新幻灯片#" not in text, "新页标题与上一页标题粘连"
    assert "# 欢迎使用蜜演" in text, "原第 1 页内容不能丢"


def test_add_slide_works_via_plugin_alias(qtbot):
    """插件兼容入口 `add_slide()` 必须走同一修复路径。"""
    fake = _FakeShow()
    fake.add_slide()
    assert len(_slide_parts(fake._editor.toPlainText())) == 2
