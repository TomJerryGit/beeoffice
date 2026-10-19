# beeoffice/beecmd.py
"""
`beecmd` —— BeeOffice 的**无界面命令行**（v0）。

## 为什么要有这个
《WPS 对比与深度变革战略》§5.2 的结论：BeeOffice 的能力全部绑在 GUI 上，
**无法被脚本/服务调用** —— 这是"从编辑器变成流水线"最大的缺口。
`beecmd` v0 先证明一件事：

> **外部用户不开界面，用一条命令完成一件真实工作。**

## v0 的能力边界（**故意很小**，但要真能用）
**纯 Python，不 import 任何 Qt**（可在服务器/容器里跑）：
* `convert`：表格互转（`xlsx`/`xls`/`csv`/`json`/`md`/`html` ↔ `xlsx`）、
  演示文稿 `md → .beshow`
* `info`：读出一个文件的工作表/尺寸/表头（检查用）
* `verify`：把转换产物与源文件**逐格对比**，输出 JSON 报告
* `batch`：按 JSON 任务清单批量执行，写 `audit.jsonl` 审计流水

## v0.1 追加（需要 Qt，自动用 offscreen）
* `convert 文稿.md --to docx`：经蜜写的富文本编辑器写 Word
* `convert 文稿.md --to pdf`：经蜜写的打印引擎出 PDF
* `verify 文稿.md 文稿.docx / .pdf`：把产物里的文本与源 Markdown 做**词元级**比对
  （PDF/Word 的文本提取会有换行差异，逐行比会误报，所以比词元集合）

**明确不在 v0.1**（不要假装有）：
* `docx → md`（蜜写的 docx 载入是带异步与"附加内容"的完整流程，没有单点 API）
* `表格 → pdf`（蜜算的打印导出挂在视图上，需要先把数据装进模型）
* 并行执行（Qt 的 offscreen 初始化在多线程里不稳；串行更诚实）

## v0.2 追加（纯 Python，仍然零 Qt）
* `merge`：**多表汇总** —— 把多个 xlsx/csv/json/md/html 合并成一个 xlsx
  * `append`（默认）：按列名对齐、纵向追加，并追加一列「来源文件」
  * `sheets`：每个输入文件的每个工作表放进同一个工作簿
  * 字符串/数字/空值按 pandas 语义处理；列不一致时取并集，缺列留空
* `batch` 支持 `{"op": "merge", "srcs": [...], "out": "...", ...}`

## v0.3 追加（纯 Python，零 Qt）
* `ai`：对文本文件执行**任务式 AI**（`summarize` / `polish` / `keywords` /
  `continue` / `extract` 条款抽取 / `outline` 演示大纲）
  * 配置顺序：命令行参数 > `BEEOFFICE_AI_*` 环境变量 > 应用「AI 设置」；
  * 本地 Ollama 示例：`--api-base http://127.0.0.1:11434/v1 --model llama3.2`（无需 Key）；
  * **诚实性**：AI 不可用/调用失败时直接报错退出，绝不拿本地规则冒充 AI；
    `extract` 输出必须是合法 JSON、`outline` 必须有标题行，否则保存 raw 并失败；
    成功时标出来源（模型名）与耗时，可写 JSON 元信息；
* `batch` 支持 `{"op": "ai", "task": "summarize", "src": "...", "out": "..."}`。

## 退出码（便于脚本判断）
* `0` 成功
* `1` 出错（参数/IO/不支持的转换）
* `2` `verify` 发现不一致
* `3` `verify` **不可判定**（例如 PDF 文本提取为空：本机无字体或产物是空白页 ——
  这是"不知道"，不是"通过"，也不是"不一致"）

## 用法
    python -m beeoffice.beecmd convert 表.xlsx --to csv -o 表.csv
    python -m beeoffice.beecmd convert 表.csv --to xlsx -o 表.xlsx
    python -m beeoffice.beecmd convert 讲稿.md --to beshow -o 讲稿.beshow
    python -m beeoffice.beecmd info 表.xlsx
    python -m beeoffice.beecmd verify 表.xlsx 表.csv --report 报告.json
    python -m beeoffice.beecmd merge 1月.xlsx 2月.xlsx 3月.xlsx -o 一季度汇总.xlsx
    python -m beeoffice.beecmd batch jobs.json --audit audit.jsonl
"""
from __future__ import annotations

import argparse
import datetime as _dt
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

__version__ = "0.3.0"

#: 支持的表格输入扩展名
SHEET_INPUTS = (".xlsx", ".xls", ".csv", ".json", ".md", ".html", ".htm")
#: 支持的输出格式
SHEET_OUTPUTS = ("xlsx", "csv", "json", "md", "html")
#: 文稿格式（pptx 走**导入**：文字/层级/备注保留，其余出损失报告）
DECK_INPUTS = (".md", ".pptx")
DECK_OUTPUTS = ("beshow",)

EXIT_OK, EXIT_ERROR, EXIT_MISMATCH, EXIT_INCONCLUSIVE = 0, 1, 2, 3


class BeecmdError(RuntimeError):
    """可预期的失败（参数/IO/不支持），CLI 会把它转成人类可读提示。"""


# ==================== 读文件 → WorkbookData ====================

