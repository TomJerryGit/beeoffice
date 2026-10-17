# beeoffice/plugins/beeshow_image_editor.py
"""
蜜演图片拖拽编辑（任务 2.3）

功能：
  在预览区拖拽调整图片的大小和位置，拖拽结束后写回 Markdown。

对标：
  - WPS 演示的元素自由移动和编辑

设计：
  - 复用任务 2.2 的元素选中框架
  - 对 <img> 特殊处理：显示 8 个缩放手柄 + 拖动主体
  - 拖拽结束通过 beeoffice://image-edit?data=... 回传
  - Python 端解析并写入 <!-- beeoffice-image: {...} --> 注释
  - _md_to_html 后处理应用图片样式

存储格式：
  <!-- beeoffice-image: {"path": ".slide > img:nth-of-type(1)",
                          "x": 100, "y": 200, "w": 400, "h": 300,
                          "align": "left"} -->

  - path   : DOM 路径（与 beeoffice-style 同机制）
  - x, y   : 相对幻灯片左上角的偏移（px），None 表示自动
  - w, h   : 宽高（px），None 表示原图尺寸
  - align  : "left" / "center" / "right"，当 x 为 None 时生效

依赖：
  - json / logging / urllib.parse
  - PySide6（无）

注意：
  - 不导入其他 beeshow_* Mixin
  - 拖拽时坐标使用归一化值（0.0~1.0）避免窗口缩放误差
  - 存储时转回像素值
"""

import json
import logging
import re
from typing import Dict, Any, Optional


