# tests/test_p2_regression/test_p1_08_friendly_errors.py
"""P1-8 回归：错误信息不跨行误捕获"""
from beeoffice.plugins.friendly_errors import FriendlyError


def test_error_no_cross_line():
    msg = "#ERROR: division by zero\n    at line 42\n    stack trace..."
    title, detail = FriendlyError.translate(msg)
    assert title == "公式计算错误"
    assert "division by zero" in detail
    assert "stack trace" not in detail


def test_error_stops_at_next_hash():
    msg = "#ERROR: invalid syntax#some_junk_after"
    _, detail = FriendlyError.translate(msg)
    assert "invalid syntax" in detail
    assert "junk" not in detail
