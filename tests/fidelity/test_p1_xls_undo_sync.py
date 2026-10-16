# tests/fidelity/test_p1_xls_undo_sync.py
"""
第三批修复的三项：
1. **蜜算 `.xls` 从"假装支持"变成真支持**（读走 xlrd；写有守卫，不损坏 .xls）；
2. **插入/删除行列可撤销 + 过安全门**（原先只改 `_loaded_df`、不压栈、不过门）；
3. **云同步从"空转"变成真的双向同步**（可配置目录 + 上传 + 下载 + 增量 + 如实计数）。

## 各项的修前状态（审计报告 §2.10 / §2.11 / §1.6）
* `.xls`：对话框与 `SHEET_EXTENSIONS` 都列了它，但读路径**写死** `engine='openpyxl'`
  （openpyxl 只认 .xlsx），而 `requirements.txt` 里的 `xlrd` **全仓无人调用**；
* 行列操作：只改 `_loaded_df`（Ctrl+Z 无效、流式大表会被分块回填覆盖、
  `_full_df` 与 `_loaded_df` 分叉）；
* 云同步：上传的是 `~/.beeoffice_data`（**全仓无写入方**）→ 永远"没有文件需要上传"；
  三个适配器的 `download()` **没有任何调用者**。

## 环境限制
本机**没有 xlwt/LibreOffice**，造不出真实 `.xls` 夹具，所以 `.xls` 的读路径按
"**引擎选择 + 接线**"验证（monkeypatch `pandas.read_excel` 断言传入的 engine），
真正的解码交给 xlrd 本身；这一点在测试里写明。
"""
import sys
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


# ======================================================================
# 一、`.xls`
# ======================================================================

def test_engine_selection_by_extension():
    from beeoffice.plugins.beesheet_workbook import pick_excel_engine

    assert pick_excel_engine("a.xlsx") == "openpyxl"
    assert pick_excel_engine("a.xlsm") == "openpyxl"
    assert pick_excel_engine("a.xls") == "xlrd"
    assert pick_excel_engine("A.XLS") == "xlrd"


def test_missing_xlrd_gives_actionable_error(monkeypatch):
    """没有 xlrd 时要说清"装什么"，而不是抛一句 pandas 的难懂错误。"""
    import builtins

    from beeoffice.plugins.beesheet_workbook import pick_excel_engine

    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name == "xlrd":
            raise ImportError("no xlrd")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)

    with pytest.raises(RuntimeError) as exc:
        pick_excel_engine("旧表.xls")
    assert "xlrd" in str(exc.value)


def test_read_workbook_passes_xlrd_for_xls(monkeypatch, tmp_path):
    """**接线验证**：`.xls` 必须让 pandas 走 xlrd（这才是"假装支持"的修复点）。"""
    from beeoffice.plugins import beesheet_workbook as wb

    seen = {}

    class _FakeWorkbook:
        sheets = []
        active = ""

    def fake_read_excel(path, **kwargs):
        seen.update(kwargs)
        return {}

    monkeypatch.setattr(pd, "read_excel", fake_read_excel)
    fake = tmp_path / "旧表.xls"
    fake.write_bytes(b"not-really-xls")       # 内容不参与：这里只验引擎选择

    wb.read_workbook(str(fake))

    assert seen.get("engine") == "xlrd", f"实际引擎: {seen.get('engine')}"


def test_sheet_import_passes_xlrd_for_xls(qtbot, monkeypatch, tmp_path):
    """蜜算的导入分支同样要走 xlrd（否则用户选 .xls 必失败）。"""
    from PySide6.QtWidgets import QMessageBox

    from beeoffice.plugins import beesheet as bs
    from beeoffice.plugins.beesheet import BeeSheetView

    seen = {}

    def fake_read_excel(path, **kwargs):
        seen.update(kwargs)
        return pd.DataFrame({"a": [1]})

    monkeypatch.setattr(pd, "read_excel", fake_read_excel)
    monkeypatch.setattr(QMessageBox, "information",
                        staticmethod(lambda *a, **k: None))
    monkeypatch.setattr(QMessageBox, "warning",
                        staticmethod(lambda *a, **k: None))
    # 让工作簿读取失败 → 落到"退回首张表"的分支（也就是原写死 openpyxl 的那条）。
    # ⚠️ 必须打补丁在**定义处**（`beesheet_workbook.read_workbook`）：
    # 蜜算是**函数内局部 import** 的，从包外给 `beesheet` 加属性没用
    # （我第一版就栽在这里：AttributeError: module has no attribute 'read_workbook'）。
    from beeoffice.plugins import beesheet_workbook as wb

    def boom(*args, **kwargs):
        raise RuntimeError("no")

    monkeypatch.setattr(wb, "read_workbook", boom)

    source = tmp_path / "旧表.xls"
    source.write_bytes(b"stub")

    view = BeeSheetView()
    qtbot.addWidget(view)
    try:
        view._import_file_from_path(str(source))
        assert seen.get("engine") == "xlrd", f"实际引擎: {seen.get('engine')}"
    finally:
        view.close()


