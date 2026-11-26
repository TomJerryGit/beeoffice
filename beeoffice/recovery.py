"""BeeOffice 崩溃恢复快照：定期把未保存标签写入本地缓存。"""
from __future__ import annotations

import json
import os
import time
from pathlib import Path


def recovery_dir() -> Path:
    candidates = []
    custom = os.environ.get("BEEOFFICE_CACHE_DIR")
    if custom:
        candidates.append(Path(custom) / "recovery")
    local = os.environ.get("LOCALAPPDATA")
    if local:
        candidates.append(Path(local) / "BeeOffice" / "recovery")
    candidates.append(Path.home() / ".beeoffice_logs" / "recovery")
    for path in candidates:
        try:
            path.mkdir(parents=True, exist_ok=True)
            probe = path / ".write_test"
            probe.write_text("ok", encoding="utf-8")
            probe.unlink(missing_ok=True)
            return path
        except Exception:
            continue
    return Path.cwd() / ".beeoffice_recovery"


class RecoveryStore:
    def __init__(self, directory=None):
        self.dir = Path(directory) if directory else recovery_dir()
        self.path = self.dir / "session.json"

    def save(self, tabs) -> bool:
        payload = {"version": 1, "saved_at": time.time(), "tabs": list(tabs or [])}
        try:
            self.dir.mkdir(parents=True, exist_ok=True)
            tmp = self.path.with_suffix(".json.tmp")
            tmp.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
            os.replace(tmp, self.path)
            return True
        except Exception:
            return False

    def load(self):
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            if data.get("version") != 1:
                return None
            return data
        except Exception:
            return None

    def clear(self):
        try:
            self.path.unlink(missing_ok=True)
        except Exception:
            pass
