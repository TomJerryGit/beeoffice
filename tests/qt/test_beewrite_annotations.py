# -*- coding: utf-8 -*-
"""
蜜写批注 / 书签读回（P0 数据丢失）

背景：
    `CommentManager` / `BookmarkManager` 一直有 `load_from_file`，
    但全仓没有任何调用点——保存后重开文档，批注和书签全部消失。

本文件锁定三件事：
    1. 侧车路径约定与 `_write_md` 保持一致
    2. `load_annotations` 能把批注/书签读回来
    3. 打开没有侧车的文档时必须清空，不能继承上一篇的批注
"""
from pathlib import Path  # noqa: F401  (供 tmp_path 类型提示阅读用)

import pytest

DOC_TEXT = "# 标题\n\n正文内容\n"


@pytest.fixture
def editor(qtbot):
    from beeoffice.plugins.beewrite import BeeWriteEditor

    ed = BeeWriteEditor()
    qtbot.addWidget(ed)
    yield ed
    try:
        ed.close()
    except Exception:
        pass


def _save_sidecars(editor, doc_path):
    """按 _write_md 的约定写侧车文件。"""
    cpath, bpath = editor._annotation_paths(str(doc_path))
    editor._comment_manager.save_to_file(str(cpath))
    editor._bookmark_manager.save_to_file(str(bpath))
    return cpath, bpath


def test_annotation_paths_match_save_convention(tmp_path):
    from beeoffice.plugins.beewrite import BeeWriteEditor

    cpath, bpath = BeeWriteEditor._annotation_paths(str(tmp_path / "doc.md"))
    assert cpath.name == "doc.comments.json"
    assert bpath.name == "doc.bookmarks.json"


def test_comments_and_bookmarks_survive_reopen(editor, tmp_path):
    doc = tmp_path / "doc.md"
    doc.write_text(DOC_TEXT, encoding="utf-8")

    editor._comment_manager.add("这条批注要活下来", 2, 5, "正文")
    editor._bookmark_manager.add("书签1", 8, 2)
    _save_sidecars(editor, doc)

    # 模拟"关掉重开"：清空内存后从侧车恢复
    editor._comment_manager.clear()
    editor._bookmark_manager.clear()

    result = editor.load_annotations(str(doc))

    assert result["comments"] is True
    assert result["bookmarks"] is True
    assert editor._comment_manager.count() == 1
    assert editor._comment_manager.get_all()[0]["text"] == "这条批注要活下来"
    assert editor._bookmark_manager.count() == 1
    assert editor._bookmark_manager.has("书签1")


def test_opening_doc_without_sidecar_clears_previous(editor, tmp_path):
    """打开无侧车的文档时不能残留上一篇的批注（跨文档串味）。"""
    doc_a = tmp_path / "a.md"
    doc_b = tmp_path / "b.md"
    doc_a.write_text(DOC_TEXT, encoding="utf-8")
    doc_b.write_text(DOC_TEXT, encoding="utf-8")

    editor._comment_manager.add("A 的批注", 0, 2, "")
    _save_sidecars(editor, doc_a)

    editor.load_annotations(str(doc_a))
    assert editor._comment_manager.count() == 1

    editor.load_annotations(str(doc_b))
    assert editor._comment_manager.count() == 0, (
        "打开 B 时继承了 A 的批注"
    )
    assert editor._bookmark_manager.count() == 0
