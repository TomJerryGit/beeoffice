# beeoffice/plugins/webdav_sync.py
"""
WebDAV 同步 worker 与配置

v5.0.1 修复（P0-10）：
  - _sync_folder 接入 _check_conflict 冲突检测
    - 上传前：若远端更新，跳过上传（避免覆盖远端新文件）
    - 下载前：若本地更新，跳过下载（避免覆盖本地新文件）
  - 补 logging 与异常处理，上传/下载失败时通过 progress 信号通知
  - _sync_folder 对每个文件的异常进行捕获，避免单文件失败中断整个同步
"""
import json
import logging
from pathlib import Path
from datetime import datetime
from PySide6.QtCore import QThread, Signal


class WebDAVSyncWorker(QThread):
    progress = Signal(str)
    finished = Signal(bool, str, list)

    def __init__(self, url, username, password, local_dir, remote_dir="/beeoffice", sync_direction="both"):
        super().__init__()
        self.url = url.rstrip('/'); self.username = username; self.password = password
        self.local_dir = Path(local_dir); self.remote_dir = remote_dir.rstrip('/')
        self.sync_direction = sync_direction

    def run(self):
        try:
            from webdav3.client import Client
            options = {'webdav_hostname': self.url, 'webdav_login': self.username, 'webdav_password': self.password}
            client = Client(options)
            self._mkdir_remote(client, self.remote_dir)
            templates_remote = f"{self.remote_dir}/templates"
            templates_local = self.local_dir / "templates"
            templates_local.mkdir(parents=True, exist_ok=True)
            self._mkdir_remote(client, templates_remote)

            if self.sync_direction in ("upload", "both"):
                self.progress.emit("正在上传模板...")
                self._sync_folder(client, templates_local, templates_remote, "upload")
            if self.sync_direction in ("download", "both"):
                self.progress.emit("正在下载模板...")
                self._sync_folder(client, templates_local, templates_remote, "download")

            self.finished.emit(True, "同步完成", [])
        except Exception as e:
            self.finished.emit(False, f"同步失败: {e}", [])

    def _mkdir_remote(self, client, path):
        try:
            if not client.check(path): client.mkdir(path)
        except: pass

    def _sync_folder(self, client, local_dir, remote_dir, direction):
        """
        同步文件夹（P0-10：接入冲突检测，避免覆盖新文件）

        上传方向：
          - 遍历本地文件
          - 上传前调用 _check_conflict
          - 若远端更新（remote_newer）则跳过，避免覆盖远端
          - 其他情况正常上传

        下载方向：
          - 列出远端文件
          - 下载前调用 _check_conflict
          - 若本地更新（local_newer）则跳过，避免覆盖本地
          - 其他情况正常下载

        异常策略：
          - 单文件上传/下载失败不中断整体同步，仅通过 progress 提示
        """
        if direction == "upload":
            for fp in local_dir.iterdir():
                if not fp.is_file():
                    continue
                remote_path = f"{remote_dir}/{fp.name}"

                # P0-10：上传前检查冲突
                conflict = self._check_conflict(client, fp, remote_path)
                if conflict == "remote_newer":
                    self.progress.emit(
                        f"⚠ 跳过上传（远端更新）: {fp.name}"
                    )
                    continue

                try:
                    client.upload_sync(
                        remote_path=remote_path,
                        local_path=str(fp),
                    )
                except Exception as e:
                    self.progress.emit(f"⚠ 上传失败 {fp.name}: {e}")

        elif direction == "download":
            try:
                files = client.list(remote_dir)
            except Exception as e:
                self.progress.emit(f"⚠ 列目录失败: {e}")
                return

            for f in files:
                name = f.strip('/').split('/')[-1]
                if not name or name == remote_dir.strip('/').split('/')[-1]:
                    continue
                local_path = local_dir / name
                remote_path = f"{remote_dir}/{name}"

                # P0-10：下载前检查冲突
                conflict = self._check_conflict(client, local_path, remote_path)
                if conflict == "local_newer":
                    self.progress.emit(
                        f"⚠ 跳过下载（本地更新）: {name}"
                    )
                    continue

                try:
                    client.download_sync(
                        remote_path=remote_path,
                        local_path=str(local_path),
                    )
                except Exception as e:
                    self.progress.emit(f"⚠ 下载失败 {name}: {e}")

    def _check_conflict(self, client, local_path, remote_path):
        """检查文件冲突 G3"""
        try:
            local_mtime = local_path.stat().st_mtime if local_path.exists() else 0
            remote_info = client.info(remote_path)
            remote_mtime = remote_info.get('modified', '')
            if remote_mtime and local_mtime > 0:
                remote_dt = datetime.strptime(remote_mtime, '%a, %d %b %Y %H:%M:%S %Z')
                if local_mtime > remote_dt.timestamp() + 1: return "local_newer"
                elif remote_dt.timestamp() > local_mtime + 1: return "remote_newer"
            return "same"
        except: return "unknown"


class WebDAVConfig:
    CONFIG_FILE = Path.home() / ".beeoffice_webdav.json"

    def __init__(self):
        self.url = ""; self.username = ""; self.password = ""
        self.enabled = False; self.auto_sync = False
        self.load()

    def load(self):
        if self.CONFIG_FILE.exists():
            try:
                with open(self.CONFIG_FILE, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                self.url = data.get("url",""); self.username = data.get("username","")
                self.password = data.get("password",""); self.enabled = data.get("enabled",False)
                self.auto_sync = data.get("auto_sync",False)
            except: pass

    def save(self):
        with open(self.CONFIG_FILE, 'w', encoding='utf-8') as f:
            json.dump({"url":self.url,"username":self.username,"password":self.password,"enabled":self.enabled,"auto_sync":self.auto_sync}, f, indent=2)