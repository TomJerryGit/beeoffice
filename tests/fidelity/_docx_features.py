"""
构造含"难以保真"构造的 DOCX 夹具，用于**实测**这些构造在往返中的真实命运。

为什么要造这些夹具：写"导出前损失提示"必须**准确**——
把实际能保住的构造说成会丢，用户就被误导了。而 python-docx 无法创建
脚注/批注/文本框/公式/OLE/修订/内容控件，只能直接注入 OOXML。

用法：
    from _docx_features import FEATURES, build_feature_docx
    build_feature_docx(path)          # 一个文档里塞进尽量多的构造
    build_feature_docx(path, only=["textbox"])   # 只要某一个
"""
import shutil
import zipfile
from pathlib import Path

from docx import Document
from docx.oxml import OxmlElement
from docx.oxml.ns import qn

W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
M = "http://schemas.openxmlformats.org/officeDocument/2006/math"
R = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
V = "urn:schemas-microsoft-com:vml"

#: 构造名 → 中文说明（也是损失报告里给用户看的措辞依据）
FEATURES = {
    "nested_table": "嵌套表格（单元格里的表格）",
    "textbox": "文本框",
    "equation": "公式（OMML）",
    "tracked_change": "修订痕迹（插入/删除）",
    "content_control": "内容控件（结构化文档标签）",
    "toc_field": "目录域",
    "footnote": "脚注",
    "comment": "批注",
    "legacy_vml": "旧版 VML 图形",
}


def _body(document):
    return document.element.body


def _add_nested_table(document):
    """在表格单元格里再放一张表格。"""
    outer = document.add_table(rows=1, cols=1)
    cell = outer.cell(0, 0)
    cell.text = "外层单元格"
    inner = cell.add_table(rows=1, cols=1) if hasattr(cell, "add_table") \
        else None
    if inner is not None:
        inner.cell(0, 0).text = "内层表格内容"
        return
    # python-docx 版本不支持 cell.add_table 时手搓
    tbl = OxmlElement("w:tbl")
    tr = OxmlElement("w:tr")
    tc = OxmlElement("w:tc")
    para = OxmlElement("w:p")
    run = OxmlElement("w:r")
    text = OxmlElement("w:t")
    text.text = "内层表格内容"
    run.append(text)
    para.append(run)
    tc.append(para)
    tr.append(tc)
    tbl.append(tr)
    cell._tc.append(tbl)


def _add_textbox(document):
    """文本框：w:pict > v:shape > v:textbox > w:txbxContent（含一个段落）。"""
    xml = (
        f'<w:p xmlns:w="{W}" xmlns:v="{V}">'
        '<w:r><w:pict>'
        '<v:shape style="width:100pt;height:40pt">'
        '<v:textbox><w:txbxContent>'
        '<w:p><w:r><w:t>文本框里的文字</w:t></w:r></w:p>'
        '</w:txbxContent></v:textbox>'
        '</v:shape></w:pict></w:r></w:p>'
    )
    _append_xml(document, xml)


def _add_equation(document):
    """OMML 公式：m:oMath，里面的 m:t 承载公式文本。"""
    xml = (
        f'<w:p xmlns:w="{W}" xmlns:m="{M}">'
        '<m:oMath>'
        '<m:r><m:t>x</m:t></m:r>'
        '<m:r><m:t>=</m:t></m:r>'
        '<m:r><m:t>1</m:t></m:r>'
        '</m:oMath>'
        '</w:p>'
    )
    _append_xml(document, xml)


def _add_tracked_change(document):
    """修订：w:ins（插入）与 w:del（删除，文字在 w:delText 里）。"""
    xml = (
        f'<w:p xmlns:w="{W}">'
        '<w:r><w:t>前</w:t></w:r>'
        '<w:ins w:id="10" w:author="审阅者" w:date="2020-01-01T00:00:00Z">'
        '<w:r><w:t>新增的文字</w:t></w:r></w:ins>'
        '<w:del w:id="11" w:author="审阅者" w:date="2020-01-01T00:00:00Z">'
        '<w:r><w:delText>被删除的文字</w:delText></w:r></w:del>'
        '<w:r><w:t>后</w:t></w:r>'
        '</w:p>'
    )
    _append_xml(document, xml)


def _add_content_control(document):
    """内容控件：w:sdt > w:sdtContent > w:p。"""
    xml = (
        f'<w:p xmlns:w="{W}">'
        '<w:sdt><w:sdtPr><w:tag w:val="mytag"/></w:sdtPr>'
        '<w:sdtContent>'
        '<w:r><w:t>控件里的文字</w:t></w:r>'
        '</w:sdtContent></w:sdt>'
        '</w:p>'
    )
    _append_xml(document, xml)


def _add_toc_field(document):
    """目录域（复杂域）：fldChar begin → instrText TOC → separate → 结果 → end。"""
    xml = (
        f'<w:p xmlns:w="{W}">'
        '<w:r><w:fldChar w:fldCharType="begin"/></w:r>'
        '<w:r><w:instrText xml:space="preserve"> TOC \\o "1-3" </w:instrText></w:r>'
        '<w:r><w:fldChar w:fldCharType="separate"/></w:r>'
        '<w:r><w:t>第一章 ......... 1</w:t></w:r>'
        '<w:r><w:fldChar w:fldCharType="end"/></w:r>'
        '</w:p>'
    )
    _append_xml(document, xml)


def _add_legacy_vml(document):
    """旧版 VML 图形（非文本框，仅一个 shape，通常带图片引用）。"""
    xml = (
        f'<w:p xmlns:w="{W}" xmlns:v="{V}">'
        '<w:r><w:pict><v:rect style="width:50pt;height:20pt"/></w:pict></w:r>'
        '</w:p>'
    )
    _append_xml(document, xml)


