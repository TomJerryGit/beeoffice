# tests/fidelity/test_docx_paragraph_styles.py
"""
保真度阶段 A：**段落样式**往返，以及**强调标记的空格**问题。

### 1. 段落样式（`styled_paragraphs` 43 → 0）

实测 7 份真实教程里 3 份用了内置样式，其中 `yum源更新.docx` 有 **41 段
`HTML Preformatted`**（Word 给预格式化/代码文本的**等宽**样式）。
丢失后果：技术文档里几十段命令记录退化成普通正文，等宽版式全丢。

**关键难点**：python-docx 的默认模板里**没有**这些样式
（实测默认 164 个样式里既没有 `HTML Preformatted` 也没有 `Normal (Web)`），
所以不能只记样式名 —— 必须把**样式定义**一起搬过去（含 `w:basedOn` 链）。

两个踩过的坑：

1. **注入定义必须用 python-docx 自己的解析器**（`docx.oxml.parse_xml`）。
   `lxml.etree.fromstring` 造出的是裸 `_Element`，没有 python-docx 元素类的
   `.type` 属性 → `doc.styles[name]` 抛 `AttributeError`
   （`'lxml.etree._Element' object has no attribute 'type'`）。
   当时它被宽 `except` 吞掉，表现为"样式定义注入成功、但一段都没应用上"（返回 0）。
2. **同一个段落不能被用两次**：正文里有内容完全相同的段落（41 段代码记录里就有），
   只按"第一个文字相同"匹配会让它们全落到同一段上，43 段里只有 36 段装上样式。

### 2. 强调标记的首尾空格（**渲染才发现**）

Markdown 要求强调的收尾定界符不能紧跟在空白之后。实测源里存
`bold=True` 且**结尾带空格**的 run：

    'Linux-mount: 在 /dev/sr0 上找不到媒体 '

直接套成 `**…媒体 **` 后**星号原样显示**在文档里。
这个问题**结构性指标完全看不到**（`**` 也是字符，字符数不变），
只有把导出的 DOCX 真的渲染出来才看得见 —— 是 LibreOffice 渲染暴露的。
"""
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from docx import Document                                  # noqa: E402
from docx.enum.style import WD_STYLE_TYPE                  # noqa: E402

from beeoffice.plugins.bee_export import (                 # noqa: E402
    _read_paragraph_styles,
    _read_style_definitions,
    _wrap_emphasis,
    apply_paragraph_styles,
    export_to_docx,
    import_from_docx,
    read_docx_extras,
)


def _roundtrip(src: Path, tmp_path: Path) -> Path:
    out = tmp_path / "out.docx"
    extras = read_docx_extras(src)
    assert export_to_docx(
        import_from_docx(str(src)), str(out),
        page_settings=extras, base_dir=str(tmp_path),
        header_text=extras.get("header_text"),
        footer_text=extras.get("footer_text"),
        header_xml=extras.get("header_xml", ""),
        footer_xml=extras.get("footer_xml", ""),
        table_merges=extras.get("table_merges"),
        sections=extras.get("sections"),
        bookmarks=extras.get("bookmarks"),
        paragraph_styles=extras.get("paragraph_styles"),
        style_definitions=extras.get("style_definitions"),
    ) is True
    return out


def _make_docx_with_custom_style(path: Path, style_name="我的代码样式") -> Path:
    """建一个带**自定义**段落样式的文档（默认模板里没有它，必须靠搬定义）。"""
    doc = Document()
    style = doc.styles.add_style(style_name, WD_STYLE_TYPE.PARAGRAPH)
    style.base_style = doc.styles["Normal"]
    font = style.font
    font.name = "Courier New"

    doc.add_paragraph("普通一段")
    doc.add_paragraph("等宽代码第一行", style=style_name)
    doc.add_paragraph("等宽代码第二行", style=style_name)
    doc.save(str(path))
    return path


