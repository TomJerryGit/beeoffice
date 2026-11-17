"""BeeShow 原生形状模型 + PPTX 导出。"""
from __future__ import annotations

import json
import re

MARKER_RE = re.compile(r"<!--\s*beeoffice-shapes:\s*(\{.*?\})\s*-->", re.DOTALL)
DEFAULT_SHAPES = []


def parse_shapes(md: str):
    m = MARKER_RE.search(md or "")
    if not m:
        return [], md or ""
    try:
        data = json.loads(m.group(1))
        return list(data.get("shapes", [])), MARKER_RE.sub("", md).strip()
    except Exception:
        return [], md or ""


def marker_for(shapes) -> str:
    return "<!-- beeoffice-shapes: " + json.dumps(
        {"shapes": list(shapes)}, ensure_ascii=False, separators=(",", ":")
    ) + " -->"


def shapes_html(shapes) -> str:
    parts = []
    for s in shapes or []:
        kind = s.get("kind", "rect")
        x = float(s.get("x", 10)); y = float(s.get("y", 10))
        w = float(s.get("w", 30)); h = float(s.get("h", 15))
        fill = s.get("fill", "#FFF3E0"); line = s.get("line", "#E67E22")
        text = str(s.get("text", ""))
        rot = float(s.get("rotation", 0) or 0)
        base = (f"position:absolute;left:{x}%;top:{y}%;width:{w}%;height:{h}%;"
                f"box-sizing:border-box;border:2px solid {line};"
                f"transform:rotate({rot}deg);"
                f"display:flex;align-items:center;justify-content:center;")
        if kind == "ellipse":
            base += f"border-radius:50%;background:{fill};"
            parts.append(f'<div style="{base}">{text}</div>')
        elif kind == "text":
            base += f"background:transparent;border:1px dashed {line};color:{line};"
            parts.append(f'<div style="{base}">{text or "文本"}</div>')
        elif kind == "art":
            base += f"background:transparent;border:none;color:{line};"
            parts.append(f'<div style="{base}font-size:32px;font-weight:bold;">{text or "艺术字"}</div>')
        else:
            base += f"background:{fill};"
            parts.append(f'<div style="{base}">{text}</div>')
    return '<div class="native-shapes" style="position:absolute;inset:0;pointer-events:none;">' + "".join(parts) + "</div>"


def apply_native_shapes(pptx_path: str, configs) -> int:
    """把原生形状写入 PPTX。"""
    from pptx import Presentation
    from pptx.enum.shapes import MSO_SHAPE
    from pptx.dml.color import RGBColor
    from pptx.util import Inches
    from pptx.enum.text import PP_ALIGN

    prs = Presentation(pptx_path)
    sw = prs.slide_width; sh = prs.slide_height
    count = 0
    for slide, shapes in zip(prs.slides, configs or []):
        for s in shapes or []:
            kind = s.get("kind", "rect")
            x = float(s.get("x", 10)) / 100 * sw
            y = float(s.get("y", 10)) / 100 * sh
            w = float(s.get("w", 30)) / 100 * sw
            h = float(s.get("h", 15)) / 100 * sh
            mso = {"ellipse": MSO_SHAPE.OVAL, "arrow": MSO_SHAPE.RIGHT_ARROW}.get(
                kind, MSO_SHAPE.RECTANGLE
            )
            shape = slide.shapes.add_shape(mso, x, y, w, h)
            try:
                shape.fill.solid()
                hex_fill = str(s.get("fill", "#FFF3E0")).lstrip("#")
                shape.fill.fore_color.rgb = RGBColor.from_string(hex_fill)
                shape.line.color.rgb = RGBColor.from_string(
                    str(s.get("line", "#E67E22")).lstrip("#")
                )
            except Exception:
                pass
            if kind in ("text", "art"):
                shape.text = str(s.get("text", ""))
                shape.text_frame.paragraphs[0].alignment = PP_ALIGN.CENTER
            try:
                shape.rotation = float(s.get("rotation", 0) or 0)
            except Exception:
                pass
            count += 1
    prs.save(pptx_path)
    return count


