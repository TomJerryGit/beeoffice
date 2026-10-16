# tests/fidelity/test_beesheet_export_wiring.py
"""
保真度阶段 A 第一刀的**接线测试**：产品导出路径必须真的用上工作簿对象。

为什么单独测接线
----------------
`tests/fidelity/test_beesheet_workbook.py` 测的是模块本身；
但如果 `beesheet_data_mixin._export_xlsx()` 没接上它（仍是 `df.to_excel`），
模块写得再好也没用。本项目踩过同类坑：命令注册指向了不存在的方法、
HTML 导出入口被删掉却没接线 —— 都属于"单测绿、产品坏"。

这里用**轻量桩**驱动真实的 `_export_xlsx()`（不构造完整 BeeSheetView），
并 monkeypatch 掉文件对话框与消息框。
"""
import sys
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from beeoffice.plugins import beesheet_data_mixin as dm   # noqa: E402
from beeoffice.plugins.beesheet_workbook import read_workbook  # noqa: E402


def _make_xlsx(path: Path) -> Path:
    from openpyxl import Workbook

    wb = Workbook()
    ws = wb.active
    ws.title = "明细"
    for row in [
        ["产品", "数量", "金额"],
        ["甲", 10, "=B2*2"],
        ["乙", 20, "=B3*2"],
    ]:
        ws.append(row)
    second = wb.create_sheet("汇总")
    second.append(["项目", "值"])
    second.append(["合计", "=SUM(明细!C2:C3)"])
    wb.save(str(path))
    return path


class _StubModel:
    def __init__(self, df):
        self.df = df


class _View(dm.DataMixin):
    """最小宿主：只提供 `_export_xlsx` 需要的属性。"""

    def __init__(self, df, workbook=None, active=""):
        self.model = _StubModel(df)
        self._workbook = workbook
        self._active_sheet_name = active


@pytest.fixture
def patched(monkeypatch):
    """拦下文件对话框与消息框，并记录保存路径。"""
    saved = {}
    shown = []

    def fake_save(*args, **kwargs):
        return saved.get("path", ""), ""

    monkeypatch.setattr(dm.QFileDialog, "getSaveFileName",
                        staticmethod(fake_save))
    monkeypatch.setattr(
        dm.QMessageBox, "information",
        staticmethod(lambda *a, **k: shown.append(("info", a))),
    )
    monkeypatch.setattr(
        dm.QMessageBox, "warning",
        staticmethod(lambda *a, **k: shown.append(("warn", a))),
    )
    return saved, shown


def test_export_writes_all_sheets_and_formulas(tmp_path, patched):
    """核心：导入→导出后，工作表数与公式数都不变。"""
    src = _make_xlsx(tmp_path / "in.xlsx")
    workbook = read_workbook(src)
    df = workbook.get("明细").df.copy()

    out = tmp_path / "out.xlsx"
    saved, shown = patched
    saved["path"] = str(out)

    _View(df, workbook, active="明细")._export_xlsx()

    assert out.is_file(), f"没有产出文件；消息框: {shown}"
    assert not [s for s in shown if s[0] == "warn"], shown

    again = read_workbook(out)
    assert again.sheet_names == ["明细", "汇总"], again.sheet_names
    assert again.formula_count == 3, again.formula_count


def test_export_persists_user_edits(tmp_path, patched):
    """用户在表格里改过的内容必须写出去（不能被原始工作簿覆盖）。"""
    src = _make_xlsx(tmp_path / "in.xlsx")
    workbook = read_workbook(src)
    df = workbook.get("明细").df.copy()
    df.loc[0, "产品"] = "甲（改过）"

    out = tmp_path / "out.xlsx"
    saved, _ = patched
    saved["path"] = str(out)

    _View(df, workbook, active="明细")._export_xlsx()

    again = read_workbook(out)
    assert again.get("明细").df.loc[0, "产品"] == "甲（改过）"
    assert again.get("明细").formulas, "改内容不应丢公式"


def test_export_without_workbook_falls_back(tmp_path, patched):
    """没有工作簿对象时退回 `df.to_excel`（CSV 导入、新建表格等场景）。"""
    out = tmp_path / "out.xlsx"
    saved, shown = patched
    saved["path"] = str(out)

    _View(pd.DataFrame({"A": [1, 2]}), workbook=None)._export_xlsx()

    assert out.is_file(), shown
    assert list(pd.read_excel(out).columns) == ["A"]


def test_export_with_empty_workbook_falls_back(tmp_path, patched):
    """工作簿存在但没有工作表时，不应崩溃，也要能导出。"""
    from beeoffice.plugins.beesheet_workbook import WorkbookData

    out = tmp_path / "out.xlsx"
    saved, shown = patched
    saved["path"] = str(out)

    _View(pd.DataFrame({"A": [1]}), workbook=WorkbookData())._export_xlsx()

    assert out.is_file(), shown


def test_export_cancelled_writes_nothing(tmp_path, patched):
    """用户取消对话框时不应写文件。"""
    saved, _ = patched
    saved["path"] = ""          # 模拟取消

    out = tmp_path / "never.xlsx"
    _View(pd.DataFrame({"A": [1]}))._export_xlsx()

    assert not out.exists()


def test_import_path_reads_all_sheets_via_product_code(tmp_path):
    """
    导入侧接线：`beesheet._import_file_from_path` 用的是工作簿读取。

    用 AST 断言而不是文本搜索（本会话已多次被自己的注释骗到）。
    """
    import ast
    import inspect
    import textwrap

    from beeoffice.plugins.beesheet import BeeSheetView

    src = textwrap.dedent(
        inspect.getsource(BeeSheetView._import_file_from_path)
    )
    tree = ast.parse(src)

    imported = {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom)
        for alias in node.names
    }
    called = {
        node.func.id
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    }

    assert "read_workbook" in imported, (
        "导入路径没有用 beesheet_workbook.read_workbook"
    )
    assert "read_workbook" in called, "导入了却没调用"
    # 仍然要有回退（且只在异常分支里），避免读取失败时整个导入崩掉
    assert "read_excel" in {
        node.func.attr
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
    }, "应保留 pd.read_excel 作为回退"
