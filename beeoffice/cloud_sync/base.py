# beeoffice/cloud_sync/base.py
"""
云存储统一接口抽象基类
"""
from abc import ABC, abstractmethod
from typing import List, Tuple, Optional


class CloudStorage(ABC):
    """云存储抽象基类，所有云存储实现应继承此类"""

    # 存储类型名称（子类覆盖）
    name: str = "Base"

    def __init__(self, config: dict):
        """
        :param config: 配置字典，包含认证信息等
        """
        self.config = config or {}

    # ---------- 认证 ----------
    @abstractmethod
    def authenticate(self) -> bool:
        """
        执行认证操作
        :return: 是否认证成功
        """
        pass

    # ---------- 文件列表 ----------
    @abstractmethod
    def list_files(self, remote_path: str) -> List[str]:
        """
        列出远端指定目录下的文件
        :param remote_path: 远端路径
        :return: 文件名列表
        """
        pass

    # ---------- 下载 ----------
    @abstractmethod
    def download(self, remote_path: str, local_path: str) -> bool:
        """
        从远端下载文件到本地
        :param remote_path: 远端文件路径
        :param local_path: 本地保存路径
        :return: 是否成功
        """
        pass

    # ---------- 上传 ----------
    @abstractmethod
    def upload(self, local_path: str, remote_path: str) -> bool:
        """
        从本地上传文件到远端
        :param local_path: 本地文件路径
        :param remote_path: 远端保存路径
        :return: 是否成功
        """
        pass

    # ---------- 删除 ----------
    @abstractmethod
    def delete(self, remote_path: str) -> bool:
        """
        删除远端文件
        :param remote_path: 远端文件路径
        :return: 是否成功
        """
        pass

    # ---------- 存在性检查 ----------
    @abstractmethod
    def exists(self, remote_path: str) -> bool:
        """
        检查远端文件是否存在
        :param remote_path: 远端文件路径
        :return: 是否存在
        """
        pass

    # ---------- 文件信息 ----------
    @abstractmethod
    def get_file_info(self, remote_path: str) -> Tuple[int, float]:
        """
        获取远端文件的信息
        :param remote_path: 远端文件路径
        :return: (文件大小字节数, 修改时间戳)
        """
        pass

    # ---------- 便捷方法（非抽象，子类可继承） ----------
    def get_name(self) -> str:
        """返回存储类型名称"""
        return self.name

    def __repr__(self) -> str:
        return f"<CloudStorage {self.name}>"