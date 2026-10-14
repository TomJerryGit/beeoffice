# beeoffice/plugins/beewrite_spellcheck_dialog.py
"""
蜜写的**拼写检查**（按需，不做常驻红波浪线）。

为什么是"按需对话框"而不是"边打字边标红"
------------------------------------------
实测（装上真英文词典后，对 `tests/fidelity/corpus/` 里的真实**中文技术文档**
逐字跑一遍）：**误报 619 处** —— `CentOS`、`mysql`、`yum`、`Xshell`、`VMware`、
`ens33`、`iptables` 这类技术词/产品名全被判为拼写错误。

    CentOS7 环境 mysql的安装与使用     313 处
    yum源更新                         217 处
    修改Centos7网卡 ens33 为 eth0       60 处
    Win710 上使用 Xshell 连接 VMware     18 处
    …（7 份合计 619）

**常驻波浪线会让用户满屏红字**，这不叫功能，叫骚扰。所以本模块的形态是：

  · 用户**主动**点「拼写检查」才跑；
  · 结果进**列表**，逐条给建议，可 替换 / 全部替换 / 忽略 / **全部忽略** /
    **加入词典**（写入用户词典后永久生效）；
  · 技术文档里几百个技术词，用户点几次"全部忽略/加入词典"就干净了 ——
    这是"知情 + 可控"，而不是把噪音强加给用户。

（Word 的拼写检查也是这个形态：对话框 + 忽略全部 + 自定义词典。）
"""
import logging
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView, QComboBox, QDialog, QDialogButtonBox, QHBoxLayout,
    QHeaderView, QLabel, QMessageBox, QPushButton, QTableWidget,
    QTableWidgetItem, QVBoxLayout,
)

#: 用户词典路径（与设置文件同目录，沿用本项目约定）
USER_DICTIONARY_NAME = ".beeoffice_dictionary.txt"


def user_dictionary_path() -> Path:
    """用户自定义词典的默认路径。"""
    return Path.home() / USER_DICTIONARY_NAME


