# tests/regression/v5/test_v505_comment_bookmark_persistence.py
"""
优化规划 §2.6 回归：批注 / 书签保存后必须能读回（原先重开文档全丢）。

原缺陷（数据丢失）
------------------
`_write_md()` 会把批注写入 `<base>.comments.json`、书签写入
`<base>.bookmarks.json`，但**打开文档时从不读回**：
`CommentManager.load_from_file()` 与 `BookmarkManager.load_from_file()`
在整个代码库里没有任何调用点（全仓 grep 确认，只有定义与两处
`save_to_file`）。

后果：用户加完批注、书签，保存，关闭，重新打开 —— 批注和书签全部消失，
而数据其实还躺在磁盘上。用户会认为"保存没生效"或"软件把数据弄丢了"。
这是不可逆的信任损失，因此优先于其他 §2.6 项处理。

修复：新增 `ExportMixin.load_md_sidecars(path)`，并在
`BeeApp._open_text_file()` 加载内容后调用它。
"""

import pytest


@pytest.fixture
def editor(beewrite_editor):
    """默认处于 markdown 模式的真实 BeeWriteEditor。"""
    return beewrite_editor


def _add_comment(editor, text="这是一条批注"):
    return editor._comment_manager.add(text, 0, 5, excerpt="摘录")


# ==================== 批注往返 ====================

def test_comments_survive_save_and_reopen(editor, tmp_path):
    md_path = tmp_path / "doc.md"
    _add_comment(editor, "第一条")
    _add_comment(editor, "第二条")
    assert editor._comment_manager.count() == 2

    assert editor._write_md(str(md_path)) is True
    sidecar = tmp_path / "doc.comments.json"
    assert sidecar.exists(), "保存时应写出批注旁挂文件"

    # 模拟"关闭后重新打开"：管理器是全新的（内容来自磁盘）
    editor._comment_manager.clear()
    assert editor._comment_manager.count() == 0

    loaded = editor.load_md_sidecars(str(md_path))

    assert loaded["comments"] is True, "应报告成功载入批注"
    assert editor._comment_manager.count() == 2, "批注没有读回来（原缺陷）"
    texts = [c.get("text") for c in editor._comment_manager.get_all()]
    assert texts == ["第一条", "第二条"]


def test_comment_ids_do_not_collide_after_reload(editor, tmp_path):
    """读回后新增批注不应与已有 ID 冲突。"""
    md_path = tmp_path / "doc.md"
    _add_comment(editor, "旧批注")
    editor._write_md(str(md_path))

    editor._comment_manager.clear()
    editor.load_md_sidecars(str(md_path))

    existing_ids = {c["id"] for c in editor._comment_manager.get_all()}
    new_id = editor._comment_manager.add("新批注", 10, 12)["id"]
    assert new_id not in existing_ids, "新批注 ID 与读回的旧批注冲突"


# ==================== 书签往返 ====================

def test_bookmarks_survive_save_and_reopen(editor, tmp_path):
    md_path = tmp_path / "doc.md"
    editor._bookmark_manager.add("开头", 0, 1)
    editor._bookmark_manager.add("结论", 120, 30)
    assert editor._bookmark_manager.count() == 2

    assert editor._write_md(str(md_path)) is True
    assert (tmp_path / "doc.bookmarks.json").exists()

    editor._bookmark_manager.clear()
    assert editor._bookmark_manager.count() == 0

    loaded = editor.load_md_sidecars(str(md_path))

    assert loaded["bookmarks"] is True
    assert editor._bookmark_manager.count() == 2
    assert editor._bookmark_manager.has("开头")
    assert editor._bookmark_manager.get("结论")["pos"] == 120


def test_both_sidecars_load_together(editor, tmp_path):
    md_path = tmp_path / "both.md"
    _add_comment(editor, "c1")
    editor._bookmark_manager.add("b1", 3, 1)
    editor._write_md(str(md_path))

    editor._comment_manager.clear()
    editor._bookmark_manager.clear()

    loaded = editor.load_md_sidecars(str(md_path))
    assert loaded == {"comments": True, "bookmarks": True}
    assert editor._comment_manager.count() == 1
    assert editor._bookmark_manager.count() == 1


# ==================== 边界情况 ====================

def test_missing_sidecars_are_tolerated(editor, tmp_path):
    """没有旁挂文件（例如别人给的 .md）时应正常打开，不报错。"""
    md_path = tmp_path / "plain.md"
    md_path.write_text("# 标题\n", encoding="utf-8")

    loaded = editor.load_md_sidecars(str(md_path))

    assert loaded == {"comments": False, "bookmarks": False}
    assert editor._comment_manager.count() == 0


def test_no_sidecar_rewrite_when_empty(editor, tmp_path):
    """没有批注/书签时不应凭空产生旁挂文件。"""
    md_path = tmp_path / "empty.md"
    assert editor._write_md(str(md_path)) is True

    assert not (tmp_path / "empty.comments.json").exists()
    assert not (tmp_path / "empty.bookmarks.json").exists()


def test_empty_path_is_safe(editor):
    assert editor.load_md_sidecars("") == {
        "comments": False, "bookmarks": False
    }
    assert editor.load_md_sidecars(None) == {
        "comments": False, "bookmarks": False
    }


def test_corrupt_sidecar_does_not_break_opening(editor, tmp_path):
    """损坏的旁挂文件应被忽略，不应让"打开文档"失败。"""
    md_path = tmp_path / "bad.md"
    md_path.write_text("内容", encoding="utf-8")
    (tmp_path / "bad.comments.json").write_text(
        "{ 这不是合法 JSON", encoding="utf-8"
    )

    loaded = editor.load_md_sidecars(str(md_path))

    assert loaded["comments"] is False, "损坏文件应报告失败"
    assert editor._comment_manager.count() == 0


# ==================== 打开路径确实接线了 ====================

def test_open_text_file_loads_sidecars():
    """`BeeApp._open_text_file` 必须在 set_content 之后载入旁挂数据。"""
    import inspect

    from beeoffice.app import BeeApp

    src = inspect.getsource(BeeApp._open_text_file)
    assert "load_md_sidecars" in src, (
        "打开 .md 时没有调用 load_md_sidecars，批注书签仍会丢"
    )
    # 顺序：必须在内容加载之后
    assert src.index("set_content") < src.index("load_md_sidecars")
