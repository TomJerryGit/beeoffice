# beeoffice/webdav.py
"""
WebDAV 专用模块：提供 WebDAV 配置对话框与快速同步入口
（通用云存储设置请使用 beeoffice.cloud_settings）
"""
import logging
from pathlib import Path

from PySide6.QtWidgets import (
    QDialog, QFormLayout, QLineEdit, QCheckBox,
    QDialogButtonBox, QPushButton, QMessageBox, QProgressDialog
)
from PySide6.QtCore import Qt

from beeoffice.plugins.webdav_sync import WebDAVConfig
from beeoffice.async_task import AsyncTaskManager
from beeoffice.i18n import tr


def show_webdav_settings(parent):
    """
    显示 WebDAV 专用设置对话框（兼容旧入口）
    :param parent: 主窗口实例
    """
    config = WebDAVConfig()
    dlg = QDialog(parent)
    dlg.setWindowTitle(tr("auto.webdav.2d9894f5", "☁️ WebDAV 设置"))
    dlg.resize(420, 260)
    form = QFormLayout(dlg)

    # 地址
    url = QLineEdit(config.url)
    url.setPlaceholderText("https://example.com/webdav")
    form.addRow("地址:", url)

    # 用户名
    user = QLineEdit(config.username)
    form.addRow("用户名:", user)

    # 密码
    pwd = QLineEdit(config.password)
    pwd.setEchoMode(QLineEdit.Password)
    form.addRow("密码:", pwd)

    # 自动同步
    auto = QCheckBox(tr("auto.webdav.e4bdc666", "启动时自动同步"))
    auto.setChecked(config.auto_sync)
    form.addRow(auto)

    # 启用
    enabled = QCheckBox(tr("auto.webdav.7693437d", "启用 WebDAV 同步"))
    enabled.setChecked(config.enabled)
    form.addRow(enabled)

    # 按钮
    btns = QDialogButtonBox()
    save_btn = QPushButton(tr("auto.webdav.fadf24db", "保存"))
    test_btn = QPushButton(tr("auto.webdav.10b7d8ec", "测试连接"))
    cancel_btn = QPushButton(tr("auto.webdav.4d0b4688", "取消"))
    btns.addButton(save_btn, QDialogButtonBox.AcceptRole)
    btns.addButton(test_btn, QDialogButtonBox.ActionRole)
    btns.addButton(cancel_btn, QDialogButtonBox.RejectRole)
    form.addRow(btns)

    def save_config():
        """保存配置"""
        text_url = url.text().strip()
        # 校验 URL
        if text_url and not (text_url.startswith("http://") or text_url.startswith("https://")):
            QMessageBox.warning(dlg, tr("auto.webdav.b859c7be", "错误"), tr("auto.webdav.6f7b037c", "地址必须以 http:// 或 https:// 开头"))
            return
        config.url = text_url
        config.username = user.text().strip()
        config.password = pwd.text()
        config.auto_sync = auto.isChecked()
        config.enabled = enabled.isChecked()
        config.save()
        QMessageBox.information(dlg, tr("auto.webdav.cdfab96f", "已保存"), tr("auto.webdav.6bbe8892", "WebDAV 设置已保存"))
        dlg.accept()

    def test_connection():
        """测试连接"""
        if not url.text().strip():
            QMessageBox.warning(dlg, tr("auto.webdav.ab3656a9", "提示"), tr("auto.webdav.c0d8905a", "请先填写地址"))
            return
        try:
            from webdav3.client import Client
            client = Client({
                "webdav_hostname": url.text().strip(),
                "webdav_login": user.text().strip(),
                "webdav_password": pwd.text(),
            })
            client.check()
            QMessageBox.information(dlg, tr("auto.webdav.51991a5d", "成功"), tr("auto.webdav.7ae0ea69", "连接成功！"))
        except Exception as e:
            QMessageBox.warning(dlg, tr("auto.webdav.3e3c8068", "失败"), f"连接失败：\n{e}")

    save_btn.clicked.connect(save_config)
    test_btn.clicked.connect(test_connection)
    cancel_btn.clicked.connect(dlg.reject)

    dlg.exec()


def sync_now(parent):
    """
    立即执行 WebDAV 同步（带进度对话框）
    :param parent: 主窗口实例
    """
    config = WebDAVConfig()
    if not config.enabled:
        QMessageBox.information(parent, tr("auto.webdav.ab3656a9", "提示"), tr("auto.webdav.abf804ca", "请先配置并启用 WebDAV"))
        return
    if not config.url:
        QMessageBox.information(parent, tr("auto.webdav.ab3656a9", "提示"), tr("auto.webdav.253a128f", "WebDAV 地址未配置"))
        return

    # 防止重复同步
    worker_ref = getattr(parent, '_sync_worker', None)
    if worker_ref is not None and worker_ref.isRunning():
        QMessageBox.information(parent, tr("auto.webdav.ab3656a9", "提示"), tr("auto.webdav.8a6b5672", "同步正在进行中"))
        return

    # 进度对话框
    progress_dlg = QProgressDialog("正在同步...", "取消", 0, 100, parent)
    progress_dlg.setWindowTitle(tr("auto.webdav.936653fe", "WebDAV 同步"))
    progress_dlg.setWindowModality(Qt.WindowModal)
    progress_dlg.setMinimumDuration(0)
    progress_dlg.setValue(0)

    # 创建同步 worker
    from beeoffice.plugins.webdav_sync import WebDAVSyncWorker
    worker = WebDAVSyncWorker(
        config.url,
        config.username,
        config.password,
        str(Path.home() / ".beeoffice_data"),
        "/beeoffice",
        "both"
    )
    parent._sync_worker = worker

    # 连接信号
    if hasattr(worker, 'progress'):
        worker.progress.connect(progress_dlg.setValue)
    worker.finished.connect(
        lambda success, msg, count: _on_sync_finished(parent, progress_dlg, success, msg)
    )
    progress_dlg.canceled.connect(worker.cancel)

    worker.start()


def _on_sync_finished(parent, progress_dlg, success, msg):
    """同步完成回调"""
    try:
        progress_dlg.close()
    except Exception:
        pass
    parent._sync_worker = None
    if success:
        QMessageBox.information(parent, tr("auto.webdav.33246f6a", "完成"), msg)
        if hasattr(parent, 'set_global_status'):
            parent.set_global_status(msg, 3000)
    else:
        QMessageBox.warning(parent, tr("auto.webdav.5521e368", "警告"), msg)
        if hasattr(parent, 'set_global_status'):
            parent.set_global_status(tr("auto.webdav.a8f14c99", "同步失败"), 3000)