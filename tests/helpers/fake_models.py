# tests/helpers/fake_models.py
"""模拟 Qt Model / DataFrame 的小工具，供多个测试共享。"""


class FakeModel:
    """模拟 SheetDataModel：只实现 get_value(r, c)。"""

    def __init__(self, data):
        self._data = data

    def get_value(self, r, c):
        if 0 <= r < len(self._data) and 0 <= c < len(self._data[r]):
            return self._data[r][c]
        return None


class FakeMultiSheetModel(FakeModel):
    """模拟多 sheet 场景。"""

    def __init__(self, sheets: dict):
        super().__init__([[None]])
        self._sheets = sheets

    def get_sheet_data(self, name):
        return self._sheets.get(name)
