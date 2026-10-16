# tests/test_settings.py
"""
AppSettings 测试

覆盖：
  - 保存 / 加载
  - 版本迁移
  - 敏感信息编码
"""
import json



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


class TestAtomicSave:
    """
    优化规划 §1.2 回归：保存失败绝不能破坏已有设置文件。

    原缺陷：save() 先以 "w" 打开（立即截断文件）再在 json.dump 的参数位置
    构造 payload，任何构造期异常都会把用户设置留成 0 字节空文件。
    """

    def test_failure_keeps_old_file_intact(self, temp_settings):
        """构造 payload 失败时，磁盘上的旧设置必须原样保留。"""
        from beeoffice.settings import AppSettings

        s = AppSettings()
        s.theme = "dark"
        assert s.save() is True

        before = temp_settings.read_text(encoding="utf-8")
        assert '"dark"' in before

        # 复现真实事故：某个代码路径上缺了 v5.1 新增的字段
        del s.ai_api_key
        assert s.save() is False

        after = temp_settings.read_text(encoding="utf-8")
        assert after.strip(), "原文件不得被截断成空文件"
        assert after == before, "保存失败时原文件必须逐字节保持不变"

    def test_unserializable_value_keeps_old_file_intact(self, temp_settings):
        """序列化失败同样不得破坏旧文件。"""
        from beeoffice.settings import AppSettings

        s = AppSettings()
        assert s.save() is True
        before = temp_settings.read_text(encoding="utf-8")

        s.recent_files = [object()]  # 不可 JSON 序列化
        assert s.save() is False
        assert temp_settings.read_text(encoding="utf-8") == before

    def test_no_temp_files_left_behind(self, temp_settings):
        """原子写不得留下 .tmp 残留文件。"""
        from beeoffice.settings import AppSettings

        s = AppSettings()
        s.save()
        del s.ai_api_key
        s.save()

        leftovers = sorted(p.name for p in temp_settings.parent.glob("*.tmp"))
        assert leftovers == [], f"残留临时文件: {leftovers}"

    def test_failure_is_not_silent(self, temp_settings, monkeypatch):
        """保存失败必须通知用户，不能只写日志。"""
        from beeoffice.settings import AppSettings

        seen = []
        monkeypatch.setattr(
            AppSettings, "on_save_error", staticmethod(seen.append)
        )

        s = AppSettings()
        del s.ai_api_key
        assert s.save() is False
        assert seen, "保存失败应触发 on_save_error 回调"

    def test_save_returns_true_on_success(self, temp_settings):
        """成功路径返回 True，且能被重新加载。"""
        from beeoffice.settings import AppSettings

        s = AppSettings()
        s.theme = "dark"
        s.accent_color = "forest"
        assert s.save() is True

        s2 = AppSettings()
        assert (s2.theme, s2.accent_color) == ("dark", "forest")