def _read_sheet_table(path: Path, sheet: Optional[str] = None):
    """把表格类文件读成 `WorkbookData`（xlsx/xls 走工作簿读取器，其余走 pandas/md 解析）。"""
    from beeoffice.plugins.beesheet_workbook import read_workbook

    suffix = path.suffix.lower()
    if suffix in (".xlsx", ".xls"):
        return read_workbook(str(path))
    if suffix == ".csv":
        import pandas as pd

        df = pd.read_csv(path)
        return _make_workbook([(path.stem, df)])
    if suffix == ".json":
        import pandas as pd

        df = pd.read_json(path)
        return _make_workbook([(path.stem, df)])
    if suffix in (".html", ".htm"):
        import pandas as pd

        tables = pd.read_html(path)
        if not tables:
            raise BeecmdError(f"{path} 里没有可解析的表格")
        return _make_workbook([(f"{path.stem}_{i + 1}", t)
                               for i, t in enumerate(tables)])
    if suffix == ".md":
        from beeoffice.plugins.beewrite_utils import parse_md_table

        # 用 utf-8-sig：Windows 上 Notepad/PowerShell 写出的文件常带 BOM
        rows = parse_md_table(
            path.read_text(encoding="utf-8-sig").splitlines()
        )
        if not rows:
            raise BeecmdError(f"{path} 里没有 Markdown 表格")
        header, body = rows[0], rows[1:]
        import pandas as pd

        df = pd.DataFrame(body, columns=header)
        return _make_workbook([(path.stem, df)])
    raise BeecmdError(f"不支持的表格输入: {path.suffix}")


def _make_workbook(pairs):
    """`[(表名, DataFrame)] → WorkbookData`（走产品自己的数据结构，保证与 GUI 一致）。"""
    from beeoffice.plugins.beesheet_workbook import SheetData, WorkbookData

    return WorkbookData(sheets=[SheetData(name=str(n), df=df) for n, df in pairs])


# ==================== 写文件 ← WorkbookData ====================

def _pick_sheet(workbook, sheet: Optional[str]):
    if sheet is None:
        return workbook.sheets[0]
    got = workbook.get(sheet)
    if got is None:
        names = [s.name for s in workbook.sheets]
        raise BeecmdError(f"没有工作表 {sheet!r}；可选: {names}")
    return got


def _write_sheet(workbook, fmt: str, out: Path, sheet: Optional[str]) -> Path:
    fmt = fmt.lower().lstrip(".")
    if fmt not in SHEET_OUTPUTS:
        raise BeecmdError(f"不支持的输出格式 {fmt!r}；可选: {', '.join(SHEET_OUTPUTS)}")

    if fmt == "xlsx":
        from beeoffice.plugins.beesheet_workbook import write_workbook

        status = write_workbook(workbook, str(out))
        if status not in (None, "", "ok", True):
            # 写入器返回的是状态说明；只有明确失败才算失败
            text = str(status)
            if "失败" in text or "error" in text.lower():
                raise BeecmdError(f"写 {out} 失败: {text}")
        return out

    target = _pick_sheet(workbook, sheet)
    df = target.df
    out.parent.mkdir(parents=True, exist_ok=True)
    if fmt == "csv":
        df.to_csv(out, index=False, encoding="utf-8-sig")
    elif fmt == "json":
        out.write_text(
            df.to_json(orient="records", force_ascii=False, indent=2),
            encoding="utf-8",
        )
    elif fmt == "md":
        out.write_text(_df_to_md(df), encoding="utf-8")
    elif fmt == "html":
        out.write_text(df.to_html(index=False), encoding="utf-8")
    return out


def _df_to_md(df) -> str:
    """DataFrame → Markdown 表格（本仓库既有 `render_md_table` 的语义）。"""
    from beeoffice.plugins.beewrite_utils import render_md_table

    header = [str(c) for c in df.columns]
    rows = [[("" if _is_blank(v) else str(v)) for v in row]
            for row in df.itertuples(index=False, name=None)]
    return render_md_table([header] + rows)


def _is_blank(value) -> bool:
    if value is None:
        return True
    try:
        import pandas as pd

        return bool(pd.isna(value))
    except Exception:  # noqa: BLE001
        return False


# ==================== 演示文稿 ====================

def _write_deck(src: Path, out: Path) -> Path:
    """
    Markdown / `.pptx` → 蜜演文稿（`.beshow`）。

    `.pptx` 走 `beeshow_pptx_import` 的导入路径（**文字/层级/备注保留，
    图片/表格/图表/版式不保留**），并把损失清单打印出来 —— 不假装搬得过去。
    """
    from beeoffice.plugins.beeshow_doc import save_deck

    if src.suffix.lower() == ".pptx":
        from beeoffice.plugins.beeshow_pptx_import import (
            import_pptx, loss_summary,
        )

        imported, markdown = import_pptx(src)
        if not save_deck(str(out), markdown):
            raise BeecmdError(f"写 {out} 失败（.beshow 保存返回 False）")
        print(f"📄 已导入 {imported.slide_count} 页；{loss_summary(imported)}")
        return out

    # 用 utf-8-sig：Windows 上 Notepad/PowerShell 写的文件常带 BOM
    text = src.read_text(encoding="utf-8-sig")
    if not save_deck(str(out), text):
        raise BeecmdError(f"写 {out} 失败（.beshow 保存返回 False）")
    return out


# ==================== 文稿：md → docx / pdf（v0.1，需要 Qt）====================

#: 视为"文稿源"的扩展名（目前只有 Markdown —— docx→md 没有单点 API，见模块文档）
DOC_SOURCES = (".md", ".markdown", ".txt")
#: 需要 Qt 的输出格式
QT_OUTPUTS = ("docx", "pdf")

_QT_APP = None


