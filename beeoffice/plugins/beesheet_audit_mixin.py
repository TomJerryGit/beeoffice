# beeoffice/plugins/beesheet_audit_mixin.py
"""
蜜算审计功能 Mixin：公式审计、错误助手、公式翻译、兼容性检查
"""
import re
from datetime import datetime
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTextEdit, QFileDialog, QMessageBox, QApplication
)
from PySide6.QtCore import Qt

from beeoffice.plugins.beesheet_utils import extract_refs_from_formula


class AuditMixin:
    """审计相关功能的 Mixin"""

    # ==================== 追踪引用/从属 ====================
    def _trace_precedents(self):
        """追踪引用：找出当前单元格的公式引用了哪些单元格"""
        idx = self.table_view.currentIndex()
        if not idx.isValid():
            return
        key = (idx.row(), idx.column())
        if key not in self._formula_cells:
            QMessageBox.information(self, "提示", "当前单元格没有公式")
            return
        formula = self._formula_cells[key]
        refs = extract_refs_from_formula(formula)
        self._audit_cells.clear()
        self._audit_cells.update(refs)
        self._refresh_all_cells()
        if refs:
            self._set_status(
                f"📌 追踪引用：{len(refs)} 个单元格（橙色高亮）",
                5000
            )
        else:
            self._set_status("该公式没有引用其他单元格", 3000)

    def _trace_dependents(self):
        """追踪从属：找出哪些单元格的公式引用了当前单元格"""
        idx = self.table_view.currentIndex()
        if not idx.isValid():
            return
        target = (idx.row(), idx.column())
        target_ref = f"{self._col_index_to_name(target[1])}{target[0]+1}"
        dependents = set()
        for (r, c), formula in self._formula_cells.items():
            refs = extract_refs_from_formula(formula)
            if target in refs:
                dependents.add((r, c))
        self._audit_cells.clear()
        self._audit_cells.update(dependents)
        self._refresh_all_cells()
        if dependents:
            self._set_status(
                f"📌 追踪从属：{len(dependents)} 个单元格引用了 "
                f"{target_ref}（橙色高亮）", 5000
            )
        else:
            self._set_status(f"{target_ref} 没有被任何公式引用", 3000)

    def _clear_audit(self):
        """清除审计高亮"""
        if self._audit_cells:
            self._audit_cells.clear()
            self._refresh_all_cells()
            self._set_status("已清除审计高亮", 2000)

    def _refresh_all_cells(self):
        """刷新整个表格（用于审计高亮变化）"""
        if self.model.rowCount() > 0 and self.model.columnCount() > 0:
            self.model.dataChanged.emit(
                self.model.index(0, 0),
                self.model.index(
                    self.model.rowCount() - 1,
                    self.model.columnCount() - 1
                ),
                [Qt.BackgroundRole, Qt.DisplayRole]
            )

    # ==================== 公式翻译 ====================
    def _translate_current_formula(self):
        """翻译当前单元格的公式为中文说明"""
        idx = self.table_view.currentIndex()
        if not idx.isValid():
            return
        key = (idx.row(), idx.column())
        formula = self._formula_cells.get(key)
        if not formula:
            val = str(self.model.get_value(idx.row(), idx.column()))
            if val.startswith('='):
                formula = val
            else:
                QMessageBox.information(self, "提示", "当前单元格没有公式")
                return
        translation = self._translate_formula_to_chinese(formula)

        dlg = QDialog(self)
        dlg.setWindowTitle("📖 公式翻译器")
        dlg.resize(520, 360)
        layout = QVBoxLayout(dlg)

        layout.addWidget(QLabel("<b>公式：</b>"))
        f_label = QLabel(formula)
        f_label.setStyleSheet(
            "QLabel{background:#F5F5F5;padding:10px;"
            "font-family:Consolas;font-size:14px;border-radius:4px;}"
        )
        f_label.setWordWrap(True)
        layout.addWidget(f_label)

        layout.addWidget(QLabel("<b>中文说明：</b>"))
        t_label = QLabel(translation)
        t_label.setStyleSheet(
            "QLabel{background:#FFF8E1;padding:12px;font-size:14px;"
            "line-height:1.8;border-radius:6px;"
            "border:1px solid #FFE0B2;}"
        )
        t_label.setWordWrap(True)
        layout.addWidget(t_label)
        layout.addStretch()

        bl = QHBoxLayout()
        copy_btn = QPushButton("📋 复制说明")
        copy_btn.clicked.connect(
            lambda: QApplication.clipboard().setText(translation)
        )
        bl.addWidget(copy_btn)
        bl.addStretch()
        close_btn = QPushButton("关闭")
        close_btn.clicked.connect(dlg.reject)
        bl.addWidget(close_btn)
        layout.addLayout(bl)
        dlg.exec()

    def _translate_formula_to_chinese(self, formula):
        """将公式翻译成中文说明"""
        if not formula.startswith('='):
            return formula
        expr = formula[1:].strip()

        func_names = {
            "SUM": "求和", "AVERAGE": "平均值", "MAX": "最大值",
            "MIN": "最小值", "COUNT": "计数", "COUNTA": "非空计数",
            "IF": "如果", "IFERROR": "如果出错则", "AND": "并且",
            "OR": "或者", "NOT": "非", "VLOOKUP": "纵向查找",
            "HLOOKUP": "横向查找", "XLOOKUP": "智能查找",
            "INDEX": "索引", "MATCH": "匹配位置", "ROUND": "四舍五入",
            "ROUNDUP": "向上取整", "ROUNDDOWN": "向下取整",
            "ABS": "绝对值", "SQRT": "平方根", "POWER": "幂运算",
            "MOD": "取余", "INT": "取整", "CEILING": "向上舍入",
            "FLOOR": "向下舍入", "LEFT": "取左侧", "RIGHT": "取右侧",
            "MID": "取中间", "LEN": "长度", "TRIM": "去空格",
            "UPPER": "转大写", "LOWER": "转小写",
            "PROPER": "首字母大写",
            "CONCATENATE": "连接文本",
            "TEXTJOIN": "连接文本（带分隔符）",
            "FIND": "查找位置", "SEARCH": "搜索位置",
            "SUBSTITUTE": "替换", "REPLACE": "替换位置",
            "TEXT": "转文本格式", "VALUE": "转数值",
            "TODAY": "今天日期", "NOW": "当前时间",
            "DATE": "构造日期", "YEAR": "年", "MONTH": "月",
            "DAY": "日", "DATEDIF": "日期差", "WEEKDAY": "星期几",
            "PMT": "等额本息还款额", "FV": "终值", "PV": "现值",
            "NPV": "净现值", "IRR": "内部收益率",
        }

        m = re.match(r'^([A-Z]+)\((.+)\)$', expr, re.IGNORECASE)
        if m:
            fname = m.group(1).upper()
            args_str = m.group(2)
            cn_name = func_names.get(fname, fname)
            return (
                f"<b>{cn_name}</b>：使用 {args_str}<br><br>"
                f"<span style='color:#999;font-size:12px;'>"
                f"英文：{fname}({args_str})</span>"
            )
        return f"算术表达式：{expr}"

    # ==================== 错误助手 ====================
    def _show_error_helper(self, key, error_value):
        """显示公式错误助手"""
        formula = self._formula_cells.get(key, "")
        if not formula:
            QMessageBox.information(
                self, "错误详情",
                f"该单元格存在错误：\n\n{error_value}\n\n"
                f"（公式记录已丢失，无法显示详细原因）"
            )
            return

        dlg = QDialog(self)
        dlg.setWindowTitle("⚠ 公式错误助手")
        dlg.resize(520, 380)
        layout = QVBoxLayout(dlg)

        # 错误摘要
        err_box = QLabel(
            f"<b style='color:#B71C1C;font-size:15px;'>"
            f"❌ {error_value}</b>"
        )
        err_box.setWordWrap(True)
        err_box.setStyleSheet(
            "QLabel{background:#FFEBEE;padding:12px;"
            "border-radius:6px;}"
        )
        layout.addWidget(err_box)

        # 公式原文
        layout.addWidget(QLabel("📝 原始公式："))
        formula_label = QLabel(formula)
        formula_label.setStyleSheet(
            "QLabel{background:#F5F5F5;padding:10px;"
            "font-family:Consolas;border-radius:4px;font-size:13px;}"
        )
        formula_label.setWordWrap(True)
        layout.addWidget(formula_label)

        # 诊断与建议
        layout.addWidget(QLabel("💡 诊断与建议："))
        diag = self._diagnose_error(formula, error_value)
        diag_label = QLabel(diag)
        diag_label.setWordWrap(True)
        diag_label.setStyleSheet(
            "QLabel{background:#FFF8E1;padding:12px;"
            "border-radius:6px;font-size:13px;line-height:1.6;}"
        )
        layout.addWidget(diag_label)
        layout.addStretch()

        # 按钮
        bl = QHBoxLayout()
        copy_btn = QPushButton("📋 复制公式")
        copy_btn.clicked.connect(
            lambda: QApplication.clipboard().setText(formula)
        )
        edit_btn = QPushButton("✏️ 编辑公式")
        edit_btn.clicked.connect(
            lambda: [
                self.table_view.setCurrentIndex(
                    self.model.index(key[0], key[1])
                ),
                self.table_view.edit(
                    self.model.index(key[0], key[1])
                ),
                dlg.accept()
            ]
        )
        bl.addWidget(copy_btn)
        bl.addWidget(edit_btn)
        bl.addStretch()
        close_btn = QPushButton("关闭")
        close_btn.clicked.connect(dlg.reject)
        bl.addWidget(close_btn)
        layout.addLayout(bl)
        dlg.exec()

    def _diagnose_error(self, formula, error_value):
        """根据公式和错误类型给出诊断建议"""
        suggestions = []

        if "#DIV/0" in error_value or "division" in error_value.lower():
            suggestions.append(
                "• <b>除零错误</b>：公式中有除数（分母）为 0 或空值"
            )
            suggestions.append(
                "• 建议：用 IFERROR 包裹，如 "
                "<code>=IFERROR(公式, 0)</code>"
            )
        elif "#N/A" in error_value:
            suggestions.append(
                "• <b>未找到匹配值</b>：VLOOKUP 等查找函数没有匹配"
            )
            suggestions.append(
                "• 建议：检查查找值拼写，或添加 IFERROR 处理"
            )
        elif "未知函数" in error_value:
            suggestions.append("• <b>函数名拼写错误</b>")
            suggestions.append("• 查看函数参考：点击工具栏'📚 函数'")
        else:
            if '(' in formula:
                lp = formula.count('(')
                rp = formula.count(')')
                if lp != rp:
                    suggestions.append(
                        f"• <b>括号不匹配</b>：左括号 {lp} 个，"
                        f"右括号 {rp} 个"
                    )
            if not suggestions:
                suggestions.append(f"• 详细错误信息：{error_value}")
            suggestions.append(
                "• 查看函数参考：点击工具栏'📚 函数'按钮"
            )
        return "<br>".join(suggestions)

    # ==================== 兼容性检查 ====================
    def _check_excel_compatibility(self):
        """检查当前表格的公式、名称在 Excel/WPS 中的兼容性"""
        issues = []
        warnings = []
        ok_count = 0

        # 检查所有公式
        for (r, c), formula in self._formula_cells.items():
            cell_ref = f"{self._col_index_to_name(c)}{r+1}"
            result = self._check_formula_compatibility(formula)
            if result["level"] == "error":
                issues.append(f"❌ {cell_ref}: {result['msg']}")
            elif result["level"] == "warning":
                warnings.append(f"⚠️ {cell_ref}: {result['msg']}")
            else:
                ok_count += 1

        # 检查命名区域
        for name, ref in self._named_ranges.items():
            if not re.match(
                r'^[\u4e00-\u9fffA-Za-z_][\u4e00-\u9fffA-Za-z0-9_]*$',
                name
            ):
                issues.append(f"❌ 名称「{name}」含非法字符")
            elif name.upper() in ("SUM", "AVERAGE", "IF", "VLOOKUP"):
                issues.append(f"❌ 名称「{name}」与 Excel 保留名称冲突")
            else:
                ok_count += 1

        # 构建对话框
        dlg = QDialog(self)
        dlg.setWindowTitle("✓ Excel 兼容性检查")
        dlg.resize(560, 480)
        layout = QVBoxLayout(dlg)

        total = len(issues) + len(warnings) + ok_count
        summary = QLabel()
        if not issues and not warnings:
            summary.setText(
                f"<h2 style='color:#1B5E20;'>✅ 完美兼容</h2>"
                f"<p>共检查 {total} 项，全部通过。</p>"
            )
        elif issues:
            summary.setText(
                f"<h2 style='color:#B71C1C;'>❌ 发现 {len(issues)} 个问题</h2>"
                f"<p>警告 {len(warnings)} 项，通过 {ok_count} 项。</p>"
            )
        else:
            summary.setText(
                f"<h2 style='color:#E65100;'>⚠️ 发现 {len(warnings)} 个警告</h2>"
                f"<p>全部通过 {ok_count} 项。</p>"
            )
        layout.addWidget(summary)

        # 结果列表
        result_text = QTextEdit()
        result_text.setReadOnly(True)
        result_text.setStyleSheet(
            "QTextEdit{background:#FAFAFA;font-family:Consolas;"
            "font-size:13px;padding:8px;}"
        )

        lines = []
        if issues:
            lines.append("【❌ 必须修复的问题】")
            lines.append("")
            for issue in issues:
                lines.append(issue)
            lines.append("")
        if warnings:
            lines.append("【⚠️ 建议注意的警告】")
            lines.append("")
            for warn in warnings:
                lines.append(warn)
            lines.append("")
        if not issues and not warnings:
            lines.append("所有公式、格式、名称均与 Excel/WPS 兼容。")

        result_text.setPlainText("\n".join(lines))
        layout.addWidget(result_text)

        # 按钮
        bl = QHBoxLayout()

        def export_report():
            path, _ = QFileDialog.getSaveFileName(
                dlg, "保存报告", "兼容性报告.txt", "文本 (*.txt)"
            )
            if path:
                try:
                    with open(path, 'w', encoding='utf-8') as f:
                        f.write(
                            "BeeOffice Excel 兼容性报告\n" +
                            "=" * 40 + "\n\n"
                        )
                        f.write(f"检查时间：{datetime.now()}\n\n")
                        f.write("\n".join(lines))
                    QMessageBox.information(
                        dlg, "成功", f"已保存：\n{path}"
                    )
                except Exception as e:
                    QMessageBox.warning(dlg, "失败", str(e))

        export_btn = QPushButton("📋 导出报告")
        export_btn.clicked.connect(export_report)
        bl.addWidget(export_btn)
        bl.addStretch()
        close_btn = QPushButton("关闭")
        close_btn.clicked.connect(dlg.reject)
        bl.addWidget(close_btn)
        layout.addLayout(bl)
        dlg.exec()

    def _check_formula_compatibility(self, formula):
        """检查单个公式在 Excel 中的兼容性"""
        if not formula or not formula.startswith('='):
            return {"level": "ok"}
        upper = formula.upper()

        # 检查是否使用了不兼容的函数
        incompatible_funcs = {
            "XLOOKUP": "XLOOKUP 仅 Excel 365/2021+ 支持，旧版会显示 #NAME?",
            "IFS": "IFS 仅 Excel 2019+ 支持",
            "TEXTJOIN": "TEXTJOIN 仅 Excel 2019+ 支持",
        }
        for fn, msg in incompatible_funcs.items():
            if re.search(r'\b' + fn + r'\s*\(', upper):
                return {"level": "warning", "msg": msg}

        # 检查是否使用了 SQLite 风格语法
        if '||' in formula:
            return {
                "level": "error",
                "msg": "Excel 不支持 || 连接符，请用 & 或 CONCATENATE"
            }

        # 检查函数是否在白名单中
        fn_match = re.match(r'^=([A-Z]+)\s*\(', upper)
        if fn_match:
            fn = fn_match.group(1)
            supported = {
                "SUM", "AVERAGE", "MAX", "MIN", "COUNT", "COUNTA",
                "COUNTIF", "MEDIAN", "MODE", "STDEV", "VAR",
                "LARGE", "SMALL", "RANK",
                "IF", "IFERROR", "IFNA", "AND", "OR", "NOT",
                "VLOOKUP", "HLOOKUP", "INDEX", "MATCH", "CHOOSE",
                "SUMIF", "AVERAGEIF", "COUNTIFS", "SUMIFS",
                "AVERAGEIFS",
                "ROUND", "ROUNDUP", "ROUNDDOWN", "ABS", "SQRT",
                "POWER", "MOD", "INT", "TRUNC", "CEILING", "FLOOR",
                "SUMPRODUCT",
                "LEFT", "RIGHT", "MID", "LEN", "TRIM", "UPPER",
                "LOWER", "PROPER", "CONCATENATE", "FIND", "SEARCH",
                "REPLACE", "SUBSTITUTE", "TEXT", "VALUE", "REPT",
                "EXACT",
                "TODAY", "NOW", "YEAR", "MONTH", "DAY", "DATE",
                "DATEDIF", "EDATE", "EOMONTH", "WEEKDAY", "WEEKNUM",
                "NETWORKDAYS", "WORKDAY", "HOUR", "MINUTE", "SECOND",
                "PMT", "FV", "PV", "NPV", "IRR", "RATE", "NPER",
                "SLN", "DB"
            }
            if fn not in supported:
                return {
                    "level": "warning",
                    "msg": f"函数 {fn} 未在兼容列表中"
                }

        return {"level": "ok"}