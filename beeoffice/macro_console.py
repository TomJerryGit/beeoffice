# beeoffice/macro_console.py
"""宏控制台核心：白名单命令 + 参数校验 + 审计日志（S3）。

不提供任意 Python 执行；所有命令必须显式注册。
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable


class MacroError(ValueError):
    pass


@dataclass(frozen=True)
class MacroCommand:
    command_id: str
    handler: Callable[..., Any]
    description: str = ""
    required_args: tuple[str, ...] = ()


class MacroAudit:
    def __init__(self, path: str | Path | None = None):
        self.path = Path(path) if path else None

    def write(self, command_id: str, args: dict, ok: bool, result: Any = None,
              error: str = ""):
        record = {
            "ts": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "command": command_id,
            "args": args,
            "ok": bool(ok),
            "result": "" if result is None else str(result)[:500],
            "error": error[:500],
        }
        if self.path is not None:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self.path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(record, ensure_ascii=False) + "\n")
        return record


class MacroRegistry:
    def __init__(self):
        self._commands: dict[str, MacroCommand] = {}

    def register(self, command_id: str, handler: Callable, *,
                 description: str = "", required_args: tuple[str, ...] = ()):
        if not command_id or command_id in self._commands:
            raise MacroError(f"命令重复或为空: {command_id}")
        if not callable(handler):
            raise MacroError("handler 必须可调用")
        self._commands[command_id] = MacroCommand(
            command_id, handler, description, tuple(required_args)
        )

    def get(self, command_id: str) -> MacroCommand:
        if command_id not in self._commands:
            raise MacroError(f"命令不在白名单: {command_id}")
        return self._commands[command_id]

    def ids(self) -> list[str]:
        return sorted(self._commands)

    def execute(self, command_id: str, args: dict | None = None,
                audit: MacroAudit | None = None):
        args = dict(args or {})
        cmd = self.get(command_id)
        missing = [name for name in cmd.required_args if name not in args]
        if missing:
            err = f"缺少参数: {', '.join(missing)}"
            if audit:
                audit.write(command_id, args, False, error=err)
            raise MacroError(err)
        try:
            result = cmd.handler(**args)
        except Exception as e:  # noqa: BLE001
            if audit:
                audit.write(command_id, args, False, error=str(e))
            raise
        if audit:
            audit.write(command_id, args, True, result=result)
        return result


class MacroRunner:
    """回放 JSON 步骤：[{"command": "...", "args": {...}}, ...]。"""

    def __init__(self, registry: MacroRegistry, audit: MacroAudit | None = None):
        self.registry = registry
        self.audit = audit

    def run(self, steps: list[dict]) -> list[Any]:
        results = []
        for index, step in enumerate(steps, 1):
            if not isinstance(step, dict) or "command" not in step:
                raise MacroError(f"第 {index} 步格式错误")
            results.append(self.registry.execute(
                str(step["command"]), step.get("args") or {}, self.audit
            ))
        return results
