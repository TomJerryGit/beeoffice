# tests/test_p2_regression/test_p1_05_settings_migrate.py
"""P1-5 回归：settings 迁移不双重解码"""
import json
import base64
from pathlib import Path


def _b64(s):
    return base64.b64encode(s.encode("utf-8")).decode("utf-8")


def _patch_init(self, path):
    from pathlib import Path
    self.path = Path(path)
    self.window_size = (1024, 680)
    self.recent_files = []
    self.open_tabs = []
    self.theme = "light"
    self.accent_color = "amber"
    self.language = "zh_CN"
    self.has_completed_onboarding = True
    self.recent_commands = []
    self.webdav_url = ""
    self.webdav_user = ""
    self.webdav_pass = ""
    self.webdav_enabled = False
    self.webdav_auto_sync = False
    self.git_repo_path = ""
    self.git_enabled = False
    self.cloud_type = "webdav"
    self.cloud_config = {}
    self.cloud_enabled = False
    self.cloud_auto_sync = False
    self.load()


def test_migrate_old_webdav_to_cloud(tmp_path, monkeypatch):
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
    monkeypatch.setattr(
        "beeoffice.settings.AppSettings.__init__",
        lambda self: _patch_init(self, settings_path)
    )
    s = AppSettings()
    assert s.cloud_config.get("password") == "secret123"
