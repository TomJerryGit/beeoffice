# beeoffice/backup_center.py
"""
**备份与恢复中心**（R6 的界面部分；核心逻辑在 `backup.py`，不依赖 Qt）。

职责：
  · 列出某文件（或全部）的历史备份
  · 恢复 / 另存为 / 删除 / 全部清理 / 打开备份目录

设计取舍：
  · **"恢复"是破坏性操作** → 先 `question` 确认，且 `BackupStore.restore()`
    会**先给当前内容留一份**（`before_restore`），所以恢复本身也能回退。
  · 恢复后**不自动重载**编辑区 —— 由调用方决定（app 会问用户是否立即重开），
    避免"文件被换掉了但界面还是旧的"这种更迷惑的状态。
"""
import logging
from pathlib import Path

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QAbstractItemView, QDialog, QDialogButtonBox, QFileDialog, QHBoxLayout,
    QHeaderView, QLabel, QMessageBox, QPushButton, QTableWidget,
    QTableWidgetItem, QVBoxLayout,
)

from beeoffice.backup import BackupStore, BackupVersion


class BackupCenterDialog(QDialog):
    """历史版本列表 + 恢复操作。"""

    def __init__(self, parent=None, store=None, source=None):
        super().__init__(parent)
        self.store = store if store is not None else BackupStore()
        self.source = Path(source) if source else None
        self.restored_path = None          # 恢复成功后由调用方读取

        self.setWindowTitle("🗂️ 备份与恢复")
        self.resize(760, 460)
        self._build_ui()
        self.refresh()

    # ------------------------------------------------------------------
    def _build_ui(self):
        layout = QVBoxLayout(self)

        title = (f"当前文件：{self.source.name}" if self.source
                 else "所有文件的备份")
        self.summary = QLabel(title)
        layout.addWidget(self.summary)

        self.notice = QLabel(
            "每次自动保存/手动保存**之前**都会自动留一份；也可随时点"
            "「立即备份」。恢复时也会先给当前内容留一份，所以恢复错了还能再回来。"
        )
        self.notice.setWordWrap(True)
        self.notice.setStyleSheet("color:#666;font-size:12px;")
        layout.addWidget(self.notice)

        self.table = QTableWidget(0, 4, self)
        self.table.setHorizontalHeaderLabels(["时间", "文件", "原因", "大小"])
        self.table.setEditTriggers(
            QAbstractItemView.EditTrigger.NoEditTriggers
        )
        self.table.setSelectionBehavior(
            QAbstractItemView.SelectionBehavior.SelectRows
        )
        self.table.setSelectionMode(
            QAbstractItemView.SelectionMode.SingleSelection
        )
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        self.table.doubleClicked.connect(self.restore_selected)
        layout.addWidget(self.table)

        row = QHBoxLayout()
        self.restore_btn = QPushButton("恢复")
        self.restore_btn.setToolTip(
            "把选中的备份恢复到当前文件（恢复前会再留一份现有内容）"
        )
        self.restore_btn.clicked.connect(self.restore_selected)
        self.save_as_btn = QPushButton("另存为…")
        self.save_as_btn.clicked.connect(self.save_selected_as)
        self.open_dir_btn = QPushButton("打开备份目录")
        self.open_dir_btn.clicked.connect(self.open_backup_dir)
        self.delete_btn = QPushButton("删除")
        self.delete_btn.clicked.connect(self.delete_selected)
        self.clean_btn = QPushButton("清理旧备份")
        self.clean_btn.clicked.connect(self.clean_old)
        for button in (self.restore_btn, self.save_as_btn,
                       self.open_dir_btn, self.delete_btn, self.clean_btn):
            row.addWidget(button)
        row.addStretch(1)
        layout.addLayout(row)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    # ------------------------------------------------------------------
    def refresh(self):
        versions = (self.store.list_versions(self.source) if self.source
                    else self.store.list_all())
        self.versions = versions
        self.table.setRowCount(len(versions))
        reason_text = {
            "before_save": "保存前自动",
            "auto": "自动备份",
            "manual": "手动备份",
            "before_restore": "恢复前",
        }
        for row, version in enumerate(versions):
            self.table.setItem(row, 0, QTableWidgetItem(version.display_time()))
            self.table.setItem(row, 1, QTableWidgetItem(version.source))
            self.table.setItem(
                row, 2,
                QTableWidgetItem(reason_text.get(version.reason, version.reason)),
            )
            self.table.setItem(row, 3, QTableWidgetItem(version.size_text()))

        if not versions:
            self.summary.setText(
                (f"当前文件：{self.source.name}　—　"
                 if self.source else "")
                + "还没有备份（保存一次后就会出现）"
            )
        else:
            total = self.store.total_size()
            self.summary.setText(
                (f"当前文件：{self.source.name}　—　" if self.source else "")
                + f"共 {len(versions)} 份备份，合计约 {total / 1024:.0f} KB"
            )
        self._update_buttons()

    def _update_buttons(self):
        enabled = bool(self.versions)
        for button in (self.restore_btn, self.save_as_btn,
                       self.delete_btn, self.clean_btn):
            button.setEnabled(enabled)
        self.restore_btn.setEnabled(bool(self.versions) and self.source is not None)

    def current_version(self):
        rows = self.table.selectionModel().selectedRows()
        if not rows:
            return None
        row = rows[0].row()
        if 0 <= row < len(self.versions):
            return self.versions[row]
        return None

    # ------------------------------------------------------------------
    # 操作
    # ------------------------------------------------------------------
    def restore_selected(self, *_args):
        version = self.current_version()
        if version is None or self.source is None:
            return
        reply = QMessageBox.question(
            self, "确认恢复",
            f"用这份备份覆盖当前文件？\n\n"
            f"备份时间：{version.display_time()}\n"
            f"目标文件：{self.source}\n\n"
            "（恢复前会自动再留一份当前内容，恢复错了还能回来）",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return
        if self.store.restore(version, self.source):
            self.restored_path = self.source
            QMessageBox.information(
                self, "已恢复",
                f"已把 {version.display_time()} 的备份恢复到：\n{self.source}\n\n"
                "如需在编辑器里看到结果，请重新打开该文件。",
            )
            self.refresh()
        else:
            QMessageBox.warning(self, "恢复失败", "无法写入目标文件（可能被占用）。")

    def save_selected_as(self):
        version = self.current_version()
        if version is None:
            return
        target, _ = QFileDialog.getSaveFileName(
            self, "另存备份为", version.source, "所有文件 (*)",
        )
        if not target:
            return
        try:
            import shutil

            shutil.copy2(version.path, target)
        except Exception as e:  # noqa: BLE001
            logging.error(f"[备份] 另存失败：{e}")
            QMessageBox.warning(self, "另存失败", str(e))
            return
        QMessageBox.information(self, "已另存", f"已保存到：\n{target}")

    def delete_selected(self):
        version = self.current_version()
        if version is None:
            return
        if self.store.delete(version):
            self.refresh()

    def clean_old(self):
        """按保留策略清理（与自动轮转同一套规则）。"""
        removed = self.store.prune(self.source)
        self.refresh()
        QMessageBox.information(
            self, "清理完成",
            f"已清理 {removed} 份旧备份（每个文件保留最近 "
            f"{self.store.keep} 份）。",
        )

    def open_backup_dir(self):
        target = (self.store.folder_for(self.source) if self.source
                  else self.store.root)
        try:
            target.mkdir(parents=True, exist_ok=True)
        except Exception as e:  # noqa: BLE001
            QMessageBox.warning(self, "打不开", str(e))
            return
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(target)))


def show_backup_center(parent=None, source=None,
                       store=None) -> BackupCenterDialog:
    """显示备份中心；返回对话框（调用方读 `restored_path` 判断是否恢复过）。"""
    dialog = BackupCenterDialog(parent, store=store, source=source)
    dialog.exec()
    return dialog
