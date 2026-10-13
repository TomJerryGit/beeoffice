# tools/fidelity_corpus.py
"""
保真度 **corpus 运行器**（阶段 A）

与 `fidelity_roundtrip.py` 的区别
--------------------------------
后者用**自己合成的**测试文件；本工具遍历**真实文件**并逐一做往返、报丢失。

为什么需要它：合成文件是我自己造的，**必然覆盖不到真实世界的构造**。
"往返零丢失"这个结论目前只成立于合成夹具；要检验它对真实文档是否成立，
只能拿真实文件去撞。

用法
----
    python tools/fidelity_corpus.py                    # 默认扫描 test+files 与 corpus
    python tools/fidelity_corpus.py --dir 某目录        # 指定目录（可多次）
    python tools/fidelity_corpus.py --json 结果.json
    python tools/fidelity_corpus.py --quiet            # 只打印有丢失的文件

默认目录：
    test+files/                  仓库里已有的真实样例
    tests/fidelity/corpus/       建议放置脱敏后的真实文件（可提交小文件）

退出码：发现任何丢失则为 1（可直接作为 CI 门禁）。
"""

import argparse
import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.ooxml_probe import compare, probe          # noqa: E402

DEFAULT_DIRS = ("test+files", "tests/fidelity/corpus")
SUPPORTED = (".docx", ".xlsx", ".pptx")


def iter_files(dirs):
    """
    遍历给定目录下的 OOXML 文件（跳过 Office 锁文件与往返产物）。

    注意：**不要**在这里过滤 `_ptmp` —— 用户可能显式把临时目录当语料目录
    （本会话就是这么测压力语料的；我第一版加了该过滤，结果"找到 0 个文件"）。
    """
    found = []
    for d in dirs:
        base = Path(d)
        if not base.is_dir():
            continue
        for path in sorted(base.rglob("*")):
            if path.suffix.lower() not in SUPPORTED:
                continue
            if path.name.startswith("~$"):
                continue
            if path.name.startswith("rt_"):
                continue          # 本工具自己产出的往返结果
            found.append(path)
    return found


def _roundtrip_for(suffix):
    """返回该格式的往返函数；PPTX 没有导入路径。"""
    if suffix == ".docx":
        from tools.fidelity_roundtrip import roundtrip_docx

        return roundtrip_docx
    if suffix == ".xlsx":
        from tools.fidelity_roundtrip import roundtrip_xlsx

        return roundtrip_xlsx
    return None


def run_one(path: Path, workdir: Path) -> dict:
    """
    探测 → 往返 → 再探测。

    **先在临时目录里做一份副本**再往返，原因有两条：

    1. `import_from_docx()` 会把提取出的图片写到**源文件旁边**的
       `<源名>_media/`。若直接在 corpus 里跑，就会往用户的语料目录里写东西。
    2. 若那个 `_media/` 目录**已存在**（例如人工跑过一次）而当前进程无权覆盖，
       图片提取会失败、表现为 `images → 0` —— 那是**测量环境的假象**，
       会被误读成产品缺陷（我第一版就踩了这个假象）。
    """
    import shutil

    result = {
        "path": str(path), "name": path.name,
        "format": path.suffix.lower().lstrip("."),
        "size": path.stat().st_size,
        "before": None, "after": None, "rows": [], "error": None,
        "skipped": None,
    }

    try:
        work_src = workdir / path.name
        shutil.copy2(path, work_src)

        result["before"] = probe(work_src)
    except Exception as e:                                  # noqa: BLE001
        result["error"] = f"探测失败: {type(e).__name__}: {e}"
        return result

    roundtrip = _roundtrip_for(path.suffix.lower())
    if roundtrip is None:
        result["skipped"] = "该格式没有导入路径（只导出）"
        return result

    out = workdir / f"rt_{path.stem}{path.suffix}"
    try:
        ok, _note = roundtrip(work_src, out)
    except Exception as e:                                  # noqa: BLE001
        result["error"] = f"往返异常: {type(e).__name__}: {e}"
        return result

    if not ok or not out.is_file():
        result["error"] = "往返未产出文件"
        return result

    result["after"] = probe(out)
    result["rows"] = compare(result["before"], result["after"])
    return result


def summarize(results):
    """统计：有丢失的文件、丢失项明细。"""
    bad = []
    for r in results:
        if r["error"] or r["skipped"]:
            continue
        lost = [x for x in r["rows"] if x["status"] == "lost"]
        if lost:
            bad.append((r, lost))
    return bad


def render(results, quiet=False):
    lines = []
    for r in results:
        head = f"{r['name']}  ({r['format']}, {r['size']} B)"
        if r["error"]:
            lines.append(f"✗ {head}\n    {r['error']}")
            continue
        if r["skipped"]:
            if not quiet:
                lines.append(f"— {head}\n    {r['skipped']}")
            continue
        lost = [x for x in r["rows"] if x["status"] == "lost"]
        changed = [x for x in r["rows"] if x["status"] == "changed"]
        gained = [x for x in r["rows"] if x["status"] == "gained"]
        if not lost and not changed and not gained:
            if not quiet:
                lines.append(f"✓ {head}  零差异")
            continue
        lines.append(
            f"{'✗' if lost else '~'} {head}  "
            f"丢失 {len(lost)} / 变化 {len(changed)} / 增加 {len(gained)}"
        )
        for x in lost + changed:
            lines.append(
                f"      {x['feature']}: {x['before']} → {x['after']}"
            )
        for x in gained:
            lines.append(
                f"      (增加) {x['feature']}: {x['before']} → {x['after']}"
            )
    return "\n".join(lines)


def main(argv=None):
    ap = argparse.ArgumentParser(description="真实文件保真度往返检查")
    ap.add_argument("--dir", action="append", dest="dirs",
                    help="要扫描的目录（可多次；默认 test+files 与 corpus）")
    ap.add_argument("--json", help="结果另存为 JSON")
    ap.add_argument("--quiet", action="store_true",
                    help="只列出有差异/失败的文件")
    args = ap.parse_args(argv)

    dirs = args.dirs or list(DEFAULT_DIRS)
    files = iter_files(dirs)

    print(f"扫描目录: {', '.join(dirs)}")
    print(f"找到 {len(files)} 个文件\n")

    if not files:
        print("没有找到可测文件。可把脱敏的真实文件放进 "
              "tests/fidelity/corpus/ 后再运行。")
        return 0

    results = []
    with tempfile.TemporaryDirectory(prefix="beeoffice_corpus_") as td:
        workdir = Path(td)
        for path in files:
            print(f"  正在测 {path.name} ...", flush=True)
            results.append(run_one(path, workdir))

    print()
    print(render(results, quiet=args.quiet))

    bad = summarize(results)
    errors = [r for r in results if r["error"]]

    print()
    print("=" * 60)
    print(f"文件 {len(results)} 个："
          f"有丢失 {len(bad)}、异常 {len(errors)}、"
          f"跳过往返 {len([r for r in results if r['skipped']])}")

    if args.json:
        Path(args.json).write_text(
            json.dumps(results, ensure_ascii=False, indent=2, default=str),
            encoding="utf-8",
        )
        print(f"JSON 已写入 {args.json}")

    return 1 if (bad or errors) else 0


if __name__ == "__main__":
    sys.exit(main())