def _append_xml(document, xml):
    """把一段 XML 追加到正文末尾（runs 与段落都直接挂到 body）。"""
    from lxml import etree

    wrapper = etree.fromstring(
        f'<w:root xmlns:w="{W}" xmlns:m="{M}" xmlns:r="{R}" '
        f'xmlns:v="{V}">{xml}</w:root>'
    )
    body = _body(document)
    for child in wrapper:
        body.append(child)


def _inject_part(docx_path: Path, part_name: str, payload: bytes,
                 content_type: str, rel_id: str, rel_type: str):
    """往已保存的 docx 里塞入一个新部件 + 内容类型 + 关系。"""
    from lxml import etree

    temp = docx_path.with_suffix(".tmp.docx")
    with zipfile.ZipFile(docx_path) as src, \
            zipfile.ZipFile(temp, "w", zipfile.ZIP_DEFLATED) as dst:
        for item in src.infolist():
            data = src.read(item.filename)
            if item.filename == "[Content_Types].xml":
                root = etree.fromstring(data)
                ns = root.nsmap[None]
                override = etree.SubElement(root, f"{{{ns}}}Override")
                override.set("PartName", f"/{part_name}")
                override.set("ContentType", content_type)
                data = etree.tostring(root, xml_declaration=True,
                                      encoding="UTF-8", standalone=True)
            elif item.filename == "word/_rels/document.xml.rels":
                root = etree.fromstring(data)
                ns = root.nsmap[None]
                rel = etree.SubElement(root, f"{{{ns}}}Relationship")
                rel.set("Id", rel_id)
                rel.set("Type", rel_type)
                rel.set("Target", part_name.replace("word/", ""))
                data = etree.tostring(root, xml_declaration=True,
                                      encoding="UTF-8", standalone=True)
            dst.writestr(item, data)
        dst.writestr(part_name, payload)
    shutil.move(str(temp), str(docx_path))


def _add_footnote(document, docx_path: Path):
    """脚注：正文里一个 w:footnoteReference + word/footnotes.xml。"""
    xml = (
        f'<w:p xmlns:w="{W}">'
        '<w:r><w:t>正文有脚注</w:t></w:r>'
        '<w:r><w:footnoteReference w:id="1"/></w:r>'
        '</w:p>'
    )
    _append_xml(document, xml)
    document.save(str(docx_path))

    footnotes = (
        f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        f'<w:footnotes xmlns:w="{W}">'
        '<w:footnote w:id="1"><w:p><w:r>'
        '<w:t>这是脚注的正文内容</w:t></w:r></w:p></w:footnote>'
        '</w:footnotes>'
    ).encode("utf-8")
    _inject_part(
        docx_path, "word/footnotes.xml", footnotes,
        "application/vnd.openxmlformats-officedocument."
        "wordprocessingml.footnotes+xml",
        "rIdFootnotes",
        f"{R}/footnotes",
    )


def _add_comment(document, docx_path: Path):
    """批注：commentRangeStart/End + commentReference + word/comments.xml。"""
    xml = (
        f'<w:p xmlns:w="{W}">'
        '<w:r><w:t>被批注的文字</w:t></w:r>'
        '<w:commentRangeStart w:id="1"/>'
        '<w:r><w:t>这段有批注</w:t></w:r>'
        '<w:commentRangeEnd w:id="1"/>'
        '<w:r><w:commentReference w:id="1"/></w:r>'
        '</w:p>'
    )
    _append_xml(document, xml)
    document.save(str(docx_path))

    comments = (
        f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        f'<w:comments xmlns:w="{W}">'
        '<w:comment w:id="1" w:author="审阅者" w:date="2020-01-01T00:00:00Z">'
        '<w:p><w:r><w:t>这是一条批注</w:t></w:r></w:p>'
        '</w:comment></w:comments>'
    ).encode("utf-8")
    _inject_part(
        docx_path, "word/comments.xml", comments,
        "application/vnd.openxmlformats-officedocument."
        "wordprocessingml.comments+xml",
        "rIdComments",
        f"{R}/comments",
    )


_INLINE_BUILDERS = {
    "nested_table": _add_nested_table,
    "textbox": _add_textbox,
    "equation": _add_equation,
    "tracked_change": _add_tracked_change,
    "content_control": _add_content_control,
    "toc_field": _add_toc_field,
    "legacy_vml": _add_legacy_vml,
}


def build_feature_docx(path, only=None) -> Path:
    """
    生成含指定"难保真"构造的 DOCX。

    :param only: 只要这些构造（None = 全部内联构造 + 脚注 + 批注）
    """
    path = Path(path)
    wanted = set(only) if only else set(FEATURES)

    document = Document()
    document.add_paragraph("普通正文第一段")

    for name, builder in _INLINE_BUILDERS.items():
        if name in wanted:
            builder(document)

    needs_late_part = bool(wanted & {"footnote", "comment"})
    if needs_late_part:
        # 先把文档存下来（后面要往 zip 里加部件）
        pass

    document.add_paragraph("普通正文最后一段")

    if "footnote" in wanted and "comment" in wanted:
        # 两个都要：先存盘加脚注，再加批注（每次都会重写 zip）
        _add_footnote(document, path)
        _add_comment(document, path)
        return path
    if "footnote" in wanted:
        _add_footnote(document, path)
        return path
    if "comment" in wanted:
        _add_comment(document, path)
        return path

    document.save(str(path))
    return path
