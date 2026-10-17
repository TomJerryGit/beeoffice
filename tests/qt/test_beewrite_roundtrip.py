# -*- coding: utf-8 -*-
"""
蜜写 md ↔ 富文本 往返一致性（P1，架构级）

策略：**先写幂等断言，再改实现**。
    `md → rich → md` 应与原始 md 在语义上一致（空白归一化后）。

覆盖三个已知丢失点：
    1. 引用块：重建用 margin=20，回写却判断 >30 → 永远识别不回来
    2. 超链接：只给文字染色，不存 URL → 永久丢失
    3. 表格空单元格：解析时 `if c.strip()` 把空列吞掉 → 数据左移
"""
import pytest

pytest.importorskip("PySide6.QtWidgets")


@pytest.fixture
def rich(qtbot):
    from beeoffice.plugins.beewrite_rich_editor import RichTextEditor

    ed = RichTextEditor()
    qtbot.addWidget(ed)
    yield ed
    try:
        ed.deleteLater()
    except Exception:
        pass


def _norm(md: str) -> str:
    """归一化：统一换行、去行尾空白、去尾部空行。"""
    lines = [ln.rstrip() for ln in md.replace("\r\n", "\n").split("\n")]
    while lines and not lines[-1]:
        lines.pop()
    return "\n".join(lines)


def _roundtrip(rich, md: str) -> str:
    rich.clear()
    rich.set_markdown(md)
    return rich.to_markdown()


# ==================== 引用块 ====================

def test_blockquote_preserved(rich):
    out = _roundtrip(rich, "> 引用的内容")
    assert _norm(out) == "> 引用的内容", f"实际输出: {out!r}"


def test_blockquote_not_accumulating_prefix(rich):
    """反复往返不应累积 "▎ " 前缀。"""
    md = "> 第一条"
    once = _norm(_roundtrip(rich, md))
    twice = _norm(_roundtrip(rich, once))
    assert once == twice == md, f"once={once!r} twice={twice!r}"


# ==================== 超链接 ====================

def test_link_url_preserved(rich):
    md = "[蜜蜂办公](https://example.com/bee)"
    out = _roundtrip(rich, md)
    assert "[蜜蜂办公](https://example.com/bee)" in out, f"实际输出: {out!r}"


def test_link_inside_sentence(rich):
    md = "详见 [文档](https://example.com/doc) 一节"
    out = _roundtrip(rich, md)
    assert "https://example.com/doc" in out
    assert "[文档]" in out


# ==================== 表格 ====================

def test_table_with_empty_cell_keeps_columns(rich):
    md = (
        "| a |  | c |\n"
        "|---|---|---|\n"
        "| 1 |  | 3 |\n"
    )
    out = _roundtrip(rich, md)
    rows = [ln for ln in out.strip().split("\n") if ln.strip()]
    assert rows, "表格没有输出"
    for line in rows:
        assert line.count("|") == 4, (
            f"列数丢失（应为 3 列 4 个竖线）: {line!r}\n完整输出:\n{out}"
        )


def test_table_normal_still_works(rich):
    md = (
        "| 序号 | 姓名 |\n"
        "|---|---|\n"
        "| 1 | 张三 |\n"
    )
    out = _roundtrip(rich, md)
    assert "张三" in out
    assert out.count("|") >= 8
