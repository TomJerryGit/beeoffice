# beeoffice/plugins/beesheet_chart_mixin.py
"""
蜜算图表 Mixin

职责：
  - _create_chart       : 图表类型选择对话框
  - _generate_chart     : 根据选中数据生成图表（柱状/折线/饼图/散点/面积/雷达）
  - _save_chart         : 保存图表为 PNG
  - _show_pivot_table   : 数据透视表（在新标签页生成）

从 beesheet.py 抽取，降低主文件复杂度。

依赖：
  - numpy（np.linspace）
  - matplotlib（延迟 import，未安装时静默返回）
  - PySide6（QDialog / QVBoxLayout / QPushButton / QFileDialog / QMessageBox）

注意：
  - 所有方法依赖 self.model / self.table_view / self._set_status /
    self._find_main_window 等，由 BeeSheetView 主类提供
  - _show_pivot_table 里延迟 import BeeSheetView 以避免循环依赖
  - 透视表的**计算与落盘**已移到 `beesheet_pivot.py`（纯逻辑，便于测试）；
    本文件不再直接依赖 pandas
"""
import numpy as np

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QPushButton, QFileDialog, QMessageBox,
)
from PySide6.QtCore import Qt

from beeoffice.plugins.beesheet_dialogs import PivotTableDialog


