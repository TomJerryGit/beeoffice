# tests/test_p2_regression/test_v504_image_paragraph_docx.py
"""
v5.0.4 回归：图片段落导出 DOCX 后应居中对齐 + 段前后各 12pt。

背景：
  原 _rich_to_docx 里的图片段落继承 block format（默认左对齐），
  导出的 DOCX 里图片紧贴左侧，和相邻表格"贴在一起"，观感差。

修复：
  _rich_to_docx 在写图片段落时特殊处理：
    · para.paragraph_format.alignment = WD_ALIGN_PARAGRAPH.CENTER
    · para.paragraph_format.space_before = Pt(12)
    · para.paragraph_format.space_after = Pt(12)
  且图片段落不再叠加 rich editor 的 block format，避免被覆盖。

测试策略：
  1. 造一张图片
  2. 构造 BeeWriteEditor，切到富文本模式
  3. 调 rich_editor._insert_image_by_path 插入图片
     （注意：_insert_image_by_path 是 RichTextEditor 的方法，
      BeeWriteEditor 通过 self.rich_editor 访问）
  4. 调 _write_docx 导出到临时文件
  5. 用 python-docx 读回，找到含图片的段落
  6. 断言 alignment == CENTER，space_before/after ≈ 12pt

v5.0.5 hotfix：
  原测试误写为 beewrite_editor._insert_image_by_path(...)，
  但该方法定义在 RichTextEditor 上，导致 AttributeError。
  已改为 beewrite_editor.rich_editor._insert_image_by_path(...)。
"""
import pytest


try:
    from docx import Document as _DocxDocumentFactory
    from docx.shared import Pt
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    HAS_DOCX = True
except ImportError:
    HAS_DOCX = False

try:
    from PIL import Image
    HAS_PIL = True
except ImportError:
    HAS_PIL = False


# DOCX 里的 w:drawing / w:pict 命名空间
_W_NS = (
    "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
)


@pytest.fixture
def sample_image(tmp_path):
    """造一张小图片。"""
    if not HAS_PIL:
        pytest.skip("Pillow 未安装")
    img_path = tmp_path / "src.png"
    img = Image.new("RGB", (200, 100), color="blue")
    img.save(str(img_path))
    return img_path


def _paragraph_has_image(para):
    """检查 python-docx Paragraph 是否含图片。"""
    for run in para.runs:
        # DrawingML 图片
        if run._element.findall(f".//{_W_NS}drawing"):
            return True
        # VML 图片
        if run._element.findall(f".//{_W_NS}pict"):
            return True
    return False


def test_image_paragraph_centered_in_docx(
    beewrite_editor, tmp_path, sample_image
):
    """v5.0.4：导出 DOCX 后，图片段落应居中对齐。"""
    if not HAS_DOCX:
        pytest.skip("python-docx 未安装")

    # 切到富文本模式
    beewrite_editor._switch_mode("rich_text")

    # ★ 修正：_insert_image_by_path 是 RichTextEditor 的方法，
    #   通过 beewrite_editor.rich_editor 访问
    beewrite_editor.rich_editor._insert_image_by_path(str(sample_image))

    # 导出
    out = tmp_path / "test.docx"
    ok = beewrite_editor._write_docx(str(out))
    assert ok, "导出 DOCX 失败"

    # 读回 DOCX，找含图片的段落
    doc = _DocxDocumentFactory(str(out))
    image_paras = [
        p for p in doc.paragraphs if _paragraph_has_image(p)
    ]
    assert image_paras, (
        "导出的 DOCX 里未找到含图片的段落。"
        "_insert_picture_to_para 可能未成功插入图片"
    )

    for para in image_paras:
        fmt = para.paragraph_format
        assert fmt.alignment == WD_ALIGN_PARAGRAPH.CENTER, (
            f"v5.0.4：图片段落应居中，实际 alignment={fmt.alignment}"
        )


def test_image_paragraph_has_12pt_spacing(
    beewrite_editor, tmp_path, sample_image
):
    """v5.0.4：图片段落应有段前段后各 12pt 的间距。"""
    if not HAS_DOCX:
        pytest.skip("python-docx 未安装")

    beewrite_editor._switch_mode("rich_text")
    beewrite_editor.rich_editor._insert_image_by_path(str(sample_image))

    out = tmp_path / "test.docx"
    ok = beewrite_editor._write_docx(str(out))
    assert ok

    doc = _DocxDocumentFactory(str(out))
    image_paras = [
        p for p in doc.paragraphs if _paragraph_has_image(p)
    ]
    assert image_paras

    for para in image_paras:
        fmt = para.paragraph_format
        # Pt(12) 在 python-docx 里是 Length 对象
        expected = Pt(12)
        if fmt.space_before is not None:
            assert fmt.space_before == expected, (
                f"v5.0.4：段前应为 12pt，实际 {fmt.space_before}"
            )
        if fmt.space_after is not None:
            assert fmt.space_after == expected, (
                f"v5.0.4：段后应为 12pt，实际 {fmt.space_after}"
            )


def test_inserted_image_centered_in_editor(
    beewrite_editor, tmp_path, sample_image
):
    """
    v5.0.4 对照测试：导出前，Qt 编辑器里的图片段落应已居中。

    验证 _insert_image_by_path 的居中处理生效（Qt 侧），
    而非只在导出时才居中。
    """
    from PySide6.QtCore import Qt

    beewrite_editor._switch_mode("rich_text")
    beewrite_editor.rich_editor._insert_image_by_path(str(sample_image))

    doc = beewrite_editor.rich_editor.document()
    block = doc.begin()
    found_image_block = False
    while block.isValid():
        # 检查 block 是否含图片
        it = block.begin()
        has_img = False
        while not it.atEnd():
            frag = it.fragment()
            if frag.isValid() and frag.charFormat().isImageFormat():
                has_img = True
                break
            it += 1
        if has_img:
            found_image_block = True
            bf = block.blockFormat()
            assert bf.alignment() == Qt.AlignCenter, (
                f"v5.0.4：Qt 编辑器里的图片段落也应居中。"
                f"实际 alignment={bf.alignment()}"
            )
            break
        block = block.next()

    assert found_image_block, "未在编辑器里找到含图片的 block"