# tests/regression/v5/test_v505_cloud_sync_policy.py
"""
优化规划 §4.5 回归：云同步的上传策略与"如实计数"。

背景（分析报告 §4.6 实测）
--------------------------
`app._sync_now()` 的 `sync_files()` 原先只有一个无过滤的循环：

    for file in local_dir.rglob("*"):
        storage.upload(str(file), remote_path)

两个后果：
  1. **没有过滤** —— `~/.beeoffice_data` 里的任何内容都会**明文**上传到用户的
     WebDAV / OneDrive / Google Drive，包括各类凭据文件；
  2. **没有计量** —— 无论上传 0 个还是 100 个、无论失败多少，UI 一律显示
     "同步完成"。

现在：过滤 + 计数都抽到 `cloud_sync/policy.py`（不依赖 Qt），
因此本文件用**临时目录 + 假 storage** 即可测，不用构造 GUI。
"""
import json
from pathlib import Path

import pytest

from beeoffice.cloud_sync.policy import (
    describe_result,
    is_sensitive_settings,
    should_upload,
    upload_tree,
)


class _FakeStorage:
    """记录上传调用；可指定哪些路径上传失败。"""

    def __init__(self, fail_on=()):
        self.uploaded = []
        self.fail_on = set(fail_on)

    def upload(self, local_path, remote_path):
        if Path(local_path).name in self.fail_on:
            return False
        self.uploaded.append((local_path, remote_path))
        return True


# ==================== should_upload：密钥/凭据必须拒收 ====================

@pytest.mark.parametrize("name", [
    "server.key", "cert.pem", "client.p12", "store.pfx",
    "id_rsa", "id_ed25519", "credentials", ".env", ".netrc",
])
def test_sensitive_files_are_blocked(tmp_path, name):
    f = tmp_path / name
    f.write_text("secret-content")

    ok, reason = should_upload(f)

    assert ok is False, f"{name} 竟然允许上传"
    assert reason, "应给出跳过原因"


def test_temporary_files_skipped(tmp_path):
    for name in ("a.tmp", "b.part", "c.crdownload", "~$doc.docx"):
        f = tmp_path / name
        f.write_text("x")
        ok, _ = should_upload(f)
        assert ok is False, f"{name} 应跳过"


def test_empty_file_skipped(tmp_path):
    f = tmp_path / "empty.txt"
    f.touch()
    ok, reason = should_upload(f)
    assert ok is False and "空文件" in reason


def test_oversized_file_skipped(tmp_path, monkeypatch):
    f = tmp_path / "big.bin"
    f.write_bytes(b"xx")          # 2 字节
    # 上限设为 1 字节 → 2 > 1 应被拒（注意不能把上限设成与文件同大小，
    # 那样 size > MAX 不成立，文件会被放行 —— 我第一版就是这么写错的）
    monkeypatch.setattr(
        "beeoffice.cloud_sync.policy.MAX_UPLOAD_BYTES", 1
    )
    ok, reason = should_upload(f)
    assert ok is False and "上限" in reason


def test_normal_document_is_allowed(tmp_path):
    f = tmp_path / "report.md"
    f.write_text("# 正常文档")
    ok, reason = should_upload(f)
    assert ok is True and reason == ""


def test_sensitive_settings_json_is_blocked(tmp_path):
    f = tmp_path / "settings.json"
    f.write_text(json.dumps({"ai_api_key": "sk-123", "theme": "dark"}))
    ok, reason = should_upload(f)
    assert ok is False, "含 ai_api_key 的配置不应上传"
    assert "凭据" in reason


def test_plain_settings_json_is_allowed(tmp_path):
    f = tmp_path / "settings.json"
    f.write_text(json.dumps({"theme": "dark", "font_size": 14}))
    ok, _ = should_upload(f)
    assert ok is True


def test_empty_credential_value_is_not_sensitive(tmp_path):
    """键存在但值为空 → 不算敏感（避免把正常配置一刀切拒掉）。"""
    assert is_sensitive_settings.__name__ == "is_sensitive_settings"
    f = tmp_path / "s.json"
    f.write_text(json.dumps({"ai_api_key": ""}))
    assert is_sensitive_settings(f) is False


def test_nested_sensitive_key_detected(tmp_path):
    f = tmp_path / "s.json"
    f.write_text(json.dumps({"cloud_config": {"password": "p@ss"}}))
    assert is_sensitive_settings(f) is True


def test_broken_json_is_not_treated_as_sensitive(tmp_path):
    """无法解析的 JSON 按普通文件处理（不因为解析失败就一律拒传）。"""
    f = tmp_path / "broken.json"
    f.write_text("{ 不是合法 json")
    assert is_sensitive_settings(f) is False


# ==================== upload_tree：过滤 + 计数 ====================

