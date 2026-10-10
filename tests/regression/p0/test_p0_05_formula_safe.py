# tests/test_p0_regression/test_p0_05_formula_safe.py
"""
P0-5 回归：公式引擎不允许执行任意 Python。

背景：
  原 formula_engine.py 的 IF / AND / OR / NOT / IFS 函数内部使用裸
  eval() 求值条件表达式，导致公式可以执行任意 Python 代码：
      =IF(__import__('os').system('rm -rf /'), 1, 2)
  修复后改用 AST 白名单（_safe_eval），禁止 __import__、属性访问、
  下标访问、lambda、推导式、赋值等。

v5.0.5 修复：
  本测试原以 FormulaEngine(provider) 实例化方式调用（旧 API），
  但当前工程有两个公式引擎：
    - plugins/formula_engine.py    实例式（旧）
    - plugins/beesheet_engine.py   classmethod 式（新，已加固）
  P0-5 修复在 beesheet_engine.py 中，因此本测试必须针对它。

  本次改为：
    - 导入 beesheet_engine.FormulaEngine
    - 用 _FakeModel 提供 get_value(r, c) 接口
    - 通过 FormulaEngine.evaluate(expr, model) classmethod 调用
"""
import pytest
from beeoffice.plugins.beesheet_engine import FormulaEngine


class _FakeModel:
    """
    模拟 SheetDataModel 的最小接口。

    只需要提供 get_value(row, col) 方法，
    供 FormulaEngine 在解析单元格引用时回调。
    """

    def __init__(self, data):
        self._data = data

    def get_value(self, r, c):
        if 0 <= r < len(self._data) and 0 <= c < len(self._data[r]):
            return self._data[r][c]
        return None


# ==================== 安全测试 ====================

def test_if_rejects_import():
    """
    IF 条件中不允许执行 __import__。

    修复后 _safe_eval 遇到 __import__ 应抛 ValueError，
    evaluate() 捕获后返回 "#ERROR: ..." 字符串。
    """
    model = _FakeModel([[1]])
    result = FormulaEngine.evaluate(
        "=IF(__import__('os').system('echo hi'),1,2)", model
    )
    assert isinstance(result, str), f"应返回错误字符串，实际: {result!r}"
    assert result.startswith("#ERROR"), f"应拒绝危险公式，实际: {result!r}"


def test_if_normal_condition_works():
    """
    正常的 IF 条件应正确求值。

    数据 A1 = 5，条件 A1>0 为真，应返回 "正"。
    """
    model = _FakeModel([[5]])
    assert FormulaEngine.evaluate('=IF(A1>0,"正","负")', model) == "正"