# ==================== 1. 读取 ====================

def test_reads_only_non_default_styles(tmp_path):
    src = _make_docx_with_custom_style(tmp_path / "a.docx")

    records = _read_paragraph_styles(Document(str(src)))

    assert [r["style"] for r in records] == ["我的代码样式"] * 2
    assert records[0]["paragraph_text"] == "等宽代码第一行"
    assert records[0]["index"] == 1


def test_default_normal_paragraphs_are_not_recorded(tmp_path):
    doc = Document()
    doc.add_paragraph("普通段落")
    assert _read_paragraph_styles(doc) == []


def test_style_definition_includes_based_on_chain(tmp_path):
    """`w:basedOn` 指向的样式也要一起搬，否则定义站不住。"""
    src = _make_docx_with_custom_style(tmp_path / "a.docx")

    definitions = _read_style_definitions(
        Document(str(src)), {"我的代码样式"}
    )

    assert "我的代码样式" in definitions
    assert "Normal" in definitions, "basedOn 的基样式没被带上"


# ==================== 2. 注入与应用 ====================

def test_injects_definition_so_python_docx_can_resolve_it(tmp_path):
    """
    **回归**：注入的样式必须能被 python-docx 解析。

    踩过的坑：用 `lxml.etree.fromstring` 注入的是裸 `_Element`，
    `doc.styles[name]` 会抛 `AttributeError: ... has no attribute 'type'`。
    """
    src = _make_docx_with_custom_style(tmp_path / "a.docx")
    definitions = _read_style_definitions(
        Document(str(src)), {"我的代码样式"}
    )

    doc = Document()
    doc.add_paragraph("代码行")
    apply_paragraph_styles(
        doc,
        [{"style": "我的代码样式", "paragraph_text": "代码行", "index": 0}],
        definitions,
    )

    assert doc.styles["我的代码样式"].name == "我的代码样式"
    assert doc.paragraphs[0].style.name == "我的代码样式"


def test_each_paragraph_is_used_once(tmp_path):
    """
    **回归**：内容相同的多个段落必须**各自**装上样式。

    实测 41 段代码记录里有重复内容，只按"第一个文字相同"匹配会让它们
    全落到同一段上（43 段只装上 36 段）。
    """
    src = _make_docx_with_custom_style(tmp_path / "a.docx")
    definitions = _read_style_definitions(
        Document(str(src)), {"我的代码样式"}
    )

    doc = Document()
    for _ in range(3):
        doc.add_paragraph("一模一样的行")
    applied = apply_paragraph_styles(
        doc,
        [{"style": "我的代码样式", "paragraph_text": "一模一样的行",
          "index": i} for i in range(3)],
        definitions,
    )

    assert applied == 3, f"只应用了 {applied} 段"
    assert all(p.style.name == "我的代码样式" for p in doc.paragraphs)


def test_style_id_collision_is_renamed(tmp_path):
    """`w:styleId` 撞车时应改名而不是覆盖已有样式。"""
    src = _make_docx_with_custom_style(tmp_path / "a.docx")
    definitions = _read_style_definitions(
        Document(str(src)), {"我的代码样式"}
    )
    # 人为弄成与内置样式相同的 styleId
    xml = definitions["我的代码样式"]
    xml = xml.replace('w:styleId="', 'w:styleId="Normal_', 1)
    definitions["我的代码样式"] = xml

    doc = Document()
    doc.add_paragraph("x")
    apply_paragraph_styles(
        doc, [{"style": "我的代码样式", "paragraph_text": "x", "index": 0}],
        definitions,
    )

    assert doc.styles["我的代码样式"].name == "我的代码样式"


def test_unknown_style_is_skipped_not_crash():
    doc = Document()
    doc.add_paragraph("x")

    applied = apply_paragraph_styles(
        doc, [{"style": "并不存在的样式", "paragraph_text": "x", "index": 0}],
        {},
    )

    assert applied == 0


