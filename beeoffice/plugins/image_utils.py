# beeoffice/plugins/image_utils.py
"""
图片处理工具（优化规划 §3.3 消重）

集中三件原先散落多处的逻辑：

1. **图片引用规范化** —— `file:///C:/a.png`、`%20` 转义、前后空白
   （原先 `bee_export._resolve_image_path` 自行处理，其余实现完全不处理）
2. **相对路径的多基准目录兜底解析** —— 原先在
   `beewrite_export_mixin._resolve_image_path_for_export()` 与
   `beewrite_rich_editor._insert_image_by_path()` 里各有一份**形态相同**的实现
   （候选去重保序 → `base / name` → 第一个存在的 → 记录 tried_paths）
3. **遍历文档里的内联图片** —— 原先 4 处重复
   "遍历 block → fragment → `charFormat().isImageFormat()`"

设计取舍：**候选目录的来源留在调用方**（各自才知道自己的文档状态：导出侧看
`_current_file_path`/`get_current_file_dir()`，编辑器侧看 parent 链），
本模块只负责**算法**。因此不需要把 Qt 控件塞进来，纯逻辑可测。
"""

import logging
from pathlib import Path
from urllib.parse import unquote, urlparse


def normalize_image_ref(ref) -> str:
    """
    把图片引用规范化成本地路径字符串。

    - `file:///C:/a/b.png` → `C:/a/b.png`（去掉盘符前的斜杠）
    - `%20` 等百分号转义 → 原字符
    - 去掉前后空白

    http(s) 引用原样返回（本地解析不到，由调用方决定怎么提示）。

    :param ref: 原始引用（可能是 str / Path）
    :return: 规范化后的字符串（空输入返回空串）
    """
    if not ref:
        return ""
    text = str(ref).strip()
    if not text:
        return ""

    lowered = text.lower()

    # 关键：**不要无条件用 urlparse**。Windows 盘符是单字母 + 冒号，
    # urlparse("D:\\a\\b.png") 会把 "d" 当成 scheme、path 变成 "\\a\\b.png"，
    # 盘符被丢掉（实测该回归：绝对路径解析失败 → 导出 DOCX 里图片消失）。
    # 因此只在真的是 URL 时才交给 urlparse。
    if lowered.startswith(("http://", "https://")):
        return text

    if lowered.startswith("file:"):
        raw = unquote(urlparse(text).path or "")
        # file:///C:/dir/x.png 的 parsed.path 是 /C:/dir/x.png
        if raw.startswith("/") and len(raw) > 2 and raw[2] == ":":
            raw = raw[1:]
        return raw

    # 普通路径：只需处理百分号转义
    return unquote(text)


def resolve_image_path(name, base_dirs=(), *, home_fallback=True):
    """
    解析图片路径，返回 `(resolved_path_or_None, tried_paths)`。

    行为与抽取前的两份实现保持一致：

    - **绝对路径**：只尝试它自己；不存在即失败（不会退到 `base_dirs`/home，
      避免在无关目录里"碰运气"拼出同名文件）
    - **相对路径**：按 `base_dirs` 顺序（去重、保序）逐个试 `base / name`，
      最后（`home_fallback=True` 时）再试 `Path.home() / name`
    - `tried_paths` 记录所有尝试过的候选，供日志与"图片缺失"占位提示使用

    :param name: 图片路径/引用
    :param base_dirs: 候选基准目录（可为 None 项，自动跳过）
    :param home_fallback: 是否以用户主目录作为最后兜底
    :return: (Path 或 None, list[str])
    """
    tried = []
    if not name:
        return None, tried

    normalized = normalize_image_ref(name)
    if not normalized:
        return None, tried

    path = Path(normalized)
    if path.is_absolute():
        tried.append(str(path))
        return (path if path.exists() else None), tried

    candidates = []
    for d in base_dirs or ():
        if d:
            candidates.append(str(d))
    if home_fallback:
        candidates.append(str(Path.home()))

    seen = set()
    for base in candidates:
        if base in seen:
            continue
        seen.add(base)
        try:
            candidate = Path(base) / normalized
        except Exception:
            continue
        tried.append(str(candidate))
        if candidate.exists():
            return candidate, tried

    return None, tried


def iter_block_images(block):
    """
    遍历**单个 block** 里的内联图片，产出 `QTextImageFormat`。

    编辑器侧多处只需按 block 判断/取值（例如"该 block 是否含图片"），
    因此单独提供 block 级接口；文档级见 `iter_image_formats()`。

    :param block: QTextBlock
    :return: 生成器，元素为 QTextImageFormat
    """
    it = block.begin()
    while not it.atEnd():
        frag = it.fragment()
        if frag.isValid():
            fmt = frag.charFormat()
            if fmt.isImageFormat():
                try:
                    yield fmt.toImageFormat()
                except Exception as e:
                    logging.debug(f"读取图片格式失败: {e}")
        it += 1


def iter_image_formats(document):
    """
    遍历**整个文档**里的内联图片。

    原先多处各自重复同一套遍历：
        block = doc.begin()
        while block.isValid():
            it = block.begin()
            while not it.atEnd():
                if it.fragment().charFormat().isImageFormat(): ...

    产出 `(QTextImageFormat, block_position)`：
      - `QTextImageFormat` 便于取 `name()`（路径）与宽高
      - `block_position` 便于定位（与 `QTextBlock.position()` 同语义）

    :param document: QTextDocument
    :return: 生成器
    """
    block = document.begin()
    while block.isValid():
        for img in iter_block_images(block):
            yield img, block.position()
        block = block.next()
