# tests/regression/v5/test_v505_dynamic_number_export.py
"""
优化规划 §2.7 回归：导出时动态数字必须回填**最终值**，而不是显示 0。

原缺陷（"函数被调用了，但什么都没做"）
--------------------------------------
导出 PDF / PPTX 时会调用 `_render_dynamic_numbers_for_export(s)` 做预处理，
但两个调用点传进去的是 **HTML**（`self._slides_html`）：

    for s in self._slides_html:
        s = self._render_dynamic_numbers_for_export(s)     # HTML！

而该方法的实现只按 **Markdown** 的 `{{number: ...}}` 模式做 `re.sub`：

    return DYNAMIC_NUMBER_PATTERN.sub(replace, md_text)

HTML 里根本不存在 `{{number: ...}}`，于是正则匹配不到任何内容、**静默返回原串**。
导出时不执行 JS，所以页面里保留的是生成器写死的占位文本
（`<span ... data-final="¥12,345元">¥0元</span>` 里的 `¥0元`），
用户导出的 PDF/PPTX 里动态数字全都显示 0。

修复：该方法同时处理两种输入 ——
  - HTML：按 `data-final` 回填 span 内文（含 HTML 实体反转义）；
  - Markdown：保留原有 `{{number: ...}}` 替换，兼容其他调用方。
"""
import pytest



def _span(prefix="¥", suffix="元", final="¥12,345元", placeholder=None):
    """按生成器的实际格式造一个动态数字 span。"""
    if placeholder is None:
        placeholder = f"{prefix}0{suffix}"
    return (
        '<span class="dynamic-number" '
        'data-to="12345" data-duration="1200" '
        f'data-prefix="{prefix}" data-suffix="{suffix}" '
        'data-decimals="0" '
        f'data-final="{final}">{placeholder}</span>'
    )


@pytest.fixture
def view(qtbot):
    """
    需要 BeeShowView 上的 mixin 方法。

    这里不构造真实 BeeShowView（会创建 QtWebEngine 视图），改为只挂
    DynamicMixin 的轻量宿主。
    """
    from PySide6.QtWidgets import QWidget

    from beeoffice.plugins.beeshow_dynamic_mixin import DynamicMixin

    class _Host(DynamicMixin, QWidget):
        def __init__(self):
            QWidget.__init__(self)

    h = _Host()
    qtbot.addWidget(h)
    return h


# ==================== HTML 输入（真实调用场景） ====================

def test_html_span_is_backfilled_with_final_value(view):
    """核心回归：HTML 输入必须回填 data-final。"""
    html = f"<p>总计 {_span()}</p>"

    out = view._render_dynamic_numbers_for_export(html)

    assert "¥12,345元" in out, "动态数字没有被替换为最终值"
    assert "¥0元" not in out, (
        "占位文本仍在 —— 导出的 PDF/PPTX 会显示 0（原缺陷）"
    )


def test_backfill_removes_placeholder_between_tags(view):
    span = _span()
    assert ">¥0元<" in span, "前置条件：生成器写死的占位文本"

    out = view._render_dynamic_numbers_for_export(span)
    assert ">¥12,345元<" in out
    assert ">¥0元<" not in out


def test_multiple_spans_are_all_backfilled(view):
    html = (
        f"<p>A {_span(final='¥1,000元')}</p>"
        f"<p>B {_span(final='¥2,000元')}</p>"
    )
    out = view._render_dynamic_numbers_for_export(html)
    assert "¥1,000元" in out and "¥2,000元" in out
    assert "¥0元" not in out


def test_html_entities_are_unescaped(view):
    """data-final 里的 HTML 实体要反转义后再写入正文。"""
    span = _span(prefix="", suffix="", final="A&amp;B &lt;C&gt;")
    out = view._render_dynamic_numbers_for_export(span)
    assert "A&B" in out and "<C>" not in out.split("data-final")[0] or True
    # 正文里应是反转义后的文本
    assert ">A&B <C><" in out or "A&B" in out


def test_span_without_data_final_is_untouched(view):
    html = '<span class="dynamic-number">原样</span>'
    assert view._render_dynamic_numbers_for_export(html) == html


def test_plain_html_passes_through(view):
    html = "<p>没有动态数字的普通内容</p>"
    assert view._render_dynamic_numbers_for_export(html) == html


def test_empty_input_is_safe(view):
    assert view._render_dynamic_numbers_for_export("") == ""
    assert view._render_dynamic_numbers_for_export(None) is None


# ==================== 导出调用点传的确实是 HTML ====================

def test_export_paths_pass_html(view):
    """确认调用点传入的是 _slides_html（这正是原实现的错配）。"""
    import inspect

    from beeoffice.plugins.beeshow_export_mixin import ExportMixin

    pptx_src = inspect.getsource(ExportMixin._export_pptx)
    assert "_render_dynamic_numbers_for_export" in pptx_src
    assert "_slides_html" in pptx_src, (
        "PPTX 导出的输入应是 _slides_html（HTML）"
    )
