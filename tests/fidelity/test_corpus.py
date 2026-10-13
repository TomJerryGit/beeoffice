# tests/fidelity/test_corpus.py
"""
保真度 **corpus 测试**（阶段 A）

两层语料
--------
1. **真实文件**：`test+files/` 里已有的真实 Word/Excel 样例（仓库自带）。
   这是唯一能检验"零丢失"是否成立于真实世界的材料。
2. **压力语料**：`tools/fidelity_corpus_gen.py` 生成的、每个文件专攻一个维度的
   文件（多分节、列表、嵌套表格、书签、页眉表格、宽表、高表……）。

为什么要这个文件
----------------
`tests/fidelity/test_ooxml_probe.py` 只用了**一个**合成夹具，覆盖面很窄。
本文件把**真实文件 + 压力语料**一起跑往返，暴露合成夹具覆盖不到的构造。

第一次运行就撞出了 3 类新丢失（见下面 `KNOWN_LOSSES`），这正是它的价值。
"""
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.fidelity_corpus import iter_files, run_one   # noqa: E402
from tools.fidelity_corpus_gen import generate_all      # noqa: E402

REAL_DIR = ROOT / "test+files"


@pytest.fixture(scope="module")
def stress_results(tmp_path_factory):
    """生成压力语料并逐个往返（模块级：只跑一次）。"""
    workdir = tmp_path_factory.mktemp("corpus_gen")
    corpus = tmp_path_factory.mktemp("corpus")
    generate_all(corpus)
    return {r["name"]: r for r in (
        run_one(p, workdir) for p in iter_files([str(corpus)])
    )}


def _lost(result):
    return {r["feature"] for r in result["rows"] if r["status"] == "lost"}


# ==================== 1. 压力语料：不该有异常 ====================

def test_no_corpus_file_errors(stress_results):
    broken = {
        name: r["error"] for name, r in stress_results.items() if r["error"]
    }
    assert not broken, f"这些文件往返时异常: {broken}"


def test_all_expected_files_were_measured(stress_results):
    assert len(stress_results) == 9, sorted(stress_results)


# ==================== 2. 干净的文件必须保持干净 ====================

@pytest.mark.parametrize("name", [
    "docx_lists.docx",      # 项目符号 / 编号列表
    "docx_headers.docx",    # 页眉含表格 + 非标准纸张
    "xlsx_wide.xlsx",       # 200 列 × 50 行
    "xlsx_tall.xlsx",       # 5000 行
])
def test_clean_corpus_file_has_no_loss(stress_results, name):
    """这些维度已经能完整往返；一旦退化就说明有回归。"""
    result = stress_results[name]
    assert not _lost(result), (
        f"{name} 出现丢失: "
        + str([r for r in result["rows"] if r["status"] == "lost"])
    )


# ==================== 3. 已撞出的丢失：特性化钉住 ====================

#: 2026-10-11 由压力语料撞出的丢失 → 每一类都是下一刀的方向
#: （`docx_sections` 的 `sections` 已在"第七刀：多分节"修好，故只剩 `paragraphs`）
KNOWN_LOSSES = {
    "docx_inline.docx": {"bookmarks"},
    "docx_sections.docx": {"paragraphs"},
    "docx_tables.docx": {"tables", "text_chars"},
}


@pytest.mark.parametrize("name", sorted(KNOWN_LOSSES))
def test_known_losses_are_recorded(stress_results, name):
    """
    特性化：这些丢失是**已知**的，不是回归。

    若哪天真修好了，本测试会失败 —— 那时请把该项从 `KNOWN_LOSSES` 移出，
    并在 docs/fidelity.md 记录进展（这是有意设计的提示）。
    """
    result = stress_results[name]
    lost = _lost(result)
    expected = KNOWN_LOSSES[name]

    assert lost == expected, (
        f"{name} 的丢失集合变了：\n"
        f"  实际: {sorted(lost)}\n  预期: {sorted(expected)}\n"
        f"细节: {[r for r in result['rows'] if r['status'] == 'lost']}"
    )


