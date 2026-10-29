# beeoffice/plugins/proofread_dialog.py
"""S2 校对体检 MVP：对当前 Writer 正文做规则检查（不依赖网络）。"""
from __future__ import annotations

import re
from dataclasses import dataclass

from PySide6.QtWidgets import (
    QDialog,
    QWidget,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QPushButton,
    QVBoxLayout,
)


@dataclass
class ProofIssue:
    line: int
    kind: str
    detail: str


def scan_text(text: str) -> list[ProofIssue]:
    """返回规则问题；行号从 1 开始。"""
    issues: list[ProofIssue] = []
    if not text:
        return issues
    for lineno, line in enumerate(text.splitlines(), 1):
        if re.search(r"[ \t]{2,}", line):
            issues.append(ProofIssue(lineno, "多余空格", line.strip()[:60]))
        if re.search(r"[，。；：！？]{2,}", line):
            issues.append(ProofIssue(lineno, "重复标点", line.strip()[:60]))
        if re.search(r"[\u4e00-\u9fff][,;:?!]", line):
            issues.append(ProofIssue(lineno, "中英文标点混用", line.strip()[:60]))
        if re.search(r"TODO|TBD|FIXME", line, re.IGNORECASE):
            issues.append(ProofIssue(lineno, "待办标记", line.strip()[:60]))
        if line.rstrip() != line:
            issues.append(ProofIssue(lineno, "行尾空白", line.strip()[:60]))
    return issues


class ProofreadDialog(QDialog):
    def __init__(self, app, parent=None):
        super().__init__(parent if isinstance(parent, QWidget) else None)
        self._app = app
        self.setWindowTitle("🔎 校对体检")
        self.resize(680, 480)
        self.summary = QLabel("点击“开始检查”")
        self.list = QListWidget()
        run_btn = QPushButton("开始检查")
        run_btn.clicked.connect(self.refresh)
        close_btn = QPushButton("关闭")
        close_btn.clicked.connect(self.reject)
        buttons = QHBoxLayout()
        buttons.addWidget(run_btn)
        buttons.addStretch()
        buttons.addWidget(close_btn)
        layout = QVBoxLayout(self)
        layout.addWidget(self.summary)
        layout.addWidget(self.list, 1)
        layout.addLayout(buttons)

    def _text(self) -> str:
        widget = None
        try:
            widget = self._app.tab_manager.currentWidget()
        except Exception:  # noqa: BLE001
            pass
        for attr in ("rich_editor", "markdown_editor", "text_edit", "editor"):
            editor = getattr(widget, attr, None)
            if editor is not None and hasattr(editor, "toPlainText"):
                return editor.toPlainText()
        return ""

    def refresh(self):
        issues = scan_text(self._text())
        self.list.clear()
        for issue in issues:
            self.list.addItem(
                f"第 {issue.line} 行 · {issue.kind}：{issue.detail}"
            )
        self.summary.setText(
            f"发现 {len(issues)} 处可改进项" if issues else "未发现明显问题"
        )