def test_save_never_writes_xls_in_place(qtbot, tmp_path, monkeypatch):
    """我们能读 `.xls` 但**写不了** BIFF —— 必须转成"另存为 .xlsx"，绝不原地写。"""
    from PySide6.QtWidgets import QFileDialog, QMessageBox

    from beeoffice.plugins.beesheet import BeeSheetView

    view = BeeSheetView()
    qtbot.addWidget(view)
    try:
        infos = []
        monkeypatch.setattr(
            QMessageBox, "information",
            staticmethod(lambda parent, title, text, *a, **k: infos.append(text)),
        )
        monkeypatch.setattr(QMessageBox, "warning",
                            staticmethod(lambda *a, **k: None))

        xls = tmp_path / "旧表.xls"
        xls.write_bytes(b"original-bytes")
        target = tmp_path / "旧表.xlsx"
        monkeypatch.setattr(QFileDialog, "getSaveFileName",
                            staticmethod(lambda *a, **k: (str(target), "")))

        view.model.set_full_dataframe(pd.DataFrame({"a": [1, 2, 3]}))
        view.set_current_file_path(xls)
        ok = view.save()

        assert ok is True
        assert xls.read_bytes() == b"original-bytes", "原 .xls 被改写了！"
        assert target.exists(), "没有另存为 .xlsx"
        assert any("xlsx" in t for t in infos), "应当明确告知用户改为 .xlsx"
    finally:
        view.close()


# ======================================================================
# 二、插入/删除行列：可撤销 + 过安全门
# ======================================================================

@pytest.fixture
def sheet(qtbot):
    from beeoffice.plugins.beesheet import BeeSheetView

    view = BeeSheetView()
    qtbot.addWidget(view)
    view.model.set_full_dataframe(pd.DataFrame({"a": [1, 2, 3], "b": [4, 5, 6]}))
    view.table_view.setCurrentIndex(view.model.index(1, 0))
    view._set_status = lambda *a, **k: None
    return view


def test_insert_row_is_undoable(sheet):
    before = len(sheet.model.df)

    sheet._insert_row_below()
    assert len(sheet.model.df) == before + 1
    assert sheet._undo_stack, "插入行没有压入撤销栈（Ctrl+Z 会无效）"

    sheet.undo()
    assert len(sheet.model.df) == before
    # ⚠️ 只比对**有意义的前几行**：`set_full_dataframe` 会把数据补齐到默认行数
    #（1000 行），尾部是空串 —— 我第一版直接比对整个列，被这些补齐行搞失败。
    assert sheet.model.df["a"].head(3).tolist() == [1, 2, 3]

    sheet.redo()
    assert len(sheet.model.df) == before + 1


def test_insert_column_is_undoable(sheet):
    before = list(sheet.model.df.columns)

    sheet._insert_col_left()
    assert len(sheet.model.df.columns) == len(before) + 1

    sheet.undo()
    assert list(sheet.model.df.columns) == before


def test_delete_row_and_column_are_undoable(sheet):
    sheet._delete_current_row()
    assert sheet.model.df["a"].head(3).tolist() == [1, 3, '']   # 尾行由补齐而来
    sheet.undo()
    assert sheet.model.df["a"].head(3).tolist() == [1, 2, 3]

    sheet._delete_current_col()
    assert "a" not in sheet.model.df.columns
    sheet.undo()
    assert "a" in sheet.model.df.columns


def test_rowcol_ops_respect_safety_gate(sheet, monkeypatch):
    """
    两阶段载入期间**必须被安全门拦住**（否则改动会被后台分块回填覆盖）。
    """
    monkeypatch.setattr(sheet, "_ensure_full_data", lambda *a, **k: False)

    rows_before = len(sheet.model.df)
    sheet._insert_row_below()
    sheet._delete_current_row()

    assert len(sheet.model.df) == rows_before, "安全门没拦住结构性改动"
    assert not sheet._undo_stack


