# beeoffice/resources/asset_manager.py
"""本地素材库：扫描/导入/删除用户素材（图片、SVG）。"""
from __future__ import annotations

import logging
import re
import shutil
from dataclasses import dataclass
from pathlib import Path

ALLOWED_EXTS = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".svg"}
MAX_BYTES = 50 * 1024 * 1024
_ILLEGAL = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


@dataclass(frozen=True)
class AssetEntry:
    name: str
    path: str
    size: int


def _safe_name(name: str) -> str:
    cleaned = _ILLEGAL.sub("_", name or "").strip().rstrip(".")
    return (cleaned or "asset")[:100]


class AssetManager:
    def __init__(self, root=None):
        self._root = Path(root or (Path.home() / ".beeoffice_assets"))
        try:
            self._root.mkdir(parents=True, exist_ok=True)
        except Exception as e:  # noqa: BLE001
            logging.error(f"创建素材目录失败 {self._root}: {e}")

    @property
    def root(self) -> Path:
        return self._root

    def list_assets(self) -> list[AssetEntry]:
        try:
            return [
                AssetEntry(p.name, str(p), p.stat().st_size)
                for p in sorted(self._root.rglob("*"))
                if p.is_file() and p.suffix.lower() in ALLOWED_EXTS
            ]
        except Exception as e:  # noqa: BLE001
            logging.error(f"扫描素材失败: {e}")
            return []

    def import_asset(self, src) -> AssetEntry | None:
        src = Path(src)
        if not src.is_file():
            raise ValueError(f"文件不存在: {src}")
        if src.suffix.lower() not in ALLOWED_EXTS:
            raise ValueError(f"不支持的素材格式: {src.suffix}")
        if src.stat().st_size > MAX_BYTES:
            raise ValueError("素材超过 50MB 限制")
        target = self._root / _safe_name(src.name)
        stem, suffix, index = target.stem, target.suffix, 1
        while target.exists():
            target = self._root / f"{stem}_{index}{suffix}"
            index += 1
        shutil.copy2(src, target)
        return AssetEntry(target.name, str(target), target.stat().st_size)

    def delete_asset(self, path) -> bool:
        path = Path(path).resolve()
        try:
            path.relative_to(self._root.resolve())
        except ValueError:
            return False
        try:
            path.unlink()
            return True
        except Exception as e:  # noqa: BLE001
            logging.error(f"删除素材失败 {path}: {e}")
            return False
