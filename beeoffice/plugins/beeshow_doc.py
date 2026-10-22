# beeoffice/plugins/beeshow_doc.py
"""
蜜演文稿的**文件格式与读写**（纯逻辑，不依赖 Qt —— 便于完整测试）。

## 为什么需要它（审计报告 §2.7）
蜜演原先**没有保存链路**：`def save`/`save_as`/`content` 全为 0，
`app._save_current` 的两个分支都不命中 → **Ctrl+S 毫无反应、也没有任何提示**；
"历史版本"只在内存里（50 条），导出件是 PPTX/PDF/HTML，**回不到编辑器**。
后果是小公司/普通人最容易踩的：**做了一上午的演示，关掉标签就再也改不了**。

## 格式选择（`.beshow`）
蜜演的"源"本来就是 **Markdown**（编辑器里按 `---` 分页，`_update_preview`
把它渲染成幻灯片）。所以最诚实的保存格式就是**把这份 Markdown 存下来**，
用一个自己的扩展名 `.beshow` 与之绑定：

* 内容是**纯 Markdown**（人是可读的、可用别的编辑器打开、也方便排查）；
* 头部加一行注释标记（`<!-- beeshow-deck v1 -->`）——
  Markdown 注释在渲染时被忽略，所以不影响任何解析；
  同时让"这到底是不是蜜演文稿"可以**明确判断**，而不是靠猜扩展名；
* **原子写**（先写 `.tmp` 再 `os.replace`）：保存过程被打断不会留半份文件
  （这条沿用 `backup.py`/`settings.py` 的既有做法）。

## 兼容旧数据
早期"AI 模板/导入"等路径可能直接把 Markdown 写进 `.md`。
`load()` 对**没有标记的文件**也照常返回内容（宽松读取），
只有 `is_deck_file()` 才严格要求标记——这样不会出现"以前存的打不开"。
"""
import json
import logging
import os
import re
from pathlib import Path
from typing import Optional

#: 蜜演文稿扩展名
DECK_EXTENSION = ".beshow"
#: 文稿标记（Markdown 注释，渲染时被忽略；用于识别"这确实是蜜演文稿"）
DECK_MARKER = "<!-- beeshow-deck v1 -->"
#: 允许被识别的历史标记（将来改版本号时留兼容位）
KNOWN_MARKERS = (DECK_MARKER,)
#: 排练计时元数据（Markdown 注释，渲染时忽略；2026-10-22 4.6）
REHEARSAL_PREFIX = "<!-- beeshow-rehearsal:"


def serialize(text: str, rehearsal=None) -> str:
    """
    把编辑器里的 Markdown 变成"要写盘的内容"（幂等：已有标记则不重复加）。

    `rehearsal`：可选的 `{页序号: 秒数}` 排练计时；写进 marker 后的 Markdown
    注释里（不进正文、渲染被忽略），供下次打开恢复。
    """
    body = text or ""
    meta = ""
    if rehearsal:
        try:
            payload = json.dumps(
                {"page_seconds": {
                    str(k): round(float(v), 2)
                    for k, v in dict(rehearsal).items()
                }},
                ensure_ascii=False, separators=(",", ":"),
            )
            meta = f"{REHEARSAL_PREFIX}{payload} -->\n"
        except Exception:  # noqa: BLE001 - 元数据失败不影响正文保存
            meta = ""
    if body.lstrip().startswith(KNOWN_MARKERS):
        # 已有 marker：把新 meta 插到 marker 行后（去重旧 meta）
        body = strip_rehearsal_meta(body)
        first_newline = body.find("\n")
        if first_newline < 0:
            return body + "\n" + meta
        return body[:first_newline + 1] + meta + body[first_newline + 1:]
    return f"{DECK_MARKER}\n{meta}\n{body}"


def strip_rehearsal_meta(text: str) -> str:
    """去掉排练计时元数据注释（保留正文与 marker）。"""
    if not text:
        return ""
    lines = []
    for line in str(text).splitlines(keepends=True):
        if line.lstrip().startswith(REHEARSAL_PREFIX):
            continue
        lines.append(line)
    return "".join(lines)


def strip_marker(text: str) -> str:
    """去掉文稿标记 + 排练计时元数据，返回纯 Markdown（读入编辑器时用）。"""
    if not text:
        return ""
    stripped = strip_rehearsal_meta(text).lstrip()
    for marker in KNOWN_MARKERS:
        if stripped.startswith(marker):
            return stripped[len(marker):].lstrip("\r\n")
    return stripped


def has_marker(text: str) -> bool:
    """文本是否带蜜演文稿标记。"""
    return bool(text) and text.lstrip().startswith(KNOWN_MARKERS)


def is_deck_file(path) -> bool:
    """按扩展名判断是否是蜜演文稿。"""
    try:
        return str(path).lower().endswith(DECK_EXTENSION)
    except Exception:  # noqa: BLE001
        return False


def save_deck(path, text: str, rehearsal=None) -> bool:
    """
    把文稿写入 `path`（**原子写**）。

    :return: 成功 True；失败 False 且**不留下半份文件**（与 `backup.py` 同策略）
    """
    target = Path(path)
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
    except Exception as e:  # noqa: BLE001
        logging.error(f"[蜜演] 创建目录失败 {target.parent}: {e}")
        return False

    payload = serialize(text, rehearsal=rehearsal)
    temp = target.with_suffix(target.suffix + ".tmp")
    try:
        temp.write_text(payload, encoding="utf-8")
        os.replace(temp, target)
        return True
    except Exception as e:  # noqa: BLE001
        logging.error(f"[蜜演] 保存文稿失败 {target}: {e}")
        try:
            temp.unlink(missing_ok=True)
        except OSError:
            pass
        return False


def load_rehearsal(path) -> dict:
    """读取文稿里的排练计时元数据 `{页序号(int): 秒数(float)}`。"""
    try:
        raw = Path(path).read_text(encoding="utf-8")
    except Exception:  # noqa: BLE001
        return {}
    match = re.search(
        re.escape(REHEARSAL_PREFIX) + r"(.+?)\s*-->", raw, re.S
    )
    if not match:
        return {}
    try:
        payload = json.loads(match.group(1).strip())
        seconds = payload.get("page_seconds", {})
        return {int(k): float(v) for k, v in seconds.items()}
    except Exception:  # noqa: BLE001
        return {}


def load_deck(path) -> Optional[str]:
    """
    读取文稿（**宽松**：没有标记的普通 Markdown 也照常返回）。

    :return: Markdown 文本；读取失败返回 None（调用方据此提示，而不是静默空文稿）
    """
    try:
        text = Path(path).read_text(encoding="utf-8")
    except Exception as e:  # noqa: BLE001
        logging.error(f"[蜜演] 读取文稿失败 {path}: {e}")
        return None
    return strip_marker(text)


def suggested_filename(title: str = "") -> str:
    """
    根据首行标题给一个文件名建议（非法字符替换掉，与蜜写保持一致）。
    """
    name = (title or "").strip().splitlines()[0] if title else ""
    name = name.lstrip("#").strip()[:50] or "未命名演示"
    for ch in '<>:"/\\|?*':
        name = name.replace(ch, "")
    return f"{name}{DECK_EXTENSION}"
