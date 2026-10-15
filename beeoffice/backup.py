# beeoffice/backup.py
"""
**本地备份与恢复**（R6）。

## 为什么做这个
WPS 有"备份中心"（可回到历史版本）。我们原先只有 5 分钟自动保存
（`AUTOSAVE_INTERVAL_MS`）——**用户看不到、也没法回到上一版**，
而且自动保存是**直接覆盖**：保存写坏了就真的没了。

本地软件做这件事的成本很低（不需要云），而收益很直接：
**任何一次覆盖保存之前，先留一份**，用户随时能回去。

## 设计（几条刻意的取舍）
* **备份在"覆盖前"做**：`_autosave` 与手动保存都会先调 `create()`。
  这样备份的是**上一个好状态**，而不是刚写坏的内容。
* **原子写**：先写 `.tmp` 再 `os.replace` —— 备份本身绝不能被中断留半份。
* **轮转有上限**：每个文件保留 `keep` 份 + 全局总容量上限，
  超了按**最旧优先**清理。备份功能不能变成吃磁盘的怪物。
* **目录不可写就快速失败**：返回 `None` 并只记一次日志（沿用 R7 的教训，
  不要每份文件各失败一次）。
* **本模块不依赖 Qt**：便于单独测试；界面在 `backup_center.py`。
"""
import logging
import os
import re
import shutil
import time
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

#: 每个文件默认保留多少份
DEFAULT_KEEP = 10
#: 备份总容量上限（字节）—— 超过就按最旧优先清理
DEFAULT_MAX_TOTAL_BYTES = 512 * 1024 * 1024      # 512 MB
#: 备份根目录名（放在用户主目录下，与会话设置同级）
BACKUP_ROOT_NAME = ".beeoffice_backups"

#: 备份文件名：`<原名>__<时间戳>__<原因>.<扩展名>`
#: 时间戳可排序（`%Y%m%d-%H%M%S`），因此"最新一份"可直接取字典序最大者。
_STAMP_FMT = "%Y%m%d-%H%M%S"
_NAME_RE = re.compile(
    r"^(?P<stem>.+?)__(?P<stamp>\d{8}-\d{6})(?:_(?P<seq>\d+))?"
    r"__(?P<reason>[a-z_]+)(?P<ext>\.[^.]+)?$"
)


@dataclass
class BackupVersion:
    """一份备份。"""

    path: Path
    source: str          # 原文件路径
    stamp: str           # 时间戳字符串
    reason: str          # before_save / auto / manual
    size: int

    @property
    def mtime(self) -> float:
        try:
            return self.path.stat().st_mtime
        except OSError:
            return 0.0

    def display_time(self) -> str:
        return self.stamp

    def size_text(self) -> str:
        size = float(self.size)
        for unit in ("B", "KB", "MB", "GB"):
            if size < 1024 or unit == "GB":
                return f"{size:.0f} {unit}" if unit == "B" else f"{size:.1f} {unit}"
            size /= 1024
        return f"{size:.1f} GB"


def default_backup_root() -> Path:
    """默认备份根目录（`~/.beeoffice_backups`，与会话设置同级）。"""
    return Path.home() / BACKUP_ROOT_NAME


