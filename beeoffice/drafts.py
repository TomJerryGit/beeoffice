# beeoffice/drafts.py
"""
未保存内容的**草稿**存取（P0-5：崩溃恢复的"读取端"）。

## 修的是什么
审计发现"自动保存有写无读"，更准确地说：`app._autosave()` 只对
**已有文件路径**的文档 `save()`，所以**新建但没保存过**的文档
（`_current_file_path is None`）在崩溃时会**整份丢失** —— 没有任何地方留着它。
本模块给这类内容一个落点，并在下次启动时**列出、恢复或丢弃**。

## 设计：草稿 = 草稿目录里**带原生扩展名的真实文件**
* 蜜写 → `.md`、蜜算 → `.xlsx`、蜜演 → `.beshow`
* 因此"恢复"可以直接复用**已有的打开分流**（`_open_recent` → 按扩展名派发），
  **不新增文件格式**、也不需要新的反序列化代码。
* 每个草稿配一个 `.meta.json`（时间、模块、标题、原路径）—— 用于在提示里
  说清"这是什么"，而不是让用户面对一堆随机文件名。

## 安全与整洁
* **原子写**（先写 `.tmp` 再 `os.replace`），避免半截文件；
* 草稿目录与真实文件**分离**（默认 `~/.beeoffice_drafts`），不会混进用户的项目目录；
* `BEEOFFICE_DRAFT_DIR` 环境变量可覆盖（测试用）；
* `cleanup_stale()` 清理超过 N 天的旧草稿（崩溃后没人认领的）。
"""
from __future__ import annotations

import json
import os
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional

#: 模块 → 草稿扩展名（恢复时靠它走既有的打开分流）
KIND_EXTENSIONS: Dict[str, str] = {
    "doc": ".md",
    "sheet": ".xlsx",
    "show": ".beshow",
}

#: 元信息文件名后缀
META_SUFFIX = ".meta.json"
#: 默认保留天数
DEFAULT_MAX_AGE_DAYS = 7


def drafts_dir() -> Path:
    """
    草稿根目录（可用 `BEEOFFICE_DRAFT_DIR` 覆盖，测试/便携部署用）。

    ⚠️ **绝不抛异常**：home 只读、或路径被一个同名文件占住时，
    创建目录会失败。原先这里直接 `mkdir()` → 启动时的草稿检查会抛
    `FileExistsError`/`PermissionError`（实测过），把"恢复"变成"启动报错"。
    现在失败就返回路径本身，调用方（`list_drafts`/`record`）各自容错。
    """
    override = os.environ.get("BEEOFFICE_DRAFT_DIR", "").strip()
    root = Path(override) if override else Path.home() / ".beeoffice_drafts"
    try:
        root.mkdir(parents=True, exist_ok=True)
    except OSError:
        pass          # 目录不可用 → 后续读取/写入各自兜底，不在初始化时炸
    return root


@dataclass
class DraftEntry:
    """一条草稿（文件 + 元信息）。"""

    path: Path
    kind: str
    created: float
    title: str = ""
    source: str = ""

    @property
    def age_days(self) -> float:
        return max(0.0, (time.time() - self.created) / 86400)

    def display_time(self) -> str:
        try:
            return time.strftime("%Y-%m-%d %H:%M", time.localtime(self.created))
        except Exception:  # noqa: BLE001
            return ""


def extension_for(kind: str) -> str:
    if kind not in KIND_EXTENSIONS:
        raise ValueError(f"未知草稿类型: {kind!r}（可选: {sorted(KIND_EXTENSIONS)}）")
    return KIND_EXTENSIONS[kind]


def new_draft_path(kind: str) -> Path:
    """给一条新草稿分配路径（文件名含时间戳，便于人工辨认）。"""
    ext = extension_for(kind)
    stamp = time.strftime("%Y%m%d-%H%M%S")
    return drafts_dir() / f"draft-{kind}-{stamp}-{uuid.uuid4().hex[:6]}{ext}"


def meta_path(draft: Path) -> Path:
    return draft.with_name(draft.name + META_SUFFIX)


def record(draft: Path, *, kind: str, title: str = "",
           source: str = "", created: Optional[float] = None) -> bool:
    """写元信息（原子写）。写不了（只读目录/磁盘满）返回 False，**不抛异常**。"""
    payload = {
        "kind": kind,
        "title": title,
        "source": source,
        "created": created if created is not None else time.time(),
    }
    target = meta_path(Path(draft))
    tmp = target.with_name(target.name + ".tmp")
    try:
        tmp.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        os.replace(tmp, target)
        return True
    except OSError:
        try:
            tmp.unlink(missing_ok=True)
        except OSError:
            pass
        return False


def discard(draft) -> bool:
    """删除一条草稿（连同元信息）。返回是否删掉了主文件。"""
    path = Path(draft)
    removed = False
    for target in (path, meta_path(path)):
        try:
            if target.is_file():
                target.unlink()
                removed = removed or target == path
        except OSError:
            pass
    return removed


def list_drafts(max_age_days: Optional[float] = None) -> List[DraftEntry]:
    """
    列出草稿（按创建时间倒序）。目录不可用/读不了时返回**空列表**，不抛异常。

    :param max_age_days: 只返回这个天数以内的（None = 全部）
    """
    entries: List[DraftEntry] = []
    try:
        candidates = list(drafts_dir().glob("draft-*"))
    except OSError:
        return entries
    for path in candidates:
        if path.name.endswith(META_SUFFIX) or path.suffix == ".tmp":
            continue
        if not path.is_file():
            continue
        meta: Dict = {}
        try:
            meta_file = meta_path(path)
            if meta_file.is_file():
                meta = json.loads(meta_file.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001 - 元信息坏了不该让整条草稿消失
            meta = {}
        kind = str(meta.get("kind") or _kind_from_name(path))
        created = float(meta.get("created") or path.stat().st_mtime)
        entry = DraftEntry(path=path, kind=kind, created=created,
                           title=str(meta.get("title") or ""),
                           source=str(meta.get("source") or ""))
        if max_age_days is not None and entry.age_days > max_age_days:
            continue
        entries.append(entry)
    entries.sort(key=lambda e: e.created, reverse=True)
    return entries


def _kind_from_name(path: Path) -> str:
    """元信息缺失时从文件名猜类型（`draft-sheet-...`）。"""
    parts = path.stem.split("-")
    if len(parts) >= 2 and parts[0] == "draft":
        candidate = parts[1]
        if candidate in KIND_EXTENSIONS:
            return candidate
    return "doc"


def cleanup_stale(max_age_days: float = DEFAULT_MAX_AGE_DAYS) -> int:
    """清理过期草稿，返回清理条数。"""
    removed = 0
    for entry in list_drafts():
        if entry.age_days > max_age_days:
            if discard(entry.path):
                removed += 1
    return removed


def describe(entry: DraftEntry) -> str:
    """一句话描述一条草稿（给对话框用）。"""
    kind_name = {"doc": "文档", "sheet": "表格", "show": "演示"}.get(
        entry.kind, entry.kind
    )
    title = entry.title.strip() or entry.path.stem
    return f"{kind_name}「{title}」 · {entry.display_time()}"
