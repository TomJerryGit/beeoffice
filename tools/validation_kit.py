# tools/validation_kit.py
"""
**外部验证证据采集工具**（阶段③最后一道门槛的辅助工具）。

## 为什么
"90 天可验证交付"还缺一份**真实外部用户**的证据：
一台没装 Python/GUI 的机器上，用 `beecmd.exe` 完成一件真实工作。
这一步必须由人执行；但"怎么跑、要留什么证据、怎么回传"可以工具化，
把门槛降到一条命令。

## 用法（在外部机器上）
    python tools/validation_kit.py --beecmd beecmd.exe --task merge \
        --input 一月.xlsx --input 二月.xlsx --out-file 汇总.xlsx --out 证据目录

也支持 `convert` / `clean` / `ai` 三种任务。工具会：
1. 运行 `beecmd.exe` 并记录命令、退出码、stdout/stderr、耗时；
2. 记录输入/输出文件的 SHA-256 与大小（证明产物确实生成）；
3. 写 `evidence.json` + `evidence.md`；
4. `--zip` 时打包成 `evidence.zip`，便于回传。

## 隐私
不读取文件内容，只记录**路径/哈希/大小**；证据里不包含用户名等系统信息
（hostname 仅写平台名）。如果路径敏感，请先在外部机器上把文件放到独立目录再跑。
"""
import argparse
import hashlib
import json
import platform
import subprocess
import sys
import time
import zipfile
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

#: 任务 → 构造参数的说明（供帮助文本与测试使用）
TASKS = ("convert", "merge", "clean", "ai")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def file_record(path: Path) -> dict:
    """记录一个文件的路径/大小/哈希（不读内容到证据里）。"""
    path = Path(path)
    if not path.is_file():
        return {"path": str(path), "exists": False}
    return {
        "path": str(path),
        "exists": True,
        "size": path.stat().st_size,
        "sha256": sha256_file(path),
    }


def build_command(beecmd: str, task: str, inputs, out_file=None,
                  to: str = "xlsx", plan=None, api_base="",
                  model=""):
    """按任务构造命令行（纯函数，便于测试）。"""
    exe = str(beecmd)
    inputs = [str(item) for item in inputs]
    if task == "convert":
        cmd = [exe, "convert", inputs[0], "--to", to]
        if out_file:
            cmd += ["-o", str(out_file)]
    elif task == "merge":
        cmd = [exe, "merge", *inputs, "-o", str(out_file)]
    elif task == "clean":
        cmd = [exe, "clean", inputs[0], "-o", str(out_file)]
        if plan:
            cmd += ["--plan", str(plan)]
    elif task == "ai":
        cmd = [exe, "ai", "summarize", inputs[0], "-o", str(out_file)]
        if api_base:
            cmd += ["--api-base", api_base]
        if model:
            cmd += ["--model", model]
    else:
        raise ValueError(f"未知任务: {task}（可选 {TASKS}）")
    return cmd


def run_command(cmd, timeout: int = 600) -> dict:
    """运行命令并采集退出码/输出/耗时（失败也返回证据，由调用方判定）。"""
    started = time.perf_counter()
    try:
        completed = subprocess.run(
            cmd, capture_output=True, text=True, encoding="utf-8",
            errors="replace", timeout=timeout,
        )
        elapsed = time.perf_counter() - started
        return {
            "exit_code": completed.returncode,
            "stdout": completed.stdout.strip(),
            "stderr": completed.stderr.strip(),
            "elapsed_s": round(elapsed, 2),
            "timeout": False,
        }
    except subprocess.TimeoutExpired:
        return {
            "exit_code": None,
            "stdout": "",
            "stderr": f"命令超时（>{timeout}s）",
            "elapsed_s": round(time.perf_counter() - started, 2),
            "timeout": True,
        }


def build_evidence(beecmd, task, command, result, inputs, out_file,
                   extra_files=()) -> dict:
    """把一次验证运行整理成证据对象。"""
    outputs = []
    if out_file:
        outputs.append(file_record(Path(out_file)))
    # 同目录的附属产物（报告/计划等）由调用方显式给出
    outputs += [file_record(Path(p)) for p in extra_files]
    return {
        "tool": "validation_kit",
        "collected_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "platform": platform.platform(),
        "beecmd": str(beecmd),
        "task": task,
        "command": command,
        "result": result,
        "inputs": [file_record(Path(p)) for p in inputs],
        "outputs": outputs,
        "ok": result.get("exit_code") == 0 and all(
            item.get("exists") for item in outputs
        ),
    }


