# tools/check_gates.py
"""
**回归门禁**：把本项目的关键修复固化成可执行检查，防止后续改动悄悄退回去。

## 为什么需要它
本项目每一轮修复背后都有一次**真实踩坑**（O(N²) 状态栏统计、公式扫描逐格遍历、
静默插模板句、撤销删正文、惰性载入写坏文件…）。只写在文档里不够 ——
下一轮改代码的人（包括未来的我）不会每次都读文档。

## 两类门禁（这是本文件的核心设计）
* **确定性门禁（blocking）**：断言"调用次数 / 结构 / 文件内容"这类**与机器负载无关**的
  事实。例如"批量加载期间 `to_markdown()` 调用次数必须为 0"。
  → CI 里**失败即红**。
* **计时门禁（timing）**：断言绝对耗时。**天然受机器负载影响**
  （本项目已两次被污染的机器骗过：xlsx 预检 2817ms 测成 5199ms；
  R1/R3 并行时重绘 19ms 测成 108ms）。
  → **默认只报告不阻断**；要用它卡住回归请加 `--strict-timing`（在空载机器上跑）。

## 用法
    python tools/check_gates.py                  # 全部；计时门禁只报告
    python tools/check_gates.py --strict-timing  # 计时门禁也阻断（需空载）
    python tools/check_gates.py --only docx-open-on2,xlsx-formula-precheck
    python tools/check_gates.py --list           # 只看门禁清单
"""
import argparse
import shlex
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class Gate:
    def __init__(self, gid, title, target, guards, timing=False, kind="pytest"):
        self.gid = gid
        self.title = title
        self.target = target          # pytest 路径/节点，或 ruff 参数
        self.guards = guards          # 它守的是哪次踩坑
        self.timing = timing
        self.kind = kind


