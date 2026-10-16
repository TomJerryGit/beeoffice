# tests/fidelity/test_p1_table_style_validations.py
"""
第五批：蜜算**表格样式 + 数据验证**落盘（写 + 读回）。

## 修前
* `_table_style`（预设：琥珀蜜蜂/海洋蓝/… 就是 `{header_bg, stripe_bg, stripe}`）
  与 `_data_validations`（`{(row, col): [选项…]}`，delegate 靠它弹下拉）
  和第四批修的那些一样：**只在内存里**，导出链零引用 → 保存后消失。

## 本批做的
* 表格样式 → 第一条数据行 + 隔行斑马纹的填充（**照实复刻屏幕**，见下方说明）；
* 数据验证 → 逐格的 openpyxl list 验证；
* 读回：从填充色反推预设（只需那三个键，模型就是这么渲染的）、
  从 `dataValidation` 反解下拉选项（并交给模型引用）。

## 一个如实记录、**没有擅自改**的发现
视图的 `_table_style_ref` 在 `beesheet_model.data()` 里写的是
`if r == 0: return header_bg`，而模型**没有表头行**（`r` 直接索引数据）→
那个"表头色"实际涂在**第一条数据行**上，不是列名表头。
本批**照实复刻屏幕**（保证"导出的文件 == 用户看到的表"），
off-by-one 留给后续统一修（已在审计报告记录）。

## 两个我自己的 bug（都有回归测试）
1. `len(getattr(self.model.df, "columns", []) or [])` —— 对 pandas **Index**
   做 `or []` 会抛"truth value of a Index is ambiguous"，整套样式写入被吞成一行日志；
2. `for row in ws["A2"]` —— `ws[区域]` 返回 **Cell**（不是元组），
   直接迭代抛 `'Cell' object is not iterable`，表现为"验证写进去了却读不回"。
"""
import sys
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

SLATE = {"header_bg": (255, 179, 0, 220), "stripe_bg": (255, 243, 224, 150)}


def _style_dict():
    from PySide6.QtGui import QColor

    return {
        "header_bg": QColor(*SLATE["header_bg"]),
        "stripe_bg": QColor(*SLATE["stripe_bg"]),
        "stripe": True,
    }


def _load(path):
    from openpyxl import load_workbook

    workbook = load_workbook(path)
    return workbook, workbook[workbook.sheetnames[0]]


@pytest.fixture
def sheet_view(qtbot):
    from PySide6.QtWidgets import QMessageBox

    from beeoffice.plugins.beesheet import BeeSheetView

    view = BeeSheetView()
    qtbot.addWidget(view)
    view.model.set_full_dataframe(
        pd.DataFrame({"状态": ["待办", "完成", "待办"], "负责人": ["甲", "乙", "丙"]})
    )
    view._set_status = lambda *a, **k: None
    QMessageBox.information = staticmethod(lambda *a, **k: None)
    QMessageBox.warning = staticmethod(lambda *a, **k: None)
    return view


# ==================== 1. 颜色换算（含 alpha 混合）====================

def test_qt_color_to_hex_with_and_without_alpha():
    from PySide6.QtGui import QColor

    from beeoffice.plugins.beesheet_style_export import _qt_color_to_hex

    assert _qt_color_to_hex(QColor(255, 179, 0)) == "FFB300"
    # 半透明色按 alpha 与白底混合（Excel 填充没有 alpha，直接丢 alpha 会更深）
    blended = _qt_color_to_hex(QColor(255, 179, 0, 220), blend_over_white=True)
    assert blended == "FFBD23", blended
    assert _qt_color_to_hex(None) is None


# ==================== 2. 表格样式：写 ====================

def test_table_style_is_persisted(sheet_view, tmp_path):
    """样式要通过**视图的保存路径**真的写进文件（这条守着我那个 Index 真值 bug）。"""
    target = tmp_path / "样式.xlsx"
    sheet_view._table_style = _style_dict()
    sheet_view.set_current_file_path(target)

    assert sheet_view.save() is True

    _, ws = _load(target)
    assert ws["A2"].fill.fill_type == "solid", "第一条数据行没有表头色"
    assert ws["A2"].fill.start_color.rgb.endswith("FFBD23")
    assert ws["A3"].fill.fill_type == "solid", "隔行斑马纹没有写"
    assert ws["A4"].fill.fill_type is None, "第 2 条数据不该有斑马纹（应是隔行）"


def test_table_style_none_is_noop(sheet_view, tmp_path):
    target = tmp_path / "无样式.xlsx"
    sheet_view._table_style = None
    sheet_view.set_current_file_path(target)

    sheet_view.save()

    _, ws = _load(target)
    assert ws["A2"].fill.fill_type is None


# ==================== 3. 表格样式：读回 ====================

