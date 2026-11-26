"""崩溃恢复快照存储。"""
from beeoffice.recovery import RecoveryStore


def test_recovery_roundtrip(tmp_path):
    store = RecoveryStore(tmp_path / "recovery")
    tabs = [{"kind": "word", "path": "", "content": "未保存内容", "title": "文档"}]
    assert store.save(tabs)
    data = store.load()
    assert data and data["tabs"][0]["content"] == "未保存内容"
    store.clear()
    assert store.load() is None
