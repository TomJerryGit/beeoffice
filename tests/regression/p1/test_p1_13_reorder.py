# tests/test_p2_regression/test_p1_13_reorder.py
"""P1-13 回归：重排序不丢失标题"""


def test_reorder_preserves_title(qtbot):
    from beeoffice.plugins.beeshow import BeeShowView
    view = BeeShowView()
    qtbot.addWidget(view)
    view._editor.setPlainText(
        "# 第一页\n\n内容 1\n\n---\n\n# 第二页\n\n内容 2"
    )
    view._update_preview()
    assert len(view._slides_md) == 2
    assert "# 第一页" in view._slides_md[0]
    view._on_slides_reordered(None, 0, 0, None, 1)
    new_text = view._editor.toPlainText()
    assert "# 第一页" in new_text
    assert "# 第二页" in new_text