class SpellCheckDialog(QDialog):
    """
    拼写检查对话框。

    设计成"依赖注入"式：**不直接读编辑器**，而是拿
      · `service`：拼写检查服务（测试里可注入桩后端）
      · `text`：要检查的纯文本（下标与编辑器文档位置一致）
      · `apply_replace(start, end, replacement)`：由调用方执行替换
    这样对话框的全部逻辑都能在没有编辑器、没有真实词典的环境里测。
    """

    def __init__(self, parent, service, text, apply_replace,
                 on_locate=None, dictionary_path=None, text_provider=None):
        super().__init__(parent)
        self.service = service
        self.text = text or ""
        self.apply_replace = apply_replace
        self.on_locate = on_locate
        #: 替换后重新取当前文本（对话框自己不读编辑器，由调用方注入）
        self.text_provider = text_provider
        self.dictionary_path = Path(dictionary_path) if dictionary_path \
            else user_dictionary_path()
        self.items = []
        self._added_words = []
        #: 一次性提示（如"已加入词典"/"词典保存失败"）。
        #: ⚠️ 必须在 refresh() 之后仍然可见 —— 我第一版先 setText 再 refresh()，
        #: 提示被 refresh 覆盖，用户永远看不到"保存失败"。
        self._notice = ""

        self.setWindowTitle("拼写检查")
        self.resize(760, 460)
        self._build_ui()
        self.refresh()

    # ------------------------------------------------------------------
    def _build_ui(self):
        layout = QVBoxLayout(self)

        self.summary = QLabel("")
        layout.addWidget(self.summary)

        self.table = QTableWidget(0, 3, self)
        self.table.setHorizontalHeaderLabels(["词", "建议（可改）", "位置"])
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
        self.table.itemSelectionChanged.connect(self._on_row_changed)
        self.table.doubleClicked.connect(self._locate_current)
        layout.addWidget(self.table)

        row = QHBoxLayout()
        self.replace_btn = QPushButton("替换")
        self.replace_btn.clicked.connect(self.replace_current)
        self.replace_all_btn = QPushButton("全部替换")
        self.replace_all_btn.clicked.connect(self.replace_all)
        self.ignore_btn = QPushButton("忽略")
        self.ignore_btn.clicked.connect(self.ignore_current)
        self.ignore_all_btn = QPushButton("全部忽略")
        self.ignore_all_btn.clicked.connect(self.ignore_all)
        self.add_btn = QPushButton("加入词典")
        self.add_btn.clicked.connect(self.add_current_to_dictionary)
        for button in (self.replace_btn, self.replace_all_btn,
                       self.ignore_btn, self.ignore_all_btn, self.add_btn):
            row.addWidget(button)
        row.addStretch(1)
        layout.addLayout(row)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.reject)
        buttons.accepted.connect(self.accept)
        layout.addWidget(buttons)

    # ------------------------------------------------------------------
    # 检查与刷新
    # ------------------------------------------------------------------
    def refresh(self):
        """重新检查文本并刷新列表（忽略过的词不会再出现）。"""
        self.items = list(self.service.check_text(self.text))
        self.table.setRowCount(len(self.items))
        for row, item in enumerate(self.items):
            word_cell = QTableWidgetItem(item.word)
            word_cell.setData(Qt.ItemDataRole.UserRole, (item.start, item.end))
            self.table.setItem(row, 0, word_cell)

            combo = QComboBox()
            combo.setEditable(True)
            suggestions = list(item.suggestions or [])
            if not suggestions:
                combo.addItem("（无建议）")
            combo.addItems(suggestions)
            self.table.setCellWidget(row, 1, combo)

            self.table.setItem(
                row, 2,
                QTableWidgetItem(f"第 {self._line_of(item.start)} 行"),
            )

        if not self.items:
            ignored = getattr(self.service, "_ignored", None) or set()
            text = (
                "✅ 检查完成，没有发现拼写问题。"
                + (f"（本次已忽略 {len(ignored)} 个词）" if ignored else "")
            )
        else:
            text = (
                f"发现 {len(self.items)} 处可疑拼写。"
                f"技术词/产品名可点「加入词典」永久忽略。"
            )
        if self._notice:
            text = f"{text}\n{self._notice}"
        self.summary.setText(text)
        self._update_buttons()

    def _line_of(self, position):
        return self.text.count("\n", 0, position) + 1

    def _update_buttons(self):
        enabled = bool(self.items)
        for button in (self.replace_btn, self.replace_all_btn,
                       self.ignore_btn, self.ignore_all_btn, self.add_btn):
            button.setEnabled(enabled)

    def current_row(self):
        rows = self.table.selectionModel().selectedRows()
        if not rows:
            return -1
        return rows[0].row()

    def _current_item(self):
        row = self.current_row()
        if row < 0 or row >= len(self.items):
            return None
        return self.items[row]

    def _selected_replacement(self, row):
        widget = self.table.cellWidget(row, 1)
        if isinstance(widget, QComboBox):
            return widget.currentText().strip()
        return ""

    def _on_row_changed(self):
        item = self._current_item()
        if item and self.on_locate is not None:
            self.on_locate(item.start, item.end)

    def _locate_current(self):
        self._on_row_changed()

    # ------------------------------------------------------------------
    # 操作
    # ------------------------------------------------------------------
    def replace_current(self):
        """替换当前这一处（按建议）。"""
        row = self.current_row()
        item = self._current_item()
        if item is None:
            return
        replacement = self._selected_replacement(row)
        if not replacement or replacement == "（无建议）":
            QMessageBox.information(self, "提示", "这个词没有可用的建议，请手动填写。")
            return
        self._replace_item(item, replacement)

    def replace_all(self):
        """把所有有建议的词一次性替换。"""
        replaced = 0
        for item in list(self.items):
            row = self.items.index(item)
            replacement = self._selected_replacement(row)
            if not replacement or replacement == "（无建议）":
                continue
            self._replace_item(item, replacement)
            replaced += 1
        if replaced == 0:
            QMessageBox.information(self, "提示", "没有可替换的建议。")

    def _replace_item(self, item, replacement):
        self.apply_replace(item.start, item.end, replacement)
        # 替换后原文变了，位置会失效 —— 重新取一次文本并重算
        if self.text_provider is not None:
            try:
                self.text = self.text_provider() or ""
            except Exception as e:  # noqa: BLE001
                logging.debug(f"[拼写检查] 重新取文本失败: {e}")
        self.service.ignore(item.word)
        self.refresh()

    def ignore_current(self):
        item = self._current_item()
        if item is None:
            return
        self.service.ignore(item.word)
        self.refresh()

    def ignore_all(self):
        """全部忽略（技术文档里这一步最常用）。"""
        for item in list(self.items):
            self.service.ignore(item.word)
        self.refresh()

    def add_current_to_dictionary(self):
        """加入用户词典并**持久化** —— 下次打开还在。"""
        item = self._current_item()
        if item is None:
            return
        word = item.word
        self.service.add_to_dictionary(word)
        if word not in self._added_words:
            self._added_words.append(word)
        try:
            from beeoffice.plugins.spellcheck import (
                load_user_dictionary, save_user_dictionary,
            )

            words = set(load_user_dictionary(self.dictionary_path))
            words.add(word)
            save_user_dictionary(self.dictionary_path, sorted(words))
            self._notice = f"已把「{word}」加入词典并保存（下次打开仍生效）。"
        except Exception as e:  # noqa: BLE001 - 存不下也不能影响本次检查
            logging.warning(f"[拼写检查] 保存用户词典失败: {e}")
            self._notice = f"已忽略「{word}」，但词典保存失败：{e}"
        self.refresh()
