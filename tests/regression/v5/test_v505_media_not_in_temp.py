# tests/regression/v5/test_v505_media_not_in_temp.py
"""
优化规划 §2.6 回归：插入的图片 / 公式图片不得只留在 %TEMP%。

原缺陷（数据丢失）
------------------
插入图片走 `ImageEditorDialog._insert_to_document()`，它把处理后的图片写到

    %TEMP%/beeoffice_images/edited_<毫秒>.png

然后把那个**绝对临时路径**通过 `QTextImageFormat.setName()` 写进文档；
插入公式同理（`%TEMP%/beeoffice_formulas/`）。

后果：
  - `%TEMP%` 会被系统清理（存储感知 / 磁盘清理 / 重启）→ 文档里的图片
    之后永久失效，用户可能过几天才发现；
  - 临时路径只在本机有效 → 文档拷到别的电脑上图片全部打不开。

而 `import_from_docx` 导入图片时早已是"导出到 `<文档名>_media/` + 相对路径
引用"，两条路径行为不一致。

修复：新增 `LinkMixin._persist_media_to_document()`，插入前把图片复制到
文档旁边的 `<文档名>_media/`（文档未保存时落到应用数据目录），再用新路径插入。
"""
import tempfile
from pathlib import Path

import pytest

from beeoffice.plugins.beewrite import BeeWriteEditor


def _make_temp_image(name="edited_1.png") -> Path:
    """在系统临时目录里造一张图（模拟对话框的产物）。"""
    tmp_dir = Path(tempfile.gettempdir()) / "beeoffice_images"
    tmp_dir.mkdir(parents=True, exist_ok=True)
    path = tmp_dir / name
    path.write_bytes(b"\x89PNG\r\n\x1a\n" + b"fake-image-bytes")
    return path


def _is_under_temp(path) -> bool:
    temp_root = Path(tempfile.gettempdir()).resolve()
    try:
        Path(path).resolve().relative_to(temp_root)
        return True
    except ValueError:
        return False


# ==================== 已保存文档：落到 <文档名>_media/ ====================

def test_media_is_copied_beside_saved_document(beewrite_editor, tmp_path):
    editor = beewrite_editor
    src = _make_temp_image()
    editor._current_file_path = str(tmp_path / "我的文档.md")

    result = editor._persist_media_to_document(str(src))

    assert result != str(src), "不应继续引用临时路径"
    assert not _is_under_temp(result), f"结果仍在临时目录: {result}"

    result_path = Path(result)
    assert result_path.exists(), "应产出真实文件"
    assert result_path.read_bytes() == src.read_bytes(), "内容应逐字节一致"
    assert result_path.parent == tmp_path / "我的文档_media", (
        f"应放在文档旁边，实际: {result_path.parent}"
    )


def test_persist_does_not_delete_source(beewrite_editor, tmp_path):
    """用复制而非移动：对话框自身的结果文件不受影响。"""
    editor = beewrite_editor
    src = _make_temp_image("keep_me.png")
    editor._current_file_path = str(tmp_path / "doc.md")

    editor._persist_media_to_document(str(src))

    assert src.exists(), "源文件不应被移走/删除"


def test_same_name_different_content_does_not_overwrite(beewrite_editor, tmp_path):
    """同名但内容不同的图片不应互相覆盖。"""
    editor = beewrite_editor
    editor._current_file_path = str(tmp_path / "doc.md")

    first = _make_temp_image("same.png")
    first.write_bytes(b"AAAA")
    r1 = editor._persist_media_to_document(str(first))

    second = _make_temp_image("same.png")
    second.write_bytes(b"BBBBBBBB")
    r2 = editor._persist_media_to_document(str(second))

    assert r1 != r2, "内容不同应另起文件名，不能覆盖"
    assert Path(r1).read_bytes() == b"AAAA"
    assert Path(r2).read_bytes() == b"BBBBBBBB"


def test_identical_content_reuses_file(beewrite_editor, tmp_path):
    """完全相同的图片重复插入不必产生副本。"""
    editor = beewrite_editor
    editor._current_file_path = str(tmp_path / "doc.md")
    src = _make_temp_image("dup.png")
    src.write_bytes(b"SAME")

    r1 = editor._persist_media_to_document(str(src))
    r2 = editor._persist_media_to_document(str(src))
    assert r1 == r2


# ==================== 未保存文档：落到应用数据目录 ====================

def test_unsaved_document_uses_stable_app_dir(beewrite_editor, tmp_path, monkeypatch):
    """
    文档尚未保存时，应落到应用数据目录而不是 %TEMP%。

    这里把 `get_app_data_dir` 指到一个可写的临时目录：真实的
    `get_app_data_dir()` 位于用户主目录下，在受限沙箱/无家目录写入权限的
    环境里不可写，此时实现会**优雅回退**到原路径（已由
    `test_unwritable_target_falls_back_gracefully` 覆盖）。
    """
    import beeoffice.utils as utils

    app_dir = tmp_path / "appdata"
    monkeypatch.setattr(utils, "get_app_data_dir", lambda: app_dir)

    editor = beewrite_editor
    editor._current_file_path = None
    src = _make_temp_image("unsaved.png")

    result = editor._persist_media_to_document(str(src))

    assert result != str(src)
    assert not _is_under_temp(result), "未保存文档也不应留在 %TEMP%"
    assert Path(result).exists()
    assert app_dir in Path(result).parents, (
        f"应落在应用数据目录下，实际: {result}"
    )


def test_unwritable_target_falls_back_gracefully(
    beewrite_editor, tmp_path, monkeypatch
):
    """
    目标目录不可写时必须**优雅降级**（返回原路径）而不是抛异常——
    插入图片是用户操作，不能因为落盘失败就报错中断。
    """
    import beeoffice.utils as utils

    def _boom():
        raise OSError("模拟不可写")

    monkeypatch.setattr(utils, "get_app_data_dir", _boom)

    editor = beewrite_editor
    editor._current_file_path = None
    src = _make_temp_image("fallback.png")

    result = editor._persist_media_to_document(str(src))

    assert result == str(src), "无法落盘时应返回原路径而不是抛异常"
    assert src.exists()


# ==================== 边界情况 ====================

@pytest.mark.parametrize("bad", ["", None])
def test_empty_path_is_returned_unchanged(beewrite_editor, bad):
    assert beewrite_editor._persist_media_to_document(bad) == bad


def test_missing_source_is_returned_unchanged(beewrite_editor, tmp_path):
    missing = str(tmp_path / "not_there.png")
    assert beewrite_editor._persist_media_to_document(missing) == missing


# ==================== 两个插入入口都走了落盘 ====================

def test_both_insert_paths_use_persistence_helper():
    import inspect

    src = inspect.getsource(BeeWriteEditor._insert_image)
    assert "_persist_media_to_document" in src, (
        "插入图片没有落盘，仍会把 %TEMP% 路径写进文档"
    )

    src = inspect.getsource(BeeWriteEditor._insert_formula)
    assert "_persist_media_to_document" in src, (
        "插入公式没有落盘，仍会把 %TEMP% 路径写进文档"
    )
