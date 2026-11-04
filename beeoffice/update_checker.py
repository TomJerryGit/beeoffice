# beeoffice/update_checker.py
"""自动更新检查：读取 GitHub Releases，比较版本并校验下载包。

安全边界：
  - 只接受 HTTPS 的 GitHub 下载 URL；
  - 下载后必须校验 sha256；
  - 默认不自动安装，只提示用户打开 Release 页面。
"""
from __future__ import annotations

import hashlib
import json
import re
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path

DEFAULT_REPO = "TomJerryGit/beeoffice"
API = "https://api.github.com/repos/{repo}/releases"


class UpdateError(RuntimeError):
    pass


@dataclass
class UpdateInfo:
    version: str
    tag: str
    html_url: str
    body: str = ""
    published_at: str = ""
    prerelease: bool = False
    assets: list[dict] = field(default_factory=list)

    @property
    def sha256_asset(self) -> dict | None:
        for asset in self.assets:
            if asset.get("name", "").endswith(".sha256"):
                return asset
        return None


def parse_version(text: str) -> tuple[int, ...]:
    """'v5.3.2' / '5.3.2' / '5.3.2-beta' → (5,3,2)。"""
    match = re.search(r"(\d+(?:\.\d+)*)", text or "")
    if not match:
        raise UpdateError(f"无法解析版本号: {text!r}")
    return tuple(int(p) for p in match.group(1).split("."))


def is_newer(current: str, latest: str) -> bool:
    cur = parse_version(current)
    new = parse_version(latest)
    width = max(len(cur), len(new))
    return new + (0,) * (width - len(new)) > cur + (0,) * (width - len(cur))


def _get_json(url: str, timeout: int = 8):
    req = urllib.request.Request(url, headers={
        "Accept": "application/vnd.github+json",
        "User-Agent": "BeeOffice-UpdateChecker",
    })
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except Exception as e:  # noqa: BLE001
        raise UpdateError(f"检查更新失败: {e}") from e


def check_for_update(current_version: str,
                     repo: str = DEFAULT_REPO,
                     include_prerelease: bool = False,
                     timeout: int = 8) -> UpdateInfo | None:
    """返回比 current_version 新的 Release；没有则返回 None。"""
    releases = _get_json(API.format(repo=repo), timeout=timeout)
    if not isinstance(releases, list):
        raise UpdateError("GitHub Releases 返回格式异常")
    candidates = []
    for item in releases:
        if item.get("draft"):
            continue
        if item.get("prerelease") and not include_prerelease:
            continue
        try:
            version = ".".join(str(p) for p in parse_version(item.get("tag_name", "")))
        except UpdateError:
            continue
        candidates.append((parse_version(version), version, item))
    if not candidates:
        return None
    candidates.sort(key=lambda x: x[0], reverse=True)
    _, version, item = candidates[0]
    if not is_newer(current_version, version):
        return None
    return UpdateInfo(
        version=version,
        tag=item.get("tag_name", ""),
        html_url=item.get("html_url", ""),
        body=item.get("body", "") or "",
        published_at=item.get("published_at", "") or "",
        prerelease=bool(item.get("prerelease")),
        assets=list(item.get("assets") or []),
    )


def download_update(url: str, dest, expected_sha256: str) -> Path:
    """下载更新包并校验 sha256；仅允许 HTTPS。"""
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme != "https":
        raise UpdateError("更新包必须使用 HTTPS")
    req = urllib.request.Request(url, headers={"User-Agent": "BeeOffice-Updater"})
    target = Path(dest)
    target.parent.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha256()
    try:
        with urllib.request.urlopen(req, timeout=60) as resp, \
                open(target, "wb") as f:
            while True:
                chunk = resp.read(1024 * 1024)
                if not chunk:
                    break
                digest.update(chunk)
                f.write(chunk)
    except Exception as e:  # noqa: BLE001
        target.unlink(missing_ok=True)
        raise UpdateError(f"下载更新失败: {e}") from e
    actual = digest.hexdigest().lower()
    if actual != (expected_sha256 or "").strip().lower():
        target.unlink(missing_ok=True)
        raise UpdateError("更新包 sha256 校验失败，已删除下载文件")
    return target