def _ensure_qt():
    """
    惰性初始化 Qt（**只在文稿/PDF 路径**用到，表格路径保持零 Qt）。

    默认把平台设成 `offscreen`：CLI 不需要真窗口，服务器/CI 也能跑。
    用户显式设过 `QT_QPA_PLATFORM` 就尊重他的设置。
    """
    global _QT_APP
    if _QT_APP is not None:
        return _QT_APP
    import os

    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    try:
        from PySide6.QtWidgets import QApplication
    except Exception as e:  # noqa: BLE001
        raise BeecmdError(
            f"文稿/PDF 转换需要 PySide6（当前环境不可用：{e}）。\n"
            "表格类转换（xlsx/csv/json/md/html）不需要 Qt，可以照常使用。"
        ) from e
    _QT_APP = QApplication.instance() or QApplication([])
    return _QT_APP


def _convert_doc(src: Path, fmt: str, out: Path) -> Path:
    """
    用蜜写的编辑器件把 Markdown 变成 docx / pdf（与 GUI 同一套代码）。

    实测要点（都踩过）：
    * 用 **`set_content()`**（GUI 与测试里的正规入口）而不是 `rich_editor.set_markdown()`
      —— 后者只喂内部编辑器，`_write_docx` 在 markdown 模式下取的是
      `get_rendered_content()`，会写出**空文档**（我踩过，`_write_docx` 还返回 True）；
    * 需要 `show()` + `resize()`：打印/导出依赖布局。

    ⚠️ **PDF 的文本内容在本机无法验证**：offscreen 下 Qt 报
    `QFontDatabase: Cannot find font directory`，文字渲染不出来 →
    产物页数正常但**提取不到文本**。所以 `verify` 对 PDF 会返回"不可判定"（退出码 3），
    而不是假装通过或假装失败。
    """
    app = _ensure_qt()
    from beeoffice.plugins.beewrite import BeeWriteEditor

    text = src.read_text(encoding="utf-8-sig")
    editor = BeeWriteEditor()
    editor.resize(900, 1200)
    editor.show()
    app.processEvents()
    try:
        editor.set_content(text)
        app.processEvents()
        if fmt == "docx":
            ok = editor._write_docx(str(out))
            if ok is False:
                raise BeecmdError(f"写 {out} 失败（_write_docx 返回 False）")
        elif fmt == "pdf":
            # MRO 里 DocMixin 在 ExportMixin 之前 → 这个 export_pdf 收 path
            ok = editor.export_pdf(str(out))
            if not ok:
                raise BeecmdError(f"写 {out} 失败（export_pdf 返回假）")
        else:  # pragma: no cover - 由调用方保证
            raise BeecmdError(f"不支持的文稿输出格式: {fmt}")
    finally:
        editor.close()
        editor.deleteLater()
        app.processEvents()   # 没有事件循环时也让 deleteLater 生效
    return out


# ==================== 命令：convert ====================

def cmd_convert(src: str, to: str, out: Optional[str],
                sheet: Optional[str] = None) -> int:
    src_path = Path(src)
    if not src_path.is_file():
        raise BeecmdError(f"源文件不存在: {src}")

    fmt = to.lower().lstrip(".")
    out_path = Path(out) if out else _default_out(src_path, fmt)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    if fmt == "beshow":
        _write_deck(src_path, out_path)
    elif fmt in QT_OUTPUTS:
        if src_path.suffix.lower() not in DOC_SOURCES:
            raise BeecmdError(
                f"{fmt} 输出 v0.1 只支持 Markdown 源（{', '.join(DOC_SOURCES)}），"
                f"收到 {src_path.suffix}。\n"
                "表格→PDF、docx→md 尚未支持（见模块文档的 v0.2 待办）。"
            )
        _convert_doc(src_path, fmt, out_path)
    else:
        workbook = _read_sheet_table(src_path, sheet)
        _write_sheet(workbook, fmt, out_path, sheet)

    print(f"✅ {src_path.name} → {out_path}（{fmt}）")
    return EXIT_OK


def _default_out(src: Path, fmt: str) -> Path:
    return src.with_suffix(f".{fmt}")


# ==================== 命令：info ====================

