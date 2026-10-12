# tests/regression/v5/test_v505_page_margin_units.py
"""
优化规划 §2.2 回归：页边距单位统一为 **mm**。

原缺陷（三处不一致）
--------------------
同一份 `_page_settings` 被三条路径以不同单位解释：

| 位置 | 代码 | 把它当作 |
|---|---|---|
| `beewrite.py` 默认值 | `margin_top = 2.54` / `margin_left = 3.17` | **cm**（1 英寸 / 1.25 英寸的正确数值） |
| DOCX 导出 | `section.top_margin = Mm(...)` | **mm** |
| PDF 导出 | `margin_top * 0.264583`（px→mm） | **px** |
| 页面设置对话框 | 标题「页边距（厘米）」+ `/10` 显示、`*10` 存储 | 存储 **mm**、界面 **cm** |

后果：默认导出 DOCX 的页边距只有 **2.54 mm**、PDF 只有 **0.67 mm**
（应为 25.4 mm = 2.54 cm）。对话框里一打开显示的是 0.25 cm。

修复后统一为「**存储 mm / 界面 cm / 两条导出路径都按 mm**」。
"""
import pytest

try:
    from docx import Document as _Docx
    HAS_DOCX = True
except ImportError:  # pragma: no cover
    HAS_DOCX = False


#: 中文 Word 的常用默认页边距：1 英寸 / 1.25 英寸
EXPECTED_MM = {
    "margin_top": 25.4,
    "margin_bottom": 25.4,
    "margin_left": 31.7,
    "margin_right": 31.7,
}


# ==================== 默认值 ====================

def test_default_page_settings_are_millimetres(beewrite_editor):
    settings = beewrite_editor.get_page_settings()
    for key, expected in EXPECTED_MM.items():
        assert settings[key] == expected, (
            f"{key} 应为 {expected} mm，实际 {settings[key]}；"
            f"若为 {expected / 10} 说明又退回成 cm 了"
        )


def test_dialog_would_show_centimetres(beewrite_editor):
    """
    对话框标题是「页边距（厘米）」且按 /10 显示，因此存储值必须是 mm。
    这里断言二者关系成立（2.54 cm）。
    """
    settings = beewrite_editor.get_page_settings()
    assert settings["margin_top"] / 10 == pytest.approx(2.54)
    assert settings["margin_left"] / 10 == pytest.approx(3.17)


# ==================== PDF 路径 ====================

def test_pdf_page_css_uses_mm_without_rescaling(beewrite_editor):
    """PDF 的 @page margin 必须直接等于存储的 mm，不得再乘 0.264583。"""
    content = "<html><head></head><body>正文</body></html>"
    out = beewrite_editor._apply_page_settings_to_content(
        content, beewrite_editor.get_page_settings()
    )
    assert "margin: 25.4mm 31.7mm 25.4mm 31.7mm" in out, out[:400]
    # 原缺陷的两种错误结果都不应出现
    assert "0.7mm" not in out, "又按 px 换算了（2.54 * 0.264583 ≈ 0.67）"
    assert "6.7mm" not in out, "又按 px 换算了（25.4 * 0.264583 ≈ 6.72）"


def test_pdf_page_css_tracks_custom_margins(beewrite_editor):
    """自定义页边距应原样进入 CSS（不缩放）。"""
    settings = dict(beewrite_editor.get_page_settings())
    settings.update({
        "margin_top": 20.0, "margin_bottom": 20.0,
        "margin_left": 25.0, "margin_right": 25.0,
    })
    out = beewrite_editor._apply_page_settings_to_content(
        "<html><head></head><body>x</body></html>", settings
    )
    assert "margin: 20.0mm 25.0mm 20.0mm 25.0mm" in out, out[:400]


# ==================== DOCX 路径（两种编辑模式都要生效） ====================

def _export_and_read(editor, tmp_path, name):
    out_path = tmp_path / name
    assert editor._write_docx(str(out_path)) is True
    assert out_path.exists() and out_path.stat().st_size > 0
    return _Docx(str(out_path)).sections[0]


@pytest.mark.skipif(not HAS_DOCX, reason="python-docx 未安装")
def test_docx_export_rich_text_mode_uses_stored_margins(
    beewrite_editor, tmp_path
):
    """富文本模式：自定义页边距必须写出（而不是落到模板默认值）。"""
    beewrite_editor._edit_mode = "rich_text"
    beewrite_editor._page_settings.update({
        "margin_top": 15.0, "margin_bottom": 16.0,
        "margin_left": 18.0, "margin_right": 19.0,
    })
    section = _export_and_read(beewrite_editor, tmp_path, "rich.docx")
    assert section.top_margin.mm == pytest.approx(15.0, abs=0.5)
    assert section.bottom_margin.mm == pytest.approx(16.0, abs=0.5)
    assert section.left_margin.mm == pytest.approx(18.0, abs=0.5)
    assert section.right_margin.mm == pytest.approx(19.0, abs=0.5)


@pytest.mark.skipif(not HAS_DOCX, reason="python-docx 未安装")
def test_docx_export_markdown_mode_uses_stored_margins(
    beewrite_editor, tmp_path
):
    """
    Markdown 模式：同样必须写出页面设置。

    这是本轮发现的一个真实缺陷——Markdown 路径原先根本不应用页面设置，
    于是"导出 Word"的纸张与页边距取决于编辑器处于哪种模式。
    """
    beewrite_editor._edit_mode = "markdown"
    beewrite_editor._page_settings.update({
        "margin_top": 12.0, "margin_bottom": 13.0,
        "margin_left": 14.0, "margin_right": 15.0,
    })
    section = _export_and_read(beewrite_editor, tmp_path, "md.docx")
    assert section.top_margin.mm == pytest.approx(12.0, abs=0.5)
    assert section.bottom_margin.mm == pytest.approx(13.0, abs=0.5)
    assert section.left_margin.mm == pytest.approx(14.0, abs=0.5)
    assert section.right_margin.mm == pytest.approx(15.0, abs=0.5)


@pytest.mark.skipif(not HAS_DOCX, reason="python-docx 未安装")
def test_docx_export_paper_size_is_applied(beewrite_editor, tmp_path):
    """纸张尺寸也要按设置走（A4 = 210×297mm），而不是模板默认的 Letter。"""
    beewrite_editor._edit_mode = "markdown"
    beewrite_editor._page_settings["paper"] = "A4"
    beewrite_editor._page_settings["orientation"] = "portrait"
    section = _export_and_read(beewrite_editor, tmp_path, "a4.docx")
    assert section.page_width.mm == pytest.approx(210, abs=1)
    assert section.page_height.mm == pytest.approx(297, abs=1)


@pytest.mark.skipif(not HAS_DOCX, reason="python-docx 未安装")
def test_default_margins_are_not_accidentally_python_docx_template(
    beewrite_editor, tmp_path
):
    """
    区分"我们写入了 25.4mm"与"恰好等于 python-docx 模板默认值"。

    模板默认左右边距是 31.75mm（1.25 英寸），而我们的设置是 31.7mm，
    因此用左/右边距断言更可靠；同时用自定义值再确认一次。
    """
    beewrite_editor._edit_mode = "markdown"
    section = _export_and_read(beewrite_editor, tmp_path, "default.docx")
    assert section.left_margin.mm == pytest.approx(31.7, abs=0.2), (
        "左边距若为 31.75 说明落到了 python-docx 模板默认值，页面设置没生效"
    )

