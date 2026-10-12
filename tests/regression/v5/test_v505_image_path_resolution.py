# tests/regression/v5/test_v505_image_path_resolution.py
"""
优化规划 §3.3 图片项的安全网：**先固化路径兜底行为，再消重**。

为什么先写这些
--------------
`_resolve_image_path_for_export()`（beewrite_export_mixin）与
`_insert_image_by_path()`（beewrite_rich_editor）里有**两份形态相同**的
"多基准目录兜底"实现，即将抽取到 `image_utils.resolve_image_path()`。
该改动直接影响"导出 DOCX 时图片能不能找到"，属于数据可见的路径，
所以先把当前行为逐条钉住；消重后必须全部仍然通过。

产品级安全网已存在于 `test_v504_image_paragraph_docx.py`
（插入图片 → 导出 DOCX → 断言段落里真有图片），本文件补的是**解析层**。
"""
from pathlib import Path

import pytest

try:
    from PIL import Image
    HAS_PIL = True
except ImportError:  # pragma: no cover
    HAS_PIL = False

from PySide6.QtGui import QTextDocument  # noqa: E402


def _make_png(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (40, 30), color="green").save(str(path))
    return path


def _document_has_image(document: QTextDocument) -> bool:
    """遍历 block 的 fragment，判断文档里是否有内联图片。"""
    block = document.begin()
    while block.isValid():
        it = block.begin()
        while not it.atEnd():
            frag = it.fragment()
            if frag.isValid() and frag.charFormat().isImageFormat():
                return True
            it += 1
        block = block.next()
    return False


@pytest.fixture
def editor(beewrite_editor):
    """
    默认切到**富文本模式**。

    `_insert_image_by_path` 与 `_write_docx` 都区分编辑模式：markdown 模式下
    导出走 `bee_export.export_to_docx`（基于 Markdown 文本），富文本模式下才走
    `_rich_to_docx`（处理 QTextImageFormat）。不切换的话，插入到 rich_editor 的
    图片根本不在导出输入里 —— 这是测试自身容易踩的坑，不是产品缺陷。
    """
    beewrite_editor._switch_mode("rich_text")
    return beewrite_editor


# ==================== 导出侧解析：_resolve_image_path_for_export ====================

@pytest.mark.skipif(not HAS_PIL, reason="Pillow 未安装")
def test_absolute_path_is_resolved_directly(editor, tmp_path):
    img = _make_png(tmp_path / "abs.png")

    resolved, tried = editor._resolve_image_path_for_export(str(img))

    assert resolved == img
    assert str(img) in tried[0]


def test_missing_absolute_path_does_not_fall_back_to_home(editor, tmp_path):
    """
    绝对路径不存在时应直接判定失败 —— 不应再到 home 目录里"碰运气"拼同名文件。
    （当前实现的既有行为，消重后必须保持。）
    """
    missing = tmp_path / "sub" / "missing.png"

    resolved, tried = editor._resolve_image_path_for_export(str(missing))

    assert resolved is None
    assert tried == [str(missing)], (
        f"绝对路径只应尝试它自己，实际尝试了: {tried}"
    )


@pytest.mark.skipif(not HAS_PIL, reason="Pillow 未安装")
def test_relative_path_resolved_via_current_file_path(editor, tmp_path):
    """相对路径应相对"当前文档所在目录"解析（最可靠的那条候选）。"""
    docs = tmp_path / "docs"
    img = _make_png(docs / "pic.png")
    editor._current_file_path = str(docs / "doc.md")

    resolved, _ = editor._resolve_image_path_for_export("pic.png")

    assert resolved == img


@pytest.mark.skipif(not HAS_PIL, reason="Pillow 未安装")
def test_relative_path_resolved_via_rich_editor_dir(editor, tmp_path):
    """没有 _current_file_path 时，退化到 rich_editor._current_file_dir。"""
    docs = tmp_path / "d2"
    img = _make_png(docs / "p2.png")
    editor._current_file_path = None
    editor.rich_editor.set_current_file_dir(str(docs))

    resolved, _ = editor._resolve_image_path_for_export("p2.png")

    assert resolved == img


