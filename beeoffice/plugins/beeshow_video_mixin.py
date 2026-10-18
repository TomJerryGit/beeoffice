# beeoffice/plugins/beeshow_video_mixin.py
"""
蜜演视频嵌入 Mixin（任务 5.3）

功能：
  把 Markdown 中的 {{video: path/to/video.mp4}} 语法渲染为 <video> 标签。

对标：
  - WPS 演示的「插入视频」——支持 MP4 嵌入、自动播放、循环

语法：
  {{video: path/to/video.mp4}}
  {{video: path/to/video.mp4, autoplay: true}}
  {{video: path/to/video.mp4, autoplay: true, loop: true, controls: true}}
  {{video: path/to/video.mp4, width: 80%, height: 400}}
  {{video: path/to/video.mp4, poster: path/to/poster.png}}

参数：
  - video    : 视频文件路径（必填）
  - autoplay : 自动播放（默认 false）
  - loop     : 循环播放（默认 false）
  - controls : 显示播放控制条（默认 true）
  - muted    : 静音（autoplay 时通常需要 true）
  - width    : 宽度（默认 80%）
  - height   : 高度（默认 auto）
  - poster   : 封面图路径（可选）

路径解析：
  - 绝对路径：直接使用
  - 相对路径：优先从 _current_file_path 的父目录解析
             其次从当前工作目录
             最后从用户主目录

导出：
  - HTML 导出：复制视频文件到输出目录，改相对路径
  - PDF 导出：用 ffmpeg 提取首帧（若有），否则占位图
  - PPTX 导出：跳过视频（python-pptx 支持有限，一期不实现）

依赖：
  - PySide6（无，本模块纯逻辑）
  - ffmpeg（可选，用于 PDF 导出的首帧提取）

注意：
  - 不导入其他 beeshow_* Mixin
  - 视频不存在时渲染为占位符，提示用户
"""

import re
import logging
import subprocess
import shutil
from pathlib import Path
from typing import Dict, Any, Optional
from beeoffice.i18n import tr


# ==================== 语法解析 ====================
# 匹配 {{video: ...}}
VIDEO_PATTERN = re.compile(
    r"\{\{\s*video\s*:\s*(.+?)\s*\}\}",
    re.IGNORECASE,
)


