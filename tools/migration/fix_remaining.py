# fix_remaining.py
"""
修复新测试暴露的 2 个遗漏问题：

1. P0-8 漏修点：beeshow_plugin.py 的 edit_notes fallback
   里 getattr(view, "current_index") / speaker_notes 属性名错误。
   （play_show 已在 v5.0.1 修了，edit_notes 忘了）

2. P1-11 漏修点：10 个 beewrite_*.py 的文件头注释里
   仍有 bewrite_（少一个 e），v5.0.1 只改了文件名。

3. P0-8 测试断言改成模式匹配，避免误伤 docstring 说明文字。

用法:
    python fix_remaining.py            # 执行
    python fix_remaining.py --dry-run  # 只看会做什么
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).parent.resolve()
PLUGINS = ROOT / "beeoffice" / "plugins"
DRY = "--dry-run" in sys.argv


# ============================================================
# 1. 修 beeshow_plugin.py 的 edit_notes
# ============================================================

OLD_EDIT_NOTES = '''                current_idx = getattr(view, "current_index", 0)
                current_notes = ""
                if hasattr(view, "speaker_notes"):
                    current_notes = view.speaker_notes.get(current_idx, "")'''

NEW_EDIT_NOTES = '''                current_idx = getattr(view, "_current_slide", 0)
                current_notes = ""
                notes = getattr(view, "_speaker_notes", None)
                if isinstance(notes, list) and 0 <= current_idx < len(notes):
                    current_notes = notes[current_idx]'''


def fix_beeshow_plugin():
    print("【1】修 beeshow_plugin.py 的 edit_notes fallback")
    target = PLUGINS / "beeshow_plugin.py"
    if not target.exists():
        print(f"  ❌ 找不到: {target}")
        return False

    text = target.read_text(encoding="utf-8")

    if NEW_EDIT_NOTES in text:
        print("  ⏭️  已修复过，跳过")
        return True

    if OLD_EDIT_NOTES not in text:
        print("  ⚠️  找不到目标片段（可能已被手动修改）")
        return False

    text = text.replace(OLD_EDIT_NOTES, NEW_EDIT_NOTES, 1)
    if not DRY:
        target.write_text(text, encoding="utf-8")
    print(f"  ✅ {target.relative_to(ROOT)}")
    return True


# ============================================================
# 2. 修 10 个 beewrite 文件的文件头拼写
# ============================================================

# 只匹配真正的拼写错误：bewrite_ 前面不是 e
BAD_PATTERN = re.compile(r"(?<!e)bewrite_")


def fix_beewrite_spelling():
    print()
    print("【2】修 beewrite_*.py 的文件头拼写（bewrite_ → beewrite_）")
    files = sorted(PLUGINS.glob("beewrite_*.py"))
    if not files:
        print("  ❌ 未找到 beewrite_*.py")
        return False

    fixed = 0
    for f in files:
        text = f.read_text(encoding="utf-8")
        new_text = BAD_PATTERN.sub("beewrite_", text)
        if new_text != text:
            if not DRY:
                f.write_text(new_text, encoding="utf-8")
            count = len(BAD_PATTERN.findall(text))
            print(f"  ✅ {f.name}  ({count} 处)")
            fixed += 1

    if fixed == 0:
        print("  ⏭️  所有文件都已正确，无需修改")
    else:
        print(f"  → 共修复 {fixed} 个文件")
    return True


# ============================================================
# 3. 重写 P0-8 测试断言
# ============================================================

NEW_P0_08_TEST = '''# tests/regression/p0/test_p0_08_beeshow_plugin.py
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
  1. 模式断言：源码里不应含对 current_index / show_slide 的
     getattr / hasattr 调用（不误伤 docstring 说明文字）
  2. 行为断言：mock view._start_play，调用 plugin.play_show，验证被调用
  3. edit_notes fallback 使用正确的属性名
"""
import re
from pathlib import Path


def _get_source():
    """获取 beeshow_plugin.py 的源码文本。"""
    from beeoffice.plugins import beeshow_plugin
    return Path(beeshow_plugin.__file__).read_text(encoding="utf-8")


def test_play_show_has_no_dead_code():
    """
    P0-8：源码里不应有对 current_index / show_slide 的
    getattr / hasattr 调用。

    注意：这里只检查具体的代码调用模式，不检查 docstring
    里的说明文字（docstring 允许提到这两个名字作为历史描述）。
    """
    source = _get_source()

    bad_patterns = [
        'getattr(view, "current_index"',
        "getattr(view, 'current_index'",
        'hasattr(view, "current_index"',
        "hasattr(view, 'current_index'",
        'getattr(view, "show_slide"',
        "getattr(view, 'show_slide'",
        'hasattr(view, "show_slide"',
        "hasattr(view, 'show_slide'",
    ]
    found = [p for p in bad_patterns if p in source]
    assert not found, (
        "P0-8：beeshow_plugin 里仍有死代码调用：\\n"
        + "\\n".join(f"  {p}" for p in found)
    )


def test_edit_notes_uses_correct_attrs():
    """
    P0-8 遗漏点回归：edit_notes 的 fallback 分支应使用
    _current_slide / _speaker_notes，而非 current_index / speaker_notes。
    """
    source = _get_source()

    # 不允许出现的错误模式
    assert 'getattr(view, "current_index"' not in source, (
        "P0-8：edit_notes fallback 仍用 current_index。"
        "应改为 getattr(view, '_current_slide', 0)"
    )
    assert 'view.speaker_notes.get(' not in source, (
        "P0-8：edit_notes fallback 仍用 speaker_notes dict。"
        "BeeShowView 用的是 _speaker_notes 列表"
    )

    # 应该存在的正确模式
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


def rewrite_p0_08_test():
    print()
    print("【3】重写 P0-8 测试断言（避免误伤 docstring）")
    target = ROOT / "tests" / "regression" / "p0" / "test_p0_08_beeshow_plugin.py"
    if not target.exists():
        print(f"  ⚠️  找不到: {target}，跳过")
        return False

    old_text = target.read_text(encoding="utf-8")

    # 检查是否已经是新模式
    if "test_edit_notes_uses_correct_attrs" in old_text:
        print("  ⏭️  已重写过，跳过")
        return True

    if not DRY:
        target.write_text(NEW_P0_08_TEST, encoding="utf-8")
    print(f"  ✅ {target.relative_to(ROOT)}")
    return True


# ============================================================
# main
# ============================================================

def main():
    print("=" * 60)
    print(f"  修复遗漏问题  {'[DRY-RUN]' if DRY else ''}")
    print("=" * 60)
    print()

    results = [
        fix_beeshow_plugin(),
        fix_beewrite_spelling(),
        rewrite_p0_08_test(),
    ]

    print()
    print("=" * 60)
    if DRY:
        print("  DRY-RUN 完成，未做任何改动")
    else:
        ok = sum(1 for r in results if r)
        print(f"  ✅ 完成 {ok}/{len(results)} 项修复")
        print()
        print("  下一步:")
        print("    1. pytest tests/regression/p0/test_p0_08_beeshow_plugin.py -v")
        print("    2. pytest tests/regression/p1/test_p1_11_spelling.py -v")
        print("    3. run_tests.bat")
    print("=" * 60)


if __name__ == "__main__":
    main()