def test_table_style_is_read_back(sheet_view, qtbot, tmp_path):
    target = tmp_path / "样式往返.xlsx"
    sheet_view._table_style = _style_dict()
    sheet_view.set_current_file_path(target)
    sheet_view.save()

    from beeoffice.plugins.beesheet import BeeSheetView

    reader = BeeSheetView()
    qtbot.addWidget(reader)
    reader._set_status = lambda *a, **k: None
    try:
        reader._import_file_from_path(str(target))

        style = reader._table_style or {}
        assert style.get("stripe") is True
        assert style.get("header_bg") is not None
        assert style["header_bg"].name().lower() == "#ffbd23"
        assert style["stripe_bg"].name().lower() == "#fff8ed"
        # 模型也要拿到引用（渲染时读的是它）
        assert reader.model._table_style_ref is not None
    finally:
        reader.close()


# ==================== 4. 数据验证：写 + 读回 + delegate 生效 ====================

def test_data_validation_is_persisted(sheet_view, tmp_path):
    target = tmp_path / "验证.xlsx"
    sheet_view._data_validations = {(0, 0): ["待办", "进行中", "完成"]}
    sheet_view.set_current_file_path(target)

    sheet_view.save()

    _, ws = _load(target)
    validations = list(ws.data_validations.dataValidation)
    assert len(validations) == 1, "下拉验证没有写进文件"
    assert validations[0].type == "list"
    assert str(validations[0].sqref) == "A2"      # 视图 (0,0) → 工作表 A2
    assert validations[0].formula1 == '"待办,进行中,完成"'


def test_data_validation_is_read_back(sheet_view, qtbot, tmp_path):
    target = tmp_path / "验证往返.xlsx"
    sheet_view._data_validations = {(0, 0): ["待办", "完成"]}
    sheet_view.set_current_file_path(target)
    sheet_view.save()

    from beeoffice.plugins.beesheet import BeeSheetView

    reader = BeeSheetView()
    qtbot.addWidget(reader)
    reader._set_status = lambda *a, **k: None
    try:
        reader._import_file_from_path(str(target))

        assert reader._data_validations.get((0, 0)) == ["待办", "完成"]
        assert reader.model._validations_ref, "模型没拿到验证引用"
    finally:
        reader.close()


def test_validation_drives_dropdown_editor(qtbot):
    """读回的验证要真的能让单元格变成下拉框（delegate 的行为）。"""
    from beeoffice.plugins.beesheet import BeeSheetView

    view = BeeSheetView()
    qtbot.addWidget(view)
    try:
        view.model.set_full_dataframe(pd.DataFrame({"状态": ["待办"]}))
        view._data_validations = {(0, 0): ["待办", "完成"]}
        view.model._validations_ref = view._data_validations

        editor = view.table_view.itemDelegate().createEditor(
            None, None, view.model.index(0, 0)
        )
        assert editor is not None
        assert "ComboBox" in type(editor).__name__, (
            f"有下拉验证却不是下拉框：{type(editor).__name__}"
        )
    finally:
        view.close()


def test_validation_options_with_comma_are_skipped_honestly(sheet_view,
                                                            tmp_path):
    """选项含逗号 → Excel 列表语法表达不了，**跳过并记录**，不写出坏验证。"""
    target = tmp_path / "逗号.xlsx"
    sheet_view._data_validations = {(0, 0): ["甲,乙", "丙"]}
    sheet_view.set_current_file_path(target)

    sheet_view.save()

    _, ws = _load(target)
    assert list(ws.data_validations.dataValidation) == [], "写出了语法错误的验证"


def test_non_list_validation_is_not_fabricated(tmp_path):
    """非列表型验证（整数区间等）不假装读回来。"""
    from openpyxl import Workbook
    from openpyxl.worksheet.datavalidation import DataValidation

    from beeoffice.plugins.beesheet_style_export import read_view_styles

    path = tmp_path / "区间验证.xlsx"
    workbook = Workbook()
    sheet = workbook.active
    sheet.append(["数量"])
    sheet.append([5])
    validation = DataValidation(type="whole", operator="between",
                               formula1="1", formula2="10")
    sheet.add_data_validation(validation)
    validation.add(sheet["A2"])
    workbook.save(path)

    styles = read_view_styles(path)

    assert not (styles.get("validations") or {}), "把区间验证当成了下拉列表"


# ==================== 5. 底线：这两项也不许动数据 ====================

def test_style_and_validation_writes_keep_data(qtbot, tmp_path):
    from beeoffice.plugins.beesheet import BeeSheetView

    target = tmp_path / "数据安全.xlsx"
    view = BeeSheetView()
    qtbot.addWidget(view)
    try:
        view._set_status = lambda *a, **k: None
        view.model.set_full_dataframe(
            pd.DataFrame({"名称": ["甲", "乙"], "金额": [10.5, 20.25]})
        )
        view._table_style = _style_dict()
        view._data_validations = {(0, 0): ["甲", "乙"]}
        view.set_current_file_path(target)
        assert view.save() is True

        _, ws = _load(target)
        assert ws["A2"].value == "甲"
        assert ws["B2"].value == 10.5
        assert ws["B3"].value == 20.25
    finally:
        view.close()