class VideoMixin:
    """蜜演视频嵌入 Mixin"""

    # 支持的视频格式
    SUPPORTED_FORMATS = {".mp4", ".webm", ".ogg", ".mov", ".m4v"}

    # ==================== Markdown 预处理 ====================
    def _process_videos(self, md_text: str) -> str:
        """
        把 Markdown 中的 {{video: ...}} 替换为 <video> 标签。

        :param md_text: 原始 Markdown
        :return: 替换后的 Markdown
        """
        def replace(match):
            try:
                inner = match.group(1).strip()
                params = self._parse_video_params(inner)
                return self._render_video_tag(params)
            except Exception as e:
                logging.warning(
                    tr("auto.beeshow_video_mixin.fa61b122", "视频解析失败：{0}（原文：{1}）").format(e, match.group(0))
                )
                return match.group(0)

        return VIDEO_PATTERN.sub(replace, md_text)

    def _parse_video_params(self, inner: str) -> Dict[str, Any]:
        """
        解析 {{video: path, autoplay: true, ...}} 里的参数。

        :param inner: 大括号内、冒号后的部分
        :return: 参数字典
        """
        params = {
            "video": "",
            "autoplay": False,
            "loop": False,
            "controls": True,
            "muted": False,
            "width": "80%",
            "height": "auto",
            "poster": "",
        }

        parts = self._split_params(inner)

        for part in parts:
            part = part.strip()
            if not part:
                continue

            if ":" in part:
                # key: value 形式
                key, _, value = part.partition(":")
                key = key.strip().lower()
                value = value.strip().strip('"').strip("'")

                # 布尔值转换
                if key in ("autoplay", "loop", "controls", "muted"):
                    params[key] = value.lower() in ("true", "1", "yes", "是")
                else:
                    params[key] = value
            else:
                # 纯路径（第一个参数）
                if not params["video"]:
                    params["video"] = part

        return params

    @staticmethod
    def _split_params(text: str) -> list:
        """按逗号切分参数，忽略引号内的逗号"""
        parts = []
        current = []
        in_quote = False
        quote_char = ""

        for ch in text:
            if in_quote:
                current.append(ch)
                if ch == quote_char:
                    in_quote = False
            elif ch in ('"', "'"):
                in_quote = True
                quote_char = ch
                current.append(ch)
            elif ch == ",":
                parts.append("".join(current))
                current = []
            else:
                current.append(ch)

        if current:
            parts.append("".join(current))

        return parts

    # ==================== 路径解析 ====================
    def _resolve_video_path(self, video_path: str) -> Optional[Path]:
        """
        解析视频路径（多基准目录兜底）。

        优先级：
          1. 绝对路径：直接使用
          2. _current_file_path 的父目录
          3. 当前工作目录
          4. 用户主目录

        :param video_path: 原始路径
        :return: 存在的 Path 或 None
        """
        p = Path(video_path)
        if p.is_absolute():
            return p if p.exists() else None

        # 候选基准目录
        candidates = []

        # 1. 当前文件的父目录
        try:
            current = getattr(self, "_current_file_path", None)
            if current:
                candidates.append(Path(current).parent)
        except Exception:
            pass

        # 2. 当前工作目录
        candidates.append(Path.cwd())

        # 3. 用户主目录
        candidates.append(Path.home())

        for base in candidates:
            candidate = base / video_path
            if candidate.exists():
                return candidate

        return None

    # ==================== HTML 渲染 ====================
    def _render_video_tag(self, params: Dict[str, Any]) -> str:
        """
        生成 <video> 标签。

        输出形如：
          <video src="path.mp4" controls
                 style="width: 80%; display: block; margin: 20px auto;">
          </video>
        """
        video_path = params["video"]
        if not video_path:
            return self._render_video_placeholder("（视频路径为空）")

        # 解析路径
        resolved = self._resolve_video_path(video_path)
        if resolved is None:
            logging.warning(tr("auto.beeshow_video_mixin.c77b82f5", "视频文件不存在：{video_path}").format(video_path=video_path))
            return self._render_video_placeholder(
                f"视频不存在：{video_path}"
            )

        # 格式检查
        ext = resolved.suffix.lower()
        if ext not in self.SUPPORTED_FORMATS:
            logging.warning(tr("auto.beeshow_video_mixin.2ec98097", "不支持的视频格式：{ext}").format(ext=ext))
            return self._render_video_placeholder(
                f"不支持的格式：{ext}"
            )

        # 构造属性
        attrs = [f'src="{self._escape_html(str(resolved))}"']

        if params["controls"]:
            attrs.append("controls")
        if params["autoplay"]:
            attrs.append("autoplay")
        if params["loop"]:
            attrs.append("loop")
        if params["muted"]:
            attrs.append("muted")
        if params["poster"]:
            poster_resolved = self._resolve_video_path(params["poster"])
            if poster_resolved:
                attrs.append(
                    f'poster="{self._escape_html(str(poster_resolved))}"'
                )

        # 样式
        style_parts = [
            f"width: {params['width']}",
            "display: block",
            "margin: 20px auto",
            "border-radius: 8px",
            "max-width: 100%",
        ]
        if params["height"] != "auto":
            style_parts.append(f"height: {params['height']}")
        attrs.append(f'style="{"; ".join(style_parts)}"')

        # preload：autoplay 时用 auto，否则 metadata
        attrs.append(
            f'preload="{"auto" if params["autoplay"] else "metadata"}"'
        )

        return f"<video {' '.join(attrs)}></video>"

    def _render_video_placeholder(self, message: str) -> str:
        """渲染占位符（视频缺失时）"""
        return (
            f'<div class="video-placeholder" '
            f'style="display: block; margin: 20px auto; '
            f'padding: 40px; background: #F5F5F5; '
            f'border: 2px dashed #CCC; border-radius: 8px; '
            f'text-align: center; color: #999; '
            f'font-size: 14px;">'
            f'🎬 {self._escape_html(message)}'
            f'</div>'
        )

    @staticmethod
    def _escape_html(s: str) -> str:
        """HTML 转义"""
        return (
            str(s)
            .replace("&", "&amp;")
            .replace('"', "&quot;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
        )

    # ==================== 导出：HTML ====================
    def _copy_videos_for_html_export(
        self, output_dir: Path, slides_html: list
    ) -> list:
        """
        导出 HTML 时，复制视频文件到输出目录的 media/ 子目录。

        :param output_dir: HTML 输出目录
        :param slides_html: 幻灯片 HTML 片段列表
        :return: 处理后的 HTML 片段列表（src 改为相对路径）
        """
        media_dir = Path(output_dir) / "media"
        media_dir.mkdir(parents=True, exist_ok=True)

        copied = {}
        new_slides = []

        for html in slides_html:
            # 找所有 <video src="..."> 和 poster="..."
            def replace_src(match):
                attr = match.group(1)  # src 或 poster
                original = match.group(2)
                try:
                    src_path = Path(original)
                    if not src_path.exists():
                        return match.group(0)

                    # 已复制过则复用
                    if str(src_path) in copied:
                        new_name = copied[str(src_path)]
                    else:
                        # 保证文件名唯一
                        new_name = src_path.name
                        counter = 1
                        while (media_dir / new_name).exists():
                            stem = src_path.stem
                            suffix = src_path.suffix
                            new_name = f"{stem}_{counter}{suffix}"
                            counter += 1
                        shutil.copy2(
                            src_path, media_dir / new_name
                        )
                        copied[str(src_path)] = new_name

                    return f'{attr}="media/{new_name}"'
                except Exception as e:
                    logging.warning(tr("auto.beeshow_video_mixin.1b5ff4e5", "复制视频失败 {original}：{e}").format(original=original, e=e))
                    return match.group(0)

            new_html = re.sub(
                r'(src|poster)="([^"]+)"',
                replace_src,
                html,
            )
            new_slides.append(new_html)

        if copied:
            logging.info(f"已复制 {len(copied)} 个视频到 {media_dir}")

        return new_slides

    # ==================== 导出：PDF ====================
    def _extract_video_poster(
        self, video_path: str, output_path: str
    ) -> Optional[str]:
        """
        用 ffmpeg 提取视频首帧作为 PDF 导出用的静态图。

        :param video_path: 视频路径
        :param output_path: 输出 PNG 路径
        :return: 输出路径（成功）或 None（失败）

        无 ffmpeg 时返回 None（调用方降级为占位符）。
        """
        # 检查 ffmpeg
        ffmpeg = shutil.which("ffmpeg")
        if not ffmpeg:
            logging.info("未找到 ffmpeg，无法提取视频首帧")
            return None

        try:
            result = subprocess.run(
                [
                    ffmpeg,
                    "-y",               # 覆盖输出
                    "-i", video_path,
                    "-ss", "00:00:00.5",  # 取 0.5 秒处（避免黑屏首帧）
                    "-vframes", "1",     # 只取一帧
                    "-q:v", "2",         # 高质量
                    output_path,
                ],
                capture_output=True,
                timeout=30,
            )
            if result.returncode == 0 and Path(output_path).exists():
                logging.info(f"视频首帧已提取：{output_path}")
                return output_path
            else:
                logging.warning(
                    tr("auto.beeshow_video_mixin.dbab38c1", "ffmpeg 提取失败：{0}").format(result.stderr.decode()[:200])
                )
                return None
        except subprocess.TimeoutExpired:
            logging.warning(tr("auto.beeshow_video_mixin.549f4411", "ffmpeg 提取超时"))
            return None
        except Exception as e:
            logging.error(f"ffmpeg 提取异常：{e}")
            return None

    def _replace_videos_with_posters(self, slides_html: list) -> list:
        """
        导出 PDF/PPTX 时，把 <video> 替换为 <img>（首帧截图）。

        :param slides_html: 幻灯片 HTML 片段列表
        :return: 处理后的 HTML 片段列表
        """
        import tempfile

        new_slides = []
        poster_cache = {}

        for html in slides_html:
            def replace_video(match):
                full_tag = match.group(0)
                # 提取 src
                src_match = re.search(
                    r'src="([^"]+)"', full_tag
                )
                if not src_match:
                    return full_tag

                video_path = src_match.group(1)

                # 提取 style
                style_match = re.search(
                    r'style="([^"]*)"', full_tag
                )
                style = style_match.group(1) if style_match else ""

                # 缓存：同一视频只提取一次
                if video_path in poster_cache:
                    poster = poster_cache[video_path]
                else:
                    try:
                        tmp_dir = Path(tempfile.gettempdir()) / \
                            "beeoffice_video_posters"
                        tmp_dir.mkdir(parents=True, exist_ok=True)
                        poster_path = tmp_dir / (
                            f"poster_{abs(hash(video_path))}.png"
                        )
                        poster = self._extract_video_poster(
                            video_path, str(poster_path)
                        )
                    except Exception as e:
                        logging.warning(tr("auto.beeshow_video_mixin.536f33de", "提取封面失败：{e}").format(e=e))
                        poster = None
                    poster_cache[video_path] = poster

                if poster:
                    return (
                        f'<img src="{self._escape_html(poster)}" '
                        f'style="{style}" '
                        f'alt="视频封面">'
                    )
                else:
                    return self._render_video_placeholder(
                        f"视频：{Path(video_path).name}\n"
                        f"（PDF 中无法播放，可安装 ffmpeg 提取封面）"
                    )

            new_html = re.sub(
                r"<video[^>]*>.*?</video>",
                replace_video,
                html,
                flags=re.DOTALL,
            )
            # 处理自闭合的 <video ...></video>
            new_html = re.sub(
                r"<video[^>]*/>",
                replace_video,
                new_html,
            )
            new_slides.append(new_html)

        return new_slides