# tests/test_p2_regression/test_p1_03_close_event.py
"""P1-3 回归：beewrite_editor fixture 触发 closeEvent"""


def test_close_event_fires(beewrite_editor, monkeypatch):
    fired = {"n": 0}
    original = beewrite_editor.closeEvent

    def spy(event):
        fired["n"] += 1
        return original(event)

    monkeypatch.setattr(beewrite_editor, "closeEvent", spy)
    beewrite_editor.close()
    assert fired["n"] >= 1


def test_timers_stopped_after_close(qtbot, temp_settings):
    from beeoffice.plugins.beewrite import BeeWriteEditor
    editor = BeeWriteEditor()
    qtbot.addWidget(editor)
    editor.markdown_editor.setPlainText("# 测试")
    timer = editor._update_timer
    editor.close()
    assert not timer.isActive()
    editor.deleteLater()
