# tools/audit_pdf_fitz.py
"""扫描 PyMuPDF/fitz 调用，生成可执行的 PDF 后端迁移映射表。

用法：
    python tools/audit_pdf_fitz.py
    python tools/audit_pdf_fitz.py --markdown docs/PDF后端迁移映射-2026-11-03.md
"""
from __future__ import annotations

import argparse
import ast
import re
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCAN_DIRS = ("beeoffice", "tools", "tests")

#: fitz 直接调用 → 替代方案
REPLACEMENTS = {
    "open": ("pypdf.PdfReader / pypdfium2.PdfDocument", "低"),
    "Document": ("pypdf.PdfReader / PdfWriter", "低"),
    "Rect": ("pypdf.generic.RectangleObject", "低"),
    "Page": ("pypdf.PageObject / pypdfium2 page", "中"),
    "Pixmap": ("pypdfium2 render().to_pil()", "低"),
    "new_page": ("pypdf.PdfWriter.add_blank_page", "低"),
    "insert_text": ("reportlab canvas.drawString（叠加层）", "中"),
    "get_text": ("pypdfium2 textpage / pypdf extract_text", "低"),
    "get_textpage": ("pypdfium2 textpage", "低"),
    "get_pixmap": ("pypdfium2 page.render()", "低"),
    "set_cropbox": ("pypdf page.cropbox = RectangleObject", "低"),
    "rotation": ("pypdf page.rotate", "低"),
    "mediabox": ("pypdf page.mediabox", "低"),
    "rect": ("pypdf page.mediabox", "低"),
    "load_page": ("reader.pages[i]", "低"),
    "insert_pdf": ("PdfWriter.append(reader, pages=...)", "中"),
    "delete_page": ("PdfWriter 重建页面列表", "中"),
    "save": ("PdfWriter.write(path)", "低"),
    "tobytes": ("BytesIO + PdfWriter.write", "低"),
    "get_toc": ("PdfReader.outline", "中"),
    "set_toc": ("PdfWriter.add_outline_item", "中"),
    "encrypt": ("PdfWriter.encrypt", "低"),
    "metadata": ("PdfReader.metadata", "低"),
    "get_images": ("pypdf page.images", "中"),
    "extract_image": ("pypdf page.images[].data", "中"),
    "insert_image": ("reportlab drawImage（叠加层）", "中"),
    "add_annot": ("pypdf 注释写入受限；需叠加层/延后", "高"),
    "annots": ("pypdf 注释读取受限；需叠加层/延后", "高"),
    "subset_fonts": ("移除；压缩策略改为 pypdf 重写", "中"),
    "close": ("PdfReader/PdfiumDocument.close", "低"),
}

#: 在 fitz 文件中出现的 doc/page 方法（候选清单，需人工确认）
DOC_PAGE_METHODS = {
    "load_page", "insert_pdf", "delete_page", "save", "tobytes",
    "get_toc", "set_toc", "encrypt", "metadata", "subset_fonts",
    "close", "new_page", "insert_text", "get_text", "get_textpage",
    "get_pixmap", "set_cropbox", "insert_image", "add_annot", "annots",
    "get_images", "extract_image", "rotation",
}


@dataclass
class Hit:
    file: str
    line: int
    func: str
    expression: str
    replacement: str
    risk: str
    kind: str


def _enclosing_func(tree: ast.AST) -> dict[int, str]:
    result: dict[int, str] = {}
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            for ln in range(node.lineno,
                            getattr(node, "end_lineno", node.lineno) + 1):
                result[ln] = node.name
    return result


def scan_file(path: Path) -> list[Hit]:
    text = path.read_text(encoding="utf-8", errors="ignore")
    if not re.search(r"(?m)^\s*(import fitz|from fitz import)", text):
        return []
    try:
        tree = ast.parse(text)
        funcs = _enclosing_func(tree)
    except SyntaxError:
        funcs = {}
    lines = text.splitlines()
    hits: list[Hit] = []
    for i, line in enumerate(lines, 1):
        for m in re.finditer(r"\bfitz\.([A-Za-z_]\w*)", line):
            attr = m.group(1)
            repl, risk = REPLACEMENTS.get(attr, ("人工映射", "中"))
            hits.append(Hit(
                str(path.relative_to(ROOT)), i, funcs.get(i, "?"),
                line.strip(), repl, risk, "fitz 直接调用",
            ))
        # doc/page 方法候选
        for m in re.finditer(r"\b(?:doc|page|reader|writer)\.([A-Za-z_]\w*)\s*\(", line):
            attr = m.group(1)
            if attr not in DOC_PAGE_METHODS:
                continue
            repl, risk = REPLACEMENTS.get(attr, ("人工映射", "中"))
            hits.append(Hit(
                str(path.relative_to(ROOT)), i, funcs.get(i, "?"),
                line.strip(), repl, risk, "doc/page 方法候选",
            ))
    return hits


