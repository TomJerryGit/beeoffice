# beeoffice/plugins/beeshow_sync_mixin.py
"""
蜜演远程同步 Mixin（任务 4.3）

职责：
  - _toggle_sync_mode     : 开启 / 关闭同步演示
  - _broadcast_slide      : 广播翻页
  - _broadcast_laser      : 广播激光笔位置
  - _broadcast_black_screen : 广播黑屏
  - _show_sync_dialog     : 显示二维码和观众链接

设计：
  - 演示者开启同步模式后，每次翻页自动广播
  - 观众通过二维码或链接访问
  - 演示状态由 SyncServer 缓存，新观众加入时自动同步

对标：
  - WPS 365「观众扫码实时跟随翻页」

依赖：
  - PySide6（QMessageBox / QDialog / QVBoxLayout / QLabel /
             QPushButton / QTimer）
  - beeshow_sync_server.SyncServer

注意：
  - 不导入其他 beeshow_* Mixin
  - 服务器运行在独立线程，UI 不阻塞
  - 关闭蜜演时需调 _stop_sync_server
"""

import logging

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QMessageBox,
)
from PySide6.QtCore import Qt, QTimer

from beeoffice.plugins.beeshow_sync_server import SyncServer


class SyncMixin:
    """蜜演远程同步 Mixin"""

    # ==================== 初始化 ====================
    def _init_sync_state(self):
        """初始化同步状态（由 BeeShowView._init_state 调用）"""
        self._sync_server = None
        self._sync_enabled = False
        self._sync_url = ""
        # 激光笔节流：最多 20 次/秒
        self._last_laser_broadcast = 0.0
        self._laser_throttle_interval = 0.05

    # ==================== 开启 / 关闭 ====================
    def _toggle_sync_mode(self):
        """开启 / 关闭同步演示"""
        if self._sync_enabled:
            self._stop_sync_mode()
        else:
            self._start_sync_mode()

    def _start_sync_mode(self):
        """开启同步演示"""
        if not self._slides_html:
            QMessageBox.information(
                self, "提示", "请先编写幻灯片内容"
            )
            return

        try:
            # 创建并启动服务器
            # 优化规划 §1.4：同步演示的本意就是让局域网里的观众观看，所以这里
            # 显式开启局域网访问；但访问已由一次性令牌保护（令牌只出现在演示端
            # 给出的观众 URL 里），不再是无鉴权的裸服务。
            self._sync_server = SyncServer(
                http_port=8765,
                ws_port=8766,
                allow_lan=True,
            )
            # 优化规划 §2.7：把幻灯片内容交给服务器。原实现从未调用
            # set_slides_html()，于是 /api/slide/<idx> 恒返回「（无此页）」——
            # 观众端只有页码在跳，画面永远是空的。
            self._sync_server.set_slides_html(self._slides_html)
            if not self._sync_server.start():
                QMessageBox.warning(
                    self, "启动失败",
                    "同步服务器启动失败。\n\n"
                    "可能原因：\n"
                    "• 端口 8765 / 8766 已被占用\n"
                    "• 防火墙阻止了监听\n\n"
                    "请检查后重试。"
                )
                self._sync_server = None
                return

            self._sync_enabled = True
            self._sync_server.on_control = self._remote_control
            self._sync_url = self._sync_server.get_viewer_url()

            # 广播当前状态
            self._broadcast_slide()

            # 显示对话框
            self._show_sync_dialog()

            self._set_status(
                f"📱 同步演示已开启（{self._sync_url}）", 5000
            )

        except Exception as e:
            logging.error(f"开启同步失败：{e}")
            QMessageBox.warning(self, "失败", str(e))
            self._stop_sync_mode()

    def _remote_control(self, action: str):
        """手机遥控：next/prev/black/end。"""
        if action == "next":
            self._show_slide(min(
                getattr(self, "_current_slide", 0) + 1,
                max(0, len(getattr(self, "_slides_html", [])) - 1),
            ))
        elif action == "prev":
            self._show_slide(max(0, getattr(self, "_current_slide", 0) - 1))
        elif action == "black":
            self._broadcast_black_screen(True)
        elif action == "end":
            self._stop_sync_mode()

    def _stop_sync_mode(self):
        """关闭同步演示"""
        if self._sync_server is not None:
            try:
                self._sync_server.stop()
            except Exception as e:
                logging.error(f"停止同步服务器失败：{e}")
            self._sync_server = None

        self._sync_enabled = False
        self._sync_url = ""
        self._set_status("📱 同步演示已关闭", 2000)

    # ==================== 广播 ====================
    def _broadcast_slide(self):
        """广播当前页"""
        if not self._sync_enabled or self._sync_server is None:
            return
        try:
            self._sync_server.broadcast_slide(
                index=self._current_slide,
                total=len(self._slides_html),
            )
        except Exception as e:
            logging.error(f"广播翻页失败：{e}")

    def _broadcast_laser(
        self, x: float, y: float, visible: bool = True
    ):
        """
        广播激光笔位置（带节流）。

        :param x, y: 归一化坐标（0.0 ~ 1.0）
        :param visible: 是否可见
        """
        if not self._sync_enabled or self._sync_server is None:
            return

        import time
        now = time.time()
        if now - self._last_laser_broadcast < \
                self._laser_throttle_interval:
            return
        self._last_laser_broadcast = now

        try:
            self._sync_server.broadcast_laser(x, y, visible)
        except Exception as e:
            logging.error(f"广播激光笔失败：{e}")

    def _broadcast_black_screen(self, visible: bool):
        """广播黑屏"""
        if not self._sync_enabled or self._sync_server is None:
            return
        try:
            self._sync_server.broadcast_black_screen(visible)
        except Exception as e:
            logging.error(f"广播黑屏失败：{e}")

    def _broadcast_theme(self, theme: str):
        """广播主题切换"""
        if not self._sync_enabled or self._sync_server is None:
            return
        try:
            self._sync_server.broadcast_theme(theme)
        except Exception as e:
            logging.error(f"广播主题失败：{e}")

    # ==================== 观众对话框 ====================
    def _show_sync_dialog(self):
        """显示同步演示对话框（含链接和观众数）"""
        if self._sync_server is None:
            return

        dlg = QDialog(self)
        dlg.setWindowTitle("📱 同步演示")
        dlg.resize(480, 360)
        layout = QVBoxLayout(dlg)

        # 标题
        title = QLabel("📱 观众扫码或访问链接")
        title.setStyleSheet(
            "QLabel{font-size:15px;font-weight:bold;"
            "color:#E65100;padding:8px;}"
        )
        layout.addWidget(title)

        # 观众 URL
        url_label = QLabel(self._sync_url)
        url_label.setStyleSheet(
            "QLabel{background:#F5F5F5;padding:12px;"
            "font-family:Consolas;font-size:14px;"
            "border-radius:4px;color:#0D47A1;}"
        )
        url_label.setTextInteractionFlags(
            Qt.TextSelectableByMouse
        )
        url_label.setWordWrap(True)
        layout.addWidget(url_label)

        # 复制按钮
        copy_btn = QPushButton("📋 复制链接")
        copy_btn.clicked.connect(
            lambda: self._copy_to_clipboard(self._sync_url)
        )
        layout.addWidget(copy_btn)

        # 观众数
        viewer_label = QLabel("👥 当前观众：0")
        viewer_label.setStyleSheet(
            "QLabel{padding:8px;font-size:13px;color:#555;}"
        )
        layout.addWidget(viewer_label)

        # 定时刷新观众数
        timer = QTimer(dlg)
        timer.timeout.connect(
            lambda: viewer_label.setText(
                f"👥 当前观众："
                f"{self._sync_server.viewer_count if self._sync_server else 0}"
            )
        )
        timer.start(2000)

        # 提示
        tip = QLabel(
            "💡 观众手机需与电脑在同一局域网。\n"
            "   演示者的翻页、激光笔、黑屏操作会同步显示。"
        )
        tip.setStyleSheet(
            "QLabel{color:#666;font-size:12px;padding:8px;"
            "background:#FFF8E1;border-radius:4px;}"
        )
        tip.setWordWrap(True)
        layout.addWidget(tip)

        layout.addStretch()

        # 底部按钮
        bl = QHBoxLayout()
        bl.addStretch()

        close_btn = QPushButton("关闭对话框")
        close_btn.clicked.connect(dlg.reject)
        bl.addWidget(close_btn)

        stop_btn = QPushButton("🛑 停止同步")
        stop_btn.setStyleSheet(
            "QPushButton{background:#FFEBEE;color:#B71C1C;"
            "border:1px solid #F44336;padding:6px 16px;"
            "border-radius:4px;}"
            "QPushButton:hover{background:#FFCDD2;}"
        )

        def do_stop():
            self._stop_sync_mode()
            dlg.accept()

        stop_btn.clicked.connect(do_stop)
        bl.addWidget(stop_btn)

        layout.addLayout(bl)
        dlg.exec()

    def _copy_to_clipboard(self, text: str):
        """复制文本到剪贴板"""
        try:
            from PySide6.QtWidgets import QApplication
            QApplication.clipboard().setText(text)
            self._set_status("✅ 链接已复制到剪贴板", 2000)
        except Exception as e:
            logging.error(f"复制失败：{e}")

    # ==================== 清理 ====================
    def _cleanup_sync(self):
        """清理（由 closeEvent 调用）"""
        if self._sync_server is not None:
            try:
                self._sync_server.stop()
            except Exception:
                pass
            self._sync_server = None
        self._sync_enabled = False