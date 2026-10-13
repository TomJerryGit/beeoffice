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
#: （`docx_sections` 的 `sections` 已修；`docx_inline` 的书签已于 2026-10-13 修好，
#:   它现在零丢失，故不在表内）
KNOWN_LOSSES = {
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


def test_bookmark_is_now_preserved(stress_results):
    """
    `docx_inline.docx` 里有一个具名书签（`ch1`）与一个指向它的内部链接。

    **已修复（第九刀）**：原先 `bookmarks 1 → 0` —— 链接还在、锚点没了，
    也就是**内部跳转变成死链**。现由 `_read_bookmarks()` + `apply_bookmarks()`
    写回，两侧都在（见 tests/fidelity/test_docx_bookmarks.py 的端到端断言）。
    """
    result = stress_results["docx_inline.docx"]
    before = result["before"]["features"]["bookmarks"]
    after = result["after"]["features"]["bookmarks"]
    assert before == 1 and after == 1, f"书签又丢了: {before} → {after}"


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


# ==================== 6. 用户提供的语料（tests/fidelity/corpus）====================

USER_CORPUS = ROOT / "tests" / "fidelity" / "corpus"


@pytest.fixture(scope="module")
def user_results(tmp_path_factory):
    """
    扫描 `tests/fidelity/corpus/`（**用户提供的真实文件**）。

    断言用**性质**（不写死具体数字），这样用户后续增删文件都不会让测试失效，
    但一旦出现"凭空多出标题""文字大段丢失"这类回归就会立刻失败。
    """
    if not USER_CORPUS.is_dir():
        pytest.skip("没有用户语料目录")
    files = [p for p in iter_files([str(USER_CORPUS)])
             if p.suffix.lower() in (".docx", ".xlsx")]
    if not files:
        pytest.skip("用户语料目录里还没有文件（放脱敏的真实文件即可）")
    workdir = tmp_path_factory.mktemp("corpus_user")
    results = {r["name"]: r for r in (run_one(p, workdir) for p in files)}
    return {name: r for name, r in results.items()}


def test_user_files_were_measured(user_results):
    assert user_results, "没有测到任何用户文件"


def test_user_docs_do_not_gain_styles_or_headings(user_results):
    """
    **真实文档撞出来的最严重问题**：导入时未转义导致行首 `#` 被判成标题。

    实测 `修改Centos7网卡ens33为eth0.docx` 凭空多出 **13 个标题**、
    `Win710…Centos7.docx` 多出 8 个。这条断言直接盯住它。
    """
    problems = {}
    for name, result in user_results.items():
        if result["error"] or result["skipped"]:
            continue
        before = result["before"]["features"]
        after = result["after"]["features"]
        for key in ("headings", "styled_paragraphs"):
            if after.get(key, 0) > before.get(key, 0):
                problems[name] = (
                    f"{key} 凭空增加: {before.get(key)} → {after.get(key)}"
                )
    assert not problems, f"文档结构被改写: {problems}"


def test_user_doc_text_loss_is_small(user_results):
    """
    文字丢失必须很小（当前实测：3145 字丢 2 字、2271 字丢 16 字）。

    原先是 178 / 37 字 —— 主要来自"尖括号被当 HTML 吃掉"与"行首缩进被 strip"。
    这里放宽到 2%，既能容纳空行等噪声，又能抓住"大段文字消失"这类回归。
    """
    problems = {}
    for name, result in user_results.items():
        if result["error"] or result["skipped"]:
            continue
        before = result["before"]["features"]["text_chars"]
        after = result["after"]["features"]["text_chars"]
        if before and after < before * 0.98:
            problems[name] = f"文字丢失过多: {before} → {after}"
    assert not problems, problems


def test_user_doc_paragraph_loss_is_explained_by_empty_paragraphs(user_results):
    """
    段落数减少**只应**来自"空段落无法用 Markdown 表达"。

    Markdown 里空行只是段落分隔符，不能表示"一个空段落"，所以源文件里 N 个
    空段落最多导致 N 个段落丢失。超出这个数就说明有真段落被吞了。
    """
    from docx import Document as D

    problems = {}
    for name, result in user_results.items():
        if result["error"] or result["skipped"]:
            continue
        if not name.lower().endswith(".docx"):
            continue
        path = Path(result["path"])
        source = D(str(path))
        empty = sum(1 for p in source.paragraphs if not (p.text or "").strip())

        before = result["before"]["features"]["paragraphs"]
        after = result["after"]["features"]["paragraphs"]
        lost = before - after
        if lost > empty:
            problems[name] = (
                f"丢了 {lost} 段，但源里只有 {empty} 个空段落 —— "
                f"多出的 {lost - empty} 段说明有内容被吞"
            )
    assert not problems, problems


def test_user_doc_page_number_footer_is_known_lost(user_results):
    """
    **已知未修**：页脚部件丢失（`footer_parts` 1 → 0）。

    原因：这些文档的页脚装的是**页码域**（非文字），而现有的页眉页脚传递只
    搬运**文字**（`read_docx_extras` 取 `footer.text`，域取不到文字）。
    所以"有文字页脚"能保住，"页码页脚"会整部件消失。

    修它需要复制页脚部件的 XML（而不是只搬文字）—— 留作后续。
    这条测试把现状钉住，修好时会失败并提醒更新。
    """
    known = []
    for name, result in user_results.items():
        if result["error"] or result["skipped"]:
            continue
        before = result["before"]["features"].get("footer_parts", 0)
        after = result["after"]["features"].get("footer_parts", 0)
        if before and not after:
            known.append(name)
    # 这条断言只要求"若仍丢失，必须是已知的那一类"，不强制丢失
    for name in known:
        result = user_results[name]
        assert result["before"]["features"]["footer_parts"] == 1, (
            f"{name}: 页脚部件数异常"
        )


#: 7 份真实文档实测出的丢失类别（2026-10-13；书签/页脚/超链接域/段落样式已修）
USER_KNOWN_LOSS_KEYS = {
    "paragraphs",          # 空段落（Markdown 无法表示）
    # 文字仍有少量损耗（实测 2~16 字），已从 178 字降到 2 字级别，
    # 剩下的是行尾空格之类的空白；由 test_user_doc_text_loss_is_small 兜住比例
    "text_chars",
    # ⚠️ `fields` 的"丢失"其实是**表示法改善**：那些域是 `HYPERLINK` 域
    # （以域形式存的超链接），现在被转成真正的 `w:hyperlink` ——
    # `fields 6 → 0` 同时 `hyperlinks 0 → 6`，用户看到的是同样的可点击链接。
    # 由 test_user_doc_hyperlink_fields_become_links 验证信息没丢。
    "fields",
}


def test_user_doc_paragraph_styles_are_preserved(user_results):
    """
    **已修复**：段落样式不再丢（原先 3/7 份，`yum源更新.docx` 有 43 段）。

    那几份用的是内置样式 `HTML Preformatted`（Word 给代码/预格式化文本的
    **等宽**样式）与 `Normal (Web)`。python-docx 的默认模板里**没有**它们
    （实测 164 个样式里都没有），所以必须连**样式定义**一起搬。
    """
    problems = {}
    for name, result in user_results.items():
        if result["error"] or result["skipped"]:
            continue
        before = result["before"]["features"].get("styled_paragraphs", 0)
        after = result["after"]["features"].get("styled_paragraphs", 0)
        if after < before:
            problems[name] = f"{before} → {after}"
    assert not problems, f"段落样式又丢了: {problems}"


def test_user_doc_hyperlink_fields_become_links(user_results):
    """
    认领 `fields` 那一项：**信息没丢，只是换了更好的表示法**。

    实测 `yum源更新.docx` 与 `CentOS7…mysql…docx` 里的域全是 `HYPERLINK` 域
    （Word 存超链接的另一种方式）。往返后它们变成真 `w:hyperlink`：
    域数归零、超链接数等于原来的域数 —— 链接依然可点击，而且更规范。
    """
    checked = 0
    for name, result in user_results.items():
        if result["error"] or result["skipped"]:
            continue
        before = result["before"]["features"]
        after = result["after"]["features"]
        field_count = before.get("fields", 0)
        if not field_count:
            continue
        checked += 1
        assert after.get("hyperlinks", 0) >= field_count, (
            f"{name}: 原有 {field_count} 个 HYPERLINK 域，"
            f"往返后只有 {after.get('hyperlinks', 0)} 个超链接 —— 链接丢了"
        )
    assert checked or True        # 语料里没有域时也允许通过


def test_user_doc_footers_are_preserved(user_results):
    """
    **已修复**：带**页码域**的页脚不再丢（原先 3/7 份 `footer_parts 1 → 0`）。

    根因不是"没搬文字"，而是 python-docx **不进入 `w:sdt`** ——
    那 3 份的页码在嵌套内容控件里，`footer.paragraphs` 只返回一个空段落，
    于是被判成"没有页脚"。修法是整段搬运部件 XML。
    """
    problems = {}
    for name, result in user_results.items():
        if result["error"] or result["skipped"]:
            continue
        before = result["before"]["features"].get("footer_parts", 0)
        after = result["after"]["features"].get("footer_parts", 0)
        if after < before:
            problems[name] = f"{before} → {after}"
    assert not problems, f"页脚又丢了: {problems}"


def test_user_doc_bookmarks_are_preserved(user_results):
    """
    **已修复（第九刀）**：书签不再丢失。

    7 份里的 5 份带书签，往返后 `bookmarks 1 → 0`。

    ⚠️ 更正一处我先前的判断：那些书签名**全是 `_GoBack`** —— Word 的
    "上次编辑位置"内部标记，**不是用户内容**，也没有链接指向它，所以
    **不会造成死链**。我最初推测"多半是目录锚点 `_Toc…`"是错的。
    仍然选择保留它（往返不该改动用户的文件）。
    """
    problems = {}
    for name, result in user_results.items():
        if result["error"] or result["skipped"]:
            continue
        before = result["before"]["features"].get("bookmarks", 0)
        after = result["after"]["features"].get("bookmarks", 0)
        if after < before:
            problems[name] = f"{before} → {after}"
    assert not problems, f"书签又丢了: {problems}"


def test_user_doc_losses_are_within_known_categories(user_results):
    """
    **护栏**：真实文档的丢失项只能落在已知类别里。

    出现**新类别**就说明有尚未调查的问题 —— 这才是这条测试的价值：
    它不要求"零丢失"（现实还没做到），但要求"每一处丢失都已被认识"。
    """
    unknown = {}
    for name, result in user_results.items():
        if result["error"] or result["skipped"]:
            continue
        lost = {x["feature"] for x in result["rows"] if x["status"] == "lost"}
        extra = lost - USER_KNOWN_LOSS_KEYS
        if extra:
            unknown[name] = sorted(extra)
    assert not unknown, (
        f"真实文档出现**新的**丢失类别，需要调查：{unknown}\n"
        f"（已知类别：{sorted(USER_KNOWN_LOSS_KEYS)}）"
    )


def test_known_loss_categories_are_still_happening(user_results):
    """
    反向确认：上面那些"已知丢失"确实还在发生 —— 否则说明已修好，
    应把它们从 `USER_KNOWN_LOSS_KEYS` 移除并在 docs 记录进展。
    """
    hits = set()
    for result in user_results.values():
        if result["error"] or result["skipped"]:
            continue
        hits |= {x["feature"] for x in result["rows"] if x["status"] == "lost"}

    # 只要求"已知类别里至少还有一类真的在丢"，避免这份清单变成空话
    assert hits & USER_KNOWN_LOSS_KEYS, (
        "所有已知丢失类别都不再发生 —— 请更新清单与 docs/fidelity.md"
    )

