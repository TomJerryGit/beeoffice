# beeoffice/cloud_sync/googledrive.py
"""
Google Drive 云存储适配器（基于 Google Drive API v3）
"""
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import List, Tuple

from beeoffice.cloud_sync.base import CloudStorage
from beeoffice.i18n import tr


class GoogleDriveStorage(CloudStorage):
    """Google Drive 云存储实现"""

    name = "Google Drive"

    # Google Drive API 基础地址
    API_BASE = "https://www.googleapis.com/drive/v3"
    UPLOAD_BASE = "https://www.googleapis.com/upload/drive/v3"

    def __init__(self, config: dict):
        """
        :param config: 配置字典，包含 access_token
        """
        super().__init__(config)
        self.access_token = config.get("access_token", "")

    # ---------- 请求头 ----------
    def _headers(self, content_type: str = "application/json") -> dict:
        """构造认证请求头"""
        return {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": content_type,
        }

    def _check_requests(self):
        """确保 requests 库可用"""
        try:
            import requests  # noqa: F401
        except ImportError as e:
            raise RuntimeError(f"未安装 requests 库: {e}")

    # ---------- 内部辅助：路径转文件ID ----------
    def _resolve_path(self, remote_path: str) -> str:
        """
        将路径（如 "/folder/file.txt"）解析为文件 ID。
        若路径不存在，返回空字符串。
        """
        clean_path = remote_path.strip("/")
        if not clean_path:
            # 根目录
            return "root"

        parts = clean_path.split("/")
        parent_id = "root"

        for idx, part in enumerate(parts):
            query = (
                f"name = '{self._escape_query(part)}' "
                f"and '{parent_id}' in parents and trashed = false"
            )
            file_id = self._find_file_by_query(query)
            if not file_id:
                return ""
            parent_id = file_id

        return parent_id

    @staticmethod
    def _escape_query(text: str) -> str:
        """转义查询字符串中的单引号"""
        return text.replace("\\", "\\\\").replace("'", "\\'")

    def _find_file_by_query(self, query: str) -> str:
        """根据查询条件查找文件 ID"""
        try:
            import requests
            url = f"{self.API_BASE}/files"
            params = {
                "q": query,
                "fields": "files(id,name)",
                "pageSize": 1,
            }
            resp = requests.get(
                url, headers=self._headers(), params=params, timeout=15
            )
            if resp.status_code == 200:
                files = resp.json().get("files", [])
                if files:
                    return files[0]["id"]
            return ""
        except Exception as e:
            logging.error(f"Google Drive 查询文件失败: {e}")
            return ""

    def _ensure_folder_path(self, remote_dir: str) -> str:
        """
        确保远端目录存在，返回目录 ID。
        逐级创建不存在的文件夹。
        """
        clean_path = remote_dir.strip("/")
        if not clean_path:
            return "root"

        parts = clean_path.split("/")
        parent_id = "root"

        for part in parts:
            query = (
                f"name = '{self._escape_query(part)}' "
                f"and '{parent_id}' in parents "
                f"and mimeType = 'application/vnd.google-apps.folder' "
                f"and trashed = false"
            )
            folder_id = self._find_file_by_query(query)
            if not folder_id:
                # 创建文件夹
                folder_id = self._create_folder(part, parent_id)
                if not folder_id:
                    return ""
            parent_id = folder_id

        return parent_id

    def _create_folder(self, name: str, parent_id: str) -> str:
        """创建文件夹，返回新文件夹 ID"""
        try:
            import requests
            url = f"{self.API_BASE}/files"
            metadata = {
                "name": name,
                "mimeType": "application/vnd.google-apps.folder",
                "parents": [parent_id],
            }
            resp = requests.post(
                url, headers=self._headers(), json=metadata, timeout=15
            )
            if resp.status_code in (200, 201):
                return resp.json().get("id", "")
            logging.error(f"创建文件夹失败: {resp.status_code} {resp.text}")
            return ""
        except Exception as e:
            logging.error(f"创建文件夹异常: {e}")
            return ""

    # ---------- 认证 ----------
    def authenticate(self) -> bool:
        """测试 Google Drive 连接"""
        if not self.access_token:
            logging.warning(tr("auto.googledrive.7656a4a3", "Google Drive access_token 为空"))
            return False
        try:
            self._check_requests()
            import requests
            url = f"{self.API_BASE}/about"
            params = {"fields": "user"}
            resp = requests.get(
                url, headers=self._headers(), params=params, timeout=15
            )
            return resp.status_code == 200
        except Exception as e:
            logging.error(f"Google Drive 认证失败: {e}")
            return False

    # ---------- 列出文件 ----------
    def list_files(self, remote_path: str) -> List[str]:
        """
        列出远端目录下的文件
        :param remote_path: 目录路径，如 "/Documents" 或 "" (根目录)
        """
        try:
            self._check_requests()
            import requests

            parent_id = self._resolve_path(remote_path)
            if not parent_id:
                logging.error(f"目录不存在: {remote_path}")
                return []

            url = f"{self.API_BASE}/files"
            params = {
                "q": f"'{parent_id}' in parents and trashed = false",
                "fields": "files(id,name,mimeType)",
                "pageSize": 1000,
            }
            resp = requests.get(
                url, headers=self._headers(), params=params, timeout=15
            )
            if resp.status_code == 200:
                items = resp.json().get("files", [])
                return [item["name"] for item in items]
            else:
                logging.error(f"列出文件失败: {resp.status_code} {resp.text}")
                return []
        except Exception as e:
            logging.error(f"Google Drive 列出文件异常 {remote_path}: {e}")
            return []

    # ---------- 下载 ----------
    def download(self, remote_path: str, local_path: str) -> bool:
        """从远端下载文件"""
        try:
            self._check_requests()
            import requests

            file_id = self._resolve_path(remote_path)
            if not file_id or file_id == "root":
                logging.error(f"文件不存在: {remote_path}")
                return False

            url = f"{self.API_BASE}/files/{file_id}"
            params = {"alt": "media"}

            # 确保本地目录存在
            Path(local_path).parent.mkdir(parents=True, exist_ok=True)

            resp = requests.get(
                url, headers=self._headers(), params=params,
                stream=True, timeout=60
            )
            if resp.status_code == 200:
                with open(local_path, "wb") as f:
                    for chunk in resp.iter_content(chunk_size=8192):
                        if chunk:
                            f.write(chunk)
                return True
            else:
                logging.error(f"下载失败: {resp.status_code} {resp.text}")
                return False
        except Exception as e:
            logging.error(f"Google Drive 下载异常 {remote_path}: {e}")
            return False

    # ---------- 上传 ----------
    def upload(self, local_path: str, remote_path: str) -> bool:
        """上传本地文件到远端（分片上传）"""
        try:
            self._check_requests()
            import requests

            local_file = Path(local_path)
            if not local_file.exists():
                logging.error(f"本地文件不存在: {local_path}")
                return False

            # 解析目标路径
            remote_path_clean = remote_path.strip("/")
            if not remote_path_clean:
                logging.error("远端路径不能为空")
                return False

            parts = remote_path_clean.split("/")
            file_name = parts[-1]
            parent_dir = "/".join(parts[:-1])

            # 确保父目录存在
            if parent_dir:
                parent_id = self._ensure_folder_path(parent_dir)
                if not parent_id:
                    logging.error(f"创建父目录失败: {parent_dir}")
                    return False
            else:
                parent_id = "root"

            # 检查同名文件是否存在（存在则更新）
            query = (
                f"name = '{self._escape_query(file_name)}' "
                f"and '{parent_id}' in parents and trashed = false"
            )
            existing_id = self._find_file_by_query(query)

            file_size = local_file.stat().st_size
            chunk_size = 5 * 1024 * 1024  # 5MB 分片

            if existing_id:
                # 更新已有文件
                upload_url = (
                    f"{self.UPLOAD_BASE}/files/{existing_id}"
                    f"?uploadType=media"
                )
                with open(local_path, "rb") as f:
                    resp = requests.patch(
                        upload_url,
                        headers=self._headers(content_type="application/octet-stream"),
                        data=f,
                        timeout=180,
                    )
                return resp.status_code in (200, 201)
            else:
                # 新建文件：使用分片上传（适合大文件）
                if file_size <= chunk_size:
                    # 小文件直接上传
                    url = f"{self.UPLOAD_BASE}/files?uploadType=multipart"
                    metadata = {"name": file_name, "parents": [parent_id]}
                    files = {
                        "metadata": (
                            "metadata",
                            json.dumps(metadata),
                            "application/json",
                        ),
                        "file": (
                            file_name,
                            open(local_path, "rb"),
                            "application/octet-stream",
                        ),
                    }
                    headers = {"Authorization": f"Bearer {self.access_token}"}
                    resp = requests.post(
                        url, headers=headers, files=files, timeout=180
                    )
                    return resp.status_code in (200, 201)
                else:
                    # 大文件分片上传
                    return self._upload_resumable(local_path, file_name, parent_id)
        except Exception as e:
            logging.error(f"Google Drive 上传异常 {local_path}: {e}")
            return False

    def _upload_resumable(self, local_path: str, file_name: str, parent_id: str) -> bool:
        """使用可续传上传会话上传大文件"""
        try:
            import requests

            # 1. 初始化上传会话
            url = f"{self.UPLOAD_BASE}/files?uploadType=resumable"
            metadata = {"name": file_name, "parents": [parent_id]}
            headers = {
                "Authorization": f"Bearer {self.access_token}",
                "Content-Type": "application/json; charset=UTF-8",
                "X-Upload-Content-Type": "application/octet-stream",
            }
            resp = requests.post(
                url, headers=headers, json=metadata, timeout=30
            )
            if resp.status_code != 200:
                logging.error(f"初始化上传会话失败: {resp.status_code} {resp.text}")
                return False
            session_url = resp.headers.get("Location")
            if not session_url:
                return False

            # 2. 分片上传
            chunk_size = 5 * 1024 * 1024
            file_size = Path(local_path).stat().st_size

            with open(local_path, "rb") as f:
                offset = 0
                while offset < file_size:
                    chunk = f.read(chunk_size)
                    end = offset + len(chunk) - 1
                    chunk_headers = {
                        "Content-Length": str(len(chunk)),
                        "Content-Range": f"bytes {offset}-{end}/{file_size}",
                    }
                    resp = requests.put(
                        session_url, headers=chunk_headers, data=chunk, timeout=180
                    )
                    if resp.status_code not in (200, 201, 308):
                        logging.error(f"分片上传失败: {resp.status_code} {resp.text}")
                        return False
                    offset += len(chunk)
            return True
        except Exception as e:
            logging.error(f"Google Drive 大文件上传异常: {e}")
            return False

    # ---------- 删除 ----------
    def delete(self, remote_path: str) -> bool:
        """删除远端文件"""
        try:
            self._check_requests()
            import requests

            file_id = self._resolve_path(remote_path)
            if not file_id or file_id == "root":
                logging.error(f"文件不存在: {remote_path}")
                return False

            url = f"{self.API_BASE}/files/{file_id}"
            resp = requests.delete(url, headers=self._headers(), timeout=30)
            return resp.status_code == 204
        except Exception as e:
            logging.error(f"Google Drive 删除异常 {remote_path}: {e}")
            return False

    # ---------- 存在性检查 ----------
    def exists(self, remote_path: str) -> bool:
        """检查远端文件是否存在"""
        try:
            file_id = self._resolve_path(remote_path)
            return bool(file_id)
        except Exception as e:
            logging.error(f"Google Drive 检查存在性异常 {remote_path}: {e}")
            return False

    # ---------- 文件信息 ----------
    def get_file_info(self, remote_path: str) -> Tuple[int, float]:
        """获取远端文件大小和修改时间"""
        try:
            self._check_requests()
            import requests

            file_id = self._resolve_path(remote_path)
            if not file_id or file_id == "root":
                return 0, 0.0

            url = f"{self.API_BASE}/files/{file_id}"
            params = {"fields": "size,modifiedTime"}
            resp = requests.get(
                url, headers=self._headers(), params=params, timeout=15
            )
            if resp.status_code == 200:
                data = resp.json()
                size = int(data.get("size", 0))
                mtime_str = data.get("modifiedTime", "")
                mtime = 0.0
                if mtime_str:
                    try:
                        # 处理 ISO 8601 格式（如 "2024-01-01T12:00:00.000Z"）
                        mtime_str_clean = mtime_str.rstrip("Z").split(".")[0]
                        dt = datetime.fromisoformat(mtime_str_clean)
                        mtime = dt.timestamp()
                    except Exception:
                        mtime = 0.0
                return size, mtime
            return 0, 0.0
        except Exception as e:
            logging.error(f"Google Drive 获取文件信息异常 {remote_path}: {e}")
            return 0, 0.0