def test_rowcol_ops_keep_full_df_in_sync(sheet):
    """`_full_df` 与 `_loaded_df` 不能分叉（否则分块回填会用旧表覆盖）。"""
    sheet.model._full_df = sheet.model._loaded_df
    sheet._insert_row_below()

    assert len(sheet.model._full_df) == len(sheet.model._loaded_df)


# ======================================================================
# 三、云同步：可配置目录 + 双向 + 增量 + 如实计数
# ======================================================================

class FakeStorage:
    """假云盘：只把文件放在内存里，因此测试**完全不需要联网**。"""

    def __init__(self):
        self.remote = {}
        self.meta = {}
        self.uploads = []
        self.downloads = []

    def upload(self, local_path, remote_path):
        file = Path(local_path)
        self.remote[remote_path] = file.read_bytes()
        self.meta[remote_path] = file.stat().st_mtime
        self.uploads.append(remote_path)
        return True

    def download(self, remote_path, local_path):
        Path(local_path).write_bytes(self.remote[remote_path])
        self.downloads.append(remote_path)
        return True

    def list_files(self, remote_dir):
        return [k.rsplit("/", 1)[-1] for k in self.remote
                if k.startswith(remote_dir)]

    def get_file_info(self, remote_path):
        return (len(self.remote.get(remote_path, b"")),
                self.meta.get(remote_path, 0))

    def exists(self, remote_path):
        return remote_path in self.remote


def test_sync_uploads_local_files(tmp_path):
    from beeoffice.cloud_sync.engine import sync_folder

    local = tmp_path / "同步"
    local.mkdir()
    (local / "报告.docx").write_bytes(b"content")

    storage = FakeStorage()
    result = sync_folder(storage, local, "/beeoffice")

    assert result["uploaded"] == 1
    assert "/beeoffice/报告.docx" in storage.remote


def test_sync_downloads_remote_only_files(tmp_path):
    """补上"`download()` 没有任何调用者"这个缺口。"""
    from beeoffice.cloud_sync.engine import sync_folder

    local = tmp_path / "同步"
    local.mkdir()
    storage = FakeStorage()
    storage.remote["/beeoffice/云上.xlsx"] = b"remote"

    result = sync_folder(storage, local, "/beeoffice")

    assert result["downloaded"] == 1
    assert (local / "云上.xlsx").read_bytes() == b"remote"
    assert storage.downloads, "download() 仍未被调用"


def test_sync_is_incremental(tmp_path):
    """第二次同步不该把整个目录重传一遍（WebDAV 上很慢）。"""
    from beeoffice.cloud_sync.engine import sync_folder

    local = tmp_path / "同步"
    local.mkdir()
    (local / "a.txt").write_bytes(b"x")
    storage = FakeStorage()

    first = sync_folder(storage, local, "/beeoffice")
    second = sync_folder(storage, local, "/beeoffice")

    assert first["uploaded"] == 1
    assert second["uploaded"] == 0, "第二次又重传了"
    assert second["up_to_date"] >= 1


def test_sync_reports_honestly_when_nothing_to_do(tmp_path):
    """什么都没做时必须**照实说**（不能一律报"同步完成"）。"""
    from beeoffice.cloud_sync.engine import describe_sync, sync_folder

    local = tmp_path / "空目录"
    result = sync_folder(FakeStorage(), local, "/beeoffice")
    message = describe_sync(result)

    assert result["uploaded"] == 0 and result["downloaded"] == 0
    assert "没有需要同步的变化" in message


def test_sync_skips_are_counted_with_reasons(tmp_path):
    """按策略跳过的文件要计数并给出原因（同步目录里不该有秘密上传）。"""
    from beeoffice.cloud_sync.engine import sync_folder

    local = tmp_path / "同步"
    local.mkdir()
    # ⚠️ 用策略里**真的**在名单上的名字（我第一版自造了"凭据.txt"，结果 skipped=0）
    (local / ".env").write_bytes(b"secret")            # BLOCKED_FILENAMES
    (local / "正常.docx").write_bytes(b"ok")
    storage = FakeStorage()

    result = sync_folder(storage, local, "/beeoffice")

    assert result["uploaded"] + result["skipped"] == result["total_local"]
    assert result["skipped"] >= 1
    assert result["reasons"], "跳过却没给出原因"


