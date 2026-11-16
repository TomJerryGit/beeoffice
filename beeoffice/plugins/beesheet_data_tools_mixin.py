"""BeeSheet 数据整理工具：重复项、分列、分类汇总、合并计算。"""
from __future__ import annotations

import pandas as pd
from PySide6.QtWidgets import (
    QDialog, QDialogButtonBox, QInputDialog, QLabel, QMessageBox,
    QTableWidget, QTableWidgetItem, QVBoxLayout,
)


def remove_duplicate_rows(df: pd.DataFrame, subset=None) -> pd.DataFrame:
    """删除重复行，保留第一项。"""
    if df is None:
        return pd.DataFrame()
    return df.drop_duplicates(subset=subset, keep="first").reset_index(drop=True)


def split_column(df: pd.DataFrame, column: str, delimiter: str) -> pd.DataFrame:
    """把一列按分隔符拆成多列，替换原列。"""
    if df is None or column not in df.columns:
        return df
    parts = df[column].astype(str).str.split(delimiter, expand=True)
    parts.columns = [f"{column}_{i + 1}" for i in range(parts.shape[1])]
    pos = list(df.columns).index(column)
    left = df.iloc[:, :pos]
    right = df.iloc[:, pos + 1:]
    return pd.concat([left, parts, right], axis=1)


def subtotal(df: pd.DataFrame, group_col: str, value_cols, agg="sum") -> pd.DataFrame:
    """按分组列汇总数值列。"""
    if df is None or group_col not in df.columns:
        return pd.DataFrame()
    values = [c for c in value_cols if c in df.columns]
    if not values:
        return pd.DataFrame()
    return (
        df.groupby(group_col, dropna=False)[values]
        .agg(agg)
        .reset_index()
    )


def consolidate(frames, agg="sum") -> pd.DataFrame:
    """合并多个同样形状的区域；agg=sum/count/mean。"""
    frames = [f for f in frames if f is not None and not f.empty]
    if not frames:
        return pd.DataFrame()
    if agg == "count":
        return sum((f.notna().astype(int) for f in frames))
    if agg == "mean":
        return sum(frames) / len(frames)
    return sum(frames)


class DataToolsMixin:
    """BeeSheet 数据整理 UI。"""

    def _current_df(self):
        return getattr(self.model, "df", pd.DataFrame())

    def _apply_data_tools_df(self, df):
        if df is None or df.empty:
            return
        self.model.set_full_dataframe(df)
        self.model.layoutChanged.emit()
        self._set_status("数据已更新", 2000)

    def _remove_duplicates(self):
        df = self._current_df()
        result = remove_duplicate_rows(df)
        if len(result) == len(df):
            self._set_status("未发现重复行", 2000)
            return
        self._apply_data_tools_df(result)
        self._set_status(f"已删除 {len(df) - len(result)} 行重复项", 3000)

    def _split_column_dialog(self):
        idx = self.table_view.currentIndex()
        if not idx.isValid():
            return
        col = self._current_df().columns[idx.column()]
        text, ok = QInputDialog.getText(
            self, "分列", "分隔符（如 , 或 ; 或 \\t）："
        )
        if not ok or not text:
            return
        self._apply_data_tools_df(split_column(self._current_df(), col, text))
        self._set_status(f"已按“{text}”拆分列 {col}", 3000)

    def _show_subtotal_dialog(self):
        df = self._current_df()
        if df.empty:
            return
        group_col, ok = QInputDialog.getItem(
            self, "分类汇总", "分组列：", [str(c) for c in df.columns], 0, False
        )
        if not ok:
            return
        value_cols = [
            c for c in df.columns
            if c != group_col and pd.api.types.is_numeric_dtype(df[c])
        ]
        result = subtotal(df, group_col, value_cols)
        self._show_dataframe_dialog("分类汇总结果", result)

    def _show_consolidate_dialog(self):
        df = self._current_df()
        if df.empty:
            return
        text, ok = QInputDialog.getText(
            self, "合并计算",
            "输入区域（用 ; 分隔，如 A1:B3; D1:E3）：",
        )
        if not ok or not text:
            return
        frames = []
        for spec in text.split(";"):
            spec = spec.strip()
            if not spec:
                continue
            try:
                frames.append(self._read_range(spec))
            except Exception as e:  # noqa: BLE001
                QMessageBox.warning(self, "合并计算", f"区域无效: {spec}\n{e}")
                return
        self._show_dataframe_dialog("合并计算结果", consolidate(frames))

    def _read_range(self, spec: str) -> pd.DataFrame:
        from beeoffice.plugins.beesheet_utils import col_name_to_index

        def parse(cell):
            letters = "".join(ch for ch in cell if ch.isalpha())
            digits = "".join(ch for ch in cell if ch.isdigit())
            return int(digits) - 1, col_name_to_index(letters.upper())

        start, end = spec.upper().split(":")
        r0, c0 = parse(start)
        r1, c1 = parse(end)
        df = self._current_df()
        return df.iloc[r0:r1 + 1, c0:c1 + 1]

    def _show_dataframe_dialog(self, title, df):
        dlg = QDialog(self)
        dlg.setWindowTitle(title)
        dlg.resize(640, 360)
        layout = QVBoxLayout(dlg)
        layout.addWidget(QLabel(f"{title}（{len(df)} 行）"))
        table = QTableWidget(len(df), len(df.columns))
        table.setHorizontalHeaderLabels([str(c) for c in df.columns])
        for r in range(len(df)):
            for c in range(len(df.columns)):
                table.setItem(r, c, QTableWidgetItem(str(df.iloc[r, c])))
        layout.addWidget(table)
        btns = QDialogButtonBox(QDialogButtonBox.Close)
        btns.rejected.connect(dlg.reject)
        btns.accepted.connect(dlg.accept)
        btns.rejected.connect(dlg.reject)
        layout.addWidget(btns)
        dlg.exec()
