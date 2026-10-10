# beeoffice/cloud_sync/webdav.py
"""
WebDAV 云存储适配器
"""
import logging
from pathlib import Path
from typing import List, Tuple

from beeoffice.cloud_sync.base import CloudStorage


class WebDAVStorage(CloudStorage):
    """WebDAV 云存储实现"""

    name = "WebDAV"

    def __init__(self, config: dict):
        """
        :param config: 配置字典，包含 url、username、password
        """
        super().__init__(config)
        self.url = config.get("url", "")
        self.username = config.get("username", "")
        self.password = config.get("password", "")
        self._client = None

    # ---------- 内部客户端 ----------
    def _get_client(self):
        """延迟创建 WebDAV 客户端"""
        if self._client is None:
            try:
                from webdav3.client import Client
            except ImportError as e:
                raise RuntimeError(f"未安装 webdavclient3: {e}")

            options = {
                "webdav_hostname": self.url,
                "webdav_login": self.username,
                "webdav_password": self.password,
            }
            self._client = Client(options)
        return self._client

    # ---------- 认证 ----------
    def authenticate(self) -> bool:
        """测试 WebDAV 连接"""
        try:
            self._get_client().check()
            return True
        except Exception as e:
            logging.error(f"WebDAV 认证失败: {e}")
            return False

    # ---------- 列出文件 ----------
    def list_files(self, remote_path: str) -> List[str]:
        """列出远端目录下的文件"""
        try:
            client = self._get_client()
            # 确保路径以 / 开头
            path = remote_path if remote_path.startswith("/") else f"/{remote_path}"
            files = client.list(path)
            # 过滤掉 "." 和 ".."
            return [f for f in files if f not in (".", "..")]
        except Exception as e:
            logging.error(f"列出文件失败 {remote_path}: {e}")
            return []

    # ---------- 下载 ----------
    def download(self, remote_path: str, local_path: str) -> bool:
        """从远端下载文件"""
        try:
            client = self._get_client()
            # 确保本地目录存在
            Path(local_path).parent.mkdir(parents=True, exist_ok=True)
            client.download_sync(remote_path, local_path)
            return True
        except Exception as e:
            logging.error(f"下载失败 {remote_path} -> {local_path}: {e}")
            return False

    # ---------- 上传 ----------
    def upload(self, local_path: str, remote_path: str) -> bool:
        """上传本地文件到远端"""
        try:
            client = self._get_client()
            # 确保远端父目录存在
            remote_parent = str(Path(remote_path).parent).replace("\\", "/")
            if remote_parent and remote_parent != "/":
                try:
                    if not client.check(remote_parent):
                        client.mkdir(remote_parent)
                except Exception:
                    # 目录创建失败时继续尝试上传（有些服务器自动创建）
                    pass
            client.upload_sync(remote_path, local_path)
            return True
        except Exception as e:
            logging.error(f"上传失败 {local_path} -> {remote_path}: {e}")
            return False

    # ---------- 删除 ----------
    def delete(self, remote_path: str) -> bool:
        """删除远端文件或目录"""
        try:
            client = self._get_client()
            client.clean(remote_path)
            return True
        except Exception as e:
            logging.error(f"删除失败 {remote_path}: {e}")
            return False

    # ---------- 存在性检查 ----------
    def exists(self, remote_path: str) -> bool:
        """检查远端文件是否存在"""
        try:
            client = self._get_client()
            return client.check(remote_path)
        except Exception as e:
            logging.error(f"检查存在性失败 {remote_path}: {e}")
            return False

    # ---------- 文件信息 ----------
    def get_file_info(self, remote_path: str) -> Tuple[int, float]:
        """获取远端文件的大小和修改时间"""
        try:
            client = self._get_client()
            info = client.info(remote_path)
            # 大小可能返回字符串，转为 int
            size_raw = info.get("size", 0)
            try:
                size = int(size_raw)
            except (TypeError, ValueError):
                size = 0
            # 修改时间可能是字符串或时间戳
            mtime_raw = info.get("modified", 0)
            try:
                mtime = float(mtime_raw)
            except (TypeError, ValueError):
                # 若为日期字符串，忽略
                mtime = 0.0
            return size, mtime
        except Exception as e:
            logging.error(f"获取文件信息失败 {remote_path}: {e}")
            return 0, 0.0

    # ---------- 资源清理 ----------
    def __del__(self):
        """释放客户端引用"""
        self._client = None