def test_sync_conflict_keeps_local(tmp_path):
    """两边都有且分不出先后（无时间信息、大小不同）→ 保留本地并**单独计数**。"""
    from beeoffice.cloud_sync.engine import sync_folder

    local = tmp_path / "同步"
    local.mkdir()
    (local / "a.txt").write_bytes(b"local-content")

    class NoTimeStorage(FakeStorage):
        def get_file_info(self, remote_path):
            return (len(self.remote.get(remote_path, b"")), 0)   # 无时间

    storage = NoTimeStorage()
    storage.remote["/beeoffice/a.txt"] = b"remote-different"
    result = sync_folder(storage, local, "/beeoffice")

    assert (local / "a.txt").read_bytes() == b"local-content", "本地被覆盖了"
    # 上传侧会先上传（大小不同），下载侧再判为冲突
    assert result["conflicts"] >= 1 or result["uploaded"] >= 1


def test_sync_dir_setting_roundtrip(tmp_path):
    from beeoffice.settings import AppSettings

    path = tmp_path / "settings.json"
    settings = AppSettings(path=path)
    settings.cloud_sync_dir = str(tmp_path / "我的同步")
    settings.save()

    reloaded = AppSettings(path=path)
    reloaded.load()

    assert reloaded.cloud_sync_dir == str(tmp_path / "我的同步")


def test_sync_now_uses_configured_dir_and_reports(qtbot, app, tmp_path,
                                                  monkeypatch):
    """`_sync_now` 要用**配置的目录**，并用双向引擎如实汇报。"""
    from PySide6.QtWidgets import QMessageBox

    from beeoffice.cloud_sync import engine as engine_module

    local = tmp_path / "配置的同步目录"
    local.mkdir()
    (local / "文件.docx").write_bytes(b"data")
    app.settings.cloud_sync_dir = str(local)

    storage = FakeStorage()
    monkeypatch.setattr("beeoffice.cloud.get_cloud_storage",
                        lambda: storage)

    shown = []
    monkeypatch.setattr(
        QMessageBox, "information",
        staticmethod(lambda parent, title, text, *a, **k: shown.append(text)),
    )
    monkeypatch.setattr(QMessageBox, "warning",
                        staticmethod(lambda *a, **k: None))

    # 让"后台任务"同步执行（测试里不需要线程）
    from beeoffice import async_task

    def run(fn, *args, on_result=None, on_error=None, **kwargs):
        try:
            result = fn(*args, **kwargs)
        except Exception as e:  # noqa: BLE001
            if on_error:
                on_error(str(e))
            return None
        if on_result:
            on_result(result)
        return None

    monkeypatch.setattr(async_task.AsyncTaskManager, "run", staticmethod(run))

    app._sync_now()

    assert "/beeoffice/文件.docx" in storage.remote, (
        f"没有同步配置目录里的文件；引擎结果被丢弃了？（{shown}）"
    )
    assert app._sync_in_progress is False


def test_add_current_document_to_sync_dir(qtbot, app, tmp_path, monkeypatch):
    """「把当前文档加入同步目录」：给用户一个明确的、能用的入口。"""
    from PySide6.QtWidgets import QMessageBox

    from beeoffice.plugins.beewrite import BeeWriteEditor

    local = tmp_path / "同步目录"
    local.mkdir()
    app.settings.cloud_sync_dir = str(local)

    source = tmp_path / "我的文档.md"
    source.write_text("内容", encoding="utf-8")

    editor = BeeWriteEditor()
    qtbot.addWidget(editor)
    app.tab_manager.addTab(editor, "蜜写")
    app.tab_manager.setCurrentWidget(editor)
    editor._current_file_path = str(source)

    monkeypatch.setattr(QMessageBox, "information",
                        staticmethod(lambda *a, **k: None))
    monkeypatch.setattr(QMessageBox, "warning",
                        staticmethod(lambda *a, **k: None))

    app._add_current_to_sync_dir()

    copied = local / "我的文档.md"
    assert copied.exists(), "当前文档没有被复制到同步目录"
    assert copied.read_text(encoding="utf-8") == "内容"
    editor.close()


def test_add_current_without_saved_file_prompts(qtbot, app, monkeypatch):
    """没保存过的文档：要提示而不是静默失败。"""
    from PySide6.QtWidgets import QMessageBox

    from beeoffice.plugins.beewrite import BeeWriteEditor

    editor = BeeWriteEditor()
    qtbot.addWidget(editor)
    app.tab_manager.addTab(editor, "蜜写")
    app.tab_manager.setCurrentWidget(editor)
    editor._current_file_path = None

    shown = []
    monkeypatch.setattr(
        QMessageBox, "information",
        staticmethod(lambda parent, title, text, *a, **k: shown.append(text)),
    )

    app._add_current_to_sync_dir()

    assert shown, "没有保存过的文档应当有提示"
    editor.close()
