# beeoffice/plugins/macro_console_dialog.py
"""宏控制台 UI（S3）：白名单命令 + 审计，无任意 Python 执行。"""
from __future__ import annotations

import json
import time
from pathlib import Path

from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
)

from beeoffice.macro_console import (
    MacroAudit,
    MacroError,
    MacroRegistry,
    MacroRunner,
    load_script,
    mark_risk_ack,
    needs_risk_ack,
    save_script,
    validate_steps,
)


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
    def _optional(name):
        def handler(**kwargs):
            method = getattr(app, name, None)
            if method is None:
                raise RuntimeError(f"当前入口不可用: {name}")
            return method(**kwargs)
        return handler

    def _current(name):
        def handler(**kwargs):
            view = app.tab_manager.currentWidget()
            method = getattr(view, name, None) if view is not None else None
            if method is None:
                raise RuntimeError(f"当前标签页不支持: {name}")
            return method()
        return handler

    def _pdf_merge(srcs, out):
        from beeoffice import pdf_tools
        return pdf_tools.merge_pdfs(srcs, out)

    def _pdf_compress(src, out):
        from beeoffice import pdf_tools
        return pdf_tools.compress_pdf(src, out)

    reg.register("ui.templates", _optional("_show_template_picker"),
                 description="打开模板与素材中心")
    reg.register("file.save", _optional("_save_current"),
                 description="保存当前文档")
    reg.register("file.save_as", _optional("_save_as_current"),
                 description="另存当前文档")
    reg.register("sheet.sort", _current("_show_sort_dialog"),
                 description="打开排序对话框")
    reg.register("pdf.merge", _pdf_merge,
                 description="合并 PDF：srcs, out",
                 required_args=("srcs", "out"))
    reg.register("pdf.compress", _pdf_compress,
                 description="压缩 PDF：src, out",
                 required_args=("src", "out"))
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

        self.script_edit = QTextEdit()
        self.script_edit.setMaximumHeight(130)
        self.script_edit.setPlaceholderText(
            '脚本步骤 JSON：[{"command": "macro.wait", "args": {"seconds": 1}}]'
        )
        import_btn = QPushButton("导入脚本…")
        export_btn = QPushButton("导出脚本…")
        run_script_btn = QPushButton("回放脚本")
        import_btn.clicked.connect(self._import_script)
        export_btn.clicked.connect(self._export_script)
        run_script_btn.clicked.connect(self._run_script)
        script_row = QHBoxLayout()
        script_row.addWidget(import_btn)
        script_row.addWidget(export_btn)
        script_row.addWidget(run_script_btn)
        script_row.addStretch()

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("只支持白名单命令；每次执行写入审计日志。"))
        layout.addLayout(row)
        layout.addWidget(self.args)
        layout.addWidget(self.script_edit)
        layout.addLayout(script_row)
        layout.addWidget(self.output, 1)

    def _ensure_risk(self) -> bool:
        if not needs_risk_ack():
            return True
        answer = QMessageBox.warning(
            self, "宏控制台风险提示",
            "宏只能执行白名单命令，但仍会修改当前文档/文件。\n"
            "请确认脚本来源可信后再运行。",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if answer != QMessageBox.Yes:
            self.output.append("✗ 已取消：未确认风险")
            return False
        mark_risk_ack()
        return True

    def _run(self):
        if not self._ensure_risk():
            return
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

    def _import_script(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "导入宏脚本", "", "JSON (*.json);;所有文件 (*)"
        )
        if not path:
            return
        try:
            steps = load_script(path)
        except MacroError as e:
            self.output.append(f"✗ 导入失败：{e}")
            return
        self.script_edit.setPlainText(json.dumps(
            {"steps": steps}, ensure_ascii=False, indent=2
        ))
        self.output.append(f"✅ 已导入 {len(steps)} 步脚本")

    def _export_script(self):
        try:
            steps = validate_steps(json.loads(
                self.script_edit.toPlainText().strip() or "[]"
            ))
        except Exception as e:  # noqa: BLE001
            self.output.append(f"✗ 脚本格式错误：{e}")
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "导出宏脚本", "macro.json", "JSON (*.json)"
        )
        if not path:
            return
        save_script(path, steps)
        self.output.append(f"✅ 已导出 {len(steps)} 步脚本：{path}")

    def _run_script(self):
        if not self._ensure_risk():
            return
        try:
            steps = validate_steps(json.loads(
                self.script_edit.toPlainText().strip() or "[]"
            ))
        except Exception as e:  # noqa: BLE001
            self.output.append(f"✗ 脚本格式错误：{e}")
            return
        results = MacroRunner(self.registry, self.audit).run(steps)
        self.output.append(f"✅ 回放完成：{len(results)} 步")
