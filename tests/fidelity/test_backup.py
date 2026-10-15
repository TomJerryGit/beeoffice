# tests/fidelity/test_backup.py
"""
R6：**本地备份与恢复**（核心 `beeoffice/backup.py` + 界面 `backup_center.py`）。

## 为什么做这个
WPS 有"备份中心"（可回到历史版本）。我们原先只有 5 分钟自动保存 ——
**看不到、回不去**，而且自动保存是**直接覆盖**：写坏了就真没了。
本地软件做这件事成本很低（不需要云）。

## 本文件守的几条关键性质
* 备份在**覆盖前**做（`_backup_before_save`），备的是"上一个好状态"；
* **原子写**：先 `.tmp` 再 `os.replace` —— 备份自身不能被中断留半份；
* **恢复本身也可回退**：恢复前自动留一份 `before_restore`；
* **轮转有上限**：每文件保留 `keep` 份 + 总容量上限，超了按**最旧优先**删；
* **目录不可写就快速失败**（返回 None、只警告一次），沿用 R7 的教训；
* 备份失败**绝不阻断保存**。
"""
import sys
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from beeoffice.backup import BackupStore, BackupVersion           # noqa: E402


@pytest.fixture
def store(tmp_path):
    return BackupStore(root=tmp_path / "backups", keep=3)


@pytest.fixture
def source(tmp_path):
    path = tmp_path / "文档.docx"
    path.write_text("第一版内容", encoding="utf-8")
    return path


# ==================== 1. 创建 ====================

def test_create_copies_content(store, source):
    created = store.create(source, reason="before_save")

    assert created is not None and created.is_file()
    assert created.read_text(encoding="utf-8") == "第一版内容"


def test_create_name_is_sortable_and_has_reason(store, source):
    created = store.create(source, reason="manual")

    name = created.name
    assert "__" in name and "manual" in name
    assert name.startswith("文档__")
    assert name.endswith(".docx")
    # 时间戳形如 20261015-151043（可字典序排序 = 新在前）
    stamp = name.split("__")[1]
    assert len(stamp) >= 15 and stamp[8] == "-", stamp


def test_create_returns_none_for_missing_source(store, tmp_path):
    assert store.create(tmp_path / "不存在.docx") is None


def test_create_returns_none_when_root_unwritable(tmp_path, source):
    """备份目录不可写 → 返回 None（**不抛异常**，备份失败不该中断保存）。"""
    blocker = tmp_path / "blocker"
    blocker.write_text("我是文件不是目录", encoding="utf-8")
    store = BackupStore(root=blocker)

    assert store.create(source) is None


def test_same_second_backups_do_not_overwrite(tmp_path, source):
    """同一秒内连点"立即备份"两次 → 两份（加序号），不能互相覆盖。"""
    store = BackupStore(root=tmp_path / "bk", keep=10)
    now = time.time()

    first = store.create(source, reason="manual", now=now)
    second = store.create(source, reason="manual", now=now)

    assert first != second
    assert len(store.list_versions(source)) == 2


def test_no_temp_files_left_behind(store, source):
    store.create(source)

    leftovers = [p for p in store.root.rglob("*.tmp")]
    assert not leftovers, f"留下了临时文件：{leftovers}"


# ==================== 2. 列出 ====================

def test_list_versions_newest_first(tmp_path, source):
    store = BackupStore(root=tmp_path / "bk")
    store.create(source, now=time.time() - 100)
    source.write_text("第二版", encoding="utf-8")
    store.create(source, now=time.time())

    versions = store.list_versions(source)

    assert len(versions) == 2
    assert versions[0].stamp > versions[1].stamp, "应新的在前"
    assert versions[0].path.read_text(encoding="utf-8") == "第二版"


def test_latest_returns_newest(store, source):
    store.create(source, now=time.time() - 50)
    source.write_text("更新", encoding="utf-8")
    store.create(source, now=time.time())

    assert store.latest(source).path.read_text(encoding="utf-8") == "更新"


def test_latest_is_none_without_backups(store, source):
    assert store.latest(source) is None
    assert store.list_versions(source) == []


def test_junk_files_are_ignored(tmp_path, source):
    """备份目录里混进乱七八糟的文件时不能被当版本列出（也不能崩）。"""
    store = BackupStore(root=tmp_path / "bk")
    store.create(source)
    folder = store.folder_for(source)
    (folder / "随便.txt").write_text("x", encoding="utf-8")
    (folder / "半截.docx.tmp").write_text("y", encoding="utf-8")

    versions = store.list_versions(source)

    assert len(versions) == 1, [v.path.name for v in versions]


def test_same_name_different_path_is_separate(tmp_path):
    """同名但在不同目录的文件不能共用备份（否则会互相覆盖历史）。"""
    store = BackupStore(root=tmp_path / "bk")
    a = tmp_path / "甲" / "报告.docx"
    b = tmp_path / "乙" / "报告.docx"
    a.parent.mkdir()
    b.parent.mkdir()
    a.write_text("甲的", encoding="utf-8")
    b.write_text("乙的", encoding="utf-8")

    store.create(a)
    store.create(b)

    assert len(store.list_versions(a)) == 1
    assert len(store.list_versions(b)) == 1
    assert store.folder_for(a) != store.folder_for(b)