def test_empty_input_is_noop():
    doc = Document()
    assert apply_paragraph_styles(doc, None, None) == 0
    assert apply_paragraph_styles(doc, [], {}) == 0


# ==================== 3. 端到端 ====================

def test_custom_style_survives_roundtrip(tmp_path):
    """**核心**：自定义段落样式往返后仍在。"""
    src = _make_docx_with_custom_style(tmp_path / "a.docx")
    out = _roundtrip(src, tmp_path)

    doc = Document(str(out))
    styled = [p for p in doc.paragraphs if p.style.name == "我的代码样式"]
    assert len(styled) == 2, (
        f"带样式的段落数变了: {[p.style.name for p in doc.paragraphs]}"
    )
    assert styled[0].text == "等宽代码第一行"


def test_style_definition_is_present_in_output(tmp_path):
    """不只是应用了样式名，**定义**也要在（否则 Word 里显示成普通正文）。"""
    src = _make_docx_with_custom_style(tmp_path / "a.docx")
    out = _roundtrip(src, tmp_path)

    names = [s.name for s in Document(str(out)).styles]
    assert "我的代码样式" in names


def test_write_docx_applies_styles(beewrite_editor, tmp_path):
    """产品级：编辑器带着样式信息导出后，文件里段落样式真的装上了。"""
    src = _make_docx_with_custom_style(tmp_path / "src.docx")
    extras = read_docx_extras(src)

    beewrite_editor.set_content("等宽代码第一行\n\n等宽代码第二行\n")
    beewrite_editor.apply_docx_extras(extras)

    out = tmp_path / "styled.docx"
    assert beewrite_editor._write_docx(str(out)) is True

    doc = Document(str(out))
    assert "我的代码样式" in [s.name for s in doc.styles]
    assert any(p.style.name == "我的代码样式" for p in doc.paragraphs)


# ==================== 4. 强调标记的首尾空格 ====================

def test_wrap_emphasis_moves_trailing_space_out():
    assert _wrap_emphasis("文字 ", "**") == "**文字** "
    assert _wrap_emphasis(" 文字", "**") == " **文字**"
    assert _wrap_emphasis(" 文字 ", "**") == " **文字** "


def test_wrap_emphasis_leaves_normal_text():
    assert _wrap_emphasis("文字", "**") == "**文字**"


def test_wrap_emphasis_ignores_whitespace_only():
    assert _wrap_emphasis("   ", "**") == "   "
    assert _wrap_emphasis("", "**") == ""


def test_bold_run_with_trailing_space_roundtrips(tmp_path):
    """
    **渲染暴露的缺陷**：`bold=True` 且结尾带空格的 run 曾转成 `**… **`，
    Markdown 不解析 → 星号原样显示。修复后收尾标记紧跟文字。
    """
    src = tmp_path / "src.docx"
    doc = Document()
    para = doc.add_paragraph()
    run = para.add_run("加粗文字 ")
    run.bold = True
    doc.save(str(src))

    md = import_from_docx(str(src))
    line = next(ln for ln in md.splitlines() if "加粗文字" in ln)
    assert line == "**加粗文字** ", f"星号位置不对，会原样显示: {line!r}"

    out = _roundtrip(src, tmp_path)
    out_para = [p for p in Document(str(out)).paragraphs
                if p.text.strip()][0]
    assert out_para.text == "加粗文字 ", out_para.text
    assert out_para.runs[0].bold is True, "加粗丢了"


def test_italic_run_with_trailing_space_roundtrips(tmp_path):
    src = tmp_path / "src.docx"
    doc = Document()
    para = doc.add_paragraph()
    run = para.add_run("斜体文字 ")
    run.italic = True
    doc.save(str(src))

    md = import_from_docx(str(src))
    line = next(ln for ln in md.splitlines() if "斜体文字" in ln)
    assert line == "*斜体文字* ", repr(line)
