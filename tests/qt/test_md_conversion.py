# tests/test_md_conversion.py
"""
Markdown ↔ 富文本 双向转换测试

覆盖：
  - 空标题行不应产生 "#" 输出
  - 长文本误设标题时自动降级为正文
  - 表格空列自动过滤
  - 数字列右对齐
  - 往返转换内容一致
"""
import pytest
from PySide6.QtWidgets import QApplication

from beeoffice.plugins.beewrite_rich_editor import RichTextEditor


# ==================== 空标题处理 ====================

class TestEmptyHeading:
    """空标题不应输出 #"""

    def test_empty_heading_not_output(self, qtbot):
        """
        含空标题块的文档：不应输出孤立 `#`，且正文必须保留。

        优化规划 §4.2：原实现是**恒真断言**。实测确认（三种构造）：
          - 原夹具里文档**全部为空** → `to_markdown()` 返回 `''` →
            `lines = []` → `for line in lines` **一次都不执行**，断言根本没被求值；
          - 其它构造下 `to_markdown()` 会**丢弃空标题**，因此也不可能出现 `"#"`。

        所以原测试测不到任何东西。这里改为构造一个"输出非空"的文档，
        先确认前置条件（真的有空标题块），再断言正文保留且没有空标题行 ——
        这样循环体一定会执行，断言才可能失败。
        """
        editor = RichTextEditor()
        qtbot.addWidget(editor)
        editor.set_markdown("")

        from PySide6.QtGui import QTextBlockFormat, QTextCursor  # noqa: F401

        cursor = editor.textCursor()
        cursor.insertText("正文")          # 关键：保证输出非空
        bf = QTextBlockFormat()
        bf.setHeadingLevel(1)
        cursor.insertBlock(bf)             # 空标题块（刻意不插入任何文本）

        # ---- 前置条件：文档里确实存在一个"空标题块" ----
        has_empty_heading = False
        block = editor.document().begin()
        while block.isValid():
            if block.blockFormat().headingLevel() > 0 \
                    and not block.text().strip():
                has_empty_heading = True
                break
            block = block.next()
        assert has_empty_heading, (
            "夹具没有真正造出空标题块 —— 这条测试会退化成恒真"
        )

        md = editor.to_markdown()
        lines = [l for l in md.split("\n") if l.strip()]

        # ---- 保证断言真的会被求值（原实现就是死在这里）----
        assert lines, (
            f"to_markdown() 输出为空，循环不会执行、断言又会恒真：{md!r}"
        )
        # ---- 正文不得因为空标题块而丢失 ----
        assert "正文" in md, f"正文丢了：{md!r}"
        # ---- 不得出现空标题行 ----
        for line in lines:
            assert line.strip() != "#", f"不应输出空标题行: {line!r}"
        assert not any(
            l.strip().startswith("#") and not l.strip().lstrip("#").strip()
            for l in lines
        ), f"出现了只有 # 的标题行: {lines}"

        # ---- 反向确认：判定条件本身确实能识别出 '#' 行 ----
        assert any(l.strip() == "#" for l in ["#"]), "判定条件写错了"

    def test_set_markdown_empty_heading_as_blank(self, qtbot):
        """Markdown 里的 "# " 空标题应被当作空行"""
        editor = RichTextEditor()
        qtbot.addWidget(editor)
        editor.set_markdown("# \n\n正文")
        # 不应产生标题块
        doc = editor.document()
        block = doc.begin()
        has_empty_heading = False
        while block.isValid():
            if block.blockFormat().headingLevel() > 0 and not block.text().strip():
                has_empty_heading = True
                break
            block = block.next()
        assert not has_empty_heading, "空标题不应产生标题块"


# ==================== 长文本标题降级 ====================