class BackupStore:
    """备份仓库：创建 / 列出 / 恢复 / 轮转清理。"""

    def __init__(self, root: Optional[Path] = None,
                 keep: int = DEFAULT_KEEP,
                 max_total_bytes: int = DEFAULT_MAX_TOTAL_BYTES):
        self.root = Path(root) if root is not None else default_backup_root()
        self.keep = max(1, int(keep))
        self.max_total_bytes = max(0, int(max_total_bytes))
        self._warned = False

    # ------------------------------------------------------------------
    # 路径
    # ------------------------------------------------------------------
    def folder_for(self, source) -> Path:
        """
        某个源文件对应的备份目录。

        用"路径哈希 + 可读名字"：同名的不同文件不会互相覆盖，
        而用户也能从目录名看出是哪个文件。
        """
        import hashlib

        source = Path(source)
        digest = hashlib.sha1(
            str(source).encode("utf-8", "ignore")
        ).hexdigest()[:8]
        safe = re.sub(r"[^\w\u4e00-\u9fff.-]+", "_", source.stem)[:40]
        return self.root / f"{safe}-{digest}"

    def _writeable(self) -> bool:
        """备份根目录能不能写（**一次判定**，不要每份文件各失败一次）。"""
        try:
            self.root.mkdir(parents=True, exist_ok=True)
            probe = self.root / ".write_probe"
            probe.write_text("ok", encoding="utf-8")
            probe.unlink(missing_ok=True)
            return True
        except Exception as e:  # noqa: BLE001
            if not self._warned:
                self._warned = True
                logging.warning(f"[备份] 备份目录不可写，本次不备份：{e}")
            return False

    # ------------------------------------------------------------------
    # 创建
    # ------------------------------------------------------------------
    def create(self, source, reason: str = "before_save",
               now: Optional[float] = None) -> Optional[Path]:
        """
        为 `source` 创建一份备份。

        :return: 备份文件路径；源文件不存在、或目录不可写时返回 `None`
            （**不抛异常** —— 备份失败不该阻断用户的保存）
        """
        source = Path(source)
        if not source.is_file():
            return None
        if not self._writeable():
            return None

        stamp = time.strftime(_STAMP_FMT, time.localtime(now))
        folder = self.folder_for(source)
        try:
            folder.mkdir(parents=True, exist_ok=True)
        except Exception as e:  # noqa: BLE001
            logging.warning(f"[备份] 无法创建备份目录：{e}")
            return None

        # 同一秒内可能备份多次（例如"立即备份"连点）→ 加序号避免互相覆盖
        seq = 0
        target = folder / f"{source.stem}__{stamp}__{reason}{source.suffix}"
        while target.exists():
            seq += 1
            target = folder / (
                f"{source.stem}__{stamp}_{seq}__{reason}{source.suffix}"
            )

        temp = target.with_suffix(target.suffix + ".tmp")
        try:
            shutil.copy2(source, temp)
            os.replace(temp, target)      # 原子：要么没有，要么完整
        except Exception as e:  # noqa: BLE001
            logging.warning(f"[备份] 复制失败：{e}")
            try:
                temp.unlink(missing_ok=True)
            except OSError:
                pass
            return None

        self.prune()
        return target

    # ------------------------------------------------------------------
    # 列出 / 恢复 / 删除
    # ------------------------------------------------------------------
    def list_versions(self, source) -> List[BackupVersion]:
        """列出某个源文件的备份，**新的在前**。"""
        return self._collect(self.folder_for(Path(source)))

    def list_all(self) -> List[BackupVersion]:
        """列出所有备份，新的在前。"""
        return self._collect(self.root)

    def _collect(self, folder: Path) -> List[BackupVersion]:
        versions: List[BackupVersion] = []
        if not folder.is_dir():
            return versions
        for path in folder.rglob("*"):
            if not path.is_file() or path.name.endswith(".tmp"):
                continue
            match = _NAME_RE.match(path.name)
            if not match:
                continue
            try:
                size = path.stat().st_size
            except OSError:
                continue
            versions.append(BackupVersion(
                path=path,
                source=self._source_hint(path),
                stamp=match.group("stamp"),
                reason=match.group("reason"),
                size=size,
            ))
        versions.sort(key=lambda v: (v.stamp, v.path.name), reverse=True)
        return versions

    @staticmethod
    def _source_hint(path: Path) -> str:
        """从备份文件名反推原文件名（只给界面显示用）。"""
        match = _NAME_RE.match(path.name)
        if not match:
            return path.stem
        return match.group("stem") + (match.group("ext") or "")

    def latest(self, source) -> Optional[BackupVersion]:
        versions = self.list_versions(source)
        return versions[0] if versions else None

    def restore(self, version: BackupVersion, target=None) -> bool:
        """
        把某份备份**恢复到目标路径**（默认覆盖回原路径）。

        先备份当前内容再覆盖（`reason="before_restore"`）——
        恢复本身也可能是个错误操作，不该让用户没法回头。
        """
        target = Path(target) if target is not None else None
        try:
            if target is not None and target.is_file():
                self.create(target, reason="before_restore")
            final = target or self._restore_target(version)
            if final is None:
                return False
            temp = final.with_suffix(final.suffix + ".restoring")
            shutil.copy2(version.path, temp)
            os.replace(temp, final)
            return True
        except Exception as e:  # noqa: BLE001
            logging.error(f"[备份] 恢复失败：{e}")
            return False

    def _restore_target(self, version: BackupVersion) -> Optional[Path]:
        """
        没给目标时，恢复到一个**用户能看见**的位置。

        备份里没存绝对路径，所以**不能猜原目录**（猜错就覆盖了别人的文件）。
        候选按"用户最容易找到"排序，并用写探测挑第一个**真的可写**的
        （沿用 R7 的做法：不可写不要硬写，换下一个）。
        """
        candidates = []
        try:
            candidates.append(Path.home() / "Desktop")
        except Exception:  # noqa: BLE001
            pass
        try:
            candidates.append(Path.home())
        except Exception:  # noqa: BLE001
            pass
        candidates.append(self.root / "restored")

        for folder in candidates:
            try:
                folder.mkdir(parents=True, exist_ok=True)
                probe = folder / ".write_probe"
                probe.write_text("ok", encoding="utf-8")
                probe.unlink(missing_ok=True)
            except Exception:  # noqa: BLE001
                continue
            return folder / f"恢复的-{version.source}"
        return None

    def delete(self, version: BackupVersion) -> bool:
        try:
            version.path.unlink(missing_ok=True)
            return True
        except Exception as e:  # noqa: BLE001
            logging.warning(f"[备份] 删除失败：{e}")
            return False

    def delete_all_for(self, source) -> int:
        """删掉某个源文件的全部备份，返回删除数量。"""
        removed = 0
        for version in self.list_versions(source):
            if self.delete(version):
                removed += 1
        return removed

    # ------------------------------------------------------------------
    # 轮转清理
    # ------------------------------------------------------------------
    def total_size(self) -> int:
        return sum(v.size for v in self.list_all())

    def prune(self, source=None) -> int:
        """
        按"每个文件保留 keep 份"+"总容量上限"清理，返回删除数量。

        总容量超限时**按最旧优先**删（备份是"最近更可能有用"的东西）。
        """
        removed = 0
        if source is not None:
            removed += self._prune_folder(self.folder_for(Path(source)))
        else:
            for folder in self._folders():
                removed += self._prune_folder(folder)

        # 总容量上限：全局按时间从旧到新删。
        # ⚠️ **但至少要留最新一份** —— 把历史全删光等于把备份功能弄没了，
        # 那是比"占点磁盘"严重得多的问题（测试 `test_total_cap_deletes_oldest`
        # 一开始就是因这个缺陷失败的）。
        if self.max_total_bytes:
            total = self.total_size()
            all_versions = self.list_all()
            if total > self.max_total_bytes and len(all_versions) > 1:
                for index, version in enumerate(reversed(all_versions)):
                    if total <= self.max_total_bytes:
                        break
                    if index >= len(all_versions) - 1:
                        break            # 最后一份（最新）永远保留
                    if self.delete(version):
                        total -= version.size
                        removed += 1
        return removed

    def _folders(self) -> List[Path]:
        if not self.root.is_dir():
            return []
        return [p for p in self.root.iterdir() if p.is_dir()]

    def _prune_folder(self, folder: Path) -> int:
        versions = self._collect(folder)          # 新的在前
        removed = 0
        for version in versions[self.keep:]:      # 超出保留份数的（较旧的）
            if self.delete(version):
                removed += 1
        return removed
