"""本地素材库：扫描/导入/删除/安全边界。"""
from PIL import Image

from beeoffice.resources.asset_manager import AssetManager


def test_import_list_delete(tmp_path):
    root = tmp_path / "assets"
    mgr = AssetManager(root)
    src = tmp_path / "pic.png"
    Image.new("RGB", (10, 10), "red").save(src)
    entry = mgr.import_asset(src)
    assert entry is not None
    assert (root / "pic.png").is_file()
    assert [a.name for a in mgr.list_assets()] == ["pic.png"]
    assert mgr.delete_asset(entry.path) is True
    assert mgr.list_assets() == []


def test_duplicate_name_gets_suffix(tmp_path):
    mgr = AssetManager(tmp_path / "assets")
    src = tmp_path / "pic.png"
    Image.new("RGB", (10, 10), "red").save(src)
    first = mgr.import_asset(src)
    second = mgr.import_asset(src)
    assert first.name == "pic.png"
    assert second.name == "pic_1.png"


def test_reject_unsupported_and_outside_delete(tmp_path):
    mgr = AssetManager(tmp_path / "assets")
    bad = tmp_path / "a.txt"
    bad.write_text("x", encoding="utf-8")
    try:
        mgr.import_asset(bad)
    except ValueError:
        pass
    else:
        raise AssertionError("应拒绝非图片素材")
    outside = tmp_path / "outside.png"
    Image.new("RGB", (5, 5)).save(outside)
    assert mgr.delete_asset(outside) is False
