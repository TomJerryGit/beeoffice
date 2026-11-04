"""蜜写批量渲染回归：状态栏不应在逐块插入时重复做全文统计。"""
import beeoffice.plugins.beewrite_view_mixin as view_mixin


def test_bulk_render_updates_status_once(beewrite_editor, monkeypatch):
    calls = {"n": 0}
    original = view_mixin.count_words

    def counting(text):
        calls["n"] += 1
        return original(text)

    monkeypatch.setattr(view_mixin, "count_words", counting)
    editor = beewrite_editor
    calls["n"] = 0

    md = "\n\n".join(
        f"## 第 {i} 节\n\n正文 **加粗** 与 *斜体* 第 {i} 段。" for i in range(100)
    )
    editor.set_content(md)
    calls["n"] = 0  # 忽略 Markdown 编辑器 setPlainText 的一次正常统计
    editor._switch_mode("rich_text")

    # 渲染 100 段只允许一次状态栏统计（渲染完成后统一更新）
    assert calls["n"] == 1, f"count_words 调用了 {calls['n']} 次"
    assert "第 99 节" in editor.content()
