"""BeeShow 画布编辑 JS：拖动/缩放/删除元素，通过自定义协议回传。"""
from __future__ import annotations

import json


def get_canvas_edit_js(overrides=None, deleted=None) -> str:
    """生成注入脚本；overrides 为 {index: {left,top,width,height}}。"""
    data = json.dumps(overrides or {})
    gone = json.dumps(deleted or [])
    return r"""
<script>
(function() {
  if (window.__beeCanvasInstalled) return;
  window.__beeCanvasInstalled = true;
  const overrides = __OVERRIDES__;
  const deleted = new Set(__DELETED__);
  const slide = document.querySelector('.slide');
  if (!slide) return;
  const items = Array.from(slide.querySelectorAll('[data-editable], img'));
  items.forEach((el, i) => {
    el.dataset.beeIndex = i;
    el.style.touchAction = 'none';
    if (deleted.has(i)) el.style.display = 'none';
    const ov = overrides[i];
    if (ov) {
      if (ov.left || ov.top) {
        el.style.transform = `translate(${ov.left || 0}px, ${ov.top || 0}px)`;
      }
      if (ov.width) el.style.width = ov.width + 'px';
      if (ov.height) el.style.height = ov.height + 'px';
    }
  });
  let drag = null;
  function send(kind, payload) {
    const encoded = encodeURIComponent(JSON.stringify(payload));
    window.location.href = 'beeoffice://' + kind + '?data=' + encoded;
  }
  slide.addEventListener('mousedown', (e) => {
    const el = e.target.closest('[data-editable], img');
    if (!el || !slide.contains(el)) return;
    const idx = parseInt(el.dataset.beeIndex || '-1');
    if (idx < 0) return;
    drag = { el, idx, x: e.clientX, y: e.clientY,
             left: parseFloat(el.dataset.beeLeft || '0'),
             top: parseFloat(el.dataset.beeTop || '0') };
    e.preventDefault();
  });
  slide.addEventListener('mousemove', (e) => {
    if (!drag) return;
    const dx = e.clientX - drag.x, dy = e.clientY - drag.y;
    if (Math.abs(dx) + Math.abs(dy) < 2) return;
    drag.moved = true;
    drag.el.style.transform = `translate(${drag.left + dx}px, ${drag.top + dy}px)`;
  });
  slide.addEventListener('mouseup', (e) => {
    if (!drag) return;
    const current = drag; drag = null;
    if (!current.moved) return;
    const dx = e.clientX - current.x, dy = e.clientY - current.y;
    current.el.dataset.beeLeft = String(current.left + dx);
    current.el.dataset.beeTop = String(current.top + dy);
    send('canvas-edit', {
      index: current.idx,
      left: current.left + dx,
      top: current.top + dy,
      width: current.el.offsetWidth,
      height: current.el.offsetHeight,
    });
  });
  // Alt+滚轮缩放选中元素
  slide.addEventListener('wheel', (e) => {
    if (!e.altKey) return;
    const el = e.target.closest('[data-editable], img');
    if (!el) return;
    e.preventDefault();
    const idx = parseInt(el.dataset.beeIndex || '-1');
    const w = Math.max(40, el.offsetWidth + (e.deltaY > 0 ? -20 : 20));
    el.style.width = w + 'px';
    send('canvas-edit', {index: idx, left: parseFloat(el.dataset.beeLeft || '0'), top: parseFloat(el.dataset.beeTop || '0'), width: w, height: el.offsetHeight});
  }, {passive: false});
  // Delete 删除当前悬停元素
  document.addEventListener('keydown', (e) => {
    if (e.key !== 'Delete') return;
    const el = document.activeElement || document.querySelector(':hover');
    if (el && el.dataset && el.dataset.beeIndex !== undefined) {
      send('canvas-delete', {index: parseInt(el.dataset.beeIndex)});
    }
  });
})();
</script>
""".replace("__OVERRIDES__", data).replace("__DELETED__", gone)
