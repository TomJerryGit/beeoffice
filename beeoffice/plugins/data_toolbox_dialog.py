# beeoffice/plugins/data_toolbox_dialog.py
"""S2 数据工具箱 MVP：去重 / 去空白 / 统计摘要 / 多级排序入口。"""
from __future__ import annotations

import pandas as pd
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
)

from beeoffice.plugins.data_insights import clean_table, recommend_charts


def dedupe_df(df: pd.DataFrame) -> pd.DataFrame:
    return df.drop_duplicates(ignore_index=True)


def trim_df(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    for col in out.columns:
        if out[col].dtype == object:
            out[col] = out[col].map(
                lambda v: v.strip() if isinstance(v, str) else v
            )
    return out


def summary_text(df: pd.DataFrame) -> str:
    lines = [f"行数: {len(df)}", f"列数: {len(df.columns)}", ""]
    for col in df.columns:
        series = df[col]
        missing = int(series.isna().sum())
        lines.append(f"{col}: 空值 {missing}")
    return "\n".join(lines)


class DataToolboxDialog(QDialog):
    def __init__(self, view, parent=None):
        super().__init__(parent)
        self._view = view
        self.setWindowTitle("🧰 数据工具箱")
        self.resize(560, 420)
        self.info = QLabel("选择操作；结果会直接更新当前工作表。")
        self.log = QTextEdit()
        self.log.setReadOnly(True)

        row = QHBoxLayout()
        for text, slot in [
            ("删除重复行", self._dedupe),
            ("去除首尾空白", self._trim),
            ("统计摘要", self._summary),
            ("多级排序…", self._sort),
        ]:
            btn = QPushButton(text)
            btn.clicked.connect(slot)
            row.addWidget(btn)
        row2 = QHBoxLayout()
        for text, slot in [
            ("数据透视表…", self._pivot),
            ("图表推荐…", self._recommend_chart),
            ("一键清洗", self._clean),
        ]:
            btn = QPushButton(text)
            btn.clicked.connect(slot)
            row2.addWidget(btn)
        close_btn = QPushButton("关闭")
        close_btn.clicked.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addWidget(self.info)
        layout.addLayout(row)
        layout.addLayout(row2)
        layout.addWidget(self.log, 1)
        layout.addWidget(close_btn)

    def _df(self):
        return self._view.model.df

    def _replace(self, df, label):
        self._view.model.set_full_dataframe(df)
        self._view.table_view.setModel(self._view.model)
        self._view._set_status(f"{label}：{len(df)} 行", 3000)
        self.log.append(f"✅ {label}，当前 {len(df)} 行 × {len(df.columns)} 列")

    def _dedupe(self):
        before = len(self._df())
        df = dedupe_df(self._df())
        self._replace(df, f"删除重复行 {before - len(df)} 行")

    def _trim(self):
        self._replace(trim_df(self._df()), "去除首尾空白")

    def _summary(self):
        self.log.setPlainText(summary_text(self._df()))

    def _sort(self):
        try:
            self._view._show_sort_dialog()
        except Exception as e:  # noqa: BLE001
            self.log.append(f"✗ 排序入口失败：{type(e).__name__}: {e}")

    def _pivot(self):
        if not hasattr(self._view, "_show_pivot_table"):
            self.log.append("✗ 当前视图不支持数据透视表")
            return
        try:
            self._view._show_pivot_table()
            self.log.append("✅ 已打开数据透视表对话框")
        except Exception as e:  # noqa: BLE001
            self.log.append(f"✗ 透视表失败：{type(e).__name__}: {e}")

    def _recommend_chart(self):
        recs = recommend_charts(self._df())
        if not recs:
            self.log.append("✗ 当前数据没有可推荐的图表（需要数值/分类列）")
            return
        labels = [f"{r['label']}：{r['reason']}" for r in recs]
        item, ok = QInputDialog.getItem(
            self, "图表推荐", "选择推荐图表：", labels, 0, False
        )
        if not ok or not item:
            return
        index = labels.index(item)
        try:
            self._view.table_view.selectAll()
            self._view._generate_chart(recs[index]["type"])
            self.log.append(f"✅ 已生成推荐图表：{recs[index]['label']}")
        except Exception as e:  # noqa: BLE001
            self.log.append(f"✗ 生成图表失败：{type(e).__name__}: {e}")

    def _clean(self):
        out, report = clean_table(self._df())
        details = (
            f"空行 -{report['dropped_empty_rows']}，"
            f"空列 -{report['dropped_empty_cols']}，"
            f"重复 -{report['dropped_duplicates']}，"
            f"去空白 {report['trimmed_cells']} 处"
        )
        self._replace(out, f"一键清洗（{details}）")
        if report["numeric_cols"]:
            self.log.append("数字列：" + "、".join(report["numeric_cols"]))
