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
    """
    DOCX 往返现状。

    2026-10-11 更新（两次）：
    1. 修复 `_para_to_md()` 漏掉超链接后，**`hyperlinks` 不再丢失**，
       链接文字也不再消失（原先"文字少 12 字"正是漏掉的链接文字）。
    2. 页面设置与页眉页脚改走 `read_docx_extras()` **绕开 Markdown** 传递，
       因此 `header_parts` / `footer_parts` / `page_margins` **全部保住**。

    仍丢失：**合并单元格**（Markdown 表格语法表达不了合并；它同时导致
    `table_cells` 变多、`text_chars` 略增）与**段落少 1 段**（空段落）。
    """

    def test_roundtrip_runs(self, docx_result):
        assert docx_result["error"] is None, docx_result["error"]
        assert docx_result["roundtrip"]["ok"] is True
        assert docx_result["after"] is not None

    # ---- 已修复：不再丢失 ----

    def test_hyperlinks_are_preserved(self, docx_result):
        """**已修复**：原先 `hyperlinks 1 → 0`（`para.runs` 漏掉 `w:hyperlink`）。"""
        before = docx_result["before"]["features"]["hyperlinks"]
        after = docx_result["after"]["features"]["hyperlinks"]
        assert before == 1, before
        assert after == before, f"超链接又丢了: {before} → {after}"

    def test_text_is_no_longer_lost(self, docx_result):
        """
        **已修复**：原先文字少 12 字（正是超链接文字）。

        现在不再减少（实测略增，因为表格合并单元格被拆开后文字重复出现）。
        """
        before = docx_result["before"]["features"]["text_chars"]
        after = docx_result["after"]["features"]["text_chars"]
        assert after >= before, (
            f"文字又丢了: {before} → {after}。"
            f"若这是回归，请检查 _para_to_md 是否还在遍历 w:hyperlink"
        )

    # ---- 仍丢失：留给后续切片 ----

    @pytest.mark.parametrize("feature,expected_after", [
        ("merged_cells", 0),
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

    # ---- 已修复（第三刀）：页面设置与页眉页脚 ----

    def test_header_and_footer_parts_are_preserved(self, docx_result):
        """
        **已修复**：原先 `header_parts` / `footer_parts` 直接归零
        （部件根本不存在）。现由 `read_docx_extras()` 另读一份、导出时写回。
        """
        for key in ("header_parts", "footer_parts"):
            before = docx_result["before"]["features"][key]
            after = docx_result["after"]["features"][key]
            assert before == 1, f"前置条件：构造文件里应有 {key}"
            assert after == before, f"{key} 又丢了: {before} → {after}"

    def test_page_margins_are_preserved(self, docx_result):
        """
        **已修复**：原先变成 python-docx 默认 1 英寸
        （1417,1701,1417,1701 → 1440,1800,1440,1800）。
        """
        before = docx_result["before"]["features"]["page_margins"]
        after = docx_result["after"]["features"]["page_margins"]
        assert before == after, f"页边距又变了: {before} → {after}"


class TestCurrentFidelityXLSX:
    """
    XLSX 往返现状。

    2026-10-11 第二次更新：`write_workbook()` 改为
    **"打开源工作簿、只更新单元格值"** 后，**全部 11 项特征零差异** ——
    合并区域、条件格式、数据验证、冻结窗格、图表、自定义数字格式都不再丢失。

    演进轨迹（同一把尺子测量）：
        建立基线          9 项丢 8 项
        + 多表与公式      9 项丢 5 项
        + 只改值保结构    9 项丢 0 项  ← 现在
    """

    def test_roundtrip_runs(self, xlsx_result):
        assert xlsx_result["error"] is None, xlsx_result["error"]
        assert xlsx_result["after"] is not None

    def test_no_feature_is_lost(self, xlsx_result):
        """**核心断言**：往返后不应有任何特征减少。"""
        rows = compare(xlsx_result["before"], xlsx_result["after"])
        lost = [r for r in rows if r["status"] == "lost"]
        assert not lost, (
            "xlsx 往返出现丢失（应已全部保留）：\n"
            + "\n".join(
                f"  {r['feature']}: {r['before']} → {r['after']}"
                for r in lost
            )
        )

    def test_all_sheets_are_preserved(self, xlsx_result):
        before = xlsx_result["before"]["features"]["sheets"]
        after = xlsx_result["after"]["features"]["sheets"]
        assert before == 2 and after == before, f"{before} → {after}"

    def test_formulas_are_preserved(self, xlsx_result):
        before = xlsx_result["before"]["features"]["formulas"]
        after = xlsx_result["after"]["features"]["formulas"]
        assert before > 0, "前置条件：构造文件里应有公式"
        assert after == before, f"公式又丢了: {before} → {after}"

    @pytest.mark.parametrize("feature", [
        "merged_ranges", "conditional_formatting", "data_validations",
        "freeze_panes", "charts", "cell_xfs",
    ])
    def test_non_data_features_are_preserved(self, xlsx_result, feature):
        """
        特性化 + 回归：这些非数据属性曾经全丢，现在必须原样保留。

        （`cell_xfs` 是自定义数字格式的体现。）
        """
        before = xlsx_result["before"]["features"][feature]
        after = xlsx_result["after"]["features"][feature]
        assert before > 0, f"前置条件：构造文件里应有 {feature}"
        assert after == before, (
            f"{feature}: {before} → {after}。"
            f"若这是回归，请检查 write_workbook 是否还在"
            f"'打开源工作簿只更新值'的模式下工作"
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
