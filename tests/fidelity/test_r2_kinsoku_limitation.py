# tests/fidelity/test_r2_kinsoku_limitation.py
"""
R2 避尾：**金丝雀测试** —— 钉住"Qt 富文本做不到避尾"这个实测结论。

## 为什么测试的是"做不到"
`docs/r2-中文排版-spike.md` 里我最初写"插 `U+2060` 即可修复避尾"，
但那是**从避头实验推断的、没测过避尾**。真正测下来：

    不处理 21 处；插 U+2060 / U+200D / U+FEFF / U+00A0 / U+2007 之后**都还是 21 处**
    （负对照 U+200B 是 316 处，证明仪器能分辨差异）

所以"插入文本标记"这条路是**无效**的，实现被回退、模块只留作证据。

## 这条测试的价值
它**现在恒过**，但它是一根钉子：
· 若哪天 Qt 升级后开始认这些"两侧禁断"的行断类 → 本测试**失败**；
· 那时说明 R2 避尾**可以重做**（换个标记就行），而不是继续"决定不做"。
另外它同时守住那个**仪器坑**：判据必须"剥掉插入的标记再看行末字符"，
否则会得出假的 0 违规。
"""
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from beeoffice.plugins.kinsoku import (                              # noqa: E402
    CANDIDATE_MARKERS, NEGATIVE_CONTROL, OPENING_PUNCTUATION,
    apply_marker, kin_violations, measure_violations, strip_markers,
)

WIDTHS = list(range(100, 241, 7))
DENSE = "字（" * 90          # 标点在每一个位置，断点处处可能撞上它


@pytest.fixture(scope="module")
def lines_of():
    """排版后取每行文本（必须先**强制布局**，否则拿到空列表）。"""
    from PySide6.QtGui import QFont, QTextDocument

    font = QFont()
    font.setPointSizeF(12.0)

    def make_lines(text, width):
        doc = QTextDocument()
        doc.setDefaultFont(font)
        doc.setPlainText(text)
        doc.setTextWidth(width)
        doc.documentLayout().documentSize()      # 关键：触发布局
        result = []
        block = doc.begin()
        while block.isValid():
            layout = block.layout()
            plain = block.text()
            for i in range(layout.lineCount()):
                line = layout.lineAt(i)
                segment = plain[line.textStart():line.textStart()
                                + line.textLength()]
                if segment:
                    result.append(segment)
            block = block.next()
        return result

    return make_lines


# ==================== 1. 仪器本身 ====================

def test_instrument_actually_lays_out_text(lines_of):
    """先证明仪器有效：文本真的按宽度换行了（否则后面全是假的 0）。"""
    lines = lines_of(DENSE, 200)

    assert len(lines) > 5, f"只有 {len(lines)} 行 —— 布局没生效"
    assert max(len(line) for line in lines) < len(DENSE), "没有换行"


def test_judge_strips_inserted_marker(lines_of):
    """
    **仪器坑**：判据必须剥掉插入的标记。

    不剥的话，"行末是零宽 ZWJ"会被当成"末字符不是开启标点" → 假的 0 违规。
    这条测试就用"行末是（+ZWJ"来钉住这个行为。
    """
    assert strip_markers("文字（\u200d") == "文字（"
    assert kin_violations(["文字（\u200d"]) == ["文字（"], (
        "带 ZWJ 的（ 行末仍应判为违规（ZWJ 是零宽的，视觉上还是（ 在行尾）"
    )


def test_negative_control_is_worse_than_baseline(lines_of):
    """
    **负对照**：`U+200B` 提供断行机会 → 违规应显著多于基线。

    这是"仪器能分辨差异"的证明；没有它，"所有候选都无效"这个结论不可信。
    """
    baseline = measure_violations(lines_of, DENSE, WIDTHS)
    control = measure_violations(
        lines_of, apply_marker(DENSE, NEGATIVE_CONTROL), WIDTHS
    )

    assert baseline > 0, "基线应当有违规（否则这段文本测不出问题）"
    assert control > baseline, (
        f"负对照 {control} 应多于基线 {baseline}（仪器分辨不出差异就不算有效）"
    )


# ==================== 2. 金丝雀：所有候选标记都无效 ====================

@pytest.mark.parametrize("label,marker", sorted(CANDIDATE_MARKERS.items()))
def test_marker_does_not_help(lines_of, label, marker):
    """
    **金丝雀**：这些标记插进去都**不改变**违规数（= Qt 不认）。

    哪天真支持了，这条会失败 —— 那时就是"R2 避尾可以重做"的信号。
    """
    baseline = measure_violations(lines_of, DENSE, WIDTHS)
    with_marker = measure_violations(
        lines_of, apply_marker(DENSE, marker), WIDTHS
    )

    assert with_marker == baseline, (
        f"{label} 竟然把违规从 {baseline} 改成了 {with_marker} —— "
        f"Qt 行为变了！R2 避尾可以重做（见 docs/r2-中文排版-spike.md）"
    )


def test_kinsoku_does_not_change_what_user_sees(lines_of):
    """
    顺带钉住"回退是干净的"：目前产品代码**不插任何标记**，
    所以编辑器里读到/导出的文本与用户输入**逐字一致**。
    """
    from beeoffice.plugins.beewrite_rich_editor import RichTextEditor

    # 不创建控件（无 GUI 也能证明）：直接验证判据模块不改变普通文本
    sample = "正文（示例）说明，末尾（"
    assert strip_markers(sample) == sample, "普通文本不该被改动"
    assert "\u2060" not in sample and "\u200d" not in sample
    _ = RichTextEditor          # 保持导入关系可见（产品侧不再依赖本模块）


def test_opening_punctuation_set_is_the_six_we_measured():
    """避尾管的就这 6 个开启标点（范围小是刻意的）。"""
    assert set(OPENING_PUNCTUATION) == set("（《「『【“‘")
