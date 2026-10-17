# beeoffice/cloud_sync/__init__.py
"""
云存储适配器子包

提供：
  - CloudStorage  抽象基类
  - WebDAVStorage      WebDAV 适配器
  - OneDriveStorage    OneDrive 适配器
  - GoogleDriveStorage Google Drive 适配器

对外统一通过 beeoffice.cloud.get_cloud_storage() 获取实例。
"""
from beeoffice.cloud_sync.base import CloudStorage
from beeoffice.cloud_sync.webdav import WebDAVStorage
from beeoffice.cloud_sync.onedrive import OneDriveStorage
from beeoffice.cloud_sync.googledrive import GoogleDriveStorage

__all__ = [
    "CloudStorage",
    "WebDAVStorage",
    "OneDriveStorage",
    "GoogleDriveStorage",
]