def cmd_info(src: str) -> int:
    path = Path(src)
    if not path.is_file():
        raise BeecmdError(f"文件不存在: {src}")
    workbook = _read_sheet_table(path)
    payload = {
        "tool": "beecmd",
        "version": __version__,
        "file": str(path),
        "sheets": [
            {
                "name": s.name,
                "rows": int(len(s.df)),
                "cols": int(len(s.df.columns)),
                "columns": [str(c) for c in s.df.columns],
            }
            for s in workbook.sheets
        ],
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return EXIT_OK


# ==================== 命令：merge（v0.2：多表汇总）====================

def _unique_sheet_name(name: str, used: set) -> str:
    """工作表名去重（Excel 限制 31 字符；重名时追加 `_2`/`_3`）。"""
    base = (str(name).strip() or "Sheet")[:31]
    candidate = base
    index = 2
    while candidate in used:
        suffix = f"_{index}"
        candidate = (base[:31 - len(suffix)] + suffix)
        index += 1
    used.add(candidate)
    return candidate


def cmd_merge(sources, out: str, mode: str = "append",
              source_column: str = "来源文件",
              sheet_name: str = "汇总") -> int:
    """
    多表汇总（v0.2）：把多个表格文件合并为一个 `.xlsx`。

    **append**（默认）：按列名纵向叠加，并在最前面加一列「来源文件」。
      适合"1 月.xlsx / 2 月.xlsx / 3 月.xlsx → 一季度汇总.xlsx"这类
      小公司最常见的汇总需求；列不一致时取并集，缺列留空。

    **sheets**：把每个输入文件的每个工作表放进同一个工作簿（名冲突自动加后缀）。

    :return: 退出码（成功 0；参数/IO 错误抛 BeecmdError → main 转成 1）
    """
    import pandas as pd

    if not isinstance(sources, (list, tuple)) or len(sources) < 2:
        raise BeecmdError("merge 至少需要 2 个输入文件")
    paths = [Path(s) for s in sources]
    for path in paths:
        if not path.is_file():
            raise BeecmdError(f"源文件不存在: {path}")
    out_path = Path(out)
    if out_path.suffix.lower() != ".xlsx":
        raise BeecmdError(
            f"merge 只输出 .xlsx（收到 {out_path.suffix or '无扩展名'}）"
        )
    out_path.parent.mkdir(parents=True, exist_ok=True)

    mode = (mode or "append").lower()
    if mode not in ("append", "sheets"):
        raise BeecmdError(f"不支持的 merge 模式 {mode!r}（可选 append/sheets）")

    if mode == "append":
        frames = []
        for path in paths:
            df = _read_sheet_table(path).sheets[0].df.copy()
            if source_column in df.columns:
                raise BeecmdError(
                    f"输入 {path.name} 已有列「{source_column}」，"
                    "请用 --source-column 换一个名字"
                )
            df.insert(0, source_column, path.name)
            frames.append(df)
        merged = pd.concat(frames, ignore_index=True, sort=False)
        workbook = _make_workbook([(sheet_name or "汇总", merged)])
        detail = f"{len(paths)} 个文件 / {len(merged)} 行"
    else:
        used = set()
        sheets = []
        for path in paths:
            source_wb = _read_sheet_table(path)
            multi = len(source_wb.sheets) > 1
            for index, sheet in enumerate(source_wb.sheets):
                base = (f"{path.stem}-{sheet.name}"
                        if multi else path.stem)
                sheets.append(
                    (_unique_sheet_name(base or f"Sheet{index + 1}", used),
                     sheet.df)
                )
        workbook = _make_workbook(sheets)
        total_rows = sum(int(len(df)) for _, df in sheets)
        detail = f"{len(paths)} 个文件 / {len(sheets)} 个工作表 / {total_rows} 行"

    _write_sheet(workbook, "xlsx", out_path, None)
    print(f"✅ 已汇总 {detail} → {out_path}（{mode}）")
    return EXIT_OK


# ==================== 命令：verify ====================

def cmd_verify(src: str, artifact: str, report: Optional[str] = None) -> int:
    """
    把产物与源文件对比，输出 JSON 报告。

    * 两边都能读成表格 → **逐格对比**（值相同才算通过；空值与 NaN 视为等价）
    * 否则 → 按文本行对比（去掉首尾空行与多余空白）
    """
    src_path, art_path = Path(src), Path(artifact)
    for p in (src_path, art_path):
        if not p.is_file():
            raise BeecmdError(f"文件不存在: {p}")

    result: Dict[str, Any] = {
        "tool": "beecmd",
        "version": __version__,
        "op": "verify",
        "src": str(src_path),
        "artifact": str(art_path),
        "ok": False,
        "mismatches": 0,
        "samples": [],
        "sheets_checked": [],
    }

    try:
        wb_src = _read_sheet_table(src_path)
        wb_art = _read_sheet_table(art_path)
    except Exception:  # noqa: BLE001 - 读不成表格就退到文本对比
        result["mode"] = "text"
        mismatches, samples = _compare_text(src_path, art_path)
    else:
        result["mode"] = "sheet"
        mismatches, samples, checked = _compare_workbooks(wb_src, wb_art)
        result["sheets_checked"] = checked

    result["mismatches"] = mismatches
    result["samples"] = samples
    result["ok"] = mismatches == 0
    result["checked_at"] = _dt.datetime.now().isoformat(timespec="seconds")

    # PDF/Word 提取不到文本 → "不可判定"，既不报通过也不报失败
    if (result["mode"] == "text"
            and art_path.suffix.lower() in (".pdf", ".docx")
            and not _tokens(_extract_text(art_path))):
        result["inconclusive"] = True
        result["note"] = (
            "产物里提取不到任何文本：本机可能没有字体（offscreen 渲染）"
            "或产物是空白页。请人工打开确认 —— 这是『不知道』，不是『通过』。"
        )

    text = json.dumps(result, ensure_ascii=False, indent=2)
    if report:
        Path(report).write_text(text, encoding="utf-8")
        mark = ("⚠️" if result.get("inconclusive") else
                ("✅" if result["ok"] else "❌"))
        print(f"{mark} 报告已写入 {report}"
              f"（不一致 {mismatches} 处"
              + ("；不可判定" if result.get("inconclusive") else "") + "）")
    else:
        print(text)
    if result.get("inconclusive"):
        return EXIT_INCONCLUSIVE
    return EXIT_OK if result["ok"] else EXIT_MISMATCH


def _compare_workbooks(wb_src, wb_art) -> Tuple[int, List[dict], List[str]]:
    """
    逐格对比；只报告前 20 处差异（样本），总数照实统计。

    **表名匹配策略**（跨格式转换时表名必然不同，不能因此误报）：
    1. 源表名在产物里存在 → 按名字配
    2. 否则**两边表数相同** → 按位置配（并在样本里说明是按位置配的）
    3. 否则 → 报告缺表
    """
    mismatches = 0
    samples: List[dict] = []
    checked: List[str] = []

    art_by_name = {s.name: s for s in wb_art.sheets}
    position_mode = (
        len(wb_src.sheets) == len(wb_art.sheets)
        and not all(s.name in art_by_name for s in wb_src.sheets)
    )

    for index, s_src in enumerate(wb_src.sheets):
        if position_mode:
            s_art = wb_art.sheets[index]
        else:
            s_art = art_by_name.get(s_src.name)
        checked.append(s_src.name)
        if s_art is None:
            mismatches += 1
            if len(samples) < 20:
                samples.append({"sheet": s_src.name, "issue": "产物里缺这张表"})
            continue
        count, sheet_samples = _compare_frames(s_src.df, s_art.df)
        mismatches += count
        for smp in sheet_samples:
            if len(samples) < 20:
                smp["sheet"] = s_src.name
                if position_mode:
                    smp["matched_by"] = "position"
                samples.append(smp)
    return mismatches, samples, checked


def _norm(value):
    """比较用的归一化：空值统一成 ""，数字转 float，其它转 str。"""
    if _is_blank(value):
        return ""
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip()
    try:
        return float(text)
    except ValueError:
        return text


def _compare_frames(a, b) -> Tuple[int, List[dict]]:
    import pandas as pd

    count = 0
    samples: List[dict] = []
    rows = max(len(a), len(b))
    cols = max(len(a.columns), len(b.columns))
    av = a.values.tolist()
    bv = b.values.tolist()
    for r in range(rows):
        for c in range(cols):
            left = av[r][c] if r < len(av) and c < len(av[r]) else None
            right = bv[r][c] if r < len(bv) and c < len(bv[r]) else None
            if _norm(left) != _norm(right):
                count += 1
                if len(samples) < 20:
                    samples.append({
                        "cell": f"R{r + 1}C{c + 1}",
                        "src": "" if _is_blank(left) else str(left),
                        "artifact": "" if _is_blank(right) else str(right),
                    })
    del pd  # 只用来触达 pandas 依赖的一致性，不参与比较
    return count, samples


def _extract_text(path: Path) -> str:
    """
    从不同文件类型取出**纯文本**（供文本比对）。

    * `.docx`：python-docx（段落 + 表格单元格）
    * `.pdf`：PyMuPDF（逐页取文本）
    * 其它：按文本读（UTF-8，容忍 BOM）
    """
    suffix = path.suffix.lower()
    if suffix == ".docx":
        from docx import Document

        doc = Document(str(path))
        parts = [p.text for p in doc.paragraphs]
        for table in doc.tables:
            for row in table.rows:
                parts.append("\t".join(cell.text for cell in row.cells))
        return "\n".join(parts)
    if suffix == ".pdf":
        import fitz

        with fitz.open(str(path)) as pdf:
            return "\n".join(page.get_text() for page in pdf)
    return path.read_text(encoding="utf-8-sig", errors="replace")


def _tokens(text: str) -> List[str]:
    """
    切成**词元**：英文/数字按连续片段，中文按**单个汉字**。

    为什么不用逐行比：PDF/Word 提取出来的换行与源 Markdown 完全不同
    （一段话可能被拆成几行、也可能被合并），逐行比会大面积误报。
    """
    import re

    return re.findall(r"[A-Za-z0-9_]+|[\u4e00-\u9fff]", text)


def _compare_text(a: Path, b: Path) -> Tuple[int, List[dict]]:
    """词元级比对：报告"源有产物没有"与"产物有源没有"的数量与样例。"""
    from collections import Counter

    tok_a = _tokens(_extract_text(a))
    tok_b = _tokens(_extract_text(b))
    counter_a, counter_b = Counter(tok_a), Counter(tok_b)

    missing = counter_a - counter_b      # 源里有、产物里缺
    extra = counter_b - counter_a        # 产物里多出来
    samples: List[dict] = []
    for kind, counter in (("missing_in_artifact", missing),
                          ("extra_in_artifact", extra)):
        for token, count in list(counter.items())[:10]:
            if len(samples) < 20:
                samples.append({"kind": kind, "token": token, "count": count})
    return sum(missing.values()) + sum(extra.values()), samples


# ==================== 命令：ai（v0.3：本地/云端 AI 任务）====================

#: CLI 支持的 AI 任务 → (提示词构造函数名, 默认 max_tokens)
AI_TASKS = {
    "summarize": ("build_summarize_prompt", 800),
    "polish": ("build_polish_prompt", 1200),
    "keywords": ("build_keywords_prompt", 200),
    "continue": ("build_continue_prompt", 600),
    "extract": ("build_extract_prompt", 900),
    "outline": ("build_outline_prompt", 900),
}


def _strip_code_fence(text: str) -> str:
    """去掉模型偶尔自带的 ``` 代码围栏。"""
    stripped = text.strip()
    if not stripped.startswith("```"):
        return stripped
    lines = stripped.splitlines()[1:]
    if lines and lines[-1].strip() == "```":
        lines = lines[:-1]
    return "\n".join(lines).strip()


def _postprocess_ai(task: str, result: str) -> str:
    """
    按任务校验/规范化模型输出（**不合格就失败，不写结果文件**）。

    * `extract`：必须是合法 JSON（数组或对象）——否则"结构化抽取"是假的；
    * `outline`：必须至少有一行 `# 标题`（否则不是大纲）；
    * 其余任务：原样返回。
    """
    if task == "extract":
        raw = _strip_code_fence(result)
        try:
            data = json.loads(raw)
        except Exception as e:  # noqa: BLE001 - 统一转成可读失败
            raise ValueError(f"模型输出不是合法 JSON（{e}）") from None
        if not isinstance(data, (list, dict)):
            raise ValueError("JSON 顶层应为数组或对象")
        return json.dumps(data, ensure_ascii=False, indent=2)
    if task == "outline":
        raw = _strip_code_fence(result)
        if not any(line.lstrip().startswith("#") for line in raw.splitlines()):
            raise ValueError("大纲没有任何 `# 标题` 行")
        return raw
    return result.rstrip()


def _resolve_ai_config(model: str, api_base: str, api_key: str,
                       timeout: int) -> Dict[str, str]:
    """
    解析 AI 配置：**显式参数 > 环境变量 > 应用设置**。

    环境变量（便于服务器/流水线）：
      `BEEOFFICE_AI_API_BASE` / `BEEOFFICE_AI_MODEL` / `BEEOFFICE_AI_API_KEY`
    """
    import os

    try:
        from beeoffice.settings import AppSettings

        settings = AppSettings()
    except Exception:  # noqa: BLE001 - 设置文件不可用时只靠参数/环境变量
        settings = None

    base = (api_base or os.environ.get("BEEOFFICE_AI_API_BASE", "")
            or getattr(settings, "ai_api_base", "") or "")
    mdl = (model or os.environ.get("BEEOFFICE_AI_MODEL", "")
           or getattr(settings, "ai_model", "") or "")
    key = (api_key or os.environ.get("BEEOFFICE_AI_API_KEY", "")
           or getattr(settings, "ai_api_key", "") or "")
    return {
        "api_base": base.strip(),
        "model": mdl.strip(),
        "api_key": key.strip(),
        "timeout": int(timeout) if timeout else 0,
    }


def cmd_ai(task: str, src: str, out: Optional[str] = None,
           model: str = "", api_base: str = "", api_key: str = "",
           timeout: int = 0, max_points: int = 5, count: int = 8,
           length: int = 160, limit: int = 10, slides: int = 8,
           retry: bool = True,
           meta_json: Optional[str] = None) -> int:
    """
    对文本文件执行一次 AI 任务（总结 / 润色 / 关键词 / 续写 / 抽取 / 大纲）。

    **诚实性约束**（与 GUI 的 AI 纪律一致）：
      * 没配置好 AI（无地址/模型、云端无 Key）→ 直接失败并说明原因，**绝不**用本地
        规则冒充 AI 输出；
      * 调用失败 → 打印可照做的错误说明，退出码 1，不写输出文件；
      * `extract` 输出必须能解析为 JSON、`outline` 必须有标题行 —— 不满足就
        保存原始输出到 `<out>.raw.txt` 并失败，**不把不合规内容当结果**；
      * 成功 → 输出文件 + 来源标注（`AI 生成（模型名）`），可选 JSON 元信息。
    """
    import time

    from beeoffice.plugins import ai_client as ai_mod

    src_path = Path(src)
    if not src_path.is_file():
        raise BeecmdError(f"源文件不存在: {src}")
    if task not in AI_TASKS:
        raise BeecmdError(
            f"不支持的 AI 任务 {task!r}；可选: {', '.join(sorted(AI_TASKS))}"
        )
    text = src_path.read_text(encoding="utf-8-sig", errors="replace").strip()
    if not text:
        raise BeecmdError(f"源文件为空: {src}")

    prompt_name, max_tokens = AI_TASKS[task]
    builders = {
        "build_summarize_prompt": lambda t: ai_mod.build_summarize_prompt(
            t, max_points=max_points),
        "build_polish_prompt": ai_mod.build_polish_prompt,
        "build_keywords_prompt": lambda t: ai_mod.build_keywords_prompt(
            t, count=count),
        "build_continue_prompt": lambda t: ai_mod.build_continue_prompt(
            t, length_hint=length),
        "build_extract_prompt": lambda t: ai_mod.build_extract_prompt(
            t, limit=limit),
        "build_outline_prompt": lambda t: ai_mod.build_outline_prompt(
            t, slides=slides),
    }
    prompt = builders[prompt_name](text)

    cfg = _resolve_ai_config(model, api_base, api_key, timeout)
    client = ai_mod.AIClient(cfg)
    if not client.available:
        raise BeecmdError(
            f"AI 不可用：{client.unavailable_reason()}\n"
            "  本地 Ollama 示例：--api-base http://127.0.0.1:11434/v1 "
            "--model llama3.2（无需 Key）"
        )

    started = time.perf_counter()
    ok, result = client.chat(prompt, max_tokens=max_tokens)
    if not ok:
        raise BeecmdError(f"AI 调用失败：{client.last_error}")

    attempts = 1
    post_error = None
    try:
        payload = _postprocess_ai(task, result)
    except ValueError as e:
        payload = None
        post_error = e

    # 结构化任务（extract/outline）允许**一次**格式修复重试：
    # 小模型（如 llama3.2）经常差一个括号/少个标题，直接失败对用户体验太差；
    # 但绝不把修不好的内容当结果写盘。
    if payload is None and retry and task in ("extract", "outline"):
        repair = (
            ai_mod.build_extract_repair_prompt(result) if task == "extract"
            else ai_mod.build_outline_repair_prompt(result)
        )
        ok2, result2 = client.chat(repair, max_tokens=max_tokens)
        attempts = 2
        if ok2:
            result = result2
            try:
                payload = _postprocess_ai(task, result)
                post_error = None
            except ValueError as e:  # noqa: PERF203 - 单次重试，保持可读
                post_error = e
        else:
            post_error = ValueError(f"格式修复重试失败：{client.last_error}")

    elapsed_ms = (time.perf_counter() - started) * 1000
    out_path = Path(out) if out else src_path.with_name(
        f"{src_path.stem}.{task}.md"
    )
    out_path.parent.mkdir(parents=True, exist_ok=True)
    if payload is None:
        raw_path = out_path.with_name(out_path.name + ".raw.txt")
        try:
            raw_path.write_text(result, encoding="utf-8")
        except OSError:
            raw_path = None
        hint = f"；原始输出已保存到 {raw_path}" if raw_path else ""
        retried = "（已重试 1 次）" if attempts > 1 else ""
        raise BeecmdError(f"{post_error}{retried}{hint}；未写结果文件")

    out_path.write_text(payload + "\n", encoding="utf-8")
    retry_note = "，重试后通过" if attempts > 1 else ""
    print(f"✅ AI {task} 完成（{client.describe_source()}，"
          f"{elapsed_ms / 1000:.1f} s{retry_note}）→ {out_path}")

    if meta_json:
        meta = {
            "tool": "beecmd", "version": __version__, "op": "ai",
            "task": task, "src": str(src_path), "out": str(out_path),
            "model": cfg["model"], "api_base": cfg["api_base"],
            "source": client.last_source, "elapsed_ms": round(elapsed_ms, 1),
            "attempts": attempts,
        }
        meta_path = Path(meta_json)
        meta_path.parent.mkdir(parents=True, exist_ok=True)
        meta_path.write_text(
            json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(f"   元信息: {meta_path}")
    return EXIT_OK


# ==================== 命令：batch ====================

def cmd_batch(jobs_file: str, audit: Optional[str] = None) -> int:
    """
    批量执行任务（JSON 清单）。每条任务：
        {"op": "convert", "src": "a.xlsx", "to": "csv", "out": "a.csv"}
        {"op": "verify", "src": "a.xlsx", "artifact": "a.csv"}

    每条结果都写进审计流水（`audit.jsonl`，一行一条），**失败也记**。
    """
    # 用 utf-8-sig：PowerShell/记事本写的 JSON 常带 BOM
    # （这不是假设 —— 我第一次跑 batch 就撞上了 JSONDecodeError: Unexpected UTF-8 BOM）
    data = json.loads(Path(jobs_file).read_text(encoding="utf-8-sig"))
    jobs = data.get("jobs") if isinstance(data, dict) else data
    if not isinstance(jobs, list) or not jobs:
        raise BeecmdError("任务清单为空（应为 [{op:...}, ...] 或 {jobs:[...]}）")

    ok_count = 0
    audit_lines: List[dict] = []
    for index, job in enumerate(jobs, 1):
        op = str(job.get("op", "")).lower()
        started = _dt.datetime.now().isoformat(timespec="seconds")
        try:
            if op == "convert":
                code = cmd_convert(job["src"], job["to"],
                                   job.get("out"), job.get("sheet"))
            elif op == "merge":
                srcs = job.get("srcs") or job.get("src")
                if isinstance(srcs, str):
                    srcs = [srcs]
                code = cmd_merge(
                    srcs or [], job["out"],
                    mode=job.get("mode", "append"),
                    source_column=job.get("source_column", "来源文件"),
                    sheet_name=job.get("sheet_name", "汇总"),
                )
            elif op == "ai":
                code = cmd_ai(
                    job.get("task", "summarize"), job["src"],
                    out=job.get("out"),
                    model=job.get("model", ""),
                    api_base=job.get("api_base", ""),
                    api_key=job.get("api_key", ""),
                    timeout=int(job.get("timeout", 0) or 0),
                    max_points=int(job.get("max_points", 5)),
                    count=int(job.get("count", 8)),
                    length=int(job.get("length", 160)),
                    limit=int(job.get("limit", 10)),
                    slides=int(job.get("slides", 8)),
                    retry=bool(job.get("retry", True)),
                    meta_json=job.get("meta"),
                )
            elif op == "verify":
                code = cmd_verify(job["src"], job["artifact"],
                                  job.get("report"))
            else:
                raise BeecmdError(f"未知 op: {op!r}（只支持 convert / merge / verify）")
            ok = code in (EXIT_OK, EXIT_MISMATCH)
            # verify 的不一致 / 不可判定都不算"执行成功"
            if code in (EXIT_MISMATCH, EXIT_INCONCLUSIVE):
                ok = False
        except Exception as e:  # noqa: BLE001 - 单条失败不中断整批
            code, ok = EXIT_ERROR, False
            print(f"❌ 第 {index} 条失败: {e}", file=sys.stderr)
        if ok:
            ok_count += 1
        audit_lines.append({
            "ts": started,
            "index": index,
            "op": op,
            "job": job,
            "ok": ok,
            "exit_code": code,
        })

    if audit:
        audit_path = Path(audit)
        audit_path.parent.mkdir(parents=True, exist_ok=True)
        with audit_path.open("a", encoding="utf-8") as handle:
            for line in audit_lines:
                handle.write(json.dumps(line, ensure_ascii=False) + "\n")
        print(f"📝 审计流水已追加 {len(audit_lines)} 条 → {audit}")

    print(f"批量完成：{ok_count}/{len(jobs)} 条成功")
    return EXIT_OK if ok_count == len(jobs) else EXIT_ERROR


# ==================== 入口 ====================

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="beecmd",
        description="BeeOffice 无界面命令行：表格转换 / 保真校验 / 批量流水线",
    )
    parser.add_argument("--version", action="version",
                        version=f"beecmd {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    p_convert = sub.add_parser("convert", help="转换文件格式")
    p_convert.add_argument("src", help="源文件")
    p_convert.add_argument("--to", required=True,
                           help="目标格式：xlsx/csv/json/md/html/beshow"
                                "（+ v0.1: docx/pdf，仅限 Markdown 源）")
    p_convert.add_argument("-o", "--out", help="输出路径（默认同名换扩展名）")
    p_convert.add_argument("--sheet", help="指定工作表（表格转 csv/md/html 时用）")

    p_info = sub.add_parser("info", help="读出一个文件的工作表与尺寸")
    p_info.add_argument("src")

    p_merge = sub.add_parser(
        "merge", help="多表汇总：把多个表格文件合并成一个 xlsx"
    )
    p_merge.add_argument("srcs", nargs="+", help="源文件（至少 2 个）")
    p_merge.add_argument("-o", "--out", required=True, help="输出 xlsx 路径")
    p_merge.add_argument("--mode", choices=["append", "sheets"],
                         default="append",
                         help="append=按列纵向追加（默认）；sheets=每个表一个工作表")
    p_merge.add_argument("--source-column", default="来源文件",
                         help="append 模式追加的来源列名（默认：来源文件）")
    p_merge.add_argument("--sheet-name", default="汇总",
                         help="append 模式的输出工作表名（默认：汇总）")

    p_ai = sub.add_parser(
        "ai", help="对文本文件执行 AI 任务（总结/润色/关键词/续写）"
    )
    p_ai.add_argument("task", choices=sorted(AI_TASKS),
                      help="AI 任务：summarize/polish/keywords/continue")
    p_ai.add_argument("src", help="输入文本文件（.md/.txt 等）")
    p_ai.add_argument("-o", "--out", help="输出文件（默认 <源名>.<任务>.md）")
    p_ai.add_argument("--model", default="", help="模型名（本地 Ollama 例：llama3.2）")
    p_ai.add_argument("--api-base", default="",
                      help="OpenAI 兼容地址（本地：http://127.0.0.1:11434/v1）")
    p_ai.add_argument("--api-key", default="", help="云端服务 Key（本地不需要）")
    p_ai.add_argument("--timeout", type=int, default=0,
                      help="超时秒数（0 = 按本地/云端自动）")
    p_ai.add_argument("--max-points", type=int, default=5,
                      help="summarize 的要点条数上限")
    p_ai.add_argument("--count", type=int, default=8,
                      help="keywords 的关键词个数")
    p_ai.add_argument("--length", type=int, default=160,
                      help="continue 的续写字数提示")
    p_ai.add_argument("--limit", type=int, default=10,
                      help="extract 的抽取条数上限")
    p_ai.add_argument("--slides", type=int, default=8,
                      help="outline 的目标页数")
    p_ai.add_argument("--no-retry", action="store_true",
                      help="extract/outline 格式不合格时不自动重试一次")
    p_ai.add_argument("--meta", help="把调用元信息写入 JSON")

    p_verify = sub.add_parser("verify", help="对比源文件与产物，输出 JSON 报告")
    p_verify.add_argument("src")
    p_verify.add_argument("artifact")
    p_verify.add_argument("--report", help="报告输出路径（默认打印）")

    p_batch = sub.add_parser("batch", help="按 JSON 清单批量执行")
    p_batch.add_argument("jobs", help="任务清单 JSON")
    p_batch.add_argument("--audit", help="审计流水 JSONL 输出路径")

    return parser


def main(argv: Optional[List[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        if args.command == "convert":
            return cmd_convert(args.src, args.to, args.out, args.sheet)
        if args.command == "info":
            return cmd_info(args.src)
        if args.command == "merge":
            return cmd_merge(
                args.srcs, args.out, mode=args.mode,
                source_column=args.source_column,
                sheet_name=args.sheet_name,
            )
        if args.command == "verify":
            return cmd_verify(args.src, args.artifact, args.report)
        if args.command == "ai":
            return cmd_ai(
                args.task, args.src, out=args.out,
                model=args.model, api_base=args.api_base,
                api_key=args.api_key, timeout=args.timeout,
                max_points=args.max_points, count=args.count,
                length=args.length, limit=args.limit, slides=args.slides,
                retry=not args.no_retry,
                meta_json=args.meta,
            )
        if args.command == "batch":
            return cmd_batch(args.jobs, args.audit)
    except BeecmdError as e:
        print(f"❌ {e}", file=sys.stderr)
        return EXIT_ERROR
    except KeyboardInterrupt:
        return EXIT_ERROR
    except Exception as e:  # noqa: BLE001 - 未预料的错误也要**干净**报错，别甩 traceback
        # 实测：损坏的 .pptx 会抛 python-pptx 的 PackageNotFoundError，
        # 原先直接 traceback 甩给用户（exit 1 但体验很差）。
        print(f"❌ 处理失败：{type(e).__name__}: {e}", file=sys.stderr)
        print("   （如果是 .pptx，请确认文件完好、未被加密/占用）",
              file=sys.stderr)
        return EXIT_ERROR
    parser.print_help()
    return EXIT_ERROR


if __name__ == "__main__":
    sys.exit(main())
