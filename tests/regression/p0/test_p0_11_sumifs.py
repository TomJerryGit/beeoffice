# tests/test_p0_regression/test_p0_11_sumifs.py
"""
P0-11 回归：SUMIFS / AVERAGEIFS 条件范围行偏移。

背景：
  原 _sumifs / _avgifs 实现里对条件范围取值使用：
      cond_row = sr1 + (r - sr1)   # sr1 是求和范围起始行
  这一表达式恒等于 r，意味着条件列永远按"求和范围"的行索引取值，
  而不是按"条件范围"自己的行索引。当求和范围与条件范围起始行
  不一致时（例如 SUMIFS(B2:B5, A1:A4, ...)），条件匹配会错位。

  修复后改为：
      cond_row = cr[0][0] + (r - sr1)   # cr 是条件范围

  同时把 range(1, len(p), 2) 改为 range(1, len(p) - 1, 2)，
  防止 p[i+1] 越界。

v5.0.5 修复：
  本测试原以 FormulaEngine(provider) 实例化方式调用（旧 API），
  但 P0-11 修复在 beesheet_engine.py 中（classmethod 风格）。
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


# ==================== SUMIFS 回归 ====================

def test_sumifs_offset():
    """
    SUMIFS 条件列应按条件范围自己的起始行取值。

    数据：
        A 列（条件）: 1, 2, 3, 2
        B 列（求和）: 10, 20, 30, 40

    公式：=SUMIFS(B1:B4, A1:A4, "2")
    条件 A = 2 的行是第 2 行和第 4 行
    应求和 B2 + B4 = 20 + 40 = 60
    """
    model = _FakeModel([
        [1, 10],
        [2, 20],
        [3, 30],
        [2, 40],
    ])
    result = FormulaEngine.evaluate('=SUMIFS(B1:B4,A1:A4,"2")', model)
    assert result == 60, f"SUMIFS 偏移错误，期望 60，实际 {result}"


# ==================== AVERAGEIFS 回归 ====================

def test_avgifs_offset():
    """
    AVERAGEIFS 条件列应按条件范围自己的起始行取值。

    数据：
        A 列（条件）: 1, 2, 3, 2
        B 列（求平均）: 10, 20, 30, 40

    公式：=AVERAGEIFS(B1:B4, A1:A4, "2")
    条件 A = 2 的行是第 2 行和第 4 行
    应平均 (B2 + B4) / 2 = (20 + 40) / 2 = 30
    """
    model = _FakeModel([
        [1, 10],
        [2, 20],
        [3, 30],
        [2, 40],
    ])
    result = FormulaEngine.evaluate('=AVERAGEIFS(B1:B4,A1:A4,"2")', model)
    assert result == 30, f"AVERAGEIFS 偏移错误，期望 30，实际 {result}"