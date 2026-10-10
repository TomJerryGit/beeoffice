# tests/test_p2_regression/test_v505_permission_error.py
"""
v5.0.5 回归：保存失败（PermissionError）的友好提示，且不污染 _current_file_path。

背景：
  原 _write_md / _write_docx 在 try 块内直接更新 _current_file_path，
  若 open() / doc.save() 抛 PermissionError（文件被 WPS/Word 占用），
  用户看到的是底层 errno 13 的堆栈错误，且内部状态已被污染为"失败的文件"。

修复：
  1. 增加 except PermissionError 分支，弹友好提示，引导用户关闭占用程序
  2. 只有文件真正写入成功才更新 _current_file_path

测试策略：
  - _write_md：monkeypatch builtins.open 抛 PermissionError
  - _write_docx：monkeypatch docx.document.Document.save 抛 PermissionError
    （注意：docx.Document 是工厂函数，真正的类在 docx.document.Document）
  - 断言弹窗被调用、_write_* 返回 False、_current_file_path 保持原值

v5.0.5 hotfix：
  1. 修正 docx 导入：
       from docx.document import Document as _DocxDocumentClass
     原实现 `from docx import Document` 拿到的是工厂函数而非类，
     没有 .save 属性，导致 AttributeError。
  2. 修正断言目标：
     _write_docx 走的是 QMessageBox.question，不是 QMessageBox.warning。
     原测试 patch 了 warning，实际从未被触发。
"""
import builtins
import pytest


# ==================== B3：PermissionError 友好提示 ====================

def test_write_md_permission_error_shows_warning(
    beewrite_editor, tmp_path, monkeypatch
):
    """v5.0.5：_write_md 遇 PermissionError 应弹友好提示并返回 False。"""
    from PySide6.QtWidgets import QMessageBox

    # 让 open() 对 .md 文件抛 PermissionError
    original_open = builtins.open

    def fake_open(path, *args, **kwargs):
        if str(path).endswith(".md"):
            raise PermissionError(13, "Permission denied")
        return original_open(path, *args, **kwargs)

    monkeypatch.setattr(builtins, "open", fake_open)

    warnings = []

    def fake_warning(parent, title, message, *args, **kwargs):
        warnings.append((title, message))

    monkeypatch.setattr(
        QMessageBox, "warning",
        staticmethod(fake_warning),
    )

    out = tmp_path / "test.md"
    result = beewrite_editor._write_md(str(out))

    assert result is False, "PermissionError 时 _write_md 应返回 False"
    assert warnings, "应弹出 QMessageBox.warning 提示用户"

    title, message = warnings[0]
    # 提示应明确告知用户是"文件被占用"
    assert "占用" in title or "占用" in message or \
           "无法写入" in message or "无法写入" in title, (
        f"提示应说明文件被占用。实际 title={title!r}, message={message[:100]!r}"
    )


def test_write_docx_permission_error_shows_warning(
    beewrite_editor, tmp_path, monkeypatch
):
    """
    v5.0.5：_write_docx 遇 PermissionError 也应友好提示。

    关键点：
      - 用 docx.document.Document（类），不是 docx.Document（工厂函数）
      - _write_docx 走的是 QMessageBox.question 分支
      - 返回 QMessageBox.Yes 避免递归到"另存为"分支
    """
    from PySide6.QtWidgets import QMessageBox

    # 切换到富文本模式，走 _rich_to_docx 路径
    beewrite_editor._switch_mode("rich_text")

    # ★ 关键修复：从 docx.document 导入真正的 Document 类
    try:
        from docx.document import Document as _DocxDocumentClass
    except ImportError:
        pytest.skip("python-docx 未安装")

    original_save = _DocxDocumentClass.save

    def fake_save(self, path, *args, **kwargs):
        if str(path).endswith(".docx"):
            raise PermissionError(13, "Permission denied")
        return original_save(self, path, *args, **kwargs)

    monkeypatch.setattr(_DocxDocumentClass, "save", fake_save)

    # ★ _write_docx 用的是 QMessageBox.question，不是 warning
    questions = []

    def fake_question(parent, title, message, *args, **kwargs):
        questions.append((title, message))
        # 返回 Yes → 不走"另存为"分支，直接 return False
        return QMessageBox.Yes

    monkeypatch.setattr(
        QMessageBox, "question", staticmethod(fake_question)
    )

    out = tmp_path / "test.docx"
    result = beewrite_editor._write_docx(str(out))

    assert result is False, "PermissionError 时 _write_docx 应返回 False"
    assert questions, (
        "_write_docx PermissionError 应弹 QMessageBox.question"
        "（不是 warning）。实际未弹窗"
    )

    title, message = questions[0]
    assert "占用" in title or "占用" in message, (
        f"提示应说明文件被占用。实际 title={title!r}, message={message[:100]!r}"
    )


# ==================== B4：保存失败不污染 _current_file_path ====================

def test_write_md_failure_does_not_pollute_path(
    beewrite_editor, tmp_path, monkeypatch
):
    """v5.0.5：保存失败时 _current_file_path 应保持原值。"""
    from PySide6.QtWidgets import QMessageBox

    # 设置一个已知的旧路径
    old_path = "/some/old_document.md"
    beewrite_editor._current_file_path = old_path

    # 让 open() 抛 PermissionError
    original_open = builtins.open

    def fake_open(path, *args, **kwargs):
        if str(path).endswith(".md"):
            raise PermissionError(13, "Permission denied")
        return original_open(path, *args, **kwargs)

    monkeypatch.setattr(builtins, "open", fake_open)

    # 静默弹窗
    monkeypatch.setattr(
        QMessageBox, "warning",
        staticmethod(lambda *a, **k: None),
    )

    out = tmp_path / "new_document.md"
    result = beewrite_editor._write_md(str(out))

    assert result is False
    assert beewrite_editor._current_file_path == old_path, (
        f"保存失败不应污染 _current_file_path。"
        f"期望 {old_path!r}，实际 {beewrite_editor._current_file_path!r}"
    )


def test_write_md_success_updates_path(
    beewrite_editor, tmp_path
):
    """v5.0.5：保存成功才更新 _current_file_path（对照测试）。"""
    beewrite_editor._current_file_path = "/old/path.md"

    out = tmp_path / "success.md"
    result = beewrite_editor._write_md(str(out))

    assert result is True
    assert beewrite_editor._current_file_path == str(out), (
        "保存成功应更新 _current_file_path"
    )