# ==================== JS 生成器 ====================
def get_image_editor_js() -> str:
    """
    返回图片拖拽编辑的 JS 脚本。

    在任务 2.2 的 element_editor_js 之后注入。

    JS 逻辑：
      1. 为 .slide 内每个 <img> 打标记
      2. 点击图片 → 显示 8 个缩放手柄 + 可拖动主体
      3. 拖动主体 → 移动图片
      4. 拖动手柄 → 缩放图片（保持宽高比可选）
      5. 松开鼠标 → 通过 beeoffice:// 协议回传
      6. 显示对齐工具栏（左/中/右/重置）
    """
    return r"""
<script>
(function() {
    'use strict';

    // ==================== 配置 ====================
    const HANDLE_SIZE = 10;
    const MIN_SIZE = 30;

    // ==================== 状态 ====================
    let selectedImg = null;
    let handleLayer = null;
    let alignBar = null;
    let dragState = null;  // {mode, startX, startY, startRect, handle}

    // ==================== 打标记 ====================
    function markImages() {
        const slide = document.querySelector('.slide');
        if (!slide) return;

        slide.querySelectorAll('img').forEach(img => {
            // 跳过已打标的
            if (img.dataset.imageEditable === '1') return;
            img.dataset.imageEditable = '1';
            img.style.cursor = 'move';
            img.style.transition = 'outline 0.15s';
            // 让图片本身支持绝对定位
            if (getComputedStyle(img).position === 'static') {
                img.style.position = 'relative';
            }
        });
    }

    // ==================== 选中图片 ====================
    function selectImage(img) {
        clearSelection();
        selectedImg = img;

        // 高亮边框
        img.style.outline = '2px solid #2196F3';
        img.style.outlineOffset = '2px';

        // 显示缩放手柄
        showHandles(img);
        // 显示对齐栏
        showAlignBar(img);
    }

    function clearSelection() {
        if (selectedImg) {
            selectedImg.style.outline = '';
            selectedImg.style.outlineOffset = '';
            selectedImg = null;
        }
        hideHandles();
        hideAlignBar();
    }

    // ==================== 缩放手柄 ====================
    function showHandles(img) {
        hideHandles();

        handleLayer = document.createElement('div');
        handleLayer.id = 'beeoffice-image-handles';
        handleLayer.style.cssText = `
            position: fixed;
            z-index: 99998;
            pointer-events: none;
        `;
        document.body.appendChild(handleLayer);

        const rect = img.getBoundingClientRect();
        const positions = [
            ['nw', 0, 0], ['n', 0.5, 0], ['ne', 1, 0],
            ['w', 0, 0.5],               ['e', 1, 0.5],
            ['sw', 0, 1], ['s', 0.5, 1], ['se', 1, 1],
        ];

        positions.forEach(([pos, rx, ry]) => {
            const handle = document.createElement('div');
            handle.dataset.handle = pos;
            const x = rect.left + rect.width * rx - HANDLE_SIZE / 2;
            const y = rect.top + rect.height * ry - HANDLE_SIZE / 2;
            handle.style.cssText = `
                position: fixed;
                left: ${x}px;
                top: ${y}px;
                width: ${HANDLE_SIZE}px;
                height: ${HANDLE_SIZE}px;
                background: #2196F3;
                border: 1px solid #FFF;
                border-radius: 2px;
                cursor: ${getCursor(pos)};
                pointer-events: auto;
                z-index: 99999;
            `;
            handle.onmousedown = function(e) {
                e.preventDefault();
                e.stopPropagation();
                startDrag(e, img, pos);
            };
            handleLayer.appendChild(handle);
        });

        // 主体拖动
        img.onmousedown = function(e) {
            if (e.target !== img) return;
            e.preventDefault();
            e.stopPropagation();
            startDrag(e, img, 'move');
        };
    }

    function hideHandles() {
        if (handleLayer) {
            handleLayer.remove();
            handleLayer = null;
        }
        if (selectedImg) {
            selectedImg.onmousedown = null;
        }
    }

    function getCursor(pos) {
        const cursors = {
            nw: 'nwse-resize', ne: 'nesw-resize',
            sw: 'nesw-resize', se: 'nwse-resize',
            n: 'ns-resize', s: 'ns-resize',
            w: 'ew-resize', e: 'ew-resize',
            move: 'move',
        };
        return cursors[pos] || 'default';
    }

    // ==================== 拖拽 ====================
    function startDrag(e, img, handle) {
        const rect = img.getBoundingClientRect();
        dragState = {
            mode: handle,
            startX: e.clientX,
            startY: e.clientY,
            startLeft: rect.left,
            startTop: rect.top,
            startW: rect.width,
            startH: rect.height,
            img: img,
        };
        document.addEventListener('mousemove', onDrag);
        document.addEventListener('mouseup', endDrag);
    }

    function onDrag(e) {
        if (!dragState) return;
        const dx = e.clientX - dragState.startX;
        const dy = e.clientY - dragState.startY;

        let newLeft = dragState.startLeft;
        let newTop = dragState.startTop;
        let newW = dragState.startW;
        let newH = dragState.startH;

        const mode = dragState.mode;
        if (mode === 'move') {
            newLeft += dx;
            newTop += dy;
        } else {
            // 根据 handle 方向缩放
            if (mode.includes('e')) {
                newW = Math.max(MIN_SIZE, dragState.startW + dx);
            }
            if (mode.includes('w')) {
                newW = Math.max(MIN_SIZE, dragState.startW - dx);
                newLeft = dragState.startLeft + dx;
            }
            if (mode.includes('s')) {
                newH = Math.max(MIN_SIZE, dragState.startH + dy);
            }
            if (mode.includes('n')) {
                newH = Math.max(MIN_SIZE, dragState.startH - dy);
                newTop = dragState.startTop + dy;
            }
        }

        // 应用（用 fixed 坐标直接设置）
        dragState.img.style.position = 'fixed';
        dragState.img.style.left = newLeft + 'px';
        dragState.img.style.top = newTop + 'px';
        dragState.img.style.width = newW + 'px';
        dragState.img.style.height = newH + 'px';
        dragState.img.style.margin = '0';

        // 更新手柄位置
        updateHandlesPosition();
    }

    function updateHandlesPosition() {
        if (!handleLayer || !dragState) return;
        const img = dragState.img;
        const rect = img.getBoundingClientRect();
        const positions = [
            ['nw', 0, 0], ['n', 0.5, 0], ['ne', 1, 0],
            ['w', 0, 0.5],               ['e', 1, 0.5],
            ['sw', 0, 1], ['s', 0.5, 1], ['se', 1, 1],
        ];
        const handles = handleLayer.querySelectorAll('[data-handle]');
        positions.forEach(([pos, rx, ry], i) => {
            if (i >= handles.length) return;
            const h = handles[i];
            const x = rect.left + rect.width * rx - HANDLE_SIZE / 2;
            const y = rect.top + rect.height * ry - HANDLE_SIZE / 2;
            h.style.left = x + 'px';
            h.style.top = y + 'px';
        });
    }

    function endDrag() {
        document.removeEventListener('mousemove', onDrag);
        document.removeEventListener('mouseup', endDrag);
        if (dragState) {
            // 转换回幻灯片坐标系
            finalizeImagePosition(dragState.img);
            dragState = null;
        }
    }

    // ==================== 应用位置 ====================
    function finalizeImagePosition(img) {
        // 恢复为相对定位
        img.style.position = 'relative';
        const slide = document.querySelector('.slide');
        if (!slide) return;
        const slideRect = slide.getBoundingClientRect();
        const imgRect = img.getBoundingClientRect();

        // 归一化（相对幻灯片）
        const x = imgRect.left - slideRect.left;
        const y = imgRect.top - slideRect.top;
        const w = imgRect.width;
        const h = imgRect.height;

        // 转回相对定位（在 .slide 内）
        img.style.left = '';
        img.style.top = '';
        img.style.margin = '';
        // 用 margin-left 模拟偏移
        img.style.display = 'block';
        img.style.marginLeft = x + 'px';
        img.style.marginTop = y + 'px';
        img.style.width = w + 'px';
        img.style.height = h + 'px';
    }

    // ==================== 对齐栏 ====================
    function showAlignBar(img) {
        hideAlignBar();

        alignBar = document.createElement('div');
        alignBar.id = 'beeoffice-image-alignbar';
        alignBar.style.cssText = `
            position: fixed;
            background: #FFF;
            border: 1px solid #DDD;
            border-radius: 6px;
            padding: 6px 8px;
            box-shadow: 0 4px 12px rgba(0,0,0,0.15);
            z-index: 99999;
            display: flex;
            gap: 6px;
            align-items: center;
            font-size: 13px;
            font-family: -apple-system, sans-serif;
        `;

        // 对齐按钮
        const aligns = [
            ['⬅ 左', 'left'], ['↔ 中', 'center'], ['➡ 右', 'right'],
        ];
        aligns.forEach(([label, align]) => {
            const btn = document.createElement('button');
            btn.textContent = label;
            btn.style.cssText = `
                padding: 3px 8px;
                border: 1px solid #DDD; border-radius: 3px;
                background: #FFF; cursor: pointer;
                font-size: 12px;
            `;
            btn.onclick = function() {
                applyAlign(img, align);
            };
            alignBar.appendChild(btn);
        });

        // 分隔
        const sep = document.createElement('span');
        sep.style.cssText = 'width: 1px; height: 18px; background: #DDD;';
        alignBar.appendChild(sep);

        // 重置按钮
        const resetBtn = document.createElement('button');
        resetBtn.textContent = '↺ 重置';
        resetBtn.style.cssText = `
            padding: 3px 8px;
            border: 1px solid #DDD; border-radius: 3px;
            background: #FFF; cursor: pointer;
            font-size: 12px;
        `;
        resetBtn.onclick = function() {
            resetImage(img);
        };
        alignBar.appendChild(resetBtn);

        // 应用按钮
        const applyBtn = document.createElement('button');
        applyBtn.textContent = '✅ 应用';
        applyBtn.style.cssText = `
            padding: 3px 10px;
            background: #2196F3; color: #FFF;
            border: none; border-radius: 3px;
            font-weight: bold; cursor: pointer;
            font-size: 12px;
        `;
        applyBtn.onclick = function() {
            applyImageChanges(img);
        };
        alignBar.appendChild(applyBtn);

        // 取消
        const cancelBtn = document.createElement('button');
        cancelBtn.textContent = '✕';
        cancelBtn.style.cssText = `
            width: 24px; height: 24px;
            border: 1px solid #DDD; border-radius: 3px;
            background: #FFF; cursor: pointer;
        `;
        cancelBtn.onclick = clearSelection;
        alignBar.appendChild(cancelBtn);

        document.body.appendChild(alignBar);
        positionAlignBar(img);
    }

    function hideAlignBar() {
        if (alignBar) {
            alignBar.remove();
            alignBar = null;
        }
    }

    function positionAlignBar(img) {
        if (!alignBar) return;
        const rect = img.getBoundingClientRect();
        const barRect = alignBar.getBoundingClientRect();
        let top = rect.top - barRect.height - 40;
        if (top < 10) top = rect.bottom + 8;
        let left = rect.left + rect.width / 2 - barRect.width / 2;
        left = Math.max(10, Math.min(left,
            window.innerWidth - barRect.width - 10));
        alignBar.style.top = top + 'px';
        alignBar.style.left = left + 'px';
    }

    // ==================== 对齐 / 重置 ====================
    function applyAlign(img, align) {
        img.style.display = 'block';
        img.style.marginLeft = '';
        img.style.marginRight = '';
        img.style.marginTop = '';
        if (align === 'left') {
            img.style.marginLeft = '0';
            img.style.marginRight = 'auto';
        } else if (align === 'center') {
            img.style.marginLeft = 'auto';
            img.style.marginRight = 'auto';
        } else if (align === 'right') {
            img.style.marginLeft = 'auto';
            img.style.marginRight = '0';
        }
        // 更新手柄
        updateHandlesPosition();
        positionAlignBar(img);
    }

    function resetImage(img) {
        img.style.width = '';
        img.style.height = '';
        img.style.margin = '';
        img.style.display = '';
        updateHandlesPosition();
        positionAlignBar(img);
    }

    // ==================== 应用修改 ====================
    function applyImageChanges(img) {
        const slide = document.querySelector('.slide');
        if (!slide) return;
        const slideRect = slide.getBoundingClientRect();
        const imgRect = img.getBoundingClientRect();

        const cs = window.getComputedStyle(img);

        // 归一化坐标
        const x = imgRect.left - slideRect.left;
        const y = imgRect.top - slideRect.top;
        const w = imgRect.width;
        const h = imgRect.height;

        // 判断对齐
        let align = 'left';
        if (cs.marginLeft === 'auto' && cs.marginRight === 'auto') {
            align = 'center';
        } else if (cs.marginLeft === 'auto') {
            align = 'right';
        }

        const path = getElementPath(img);
        const payload = {
            path: path,
            x: Math.round(x),
            y: Math.round(y),
            w: Math.round(w),
            h: Math.round(h),
            align: align,
        };

        // 回传 Python
        try {
            const encoded = encodeURIComponent(JSON.stringify(payload));
            window.location.href = 'beeoffice://image-edit?data=' + encoded;
        } catch (e) {
            console.error('回传失败：', e);
        }

        clearSelection();
    }

    function getElementPath(el) {
        const path = [];
        let current = el;
        while (current && current !== document.body) {
            let selector = current.tagName.toLowerCase();
            if (current.parentElement) {
                const siblings = Array.from(
                    current.parentElement.children
                ).filter(c => c.tagName === current.tagName);
                if (siblings.length > 1) {
                    const idx = siblings.indexOf(current) + 1;
                    selector += ':nth-of-type(' + idx + ')';
                }
            }
            path.unshift(selector);
            current = current.parentElement;
        }
        return path.join(' > ');
    }

    // ==================== 事件绑定 ====================
    function init() {
        markImages();

        // 点击图片进入编辑
        document.addEventListener('click', function(e) {
            if (e.target.closest('#beeoffice-image-alignbar')) return;
            if (e.target.closest('#beeoffice-image-handles')) return;

            const img = e.target.closest('img[data-image-editable="1"]');
            if (img) {
                e.stopPropagation();
                selectImage(img);
                return;
            }

            // 点击非图片，清空（除非是 2.2 的文本工具栏）
            if (!e.target.closest('#beeoffice-element-toolbar')) {
                if (selectedImg && !e.target.closest('img')) {
                    clearSelection();
                }
            }
        }, true);

        // ESC 取消
        document.addEventListener('keydown', function(e) {
            if (e.key === 'Escape') {
                clearSelection();
            }
        });

        // 窗口变化时更新手柄
        window.addEventListener('resize', function() {
            if (selectedImg) {
                updateHandlesPosition();
                positionAlignBar(selectedImg);
            }
        });
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }

    // 供外部调用
    window.beeofficeClearImageSelection = clearSelection;

})();
</script>
"""


