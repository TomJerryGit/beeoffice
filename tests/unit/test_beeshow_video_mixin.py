"""BeeShow 视频嵌入纯逻辑补测。"""
from pathlib import Path

from beeoffice.plugins.beeshow_video_mixin import VideoMixin


class FakeShow(VideoMixin):
    def __init__(self, current_file=""):
        self._current_file_path = current_file


def test_escape_and_split():
    obj = FakeShow()
    assert obj._escape_html('<a & "b">') == "&lt;a &amp; &quot;b&quot;&gt;"
    assert obj._split_params('a.mp4, poster: "a,b.png", loop: true') == [
        "a.mp4", ' poster: "a,b.png"', " loop: true"
    ]


def test_parse_params():
    obj = FakeShow()
    p = obj._parse_video_params("a.mp4, autoplay: true, loop: yes, muted: 1, width: 50%, poster: p.png")
    assert p["video"] == "a.mp4"
    assert p["autoplay"] is True and p["loop"] is True and p["muted"] is True
    assert p["width"] == "50%"
    assert p["poster"] == "p.png"
    assert obj._parse_video_params("")["controls"] is True


def test_resolve_video_path(tmp_path):
    video = tmp_path / "v.mp4"; video.write_bytes(b"x")
    obj = FakeShow(str(tmp_path / "slides.md"))
    assert obj._resolve_video_path(str(video)) == video
    assert obj._resolve_video_path("v.mp4") == video
    assert obj._resolve_video_path("missing.mp4") is None


def test_render_video_tag(tmp_path):
    video = tmp_path / "v.mp4"; video.write_bytes(b"x")
    poster = tmp_path / "p.png"; poster.write_bytes(b"x")
    obj = FakeShow(str(tmp_path / "slides.md"))
    p = obj._parse_video_params(f"v.mp4, autoplay: true, loop: true, muted: true, height: 300, poster: p.png")
    html = obj._render_video_tag(p)
    assert "<video" in html and "autoplay" in html and "loop" in html
    assert "muted" in html and "height: 300" in html
    assert "poster=" in html
    assert "preload=\"auto\"" in html


def test_render_video_invalid(tmp_path):
    obj = FakeShow()
    missing = obj._parse_video_params("missing.mp4")
    assert "video-placeholder" in obj._render_video_tag(missing)
    assert "视频路径为空" in obj._render_video_tag(obj._parse_video_params(""))
    bad = tmp_path / "v.txt"; bad.write_bytes(b"x")
    assert "不支持的格式" in obj._render_video_tag(obj._parse_video_params(str(bad)))


def test_process_videos(tmp_path):
    video = tmp_path / "v.mp4"; video.write_bytes(b"x")
    obj = FakeShow(str(tmp_path / "slides.md"))
    out = obj._process_videos(f"# a\n{{{{video: {video}}}}}")
    assert "<video" in out
    out2 = obj._process_videos("{{video: missing.mp4}}")
    assert "video-placeholder" in out2
    assert "no video" in obj._process_videos("no video")


def test_copy_videos_for_html_export(tmp_path):
    video = tmp_path / "v.mp4"; video.write_bytes(b"x")
    poster = tmp_path / "p.png"; poster.write_bytes(b"x")
    out_dir = tmp_path / "out"
    obj = FakeShow()
    html = [f'<video src="{video}" poster="{poster}"></video>']
    result = obj._copy_videos_for_html_export(out_dir, html)
    assert "media/v.mp4" in result[0]
    assert (out_dir / "media" / "v.mp4").exists()
    assert (out_dir / "media" / "p.png").exists()
    # 同一次导出内复用已复制文件
    html2 = [f'<video src="{video}"></video>', f'<img src="{video}">']
    result2 = obj._copy_videos_for_html_export(out_dir, html2)
    assert "media/v_1.mp4" in result2[0]


def test_extract_poster_no_ffmpeg(monkeypatch):
    import beeoffice.plugins.beeshow_video_mixin as m
    monkeypatch.setattr(m.shutil, "which", lambda name: None)
    obj = FakeShow()
    assert obj._extract_video_poster("v.mp4", "out.png") is None


def test_replace_videos_with_posters(tmp_path):
    obj = FakeShow()
    calls = []
    def fake_extract(video, out):
        calls.append(video)
        if video.endswith("a.mp4"):
            return str(tmp_path / "poster.png")
        return None
    obj._extract_video_poster = fake_extract
    html = [
        '<video src="a.mp4" style="width:80%"></video><video src="a.mp4"></video>',
        '<video src="b.mp4"></video>',
    ]
    result = obj._replace_videos_with_posters(html)
    assert '<img src=' in result[0]
    assert "视频封面" in result[0]
    assert "video-placeholder" in result[1]
    # 同一视频只提取一次
    assert calls.count("a.mp4") == 1


def test_extract_poster_success_and_failure(monkeypatch, tmp_path):
    import beeoffice.plugins.beeshow_video_mixin as m
    monkeypatch.setattr(m.shutil, "which", lambda name: "ffmpeg")
    out = tmp_path / "p.png"
    class Res:
        returncode = 0
        stderr = b""
    def fake_run(cmd, **kwargs):
        out.write_bytes(b"x")
        return Res()
    monkeypatch.setattr(m.subprocess, "run", fake_run)
    obj = FakeShow()
    assert obj._extract_video_poster("v.mp4", str(out)) == str(out)
    class Bad:
        returncode = 1
        stderr = b"err"
    monkeypatch.setattr(m.subprocess, "run", lambda *a, **k: Bad())
    assert obj._extract_video_poster("v.mp4", str(tmp_path / "x.png")) is None
