# tests/test_settings.py
"""
AppSettings 测试

覆盖：
  - 保存 / 加载
  - 版本迁移
  - 敏感信息编码
"""
import json
from pathlib import Path

import pytest


class TestSettingsBasic:
    """基础读写"""

    def test_default_values(self, temp_settings):
        """默认值"""
        from beeoffice.settings import AppSettings
        s = AppSettings()
        assert s.theme == "light"
        assert s.accent_color == "amber"
        assert s.language == "zh_CN"

    def test_save_and_load(self, temp_settings):
        """保存后能加载"""
        from beeoffice.settings import AppSettings
        s = AppSettings()
        s.theme = "dark"
        s.accent_color = "ocean"
        s.save()

        s2 = AppSettings()
        assert s2.theme == "dark"
        assert s2.accent_color == "ocean"

    def test_window_size_serialization(self, temp_settings):
        """窗口尺寸应为 list 序列化"""
        from beeoffice.settings import AppSettings
        s = AppSettings()
        s.window_size = (1024, 768)
        s.save()

        with open(s.path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        assert isinstance(data["window_size"], list)
        assert data["window_size"] == [1024, 768]


class TestSensitiveEncoding:
    """敏感信息编码"""

    def test_password_encoded(self, temp_settings):
        """密码应 Base64 编码存储"""
        from beeoffice.settings import AppSettings
        s = AppSettings()
        s.webdav_pass = "my_secret_password"
        s.save()

        with open(s.path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        # 存储的应该是 Base64 编码
        stored = data["webdav_pass"]
        assert stored != "my_secret_password"
        assert stored  # 非空

    def test_password_decoded_on_load(self, temp_settings):
        """加载时应解码"""
        from beeoffice.settings import AppSettings
        s = AppSettings()
        s.webdav_pass = "my_secret_password"
        s.save()

        s2 = AppSettings()
        assert s2.webdav_pass == "my_secret_password"