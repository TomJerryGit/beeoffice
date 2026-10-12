# tests/regression/v5/test_v505_video_poster_cache.py
"""
优化规划 §2.7 回归：视频封面缓存必须跨进程稳定，并且要清理。

原缺陷（缓存永远命中不了 + %TEMP% 无限增长）
---------------------------------------------
`_replace_videos_with_posters()` 用

    poster_path = tmp_dir / f"poster_{abs(hash(video_path))}.png"

作为缓存文件名。但 Python 对字符串的 `hash()` 默认是**每个进程随机化**的
（PYTHONHASHSEED），所以同一个视频：

  - 每次运行程序都会得到一个**不同的文件名** → 缓存永远命中不了，
    每次导出都要重跑一遍 ffmpeg；
  - `%TEMP%/beeoffice_video_posters` 每导出一次就多留一个文件，
    而且**从来没有清理逻辑**。

修复：
  - 文件名改为 `sha1(路径 + mtime + 大小)`，跨进程稳定；视频被替换后
    mtime/大小变化会得到新名字，不会错误复用旧封面；
  - 命中已有缓存时直接复用（不再跑 ffmpeg）；
  - 每次导出前清理超过 7 天的缓存文件。

"跨进程稳定"这一点必须在两个**不同 PYTHONHASHSEED** 的子进程里验证 ——
同进程内比较是发现不了这个 bug 的。
"""
import json
import os
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

from beeoffice.plugins.beeshow_video_mixin import VideoMixin

ROOT = Path(__file__).resolve().parents[3]

_PROBE = textwrap.dedent(
    """
    import json, sys
    from beeoffice.plugins.beeshow_video_mixin import VideoMixin
    print("RESULT" + json.dumps({
        "path": str(VideoMixin._poster_cache_path(sys.argv[1])),
    }))
    """
)


def _poster_path_in_subprocess(video_path: str, hash_seed: str) -> str:
    env = dict(os.environ)
    env["PYTHONHASHSEED"] = hash_seed
    env["QT_QPA_PLATFORM"] = "offscreen"
    proc = subprocess.run(
        [sys.executable, "-c", _PROBE, str(video_path)],
        cwd=str(ROOT), env=env,
        capture_output=True, text=True, timeout=180,
        encoding="utf-8", errors="replace",
    )
    for line in (proc.stdout or "").splitlines():
        if line.startswith("RESULT"):
            return json.loads(line[len("RESULT"):])["path"]
    raise AssertionError(
        f"探针未产出结果（PYTHONHASHSEED={hash_seed}）："
        f"{proc.stdout!r} {proc.stderr[-1500:]!r}"
    )


# ==================== 跨进程稳定（核心回归） ====================

def test_poster_path_is_stable_across_processes(tmp_path):
    """
    不同 PYTHONHASHSEED 的子进程必须算出**同一个**缓存路径。

    原实现用 `abs(hash(...))`，这里会得到两个不同结果 → 测试失败。
    """
    video = tmp_path / "clip.mp4"
    video.write_bytes(b"fake video")

    p0 = _poster_path_in_subprocess(str(video), "0")
    p1 = _poster_path_in_subprocess(str(video), "1")
    p12345 = _poster_path_in_subprocess(str(video), "12345")

    assert p0 == p1 == p12345, (
        f"缓存路径随进程随机化（原缺陷）：\n{p0}\n{p1}\n{p12345}"
    )


def test_same_video_same_path(tmp_path):
    video = tmp_path / "a.mp4"
    video.write_bytes(b"x")
    assert (
        VideoMixin._poster_cache_path(str(video))
        == VideoMixin._poster_cache_path(str(video))
    )


def test_different_video_different_path(tmp_path):
    a = tmp_path / "a.mp4"
    b = tmp_path / "b.mp4"
    a.write_bytes(b"x")
    b.write_bytes(b"x")
    assert (
        VideoMixin._poster_cache_path(str(a))
        != VideoMixin._poster_cache_path(str(b))
    )


def test_changed_video_gets_new_path(tmp_path):
    """视频被替换（mtime/大小变化）后必须换名字，否则会复用旧封面。"""
    video = tmp_path / "clip.mp4"
    video.write_bytes(b"original")
    first = VideoMixin._poster_cache_path(str(video))

    video.write_bytes(b"much longer replacement content")
    os.utime(str(video), (1, 1))          # 确保 mtime 变化
    second = VideoMixin._poster_cache_path(str(video))

    assert first != second, "视频变了但缓存路径没变，会错误复用旧封面"


def test_poster_path_lives_in_dedicated_dir(tmp_path):
    video = tmp_path / "clip.mp4"
    video.write_bytes(b"x")
    path = VideoMixin._poster_cache_path(str(video))
    assert path.parent.name == "beeoffice_video_posters"
    assert path.suffix == ".png"


# ==================== 清理 ====================

def test_cleanup_removes_old_files_and_keeps_fresh(tmp_path, monkeypatch):
    """过期文件被删、新文件保留。"""
    cache_dir = tmp_path / "beeoffice_video_posters"
    cache_dir.mkdir()
    old = cache_dir / "poster_old.png"
    fresh = cache_dir / "poster_fresh.png"
    old.write_bytes(b"old")
    fresh.write_bytes(b"fresh")

    # 把 old 的 mtime 推到 30 天前
    import time
    thirty_days = time.time() - 30 * 86400
    os.utime(str(old), (thirty_days, thirty_days))

    monkeypatch.setattr(
        VideoMixin, "_poster_cache_dir", staticmethod(lambda: cache_dir)
    )

    removed = VideoMixin._cleanup_video_posters(max_age_days=7)

    assert removed == 1, f"应删除 1 个过期文件，实际 {removed}"
    assert not old.exists()
    assert fresh.exists(), "新文件不应被删除"


def test_cleanup_is_safe_when_dir_missing(tmp_path, monkeypatch):
    monkeypatch.setattr(
        VideoMixin, "_poster_cache_dir",
        staticmethod(lambda: tmp_path / "not_there"),
    )
    assert VideoMixin._cleanup_video_posters() == 0


def test_replace_videos_triggers_cleanup(monkeypatch):
    """导出流程必须调用清理（原实现从不清理）。"""
    called = {"n": 0}

    monkeypatch.setattr(
        VideoMixin, "_cleanup_video_posters",
        staticmethod(lambda *a, **k: called.__setitem__("n", called["n"] + 1)),
    )

    class _Host(VideoMixin):
        def _extract_video_poster(self, *a, **k):
            return None

        def _render_video_placeholder(self, text):
            return f"<p>{text}</p>"

        def _escape_html(self, text):
            return str(text)

    _Host()._replace_videos_with_posters(["<p>没有视频</p>"])

    assert called["n"] == 1, "导出时没有清理视频封面缓存"