def build_markdown(evidence: dict) -> str:
    result = evidence["result"]
    mark = "✅" if evidence["ok"] else "❌"
    lines = [
        "# 外部验证证据（自动生成）",
        "",
        f"> 采集时间：{evidence['collected_at']} · 平台：`{evidence['platform']}`",
        f"> 工具：`tools/validation_kit.py` · 任务：`{evidence['task']}`",
        "",
        "## 0. 结论",
        "",
        f"- {mark} 退出码 **{result.get('exit_code')}**，耗时 **{result.get('elapsed_s')} s**；"
        f"产物存在：**{'是' if evidence['ok'] else '否/不完整'}**",
        "",
        "## 1. 命令",
        "",
        "```powershell",
        " ".join(str(part) for part in evidence["command"]),
        "```",
        "",
        "## 2. 输入",
        "",
        "| 文件 | 大小 | SHA-256 |",
        "|---|---:|---|",
    ]
    for item in evidence["inputs"]:
        if not item.get("exists"):
            lines.append(f"| `{item['path']}` | — | **不存在** |")
            continue
        lines.append(
            f"| `{item['path']}` | {item['size']} B | `{item['sha256'][:16]}…` |"
        )
    lines += [
        "",
        "## 3. 产物",
        "",
        "| 文件 | 大小 | SHA-256 |",
        "|---|---:|---|",
    ]
    for item in evidence["outputs"]:
        if not item.get("exists"):
            lines.append(f"| `{item['path']}` | — | **未生成** |")
            continue
        lines.append(
            f"| `{item['path']}` | {item['size']} B | `{item['sha256'][:16]}…` |"
        )
    lines += [
        "",
        "## 4. 输出（可审计）",
        "",
        "```text",
        result.get("stdout") or "（无 stdout）",
        "```",
        "",
    ]
    if result.get("stderr"):
        lines += ["stderr：", "", "```text", result["stderr"], "```", ""]
    lines += [
        "## 5. 回传方式",
        "",
        "把本文件、`evidence.json`（以及 `--zip` 生成的 `evidence.zip`）回传即可。",
        "证据只包含**路径/哈希/大小**，不包含文件内容。",
        "",
    ]
    return "\n".join(lines)


def write_evidence(evidence: dict, out_dir: Path, make_zip: bool = False) -> dict:
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / "evidence.json"
    md_path = out_dir / "evidence.md"
    json_path.write_text(
        json.dumps(evidence, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    md_path.write_text(build_markdown(evidence), encoding="utf-8")
    result = {"json": str(json_path), "markdown": str(md_path)}
    if make_zip:
        zip_path = out_dir / "evidence.zip"
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as archive:
            archive.write(json_path, arcname="evidence.json")
            archive.write(md_path, arcname="evidence.md")
        result["zip"] = str(zip_path)
    return result


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="外部验证证据采集（在目标机器上跑 beecmd.exe 并留痕）"
    )
    parser.add_argument("--beecmd", required=True, help="beecmd.exe 路径")
    parser.add_argument("--task", required=True, choices=TASKS)
    parser.add_argument("--input", action="append", required=True,
                        help="输入文件（merge 可给多个）")
    parser.add_argument("--out-file", help="产物路径（convert/merge/clean/ai）")
    parser.add_argument("--to", default="xlsx", help="convert 的目标格式")
    parser.add_argument("--plan", help="clean 的计划 JSON")
    parser.add_argument("--api-base", default="", help="ai 的 OpenAI 兼容地址")
    parser.add_argument("--model", default="", help="ai 的模型名")
    parser.add_argument("--out", required=True, help="证据输出目录")
    parser.add_argument("--timeout", type=int, default=600)
    parser.add_argument("--zip", action="store_true", help="额外打包 evidence.zip")
    args = parser.parse_args(argv)

    command = build_command(
        args.beecmd, args.task, args.input, out_file=args.out_file,
        to=args.to, plan=args.plan, api_base=args.api_base, model=args.model,
    )
    print(f"运行：{' '.join(command)}", flush=True)
    result = run_command(command, timeout=args.timeout)
    extra = []
    if args.out_file:
        out_path = Path(args.out_file)
        for suffix in (".report.json", ".plan.json"):
            candidate = out_path.with_name(out_path.name + suffix)
            if candidate.is_file():
                extra.append(candidate)
    evidence = build_evidence(
        args.beecmd, args.task, command, result, args.input,
        args.out_file, extra_files=extra,
    )
    paths = write_evidence(evidence, Path(args.out), make_zip=args.zip)
    if evidence["ok"]:
        print("✅ 验证通过，证据已保存：")
    else:
        print("❌ 验证未通过（证据同样已保存，便于排查）：")
    for name, path in paths.items():
        print(f"   {name}: {path}")
    return 0 if evidence["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
