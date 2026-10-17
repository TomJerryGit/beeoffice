# fix_p0_08_ast.py
"""
用 AST 重写 P0-8 测试断言，避免匹配 docstring 里的说明文字。

问题：
  test_play_show_has_no_dead_code 用简单字符串匹配：
      'hasattr(view, "current_index"' in source
  但 docstring 里也写了这个字符串（用来说明历史修复），导致误报。

修复：
  改用 ast.parse 遍历所有 Call 节点，只匹配真正的
  hasattr(view, "xxx") / getattr(view, "xxx") 调用。

用法:
    python fix_p0_08_ast.py
"""
from pathlib import Path

ROOT = Path(__file__).parent.resolve()
TARGET = ROOT / "tests" / "regression" / "p0" / "test_p0_08_beeshow_plugin.py"

NEW_CONTENT = '''# tests/regression/p0/test_p0_08_beeshow_plugin.py
"""
P0-8 回归：beeshow_plugin 删死代码，直接调用 _start_play

背景：
  原 play_show 在调用 _start_play 前，检查：
    hasattr(view, "current_index")
    hasattr(view, "show_slide")
  但 BeeShowView 实际属性/方法是 _current_slide 和 _show_slide，
  这两个 hasattr 恒为 False，是纯误导性代码。

  同类 bug 也出现在 edit_notes 的 fallback 里（v5.0.1 遗漏，
  由本测试回归发现），属性名改为 _current_slide / _speaker_notes。

修复：
  play_show 删除死代码，直接调 view._start_play()
  edit_notes fallback 使用正确的属性名

测试策略：
  1. AST 断言：不误伤 docstring，只检查真正的代码调用
  2. 行为断言：mock view._start_play，调用 plugin.play_show，验证被调用
  3. edit_notes fallback 使用正确的属性名
"""
import ast
import re
from pathlib import Path


def _get_source():
    """获取 beeshow_plugin.py 的源码文本。"""
    from beeoffice.plugins import beeshow_plugin
    return Path(beeshow_plugin.__file__).read_text(encoding="utf-8")


def test_play_show_has_no_dead_code():
    """
    P0-8：AST 层面检查，代码里不应有对 view 的
    hasattr / getattr("current_index") 或 hasattr / getattr("show_slide") 调用。

    注意：docstring 里出现这两个字符串是允许的（历史说明），
    本测试用 AST 只匹配真正的函数调用节点。
    """
    source = _get_source()
    tree = ast.parse(source)

    bad_calls = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if not (isinstance(func, ast.Name)
                and func.id in ("hasattr", "getattr")):
            continue
        if len(node.args) < 2:
            continue
        first, second = node.args[0], node.args[1]
        if (isinstance(first, ast.Name) and first.id == "view"
                and isinstance(second, ast.Constant)
                and second.value in ("current_index", "show_slide")):
            bad_calls.append(
                f"  {func.id}(view, {second.value!r})  "
                f"@ line {node.lineno}"
            )

    assert not bad_calls, (
        "P0-8：beeshow_plugin 里仍有死代码调用（AST 检查）：\\n"
        + "\\n".join(bad_calls)
    )


def test_edit_notes_uses_correct_attrs():
    """
    P0-8 遗漏点回归：edit_notes 的 fallback 分支应使用
    _current_slide / _speaker_notes，而非 current_index / speaker_notes。
    """
    source = _get_source()
    tree = ast.parse(source)

    # AST 里不应有 getattr(view, "current_index")
    for node in ast.walk(tree):
        if (isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name)
                and node.func.id == "getattr"
                and len(node.args) >= 2
                and isinstance(node.args[1], ast.Constant)
                and node.args[1].value == "current_index"):
            raise AssertionError(
                f"P0-8：edit_notes fallback 仍用 current_index "
                f"@ line {node.lineno}"
            )

    # 应该存在的正确模式（字符串匹配 OK，因为这是真实代码）
    assert 'getattr(view, "_current_slide", 0)' in source, (
        "P0-8：edit_notes fallback 应使用 _current_slide"
    )
    assert 'getattr(view, "_speaker_notes", None)' in source, (
        "P0-8：edit_notes fallback 应使用 _speaker_notes"
    )


def test_play_show_calls_start_play(qtbot, monkeypatch):
    """P0-8：plugin.play_show 应实际调用 view._start_play。"""
    from beeoffice.plugins.beeshow import BeeShowView
    from beeoffice.plugins.beeshow_plugin import BeeShowPlugin

    view = BeeShowView()
    qtbot.addWidget(view)

    called = []
    monkeypatch.setattr(
        view, "_start_play",
        lambda: called.append("_start_play"),
    )

    class _FakeTabManager:
        def currentWidget(self):
            return view

    class _FakeParent:
        def __init__(self):
            self.tab_manager = _FakeTabManager()

    plugin = BeeShowPlugin(parent=_FakeParent())
    plugin.play_show()

    assert called == ["_start_play"], (
        "P0-8：play_show 未调用 view._start_play。"
        "可能死代码被恢复了"
    )


def test_play_show_warns_when_no_view(monkeypatch):
    """P0-8：无活动蜜演视图时应提示。"""
    from beeoffice.plugins.beeshow_plugin import BeeShowPlugin

    warned = []
    monkeypatch.setattr(
        BeeShowPlugin, "_warn",
        lambda self, msg: warned.append(msg),
    )

    class _FakeTabManager:
        def currentWidget(self):
            return None

    class _FakeParent:
        def __init__(self):
            self.tab_manager = _FakeTabManager()

    plugin = BeeShowPlugin(parent=_FakeParent())
    plugin.play_show()

    assert warned, "无视图时应调用 _warn()"
    assert "蜜演" in warned[0]
'''


def main():
    print("=" * 60)
    print("  用 AST 重写 P0-8 测试")
    print("=" * 60)
    print()

    if not TARGET.exists():
        print(f"❌ 找不到: {TARGET}")
        return

    old = TARGET.read_text(encoding="utf-8")
    if "ast.walk(tree)" in old and "bad_calls" in old:
        print("⏭️  已是 AST 版本，跳过")
        return

    TARGET.write_text(NEW_CONTENT, encoding="utf-8")
    print(f"✅ 已重写: {TARGET.relative_to(ROOT)}")
    print()
    print("下一步:")
    print("  pytest tests\\regression\\p0\\test_p0_08_beeshow_plugin.py -v")
    print("  run_tests.bat")


if __name__ == "__main__":
    main()