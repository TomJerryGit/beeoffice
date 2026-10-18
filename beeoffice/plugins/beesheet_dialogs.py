# beeoffice/plugins/beesheet_dialogs.py
"""
蜜算对话框：数据透视表配置
"""
import pandas as pd
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QFormLayout,
    QListWidget, QComboBox, QCheckBox, QPushButton, QTextEdit,
    QMessageBox, QAbstractItemView
)
from beeoffice.i18n import tr


class PivotTableDialog(QDialog):
    """数据透视表配置对话框"""

    def __init__(self, df, parent=None):
        super().__init__(parent)
        self.setWindowTitle(tr("auto.beesheet_dialogs.0b120dcd", "📊 数据透视表"))
        self.resize(560, 480)
        self.df = df
        self.result_config = None

        # 过滤掉完全空的行
        self.df = df[df.apply(
            lambda row: not all(
                str(v).strip() == '' or pd.isna(v) for v in row
            ),
            axis=1
        )]

        layout = QVBoxLayout(self)

        # 提示
        tip = QLabel(
            "选择行、列、值字段，生成汇总表。"
            "建议先确认数据第一行是表头。"
        )
        tip.setStyleSheet("color:#666;font-size:12px;padding:4px;")
        layout.addWidget(tip)

        # ===== 字段选择 =====
        form = QFormLayout()
        cols = list(self.df.columns)

        # 行字段
        self.row_list = QListWidget()
        self.row_list.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.row_list.setMaximumHeight(100)
        for c in cols:
            self.row_list.addItem(str(c))
        form.addRow("行字段（可多选）:", self.row_list)

        # 列字段
        self.col_list = QListWidget()
        self.col_list.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.col_list.setMaximumHeight(100)
        for c in cols:
            self.col_list.addItem(str(c))
        form.addRow("列字段（可选）:", self.col_list)

        # 值字段
        self.value_list = QListWidget()
        self.value_list.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.value_list.setMaximumHeight(100)
        for c in cols:
            self.value_list.addItem(str(c))
        form.addRow("值字段（可多选）:", self.value_list)

        # 聚合方式
        self.agg_combo = QComboBox()
        self.agg_combo.addItems(["求和", "平均", "计数", "最大值", "最小值"])
        form.addRow("聚合方式:", self.agg_combo)

        # 显示总计
        self.margins_check = QCheckBox(tr("auto.beesheet_dialogs.8a74e8e0", "显示行列总计"))
        form.addRow(self.margins_check)

        layout.addLayout(form)

        # ===== 按钮 =====
        bl = QHBoxLayout()
        preview_btn = QPushButton(tr("auto.beesheet_dialogs.5178a7de", "👁 预览"))
        preview_btn.clicked.connect(self._preview)
        bl.addWidget(preview_btn)
        bl.addStretch()

        ok_btn = QPushButton(tr("auto.beesheet_dialogs.9a157ea8", "✅ 生成"))
        ok_btn.setStyleSheet(
            "QPushButton{background:#FFB300;color:#000;"
            "padding:6px 16px;border:none;border-radius:4px;"
            "font-weight:bold;}"
            "QPushButton:hover{background:#FFA000;}"
        )
        ok_btn.clicked.connect(self._generate)
        bl.addWidget(ok_btn)

        cancel_btn = QPushButton(tr("auto.beesheet_dialogs.4d0b4688", "取消"))
        cancel_btn.clicked.connect(self.reject)
        bl.addWidget(cancel_btn)
        layout.addLayout(bl)

        # ===== 预览区 =====
        self.preview_area = QTextEdit()
        self.preview_area.setReadOnly(True)
        self.preview_area.setStyleSheet(
            "QTextEdit{background:#FAFAFA;font-family:Consolas;"
            "font-size:12px;}"
        )
        self.preview_area.setMaximumHeight(120)
        layout.addWidget(self.preview_area)

    # ==================== 配置收集 ====================
    def _get_config(self):
        """从界面收集配置"""
        rows = [item.text() for item in self.row_list.selectedItems()]
        cols = [item.text() for item in self.col_list.selectedItems()]
        values = [item.text() for item in self.value_list.selectedItems()]
        agg_map = {
            "求和": "sum",
            "平均": "mean",
            "计数": "count",
            "最大值": "max",
            "最小值": "min",
        }
        aggfunc = agg_map.get(self.agg_combo.currentText(), "sum")

        if not rows and not cols:
            return None
        if not values:
            return None
        return {
            "rows": rows,
            "cols": cols,
            "values": values,
            "aggfunc": aggfunc,
            "margins": self.margins_check.isChecked(),
        }

    # ==================== 生成透视表 ====================
    def _build_pivot(self, config):
        """根据配置生成透视表"""
        try:
            kwargs = {
                "index": config["rows"] if config["rows"] else None,
                "columns": config["cols"] if config["cols"] else None,
                "values": config["values"],
                "aggfunc": config["aggfunc"],
                "margins": config["margins"],
            }
            # 如果 index 为 None，pandas 需要至少一个 index
            if not kwargs["index"] and not kwargs["columns"]:
                return None, "必须至少指定行字段或列字段"

            pivot = pd.pivot_table(self.df, **kwargs)

            # 展平多级列索引
            if isinstance(pivot.columns, pd.MultiIndex):
                pivot.columns = [
                    "_".join(str(x) for x in col if x)
                    for col in pivot.columns
                ]
            if isinstance(pivot.index, pd.MultiIndex):
                pivot = pivot.reset_index()

            # 用默认整数索引
            pivot = pivot.reset_index(drop=True)

            # 填充空值
            pivot = pivot.fillna(0)
            return pivot, None
        except Exception as e:
            return None, str(e)

    # ==================== 预览 ====================
    def _preview(self):
        """预览前 10 行"""
        config = self._get_config()
        if not config:
            self.preview_area.setPlainText(
                "请至少选择：1 个行/列字段 + 1 个值字段"
            )
            return
        pivot, err = self._build_pivot(config)
        if err:
            self.preview_area.setPlainText(f"❌ 生成失败：{err}")
            return
        text = f"共 {len(pivot)} 行 × {len(pivot.columns)} 列\n\n"
        text += pivot.head(10).to_string(index=False)
        if len(pivot) > 10:
            text += f"\n\n... 还有 {len(pivot) - 10} 行"
        self.preview_area.setPlainText(text)

    # ==================== 生成并返回结果 ====================
    def _generate(self):
        """生成并返回结果"""
        config = self._get_config()
        if not config:
            QMessageBox.warning(
                self, tr("auto.beesheet_dialogs.ab3656a9", "提示"),
                tr("auto.beesheet_dialogs.db6477f0", "请至少选择：1 个行/列字段 + 1 个值字段")
            )
            return
        pivot, err = self._build_pivot(config)
        if err:
            QMessageBox.warning(self, tr("auto.beesheet_dialogs.64ba75d9", "生成失败"), err)
            return
        self.result_config = (pivot, config)
        self.accept()