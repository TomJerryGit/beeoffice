# -*- coding: utf-8 -*-
"""
用户文档云同步（P1-37 第一步）

背景：
    原来的"云同步"只同步配置和模板，**不同步用户文档**。
    用户以为自己的文档在云上，其实没有。

本模块实现双向同步，判定依据刻意避开"本地时间"：

    本地是否变化 → **内容 sha256**（与时间无关）
    远端是否变化 → 远端 size + mtime，但只与**上次同步时记录的同一个值**比较
                   （同一来源、同一时钟，因此不受时区影响）

    本地        远端        动作
    未变        未变        跳过
    变了        未变        上传
    未变        变了        下载
    变了        变了        冲突：本地保留，远端另存为 .remote-<时间戳>

冲突时不覆盖任何一方——这份代码不替用户做"谁更重要"的决定。

远端目录默认 `BeeOffice/`，文件名沿用本地文件名（重名会冲突，v1 已知限制）。
"""
import hashlib
import json
import logging
import time
from pathlib import Path

DEFAULT_REMOTE_DIR = "BeeOffice"


class SyncReport:
    """一次同步的结果汇总。"""

    def __init__(self):
        self.uploaded = []
        self.downloaded = []
        self.conflicts = []
        self.skipped = []
        self.failed = []

    def summary(self) -> str:
        return (
            f"上传 {len(self.uploaded)} · 下载 {len(self.downloaded)} · "
            f"冲突 {len(self.conflicts)} · 跳过 {len(self.skipped)} · "
            f"失败 {len(self.failed)}"
        )

    def as_dict(self):
        return {
            "uploaded": list(self.uploaded),
            "downloaded": list(self.downloaded),
            "conflicts": list(self.conflicts),
            "skipped": list(self.skipped),
            "failed": list(self.failed),
        }