def _make_tree(root: Path) -> None:
    (root / "docs").mkdir(parents=True, exist_ok=True)
    (root / "docs" / "a.md").write_text("A")
    (root / "docs" / "b.txt").write_text("B")
    (root / "server.key").write_text("PRIVATE")
    (root / "settings.json").write_text(json.dumps({"ai_api_key": "sk-x"}))
    (root / "empty.md").touch()


def test_upload_tree_counts_and_filters(tmp_path):
    tree = tmp_path / "data"
    _make_tree(tree)
    storage = _FakeStorage()

    result = upload_tree(storage, tree, "/beeoffice")

    assert result["total"] == 5
    assert result["uploaded"] == 2, f"应只上传 a.md 与 b.txt，实际 {storage.uploaded}"
    assert result["skipped"] == 3
    assert result["failed"] == 0

    names = sorted(Path(p).name for p, _ in storage.uploaded)
    assert names == ["a.md", "b.txt"]


def test_upload_tree_never_uploads_key_files(tmp_path):
    """安全底线：密钥文件一次都不能出现在上传列表里。"""
    tree = tmp_path / "data"
    _make_tree(tree)
    storage = _FakeStorage()

    upload_tree(storage, tree, "/beeoffice")

    for local_path, _ in storage.uploaded:
        assert not local_path.endswith(".key"), "密钥文件被上传了！"
        assert Path(local_path).name != "settings.json", "凭据配置被上传了！"


def test_upload_tree_remote_paths_preserve_structure(tmp_path):
    tree = tmp_path / "data"
    _make_tree(tree)
    storage = _FakeStorage()

    upload_tree(storage, tree, "/beeoffice")

    remotes = sorted(r for _, r in storage.uploaded)
    assert remotes == ["/beeoffice/docs/a.md", "/beeoffice/docs/b.txt"]


def test_upload_tree_counts_failures(tmp_path):
    tree = tmp_path / "data"
    _make_tree(tree)
    storage = _FakeStorage(fail_on={"b.txt"})

    result = upload_tree(storage, tree, "/beeoffice")

    assert result["uploaded"] == 1
    assert result["failed"] == 1


def test_upload_tree_missing_dir_is_empty(tmp_path):
    result = upload_tree(_FakeStorage(), tmp_path / "nope", "/beeoffice")
    assert result["total"] == 0
    assert result["uploaded"] == 0


def test_upload_tree_progress_callback(tmp_path):
    tree = tmp_path / "data"
    _make_tree(tree)
    seen = []

    upload_tree(
        _FakeStorage(), tree, "/beeoffice",
        on_progress=lambda done, total: seen.append((done, total)),
    )

    assert len(seen) == 5, "每个文件都应回调一次"
    assert seen[-1] == (5, 5)


# ==================== describe_result：不许再说"同步完成" ====================

def test_describe_empty_dir_is_honest():
    msg = describe_result({"total": 0, "uploaded": 0, "skipped": 0,
                           "failed": 0, "reasons": {}})
    assert "为空" in msg
    assert "同步完成" not in msg


def test_describe_includes_counts_and_reasons():
    msg = describe_result({
        "total": 5, "uploaded": 2, "skipped": 3, "failed": 0,
        "reasons": {"密钥/证书类文件（.key）": 1, "空文件": 2},
    })
    assert "已上传 2" in msg
    assert "跳过 3" in msg
    assert "空文件 2" in msg
    assert "失败 0" in msg


def test_describe_zero_uploaded_still_not_success_claim():
    """一个都没传成功时也不能只报成功。"""
    msg = describe_result({
        "total": 3, "uploaded": 0, "skipped": 3, "failed": 0,
        "reasons": {"临时文件": 3},
    })
    assert "已上传 0" in msg
    assert "跳过 3" in msg


def test_describe_reports_failures():
    msg = describe_result({
        "total": 2, "uploaded": 1, "skipped": 0, "failed": 1, "reasons": {},
    })
    assert "失败 1" in msg


# ==================== 接线：app 必须用这套 ====================

def test_sync_now_uses_policy_module():
    """
    接线断言用 **AST**（真实调用节点），不用源码文本搜索 ——
    `_sync_now` 里有一段解释旧实现的注释提到 `rglob`/`storage.upload(...)`，
    文本断言会被自己的注释骗到（我第一版就是这样误报的）。
    """
    import ast
    import inspect
    import textwrap

    from beeoffice.app import BeeApp

    src = textwrap.dedent(inspect.getsource(BeeApp._sync_now))
    tree = ast.parse(src)

    called_names = {
        node.func.id
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    }
    called_attrs = {
        node.func.attr
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
    }

    assert "upload_tree" in called_names, "云同步没有走 §4.5 的过滤/计数实现"
    assert "describe_result" in called_names, "没有使用如实计数文案"
    assert "upload" not in called_attrs, (
        "app 仍在直接调用 storage.upload —— 应交给 upload_tree 统一过滤"
    )
