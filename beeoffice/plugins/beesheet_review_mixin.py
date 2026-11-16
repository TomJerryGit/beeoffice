"""BeeSheet 审阅 Mixin：保护、批注查看、基础拼写检查。"""
from __future__ import annotations

import re

from PySide6.QtWidgets import (
    QAbstractItemView, QInputDialog, QLineEdit, QMessageBox,
)

from beeoffice.i18n import tr


class ReviewMixin:
    """BeeSheet 审阅功能。"""

    def _ensure_review_state(self):
        if not hasattr(self, "_sheet_protected"):
            self._sheet_protected = False
            self._workbook_protected = False
            self._sheet_password = ""

    def _toggle_sheet_protection(self):
        self._ensure_review_state()
        if self._sheet_protected:
            pwd, ok = QInputDialog.getText(
                self, "取消保护", "输入工作表密码：", QLineEdit.Password
            )
            if not ok:
                return
            if pwd != self._sheet_password:
                QMessageBox.warning(self, "取消保护", "密码不正确。")
                return
            self._sheet_protected = False
            self.table_view.setEditTriggers(
                QAbstractItemView.DoubleClicked
                | QAbstractItemView.EditKeyPressed
                | QAbstractItemView.AnyKeyPressed
            )
            self._set_status("工作表保护已取消", 2000)
            return

        pwd, ok = QInputDialog.getText(
            self, "保护工作表", "设置工作表密码（可留空）：", QLineEdit.Password
        )
        if not ok:
            return
        self._sheet_protected = True
        self._sheet_password = pwd or ""
        self.table_view.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self._set_status("工作表已保护", 2000)

    def _toggle_workbook_protection(self):
        self._ensure_review_state()
        if self._workbook_protected:
            pwd, ok = QInputDialog.getText(
                self, "取消工作簿保护", "输入工作簿密码：",
                QLineEdit.Password,
            )
            if not ok:
                return
            if pwd != self._sheet_password:
                QMessageBox.warning(self, "取消工作簿保护", "密码不正确。")
                return
            self._workbook_protected = False
            self._set_status("工作簿保护已取消", 2000)
            return
        pwd, ok = QInputDialog.getText(
            self, "保护工作簿", "设置工作簿密码（可留空）：",
            QLineEdit.Password,
        )
        if not ok:
            return
        self._workbook_protected = True
        self._sheet_password = pwd or ""
        self._set_status("工作簿已保护", 2000)

    def _show_comments_list(self):
        comments = getattr(self, "_cell_comments", {})
        if not comments:
            QMessageBox.information(self, "批注", "当前工作表没有批注。")
            return
        lines = []
        for (r, c), text in sorted(comments.items())[:30]:
            lines.append(f"{r + 1} 行 {c + 1} 列：{text}")
        QMessageBox.information(self, "批注列表", "\n".join(lines))

    _COMMON_TYPOS = {
        "teh": "the", "recieve": "receive", "adress": "address",
        "seperate": "separate", "occured": "occurred",
        "definately": "definitely", "wierd": "weird",
    }

    def _spell_check(self):
        """基础英文拼写检查：检查选中单元格中的常见拼写错误。"""
        indexes = self.table_view.selectionModel().selectedIndexes()
        if not indexes:
            QMessageBox.information(self, "拼写检查", "请先选择要检查的单元格。")
            return
        problems = []
        for idx in indexes:
            value = self.model.get_value(idx.row(), idx.column())
            if value is None:
                continue
            for word in re.findall(r"[A-Za-z]{3,}", str(value)):
                fix = self._COMMON_TYPOS.get(word.lower())
                if fix:
                    problems.append(f"{word} → {fix}")
        if problems:
            QMessageBox.information(
                self, "拼写检查",
                "发现常见拼写问题：\n" + "\n".join(problems[:20]),
            )
        else:
            self._set_status(
                tr("auto.beesheet_review.ok", "拼写检查完成：未发现常见问题"),
                3000,
            )
