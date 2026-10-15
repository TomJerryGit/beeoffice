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
    return 0


if __name__ == "__main__":
    sys.exit(main())
