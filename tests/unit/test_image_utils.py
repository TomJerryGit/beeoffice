# tests/unit/test_image_utils.py
"""
优化规划 §3.3 消重回归：图片工具模块（`plugins/image_utils.py`）。

背景
----
`resolve_image_path()` 是原先两份重复实现的合并（`beewrite_export_mixin`
与 `beewrite_rich_editor`），`iter_block_images()/iter_image_formats()` 合并了
多处 "遍历 block → fragment → isImageFormat()"。

本文件重点覆盖**消重过程中真实踩到的一个坑**：
`urlparse("D:\\a\\b.png")` 会把 `d` 当成 URL scheme，`path` 变成 `\\a\\b.png`
—— 盘符被丢掉，绝对路径被判成相对路径，最终**导出 DOCX 时图片消失**。
（实现已改为只在 `http(s)://` / `file:` 时才走 urlparse。）
"""
from pathlib import Path

import pytest

from beeoffice.plugins.image_utils import (
    iter_block_images,
    iter_image_formats,
    normalize_image_ref,
    resolve_image_path,
)


# ==================== normalize_image_ref ====================

def test_windows_drive_letter_is_preserved(tmp_path):
    """
    **本次消重引入过的回归**：Windows 盘符不能被当成 URL scheme 丢掉。
    """
    raw = str(tmp_path / "a.png")          # 形如 D:\...\a.png
    assert normalize_image_ref(raw) == raw


def test_windows_path_with_forward_slashes(tmp_path):
    raw = tmp_path.as_posix() + "/a.png"
    assert normalize_image_ref(raw) == raw


def test_file_url_is_converted_to_local_path():
    assert normalize_image_ref("file:///C:/dir/x.png") == "C:/dir/x.png"


def test_file_url_with_percent_escape():
    assert normalize_image_ref("file:///C:/dir/my%20image.png") == \
        "C:/dir/my image.png"


def test_percent_escape_in_plain_path():
    assert normalize_image_ref("my%20image.png") == "my image.png"


def test_http_reference_is_passed_through():
    """http(s) 不本地化（调用方据 scheme 决定怎么提示）。"""
    url = "https://example.com/a.png"
    assert normalize_image_ref(url) == url


def test_whitespace_is_stripped():
    assert normalize_image_ref("  a.png  ") == "a.png"


@pytest.mark.parametrize("value", ["", None])
def test_empty_input(value):
    assert normalize_image_ref(value) == ""


def test_path_object_input(tmp_path):
    p = tmp_path / "x.png"
    assert normalize_image_ref(p) == str(p)


# ==================== resolve_image_path ====================

def test_absolute_existing_path(tmp_path):
    img = tmp_path / "a.png"
    img.write_bytes(b"x")

    resolved, tried = resolve_image_path(str(img), [str(tmp_path)])

    assert resolved == img
    assert tried == [str(img)], "绝对路径只应尝试它自己"


def test_absolute_missing_path_fails_without_falling_back(tmp_path):
    """绝对路径不存在时不得去 base_dirs/home 里碰运气。"""
    missing = tmp_path / "nope.png"

    resolved, tried = resolve_image_path(
        str(missing), [str(tmp_path)], home_fallback=True
    )

    assert resolved is None
    assert tried == [str(missing)], tried


def test_relative_resolved_in_first_matching_dir(tmp_path):
    first = tmp_path / "first"
    second = tmp_path / "second"
    first.mkdir()
    second.mkdir()
    (second / "p.png").write_bytes(b"x")

    resolved, tried = resolve_image_path("p.png", [str(first), str(second)])

    assert resolved == second / "p.png"
    assert tried == [str(first / "p.png"), str(second / "p.png")]


def test_relative_prefers_earlier_candidate(tmp_path):
    """两个目录都有同名文件时，应取顺序靠前的那个。"""
    a = tmp_path / "a"
    b = tmp_path / "b"
    a.mkdir()
    b.mkdir()
    (a / "same.png").write_bytes(b"AAA")
    (b / "same.png").write_bytes(b"BBB")

    resolved, _ = resolve_image_path("same.png", [str(a), str(b)])

    assert resolved == a / "same.png"


def test_duplicate_candidates_are_tried_once(tmp_path):
    resolved, tried = resolve_image_path(
        "x.png", [str(tmp_path), str(tmp_path)], home_fallback=False
    )
    assert resolved is None
    assert len(tried) == 1, f"重复候选应去重: {tried}"


def test_home_fallback_can_be_disabled(tmp_path):
    _, tried = resolve_image_path("x.png", [], home_fallback=False)
    assert tried == []


def test_home_fallback_is_last(tmp_path):
    _, tried = resolve_image_path("x.png", [str(tmp_path)], home_fallback=True)
    assert tried[-1] == str(Path.home() / "x.png")


def test_none_entries_in_base_dirs_are_skipped(tmp_path):
    (tmp_path / "y.png").write_bytes(b"x")
    resolved, _ = resolve_image_path(
        "y.png", [None, "", str(tmp_path)], home_fallback=False
    )
    assert resolved == tmp_path / "y.png"


@pytest.mark.parametrize("value", ["", None])
def test_empty_name_returns_none(value):
    resolved, tried = resolve_image_path(value, ["/tmp"])
    assert resolved is None and tried == []


def test_file_url_is_resolved(tmp_path):
    img = tmp_path / "u.png"
    img.write_bytes(b"x")
    resolved, _ = resolve_image_path(img.as_uri(), [])
    assert resolved == img, "file:/// 形式的引用应能解析到本地文件"


# ==================== iter_block_images / iter_image_formats ====================

def _make_document_with_images(paths):
    """构造一个含内联图片的 QTextDocument。"""
    from PySide6.QtGui import (
        QTextCursor,
        QTextDocument,
        QTextImageFormat,
    )

    doc = QTextDocument()
    cursor = QTextCursor(doc)
    for p in paths:
        fmt = QTextImageFormat()
        fmt.setName(str(p))
        cursor.insertImage(fmt)
        cursor.insertBlock()
    cursor.insertText("只有文字，没有图片")
    return doc


def test_iter_block_images_yields_all_images(qapp):

    doc = _make_document_with_images(["a.png", "b.png"])

    found = []
    block = doc.begin()
    while block.isValid():
        for img in iter_block_images(block):
            found.append(img.name())
        block = block.next()

    assert found == ["a.png", "b.png"]
    assert all(isinstance(n, str) for n in found)


def test_iter_block_images_on_text_only_block(qapp):
    doc = _make_document_with_images([])
    block = doc.begin()
    assert list(iter_block_images(block)) == []


def test_iter_image_formats_yields_positions(qapp):
    doc = _make_document_with_images(["x.png", "y.png"])

    items = list(iter_image_formats(doc))

    assert [fmt.name() for fmt, _ in items] == ["x.png", "y.png"]
    positions = [pos for _, pos in items]
    assert positions == sorted(positions), "位置应递增"
    assert len(set(positions)) == 2, "两张图应在不同 block"


def test_iter_image_formats_on_document_without_images(qapp):
    doc = _make_document_with_images([])
    assert list(iter_image_formats(doc)) == []
