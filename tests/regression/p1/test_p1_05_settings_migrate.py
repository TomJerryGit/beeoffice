# tests/test_p2_regression/test_p1_05_settings_migrate.py
"""P1-5 回归：settings 迁移不双重解码"""
import json
import base64


def _b64(s):
    return base64.b64encode(s.encode("utf-8")).decode("utf-8")


def test_migrate_old_webdav_to_cloud(tmp_path):
    """
    旧版 webdav_* 字段应迁移到 cloud_config，且密码不被双重解码。

    注：原实现用一份**手工复制的** AppSettings.__init__ 字段清单来重定向
    配置路径。v5.1 给产品类新增 ai_api_key 等字段后该清单失效，save() 抛
    AttributeError 并被宽 except 吞掉——在原子写修复之前，这会把设置文件
    截断成 0 字节。现改为使用 AppSettings(path=...) 参数注入，不再复制实现。
    """
    from beeoffice.settings import AppSettings

    settings_path = tmp_path / ".beeoffice_settings.json"
    old_data = {
        "version": 0,
        "webdav_url": "https://example.com/webdav",
        "webdav_user": "alice",
        "webdav_pass": _b64("secret123"),
        "webdav_enabled": True,
    }
    settings_path.write_text(
        json.dumps(old_data, ensure_ascii=False), encoding="utf-8"
    )

    s = AppSettings(path=settings_path)
    assert s.cloud_config.get("password") == "secret123"
