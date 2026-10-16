# tests/test_p2_regression/test_p1_18_command_context.py
"""P1-18 回归：命令面板上下文识别"""


def test_beeshow_recognized(qtbot):
    from beeoffice.plugins.beeshow import BeeShowView
    from beeoffice.command_palette import CommandPalette

    class _FakeTabManager:
        def __init__(self, w):
            self._w = w

        def currentWidget(self):
            return self._w

    class _FakeParent:
        def __init__(self, w):
            self.tab_manager = _FakeTabManager(w)

    show = BeeShowView()
    qtbot.addWidget(show)
    parent = _FakeParent(show)
    palette = CommandPalette(parent)
    qtbot.addWidget(palette)
    palette._detect_context()
    assert "🎥 蜜演" in palette.context_label.text()


def test_beewrite_recognized(qtbot):
    from beeoffice.plugins.beewrite import BeeWriteEditor
    from beeoffice.command_palette import CommandPalette

    class _FakeTabManager:
        def __init__(self, w):
            self._w = w

        def currentWidget(self):
            return self._w

    class _FakeParent:
        def __init__(self, w):
            self.tab_manager = _FakeTabManager(w)

    editor = BeeWriteEditor()
    qtbot.addWidget(editor)
    parent = _FakeParent(editor)
    palette = CommandPalette(parent)
    qtbot.addWidget(palette)
    palette._detect_context()
    assert "📝 蜜写" in palette.context_label.text()