def imported_files() -> list[str]:
    result = []
    for d in SCAN_DIRS:
        for path in (ROOT / d).rglob("*.py"):
            text = path.read_text(encoding="utf-8", errors="ignore")
            if re.search(r"(?m)^\s*(import fitz|from fitz import)", text):
                result.append(str(path.relative_to(ROOT)))
    return sorted(result)


def build_markdown(hits: list[Hit], imported: list[str] | None = None) -> str:
    files = sorted({h.file for h in hits})
    imported = imported or []
    direct = [h for h in hits if h.kind == "fitz 直接调用"]
    candidates = [h for h in hits if h.kind != "fitz 直接调用"]
    risks = {"低": 0, "中": 0, "高": 0}
    for h in hits:
        risks[h.risk] = risks.get(h.risk, 0) + 1
    out = [
        "# PDF 后端迁移映射表（PyMuPDF → pypdfium2/pypdf）",
        "",
        "> 自动生成：`python tools/audit_pdf_fitz.py`",
        f"> 涉及文件：{len(files)} 个（直接调用）；"
        f"含仅 import 文件共 {len(imported)} 个；fitz 直接调用：{len(direct)} 处；"
        f"doc/page 方法候选：{len(candidates)} 处；"
        f"风险分布：低 {risks.get('低', 0)} / 中 {risks.get('中', 0)} / 高 {risks.get('高', 0)}",
        "",
        "> **运行时状态（B2h）**：`beeoffice/` 下已无 fitz import；",
        "> 下列残留仅存在于 tests/tools（开发校验），运行时不依赖 PyMuPDF。",
        "",
        "## 文件清单",
        "",
    ]
    out += [f"- 直接调用：`{f}`" for f in files]
    only_import = [f for f in imported if f not in files]
    if only_import:
        out += ["", "### 仅 import/可选依赖（不需改调用，但要去依赖）", ""]
        out += [f"- `{f}`" for f in only_import]
    out += ["", "## fitz 直接调用（必须替换）", "",
            "| 文件 | 行 | 函数 | 当前表达式 | 建议替代 | 风险 |",
            "|---|---:|---|---|---|---|"]
    for h in sorted(direct, key=lambda x: (x.file, x.line)):
        expr = h.expression.replace("|", "\\|")[:160]
        out.append(
            f"| `{h.file}` | {h.line} | `{h.func}` | `{expr}` | "
            f"{h.replacement} | {h.risk} |"
        )
    out += ["", "## doc/page 方法候选（需按调用上下文确认）", "",
            "| 文件 | 行 | 函数 | 当前表达式 | 建议替代 | 风险 |",
            "|---|---:|---|---|---|---|"]
    for h in sorted(candidates, key=lambda x: (x.file, x.line))[:120]:
        expr = h.expression.replace("|", "\\|")[:160]
        out.append(
            f"| `{h.file}` | {h.line} | `{h.func}` | `{expr}` | "
            f"{h.replacement} | {h.risk} |"
        )
    out += ["", "## 迁移顺序", "",
            "1. 先做 `beeoffice/pdf_backend.py` 适配层，禁止上层直接 import fitz；",
            "2. 先迁移页面结构操作（合并/拆分/旋转/裁剪/删除/插入/替换）；",
            "3. 再迁移文本/图片提取与渲染；",
            "4. 最后迁移批注/签名/水印（高风险，允许降级）；",
            "5. 全量测试通过后删除 PyMuPDF 依赖与所有 import。"]
    return "\n".join(out) + "\n"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--markdown", type=Path, default=None)
    args = ap.parse_args()
    hits: list[Hit] = []
    for d in SCAN_DIRS:
        for p in (ROOT / d).rglob("*.py"):
            hits.extend(scan_file(p))
    md = build_markdown(hits, imported_files())
    if args.markdown:
        args.markdown.parent.mkdir(parents=True, exist_ok=True)
        args.markdown.write_text(md, encoding="utf-8")
        print(f"wrote {args.markdown} "
              f"(fitz={sum(1 for h in hits if h.kind == 'fitz 直接调用')}, "
              f"methods={sum(1 for h in hits if h.kind != 'fitz 直接调用')})")
    else:
        print(md)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
