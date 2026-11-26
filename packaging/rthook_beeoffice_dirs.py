"""PyInstaller runtime hook: ensure BeeOffice has writable temp/cache dirs.

Runs before matplotlib's runtime hook, which requires a usable temp directory.
Falls back to the application directory when %TEMP% is unavailable.
"""
from __future__ import annotations

import os
from pathlib import Path


def _try_dir(path: Path) -> bool:
    try:
        path.mkdir(parents=True, exist_ok=True)
        probe = path / ".beeoffice_write_test"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink(missing_ok=True)
        return True
    except Exception:
        return False


def _base():
    if getattr(os, "frozen", False):
        return Path(os.path.dirname(os.path.abspath(__import__("sys").executable)))
    return Path(__file__).resolve().parents[1]


def _install():
    candidates = []
    custom = os.environ.get("BEEOFFICE_CACHE_DIR")
    if custom:
        candidates.append(Path(custom))
    for env_name in ("LOCALAPPDATA", "APPDATA"):
        value = os.environ.get(env_name)
        if value:
            candidates.append(Path(value) / "BeeOffice" / "cache")
    candidates.append(_base() / ".beeoffice_cache")
    candidates.append(Path.cwd() / ".beeoffice_cache")
    for base in candidates:
        if not _try_dir(base):
            continue
        temp = base / "temp"
        mpl = base / "matplotlib"
        if not _try_dir(temp) or not _try_dir(mpl):
            continue
        os.environ["TMP"] = str(temp)
        os.environ["TEMP"] = str(temp)
        os.environ["TMPDIR"] = str(temp)
        os.environ["MPLCONFIGDIR"] = str(mpl)
        os.environ["BEEOFFICE_CACHE_DIR"] = str(base)
        return True
    return False


_install()
