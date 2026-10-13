# tests/fidelity/test_ooxml_probe.py
"""
保真度测试集的**仪器自检** + 当前状态的**特性化测试**（阶段 A）

两层含义，别混在一起读
----------------------
1. `TestInstrument*`：验证**测量仪器本身**是可信的 —— 它能数对特征、
   能检出差异。否则下面那堆数字可能全是常数（"恒真"是本项目踩过的坑）。
2. `TestCurrentFidelity*`：**特性化测试**，钉住 **2026-10-11 实测的当前状态**。

⚠️ 第二类是"记录现状"，不是"需求"。它们故意把"丢东西"写进断言：
   - 若哪天丢了**更多** → 测试失败，这是回归，应当修代码
   - 若哪天**改善**了 → 测试也会失败，此时请**更新这些数字**并在
     `docs/fidelity.md` 里记录进展

往返定义见 `tools/fidelity_roundtrip.py`；所有往返都调用**产品代码**。
"""
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.fidelity_roundtrip import (      # noqa: E402
    build_docx_fixture,
    build_pptx_fixture,
    build_xlsx_fixture,
    measure,
    roundtrip_docx,
    roundtrip_xlsx,
)
from tools.ooxml_probe import compare, probe   # noqa: E402


# ==================== 1. 仪器可信度 ====================

class TestInstrument:
    def test_probe_counts_docx_features(self, tmp_path):
        """探针在**已知构造**的文件上必须数对。"""
        src = tmp_path / "fixture.docx"
        build_docx_fixture(src)

        info = probe(src)

        f = info["features"]
        assert f["headings"] == 2, f"应识别 2 个标题，实际 {f['headings']}"
        assert f["tables"] == 1
        assert f["merged_cells"] >= 1, "构造里有一个合并单元格"
        assert f["images"] == 1
        assert f["hyperlinks"] == 1
        assert f["header_parts"] == 1, "应存在页眉部件"
        assert f["footer_parts"] == 1, "应存在页脚部件"
        assert f["text_chars"] > 30, "应数出中文正文"

    def test_probe_counts_xlsx_features(self, tmp_path):
        src = tmp_path / "fixture.xlsx"
        build_xlsx_fixture(src)

        f = probe(src)["features"]

        assert f["sheets"] == 2
        assert f["formulas"] >= 3
        assert f["merged_ranges"] == 1
        assert f["conditional_formatting"] == 1
        assert f["freeze_panes"] == 1
        assert f["charts"] == 1

    def test_probe_counts_pptx_features(self, tmp_path):
        src = tmp_path / "fixture.pptx"
        build_pptx_fixture(src)

        f = probe(src)["features"]

        assert f["slides"] == 2
        assert f["pictures"] == 1
        assert f["tables"] == 1
        assert f["notes_slides"] == 1

    def test_compare_is_not_vacuous(self, tmp_path):
        """
        **关键**：仪器要能检出"丢失"。用一个故意做了删减的文件对比，
        必须报出 lost —— 否则整份报告可能是常数值。
        """
        from docx import Document

        rich = tmp_path / "rich.docx"
        build_docx_fixture(rich)

        plain = tmp_path / "plain.docx"
        doc = Document()
        doc.add_paragraph("只有一个段落")
        doc.save(str(plain))

        rows = compare(probe(rich), probe(plain))
        statuses = {r["feature"]: r["status"] for r in rows}

        assert statuses["tables"] == "lost"
        assert statuses["images"] == "lost"
        assert statuses["hyperlinks"] == "lost"
        assert statuses["header_parts"] == "lost"

    def test_compare_identical_files_reports_no_change(self, tmp_path):
        """同一份文件与自己比，不应报任何差异（避免噪声）。"""
        import shutil

        src = tmp_path / "fixture.xlsx"
        build_xlsx_fixture(src)
        copy = tmp_path / "copy.xlsx"
        shutil.copy(src, copy)

        rows = compare(probe(src), probe(copy))
        changed = [r for r in rows if r["status"] != "same"]
        assert not changed, f"同一文件不应有差异: {changed}"

    def test_probe_rejects_unknown_format(self, tmp_path):
        bogus = tmp_path / "x.txt"
        bogus.write_text("not ooxml", encoding="utf-8")
        with pytest.raises(ValueError):
            probe(bogus)


# ==================== 2. 当前状态（特性化） ====================

@pytest.fixture(scope="module")
def docx_result(tmp_path_factory):
    workdir = tmp_path_factory.mktemp("fid_docx")
    return measure("docx", build_docx_fixture, roundtrip_docx, workdir)


@pytest.fixture(scope="module")
def xlsx_result(tmp_path_factory):
    workdir = tmp_path_factory.mktemp("fid_xlsx")
    return measure("xlsx", build_xlsx_fixture, roundtrip_xlsx, workdir)


