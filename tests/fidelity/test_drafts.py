# tests/fidelity/test_drafts.py
"""
P0-5：**未保存内容的草稿**（崩溃恢复的"读取端"）。

## 修的是什么
`app._autosave()` 原先只对**已有文件路径**的文档 `save()`，
于是**新建但没保存过**的文档（`_current_file_path is None`）在崩溃时
**整份丢失** —— 没有任何地方留着它。审计把这条记成"自动保存有写无读"。

## 设计（为什么不新增格式）
草稿 = 草稿目录里**带原生扩展名的真实文件**（`.md` / `.xlsx` / `.beshow`）
+ 一个 `.meta.json` 记录"这是什么"。
→ 恢复时直接走**既有的打开分流**（`_open_recent` 按扩展名派发），
不需要新的反序列化代码，也不会产生"只存在于草稿里的怪格式"。

本文件锁住：存取/列表/过期清理/丢弃/元信息损坏容错，
以及 **app 侧的两条接线**（没有文件路径时写草稿、启动时检查草稿）。
"""
import sys
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


@pytest.fixture
def draft_dir(tmp_path, monkeypatch):
    """把草稿目录指到临时目录（**不碰用户 home**）。"""
    from beeoffice import drafts

    target = tmp_path / "drafts"
    monkeypatch.setenv("BEEOFFICE_DRAFT_DIR", str(target))
    return drafts


# ==================== 1. 路径与类型 ====================

def test_drafts_dir_honours_env_override(draft_dir, tmp_path):
    assert draft_dir.drafts_dir() == tmp_path / "drafts"
    assert draft_dir.drafts_dir().is_dir(), "目录应被自动创建"


def test_extension_per_kind(draft_dir):
    assert draft_dir.extension_for("doc") == ".md"
    assert draft_dir.extension_for("sheet") == ".xlsx"
    assert draft_dir.extension_for("show") == ".beshow"


def test_unknown_kind_is_rejected(draft_dir):
    with pytest.raises(ValueError) as exc:
        draft_dir.new_draft_path("pptx")
    assert "未知草稿类型" in str(exc.value)


# ==================== 2. 存取与列表 ====================

def test_write_record_and_list(draft_dir):
    path = draft_dir.new_draft_path("doc")
    path.write_text("# 未保存的内容\n正文", encoding="utf-8")
    draft_dir.record(path, kind="doc", title="周报", source="")

    entries = draft_dir.list_drafts()
    assert len(entries) == 1
    entry = entries[0]
    assert entry.path == path
    assert entry.kind == "doc"
    assert entry.title == "周报"
    assert "文档" in draft_dir.describe(entry)
    assert "周报" in draft_dir.describe(entry)


def test_discard_removes_file_and_meta(draft_dir):
    path = draft_dir.new_draft_path("sheet")
    path.write_bytes(b"fake xlsx")
    draft_dir.record(path, kind="sheet", title="表")

    assert draft_dir.discard(path) is True
    assert not path.exists()
    assert not draft_dir.meta_path(path).exists()
    assert draft_dir.list_drafts() == []


# ==================== 审计补充：目录不可用时**不许抛异常** ====================

def test_drafts_dir_survives_when_path_is_blocked(monkeypatch, tmp_path):
    """
    **审计发现（高危）**：`drafts_dir()` 原先直接 `mkdir()` →
    当草稿路径被一个**同名文件**占住（或 home 只读）时抛
    `FileExistsError` / `PermissionError`，而启动时的草稿检查会因此报错 ——
    "恢复功能"反而变成"启动报错"。
    """
    from beeoffice import drafts

    blocker = tmp_path / "blocked"
    blocker.write_text("我是一个文件，不是目录", encoding="utf-8")
    monkeypatch.setenv("BEEOFFICE_DRAFT_DIR", str(blocker))

    assert drafts.drafts_dir() == blocker          # 不抛异常
    assert drafts.list_drafts() == []               # 读不到 = 空列表
    assert drafts.record(blocker / "draft-doc-x.md", kind="doc") is False
    assert drafts.cleanup_stale() == 0


