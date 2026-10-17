# tests/test_p0_regression/test_p0_07_shortcuts.py
"""P0-7 回归：shortcuts 文档与实际绑定一致"""
from beeoffice.shortcuts import SHORTCUTS, get_shortcut_help


def test_no_ctrl_w_mismatch():
    global_items = SHORTCUTS["全局"]
    ctrl_w = [d for k, d in global_items if k == "Ctrl+W"]
    assert ctrl_w
    assert "关闭" in ctrl_w[0]


def test_no_f5_mismatch():
    beeshow_items = SHORTCUTS["蜜演 BeeShow"]
    f5 = [d for k, d in beeshow_items if k == "F5"]
    assert f5
    assert "播放" in f5[0]


def test_help_contains_expected_sections():
    text = get_shortcut_help()
    for cat in SHORTCUTS.keys():
        assert cat in text
