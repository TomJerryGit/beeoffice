# -*- coding: utf-8 -*-
"""
蜜写 Markdown ↔ 富文本 往返幂等性（P1 收尾）

背景：
    编辑器内部用 QTextDocument 表示富文本，存盘要转回 Markdown。
    此前的缺陷是"往返一次就变形"：引用块丢字、链接退化成纯文本、表格丢列。
    那三项已修，本文件用一份**覆盖全部常用语法**的样本守住整体幂等性：
    markdown → 富文本 → markdown 必须与第一次转换结果完全一致。

为什么用"二次转换后相等"而不是"与原文相等"：
    原文允许有多种合法写法（如 `*斜体*` 与 `_斜体_`），
    编辑器只保证输出一种规范形式，故以第一次输出为基准。
"""
import pytest

pytest.importorskip("PySide6.QtWidgets")

SAMPLE = """# 一级标题

## 二级标题

正文里有 **粗体**、*斜体*、~~删除线~~ 和 `行内代码`，
还有一个 [链接](https://example.com)。

- 无序一
- 无序二

1. 有序一
2. 有序二

> 引用的一行
> 引用的第二行

```python
print("代码块")
```

| 列A | 列B |
| --- | --- |
| 1 | 2 |

---

结尾段落。
"""


def _roundtrip(editor, text):
    """markdown → 富文本 → markdown"""
    editor.set_content(text)
    editor._switch_mode("rich_text")
    out = editor.content()
    editor._switch_mode("markdown")
    return out


@pytest.fixture
def editor(qtbot):
    from beeoffice.plugins.beewrite import BeeWriteEditor

    ed = BeeWriteEditor()
    qtbot.addWidget(ed)
    yield ed
    try:
        ed.close()
    except Exception:
        pass


def test_roundtrip_is_idempotent(editor):
    """第二次往返不得再改变内容。"""
    once = _roundtrip(editor, SAMPLE)
    twice = _roundtrip(editor, once)
    assert once == twice, (
        "Markdown 往返不幂等：\n"
        f"--- 第一次 ---\n{once}\n--- 第二次 ---\n{twice}"
    )


@pytest.mark.parametrize("needle,label", [
    ("**粗体**", "粗体"),
    ("*斜体*", "斜体"),
    ("~~删除线~~", "删除线"),
    ("`行内代码`", "行内代码"),
    ("[链接](https://example.com)", "链接"),
    ("> 引用的一行", "引用块"),
    ("print(\"代码块\")", "代码块"),
    ("| 列A | 列B |", "表格表头"),
    ("---", "分隔线"),
])
def test_roundtrip_preserves_syntax(editor, needle, label):
    """关键语法在往返后必须还在。"""
    out = _roundtrip(editor, SAMPLE)
    assert needle in out, f"{label} 在往返后丢失或变形：\n{out}"
