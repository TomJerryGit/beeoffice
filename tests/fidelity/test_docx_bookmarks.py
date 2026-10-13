# tests/fidelity/test_docx_bookmarks.py
"""
保真度阶段 A：DOCX **书签**往返。

背景与一次更正
--------------
Markdown 没有书签语法，所以书签在导入→导出之间必然丢失。
初看 7 份真实教程里有 5 份带书签（`bookmarks 1 → 0`），我据此推测"多半是目录
锚点 `_Toc…`，丢失会让内部跳转变死链"。

**查证后更正**：那 5 份里的书签**全是 `_GoBack`** —— Word 的"上次编辑位置"
内部标记，不是用户内容，也没有任何链接指向它，所以**不会造成死链**。
（教训：命中数量不等于严重程度，得看具体内容。）

即便如此仍然实现并保留：本工作的目标是"往返不改动用户的文件"，
`_GoBack` 也是文件的一部分；真正的用户书签（`_Toc…`、自定义锚点）走同一条通路。
**由于语料里只有 `_GoBack`，本文件必须自己构造真名书签来验证功能。**

定位策略（两处易错）
--------------------
1. 书签所在段落**可能是空段落**（实测两份真实文档的 `_GoBack` 就是空的），
   而空段落在 Markdown 里会丢 → **索引锚点必然失效**。所以额外记录
   `prev_text`（最近的前一个非空段落），挂到它之后。
2. `w:bookmarkStart` 必须插在 `w:pPr` **之后**，否则违反 OOXML 元素顺序。
"""
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from docx import Document                                  # noqa: E402
from docx.oxml import OxmlElement                          # noqa: E402
from docx.oxml.ns import qn                                # noqa: E402

from beeoffice.plugins.bee_export import (                 # noqa: E402
    _read_bookmarks,
    apply_bookmarks,
    export_to_docx,
    import_from_docx,
    read_docx_extras,
)


def _add_bookmark(para, name, bookmark_id="1"):
    start = OxmlElement("w:bookmarkStart")
    start.set(qn("w:id"), bookmark_id)
    start.set(qn("w:name"), name)
    end = OxmlElement("w:bookmarkEnd")
    end.set(qn("w:id"), bookmark_id)
    p = para._p
    pPr = p.find(qn("w:pPr"))
    # 与产品实现同样的规则：插在 pPr 之后，并跳过已有 bookmarkStart
    # （否则同段落多个书签会顺序颠倒 —— 我第一版夹具就踩了）
    children = list(p)
    pos = (children.index(pPr) + 1) if pPr is not None else 0
    while pos < len(children) and children[pos].tag == qn("w:bookmarkStart"):
        pos += 1
    p.insert(pos, start)
    p.append(end)


def _make_docx(path: Path, spec) -> Path:
    """spec: [(段落文字, [书签名, ...]), ...]"""
    doc = Document()
    idx = 1
    for text, names in spec:
        para = doc.add_paragraph(text)
        for name in names:
            _add_bookmark(para, name, str(idx))
            idx += 1
    doc.save(str(path))
    return path


def _roundtrip(src: Path, tmp_path: Path) -> Path:
    out = tmp_path / "out.docx"
    extras = read_docx_extras(src)
    assert export_to_docx(
        import_from_docx(str(src)), str(out),
        page_settings=extras, base_dir=str(tmp_path),
        header_text=extras.get("header_text"),
        footer_text=extras.get("footer_text"),
        table_merges=extras.get("table_merges"),
        sections=extras.get("sections"),
        bookmarks=extras.get("bookmarks"),
    ) is True
    return out


def _bookmark_names(path: Path):
    doc = Document(str(path))
    names = []
    for para in doc.paragraphs:
        for start in para._p.findall(qn("w:bookmarkStart")):
            names.append(start.get(qn("w:name")))
    return names


# ==================== 1. 读取 ====================

def test_reads_named_bookmark(tmp_path):
    src = _make_docx(tmp_path / "a.docx", [("目标段落", ["ch1"])])

    bookmarks = _read_bookmarks(Document(str(src)))

    assert len(bookmarks) == 1
    assert bookmarks[0]["name"] == "ch1"
    assert bookmarks[0]["paragraph_text"] == "目标段落"


def test_reads_docx_bookmarks_in_real_world_but_internal(tmp_path):
    """
    真实文档里那种 `_GoBack`（Word 内部标记）**也要保留** ——
    虽然它不是用户内容，但往返不该改动用户的文件。
    """
    src = _make_docx(tmp_path / "a.docx", [("参考文档：", ["_GoBack"])])

    bookmarks = _read_bookmarks(Document(str(src)))

    assert [b["name"] for b in bookmarks] == ["_GoBack"]


def test_records_prev_text_for_empty_paragraph_anchor(tmp_path):
    """书签落在空段落里时，必须记下"最近的前一个非空段落"作备用锚点。"""
    src = _make_docx(tmp_path / "a.docx", [
        ("上一段有文字", []),
        ("", ["ch1"]),
    ])

    bookmarks = _read_bookmarks(Document(str(src)))

    assert bookmarks[0]["paragraph_text"] == ""
    assert bookmarks[0]["prev_text"] == "上一段有文字", bookmarks[0]