class TestLongHeadingDowngrade:
    """长文本误设标题时自动降级"""

    def test_long_heading_downgrade(self, qtbot):
        """超过 40 字符且以句号结尾的标题应被降级为正文"""
        editor = RichTextEditor()
        qtbot.addWidget(editor)

        long_text = (
            "千古江山，英雄无觅孙仲谋处。舞榭歌台，风流总被雨打风吹去。"
            "斜阳草树，寻常巷陌，人道寄奴曾住。想当年，金戈铁马，"
            "气吞万里如虎。"
        )
        assert len(long_text) > 40, "测试文本必须超过 40 字符"
        assert long_text[-1] == "。", "测试文本应以句号结尾"

        md = f"# {long_text}\n"
        editor.set_markdown(md)
        out_md = editor.to_markdown()

        # 输出不应以 "# " 开头（应降级为正文）
        first_line = out_md.split("\n")[0]
        assert not first_line.startswith("#"), \
            f"长文本不应被识别为标题: {first_line!r}"

    def test_short_heading_kept(self, qtbot):
        """短标题（不带句号）应保留"""
        editor = RichTextEditor()
        qtbot.addWidget(editor)

        md = "# 永遇乐·京口北固亭怀古\n"
        editor.set_markdown(md)
        out_md = editor.to_markdown()

        assert out_md.startswith("# 永遇乐"), \
            f"短标题应保留: {out_md!r}"


# ==================== 表格转换 ====================

class TestTableConversion:
    """表格转换测试"""

    def test_empty_columns_filtered(self, qtbot):
        """Markdown 表格里的空列应被过滤"""
        editor = RichTextEditor()
        qtbot.addWidget(editor)

        md = (
            "| A | B | C |   |   |\n"
            "|---|---|---|:-:|:-:|\n"
            "| 1 | 2 | 3 |   |   |\n"
            "| 4 | 5 | 6 |   |   |\n"
        )
        editor.set_markdown(md)
        out_md = editor.to_markdown()

        # 输出应只有 3 列
        for line in out_md.split("\n"):
            if line.startswith("|") and "A" in line:
                # 表头行
                cols = [c for c in line.split("|") if c.strip()]
                assert len(cols) == 3, f"空列未过滤: {line!r}"

    def test_numeric_column_right_aligned(self, qtbot):
        """数字列应右对齐（分隔行用 ---:）"""
        editor = RichTextEditor()
        qtbot.addWidget(editor)

        md = (
            "| 姓名 | 收入 |\n"
            "|------|------|\n"
            "| 张三 | 200 |\n"
            "| 李四 | 300 |\n"
        )
        editor.set_markdown(md)
        out_md = editor.to_markdown()

        # 分隔行应包含 ---:
        lines = out_md.split("\n")
        sep_line = None
        for l in lines:
            if l.startswith("|-") or l.startswith("|:"):
                sep_line = l
                break
        assert sep_line is not None, "找不到分隔行"
        # 收入列的分隔符应带 :（右对齐）
        assert "---:" in sep_line, f"数字列应右对齐: {sep_line!r}"


# ==================== 往返转换 ====================

class TestRoundTrip:
    """Markdown → 富文本 → Markdown 往返测试"""

    def test_roundtrip_preserves_content(self, qtbot, sample_markdown):
        """往返转换后主要内容应保留"""
        editor = RichTextEditor()
        qtbot.addWidget(editor)

        editor.set_markdown(sample_markdown)
        out_md = editor.to_markdown()

        # 标题应保留
        assert "永遇乐" in out_md
        # 正文应保留
        assert "千古江山" in out_md
        # 表格数据应保留
        assert "张三" in out_md
        assert "400" in out_md

    def test_roundtrip_stable(self, qtbot, sample_markdown):
        """往返两次结果应一致"""
        editor = RichTextEditor()
        qtbot.addWidget(editor)

        editor.set_markdown(sample_markdown)
        md1 = editor.to_markdown()

        editor.set_markdown(md1)
        md2 = editor.to_markdown()

        assert md1 == md2, "往返两次结果不一致"