GATES = [
    Gate(
        "docx-open-on2",
        "DOCX 打开不再 O(N²)",
        "tests/fidelity/test_beewrite_open_hotpath.py",
        "曾经：状态栏统计每插一块就 to_markdown 整篇（1032 次 / 6.2s）→ 打开 17.7s",
    ),
    Gate(
        "xlsx-formula-precheck",
        "公式扫描不做逐格遍历",
        "tests/fidelity/test_beesheet_formula_precheck.py",
        "曾经：无公式的表也逐格扫（2635ms）；且预检失败必须退回全表扫描",
    ),
    Gate(
        "sheet-lazy-safety",
        "惰性载入不得写坏文件",
        "tests/fidelity/test_beesheet_lazy_load.py tests/fidelity/test_beesheet_lazy_view.py",
        "曾经：部分载入后排序/保存 → 前 N 行覆盖、其余留旧值（文件与界面不一致）",
    ),
    Gate(
        "sheet-hotpath-deterministic",
        "蜜算热路径的确定性不变量",
        "tests/fidelity/test_beesheet_hotpath.py -k 'fresh or aligned or flags_editable or placeholder or empty_cell or font_role or replaced or dropped'",
        "曾经：就地修改后取值不刷新、对齐错、越界行显示异常",
    ),
    Gate(
        "sheet-timing",
        "蜜算绘制/取值耗时",
        "tests/fidelity/test_beesheet_hotpath.py -k 'call_is_cheap or repaint_budget'",
        "曾经：整视口重绘 337ms/帧（≈3fps）→ 23.6ms。**计时项，受负载影响**",
        timing=True,
    ),
    Gate(
        "fidelity-corpus",
        "真实文档往返零丢失",
        "tests/fidelity/test_corpus.py",
        "曾经：7 份真实文档撞出最严重的一类 bug（导入未转义）",
    ),
    Gate(
        "fidelity-report-honesty",
        "损失提示不误报、措辞与事实一致",
        "tests/fidelity/test_fidelity_report.py",
        "曾经：按'脚注部件存在'判定 → 3/7 份零丢失的真实文档被误报",
    ),
    Gate(
        "nested-tables",
        "嵌套表格往返保真（R4）",
        "tests/fidelity/test_docx_nested_tables.py",
        "曾经：内层表格整块丢失（w:tbl 2→1）",
    ),
    Gate(
        "media-fallback-failfast",
        "图片目录全不可写时快速失败（R7）",
        "tests/fidelity/test_r7_media_fallback.py",
        "曾经：兜底返回一个不可写目录 → 每张图各失败一次（23 张图 23 次异常）",
    ),
    Gate(
        "backup-restore",
        "备份：覆盖前留档、恢复可回退、轮转不删光（R6）",
        "tests/fidelity/test_backup.py",
        "曾经：只有自动保存（直接覆盖）→ 用户看不到历史、写坏就没救",
    ),
    Gate(
        "sheet-ai",
        "蜜算 AI：不给整表、本地兜底要标注、不静默糊弄（R5）",
        "tests/fidelity/test_beesheet_ai.py",
        "曾经：蜜算 0 处 AI；且上下文漏列字母会让模型给出错公式（实测 A2*B2）",
    ),
    Gate(
        "print-fit-modes",
        "打印缩放：列不越界、等比缩放、横向分页（R8）",
        "tests/fidelity/test_beesheet_print_fit.py",
        "曾经：只有'压列宽'（把文字挤坏）且无'缩放到一页'；横向分页会切错单元格",
    ),
    Gate(
        "loss-locations",
        "损失提示要能说出'哪一处'（R9）",
        "tests/fidelity/test_r9_loss_locations.py",
        "曾经：只说'脚注 2 处'，用户不知道去哪找、也没法判断该不该处理",
    ),
    Gate(
        "r2-kinsoku-canary",
        "R2 避尾：Qt 不认禁断标记（金丝雀，Qt 变了会失败）",
        "tests/fidelity/test_r2_kinsoku_limitation.py",
        "曾经：spike 推断'插 U+2060 即可'，实测 5 种标记全部无效；判据漏剥标记还会给出假的 0",
    ),
    Gate(
        "p0-shortcuts",
        "P0：Ctrl+S/Ctrl+Z 不再因同键歧义失效（唯一来源）",
        "tests/fidelity/test_p0_shortcut_fixes.py",
        "曾经：菜单 QAction 与模块 QShortcut 同键 → Qt 判歧义 → 两个都不触发（保存/撤销完全失效）",
    ),
    Gate(
        "p0-unsaved-prompt",
        "P0：蜜算/蜜演关标签会提示未保存",
        "tests/fidelity/test_p0_unsaved_prompt.py",
        "曾经：两个视图没有 content() → initial_content 记为 None → 关标签静默丢弃内容",
    ),
    Gate(
        "p0-pdf-export",
        "P0：导出 PDF 走 Qt 路径并三模块分流（真的产出 PDF）",
        "tests/fidelity/test_p0_pdf_export.py",
        "曾经：依赖未打包的 WeasyPrint → 蜜写必失败、蜜算/蜜演弹'不支持'",
    ),
    Gate(
        "save-coverage",
        "蜜算/蜜演都有当前文件与保存（备份/自动保存才覆盖得到）",
        "tests/fidelity/test_p1_save_coverage.py",
        "曾经：蜜演整条保存链路不存在（Ctrl+S 无反应、稿子关掉就丢）；蜜算从不记路径",
    ),
    Gate(
        "xls-undo-sync",
        "蜜算 .xls 真支持 / 行列操作可撤销 / 云同步双向",
        "tests/fidelity/test_p1_xls_undo_sync.py",
        "曾经：.xls 假装支持、插入删除行列不进撤销栈、云同步上传一个永远为空的目录",
    ),
    Gate(
        "format-persistence",
        "蜜算格式落盘并读回（且写格式不得丢数据）",
        "tests/fidelity/test_p1_format_persistence.py",
        "曾经：加粗/数字格式/合并/批注/条件格式保存后全部消失；合并还会被静默吃掉数据",
    ),
    Gate(
        "table-style-validations",
        "蜜算表格样式与数据验证落盘并读回（下拉框仍生效）",
        "tests/fidelity/test_p1_table_style_validations.py",
        "曾经：表格样式与下拉验证只在内存里；且 ws[区域] 返回 Cell 会让验证静默读不回",
    ),
    Gate(
        "freeze-chart-names-author",
        "蜜算冻结窗格/图表/命名区域/批注作者落盘（且不覆盖原作者）",
        "tests/fidelity/test_p1_freeze_chart_names_author.py",
        "曾经：图表从未进过 xlsx；作者被硬编码成 BeeOffice 会覆盖原作者；命名区域行号错位",
    ),
    Gate(
        "pivot-persistence",
        "数据透视表落盘且可刷新（行标签不得丢失）",
        "tests/fidelity/test_p1_pivot_persistence.py",
        "曾经：透视配置当场丢弃、关掉即无法重算；单行字段时行标签被整个丢掉",
    ),
    Gate(
        "write-gaps",
        "条件格式读回；蜜写 markdown 格式化/分节符/导出 Word 一致性/全部替换",
        "tests/fidelity/test_p1_write_gaps.py",
        "曾经：markdown 下 Ctrl+B 毫无反应；分节符插入可见装饰文字污染导出；导出 Word 与另存为保真度不同；全部替换会抛异常",
    ),
    Gate(
        "polish-gaps",
        "图表取消不画图/缺库有提示；目录插渲染结果而非 Markdown 源码",
        "tests/fidelity/test_p1_polish_gaps.py",
        "曾经：取消图表对话框仍画柱状图；缺 matplotlib 静默无反应；目录在所见即所得里是字面源码",
    ),
    Gate(
        "beewrite-remnants",
        "蜜写余项：表格列对齐往返 / DOCX 超链接与单元格多段落 / 嵌套列表缩进",
        "tests/fidelity/test_p1_beewrite_remnants.py",
        "曾经：表格编辑抹掉列对齐；DOCX 丢链接 URL 且单元格只导出首段；多级列表被压平",
    ),
    Gate(
        "lint-clean",
        "全仓无未用导入（F401）且无空类型检查块（TC005）",
        "tests/fidelity/test_lint_clean.py",
        "曾经：全仓 196 处未用导入；--fix 还会删掉刻意导入并留下空块",
    ),
    Gate(
        "packaging",
        "打包链：数据文件进包且冻结路径解析正确；发布脚本路径正确",
        "tests/fidelity/test_packaging.py",
        "曾经：spec 漏打包 beeoffice/data（打包版拼写白名单失效）；build_release.py 一跑就报未找到 spec",
    ),
    Gate(
        "ai-error-messages",
        "AI 报错归因正确（404 看响应体：模型不存在 ≠ 地址不对）",
        "tests/fidelity/test_ai_error_messages.py",
        "曾经：Ollama 说模型不存在(404) 被误报成『接口地址不对』，把用户引向改地址",
    ),
    Gate(
        "ai-local-models",
        "AI 设置自动列出本机已装模型（不再推荐没装的模型）",
        "tests/fidelity/test_ai_local_models.py",
        "曾经：预设写死 qwen2.5/llama3.1/gemma2，用户机器上通常一个都没装 → 一测就 404",
    ),
    Gate(
        "beecmd",
        "无界面 CLI：表格互转零差异、verify 报差异、batch 审计、零 Qt 约束",
        "tests/fidelity/test_beecmd.py",
        "曾经：所有能力绑在 GUI 上，无法被脚本/服务调用（战略缺口 §5.2）",
    ),
    Gate(
        "pptx-import",
        "打开 .pptx：文字/层级/备注保留，图片表格给损失清单，绝不覆盖原 pptx",
        "tests/fidelity/test_pptx_import.py",
        "曾经：蜜演只能开 .beshow，别人发来的 .pptx 直接打不开（P0-1 门槛项）",
    ),
    Gate(
        "print-invariant",
        "打印：排版计划 == 实际页数",
        "tests/fidelity/test_beesheet_print.py tests/fidelity/test_beeshow_print.py",
        "曾经：蜜算/蜜演完全没有打印；且计划与绘制必须一致（与字体无关的不变量）",
    ),
    Gate(
        "ai-no-silent-template",
        "AI 失效时不得静默插模板句",
        "tests/fidelity/test_beewrite_ai_llm.py",
        "曾经：'AI 续写'其实是 random.choice(12 条句库)，却提示'✅ AI 续写完成'",
    ),
    Gate(
        "undo-boundary",
        "打开文件后 Ctrl+Z 不得删正文",
        "tests/fidelity/test_p1b_usability.py -k 'undo'",
        "曾经：装载内容进了撤销栈 → 刚打开按 Ctrl+Z 就把正文删了（689→677）",
    ),
    Gate(
        "spellcheck-baseline",
        "拼写检查基线 + 技术词白名单",
        "tests/fidelity/test_spellcheck.py tests/fidelity/test_spellcheck_techwords.py tests/fidelity/test_spellcheck_dialog.py",
        "曾经：真词典对中文技术文档误报 619 处；且必须按需触发而非常驻标红",
    ),
    Gate(
        "ai-settings",
        "AI 设置：保存要落盘、Ollama 免 Key",
        "tests/fidelity/test_ai_settings.py",
        "曾经：AI 功能没有可视化配置入口，用户只能手改 settings.json",
    ),
    Gate(
        "ruff-bug-classes",
        "确定性 bug 类静态检查（未定义名/重复定义/语法）",
        "beeoffice tests",
        "曾经：`_media_cache_root` 用了 tempfile 却没 import → 只读位置文档打不开",
        kind="ruff",
    ),
]