class TestCurrentFidelityDOCX:
    """DOCX 往返现状（2026-10-11 实测）。"""

    def test_roundtrip_runs(self, docx_result):
        assert docx_result["error"] is None, docx_result["error"]
        assert docx_result["roundtrip"]["ok"] is True
        assert docx_result["after"] is not None

    @pytest.mark.parametrize("feature,expected_after", [
        # 特性化：这些**当前**在往返中丢失（值 = 往返后的实测数量）
        ("merged_cells", 0),
        ("hyperlinks", 0),
        ("header_parts", 0),
        ("footer_parts", 0),
        ("tables", 1),
        ("images", 1),
    ])
    def test_feature_after_roundtrip(self, docx_result, feature,
                                     expected_after):
        before = docx_result["before"]["features"][feature]
        after = docx_result["after"]["features"][feature]
        assert after == expected_after, (
            f"{feature}: 往返前 {before} → 往返后 {after}，"
            f"实测基线是 {expected_after}。"
            f"若这是**改善**，请更新本测试与 docs/fidelity.md；"
            f"若是**回归**，请修代码。"
        )

    def test_text_is_partially_lost(self, docx_result):
        """正文文字有损失（14 段 → 13 段、102 字 → 90 字）。"""
        before = docx_result["before"]["features"]
        after = docx_result["after"]["features"]
        assert after["text_chars"] < before["text_chars"], (
            "实测往返后文字变少；若已修好，请更新基线"
        )
        assert after["text_chars"] == 90, after["text_chars"]

    def test_page_margins_do_not_survive(self, docx_result):
        """
        页边距变成 python-docx 默认值。

        原因：`import_from_docx()` 的返回值是 **Markdown 字符串** ——
        Markdown 表达不了页面设置，所以往返后这些信息必然丢失。
        """
        before = docx_result["before"]["features"]["page_margins"]
        after = docx_result["after"]["features"]["page_margins"]
        assert before != after, "若页边距已能保留，请更新基线"
        assert after.startswith("1440,"), (
            f"往返后应是默认 1 英寸（1440 twips），实际 {after}"
        )


class TestCurrentFidelityXLSX:
    """
    XLSX 往返现状。

    2026-10-11 更新：引入 `beesheet_workbook`（工作簿对象）后，
    **`sheets` 与 `formulas` 不再丢失**（原先 9 项丢 8 项 → 现在丢 6 项）。
    这组断言随之更新 —— 这正是特性化测试的预期用途。
    """

    def test_roundtrip_runs(self, xlsx_result):
        assert xlsx_result["error"] is None, xlsx_result["error"]
        assert xlsx_result["after"] is not None

    # ---- 已修复：不再丢失 ----

    def test_all_sheets_are_preserved(self, xlsx_result):
        """**已修复**：原先第 2 张工作表直接消失（read_excel 只读首张）。"""
        before = xlsx_result["before"]["features"]["sheets"]
        after = xlsx_result["after"]["features"]["sheets"]
        assert before == 2, before
        assert after == before, f"工作表又丢了: {before} → {after}"

    def test_formulas_are_preserved(self, xlsx_result):
        """**已修复**：原先公式全丢（写的是 pandas 的计算值）。"""
        before = xlsx_result["before"]["features"]["formulas"]
        after = xlsx_result["after"]["features"]["formulas"]
        assert before > 0, "前置条件：构造文件里应有公式"
        assert after == before, f"公式又丢了: {before} → {after}"

    def test_cell_values_are_preserved(self, xlsx_result):
        """**已修复**：非空单元格数不再减少。"""
        before = xlsx_result["before"]["features"]["nonempty_cells"]
        after = xlsx_result["after"]["features"]["nonempty_cells"]
        assert after >= before, f"单元格丢多了: {before} → {after}"

    # ---- 仍丢失：留给后续切片 ----

    @pytest.mark.parametrize("feature", [
        "merged_ranges", "conditional_formatting", "data_validations",
        "freeze_panes", "charts",
    ])
    def test_feature_still_lost(self, xlsx_result, feature):
        """
        特性化：这些当前**仍然**丢失。

        根因同一条 —— 它们都不是 DataFrame 能承载的东西，
        `write_workbook` 目前也只写值（不复制样式/合并/条件格式）。
        """
        before = xlsx_result["before"]["features"][feature]
        after = xlsx_result["after"]["features"][feature]
        assert before > 0, f"前置条件：构造文件里应有 {feature}"
        assert after == 0, (
            f"{feature}: {before} → {after}。"
            f"若已改善，请更新本测试与 docs/fidelity.md"
        )

    def test_custom_number_formats_are_lost(self, xlsx_result):
        """
        数字格式仍丢：`write_workbook` 只写值，用新工作簿起步，
        源文件里自定义的 `number_format`（体现在 cellXfs 数量上）不会带过去。
        """
        after = xlsx_result["after"]["features"]["cell_xfs"]
        assert after < 2, (
            f"cellXfs={after}；若数字格式已能保留，请更新基线"
        )


class TestCurrentFidelityPPTX:
    """PPTX 没有导入路径，因此不存在"往返"可测。"""

    def test_pptx_has_no_import_path(self, tmp_path):
        from beeoffice.plugins import bee_export

        assert not hasattr(bee_export, "import_from_pptx"), (
            "若实现了 PPTX 导入，请把本测试改成往返测量"
        )

    def test_pptx_roundtrip_is_skipped_with_reason(self, tmp_path):
        result = measure("pptx", build_pptx_fixture, None, tmp_path)

        assert result["roundtrip"]["skipped"] is True
        assert "无此格式的导入路径" in result["roundtrip"]["reason"]
        # 但仍然要能探测出内容特征（为将来做导入时的对照基线）
        assert result["before"]["features"]["slides"] == 2