# ==================== URL 解析 ====================
def parse_image_edit_url(url: str) -> Optional[Dict[str, Any]]:
    """
    解析 beeoffice://image-edit?data=... 的 URL。

    :param url: 完整 URL
    :return: {"path": ..., "x": ..., "y": ..., "w": ..., "h": ..., "align": ...}
             或 None
    """
    try:
        if not url.startswith("beeoffice://image-edit"):
            return None

        import urllib.parse
        query = url.split("?", 1)[1] if "?" in url else ""
        params = urllib.parse.parse_qs(query)
        data_str = params.get("data", [""])[0]
        if not data_str:
            return None

        return json.loads(urllib.parse.unquote(data_str))
    except Exception as e:
        logging.error(f"解析图片编辑 URL 失败：{e}")
        return None


# ==================== Markdown 图片信息存取 ====================
class MarkdownImagePatcher:
    """
    在 Markdown 中存取图片位置/尺寸信息。

    存储格式：
      <!-- beeoffice-image: {"path": ".slide > img:nth-of-type(1)",
                              "x": 100, "y": 200, "w": 400, "h": 300,
                              "align": "left"} -->
    """

    IMAGE_COMMENT_PREFIX = "beeoffice-image:"
    PATTERN = re.compile(
        r'<!--\s*beeoffice-image:\s*(\{.*?\})\s*-->',
        re.DOTALL,
    )

    @classmethod
    def extract_images(
        cls, md_text: str
    ) -> Dict[str, Dict[str, Any]]:
        """
        从 Markdown 提取所有图片信息。

        :param md_text: Markdown 原文
        :return: {path: {x, y, w, h, align}}
        """
        result = {}
        for m in cls.PATTERN.finditer(md_text):
            try:
                data = json.loads(m.group(1))
                if isinstance(data, dict):
                    path = data.get("path", "")
                    if path:
                        result[path] = {
                            "x": data.get("x"),
                            "y": data.get("y"),
                            "w": data.get("w"),
                            "h": data.get("h"),
                            "align": data.get("align", "left"),
                        }
            except Exception:
                continue
        return result

    @classmethod
    def upsert_image(
        cls,
        md_text: str,
        path: str,
        image_info: Dict[str, Any],
    ) -> str:
        """
        更新或插入图片信息。

        :param md_text: Markdown 原文
        :param path: 元素路径
        :param image_info: {"x", "y", "w", "h", "align"}
        :return: 更新后的 Markdown
        """
        data = {"path": path}
        data.update(image_info)
        new_comment = (
            f"<!-- beeoffice-image: "
            f"{json.dumps(data, ensure_ascii=False)} -->"
        )

        found = False
        result_parts = []
        last_end = 0

        for m in cls.PATTERN.finditer(md_text):
            try:
                existing = json.loads(m.group(1))
                if existing.get("path") == path:
                    result_parts.append(md_text[last_end:m.start()])
                    result_parts.append(new_comment)
                    last_end = m.end()
                    found = True
            except Exception:
                continue

        result_parts.append(md_text[last_end:])
        result = "".join(result_parts)

        if not found:
            result = result.rstrip() + "\n" + new_comment + "\n"

        return result

    @classmethod
    def apply_images_to_html(
        cls, html: str, images_map: Dict[str, Dict[str, Any]]
    ) -> str:
        """
        把图片信息应用到渲染后的 HTML。

        :param html: 渲染后的 HTML 片段
        :param images_map: {path: {x, y, w, h, align}}
        :return: 应用后的 HTML
        """
        if not images_map:
            return html

        try:
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(html, "html.parser")

            for path, info in images_map.items():
                img = cls._find_img_by_path(soup, path)
                if img is None:
                    continue

                css_parts = ["display: block"]

                # 宽高
                if info.get("w"):
                    css_parts.append(f"width: {info['w']}px")
                if info.get("h"):
                    css_parts.append(f"height: {info['h']}px")

                # 位置（用 margin 模拟）
                if info.get("x") is not None:
                    css_parts.append(f"margin-left: {info['x']}px")
                else:
                    # 无 x，用 align
                    align = info.get("align", "left")
                    if align == "left":
                        css_parts.append("margin-left: 0")
                        css_parts.append("margin-right: auto")
                    elif align == "center":
                        css_parts.append("margin-left: auto")
                        css_parts.append("margin-right: auto")
                    elif align == "right":
                        css_parts.append("margin-left: auto")
                        css_parts.append("margin-right: 0")

                if info.get("y") is not None:
                    css_parts.append(f"margin-top: {info['y']}px")

                existing = img.get("style", "")
                img["style"] = existing + "; " + "; ".join(css_parts)

            return str(soup)
        except ImportError:
            logging.warning("bs4 未安装，图片样式应用跳过")
            return html
        except Exception as e:
            logging.error(f"应用图片样式失败：{e}")
            return html

    @staticmethod
    def _find_img_by_path(soup, path: str):
        """
        根据路径查找 <img> 元素。

        :param soup: BeautifulSoup 对象
        :param path: 元素路径（如 ".slide > img:nth-of-type(1)"）
        :return: Tag 或 None
        """
        try:
            parts = [p.strip() for p in path.split(">") if p.strip()]
            root = soup.find(class_="slide")
            if root is None:
                root = soup

            current = root
            for part in parts:
                if part.startswith(".slide"):
                    continue

                m = re.match(
                    r"([a-zA-Z]+)(?::nth-of-type\((\d+)\))?",
                    part,
                )
                if not m:
                    return None
                tag = m.group(1).lower()
                idx = int(m.group(2)) if m.group(2) else 1

                if tag != "img":
                    # 只处理 img
                    siblings = current.find_all(tag)
                    if not siblings or idx > len(siblings):
                        return None
                    current = siblings[idx - 1]
                else:
                    siblings = current.find_all("img")
                    if not siblings or idx > len(siblings):
                        return None
                    return siblings[idx - 1]

            return current if current.name == "img" else None
        except Exception as e:
            logging.debug(f"查找图片失败 {path}：{e}")
            return None