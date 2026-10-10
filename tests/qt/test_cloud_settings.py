# tests/qt/test_cloud_settings.py
"""cloud_settings.py 测试：云存储设置对话框"""
import pytest


@pytest.fixture
def dlg(qtbot, temp_settings):
    from beeoffice.cloud_settings import CloudSettingsDialog
    d = CloudSettingsDialog()
    qtbot.addWidget(d)
    return d


class TestInit:
    def test_dialog_created(self, dlg):
        assert dlg is not None

    def test_has_type_combo(self, dlg):
        assert dlg.type_combo.count() == 3
        assert dlg.type_combo.itemData(0) == "webdav"
        assert dlg.type_combo.itemData(1) == "onedrive"
        assert dlg.type_combo.itemData(2) == "googledrive"

    def test_has_enable_check(self, dlg):
        assert dlg.enabled_check is not None

    def test_has_auto_sync_check(self, dlg):
        assert dlg.auto_sync_check is not None


class TestTypeSwitch:
    def test_switch_to_onedrive(self, dlg):
        dlg.type_combo.setCurrentIndex(1)
        assert dlg.stack.currentIndex() == 1

    def test_switch_to_googledrive(self, dlg):
        dlg.type_combo.setCurrentIndex(2)
        assert dlg.stack.currentIndex() == 2

    def test_switch_back_to_webdav(self, dlg):
        dlg.type_combo.setCurrentIndex(1)
        dlg.type_combo.setCurrentIndex(0)
        assert dlg.stack.currentIndex() == 0


class TestLoadSettings:
    def test_initial_type_from_settings(self, dlg):
        # 默认 cloud_type == "webdav"
        assert dlg.type_combo.currentData() == "webdav"

    def test_enable_check_reflects_settings(self, dlg):
        # 默认 cloud_enabled == False
        assert dlg.enabled_check.isChecked() is False


class TestSaveValidation:
    def test_webdav_invalid_url_rejected(self, dlg, monkeypatch):
        """WebDAV 地址不带 http:// 或 https:// 时，保存失败"""
        from PySide6.QtWidgets import QMessageBox
        warned = []
        monkeypatch.setattr(
            QMessageBox, "warning",
            staticmethod(lambda *a, **k: warned.append(a)),
        )
        dlg.type_combo.setCurrentIndex(0)
        dlg.url_edit.setText("ftp://invalid")
        dlg._save()
        assert warned, "非法 URL 应弹警告"

    def test_webdav_valid_url_accepted(self, dlg, monkeypatch):
        from PySide6.QtWidgets import QMessageBox
        infos = []
        monkeypatch.setattr(
            QMessageBox, "information",
            staticmethod(lambda *a, **k: infos.append(a)),
        )
        dlg.type_combo.setCurrentIndex(0)
        dlg.url_edit.setText("https://example.com/dav")
        dlg.user_edit.setText("user")
        dlg.pwd_edit.setText("pwd")
        dlg._save()
        assert infos, "合法 URL 保存应弹提示"


class TestResetSingleton:
    def test_save_resets_cloud_singleton(self, dlg, monkeypatch):
        """保存后应调用 reset_cloud_storage"""
        from beeoffice import cloud
        from PySide6.QtWidgets import QMessageBox

        called = []
        monkeypatch.setattr(
            cloud, "reset_cloud_storage",
            lambda: called.append("reset"),
        )
        monkeypatch.setattr(
            QMessageBox, "information",
            staticmethod(lambda *a, **k: None),
        )
        dlg.type_combo.setCurrentIndex(0)
        dlg.url_edit.setText("https://example.com/dav")
        dlg._save()
        assert called == ["reset"]
