# tests/helpers/fake_widgets.py
"""轻量 fake 控件，模拟 BeeApp 的部分接口。"""


class FakeTabManager:
    def __init__(self, widget=None):
        self._widget = widget

    def currentWidget(self):
        return self._widget

    def count(self):
        return 1 if self._widget else 0

    def widget(self, i):
        return self._widget if i == 0 else None

    def tabText(self, i):
        return "fake-tab"


class FakeParent:
    """模拟 BeeApp：提供 tab_manager 与 set_global_status。"""

    def __init__(self, widget=None):
        self.tab_manager = FakeTabManager(widget)
        self._status_calls = []

    def set_global_status(self, msg, timeout=0):
        self._status_calls.append((msg, timeout))
