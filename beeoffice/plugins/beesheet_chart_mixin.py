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
  - pandas（pd.isna）
  - numpy（np.linspace）
  - matplotlib（延迟 import，未安装时静默返回）
  - PySide6（QDialog / QVBoxLayout / QPushButton / QFileDialog / QMessageBox）

注意：
  - 所有方法依赖 self.model / self.table_view / self._set_status /
    self._find_main_window 等，由 BeeSheetView 主类提供
  - _show_pivot_table 里延迟 import BeeSheetView 以避免循环依赖
"""
import pandas as pd
import numpy as np

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QPushButton, QFileDialog, QMessageBox,
)
from PySide6.QtCore import Qt

from beeoffice.plugins.beesheet_dialogs import PivotTableDialog
from beeoffice.i18n import tr


class ChartMixin:
    """蜜算图表相关功能的 Mixin"""

    # ==================== 图表类型选择 ====================
    def _create_chart(self):
        """弹出图表类型选择对话框，用户选择后调用 _generate_chart"""
        sel = self.table_view.selectionModel().selection()
        if not sel:
            QMessageBox.information(self, tr("auto.beesheet_chart_mixin.ab3656a9", "提示"), tr("auto.beesheet_chart_mixin.1b9519cd", "请先选中数据"))
            return
        dlg = QDialog(self)
        layout = QVBoxLayout(dlg)
        selected = {"value": "bar"}
        for label, ct in [("柱状图", "bar"), ("折线图", "line"),
                           ("饼图", "pie"), ("散点图", "scatter"),
                           ("面积图", "area"), ("雷达图", "radar")]:
            btn = QPushButton(label)
            btn.clicked.connect(
                lambda checked=False, t=ct:
                    [selected.update({"value": t}), dlg.accept()]
            )
            layout.addWidget(btn)
        dlg.exec()
        if selected["value"]:
            self._generate_chart(selected["value"])

    # ==================== 图表生成 ====================
    def _generate_chart(self, chart_type):
        """
        根据选中数据生成图表

        :param chart_type: "bar" / "line" / "pie" / "scatter" / "area" / "radar"
        """
        try:
            import matplotlib.pyplot as plt
            # Qt6 / PySide6 应使用 backend_qtagg。
            # backend_qt5agg 在 matplotlib 3.5+ 只是兼容垫片，而且
            # beeoffice.spec 曾把它列进 excludes，导致打包后图表必崩。
            try:
                from matplotlib.backends.backend_qtagg import (
                    FigureCanvasQTAgg,
                )
            except ImportError:  # matplotlib < 3.5
                from matplotlib.backends.backend_qt5agg import (
                    FigureCanvasQTAgg,
                )
        except ImportError:
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
                QMessageBox.information(self, tr("auto.beesheet_chart_mixin.ab3656a9", "提示"), tr("auto.beesheet_chart_mixin.3118d931", "饼图数据全为零"))
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

        # 弹出图表窗口
        dlg = QDialog(self)
        layout = QVBoxLayout(dlg)
        canvas = FigureCanvasQTAgg(fig)
        layout.addWidget(canvas)
        layout.addWidget(QPushButton(
            tr("auto.beesheet_chart_mixin.a927c749", "保存图片"), clicked=lambda: self._save_chart(fig, dlg)
        ))
        dlg.resize(650, 480)
        dlg.setAttribute(Qt.WA_DeleteOnClose)
        dlg.show()

    # ==================== 图表保存 ====================
    def _save_chart(self, fig, parent):
        """将 matplotlib figure 保存为 PNG"""
        path, _ = QFileDialog.getSaveFileName(
            parent, tr("auto.beesheet_chart_mixin.fadf24db", "保存"), tr("auto.beesheet_chart_mixin.4999c234", "图表.png"), "PNG (*.png)"
        )
        if path:
            fig.savefig(path, dpi=150, bbox_inches='tight')
            self._set_status(tr("auto.beesheet_chart_mixin.cdfab96f", "已保存"), 3000)

    # ==================== 数据透视表 ====================
    def _show_pivot_table(self):
        """打开数据透视表对话框，在新标签页生成结果"""
        df = self.model.df
        if df is None or df.empty:
            QMessageBox.information(self, tr("auto.beesheet_chart_mixin.ab3656a9", "提示"), tr("auto.beesheet_chart_mixin.2e9899f6", "当前表格没有数据"))
            return

        # 过滤掉全空行
        df_clean = df[df.apply(
            lambda row: not all(
                str(v).strip() == '' or pd.isna(v) for v in row
            ), axis=1
        )]
        if df_clean.empty:
            QMessageBox.information(self, tr("auto.beesheet_chart_mixin.ab3656a9", "提示"), tr("auto.beesheet_chart_mixin.4d978bfc", "当前表格没有有效数据"))
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
            QMessageBox.warning(self, tr("auto.beesheet_chart_mixin.ab3656a9", "提示"), tr("auto.beesheet_chart_mixin.3e498b13", "无法创建新标签页"))
            return

        # 延迟 import 避免循环依赖
        from beeoffice.plugins.beesheet import BeeSheetView as _BSV
        new_sheet = _BSV()
        new_sheet.model.set_full_dataframe(pivot)
        new_sheet.table_view.setModel(new_sheet.model)
        new_sheet._auto_resize_columns()

        agg_cn = {"sum": "求和", "mean": "平均", "count": "计数",
                  "max": "最大", "min": "最小"}.get(
            config["aggfunc"], config["aggfunc"])
        title = f"📊 透视-{agg_cn}"

        parent.tab_manager.addTab(new_sheet, title)
        parent.tab_manager.setCurrentWidget(new_sheet)
        self._set_status(
            f"✅ 已生成透视表：{len(pivot)} 行 × {len(pivot.columns)} 列", 5000
        )