def test_missing_relative_records_all_attempted_paths(editor, tmp_path):
    """找不到时必须记录尝试过的路径（供日志/占位提示排查）。"""
    editor._current_file_path = str(tmp_path / "doc.md")

    resolved, tried = editor._resolve_image_path_for_export("nope.png")

    assert resolved is None
    assert tried, "应记录尝试过的路径"
    assert all("nope.png" in t for t in tried), tried
    # home 是最后兜底
    assert any(str(Path.home()) in t for t in tried), tried


def test_relative_candidates_are_deduplicated(editor, tmp_path):
    """
    多个候选基准目录相同时应去重（否则会在同一目录里重复尝试）。
    """
    docs = tmp_path / "same"
    docs.mkdir()
    editor._current_file_path = str(docs / "doc.md")
    editor.rich_editor.set_current_file_dir(str(docs))

    _, tried = editor._resolve_image_path_for_export("x.png")

    relative_attempts = [t for t in tried if "x.png" in t]
    assert len(relative_attempts) == len(set(relative_attempts)), (
        f"存在重复尝试: {relative_attempts}"
    )


# ==================== 插入侧：_insert_image_by_path ====================

@pytest.mark.skipif(not HAS_PIL, reason="Pillow 未安装")
def test_rich_editor_inserts_relative_image(editor, tmp_path):
    """相对路径插入应真的把图片放进文档（消重后不能坏）。"""
    docs = tmp_path / "rdocs"
    _make_png(docs / "rel.png")
    editor._current_file_path = str(docs / "doc.md")
    editor.rich_editor.set_current_file_dir(str(docs))

    editor.rich_editor._insert_image_by_path("rel.png")

    assert _document_has_image(editor.rich_editor.document()), (
        "相对路径的图片没有被插入（QTextImageFormat 缺失）"
    )


@pytest.mark.skipif(not HAS_PIL, reason="Pillow 未安装")
def test_rich_editor_inserts_absolute_image(editor, tmp_path):
    img = _make_png(tmp_path / "r2.png")

    editor.rich_editor._insert_image_by_path(str(img))

    assert _document_has_image(editor.rich_editor.document())


def test_rich_editor_inserts_placeholder_for_missing(editor, tmp_path):
    """找不到图片时应插入可见占位文字，而不是静默什么都不做。"""
    editor._current_file_path = str(tmp_path / "doc.md")

    editor.rich_editor._insert_image_by_path("definitely_missing.png")

    text = editor.rich_editor.toPlainText()
    assert "图片缺失" in text or "缺失" in text, (
        f"没有插入占位文字，实际内容: {text!r}"
    )


# ==================== 产物级：插入后导出 DOCX 必须真有图片 ====================

@pytest.mark.skipif(not HAS_PIL, reason="Pillow 未安装")
def test_relative_image_survives_docx_export(editor, tmp_path):
    """
    端到端：**相对路径**插入的图片，导出 DOCX 后必须真的在里面。

    这是消重时最怕坏掉的一条路径（解析失败 → 图片静默消失）。
    """
    from docx import Document as DocxDocument

    docs = tmp_path / "exp"
    _make_png(docs / "e.png")
    editor._current_file_path = str(docs / "doc.md")
    editor.rich_editor.set_current_file_dir(str(docs))
    editor.rich_editor._insert_image_by_path("e.png")

    out = tmp_path / "out.docx"
    assert editor._write_docx(str(out)) is True

    doc = DocxDocument(str(out))
    w_ns = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
    assert doc.element.body.findall(f".//{w_ns}drawing"), (
        "相对路径插入的图片没有出现在导出的 DOCX 里"
    )
