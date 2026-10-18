# beeoffice/plugins/beesheet_formula_mixin.py
"""
蜜算公式功能 Mixin：公式输入、函数选择、自动求和、公式重算、
参数提示、引用高亮、实时预览
"""
import re
import pandas as pd
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton,
    QListWidget, QListWidgetItem, QMenu, QMessageBox
)
from PySide6.QtCore import Qt, QPoint
from PySide6.QtGui import QColor

from beeoffice.plugins.beesheet_engine import FormulaEngine
from beeoffice.plugins.beesheet_commands import EditCellCommand
from beeoffice.plugins.beesheet_utils import (
    col_index_to_name, col_name_to_index
)
from beeoffice.i18n import tr


class FormulaMixin:
    """公式相关功能的 Mixin"""

    # ==================== 公式栏事件 ====================
    def _on_formula_enter(self):
        """公式栏回车：解析公式并写入单元格"""
        index = self.table_view.currentIndex()
        if not index.isValid():
            return
        key = (index.row(), index.column())
        old = self.model.get_value(index.row(), index.column())
        value = self.formula_bar.text()

        if value.startswith('='):
            result = FormulaEngine.evaluate(value, self.model)
            if isinstance(result, (int, float)):
                self._push_command(
                    EditCellCommand(index.row(), index.column(), old, result)
                )
                self.model.setData(index, result)
                self._formula_cells[key] = value
                self.formula_bar.setText(str(result))
                self._recalc_formulas()
                self._set_status(f"✅ {value} = {result}", 3000)
            else:
                self._set_status(f"❌ {result}", 5000)
        else:
            try:
                value = float(value) if '.' in value else int(value)
            except:
                pass
            self._push_command(
                EditCellCommand(index.row(), index.column(), old, value)
            )
            self.model.setData(index, value)
            self._formula_cells.pop(key, None)
            self._recalc_formulas()

        self._dirty = True
        self._update_status()
        self._clear_ref_highlights()
        self._hide_param_tip()
        self._clear_audit()
        self._preview_label.hide()

    def _on_formula_text_changed(self, text):
        """公式栏文本变化：参数提示、引用高亮、实时预览、自动补全"""
        self._update_param_tip(text)
        self._update_ref_highlights(text)
        self._update_formula_preview(text)

        if not text.startswith('='):
            self._completion_popup.hide()
            return

        expr = text[1:]
        if '(' not in expr:
            prefix = expr.upper()
            categories = {}
            for name, (syntax, cat) in self.FUNCTION_REFERENCE.items():
                if name.startswith(prefix):
                    if cat not in categories:
                        categories[cat] = []
                    categories[cat].append((name, syntax))
            if categories:
                self._completion_popup.clear()
                for cat in ["统计", "逻辑", "查找", "条件", "数学",
                            "文本", "日期", "财务"]:
                    if cat in categories:
                        item = QListWidgetItem(f"── {cat} ──")
                        item.setFlags(Qt.NoItemFlags)
                        item.setForeground(QColor("#FF8F00"))
                        self._completion_popup.addItem(item)
                        for name, syntax in categories[cat]:
                            item = QListWidgetItem(f"  {name}  {syntax}")
                            item.setData(Qt.UserRole, name)
                            self._completion_popup.addItem(item)
                pos = self.formula_bar.mapToGlobal(
                    self.formula_bar.rect().bottomLeft()
                )
                self._completion_popup.setGeometry(
                    pos.x(), pos.y() + 2, 450,
                    min(self._completion_popup.count() * 52 + 10, 350)
                )
                self._completion_popup.show()
            else:
                self._completion_popup.hide()
        else:
            self._completion_popup.hide()

    def _on_completion_selected(self, item):
        """点击自动补全项"""
        name = item.data(Qt.UserRole)
        if name:
            self.formula_bar.setText('=' + name + '(')
            self.formula_bar.setFocus()
            self._completion_popup.hide()
            if name in self.FUNCTION_REFERENCE:
                syntax, cat = self.FUNCTION_REFERENCE[name]
                self._set_status(f"📖 {name}: {syntax} [{cat}]", 8000)

    def _on_formula_cursor_moved(self):
        """公式栏光标移动：更新引用高亮"""
        self._update_ref_highlights(self.formula_bar.text())

    # ==================== 参数提示 ====================
    def _update_param_tip(self, text):
        """显示函数参数语法提示气泡"""
        if not text.startswith('='):
            self._hide_param_tip()
            return
        m = re.match(r'^=([A-Za-z]+)\s*\(', text)
        if not m:
            self._hide_param_tip()
            return
        fname = m.group(1).upper()
        if fname in self.FUNCTION_REFERENCE:
            syntax, _ = self.FUNCTION_REFERENCE[fname]
            if self._last_func_tip != fname:
                self._last_func_tip = fname
                self._param_tip.setText(f"<b>{fname}</b>  {syntax}")
                pos = self.formula_bar.mapToGlobal(
                    QPoint(0, self.formula_bar.height() + 2)
                )
                self._param_tip.move(pos)
                self._param_tip.adjustSize()
                self._param_tip.show()
        else:
            self._hide_param_tip()

    def _hide_param_tip(self):
        """隐藏参数提示气泡"""
        if self._param_tip.isVisible():
            self._param_tip.hide()
        self._last_func_tip = ""

    # ==================== 公式实时预览 ====================
    def _update_formula_preview(self, text):
        """公式栏实时显示计算结果"""
        if not text.startswith('='):
            self._preview_label.hide()
            return
        if text.count('(') != text.count(')'):
            self._preview_label.hide()
            return
        if len(text) < 3:
            self._preview_label.hide()
            return
        try:
            result = FormulaEngine.evaluate(text, self.model)
            if isinstance(result, (int, float)):
                display = (f"{result:,.4g}" if isinstance(result, float)
                           else f"{result:,}")
                self._preview_label.setText(f"= {display}")
                self._preview_label.setStyleSheet(
                    "QLabel{color:#0D47A1;font-weight:bold;"
                    "padding:2px 8px;background:#E3F2FD;"
                    "border-radius:4px;font-size:13px;}"
                )
                self._preview_label.show()
            elif isinstance(result, str):
                if result.startswith('#ERROR') or result.startswith('#N/A'):
                    self._preview_label.setText(f"⚠ {result[:20]}")
                    self._preview_label.setStyleSheet(
                        "QLabel{color:#B71C1C;font-weight:bold;"
                        "padding:2px 8px;background:#FFEBEE;"
                        "border-radius:4px;font-size:13px;}"
                    )
                    self._preview_label.show()
                else:
                    self._preview_label.setText(f"= \"{result[:20]}\"")
                    self._preview_label.setStyleSheet(
                        "QLabel{color:#1B5E20;font-weight:bold;"
                        "padding:2px 8px;background:#E8F5E9;"
                        "border-radius:4px;font-size:13px;}"
                    )
                    self._preview_label.show()
            else:
                self._preview_label.hide()
        except Exception:
            self._preview_label.hide()

    # ==================== 引用高亮 ====================
    def _update_ref_highlights(self, text):
        """高亮公式中引用的单元格"""
        refs = set()
        if text.startswith('='):
            range_spans = []
            # 先匹配范围 A1:B10
            for m in re.finditer(
                r'\$?([A-Z]+)\$?(\d+):\$?([A-Z]+)\$?(\d+)',
                text.upper()
            ):
                c1s, r1s, c2s, r2s = m.groups()
                r1, r2 = int(r1s) - 1, int(r2s) - 1
                c1, c2 = col_name_to_index(c1s), col_name_to_index(c2s)
                for r in range(min(r1, r2), max(r1, r2) + 1):
                    for c in range(min(c1, c2), max(c1, c2) + 1):
                        refs.add((r, c))
                range_spans.append(m.span())
            # 再匹配单引用 A1（跳过范围内部分）
            for m in re.finditer(r'\$?([A-Z]+)\$?(\d+)', text.upper()):
                if any(s <= m.start() < e for s, e in range_spans):
                    continue
                cs, rs = m.groups()
                refs.add((int(rs) - 1, col_name_to_index(cs)))

        old_refs = self.model._highlight_refs
        if refs != old_refs:
            self.model._highlight_refs = refs
            affected = old_refs | refs
            for (r, c) in affected:
                idx = self.model.index(r, c)
                if idx.isValid():
                    self.model.dataChanged.emit(idx, idx)

    def _clear_highlight(self):
        """清除所有引用高亮"""
        if self.model._highlight_refs:
            old = self.model._highlight_refs
            self.model._highlight_refs = set()
            for (r, c) in old:
                idx = self.model.index(r, c)
                if idx.isValid():
                    self.model.dataChanged.emit(idx, idx)

    def _clear_ref_highlights(self):
        """_clear_highlight 的别名"""
        self._clear_highlight()

    # ==================== 函数参考 ====================
    def _show_function_reference(self):
        """函数参考对话框（双击插入）"""
        dlg = QDialog(self)
        dlg.setWindowTitle(tr("auto.beesheet_formula_mixin.7cf7ff1f", "📚 函数参考（双击插入到当前单元格）"))
        dlg.resize(600, 550)
        layout = QVBoxLayout(dlg)

        search = QLineEdit()
        search.setPlaceholderText(tr("auto.beesheet_formula_mixin.29668b10", "搜索函数..."))
        layout.addWidget(search)

        lst = QListWidget()
        lst.setStyleSheet(
            "QListWidget::item { padding: 4px 8px; } "
            "QListWidget::item:selected { background: #FFE0A0; color: #000; }"
        )
        all_items = []
        for cat in ["统计", "逻辑", "查找", "条件", "数学",
                    "文本", "日期", "财务"]:
            header = QListWidgetItem(f"── {cat} ──")
            header.setFlags(Qt.NoItemFlags)
            header.setForeground(QColor("#FF8F00"))
            lst.addItem(header)
            all_items.append(header)
            for name, (syntax, c) in sorted(self.FUNCTION_REFERENCE.items()):
                if c == cat:
                    item = QListWidgetItem(f"  {name}    {syntax}")
                    item.setData(Qt.UserRole, name)
                    lst.addItem(item)
                    all_items.append(item)
        layout.addWidget(lst)

        def do_filter(text):
            text = text.upper()
            for item in all_items:
                name = item.data(Qt.UserRole)
                if name:
                    item.setHidden(
                        bool(text) and text not in item.text().upper()
                    )
                else:
                    item.setHidden(bool(text))
        search.textChanged.connect(do_filter)

        def on_double_click(item):
            name = item.data(Qt.UserRole)
            if not name:
                return
            idx = self.table_view.currentIndex()
            if not idx.isValid():
                QMessageBox.information(
                    dlg, tr("auto.beesheet_formula_mixin.ab3656a9", "提示"), tr("auto.beesheet_formula_mixin.f4d94f7a", "请先在表格中选中一个单元格")
                )
                return
            self.formula_bar.setText(f"={name}(")
            self.formula_bar.setFocus()
            self.formula_bar.setCursorPosition(len(self.formula_bar.text()))
            self._set_status(tr("auto.beesheet_formula_mixin.632cd3ff", "已插入 {name}，请在括号内填写参数").format(name=name), 3000)
            dlg.accept()
        lst.itemDoubleClicked.connect(on_double_click)

        tip = QLabel(tr("auto.beesheet_formula_mixin.843a19f1", "💡 双击函数名插入到公式栏，光标会定位到括号内"))
        tip.setStyleSheet("color:#666; font-size:12px; padding:4px;")
        layout.addWidget(tip)
        dlg.exec()

    def _show_function_picker(self):
        """函数选择器（fx 按钮打开）"""
        dlg = QDialog(self)
        dlg.setWindowTitle(tr("auto.beesheet_formula_mixin.5a598b04", "ƒx 插入函数"))
        dlg.resize(620, 560)
        layout = QVBoxLayout(dlg)

        search = QLineEdit()
        search.setPlaceholderText(tr("auto.beesheet_formula_mixin.4d9c088f", "搜索函数名或语法..."))
        layout.addWidget(search)

        lst = QListWidget()
        lst.setStyleSheet(
            "QListWidget::item { padding: 5px 8px; } "
            "QListWidget::item:selected { background: #FFE0A0; color: #000; }"
        )
        all_items = []
        for cat in ["统计", "逻辑", "查找", "条件", "数学",
                    "文本", "日期", "财务"]:
            header = QListWidgetItem(f"── {cat} ──")
            header.setFlags(Qt.NoItemFlags)
            header.setForeground(QColor("#FF8F00"))
            lst.addItem(header)
            all_items.append(header)
            for name, (syntax, c) in sorted(self.FUNCTION_REFERENCE.items()):
                if c == cat:
                    item = QListWidgetItem(f"  {name}    {syntax}")
                    item.setData(Qt.UserRole, name)
                    item.setData(Qt.UserRole + 1, syntax)
                    lst.addItem(item)
                    all_items.append(item)
        layout.addWidget(lst)

        preview = QLabel(tr("auto.beesheet_formula_mixin.d68c58ae", "双击函数名插入到当前单元格的公式栏"))
        preview.setStyleSheet(
            "QLabel{background:#FFF8E1;color:#666;padding:8px;"
            "border:1px solid #FFE0B2;border-radius:4px;font-size:13px;}"
        )
        preview.setWordWrap(True)
        layout.addWidget(preview)

        def on_select():
            item = lst.currentItem()
            if item is None:
                return
            name = item.data(Qt.UserRole)
            if not name:
                return
            syntax = item.data(Qt.UserRole + 1) or ""
            preview.setText(
                tr("auto.beesheet_formula_mixin.64caad1c", "<b style='color:#E65100;'>{name}</b><br><span style='color:#666;'>语法：{syntax}</span>").format(name=name, syntax=syntax)
            )
        lst.itemSelectionChanged.connect(on_select)

        def do_filter(text):
            text = text.upper()
            for item in all_items:
                name = item.data(Qt.UserRole)
                if name:
                    item.setHidden(
                        bool(text) and text not in item.text().upper()
                    )
                else:
                    item.setHidden(bool(text))
        search.textChanged.connect(do_filter)

        def on_double_click(item):
            name = item.data(Qt.UserRole)
            if not name:
                return
            idx = self.table_view.currentIndex()
            if not idx.isValid():
                QMessageBox.information(
                    dlg, tr("auto.beesheet_formula_mixin.ab3656a9", "提示"), tr("auto.beesheet_formula_mixin.f4d94f7a", "请先在表格中选中一个单元格")
                )
                return
            self.formula_bar.setText(f"={name}(")
            self.formula_bar.setFocus()
            self.formula_bar.setCursorPosition(len(self.formula_bar.text()))
            self._set_status(tr("auto.beesheet_formula_mixin.632cd3ff", "已插入 {name}，请在括号内填写参数").format(name=name), 3000)
            dlg.accept()
        lst.itemDoubleClicked.connect(on_double_click)

        bl = QHBoxLayout()
        bl.addStretch()
        insert_btn = QPushButton(tr("auto.beesheet_formula_mixin.b48a4da0", "插入到当前单元格"))
        insert_btn.setStyleSheet(
            "QPushButton{background:#FFB300;color:#000;"
            "padding:6px 16px;border:none;border-radius:4px;"
            "font-weight:bold;}"
            "QPushButton:hover{background:#FFA000;}"
        )

        def do_insert():
            item = lst.currentItem()
            if item:
                on_double_click(item)
        insert_btn.clicked.connect(do_insert)
        bl.addWidget(insert_btn)

        close_btn = QPushButton(tr("auto.beesheet_formula_mixin.6c14bd7f", "关闭"))
        close_btn.clicked.connect(dlg.reject)
        bl.addWidget(close_btn)
        layout.addLayout(bl)
        dlg.exec()

    def _show_fx_dropdown(self):
        """fx 按钮下拉菜单"""
        menu = QMenu(self)
        common_menu = menu.addMenu(tr("auto.beesheet_formula_mixin.25ad4e61", "🔥 常用"))
        for fn in ["SUM", "AVERAGE", "COUNT", "MAX", "MIN", "IF", "VLOOKUP"]:
            act = common_menu.addAction(fn)
            act.triggered.connect(
                lambda checked=False, f=fn: self._insert_function(f)
            )
        for cat in ["统计", "逻辑", "查找", "条件", "数学",
                    "文本", "日期", "财务"]:
            cat_menu = menu.addMenu(f"📂 {cat}")
            for name, (syntax, c) in sorted(self.FUNCTION_REFERENCE.items()):
                if c == cat:
                    act = cat_menu.addAction(f"{name}    {syntax}")
                    act.triggered.connect(
                        lambda checked=False, f=name:
                            self._insert_function(f)
                    )
        menu.addSeparator()
        menu.addAction(tr("auto.beesheet_formula_mixin.a0aba974", "🔍 更多函数...")).triggered.connect(
            self._show_function_picker
        )
        menu.exec(self._fx_btn.mapToGlobal(self._fx_btn.rect().bottomLeft()))

    def _insert_function(self, name):
        """将函数名插入到公式栏"""
        idx = self.table_view.currentIndex()
        if not idx.isValid():
            QMessageBox.information(
                self, tr("auto.beesheet_formula_mixin.ab3656a9", "提示"), tr("auto.beesheet_formula_mixin.f4d94f7a", "请先在表格中选中一个单元格")
            )
            return
        self.formula_bar.setText(f"={name}(")
        self.formula_bar.setFocus()
        self.formula_bar.setCursorPosition(len(self.formula_bar.text()))
        self._set_status(tr("auto.beesheet_formula_mixin.632cd3ff", "已插入 {name}，请在括号内填写参数").format(name=name), 3000)

    # ==================== 自动求和 ====================
    def _auto_sum(self):
        """
        自动求和：类 WPS 的 Alt+=
        - 单列选中：在末尾下方填入 =SUM(列区间)
        - 多列选中：每行右侧填入 =SUM(行区间)
        - 无选中：尝试向上探测连续数字
        """
        sel = self.table_view.selectionModel().selection()
        indexes = sel.indexes() if sel else []

        # 无选中时，从当前单元格向上探测
        if not indexes:
            cur = self.table_view.currentIndex()
            if not cur.isValid():
                QMessageBox.information(self, tr("auto.beesheet_formula_mixin.ab3656a9", "提示"), tr("auto.beesheet_formula_mixin.53c01b07", "请选中要计算的数据"))
                return
            col = cur.column()
            row = cur.row() - 1
            probe = []
            while row >= 0:
                v = self.model.get_value(row, col)
                if v is None or str(v).strip() == '':
                    break
                try:
                    float(v)
                    probe.append((row, col))
                except:
                    break
                row -= 1
            if not probe:
                QMessageBox.information(
                    self, tr("auto.beesheet_formula_mixin.ab3656a9", "提示"), tr("auto.beesheet_formula_mixin.0aa3552f", "当前单元格上方未找到可求和的数字")
                )
                return
            indexes = [self.model.index(r, c) for r, c in probe]

        pairs = sorted(
            [(i.row(), i.column()) for i in indexes],
            key=lambda x: (x[0], x[1])
        )
        rows = sorted(set(r for r, _ in pairs))
        cols = sorted(set(c for _, c in pairs))

        if not rows or not cols:
            return

        # 情况 1：单列选中 → 在末尾下方填入 SUM
        if len(cols) == 1:
            col = cols[0]
            r_start, r_end = min(rows), max(rows)
            target_row = r_end + 1
            while target_row >= len(self.model._loaded_df):
                self.model._loaded_df.loc[
                    len(self.model._loaded_df)
                ] = [None] * len(self.model._loaded_df.columns)
                self.model._total_rows = len(self.model._loaded_df)
            cn = col_index_to_name(col)
            formula = f"=SUM({cn}{r_start+1}:{cn}{r_end+1})"
            result = FormulaEngine.evaluate(formula, self.model)
            if not isinstance(result, (int, float)):
                self._set_status(tr("auto.beesheet_formula_mixin.774b9373", "❌ 求和失败: {result}").format(result=result), 5000)
                return
            old_value = self.model.get_value(target_row, col)
            self._formula_cells[(target_row, col)] = formula
            self._push_command(
                EditCellCommand(target_row, col, old_value, result)
            )
            self._set_status(f"✅ {formula} = {result}", 5000)
            return

        # 情况 2：多列选中 → 每行右侧填入 SUM
        target_col = max(cols) + 1
        while target_col >= len(self.model._loaded_df.columns):
            self.model._loaded_df[
                f"列{len(self.model._loaded_df.columns)+1}"
            ] = ''
            self.model._total_cols = len(self.model._loaded_df.columns)

        count = 0
        for r in rows:
            cols_str = ",".join(
                f"{col_index_to_name(c)}{r+1}" for c in cols
            )
            formula = f"=SUM({cols_str})"
            result = FormulaEngine.evaluate(formula, self.model)
            if isinstance(result, (int, float)):
                old_value = self.model.get_value(r, target_col)
                self._formula_cells[(r, target_col)] = formula
                self._push_command(
                    EditCellCommand(r, target_col, old_value, result)
                )
                count += 1
        self._set_status(tr("auto.beesheet_formula_mixin.bc121dae", "✅ 已按行自动求和 ({count} 行)").format(count=count), 5000)

    # ==================== 公式重算 ====================
    def _recalc_formulas(self, max_rounds=3):
        """
        重算所有记录在案的公式单元格。
        支持链式依赖（如 B1=SUM(A1:A3)，C1=B1*2），最多迭代 max_rounds 轮。
        """
        if not hasattr(self, '_formula_cells') or not self._formula_cells:
            return
        for _ in range(max_rounds):
            changed = False
            for (r, c), formula in list(self._formula_cells.items()):
                try:
                    result = FormulaEngine.evaluate(formula, self.model)
                    if isinstance(result, (int, float)):
                        cur = self.model.get_value(r, c)
                        if str(cur) != str(result):
                            self.model._loaded_df.iloc[r, c] = result
                            self.model.dataChanged.emit(
                                self.model.index(r, c),
                                self.model.index(r, c)
                            )
                            changed = True
                except Exception:
                    pass
            if not changed:
                break

    # ==================== F1 帮助 ====================
    def _f1_help(self):
        """F1 显示当前函数帮助"""
        text = self.formula_bar.text()
        if text.startswith('='):
            func_match = re.match(r'^=(\w+)', text)
            if func_match:
                func_name = func_match.group(1).upper()
                if func_name in self.FUNCTION_REFERENCE:
                    syntax, cat = self.FUNCTION_REFERENCE[func_name]
                    QMessageBox.information(
                        self, tr("auto.beesheet_formula_mixin.f6a2e07c", "📖 {func_name} 函数帮助").format(func_name=func_name),
                        tr("auto.beesheet_formula_mixin.bae572e3", "<b>分类：</b>{cat}<br><br><b>语法：</b><code>{syntax}</code>").format(cat=cat, syntax=syntax)
                    )
                    return
        QMessageBox.information(
            self, tr("auto.beesheet_formula_mixin.2006162c", "📚 函数帮助"),
            tr("auto.beesheet_formula_mixin.557b40eb", "请先在公式栏输入 `=` 加函数名，然后按 F1。")
        )