# beeoffice/plugins/beesheet_plugin.py
"""
蜜算插件：将 BeeSheetView 包装为符合 Plugin 基类的插件
"""
import logging
from datetime import datetime

from PySide6.QtWidgets import QWidget, QMessageBox, QFileDialog

from beeoffice.plugin_base import Plugin


class BeeSheetPlugin(Plugin):
    """蜜算插件"""

    name = "蜜算 BeeSheet"
    version = "1.0"
    description = "表格处理、公式引擎、图表生成、数据分析"
    author = "TomJerryGit"

    def __init__(self, parent=None):
        super().__init__(parent)

    # ---------- 创建控件 ----------
    def create_widget(self, parent=None) -> QWidget:
        """创建蜜算表格视图实例"""
        from beeoffice.plugins.beesheet import BeeSheetView
        return BeeSheetView(parent or self.parent)

    # ---------- 命令注册 ----------
    def register_commands(self, palette):
        """注册蜜算相关命令到命令面板"""
        palette.register_command(
            "蜜算：新建表格",
            "创建一个新的蜜算表格",
            self.new_sheet
        )
        palette.register_command(
            "蜜算：导入数据",
            "从 CSV/Excel 文件导入数据",
            self.import_data
        )
        palette.register_command(
            "蜜算：导出表格",
            "将当前表格导出为 Excel",
            self.export_xlsx
        )
        palette.register_command(
            "蜜算：生成图表",
            "根据选中数据生成图表",
            self.generate_chart
        )
        palette.register_command(
            "蜜算：智能数据分析",
            "对当前数据进行统计分析",
            self.analyze_data
        )
        palette.register_command(
            "蜜算：自然语言生成公式",
            "用中文指令生成公式",
            self.nl_to_formula
        )
        palette.register_command(
            "蜜算：数据清洗",
            "去除重复行、空值处理",
            self.clean_data
        )
        palette.register_command(
            "蜜算：录制宏",
            "开始/停止录制宏",
            self.toggle_macro_recording
        )
        palette.register_command(
            "蜜算：播放宏",
            "执行已录制的宏",
            self.play_macro
        )

    # ---------- 新建表格 ----------
    def new_sheet(self) -> QWidget:
        """新建一个蜜算表格并添加为标签页"""
        view = self.create_widget()
        timestamp = datetime.now().strftime("%H%M")
        self.parent.tab_manager.addTab(view, f"📊 蜜算-{timestamp}")
        self.parent.tab_manager.setCurrentWidget(view)
        return view

    # ---------- 获取当前表格 ----------
    def _current_view(self):
        """返回当前标签页的蜜算视图（若非蜜算则返回 None）"""
        widget = self.parent.tab_manager.currentWidget()
        if widget is None:
            return None
        from beeoffice.plugins.beesheet import BeeSheetView
        if isinstance(widget, BeeSheetView):
            return widget
        return None

    # ---------- 导入数据 ----------
    def import_data(self):
        """从文件导入数据"""
        view = self._current_view()
        if not view:
            # 如果没有蜜算标签，先新建一个
            view = self.new_sheet()

        path, _ = QFileDialog.getOpenFileName(
            self.parent, "导入数据", "",
            "表格文件 (*.csv *.xlsx *.xls);;CSV (*.csv);;Excel (*.xlsx *.xls);;所有文件 (*)"
        )
        if not path:
            return

        if hasattr(view, "_import_file_from_path"):
            try:
                self.parent.set_global_status("正在导入数据...", 0)
                view._import_file_from_path(path)
                self.parent.tab_manager.set_tab_file_path(view, path)
                if hasattr(self.parent, "_add_file_watch"):
                    self.parent._add_file_watch(path)
                self.parent.set_global_status(f"已导入: {path}", 3000)
            except Exception as e:
                logging.error(f"导入数据失败: {e}")
                QMessageBox.warning(self.parent, "导入失败", str(e))
        else:
            QMessageBox.information(self.parent, "提示", "当前表格不支持导入功能")

    # ---------- 导出表格 ----------
    def export_xlsx(self):
        """导出当前表格为 Excel"""
        view = self._current_view()
        if not view:
            self._warn("请先打开一个蜜算表格")
            return
        if hasattr(view, "_export_xlsx"):
            try:
                view._export_xlsx()
            except Exception as e:
                logging.error(f"导出表格失败: {e}")
                QMessageBox.warning(self.parent, "导出失败", str(e))
        else:
            self._warn("当前表格不支持导出功能")

    # ---------- 图表 ----------
    def generate_chart(self):
        """生成图表"""
        view = self._current_view()
        if not view:
            self._warn("请先打开一个蜜算表格")
            return

        # 优先调用视图自身的图表方法
        if hasattr(view, "generate_chart"):
            try:
                view.generate_chart()
                return
            except Exception as e:
                logging.error(f"生成图表失败: {e}")
                QMessageBox.warning(self.parent, "生成图表失败", str(e))
                return

        # 回退实现
        self._generate_chart_fallback(view)

    def _generate_chart_fallback(self, view):
        """回退的图表生成实现"""
        try:
            from beeoffice.plugins.beesheet import ChartDialog
            if not hasattr(view, "model") or view.model is None:
                self._warn("当前表格无数据")
                return
            df = getattr(view.model, "df", None)
            if df is None or df.empty:
                self._warn("当前表格无数据")
                return
            dialog = ChartDialog(df, self.parent)
            dialog.exec()
        except ImportError:
            self._warn("图表功能不可用，请检查 beesheet 模块")
        except Exception as e:
            logging.error(f"生成图表失败: {e}")
            QMessageBox.warning(self.parent, "生成图表失败", str(e))

    # ---------- 数据分析 ----------
    def analyze_data(self):
        """智能数据分析"""
        view = self._current_view()
        if not view:
            self._warn("请先打开一个蜜算表格")
            return
        if hasattr(view, "_analyze_data"):
            try:
                view._analyze_data()
            except Exception as e:
                logging.error(f"数据分析失败: {e}")
                QMessageBox.warning(self.parent, "分析失败", str(e))
        else:
            self._warn("当前表格不支持数据分析")

    # ---------- 自然语言生成公式 ----------
    def nl_to_formula(self):
        """自然语言生成公式"""
        view = self._current_view()
        if not view:
            self._warn("请先打开一个蜜算表格")
            return

        # 优先调用视图自身的方法
        if hasattr(view, "_nl_to_formula"):
            try:
                view._nl_to_formula()
                return
            except Exception as e:
                logging.error(f"自然语言生成公式失败: {e}")
                QMessageBox.warning(self.parent, "生成失败", str(e))
                return

        # 回退实现
        self._nl_to_formula_fallback(view)

    def _nl_to_formula_fallback(self, view):
        """回退的自然语言生成公式实现"""
        from PySide6.QtWidgets import QInputDialog
        from beeoffice.plugins.nl_formula import NLFormulaParser
        try:
            text, ok = QInputDialog.getText(
                self.parent,
                "自然语言生成公式",
                "输入指令（如：求和A1到A10）："
            )
            if not ok or not text:
                return

            result = NLFormulaParser.parse(text)
            if not result:
                QMessageBox.warning(self.parent, "无法解析",
                                    "无法理解指令，请尝试：求和A1到A10")
                return

            # 插入到当前选中单元格
            if hasattr(view, "table_view") and hasattr(view, "model"):
                index = view.table_view.currentIndex()
                if index.isValid():
                    from PySide6.QtCore import Qt
                    view.model.setData(index, result, Qt.EditRole)
                    self.parent.set_global_status(f"已插入公式: {result}", 3000)
                else:
                    QMessageBox.warning(self.parent, "提示", "请先选择一个单元格")
        except Exception as e:
            logging.error(f"自然语言生成公式失败: {e}")
            QMessageBox.warning(self.parent, "生成失败", str(e))

    # ---------- 数据清洗 ----------
    def clean_data(self):
        """数据清洗：去除重复行、空值处理"""
        view = self._current_view()
        if not view:
            self._warn("请先打开一个蜜算表格")
            return

        if not hasattr(view, "model") or view.model is None:
            self._warn("当前表格无数据")
            return

        df = getattr(view.model, "df", None)
        if df is None or df.empty:
            self._warn("当前表格无数据")
            return

        # 简单清洗：去除完全重复的行
        original_count = len(df)
        cleaned = df.drop_duplicates()
        removed = original_count - len(cleaned)

        if removed == 0:
            QMessageBox.information(self.parent, "提示", "未发现重复行")
            return

        reply = QMessageBox.question(
            self.parent, "数据清洗",
            f"发现 {removed} 行重复数据，是否删除？",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.Yes
        )
        if reply != QMessageBox.Yes:
            return

        try:
            if hasattr(view.model, "update_data"):
                view.model.update_data(cleaned)
            elif hasattr(view.model, "set_data"):
                view.model.set_data(cleaned)
            else:
                view.model.df = cleaned
                if hasattr(view.model, "layoutChanged"):
                    view.model.layoutChanged.emit()
            self.parent.set_global_status(f"已删除 {removed} 行重复数据", 3000)
        except Exception as e:
            logging.error(f"数据清洗失败: {e}")
            QMessageBox.warning(self.parent, "清洗失败", str(e))

    # ---------- 宏 ----------
    def toggle_macro_recording(self):
        """切换宏录制状态"""
        view = self._current_view()
        if not view:
            self._warn("请先打开一个蜜算表格")
            return
        if hasattr(view, "_toggle_macro_recording"):
            try:
                view._toggle_macro_recording()
            except Exception as e:
                logging.error(f"宏录制失败: {e}")
                QMessageBox.warning(self.parent, "宏录制失败", str(e))
        else:
            self._warn("当前表格不支持宏录制")

    def play_macro(self):
        """播放已录制的宏"""
        view = self._current_view()
        if not view:
            self._warn("请先打开一个蜜算表格")
            return
        if hasattr(view, "_play_macro"):
            try:
                view._play_macro()
            except Exception as e:
                logging.error(f"播放宏失败: {e}")
                QMessageBox.warning(self.parent, "播放宏失败", str(e))
        else:
            self._warn("当前表格不支持宏播放")

    # ---------- 辅助 ----------
    def _warn(self, message: str):
        """统一提示"""
        QMessageBox.information(self.parent, "提示", message)

    # ---------- 生命周期 ----------
    def on_close(self):
        """插件关闭时清理"""
        super().on_close()
        logging.info("蜜算插件已卸载")