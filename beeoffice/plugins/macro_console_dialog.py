# beeoffice/plugins/macro_console_dialog.py
"""宏控制台 UI（S3）：白名单命令 + 审计，无任意 Python 执行。"""
from __future__ import annotations

import json
import time
from pathlib import Path

from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
)

from beeoffice.macro_console import MacroAudit, MacroRegistry


def default_audit_path() -> Path:
    return Path.home() / ".beeoffice" / "macro_audit.jsonl"


def build_registry(app) -> MacroRegistry:
    reg = MacroRegistry()

    def _call(name):
        def handler():
            method = getattr(app, name, None)
            if method is None:
                raise RuntimeError(f"当前入口不可用: {name}")
            return method()
        return handler

    reg.register("ui.pdf_toolbox", _call("show_pdf_toolbox"),
                 description="打开 PDF 工具箱")
    reg.register("ui.data_toolbox", _call("show_data_toolbox"),
                 description="打开数据工具箱")
    reg.register("ui.proofread", _call("show_proofread_dialog"),
                 description="打开校对体检")
    reg.register("ui.ai_pane", _call("show_ai_task_pane"),
                 description="打开 AI 任务窗格")
    reg.register("ui.master", _call("show_beeshow_master_dialog"),
                 description="打开蜜演母版设置")
    reg.register("macro.wait", lambda seconds=0.2: time.sleep(
        max(0.0, min(10.0, float(seconds)))
    ), description="等待（0-10 秒）", required_args=())
    return reg


class MacroConsoleDialog(QDialog):
    def __init__(self, app, parent=None):
        super().__init__(parent)
        self._app = app
        self.registry = build_registry(app)
        self.audit = MacroAudit(default_audit_path())
        self.setWindowTitle("⚙ 宏控制台（白名单）")
        self.resize(620, 460)

        self.combo = QComboBox()
        self.combo.addItems(self.registry.ids())
        self.args = QLineEdit()
        self.args.setPlaceholderText('参数 JSON，如 {"seconds": 1}')
        self.output = QTextEdit()
        self.output.setReadOnly(True)
        run = QPushButton("执行")
        run.clicked.connect(self._run)
        close = QPushButton("关闭")
        close.clicked.connect(self.reject)
        row = QHBoxLayout()
        row.addWidget(QLabel("命令:"))
        row.addWidget(self.combo, 1)
        row.addWidget(run)
        row.addWidget(close)
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("只支持白名单命令；每次执行写入审计日志。"))
        layout.addLayout(row)
        layout.addWidget(self.args)
        layout.addWidget(self.output, 1)

    def _run(self):
        try:
            raw = self.args.text().strip() or "{}"
            kwargs = json.loads(raw)
        except json.JSONDecodeError as e:
            self.output.append(f"✗ 参数 JSON 错误: {e}")
            return
        command = self.combo.currentText()
        try:
            result = self.registry.execute(command, kwargs, self.audit)
            self.output.append(f"✅ {command} → {result}")
        except Exception as e:  # noqa: BLE001
            self.output.append(f"✗ {command} 失败: {type(e).__name__}: {e}")
