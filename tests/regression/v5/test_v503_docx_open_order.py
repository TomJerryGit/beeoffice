# tests/test_p2_regression/test_v503_docx_open_order.py
"""
v5.0.3 回归：打开含图片的 DOCX 时，set_current_file_path 必须先于
           set_content / _switch_mode 调用。

背景：
  原 app._open_docx_file.on_result 的顺序是：
      set_content → _switch_mode → set_current_file_path
  _switch_mode("rich_text") 内部会调 RichTextEditor.set_markdown()，
  解析 ![](相对路径) 时需要 rich_editor._current_file_dir 已是
  文档所在目录。若尚未同步，图片被替换为 "[图片缺失: path]" 占位文字，
  保存后图片彻底丢失。

修复后顺序：
      set_current_file_path → set_content → _switch_mode

测试策略：
  与其断言"调用顺序"（脆弱），不如断言**结果**：
  - 造一个真实的图片文件放在 docx 同目录的 test_media/ 下
  - mock import_from_docx 返回带相对路径图片的 markdown
  - 触发 _open_docx_file
  - 检查 rich_editor 里是否有图片 fragment（而不是 "[图片缺失]"）

  如果顺序错了，图片找不到 → 会插入 "[图片缺失: ...]" → 测试失败。

v5.0.5：
  AsyncTaskManager.run 在测试中替换为同步实现，避免线程竞态。
"""

from PySide6.QtGui import QImage, QColor


def test_open_docx_loads_image_with_relative_path(
    app, qtbot, tmp_path, monkeypatch
):
    """v5.0.3：打开含图片 DOCX，图片应被正确加载而非变成占位文字。"""
    # ---------- 1. 造一张真实图片 ----------
    media_dir = tmp_path / "test_media"
    media_dir.mkdir(parents=True, exist_ok=True)
    img_path = media_dir / "image_001.png"
    img = QImage(100, 50, QImage.Format_RGB32)
    img.fill(QColor("blue"))
    assert img.save(str(img_path)), "测试图片写入失败"

    # ---------- 2. 造一个假 docx 文件 ----------
    docx_path = tmp_path / "test.docx"
    docx_path.write_bytes(b"fake docx content")

    # ---------- 3. mock import_from_docx ----------
    # 返回带"相对路径"图片的 markdown，模拟 import_from_docx 的产出
    fake_md = (
        "# 测试标题\n\n"
        "![](test_media/image_001.png)\n\n"
        "正文段落。"
    )
    monkeypatch.setattr(
        "beeoffice.plugins.bee_export.import_from_docx",
        lambda p: fake_md,
    )

    # ---------- 4. 让 AsyncTaskManager.run 同步执行 ----------
    class _SyncAsyncTaskManager:
        @staticmethod
        def run(fn, *args, on_result=None, on_error=None, **kwargs):
            try:
                result = fn(*args, **kwargs)
            except Exception as e:
                if on_error:
                    on_error(str(e))
                return None
            if on_result:
                on_result(result)
            return None

    monkeypatch.setattr(
        "beeoffice.app.AsyncTaskManager", _SyncAsyncTaskManager
    )

    # ---------- 5. 触发 _open_docx_file ----------
    app._open_docx_file(str(docx_path))

    # ---------- 6. 断言 ----------
    widget = app.tab_manager.currentWidget()
    from beeoffice.plugins.beewrite import BeeWriteEditor
    assert isinstance(widget, BeeWriteEditor)

    # 检查 rich_editor 文档内是否有图片 fragment
    doc = widget.rich_editor.document()
    has_image = False
    has_missing_placeholder = False
    block = doc.begin()
    while block.isValid():
        it = block.begin()
        while not it.atEnd():
            fragment = it.fragment()
            if fragment.isValid():
                if fragment.charFormat().isImageFormat():
                    has_image = True
            it += 1
        if "[图片缺失" in block.text():
            has_missing_placeholder = True
        block = block.next()

    assert has_image, (
        "图片未被加载。检查 on_result 中 set_current_file_path 是否在 "
        "set_content / _switch_mode 之前调用（v5.0.3 修复点）"
    )
    assert not has_missing_placeholder, (
        "出现 '[图片缺失]' 占位文字，说明图片相对路径解析失败，"
        "v5.0.3 的调用顺序修复被回退了"
    )


def test_open_docx_sets_current_file_path(app, tmp_path, monkeypatch):
    """v5.0.3：打开 DOCX 后，widget._current_file_path 应指向该文件。"""
    docx_path = tmp_path / "test.docx"
    docx_path.write_bytes(b"fake")

    monkeypatch.setattr(
        "beeoffice.plugins.bee_export.import_from_docx",
        lambda p: "# 标题\n",
    )

    class _SyncAsyncTaskManager:
        @staticmethod
        def run(fn, *args, on_result=None, on_error=None, **kwargs):
            try:
                result = fn(*args, **kwargs)
            except Exception as e:
                if on_error:
                    on_error(str(e))
                return None
            if on_result:
                on_result(result)
            return None

    monkeypatch.setattr(
        "beeoffice.app.AsyncTaskManager", _SyncAsyncTaskManager
    )

    app._open_docx_file(str(docx_path))

    widget = app.tab_manager.currentWidget()
    # _current_file_path 和 rich_editor._current_file_dir 都应同步
    assert widget._current_file_path == str(docx_path)
    assert widget.rich_editor._current_file_dir == str(tmp_path)