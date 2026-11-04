"""宏控制台扩展：脚本导入导出 + 首次风险确认 + 新命令。"""
import json

import pytest

from beeoffice.macro_console import (
    MacroError,
    MacroRegistry,
    load_script,
    mark_risk_ack,
    needs_risk_ack,
    save_script,
    validate_steps,
)
from beeoffice.plugins.macro_console_dialog import build_registry


def test_script_roundtrip(tmp_path):
    steps = [
        {"command": "macro.wait", "args": {"seconds": 0}},
        {"command": "file.save", "args": {}},
    ]
    path = tmp_path / "macro.json"
    save_script(path, steps)
    assert load_script(path) == steps
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["steps"][0]["command"] == "macro.wait"


def test_validate_steps_rejects_bad_shapes():
    with pytest.raises(MacroError):
        validate_steps({"not": "a list"})
    with pytest.raises(MacroError):
        validate_steps([{"args": {}}])


def test_risk_ack_marker(tmp_path):
    marker = tmp_path / "ack"
    assert needs_risk_ack(marker) is True
    mark_risk_ack(marker)
    assert needs_risk_ack(marker) is False


def test_new_commands_registered():
    class App:
        tab_manager = None

    ids = build_registry(App()).ids()
    assert "file.save" in ids
    assert "pdf.merge" in ids
    assert "pdf.compress" in ids
    assert "sheet.sort" in ids


def test_required_args_checked():
    reg = MacroRegistry()
    reg.register("x", lambda a: a, required_args=("a",))
    with pytest.raises(MacroError):
        reg.execute("x", {})
