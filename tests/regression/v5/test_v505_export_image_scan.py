# tests/regression/v5/test_v505_export_image_scan.py
"""
优化规划 §3.3 回归：导出侧的图片遍历统一到 `image_utils`。

原状态
------
"遍历 block → fragment → `charFormat().isImageFormat()`"这套在导出路径里
重复了 3 处：

  - `_count_document_images()`  统计整篇文档的图片数
  - `_block_has_image(block)`   判断单个 block 是否含图
  - 表格单元格内图片的插入        （`_rich_to_docx` 里）

现已改走 `image_utils.iter_image_formats()` / `iter_block_images()`。
**有意保留**的是 `_write_block_runs()`：它按 fragment 顺序**交错**处理图片与
文本（还要保留粗体/斜体/字号/颜色），不是单纯的"扫描图片"。

本文件既测两个辅助函数的语义，也测"单元格里的图片能出现在导出的 DOCX 里"
（那条路径正是本次改动的对象）。
"""
from pathlib import Path

import pytest

try:
    from PIL import Image
    HAS_PIL = True
except ImportError:  # pragma: no cover
    HAS_PIL = False

try:
    from docx import Document as DocxDocument
    HAS_DOCX = True
except ImportError:  # pragma: no cover
    HAS_DOCX = False

_W_NS = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"


def _make_png(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (40, 30), color="purple").save(str(path))
    return path


@pytest.fixture
def editor(beewrite_editor):
    beewrite_editor._switch_mode("rich_text")
    return beewrite_editor


def _insert_image(editor, path):
    editor.rich_editor._insert_image_by_path(str(path))


# ==================== _count_document_images ====================

def test_count_is_zero_for_empty_document(editor):
    assert editor._count_document_images() == 0


def test_count_is_zero_for_text_only(editor):
    editor.rich_editor.setPlainText("只有文字，没有图片\n第二行")
    assert editor._count_document_images() == 0


@pytest.mark.skipif(not HAS_PIL, reason="Pillow 未安装")
def test_count_matches_inserted_images(editor, tmp_path):
    _insert_image(editor, _make_png(tmp_path / "a.png"))
    _insert_image(editor, _make_png(tmp_path / "b.png"))
    assert editor._count_document_images() == 2


@pytest.mark.skipif(not HAS_PIL, reason="Pillow 未安装")
def test_count_is_stable_when_called_twice(editor, tmp_path):
    _insert_image(editor, _make_png(tmp_path / "c.png"))
    first = editor._count_document_images()
    second = editor._count_document_images()
    assert first == second == 1, "重复统计不应漂移"


# ==================== _block_has_image ====================

@pytest.mark.skipif(not HAS_PIL, reason="Pillow 未安装")
def test_block_has_image_true(editor, tmp_path):
    _insert_image(editor, _make_png(tmp_path / "d.png"))
    doc = editor.rich_editor.document()
    blocks = []
    block = doc.begin()
    while block.isValid():
        blocks.append(block)
        block = block.next()
    assert any(editor._block_has_image(b) for b in blocks), (
        "插入了图片却没有任何 block 被判定为含图"
    )


def test_block_has_image_false_for_text(editor):
    editor.rich_editor.setPlainText("纯文字段落")
    doc = editor.rich_editor.document()
    block = doc.begin()
    assert editor._block_has_image(block) is False


# ==================== 端到端：单元格内图片必须能导出 ====================

@pytest.mark.skipif(not (HAS_PIL and HAS_DOCX), reason="Pillow/python-docx 未安装")
def test_image_inside_table_cell_is_exported(editor, tmp_path):
    """
    本次改动的正是"单元格内图片"那段遍历，所以必须有产物级断言：
    导出的 DOCX 里必须真的出现图片（`w:drawing`）。
    """
    from PySide6.QtGui import QTextImageFormat

    img = _make_png(tmp_path / "cell.png")

    # 插入 1x1 表格，并把图片放进单元格
    editor.rich_editor._insert_table(1, 1, has_header=False)
    doc = editor.rich_editor.document()
    table = None
    stack = list(doc.rootFrame().childFrames())
    while stack:
        frame = stack.pop()
        if hasattr(frame, "rows") and hasattr(frame, "columns"):
            table = frame
        stack.extend(frame.childFrames())
    assert table is not None, "没有插入表格"

    fmt = QTextImageFormat()
    fmt.setName(str(img))
    table.cellAt(0, 0).firstCursorPosition().insertImage(fmt)
    assert editor._block_has_image(
        table.cellAt(0, 0).firstCursorPosition().block()
    ), "前置条件：单元格里应有图片"

    out = tmp_path / "cell.docx"
    assert editor._write_docx(str(out)) is True

    docx_doc = DocxDocument(str(out))
    assert docx_doc.element.body.findall(f".//{_W_NS}drawing"), (
        "单元格里的图片没有出现在导出的 DOCX 里"
    )


@pytest.mark.skipif(not HAS_DOCX, reason="python-docx 未安装")
def test_export_without_images_still_works(editor, tmp_path):
    """没有图片时导出不应出问题（回归保护）。"""
    editor.rich_editor.setPlainText("只有文字")
    out = tmp_path / "plain.docx"
    assert editor._write_docx(str(out)) is True
    assert not DocxDocument(str(out)).element.body.findall(
        f".//{_W_NS}drawing"
    )