def test_nested_table_is_lost(stress_results):
    """
    `docx_tables.docx` 里有 4 个表（含一个**嵌套表格**），往返后只剩 3 个。

    嵌套表格（单元格里再放一个表）在 Markdown 里没有对应表达，因此整块消失。
    """
    result = stress_results["docx_tables.docx"]
    before = result["before"]["features"]["tables"]
    after = result["after"]["features"]["tables"]
    assert before == 4 and after == 3, f"{before} → {after}"


def test_sections_are_now_preserved(stress_results):
    """
    `docx_sections.docx` 有 2 个分节（第二节横向）。

    **已修复**（第七刀）：原先 `sections 2 → 1`，后果是横向页变成纵向、
    页边距随第一节。现由 `_read_sections()` + `apply_sections()` 重建。

    仍剩 `paragraphs` 5 → 4：承载 `sectPr` 的那个**空段落**在 Markdown 里
    没有对应表达（空行不等于空段落），属已知项。
    """
    result = stress_results["docx_sections.docx"]
    before = result["before"]["features"]
    after = result["after"]["features"]
    assert before["sections"] == 2 and after["sections"] == 2, (
        f"分节又丢了: {before['sections']} → {after['sections']}"
    )


def test_bookmark_is_lost(stress_results):
    """
    `docx_inline.docx` 的书签丢失 → **内部跳转链接会变成死链**。

    注意超链接本身是保住的（上一刀修的），但指向书签的 `#ch1` 没有目标了。
    """
    result = stress_results["docx_inline.docx"]
    assert result["before"]["features"]["bookmarks"] == 1
    assert result["after"]["features"]["bookmarks"] == 0


# ==================== 4. 非矩形工作表会被规范化（行为记录，非丢失） ====================

def test_irregular_sheet_is_rectangularised(stress_results):
    """
    `xlsx_rich.xlsx` 的"说明"表首行只有 1 格、次行有 3 格 —— **非矩形**。

    pandas 读成矩形 DataFrame 后写回，非空单元格 25 → 27（+2）。
    这是"用 pandas 读写表格"的固有行为，不是丢失；记录以免被当成 bug。
    """
    result = stress_results["xlsx_rich.xlsx"]
    before = result["before"]["features"]
    after = result["after"]["features"]

    assert not _lost(result), "不应有丢失"
    assert before["sheets"] == after["sheets"] == 3
    assert before["formulas"] == after["formulas"] == 4
    assert before["merged_ranges"] == after["merged_ranges"] == 1
    assert after["nonempty_cells"] >= before["nonempty_cells"], (
        f"非空单元格不该变少: {before['nonempty_cells']} → "
        f"{after['nonempty_cells']}"
    )


# ==================== 5. 真实文件（仓库自带）====================

@pytest.fixture(scope="module")
def real_results(tmp_path_factory):
    if not REAL_DIR.is_dir():
        pytest.skip(f"没有真实语料目录: {REAL_DIR}")
    files = iter_files([str(REAL_DIR)])
    if not files:
        pytest.skip("真实语料目录里没有 OOXML 文件")
    workdir = tmp_path_factory.mktemp("corpus_real")
    return {r["name"]: r for r in (run_one(p, workdir) for p in files)}


def test_real_files_have_no_loss(real_results):
    """
    `test+files/` 里的真实文件必须**零丢失**。

    这是对"零丢失"结论的唯一真实世界检验：它们包含大量空段落、多个表格、
    图片、编号与标题样式，都不是我造的。
    """
    problems = {}
    for name, result in real_results.items():
        if result["error"]:
            problems[name] = result["error"]
        elif result["skipped"]:
            continue
        else:
            lost = [r for r in result["rows"] if r["status"] == "lost"]
            if lost:
                problems[name] = lost
    assert not problems, f"真实文件出现丢失/异常: {problems}"