def _run(cmd, log_path):
    """跑一条命令，stdout/stderr **重定向到文件**（不用管道：沙箱禁止管道捕获）。"""
    with open(log_path, "w", encoding="utf-8", errors="replace") as log:
        result = subprocess.run(
            cmd, cwd=str(ROOT), stdout=log, stderr=subprocess.STDOUT,
            text=True,
        )
    return result.returncode


def _tail(path, lines=6):
    try:
        content = Path(path).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""
    return "\n".join(content.strip().splitlines()[-lines:])


def run_gate(gate, tmpdir):
    # ⚠️ 必须用 shlex 解析：直接 `.split()` 会把 `-k 'a or b'` 拆坏
    #    （引号失效 → pytest 匹配不到用例 → 假失败。我第一版就是这么错的）
    target_args = shlex.split(gate.target)
    if gate.kind == "ruff":
        cmd = [sys.executable, "-m", "ruff", "check", *target_args,
               "--select", "F821,F811,F822,F823,E9"]
    else:
        cmd = [sys.executable, "-m", "pytest", *target_args,
               "-q", "--no-header", "-p", "no:cacheprovider",
               "-o", "log_file=", "--timeout=900"]
    log = Path(tmpdir) / f"{gate.gid}.log"
    started = time.perf_counter()
    code = _run(cmd, log)
    elapsed = time.perf_counter() - started
    return code, elapsed, log


