"""S2 发布工程静态检查：安装器/签名/更新入口存在且关键指令齐全。"""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_installer_assets_exist():
    iss = ROOT / "installer" / "BeeOffice.iss"
    assert iss.is_file()
    text = iss.read_text(encoding="utf-8")
    for key in ("[Setup]", "[Files]", "[Icons]", "[Registry]",
                "dist\\BeeOffice", "BeeOffice.exe"):
        assert key in text
    assert (ROOT / "tools" / "build_installer.py").is_file()
    assert (ROOT / "tools" / "sign_windows.py").is_file()


def test_release_workflow_uses_python_tools():
    workflow = ROOT / ".github" / "workflows" / "release-windows.yml"
    assert workflow.is_file()
    text = workflow.read_text(encoding="utf-8")
    assert "build_installer.py" in text
    assert "sign_windows.py" in text


def test_update_entry_exists():
    from beeoffice.update_checker import check_for_update  # noqa: F401
    app = (ROOT / "beeoffice" / "app.py").read_text(encoding="utf-8")
    menu = (ROOT / "beeoffice" / "menus.py").read_text(encoding="utf-8")
    assert "def check_for_updates" in app
    assert "check_for_updates" in menu
