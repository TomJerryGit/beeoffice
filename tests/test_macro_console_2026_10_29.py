"""S3 宏控制台：白名单/审计/回放/UI 冒烟。"""
import pytest

from beeoffice.macro_console import MacroAudit, MacroError, MacroRegistry, MacroRunner


def test_whitelist_and_audit(tmp_path):
    log = tmp_path / "audit.jsonl"
    reg = MacroRegistry()
    reg.register("add", lambda a=0, b=0: a + b)
    audit = MacroAudit(log)
    assert reg.execute("add", {"a": 1, "b": 2}, audit) == 3
    with pytest.raises(MacroError):
        reg.execute("rm", {})
    assert "add" in log.read_text(encoding="utf-8")


def test_missing_arg_and_runner(tmp_path):
    reg = MacroRegistry()
    reg.register("need", lambda x: x, required_args=("x",))
    with pytest.raises(MacroError):
        reg.execute("need", {})
    runner = MacroRunner(reg, MacroAudit(tmp_path / "a.jsonl"))
    assert runner.run([{"command": "need", "args": {"x": 5}}]) == [5]


def test_ui_registry_contains_whitelist(qtbot):
    from beeoffice.plugins.macro_console_dialog import build_registry

    app = type("App", (), {})()
    reg = build_registry(app)
    assert "ui.pdf_toolbox" in reg.ids()
    assert "macro.wait" in reg.ids()