def main():
    parser = argparse.ArgumentParser(description="BeeOffice 回归门禁")
    parser.add_argument("--strict-timing", action="store_true",
                        help="计时门禁也参与阻断（需空载机器）")
    parser.add_argument("--only", default="",
                        help="只跑这些门禁（逗号分隔的 id）")
    parser.add_argument("--list", action="store_true", help="只列出门禁")
    args = parser.parse_args()

    gates = GATES
    if args.only:
        wanted = {x.strip() for x in args.only.split(",") if x.strip()}
        gates = [g for g in GATES if g.gid in wanted]
        if not gates:
            print(f"没有匹配的门禁：{args.only}")
            return 2

    if args.list:
        for gate in GATES:
            flag = "计时" if gate.timing else "确定性"
            print(f"  [{flag}] {gate.gid:<28} {gate.title}")
        return 0

    print("=" * 78)
    print(f"BeeOffice 回归门禁（{len(gates)} 项；"
          f"计时门禁{'参与' if args.strict_timing else '仅报告'}阻断）")
    print("=" * 78)

    failures = []
    with tempfile.TemporaryDirectory(prefix="beeoffice_gates_") as tmpdir:
        for gate in gates:
            kind = "计时" if gate.timing else "确定性"
            print(f"\n[ ] {gate.gid}（{kind}）— {gate.title}")
            print(f"      守的是：{gate.guards}")
            code, elapsed, log = run_gate(gate, tmpdir)
            ok = code == 0
            blocking = (not gate.timing) or args.strict_timing
            status = "PASS" if ok else ("FAIL" if blocking else "FAIL(不阻断)")
            print(f"      → {status}  用时 {elapsed:.1f}s")
            if not ok:
                print("      " + _tail(log, 8).replace("\n", "\n      "))
                if blocking:
                    failures.append(gate.gid)

    print()
    print("=" * 78)
    if failures:
        print(f"✗ 门禁失败（阻断项）：{', '.join(failures)}")
        return 1
    print("✓ 全部阻断项通过")
    if not args.strict_timing:
        print("  （计时项只报告，未参与阻断；用 --strict-timing 可在空载机上卡住它）")
        print("  注意：计时门禁在**满载**时出现 FAIL(不阻断) 是预期现象 ——")
        print("        本项目实测它满载会红、空载连跑 3 次都过；请单独复测再判断。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
