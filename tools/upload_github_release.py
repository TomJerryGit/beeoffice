# tools/upload_github_release.py
"""创建 GitHub Release 并上传资产（自动读取 Git Credential Manager / 环境 token）。

用法：
    python tools/upload_github_release.py --tag v5.1.0 \
        --asset release-archive/BeeOffice-v5.1.0-windows.zip \
        --asset release-archive/BeeOffice-v5.1.0-windows.zip.sha256

凭据优先级：GH_TOKEN / GITHUB_TOKEN -> git credential fill。
脚本不会打印 token。
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

REPO = "TomJerryGit/beeoffice"
API = "https://api.github.com"
UPLOAD = "https://uploads.github.com"


def _token() -> str:
    import os

    for key in ("GH_TOKEN", "GITHUB_TOKEN"):
        value = os.environ.get(key, "").strip()
        if value:
            return value
    payload = "protocol=https\nhost=github.com\nusername=TomJerryGit\n\n"
    try:
        out = subprocess.run(
            ["git", "credential", "fill"], input=payload,
            capture_output=True, text=True, timeout=30, check=False,
        ).stdout
    except Exception as e:  # noqa: BLE001
        raise SystemExit(f"无法读取 git 凭据: {e}")
    for line in out.splitlines():
        if line.startswith("password="):
            return line.split("=", 1)[1].strip()
    raise SystemExit("未找到 GitHub token（GH_TOKEN/GITHUB_TOKEN/git credential）")


def _request(method: str, url: str, token: str, data=None,
             content_type="application/json"):
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Authorization", f"Bearer {token}")
    req.add_header("Accept", "application/vnd.github+json")
    req.add_header("X-GitHub-Api-Version", "2022-11-28")
    req.add_header("User-Agent", "BeeOffice-Release-Uploader")
    if data is not None:
        req.add_header("Content-Type", content_type)
    try:
        with urllib.request.urlopen(req, timeout=300) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        raise SystemExit(f"GitHub API {method} {url} -> {e.code}: {body[:500]}")


def ensure_release(token: str, tag: str, name: str, body: str) -> dict:
    url = f"{API}/repos/{REPO}/releases"
    payload = json.dumps({
        "tag_name": tag, "name": name, "body": body, "draft": False,
        "prerelease": False,
    }).encode()
    try:
        return _request("POST", url, token, payload)
    except SystemExit as e:
        if "422" not in str(e):
            raise
    # 已存在则查回
    rel = _request("GET", f"{url}/tags/{tag}", token)
    return rel


def upload_asset(token: str, release: dict, path: Path) -> dict:
    existing = {a["name"]: a for a in release.get("assets", [])}
    if path.name in existing:
        return existing[path.name]
    data = path.read_bytes()
    ctype = "application/zip" if path.suffix == ".zip" else "text/plain"
    url = (f"{UPLOAD}/repos/{REPO}/releases/{release['id']}/assets"
           f"?name={urllib.parse.quote(path.name)}")
    return _request("POST", url, token, data, ctype)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--tag", required=True)
    parser.add_argument("--name", default="")
    parser.add_argument("--notes-file", default="")
    parser.add_argument("--asset", action="append", default=[])
    parser.add_argument("--repo", default=REPO)
    args = parser.parse_args(argv)
    globals()["REPO"] = args.repo
    token = _token()
    body = ""
    if args.notes_file:
        body = Path(args.notes_file).read_text(encoding="utf-8")
    release = ensure_release(
        token, args.tag, args.name or args.tag, body
    )
    print(f"release: {release.get('html_url', release.get('id'))}")
    for item in args.asset:
        path = Path(item)
        if not path.is_file():
            raise SystemExit(f"资产不存在: {path}")
        asset = upload_asset(token, release, path)
        print(f"asset: {asset.get('name')} {asset.get('size')} bytes")
    return 0


if __name__ == "__main__":
    sys.exit(main())
