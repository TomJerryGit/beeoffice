# beeoffice/cloud_sync/onedrive.py
"""
OneDrive 云存储适配器（基于 Microsoft Graph API）
"""
import logging
from pathlib import Path
from typing import List, Tuple

from beeoffice.cloud_sync.base import CloudStorage
from beeoffice.i18n import tr


class OneDriveStorage(CloudStorage):
    """OneDrive 云存储实现"""

    name = "OneDrive"

    # Microsoft Graph API 基础地址
    API_BASE = "https://graph.microsoft.com/v1.0/me/drive"

    def __init__(self, config: dict):
        """
        :param config: 配置字典，包含 access_token
        """
        super().__init__(config)
        self.access_token = config.get("access_token", "")

    # ---------- 请求头 ----------
    def _headers(self) -> dict:
        """构造认证请求头"""
        return {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json",
        }

    def _check_requests(self):
        """确保 requests 库可用"""
        try:
            import requests  # noqa: F401
        except ImportError as e:
            raise RuntimeError(f"未安装 requests 库: {e}")

    # ---------- 认证 ----------
    def authenticate(self) -> bool:
        """测试 OneDrive 连接"""
        if not self.access_token:
            logging.warning(tr("auto.onedrive.4738abca", "OneDrive access_token 为空"))
            return False
        try:
            self._check_requests()
            import requests
            url = f"{self.API_BASE}/root"
            resp = requests.get(url, headers=self._headers(), timeout=15)
            return resp.status_code == 200
        except Exception as e:
            logging.error(f"OneDrive 认证失败: {e}")
            return False

    # ---------- 列出文件 ----------
    def list_files(self, remote_path: str) -> List[str]:
        """
        列出远端目录下的文件
        :param remote_path: 目录路径，如 "/Documents" 或 "Documents"；根目录传 ""
        """
        try:
            self._check_requests()
            import requests

            # 规范化路径：OneDrive 使用 "root:/path:/children"
            clean_path = remote_path.strip("/")
            if clean_path:
                url = f"{self.API_BASE}/root:/{clean_path}:/children"
            else:
                url = f"{self.API_BASE}/root/children"

            resp = requests.get(url, headers=self._headers(), timeout=15)
            if resp.status_code == 200:
                items = resp.json().get("value", [])
                return [item["name"] for item in items]
            else:
                logging.error(f"OneDrive 列出文件失败: {resp.status_code} {resp.text}")
                return []
        except Exception as e:
            logging.error(f"OneDrive 列出文件异常 {remote_path}: {e}")
            return []

    # ---------- 下载 ----------
    def download(self, remote_path: str, local_path: str) -> bool:
        """从远端下载文件"""
        try:
            self._check_requests()
            import requests

            clean_path = remote_path.strip("/")
            url = f"{self.API_BASE}/root:/{clean_path}:/content"

            # 确保本地目录存在
            Path(local_path).parent.mkdir(parents=True, exist_ok=True)

            resp = requests.get(url, headers=self._headers(), stream=True, timeout=60)
            if resp.status_code == 200:
                with open(local_path, "wb") as f:
                    for chunk in resp.iter_content(chunk_size=8192):
                        if chunk:
                            f.write(chunk)
                return True
            else:
                logging.error(f"OneDrive 下载失败: {resp.status_code} {resp.text}")
                return False
        except Exception as e:
            logging.error(f"OneDrive 下载异常 {remote_path}: {e}")
            return False

    # ---------- 上传 ----------
    def upload(self, local_path: str, remote_path: str) -> bool:
        """
        上传本地文件到远端。
        小文件（<4MB）使用直接上传，大文件请使用上传会话（此处简化处理）。
        """
        try:
            self._check_requests()
            import requests

            local_file = Path(local_path)
            if not local_file.exists():
                logging.error(f"本地文件不存在: {local_path}")
                return False

            clean_path = remote_path.strip("/")
            url = f"{self.API_BASE}/root:/{clean_path}:/content"

            # 根据文件大小选择上传方式
            file_size = local_file.stat().st_size
            if file_size <= 4 * 1024 * 1024:
                # 小文件直接上传
                with open(local_path, "rb") as f:
                    headers = {"Authorization": f"Bearer {self.access_token}"}
                    resp = requests.put(url, headers=headers, data=f, timeout=120)
                if resp.status_code in (200, 201):
                    return True
                logging.error(f"OneDrive 上传失败: {resp.status_code} {resp.text}")
                return False
            else:
                # 大文件使用上传会话
                return self._upload_large(local_path, clean_path)
        except Exception as e:
            logging.error(f"OneDrive 上传异常 {local_path}: {e}")
            return False

    def _upload_large(self, local_path: str, remote_path: str) -> bool:
        """大文件分片上传"""
        try:
            import requests

            # 1. 创建上传会话
            url = f"{self.API_BASE}/root:/{remote_path}:/createUploadSession"
            resp = requests.post(url, headers=self._headers(), timeout=30)
            if resp.status_code != 200:
                logging.error(f"创建上传会话失败: {resp.status_code} {resp.text}")
                return False
            upload_url = resp.json().get("uploadUrl")
            if not upload_url:
                return False

            # 2. 分片上传
            chunk_size = 4 * 1024 * 1024  # 4MB
            file_size = Path(local_path).stat().st_size

            with open(local_path, "rb") as f:
                offset = 0
                while offset < file_size:
                    chunk = f.read(chunk_size)
                    end = offset + len(chunk) - 1
                    headers = {
                        "Content-Length": str(len(chunk)),
                        "Content-Range": f"bytes {offset}-{end}/{file_size}",
                    }
                    resp = requests.put(upload_url, headers=headers, data=chunk, timeout=120)
                    if resp.status_code not in (200, 202):
                        logging.error(f"分片上传失败: {resp.status_code} {resp.text}")
                        return False
                    offset += len(chunk)
            return True
        except Exception as e:
            logging.error(f"OneDrive 大文件上传异常: {e}")
            return False

    # ---------- 删除 ----------
    def delete(self, remote_path: str) -> bool:
        """删除远端文件"""
        try:
            self._check_requests()
            import requests

            clean_path = remote_path.strip("/")
            url = f"{self.API_BASE}/root:/{clean_path}"
            resp = requests.delete(url, headers=self._headers(), timeout=30)
            return resp.status_code in (204, 200)
        except Exception as e:
            logging.error(f"OneDrive 删除异常 {remote_path}: {e}")
            return False

    # ---------- 存在性检查 ----------
    def exists(self, remote_path: str) -> bool:
        """检查远端文件是否存在"""
        try:
            self._check_requests()
            import requests

            clean_path = remote_path.strip("/")
            url = f"{self.API_BASE}/root:/{clean_path}"
            resp = requests.get(url, headers=self._headers(), timeout=15)
            return resp.status_code == 200
        except Exception as e:
            logging.error(f"OneDrive 检查存在性异常 {remote_path}: {e}")
            return False

    # ---------- 文件信息 ----------
    def get_file_info(self, remote_path: str) -> Tuple[int, float]:
        """获取远端文件大小和修改时间"""
        try:
            self._check_requests()
            import requests
            from datetime import datetime

            clean_path = remote_path.strip("/")
            url = f"{self.API_BASE}/root:/{clean_path}?$select=size,lastModifiedDateTime"
            resp = requests.get(url, headers=self._headers(), timeout=15)
            if resp.status_code == 200:
                data = resp.json()
                size = int(data.get("size", 0))
                mtime_str = data.get("lastModifiedDateTime", "")
                mtime = 0.0
                if mtime_str:
                    try:
                        # 处理 ISO 8601 格式（如 "2024-01-01T12:00:00Z"）
                        mtime_str_clean = mtime_str.rstrip("Z").split(".")[0]
                        dt = datetime.fromisoformat(mtime_str_clean)
                        mtime = dt.timestamp()
                    except Exception:
                        mtime = 0.0
                return size, mtime
            return 0, 0.0
        except Exception as e:
            logging.error(f"OneDrive 获取文件信息异常 {remote_path}: {e}")
            return 0, 0.0