def test_multiple_bookmarks(tmp_path):
    src = _make_docx(tmp_path / "a.docx", [
        ("第一段", ["b1"]),
        ("第二段", ["b2", "b3"]),
    ])

    names = [b["name"] for b in _read_bookmarks(Document(str(src)))]

    assert names == ["b1", "b2", "b3"], names


def test_no_bookmarks(tmp_path):
    doc = Document()
    doc.add_paragraph("没有书签")
    assert _read_bookmarks(doc) == []


# ==================== 2. 写回 ====================

def test_apply_restores_bookmark(tmp_path):
    doc = Document()
    doc.add_paragraph("目标段落")

    applied = apply_bookmarks(doc, [
        {"name": "ch1", "paragraph_text": "目标段落", "index": 0},
    ])

    assert applied == 1
    out = tmp_path / "o.docx"
    doc.save(str(out))
    assert _bookmark_names(out) == ["ch1"]


def test_bookmark_start_is_after_ppr(tmp_path):
    """
    `w:bookmarkStart` 必须排在 `w:pPr` **之后**。

    顺序错了 Word 会认为文档损坏（pPr 必须是 w:p 的第一个子元素）。
    """
    doc = Document()
    para = doc.add_paragraph("有样式的段落")
    para.style = doc.styles["Heading 1"]

    apply_bookmarks(doc, [
        {"name": "ch1", "paragraph_text": "有样式的段落", "index": 0},
    ])

    children = [child.tag for child in para._p]
    pPr_idx = children.index(qn("w:pPr"))
    start_idx = children.index(qn("w:bookmarkStart"))
    assert start_idx > pPr_idx, f"bookmarkStart 排在 pPr 之前: {children}"


def test_empty_paragraph_is_noop():
    doc = Document()
    assert apply_bookmarks(doc, None) == 0
    assert apply_bookmarks(doc, []) == 0


def test_unknown_anchor_is_skipped_not_crash():
    doc = Document()
    doc.add_paragraph("某段")

    applied = apply_bookmarks(doc, [
        {"name": "x", "paragraph_text": "不存在的段落", "index": 99},
    ])

    assert applied == 0


# ==================== 3. 端到端 ====================

def test_bookmark_name_survives_roundtrip(tmp_path):
    src = _make_docx(tmp_path / "a.docx", [("目标段落", ["ch1"])])
    out = _roundtrip(src, tmp_path)

    assert _bookmark_names(out) == ["ch1"], _bookmark_names(out)


def test_multiple_bookmarks_survive_roundtrip(tmp_path):
    src = _make_docx(tmp_path / "a.docx", [
        ("第一段", ["b1"]),
        ("第二段", ["b2"]),
    ])
    out = _roundtrip(src, tmp_path)

    assert _bookmark_names(out) == ["b1", "b2"], _bookmark_names(out)


def test_bookmark_in_empty_paragraph_survives(tmp_path):
    """
    **真实文档的情形**：书签落在空段落里（`_GoBack` 就是这样）。

    空段落在 Markdown 里会丢，所以索引锚点失效 —— 靠 `prev_text` 兜住。
    """
    src = _make_docx(tmp_path / "a.docx", [
        ("有文字的上一段", []),
        ("", ["_GoBack"]),
    ])
    out = _roundtrip(src, tmp_path)

    assert _bookmark_names(out) == ["_GoBack"], _bookmark_names(out)


def test_internal_link_and_bookmark_both_survive(tmp_path):
    """
    用户可见的价值：**书签 + 指向它的内部链接**都要保住。

    只保链接不保书签 = 死链；两者都在才叫"内部跳转可用"。
    """
    from docx.opc.constants import RELATIONSHIP_TYPE as RT   # noqa: F401

    src = tmp_path / "src.docx"
    doc = Document()
    target = doc.add_paragraph("目标段落")
    _add_bookmark(target, "ch1")

    link_para = doc.add_paragraph()
    link = OxmlElement("w:hyperlink")
    link.set(qn("w:anchor"), "ch1")
    run = OxmlElement("w:r")
    t = OxmlElement("w:t")
    t.text = "跳到目标"
    run.append(t)
    link.append(run)
    link_para._p.append(link)
    doc.save(str(src))

    out = _roundtrip(src, tmp_path)

    assert _bookmark_names(out) == ["ch1"], "书签丢了 → 内部跳转会变成死链"
    md = import_from_docx(str(src))
    assert "[跳到目标](#ch1)" in md, md


# ==================== 4. 编辑器与产品接线 ====================

def test_editor_carries_bookmarks(beewrite_editor):
    records = [{"name": "ch1", "paragraph_text": "目标", "index": 0}]

    beewrite_editor.apply_docx_extras({"bookmarks": records})

    assert beewrite_editor.get_docx_extras()["bookmarks"] == records


def test_editor_defaults_to_no_bookmarks(beewrite_editor):
    assert beewrite_editor.get_docx_extras()["bookmarks"] == []


def test_write_docx_restores_bookmark(beewrite_editor, tmp_path):
    """产品级：编辑器带着书签信息导出后，文件里必须真有书签。"""
    beewrite_editor.set_content("目标段落\n\n跳到目标的文字\n")
    beewrite_editor.apply_docx_extras({"bookmarks": [
        {"name": "ch1", "paragraph_text": "目标段落", "index": 0},
    ]})

    out = tmp_path / "b.docx"
    assert beewrite_editor._write_docx(str(out)) is True

    assert _bookmark_names(out) == ["ch1"], "导出的文件里没有书签"