# ==================== 3. 恢复 ====================

def test_restore_overwrites_target(store, source):
    store.create(source)                      # 备份"第一版内容"
    source.write_text("写坏了的内容", encoding="utf-8")
    version = store.latest(source)

    assert store.restore(version, source) is True
    assert source.read_text(encoding="utf-8") == "第一版内容"


def test_restore_leaves_a_way_back(store, source):
    """
    **恢复本身也要可回退**：恢复前自动留一份 `before_restore`，
    否则"恢复错了"就真的没救了。
    """
    store.create(source, reason="before_save")
    source.write_text("恢复前的内容", encoding="utf-8")
    version = store.latest(source)

    store.restore(version, source)

    reasons = [v.reason for v in store.list_versions(source)]
    assert "before_restore" in reasons, reasons
    restored_safety = next(
        v for v in store.list_versions(source) if v.reason == "before_restore"
    )
    assert restored_safety.path.read_text(encoding="utf-8") == "恢复前的内容"


def test_restore_without_target_goes_somewhere_visible(store, source,
                                                       monkeypatch, tmp_path):
    """
    只给版本、不给目标时**不能猜原目录**（可能覆盖别人），
    而要放到用户可见且**真可写**的位置（桌面 → 主目录 → 备份目录下的 restored）。

    这里把 `Path.home` 指到 tmp_path（沙箱里真实主目录不可写），
    于是应该落在 tmp_path 下。
    """
    monkeypatch.setattr(Path, "home", staticmethod(lambda: tmp_path / "home"))
    store.create(source)
    version = store.latest(source)

    assert store.restore(version) is True
    target = store._restore_target(version)
    assert target.is_file(), target
    assert target.read_text(encoding="utf-8") == "第一版内容"
    assert tmp_path in target.parents or target.parent == tmp_path / "home"


def test_restore_missing_backup_returns_false(store, source, tmp_path):
    ghost = BackupVersion(path=tmp_path / "没有.docx", source="x.docx",
                          stamp="20260101-000000", reason="manual", size=0)

    assert store.restore(ghost, source) is False


# ==================== 4. 轮转与容量 ====================

def test_prune_keeps_newest_n(tmp_path, source):
    store = BackupStore(root=tmp_path / "bk", keep=2)
    for i in range(5):
        source.write_text(f"第{i}版", encoding="utf-8")
        store.create(source, now=time.time() + i)

    versions = store.list_versions(source)

    assert len(versions) == 2, [v.stamp for v in versions]
    # 留下的必须是**最新的两份**
    assert versions[0].path.read_text(encoding="utf-8") == "第4版"
    assert versions[1].path.read_text(encoding="utf-8") == "第3版"


def test_total_cap_deletes_oldest_but_keeps_newest(tmp_path, source):
    """
    总容量上限：超了**按最旧优先**删；但**至少要留最新一份** ——
    把历史全删光等于把备份功能弄没了（我第一版就这个缺陷：
    cap 设得极小时会把所有备份都删掉，测试因此失败）。
    """
    store = BackupStore(root=tmp_path / "bk", keep=100, max_total_bytes=1)
    store.create(source, now=time.time() - 100)
    source.write_text("x" * 500, encoding="utf-8")
    store.create(source, now=time.time())

    versions = store.list_versions(source)

    assert len(versions) == 1, [v.path.name for v in versions]
    assert versions[0].path.read_text(encoding="utf-8") == "x" * 500, (
        "留下的应当是最新那份"
    )


def test_delete_all_for(store, source):
    store.create(source)
    store.create(source)

    assert store.delete_all_for(source) == 2
    assert store.list_versions(source) == []


# ==================== 5. 界面 ====================

def _dialog(qtbot, tmp_path, source, keep=3):
    from beeoffice.backup_center import BackupCenterDialog

    store = BackupStore(root=tmp_path / "bk", keep=keep)
    dialog = BackupCenterDialog(store=store, source=source)
    qtbot.addWidget(dialog)
    return dialog, store


def test_dialog_shows_empty_state(qtbot, tmp_path, source):
    dialog, _ = _dialog(qtbot, tmp_path, source)
    try:
        assert dialog.table.rowCount() == 0
        assert "还没有备份" in dialog.summary.text()
        assert not dialog.restore_btn.isEnabled(), "没有备份时不该能点恢复"
    finally:
        dialog.close()