def test_record_returns_false_when_unwritable(draft_dir, tmp_path):
    """写元信息失败要**返回 False**，不能抛（草稿写不进去也不该影响编辑）。"""
    ro = tmp_path / "ro"
    ro.mkdir()
    target = ro / "draft-doc-x.md"
    target.write_text("内容", encoding="utf-8")
    # 用一个位于不存在目录的 meta 路径 → 写失败
    missing = ro / "nope" / "draft-doc-y.md"
    assert draft_dir.record(missing, kind="doc") is False


def test_broken_meta_does_not_hide_the_draft(draft_dir):
    """元信息坏了也不能让草稿消失（否则用户的内容就"看不见"了）。"""
    path = draft_dir.new_draft_path("show")
    path.write_text("# 演示", encoding="utf-8")
    draft_dir.meta_path(path).write_text("{ 这不是 JSON", encoding="utf-8")

    entries = draft_dir.list_drafts()
    assert len(entries) == 1
    assert entries[0].kind == "show", "应能从文件名 draft-show-… 猜出类型"


# ==================== 3. 过期清理 ====================

def test_age_filter_and_cleanup(draft_dir):
    old = draft_dir.new_draft_path("doc")
    old.write_text("旧草稿", encoding="utf-8")
    draft_dir.record(old, kind="doc", created=time.time() - 10 * 86400)
    fresh = draft_dir.new_draft_path("doc")
    fresh.write_text("新草稿", encoding="utf-8")
    draft_dir.record(fresh, kind="doc", created=time.time())

    assert len(draft_dir.list_drafts()) == 2
    assert len(draft_dir.list_drafts(max_age_days=7)) == 1

    assert draft_dir.cleanup_stale(7) == 1
    remaining = draft_dir.list_drafts()
    assert [e.path for e in remaining] == [fresh]


# ==================== 4. app 侧接线（静态/类级，不实例化窗口）====================

def test_draft_kind_mapping():
    """按能力判断草稿类型（sheet/show/doc），恢复时才能选对扩展名。"""
    from beeoffice.app import BeeApp

    class SheetLike:
        def _write_xlsx(self, path):  # noqa: D401 - 鸭子类型
            return True

    class ShowLike:
        def _write_deck(self, path):
            return True

    class DocLike:
        def content(self):
            return "文本"

    assert BeeApp._draft_kind_for(None, SheetLike()) == "sheet"
    assert BeeApp._draft_kind_for(None, ShowLike()) == "show"
    assert BeeApp._draft_kind_for(None, DocLike()) == "doc"
    assert BeeApp._draft_kind_for(None, object()) == ""


def test_autosave_writes_draft_before_the_file_path_guard():
    """
    **核心接线**：没有文件路径时必须先写草稿再返回（原先是直接 return →
    新建文档崩溃即丢）。用源码位置断言，避免依赖重窗口实例化。
    """
    source = (ROOT / "beeoffice" / "app.py").read_text(encoding="utf-8")
    marker = "if not getattr(widget, \"_current_file_path\", None):"
    assert marker in source
    tail = source.split(marker, 1)[1][:300]
    assert "_write_draft_for(widget)" in tail, "没有文件路径时应该先写草稿"


def test_startup_schedule_includes_draft_check():
    """启动时要检查草稿（否则"有写无读"依旧）。"""
    source = (ROOT / "beeoffice" / "app.py").read_text(encoding="utf-8")
    assert "_check_recoverable_drafts" in source
    assert "self._check_recoverable_drafts)" in source, "应挂到启动定时器上"


def test_saved_document_clears_its_draft():
    """成功保存后要丢掉草稿（否则每次启动都提示"有未保存内容"）。"""
    source = (ROOT / "beeoffice" / "app.py").read_text(encoding="utf-8")
    assert "draft = getattr(widget, \"_draft_path\", None)" in source
    assert "_drafts.discard(draft)" in source
