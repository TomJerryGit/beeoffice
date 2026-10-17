# tests/unit/test_cloud_factory.py
"""cloud.py 云存储工厂单例测试"""
import pytest


def _reset():
    from beeoffice import cloud
    cloud._cloud_storage_instance = None
    cloud._cloud_storage_signature = None


def _make_settings_class(**kwargs):
    class _Settings:
        pass
    for k, v in kwargs.items():
        setattr(_Settings, k, v)
    return _Settings


def test_disabled_returns_none(monkeypatch):
    from beeoffice import cloud
    _reset()
    monkeypatch.setattr(cloud, "AppSettings",
                        _make_settings_class(
                            cloud_enabled=False,
                            cloud_type="webdav",
                            cloud_config={}))
    assert cloud.get_cloud_storage() is None


def test_empty_config_returns_none(monkeypatch):
    from beeoffice import cloud
    _reset()
    monkeypatch.setattr(cloud, "AppSettings",
                        _make_settings_class(
                            cloud_enabled=True,
                            cloud_type="webdav",
                            cloud_config={}))
    assert cloud.get_cloud_storage() is None


def test_unknown_type_returns_none(monkeypatch):
    from beeoffice import cloud
    _reset()
    monkeypatch.setattr(cloud, "AppSettings",
                        _make_settings_class(
                            cloud_enabled=True,
                            cloud_type="unknown",
                            cloud_config={"k": "v"}))
    assert cloud.get_cloud_storage() is None


def test_webdav_config_creates_instance(monkeypatch):
    from beeoffice import cloud
    _reset()
    monkeypatch.setattr(cloud, "AppSettings",
                        _make_settings_class(
                            cloud_enabled=True,
                            cloud_type="webdav",
                            cloud_config={
                                "url": "https://a.com/dav",
                                "username": "u",
                                "password": "p",
                            }))
    a = cloud.get_cloud_storage()
    assert a is not None
    assert a.name == "WebDAV"
    # 单例：第二次相同配置返回同一个
    assert cloud.get_cloud_storage() is a


def test_config_change_recreates(monkeypatch):
    from beeoffice import cloud
    _reset()
    monkeypatch.setattr(cloud, "AppSettings",
                        _make_settings_class(
                            cloud_enabled=True,
                            cloud_type="webdav",
                            cloud_config={
                                "url": "https://a.com",
                                "username": "u",
                                "password": "p",
                            }))
    a = cloud.get_cloud_storage()

    monkeypatch.setattr(cloud, "AppSettings",
                        _make_settings_class(
                            cloud_enabled=True,
                            cloud_type="webdav",
                            cloud_config={
                                "url": "https://b.com",
                                "username": "u",
                                "password": "p",
                            }))
    b = cloud.get_cloud_storage()
    assert a is not b, "配置变化后应重建实例"


def test_reset_clears_singleton(monkeypatch):
    from beeoffice import cloud
    _reset()
    monkeypatch.setattr(cloud, "AppSettings",
                        _make_settings_class(
                            cloud_enabled=True,
                            cloud_type="webdav",
                            cloud_config={
                                "url": "https://x.com",
                                "username": "u",
                                "password": "p",
                            }))
    a = cloud.get_cloud_storage()
    assert a is not None

    cloud.reset_cloud_storage()
    assert cloud._cloud_storage_instance is None
    assert cloud._cloud_storage_signature is None