class ChartMixin:
    """蜜算图表相关功能的 Mixin"""

    # ==================== 图表类型选择 ====================
    def _create_chart(self):
        """弹出图表类型选择对话框，用户选择后调用 _generate_chart"""
        # R1 安全门：图表基于整表数据
        if not self._ensure_full_data("插入图表"):
            return
        # 审计 §2.14：缺 matplotlib 时原先"插入图表"**什么都不发生**。
        # 在让用户选之前就检查，避免"选完才失败"。
        if not self._matplotlib_available():
            QMessageBox.warning(
                self, "提示",
                "当前环境没有安装 matplotlib，无法绘制图表。\n\n"
                "安装方式：pip install matplotlib",
            )
            return
        sel = self.table_view.selectionModel().selection()
        if not sel:
            QMessageBox.information(self, "提示", "请先选中数据")
            return
        dlg = QDialog(self)
        layout = QVBoxLayout(dlg)
        # ⚠️ 初值必须是 None：原先初值就是 "bar"，而下面判断
        # `if selected["value"]` —— 恒为真 → **取消对话框也会画一张柱状图**
        # （审计报告 §2.14 的"取消语义不对"）。
        selected = {"value": None}
        for label, ct in [("柱状图", "bar"), ("折线图", "line"),
                           ("饼图", "pie"), ("散点图", "scatter"),
                           ("面积图", "area"), ("雷达图", "radar")]:
            btn = QPushButton(label)
            btn.clicked.connect(
                lambda checked=False, t=ct:
                    [selected.update({"value": t}), dlg.accept()]
            )
            layout.addWidget(btn)
        accepted = dlg.exec() == QDialog.DialogCode.Accepted
        if accepted and selected["value"]:
            self._generate_chart(selected["value"])

    @staticmethod
    def _matplotlib_available() -> bool:
        """matplotlib 是否可用（只做导入探测，不初始化后端）。"""
        try:
            import importlib.util

            return importlib.util.find_spec("matplotlib") is not None
        except Exception:  # noqa: BLE001
            return False

    # ==================== 图表生成 ====================
    def _generate_chart(self, chart_type):
        """
        根据选中数据生成图表

        :param chart_type: "bar" / "line" / "pie" / "scatter" / "area" / "radar"
        """
        try:
            import matplotlib.pyplot as plt
            from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg
        except ImportError:
            # 兜底提示（正常情况下 `_create_chart` 已经先拦过一次）
            QMessageBox.warning(
                self, "提示",
                "当前环境没有安装 matplotlib，无法绘制图表。\n\n"
                "安装方式：pip install matplotlib",
            )
            return

        # 收集选中区域的坐标
        indexes = sorted(
            [(i.row(), i.column()) for i in
             self.table_view.selectionModel().selection().indexes()],
            key=lambda x: (x[0], x[1])
        )
        rows = sorted(set(r for r, _ in indexes))
        cols = sorted(set(c for _, c in indexes))

        # 组装数据
        data = []
        labels = []
        for r in rows:
            row_data = []
            for c in cols:
                v = str(self.model.get_value(r, c))
                if v.replace('.', '', 1).replace('-', '', 1).isdigit():
                    row_data.append(float(self.model.get_value(r, c)))
                else:
                    row_data.append(0)
            data.append(row_data)
            if cols:
                labels.append(str(self.model.get_value(r, cols[0])))

        fig, ax = plt.subplots(figsize=(7, 5))

        if chart_type == 'bar':
            ax.bar(range(len(labels)), [r[-1] for r in data], color='#FFB300')
            ax.set_xticks(range(len(labels)))
            ax.set_xticklabels(labels, rotation=45, ha='right')
        elif chart_type == 'line':
            ax.plot([r[-1] for r in data], 'o-', color='#FF8F00')
            ax.set_xticks(range(len(labels)))
            ax.set_xticklabels(labels, rotation=45, ha='right')
        elif chart_type == 'pie' and data:
            pie_data = [abs(x) for x in (data[0] if data else [])]
            if sum(pie_data) == 0:
                QMessageBox.information(self, "提示", "饼图数据全为零")
                plt.close(fig)
                return
            ax.pie(pie_data,
                    labels=[str(self.model.df.columns[c]) for c in cols],
                    autopct='%1.1f%%')
        elif chart_type == 'scatter' and len(data) > 0:
            ax.scatter([r[0] for r in data], [r[-1] for r in data])
        elif chart_type == 'area':
            for row in data:
                ax.fill_between(range(len(row)), row, alpha=0.3)
                ax.plot(row)
        elif chart_type == 'radar' and data:
            vals = data[0]
            angles = np.linspace(0, 2 * np.pi, len(vals),
                                  endpoint=False).tolist()
            vals += vals[:1]
            angles += angles[:1]
            ax.fill(angles, vals, alpha=0.25)
            ax.plot(angles, vals)

        ax.set_title("蜜蜂图表")
        plt.tight_layout()

        # P1：记下图表规格 —— 保存时写成**原生 Excel 图表**。
        # 原先这个功能只是 matplotlib 预览（+ 存 PNG），**从来没有进过 xlsx**：
        # 用户在应用里"生成图表"，工作簿里其实什么都没有。
        if rows and cols:
            specs = getattr(self, "_charts", None)
            if specs is None:
                specs = self._charts = []
            specs.append({
                "type": str(chart_type),
                "rows": (rows[0], rows[-1]),
                "cols": (cols[0], cols[-1]),
                "title": "蜜蜂图表",
            })
            self._set_status("图表已生成；保存后它会写入工作簿", 4000)

        # 弹出图表窗口
        dlg = QDialog(self)
        layout = QVBoxLayout(dlg)
        canvas = FigureCanvasQTAgg(fig)
        layout.addWidget(canvas)
        layout.addWidget(QPushButton(
            "保存图片", clicked=lambda: self._save_chart(fig, dlg)
        ))
        dlg.resize(650, 480)
        dlg.setAttribute(Qt.WA_DeleteOnClose)
        dlg.show()

    # ==================== 图表保存 ====================
    def _save_chart(self, fig, parent):
        """将 matplotlib figure 保存为 PNG"""
        path, _ = QFileDialog.getSaveFileName(
            parent, "保存", "图表.png", "PNG (*.png)"
        )
        if path:
            fig.savefig(path, dpi=150, bbox_inches='tight')
            self._set_status("已保存", 3000)

    # ==================== 数据透视表 ====================
    def _show_pivot_table(self):
        """打开数据透视表对话框，在新标签页生成结果"""
        # R1 安全门：透视表要统计整表
        if not self._ensure_full_data("透视表"):
            return
        df = self.model.df
        if df is None or df.empty:
            QMessageBox.information(self, "提示", "当前表格没有数据")
            return

        # 过滤掉全空行（模型会把数据补齐到默认行数，尾部是空的；
        # 不过滤的话 sum 会把空值算错。与「刷新透视表」共用同一个函数）
        from beeoffice.plugins.beesheet_pivot import drop_empty_rows

        df_clean = drop_empty_rows(df)
        if df_clean.empty:
            QMessageBox.information(self, "提示", "当前表格没有有效数据")
            return

        dlg = PivotTableDialog(df_clean, self)
        if dlg.exec() != QDialog.Accepted:
            return
        if not dlg.result_config:
            return

        pivot, config = dlg.result_config

        # 在新标签页生成
        parent = self._find_main_window()
        if not parent or not hasattr(parent, 'tab_manager'):
            QMessageBox.warning(self, "提示", "无法创建新标签页")
            return

        # 延迟 import 避免循环依赖
        from beeoffice.plugins.beesheet import BeeSheetView as _BSV
        new_sheet = _BSV()
        new_sheet.model.set_full_dataframe(pivot)
        new_sheet.table_view.setModel(new_sheet.model)
        new_sheet._auto_resize_columns()

        # P1：**记住透视表规格** —— 原先 config 当场丢弃，于是关掉标签页
        # 就再也重算不了、存成文件后也看不出这是怎么汇总的。
        # 保存时会写进文件的隐藏表（规格 + 数据快照），之后可以「刷新透视表」。
        source_sheet = getattr(self, "_active_sheet_name", "") or ""
        new_sheet._pivot_spec = {
            "spec": dict(config),
            "source_sheet": source_sheet,
            "source_path": getattr(self, "_current_file_path", None),
        }
        new_sheet._pivot_source_df = df_clean

        agg_cn = {"sum": "求和", "mean": "平均", "count": "计数",
                  "max": "最大", "min": "最小"}.get(
            config["aggfunc"], config["aggfunc"])
        title = f"📊 透视-{agg_cn}"

        parent.tab_manager.addTab(new_sheet, title)
        parent.tab_manager.setCurrentWidget(new_sheet)
        self._set_status(
            f"✅ 已生成透视表：{len(pivot)} 行 × {len(pivot.columns)} 列"
            "（保存后可直接「刷新透视表」）", 6000
        )