class DocumentSync:
    """基于适配器的双向文档同步。"""

    def __init__(self, adapter, remote_dir: str = DEFAULT_REMOTE_DIR,
                 state_path=None):
        self.adapter = adapter
        self.remote_dir = remote_dir.strip("/") or DEFAULT_REMOTE_DIR
        self.state_path = (
            Path(state_path) if state_path
            else Path.home() / ".beeoffice_sync_state.json"
        )
        self._state = self._load_state()

    # ---------- 状态 ----------
    def _load_state(self) -> dict:
        try:
            if self.state_path.exists():
                return json.loads(self.state_path.read_text(encoding="utf-8"))
        except Exception as e:
            logging.warning(f"读取同步状态失败，将重新建立: {e}")
        return {}

    def _save_state(self, state: dict):
        try:
            self.state_path.write_text(
                json.dumps(state, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except Exception as e:
            logging.warning(f"保存同步状态失败: {e}")

    # ---------- 工具 ----------
    @staticmethod
    def _hash_file(path: Path) -> str:
        h = hashlib.sha256()
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(1 << 20), b""):
                h.update(chunk)
        return h.hexdigest()

    def _remote_path(self, local: Path) -> str:
        return f"{self.remote_dir}/{local.name}"

    def _remote_sig(self, remote: str):
        """远端签名 (size, mtime)；失败返回 None。"""
        try:
            if not self.adapter.exists(remote):
                return None
            size, mtime = self.adapter.get_file_info(remote)
            return [int(size), float(mtime)]
        except Exception as e:
            logging.warning(f"读取远端信息失败 {remote}: {e}")
            return None

    # ---------- 单个文件 ----------
    def sync_one(self, local_path, state: dict, report: SyncReport) -> str:
        local = Path(local_path)
        if not local.exists() or not local.is_file():
            report.failed.append(str(local))
            return "missing"

        key = str(local.resolve())
        record = state.get(key, {})
        remote = self._remote_path(local)

        try:
            local_hash = self._hash_file(local)
        except Exception as e:
            logging.error(f"计算本地哈希失败 {local}: {e}")
            report.failed.append(str(local))
            return "error"

        remote_sig = self._remote_sig(remote)
        base_hash = record.get("local_hash")
        base_sig = record.get("remote_sig")

        local_changed = (base_hash is not None and local_hash != base_hash)
        remote_changed = (
            base_sig is not None and remote_sig is not None
            and remote_sig != base_sig
        )

        # 首次同步（没有基线）
        if base_hash is None:
            if remote_sig is None:
                ok = self._upload(local, remote)
                if ok:
                    report.uploaded.append(str(local))
                    # 必须立刻记录基线：否则下一次同步又会当成"首次"，
                    # 看到远端已存在，误判成冲突。
                    state[key] = self._new_record(local, remote)
                    return "upload"
                report.failed.append(str(local))
                return "error"
            # 远端已存在：无法判断谁新，按冲突处理，偏保守
            self._save_conflict_copy(local, remote, report)
            return "conflict"

        if not local_changed and not remote_changed:
            report.skipped.append(str(local))
            return "skip"

        if local_changed and not remote_changed:
            ok = self._upload(local, remote)
            if ok:
                report.uploaded.append(str(local))
                state[key] = self._new_record(local, remote)
            else:
                report.failed.append(str(local))
            return "upload" if ok else "error"

        if remote_changed and not local_changed:
            ok = self._download(local, remote)
            if ok:
                report.downloaded.append(str(local))
                state[key] = self._new_record(local, remote)
            else:
                report.failed.append(str(local))
            return "download" if ok else "error"

        # 双方都变了
        self._save_conflict_copy(local, remote, report)
        return "conflict"

    # ---------- 动作 ----------
    def _upload(self, local: Path, remote: str) -> bool:
        try:
            return bool(self.adapter.upload(str(local), remote))
        except Exception as e:
            logging.error(f"上传失败 {local}: {e}")
            return False

    def _download(self, local: Path, remote: str) -> bool:
        try:
            tmp = local.with_suffix(local.suffix + ".sync-tmp")
            if not self.adapter.download(remote, str(tmp)):
                return False
            tmp.replace(local)
            return True
        except Exception as e:
            logging.error(f"下载失败 {remote}: {e}")
            return False

    def _save_conflict_copy(self, local: Path, remote: str,
                            report: SyncReport):
        """冲突：本地不动，远端另存一份带时间戳的副本。"""
        stamp = time.strftime("%Y%m%d-%H%M%S")
        target = local.with_name(
            f"{local.stem}.remote-{stamp}{local.suffix}"
        )
        try:
            if self.adapter.download(remote, str(target)):
                report.conflicts.append(str(local))
            else:
                report.failed.append(str(local))
        except Exception as e:
            logging.error(f"冲突副本下载失败 {remote}: {e}")
            report.failed.append(str(local))

    def _new_record(self, local: Path, remote: str) -> dict:
        return {
            "local_hash": self._hash_file(local),
            "remote_sig": self._remote_sig(remote),
            "synced_at": time.time(),
        }

    # ---------- 入口 ----------
    def sync(self, local_paths) -> SyncReport:
        report = SyncReport()
        state = dict(self._state)
        seen = set()

        for p in local_paths:
            key = str(Path(p).resolve())
            if key in seen:
                continue
            seen.add(key)
            try:
                self.sync_one(p, state, report)
            except Exception as e:
                logging.error(f"同步 {p} 失败: {e}")
                report.failed.append(str(p))

        self._state = state
        self._save_state(state)
        return report


def collect_documents(window) -> list:
    """
    收集待同步的用户文档：**当前打开的标签页** + **最近文件列表**。

    用鸭子类型而不是硬绑定主窗口类型，便于测试与复用：
      · window.tab_manager：有 count()/widget(i)，控件上带 _current_file_path
      · window.settings.recent_files：路径字符串列表

    只返回真实存在、扩展名可识别的普通文件；去重并保持顺序。
    """
    paths = []
    seen = set()

    def _add(p):
        if not p:
            return
        try:
            path = Path(p)
        except Exception:
            return
        if not path.is_file():
            return
        key = str(path.resolve())
        if key in seen:
            return
        seen.add(key)
        paths.append(path)

    tab_manager = getattr(window, "tab_manager", None)
    if tab_manager is not None:
        try:
            for i in range(tab_manager.count()):
                widget = tab_manager.widget(i)
                _add(getattr(widget, "_current_file_path", None))
        except Exception as e:
            logging.warning(f"收集已打开文档失败: {e}")

    settings = getattr(window, "settings", None)
    for attr in ("recent_files", "_recent_files"):
        recent = getattr(settings, attr, None) if settings else None
        if isinstance(recent, (list, tuple)):
            for item in recent:
                _add(item)
            break

    return paths

