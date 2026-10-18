# beeoffice/cloud.py
"""
云存储工厂模块

职责：
  - 根据 AppSettings 中的 cloud_type / cloud_config 创建对应的
    CloudStorage 实例（WebDAV / OneDrive / Google Drive）
  - 单例模式缓存，避免重复创建连接
  - 配置变化时自动重建实例

使用：
    from beeoffice.cloud import get_cloud_storage
    storage = get_cloud_storage()
    if storage:
        storage.upload("/local/file.txt", "/remote/file.txt")

设计：
  - 适配器类延迟导入，避免启动时加载所有云 SDK
  - 未启用或配置无效时返回 None
  - 不强制认证（认证失败延迟到实际调用时再暴露）
"""
import logging

from beeoffice.settings import AppSettings
from beeoffice.i18n import tr


# ==================== 单例缓存 ====================
_cloud_storage_instance = None
_cloud_storage_signature = None


# ==================== 适配器类型映射 ====================
def _get_storage_class(cloud_type: str):
    """
    根据存储类型返回适配器类。
    延迟导入，避免启动时加载所有云 SDK。
    """
    if cloud_type == "webdav":
        from beeoffice.cloud_sync.webdav import WebDAVStorage
        return WebDAVStorage
    elif cloud_type == "onedrive":
        from beeoffice.cloud_sync.onedrive import OneDriveStorage
        return OneDriveStorage
    elif cloud_type == "googledrive":
        from beeoffice.cloud_sync.googledrive import GoogleDriveStorage
        return GoogleDriveStorage
    else:
        return None


# ==================== 工厂函数 ====================
def get_cloud_storage():
    """
    返回当前配置的 CloudStorage 实例。

    返回规则：
      - cloud_enabled 为 False → 返回 None
      - cloud_config 为空 → 返回 None
      - cloud_type 未知 → 返回 None
      - 创建失败 → 返回 None

    单例策略：
      - 相同配置 → 返回缓存的实例
      - 配置变化 → 重新创建
    """
    global _cloud_storage_instance, _cloud_storage_signature

    settings = AppSettings()

    # 1. 未启用 → 返回 None
    if not settings.cloud_enabled:
        return None

    # 2. 配置为空 → 返回 None
    cloud_config = settings.cloud_config or {}
    if not cloud_config:
        return None

    cloud_type = settings.cloud_type or "webdav"

    # 3. 配置签名（用于判断是否重建）
    try:
        signature = (
            cloud_type,
            tuple(sorted((str(k), str(v)) for k, v in cloud_config.items())),
        )
    except Exception as e:
        logging.error(f"生成云存储配置签名失败: {e}")
        signature = None

    # 4. 命中缓存 → 直接返回
    if signature is not None and signature == _cloud_storage_signature:
        return _cloud_storage_instance

    # 5. 创建新实例
    cls = _get_storage_class(cloud_type)
    if cls is None:
        logging.warning(tr("auto.cloud.b9a2f2a4", "未知的云存储类型: {cloud_type}").format(cloud_type=cloud_type))
        return None

    try:
        instance = cls(cloud_config)
        _cloud_storage_instance = instance
        _cloud_storage_signature = signature
        logging.info(f"云存储实例已创建: {cloud_type}")
        return instance
    except Exception as e:
        logging.error(f"创建云存储实例失败 [{cloud_type}]: {e}")
        _cloud_storage_instance = None
        _cloud_storage_signature = None
        return None


def reset_cloud_storage():
    """
    重置云存储单例。
    在用户修改云存储设置后调用，确保下次 get_cloud_storage() 重建实例。
    """
    global _cloud_storage_instance, _cloud_storage_signature
    _cloud_storage_instance = None
    _cloud_storage_signature = None
    logging.info("云存储单例已重置")