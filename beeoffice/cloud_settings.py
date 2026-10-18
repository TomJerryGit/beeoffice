# beeoffice/cloud_settings.py
"""
云存储设置对话框：支持 WebDAV / OneDrive / Google Drive

本次更新：
  - _save 方法末尾调用 reset_cloud_storage()，确保配置变化后单例重建
  - 保存成功后再触发 reset，避免保存失败仍重置
"""
import logging

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QFormLayout, QLineEdit, QComboBox,
    QCheckBox, QPushButton, QMessageBox, QDialogButtonBox,
    QLabel, QHBoxLayout, QWidget, QStackedWidget
)
from PySide6.QtCore import Qt

from beeoffice.settings import AppSettings
from beeoffice.i18n import tr


class CloudSettingsDialog(QDialog):
    """云存储设置对话框"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(tr("auto.cloud_settings.d9bfe5c4", "☁️ 云存储设置"))
        self.resize(480, 400)
        self.settings = AppSettings()

        # 主布局
        layout = QVBoxLayout(self)
        layout.setSpacing(10)

        # 类型选择
        type_layout = QHBoxLayout()
        type_layout.addWidget(QLabel(tr("auto.cloud_settings.99e92297", "存储类型:")))
        self.type_combo = QComboBox()
        self.type_combo.addItem("WebDAV", "webdav")
        self.type_combo.addItem("OneDrive", "onedrive")
        self.type_combo.addItem("Google Drive", "googledrive")
        type_layout.addWidget(self.type_combo)
        type_layout.addStretch()
        layout.addLayout(type_layout)

        # 动态字段区（使用 QStackedWidget 切换）
        self.stack = QStackedWidget()

        # ---- WebDAV 字段 ----
        self.webdav_page = QWidget()
        webdav_form = QFormLayout(self.webdav_page)
        self.url_edit = QLineEdit()
        self.url_edit.setPlaceholderText("https://example.com/webdav")
        webdav_form.addRow("地址:", self.url_edit)

        self.user_edit = QLineEdit()
        webdav_form.addRow("用户名:", self.user_edit)

        self.pwd_edit = QLineEdit()
        self.pwd_edit.setEchoMode(QLineEdit.Password)
        webdav_form.addRow("密码:", self.pwd_edit)

        self.stack.addWidget(self.webdav_page)

        # ---- OneDrive 字段 ----
        self.onedrive_page = QWidget()
        onedrive_form = QFormLayout(self.onedrive_page)
        self.onedrive_token_edit = QLineEdit()
        self.onedrive_token_edit.setPlaceholderText("OAuth Access Token")
        onedrive_form.addRow("Access Token:", self.onedrive_token_edit)
        onedrive_form.addRow(QLabel(tr("auto.cloud_settings.506d9b43", "提示：需从 Microsoft Graph API 获取")))
        self.stack.addWidget(self.onedrive_page)

        # ---- Google Drive 字段 ----
        self.gdrive_page = QWidget()
        gdrive_form = QFormLayout(self.gdrive_page)
        self.gdrive_token_edit = QLineEdit()
        self.gdrive_token_edit.setPlaceholderText("OAuth Access Token")
        gdrive_form.addRow("Access Token:", self.gdrive_token_edit)
        gdrive_form.addRow(QLabel(tr("auto.cloud_settings.7ac31a8a", "提示：需从 Google Drive API 获取")))
        self.stack.addWidget(self.gdrive_page)

        layout.addWidget(self.stack)

        # 通用选项
        option_layout = QVBoxLayout()
        self.enabled_check = QCheckBox(tr("auto.cloud_settings.fda4091d", "启用云同步"))
        option_layout.addWidget(self.enabled_check)
        self.auto_sync_check = QCheckBox(tr("auto.cloud_settings.e4bdc666", "启动时自动同步"))
        option_layout.addWidget(self.auto_sync_check)
        layout.addLayout(option_layout)

        layout.addStretch()

        # 按钮栏
        btn_layout = QHBoxLayout()
        self.test_btn = QPushButton(tr("auto.cloud_settings.10b7d8ec", "测试连接"))
        self.test_btn.clicked.connect(self._test_connection)
        btn_layout.addWidget(self.test_btn)
        btn_layout.addStretch()

        btns = QDialogButtonBox()
        save_btn = QPushButton(tr("auto.cloud_settings.fadf24db", "保存"))
        save_btn.setDefault(True)
        cancel_btn = QPushButton(tr("auto.cloud_settings.4d0b4688", "取消"))
        btns.addButton(save_btn, QDialogButtonBox.AcceptRole)
        btns.addButton(cancel_btn, QDialogButtonBox.RejectRole)
        btn_layout.addWidget(btns)
        layout.addLayout(btn_layout)

        # 信号连接
        self.type_combo.currentIndexChanged.connect(self._on_type_changed)
        save_btn.clicked.connect(self._save)
        cancel_btn.clicked.connect(self.reject)

        # 加载当前配置
        self._load_settings()

    # ---------- 加载配置 ----------
    def _load_settings(self):
        """从 settings 加载当前配置到界面"""
        # 选择类型
        type_map = {"webdav": 0, "onedrive": 1, "googledrive": 2}
        idx = type_map.get(self.settings.cloud_type, 0)
        self.type_combo.setCurrentIndex(idx)
        self.stack.setCurrentIndex(idx)

        config = self.settings.cloud_config or {}

        # WebDAV
        if self.settings.cloud_type == "webdav":
            self.url_edit.setText(config.get("url", ""))
            self.user_edit.setText(config.get("username", ""))
            self.pwd_edit.setText(config.get("password", ""))
        # OneDrive
        elif self.settings.cloud_type == "onedrive":
            self.onedrive_token_edit.setText(config.get("access_token", ""))
        # Google Drive
        elif self.settings.cloud_type == "googledrive":
            self.gdrive_token_edit.setText(config.get("access_token", ""))

        # 通用选项
        self.enabled_check.setChecked(self.settings.cloud_enabled)
        self.auto_sync_check.setChecked(self.settings.cloud_auto_sync)

    # ---------- 类型切换 ----------
    def _on_type_changed(self, index):
        """切换存储类型时同步切换字段页"""
        self.stack.setCurrentIndex(index)

    # ---------- 保存 ----------
    def _save(self):
        """保存配置到 settings"""
        cloud_type = self.type_combo.currentData()
        config = {}

        # 按类型收集字段
        if cloud_type == "webdav":
            url = self.url_edit.text().strip()
            if url and not (url.startswith("http://") or url.startswith("https://")):
                QMessageBox.warning(self, tr("auto.cloud_settings.b859c7be", "错误"), tr("auto.cloud_settings.958c3e9e", "WebDAV 地址必须以 http:// 或 https:// 开头"))
                return
            config = {
                "url": url,
                "username": self.user_edit.text().strip(),
                "password": self.pwd_edit.text(),
            }
        elif cloud_type == "onedrive":
            token = self.onedrive_token_edit.text().strip()
            if not token and self.enabled_check.isChecked():
                QMessageBox.warning(self, tr("auto.cloud_settings.b859c7be", "错误"), tr("auto.cloud_settings.04ff1be7", "启用 OneDrive 需要填写 Access Token"))
                return
            config = {"access_token": token}
        elif cloud_type == "googledrive":
            token = self.gdrive_token_edit.text().strip()
            if not token and self.enabled_check.isChecked():
                QMessageBox.warning(self, tr("auto.cloud_settings.b859c7be", "错误"), tr("auto.cloud_settings.30570ad9", "启用 Google Drive 需要填写 Access Token"))
                return
            config = {"access_token": token}

        # 写入 settings
        self.settings.cloud_type = cloud_type
        self.settings.cloud_config = config
        self.settings.cloud_enabled = self.enabled_check.isChecked()
        self.settings.cloud_auto_sync = self.auto_sync_check.isChecked()

        try:
            self.settings.save()
        except Exception as e:
            logging.error(f"保存云存储设置失败: {e}")
            QMessageBox.warning(self, tr("auto.cloud_settings.b859c7be", "错误"), f"保存失败: {e}")
            return

        # 新增：重置云存储单例，使新配置立即生效
        try:
            from beeoffice.cloud import reset_cloud_storage
            reset_cloud_storage()
        except Exception as e:
            logging.error(f"重置云存储单例失败: {e}")

        QMessageBox.information(self, tr("auto.cloud_settings.cdfab96f", "已保存"), tr("auto.cloud_settings.cae5d135", "云存储设置已保存"))
        self.accept()

    # ---------- 测试连接 ----------
    def _test_connection(self):
        """
        测试当前配置的连接。

        修复（P1-38）：原实现在 GUI 线程里同步发网络请求，
        连接慢或超时时整个窗口卡死（最长 10 秒无响应）。
        现在参数校验留在主线程，真正的网络调用交给
        AsyncTaskManager 的线程池，结果回到主线程再弹窗。
        """
        cloud_type = self.type_combo.currentData()

        if cloud_type == "webdav":
            url = self.url_edit.text().strip()
            if not url:
                QMessageBox.warning(self, tr("auto.cloud_settings.ab3656a9", "提示"), tr("auto.cloud_settings.5f916474", "请先填写 WebDAV 地址"))
                return
            payload = (
                url,
                self.user_edit.text().strip(),
                self.pwd_edit.text(),
            )
        elif cloud_type == "onedrive":
            token = self.onedrive_token_edit.text().strip()
            if not token:
                QMessageBox.warning(self, tr("auto.cloud_settings.ab3656a9", "提示"), tr("auto.cloud_settings.fc8293e5", "请先填写 Access Token"))
                return
            payload = token
        elif cloud_type == "googledrive":
            token = self.gdrive_token_edit.text().strip()
            if not token:
                QMessageBox.warning(self, tr("auto.cloud_settings.ab3656a9", "提示"), tr("auto.cloud_settings.fc8293e5", "请先填写 Access Token"))
                return
            payload = token
        else:
            return

        from beeoffice.async_task import AsyncTaskManager

        if getattr(self, "_testing", False):
            return
        self._testing = True
        if hasattr(self, "test_btn"):
            self.test_btn.setEnabled(False)

        def finish():
            self._testing = False
            if hasattr(self, "test_btn"):
                self.test_btn.setEnabled(True)

        def on_result(code):
            finish()
            messages = {
                "webdav": tr("auto.cloud_settings.195b5ddf", "WebDAV 连接成功！"),
                "onedrive": tr("auto.cloud_settings.40c67fc1", "OneDrive 连接成功！"),
                "googledrive": tr("auto.cloud_settings.f6d9177d", "Google Drive 连接成功！"),
            }
            QMessageBox.information(
                self, tr("auto.cloud_settings.51991a5d", "成功"),
                messages.get(code, str(code)),
            )

        def on_error(err):
            finish()
            QMessageBox.warning(
                self, tr("auto.cloud_settings.3e3c8068", "失败"), err
            )

        AsyncTaskManager.run(
            self._probe_connection, cloud_type, payload,
            on_result=on_result, on_error=on_error,
        )

    @staticmethod
    def _probe_connection(cloud_type, payload):
        """
        **在 worker 线程执行**的连接探测。

        必须保持纯净：不碰任何 Qt 控件，只做网络请求并返回文本。
        """
        if cloud_type == "webdav":
            url, user, pwd = payload
            from webdav3.client import Client
            client = Client({
                "webdav_hostname": url,
                "webdav_login": user,
                "webdav_password": pwd,
            })
            client.check()
            return "webdav"

        import requests
        token = payload
        if cloud_type == "onedrive":
            resp = requests.get(
                "https://graph.microsoft.com/v1.0/me/drive/root",
                headers={"Authorization": f"Bearer {token}"},
                timeout=10,
            )
            if resp.status_code == 200:
                return "onedrive"
            raise RuntimeError(f"OneDrive 返回状态码: {resp.status_code}")

        resp = requests.get(
            "https://www.googleapis.com/drive/v3/about",
            headers={"Authorization": f"Bearer {token}"},
            params={"fields": "user"},
            timeout=10,
        )
        if resp.status_code == 200:
            return "googledrive"
        raise RuntimeError(f"Google Drive 返回状态码: {resp.status_code}")


def show_cloud_settings(parent=None):
    """
    显示云存储设置对话框（供外部调用）
    :param parent: 主窗口实例
    """
    dlg = CloudSettingsDialog(parent)
    dlg.exec()