"""BeeShow 版式槽位绑定：标题/正文/图片/说明。"""
from __future__ import annotations

from beeoffice.plugins.beeshow_constants import LAYOUTS


def bind_layout(layout_id: str, slots: dict) -> str:
    """把槽位值套入版式骨架，返回 Markdown。"""
    meta = LAYOUTS.get(layout_id)
    if not meta:
        return ""
    md = meta["skeleton"]
    title = (slots.get("title") or "").strip()
    body = (slots.get("body") or "").strip()
    subtitle = (slots.get("subtitle") or "").strip()
    image = (slots.get("image") or "").strip()
    caption = (slots.get("caption") or "").strip()

    if title:
        lines = md.splitlines()
        for i, line in enumerate(lines):
            if line.startswith("# "):
                lines[i] = "# " + title
                break
        md = "\n".join(lines)

    if subtitle:
        md = md.replace("> 副标题 / 演讲人 / 日期", "> " + subtitle)

    if image:
        import re as _re
        md = _re.sub(r"!\[[^\]]*\]\([^)]*\)", f"![]({image})", md, count=1)
    if caption:
        md = md.replace("在此输入图片说明", caption)

    if body:
        lines = body.splitlines()
        # 替换第一条连续的 - 列表
        out = []
        replaced = False
        for line in md.splitlines():
            if not replaced and line.startswith("- "):
                for item in lines:
                    out.append("- " + item.lstrip("- ").strip())
                replaced = True
            else:
                out.append(line)
        md = "\n".join(out)

    for key, value in (slots.get("extra") or {}).items():
        md = md.replace("{" + key + "}", str(value))
    return md