def test_dialog_lists_versions_newest_first(qtbot, tmp_path, source):
    dialog, store = _dialog(qtbot, tmp_path, source)
    try:
        store.create(source, now=time.time() - 60, reason="before_save")
        source.write_text("新版", encoding="utf-8")
        store.create(source, reason="manual")
        dialog.refresh()

        assert dialog.table.rowCount() == 2
        dialog.table.selectRow(0)
        assert dialog.current_version().reason == "manual"
        assert "2 份备份" in dialog.summary.text()
    finally:
        dialog.close()


def test_dialog_restore_respects_confirmation(qtbot, tmp_path, source,
                                              monkeypatch):
    """**恢复是破坏性操作**：点"否"必须什么都不做。"""
    from PySide6.QtWidgets import QMessageBox

    dialog, store = _dialog(qtbot, tmp_path, source)
    try:
        store.create(source)
        source.write_text("现在的坏内容", encoding="utf-8")
        dialog.refresh()
        dialog.table.selectRow(0)
        monkeypatch.setattr(
            QMessageBox, "question", staticmethod(lambda *a, **k: QMessageBox.No)
        )

        dialog.restore_selected()

        assert source.read_text(encoding="utf-8") == "现在的坏内容"
        assert dialog.restored_path is None
    finally:
        dialog.close()


def test_dialog_restore_on_yes_restores_and_records_path(qtbot, tmp_path,
                                                         source, monkeypatch):
    from PySide6.QtWidgets import QMessageBox

    dialog, store = _dialog(qtbot, tmp_path, source)
    try:
        store.create(source)
        source.write_text("坏内容", encoding="utf-8")
        dialog.refresh()
        dialog.table.selectRow(0)
        monkeypatch.setattr(
            QMessageBox, "question",
            staticmethod(lambda *a, **k: QMessageBox.Yes),
        )
        monkeypatch.setattr(QMessageBox, "information",
                            staticmethod(lambda *a, **k: None))

        dialog.restore_selected()

        assert source.read_text(encoding="utf-8") == "第一版内容"
        assert dialog.restored_path == source
    finally:
        dialog.close()


def test_dialog_delete_removes_row(qtbot, tmp_path, source):
    dialog, store = _dialog(qtbot, tmp_path, source)
    try:
        store.create(source)
        dialog.refresh()
        dialog.table.selectRow(0)

        dialog.delete_selected()

        assert dialog.table.rowCount() == 0
        assert store.list_versions(source) == []
    finally:
        dialog.close()


def test_dialog_clean_old_prunes(qtbot, tmp_path, source, monkeypatch):
    from PySide6.QtWidgets import QMessageBox

    dialog, store = _dialog(qtbot, tmp_path, source, keep=1)
    try:
        for i in range(3):
            source.write_text(f"第{i}版", encoding="utf-8")
            store.create(source, now=time.time() + i)
        dialog.refresh()
        monkeypatch.setattr(QMessageBox, "information",
                            staticmethod(lambda *a, **k: None))

        dialog.clean_old()

        assert dialog.table.rowCount() == 1
    finally:
        dialog.close()


# ==================== 6. 保存挂点（app 层）====================

class _FakeWidget:
    def __init__(self, path):
        self._current_file_path = str(path)


class _FakeApp:
    """只借 `BeeApp` 的备份逻辑，避免起整套 UI。"""

    def __init__(self, store):
        self._backup_store_cache = store

    def _backup_store(self):
        return self._backup_store_cache

    def _backup_before_save(self, widget, reason="before_save"):
        from beeoffice.app import BeeApp

        return BeeApp._backup_before_save(self, widget, reason=reason)


def test_backup_before_save_creates_backup(tmp_path, source):
    from beeoffice.app import BeeApp

    store = BackupStore(root=tmp_path / "bk")
    app = _FakeApp(store)
    app._backup_before_save = BeeApp._backup_before_save.__get__(
        app, _FakeApp)

    created = app._backup_before_save(_FakeWidget(source))

    assert created is True
    assert len(store.list_versions(source)) == 1
    assert store.list_versions(source)[0].reason == "before_save"


def test_backup_before_save_ignores_unsaved_document(tmp_path):
    """还没落过盘的新文档：没有可备份的内容，返回 False 且不报错。"""
    from beeoffice.app import BeeApp

    store = BackupStore(root=tmp_path / "bk")
    app = _FakeApp(store)
    app._backup_before_save = BeeApp._backup_before_save.__get__(
        app, _FakeApp)

    assert app._backup_before_save(_FakeWidget(tmp_path / "新文件.docx")) is False
    assert store.list_all() == []


def test_backup_before_save_never_raises(tmp_path, monkeypatch):
    """备份是保险不是门禁：内部炸了也必须返回 False，**不能阻断保存**。"""
    from beeoffice.app import BeeApp

    class _Boom:
        def create(self, *a, **k):
            raise RuntimeError("炸了")

    app = _FakeApp(_Boom())
    app._backup_before_save = BeeApp._backup_before_save.__get__(app, _FakeApp)
    path = tmp_path / "x.docx"
    path.write_text("x", encoding="utf-8")

    assert app._backup_before_save(_FakeWidget(path)) is False
