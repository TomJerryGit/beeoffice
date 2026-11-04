# beeoffice/plugins/beeshow_animation.py
"""蜜演动画面板核心（阶段 A）：选择器动画 + 切换效果。

持久化标记：
    <!-- beeoffice-anim: {"transition":"fade","entries":[...]} -->
"""
from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass

MARKER_RE = re.compile(
    r"<!--\s*beeoffice-anim:\s*(\{.*?\})\s*-->", re.DOTALL
)

EFFECTS = {
    "fade_in": ("进入", "淡入", "fadeIn"),
    "slide_in": ("进入", "滑入", "slideIn"),
    "zoom_in": ("进入", "缩放进入", "zoomIn"),
    "float_in": ("进入", "浮入", "floatIn"),
    "fade_out": ("退出", "淡出", "fadeOut"),
    "slide_out": ("退出", "滑出", "slideOut"),
    "zoom_out": ("退出", "缩放退出", "zoomOut"),
    "pulse": ("强调", "脉冲", "pulse"),
    "shake": ("强调", "抖动", "shake"),
    "grow": ("强调", "放大", "grow"),
}
TRANSITIONS = {
    "none": "无",
    "fade": "淡入",
    "push": "推入",
    "wipe": "擦除",
    "cover": "覆盖",
}


@dataclass
class AnimationEntry:
    selector: str
    effect: str
    duration: int = 500
    delay: int = 0

    def __post_init__(self):
        if self.effect not in EFFECTS:
            raise ValueError(f"未知动画效果: {self.effect}")
        if not self.selector.strip():
            raise ValueError("目标选择器不能为空")
        self.duration = max(100, min(5000, int(self.duration)))
        self.delay = max(0, min(10000, int(self.delay)))


def parse_animation(html: str):
    """返回 (config|None, 去掉标记后的 html)。"""
    match = MARKER_RE.search(html or "")
    if not match:
        return None, html or ""
    try:
        config = json.loads(match.group(1))
    except json.JSONDecodeError:
        config = None
    return config, MARKER_RE.sub("", html or "").strip()


def animation_marker(config: dict) -> str:
    return (
        "<!-- beeoffice-anim: "
        + json.dumps(config, ensure_ascii=False, separators=(",", ":"))
        + " -->"
    )


_KEYFRAMES = {
    "fadeIn": "from{opacity:0}to{opacity:1}",
    "slideIn": "from{opacity:0;transform:translateY(24px)}to{opacity:1;transform:none}",
    "zoomIn": "from{opacity:0;transform:scale(0.85)}to{opacity:1;transform:none}",
    "floatIn": "from{opacity:0;transform:translateX(-24px)}to{opacity:1;transform:none}",
    "fadeOut": "from{opacity:1}to{opacity:0}",
    "slideOut": "from{opacity:1;transform:none}to{opacity:0;transform:translateY(24px)}",
    "zoomOut": "from{opacity:1;transform:none}to{opacity:0;transform:scale(0.85)}",
    "pulse": "0%,100%{transform:scale(1)}50%{transform:scale(1.08)}",
    "shake": "0%,100%{transform:translateX(0)}25%{transform:translateX(-6px)}75%{transform:translateX(6px)}",
    "grow": "from{transform:scale(1)}to{transform:scale(1.12)}",
}


def build_animation_css(config: dict) -> str:
    """按顺序生成选择器动画 CSS。"""
    if not config:
        return ""
    entries = [
        AnimationEntry(**item) for item in config.get("entries", [])
        if isinstance(item, dict) and item.get("selector")
    ]
    rules = []
    cursor = 0
    used = set()
    for entry in entries:
        _, _, name = EFFECTS[entry.effect]
        if name not in used:
            rules.append(
                f"@keyframes bee_{name}{{{_KEYFRAMES[name]}}}"
            )
            used.add(name)
        delay = cursor + entry.delay
        rules.append(
            f"{entry.selector}{{animation:bee_{name} "
            f"{entry.duration}ms ease {delay}ms both;}}"
        )
        cursor += entry.duration
    return "\n".join(rules)


def build_transition_css(transition: str) -> str:
    key = transition if transition in TRANSITIONS else "none"
    if key == "none":
        return ""
    name = f"bee_t_{key}"
    frames = {
        "fade": "from{opacity:0}to{opacity:1}",
        "push": "from{opacity:0;transform:translateX(40px)}to{opacity:1;transform:none}",
        "wipe": "from{clip-path:inset(0 100% 0 0)}to{clip-path:inset(0 0 0 0)}",
        "cover": "from{opacity:0;transform:scale(0.94)}to{opacity:1;transform:none}",
    }[key]
    return (
        f"@keyframes {name}{{{frames}}}"
        f".slide{{animation:{name} 420ms ease both;}}"
    )


def config_dict(transition: str, entries) -> dict:
    return {
        "transition": transition,
        "entries": [asdict(e) for e in entries],
    }


def inject_markers(text: str, configs) -> str:
    """把每页动画配置以注释形式写回 Markdown（保存时用）。"""
    parts = re.split(r"\n---", text or "")
    out = []
    for index, part in enumerate(parts):
        clean, _old = parse_animation(part)
        config = configs[index] if index < len(configs) else None
        if config:
            body = MARKER_RE.sub("", part).rstrip()
            part = body + "\n" + animation_marker(config)
        out.append(part)
    return "\n---".join(out)