def get_native_shape_edit_js(count: int) -> str:
    """拖拽/Alt+拖拽旋转原生形状的注入脚本。"""
    return r"""
<script>
(function(){
  if (window.__beeNativeShapeEdit) return;
  window.__beeNativeShapeEdit = true;
  const slide = document.querySelector('.slide');
  if (!slide) return;
  const items = Array.from(document.querySelectorAll('.native-shapes > div'));
  const snap = (v) => Math.round(v / 5) * 5;
  items.forEach((el, idx) => {
    el.style.pointerEvents = 'auto';
    el.style.cursor = 'move';
    el.dataset.nativeIndex = idx;
    let state = null;
    el.addEventListener('mousedown', (e) => {
      e.preventDefault(); e.stopPropagation();
      const box = slide.getBoundingClientRect();
      state = {box, startX: e.clientX, startY: e.clientY,
               left: parseFloat(el.style.left) || 0,
               top: parseFloat(el.style.top) || 0,
               rot: parseFloat((el.style.transform.match(/rotate\(([-\d.]+)deg\)/) || [0,0])[1]) || 0,
               rotate: e.altKey};
    });
    window.addEventListener('mousemove', (e) => {
      if (!state) return;
      if (state.rotate) {
        const cx = state.box.left + state.box.width / 2;
        const cy = state.box.top + state.box.height / 2;
        let ang = Math.atan2(e.clientY - cy, e.clientX - cx) * 180 / Math.PI + 90;
        el.style.transform = `rotate(${ang}deg)`;
        state.angle = ang;
      } else {
        el.style.left = (state.left + (e.clientX - state.startX) / state.box.width * 100) + '%';
        el.style.top = (state.top + (e.clientY - state.startY) / state.box.height * 100) + '%';
      }
    });
    window.addEventListener('mouseup', () => {
      if (!state) return;
      const done = state; state = null;
      const payload = {
        index: idx,
        x: snap(parseFloat(el.style.left) || 0),
        y: snap(parseFloat(el.style.top) || 0),
        w: parseFloat(el.style.width) || 30,
        h: parseFloat(el.style.height) || 15,
        rotation: done.angle || done.rot
      };
      window.location.href = 'beeoffice://native-shape-edit?data=' + encodeURIComponent(JSON.stringify(payload));
    });
    // 四角缩放手柄
    [['nw', -5, -5], ['ne', 100, -5], ['sw', -5, 100], ['se', 100, 100]].forEach(([dir, hx, hy]) => {
      const h = document.createElement('div');
      h.className = 'bee-shape-handle';
      h.style.cssText = `position:absolute;left:${hx}%;top:${hy}%;width:10px;height:10px;` +
        `background:#fff;border:1px solid #E67E22;border-radius:2px;z-index:9999;cursor:${dir}-resize;transform:translate(-50%,-50%);`;
      h.addEventListener('mousedown', (ev) => {
        ev.preventDefault(); ev.stopPropagation();
        const box = slide.getBoundingClientRect();
        const start = { x: ev.clientX, y: ev.clientY,
          w: parseFloat(el.style.width) || 30, h: parseFloat(el.style.height) || 15,
          left: parseFloat(el.style.left) || 0, top: parseFloat(el.style.top) || 0 };
        const move = (e2) => {
          const dx = (e2.clientX - start.x) / box.width * 100;
          const dy = (e2.clientY - start.y) / box.height * 100;
          let nw = start.w, nh = start.h, nl = start.left, nt = start.top;
          if (dir.includes('e')) nw = Math.max(5, start.w + dx);
          if (dir.includes('s')) nh = Math.max(5, start.h + dy);
          if (dir.includes('w')) { nw = Math.max(5, start.w - dx); nl = start.left + dx; }
          if (dir.includes('n')) { nh = Math.max(5, start.h - dy); nt = start.top + dy; }
          el.style.width = snap(nw) + '%'; el.style.height = snap(nh) + '%';
          el.style.left = snap(nl) + '%'; el.style.top = snap(nt) + '%';
        };
        const up = () => {
          window.removeEventListener('mousemove', move);
          window.removeEventListener('mouseup', up);
          const payload = {index: idx, x: snap(parseFloat(el.style.left) || 0),
            y: snap(parseFloat(el.style.top) || 0),
            w: snap(parseFloat(el.style.width) || 30),
            h: snap(parseFloat(el.style.height) || 15), rotation: 0};
          window.location.href = 'beeoffice://native-shape-edit?data=' + encodeURIComponent(JSON.stringify(payload));
        };
        window.addEventListener('mousemove', move);
        window.addEventListener('mouseup', up);
      });
      el.appendChild(h);
    });
  });
})();
</script>
"""
