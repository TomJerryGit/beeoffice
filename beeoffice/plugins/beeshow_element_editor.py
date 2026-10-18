# beeoffice/plugins/beeshow_element_editor.py
"""
蜜演预览区元素级操作（任务 2.2 + 任务 2.3）

功能：
  在预览区点击选中元素，弹出小工具栏修改样式，修改同步回 Markdown。

对标：
  - WPS 演示的 WYSIWYG 编辑体验

v5.1 增量汇总：
  - 任务 2.2：本模块整体（元素点击 + 工具栏 + 样式持久化）
              * markEditableElements 跳过 <img>（由 ImageEditor 处理）
              * MarkdownStylePatcher.apply_styles_to_html 跳过 <img>
  - 任务 2.3：追加 BeeOfficeWebEnginePage 类
              * _handle_beeoffice_url 里加 beeoffice://image-edit 分支
              * 用于拦截图片拖拽编辑的回调

设计：
  - 在 _show_slide 渲染的 HTML 中注入一段 JS
  - JS 监听 .slide 内元素的点击，高亮选中
  - 弹出 HTML 浮动工具栏（改颜色/字号/对齐/加粗/斜体）
  - 用户点"应用"时通过 beeoffice:// 协议回调 Python
  - Python 端解析修改，更新对应 Markdown 行，重新渲染

通信方式：
  - JS 通过 window.location.href = "beeoffice://element-edit?..."
  - BeeOfficeWebEnginePage 重写 acceptNavigationRequest 拦截自定义协议
  - 解析参数后转发给 owner（BeeShowView）

注意：
  - 不导入其他 beeshow_* Mixin
  - 修改仅作用于"普通文本块"，图片由 beeshow_image_editor 处理
  - 所有修改持久化到 Markdown 源（HTML 注释形式存储样式覆盖）
"""

import json
import logging
import urllib.parse
from typing import Dict, Any, Optional
from beeoffice.i18n import tr


# ==================== JS 生成器 ====================
def get_element_editor_js() -> str:
    """
    返回元素编辑器的 JS 脚本。

    注入到 _show_slide 渲染的 HTML 里。

    JS 逻辑：
      1. 为 .slide 内每个"可编辑元素"打标记（h1~h6/p/li/blockquote）
         注意：跳过 <img>（由 ImageEditor 处理，任务 2.3）
      2. 监听点击 → 高亮选中
      3. 弹出 HTML 浮动工具栏（改颜色/字号/对齐/加粗/斜体）
      4. 点"应用"→ 通过 beeoffice:// 协议回传修改
      5. 按 ESC / 点击空白 → 取消选中
    """
    return r"""
<script>
(function() {
    'use strict';

    // ==================== 配置 ====================
    const EDITABLE_TAGS = [
        'h1', 'h2', 'h3', 'h4', 'h5', 'h6',
        'p', 'li', 'blockquote', 'td', 'th'
    ];

    // ==================== 状态 ====================
    let selectedEl = null;
    let toolbar = null;

    // ==================== 打标记 ====================
    function markEditableElements() {
        const slide = document.querySelector('.slide');
        if (!slide) return;

        slide.querySelectorAll(EDITABLE_TAGS.join(',')).forEach(el => {
            if (el.closest('.dynamic-number')) return;
            if (el.closest('.video-placeholder')) return;
            // 任务 2.3：跳过 img（由图片编辑器处理）
            if (el.tagName === 'IMG') return;
            el.dataset.editable = '1';
            el.style.cursor = 'pointer';
            el.style.transition = 'outline 0.15s';
        });
    }

    // ==================== 选中 ====================
    function selectElement(el) {
        clearSelection();
        selectedEl = el;

        // 高亮边框
        el.style.outline = '2px solid #FFB300';
        el.style.outlineOffset = '2px';

        // 显示工具栏
        showToolbar(el);
    }

    function clearSelection() {
        if (selectedEl) {
            selectedEl.style.outline = '';
            selectedEl.style.outlineOffset = '';
            selectedEl = null;
        }
        hideToolbar();
    }

    // ==================== 工具栏 ====================
    function showToolbar(el) {
        hideToolbar();

        toolbar = document.createElement('div');
        toolbar.id = 'beeoffice-element-toolbar';
        toolbar.style.cssText = `
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

        // 读取当前样式
        const cs = window.getComputedStyle(el);

        // ---- 加粗 ----
        toolbar.appendChild(makeToggleBtn('B', 'bold',
            parseInt(cs.fontWeight) >= 600,
            function(active) {
                el.style.fontWeight = active ? 'bold' : 'normal';
            }
        ));

        // ---- 斜体 ----
        toolbar.appendChild(makeToggleBtn('I', 'italic',
            cs.fontStyle === 'italic',
            function(active) {
                el.style.fontStyle = active ? 'italic' : 'normal';
            }
        ));

        // ---- 下划线 ----
        toolbar.appendChild(makeToggleBtn('U', 'underline',
            cs.textDecorationLine.includes('underline'),
            function(active) {
                el.style.textDecoration = active ? 'underline' : 'none';
            }
        ));

        // ---- 分隔 ----
        toolbar.appendChild(makeSeparator());

        // ---- 字号 ----
        const sizeInput = document.createElement('input');
        sizeInput.type = 'number';
        sizeInput.value = parseInt(cs.fontSize) || 18;
        sizeInput.min = 10;
        sizeInput.max = 120;
        sizeInput.style.cssText = `
            width: 48px; padding: 2px 4px;
            border: 1px solid #DDD; border-radius: 3px;
            font-size: 12px;
        `;
        sizeInput.onchange = function() {
            el.style.fontSize = sizeInput.value + 'px';
        };
        toolbar.appendChild(sizeInput);

        // ---- 颜色 ----
        const colorInput = document.createElement('input');
        colorInput.type = 'color';
        colorInput.value = rgbToHex(cs.color);
        colorInput.style.cssText = `
            width: 32px; height: 26px;
            border: 1px solid #DDD; border-radius: 3px;
            padding: 0; cursor: pointer;
        `;
        colorInput.onchange = function() {
            el.style.color = colorInput.value;
        };
        toolbar.appendChild(colorInput);

        // ---- 背景色 ----
        const bgInput = document.createElement('input');
        bgInput.type = 'color';
        bgInput.value = rgbToHex(cs.backgroundColor) || '#ffffff';
        bgInput.style.cssText = `
            width: 32px; height: 26px;
            border: 1px solid #DDD; border-radius: 3px;
            padding: 0; cursor: pointer;
        `;
        bgInput.title = '背景色';
        bgInput.onchange = function() {
            el.style.backgroundColor = bgInput.value;
        };
        toolbar.appendChild(bgInput);

        // ---- 分隔 ----
        toolbar.appendChild(makeSeparator());

        // ---- 对齐 ----
        const aligns = [
            ['⬅', 'left'], ['↔', 'center'], ['➡', 'right'],
        ];
        aligns.forEach(([icon, align]) => {
            const btn = document.createElement('button');
            btn.textContent = icon;
            btn.title = align;
            btn.style.cssText = `
                width: 26px; height: 26px;
                border: 1px solid #DDD; border-radius: 3px;
                background: ${cs.textAlign === align ? '#FFE0A0' : '#FFF'};
                cursor: pointer; font-size: 13px;
            `;
            btn.onclick = function() {
                el.style.textAlign = align;
                toolbar.querySelectorAll('button[title]').forEach(b => {
                    if (['left','center','right'].includes(b.title)) {
                        b.style.background = b.title === align
                            ? '#FFE0A0' : '#FFF';
                    }
                });
            };
            toolbar.appendChild(btn);
        });

        // ---- 分隔 ----
        toolbar.appendChild(makeSeparator());

        // ---- 应用按钮 ----
        const applyBtn = document.createElement('button');
        applyBtn.textContent = '✅ 应用';
        applyBtn.style.cssText = `
            padding: 3px 10px;
            background: #FFB300; color: #000;
            border: none; border-radius: 3px;
            font-weight: bold; cursor: pointer;
            font-size: 12px;
        `;
        applyBtn.onclick = function() {
            applyChanges(el);
        };
        toolbar.appendChild(applyBtn);

        // ---- 取消按钮 ----
        const cancelBtn = document.createElement('button');
        cancelBtn.textContent = '✕';
        cancelBtn.style.cssText = `
            width: 24px; height: 24px;
            border: 1px solid #DDD; border-radius: 3px;
            background: #FFF; cursor: pointer;
        `;
        cancelBtn.onclick = clearSelection;
        toolbar.appendChild(cancelBtn);

        document.body.appendChild(toolbar);

        // 定位（在元素上方 50px 处居中）
        positionToolbar(el);
    }

    function positionToolbar(el) {
        if (!toolbar) return;
        const rect = el.getBoundingClientRect();
        const toolbarRect = toolbar.getBoundingClientRect();

        let top = rect.top - toolbarRect.height - 8;
        if (top < 10) {
            // 上方放不下，改放下方
            top = rect.bottom + 8;
        }
        let left = rect.left + rect.width / 2 - toolbarRect.width / 2;
        left = Math.max(10, Math.min(left,
            window.innerWidth - toolbarRect.width - 10));

        toolbar.style.top = top + 'px';
        toolbar.style.left = left + 'px';
    }

    function makeToggleBtn(label, name, initialState, onChange) {
        const btn = document.createElement('button');
        btn.textContent = label;
        btn.title = name;
        btn.style.cssText = `
            width: 26px; height: 26px;
            border: 1px solid #DDD; border-radius: 3px;
            background: ${initialState ? '#FFE0A0' : '#FFF'};
            cursor: pointer; font-weight: bold;
            font-size: 13px;
        `;
        let active = initialState;
        btn.onclick = function() {
            active = !active;
            btn.style.background = active ? '#FFE0A0' : '#FFF';
            onChange(active);
        };
        return btn;
    }

    function makeSeparator() {
        const sep = document.createElement('span');
        sep.style.cssText = `
            width: 1px; height: 18px;
            background: #DDD; margin: 0 2px;
        `;
        return sep;
    }

    function hideToolbar() {
        if (toolbar) {
            toolbar.remove();
            toolbar = null;
        }
    }

    // ==================== 应用修改 ====================
    function applyChanges(el) {
        const cs = window.getComputedStyle(el);

        // 计算元素在 slide 内的路径（用于 Python 端定位）
        const path = getElementPath(el);

        const payload = {
            path: path,
            text: el.innerText,
            styles: {
                bold: parseInt(cs.fontWeight) >= 600,
                italic: cs.fontStyle === 'italic',
                underline: cs.textDecorationLine.includes('underline'),
                fontSize: parseInt(cs.fontSize),
                color: cs.color,
                backgroundColor: cs.backgroundColor,
                textAlign: cs.textAlign,
            }
        };

        // 回传 Python
        try {
            const encoded = encodeURIComponent(JSON.stringify(payload));
            window.location.href = 'beeoffice://element-edit?data=' + encoded;
        } catch (e) {
            console.error('回传失败：', e);
        }

        clearSelection();
    }

    // 计算元素路径：如 ".slide > h1:nth-of-type(1)" 用于 Python 端定位
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

    // ==================== 颜色转换 ====================
    function rgbToHex(rgb) {
        if (!rgb || rgb === 'rgba(0, 0, 0, 0)') return '#ffffff';
        const m = rgb.match(/rgba?\((\d+),\s*(\d+),\s*(\d+)/);
        if (!m) return rgb;
        const toHex = n => parseInt(n).toString(16).padStart(2, '0');
        return '#' + toHex(m[1]) + toHex(m[2]) + toHex(m[3]);
    }

    // ==================== 事件绑定 ====================
    function init() {
        markEditableElements();

        document.addEventListener('click', function(e) {
            // 点工具栏里的按钮 → 忽略
            if (e.target.closest('#beeoffice-element-toolbar')) {
                return;
            }

            const el = e.target.closest('[data-editable="1"]');
            if (el) {
                e.stopPropagation();
                selectElement(el);
            } else {
                clearSelection();
            }
        }, true);

        document.addEventListener('keydown', function(e) {
            if (e.key === 'Escape') {
                clearSelection();
            }
        });
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }

    // 供 Python 端调用：清空所有选中
    window.beeofficeClearSelection = clearSelection;
})();
</script>
"""


# ==================== Python 端解析器 ====================
def parse_element_edit_url(url: str) -> Optional[Dict[str, Any]]:
    """
    解析 beeoffice://element-edit?data=... 的 URL。

    :param url: 完整 URL
    :return: {"path": ..., "text": ..., "styles": {...}} 或 None
    """
    try:
        if not url.startswith("beeoffice://element-edit"):
            return None

        # 取 query string
        query = url.split("?", 1)[1] if "?" in url else ""
        params = urllib.parse.parse_qs(query)
        data_str = params.get("data", [""])[0]
        if not data_str:
            return None

        return json.loads(urllib.parse.unquote(data_str))
    except Exception as e:
        logging.error(f"解析元素编辑 URL 失败：{e}")
        return None


# ==================== Markdown 定位与更新 ====================
class MarkdownStylePatcher:
    """
    根据元素路径，把样式修改写回 Markdown。

    设计：
      - Markdown 里不含内联样式，样式通过 HTML 注释存储：
        <!-- beeoffice-style: {path: ".slide > h1:nth-of-type(1)",
                    styles: {bold: true, color: "#FF0000"}} -->
      - 渲染时，_md_to_html 后处理，把这些样式应用到对应元素
      - 用户修改 → 更新注释 → 重新渲染

    这样 Markdown 源保持干净，样式以可读形式存储。
    """

    STYLE_COMMENT_PREFIX = "beeoffice-style:"

    @staticmethod
    def extract_styles(md_text: str) -> Dict[str, Dict[str, Any]]:
        """
        从 Markdown 里提取所有样式覆盖。

        :param md_text: Markdown 原文
        :return: {path: {styles}} 字典
        """
        import re
        result = {}
        pattern = re.compile(
            r'<!--\s*beeoffice-style:\s*(\{.*?\})\s*-->',
            re.DOTALL,
        )
        for m in pattern.finditer(md_text):
            try:
                data = json.loads(m.group(1))
                if isinstance(data, dict):
                    path = data.get("path", "")
                    styles = data.get("styles", {})
                    if path and styles:
                        result[path] = styles
            except Exception:
                continue
        return result

    @staticmethod
    def upsert_style(
        md_text: str,
        path: str,
        styles: Dict[str, Any],
    ) -> str:
        """
        更新或插入样式覆盖。

        :param md_text: Markdown 原文
        :param path: 元素路径
        :param styles: 样式字典
        :return: 更新后的 Markdown
        """
        import re

        # 构造新的注释
        data = {"path": path, "styles": styles}
        new_comment = (
            f"<!-- beeoffice-style: "
            f"{json.dumps(data, ensure_ascii=False)} -->"
        )

        # 检查是否已有同 path 的注释
        existing_pattern = re.compile(
            r'<!--\s*beeoffice-style:\s*(\{.*?\})\s*-->',
            re.DOTALL,
        )

        found = False
        result_parts = []
        last_end = 0

        for m in existing_pattern.finditer(md_text):
            try:
                data_existing = json.loads(m.group(1))
                if data_existing.get("path") == path:
                    # 替换
                    result_parts.append(md_text[last_end:m.start()])
                    result_parts.append(new_comment)
                    last_end = m.end()
                    found = True
            except Exception:
                continue

        result_parts.append(md_text[last_end:])
        result = "".join(result_parts)

        if not found:
            # 追加到末尾
            result = result.rstrip() + "\n" + new_comment + "\n"

        return result

    @staticmethod
    def apply_styles_to_html(
        html: str, styles_map: Dict[str, Dict[str, Any]]
    ) -> str:
        """
        把样式应用到渲染后的 HTML。

        用 BeautifulSoup 解析 HTML，根据 path 定位元素，写入 style 属性。

        任务 2.3：跳过 <img>（由 MarkdownImagePatcher 处理）。

        :param html: 渲染后的 HTML 片段
        :param styles_map: {path: {styles}} 字典
        :return: 应用样式后的 HTML
        """
        if not styles_map:
            return html

        try:
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(html, "html.parser")

            for path, styles in styles_map.items():
                el = MarkdownStylePatcher._find_by_path(soup, path)
                if el is None:
                    continue
                # 任务 2.3：跳过图片（图片由 MarkdownImagePatcher 处理）
                if el.name == "img":
                    continue

                # 构造 CSS 字符串
                css_parts = []
                if styles.get("bold"):
                    css_parts.append("font-weight: bold")
                if styles.get("italic"):
                    css_parts.append("font-style: italic")
                if styles.get("underline"):
                    css_parts.append("text-decoration: underline")
                if styles.get("fontSize"):
                    css_parts.append(f"font-size: {styles['fontSize']}px")
                if styles.get("color"):
                    css_parts.append(f"color: {styles['color']}")
                if styles.get("backgroundColor"):
                    css_parts.append(
                        f"background-color: {styles['backgroundColor']}"
                    )
                if styles.get("textAlign"):
                    css_parts.append(f"text-align: {styles['textAlign']}")

                if css_parts:
                    existing = el.get("style", "")
                    el["style"] = existing + "; " + "; ".join(css_parts)

            return str(soup)
        except ImportError:
            logging.warning(tr("auto.beeshow_element_editor.c1bf0cb7", "bs4 未安装，样式应用跳过"))
            return html
        except Exception as e:
            logging.error(f"应用样式失败：{e}")
            return html

    @staticmethod
    def _find_by_path(soup, path: str):
        """
        根据路径（如 ".slide > h1:nth-of-type(1)"）查找元素。

        :param soup: BeautifulSoup 对象
        :param path: 元素路径
        :return: Tag 或 None
        """
        try:
            # 路径格式：.slide > h1:nth-of-type(1) > ...
            # 简化：直接用最后一段定位
            parts = [p.strip() for p in path.split(">") if p.strip()]
            if not parts:
                return None

            # 找到 .slide 根
            root = soup.find(class_="slide")
            if root is None:
                root = soup

            # 逐级查找
            current = root
            for part in parts:
                if part.startswith(".slide"):
                    continue

                # 解析 tag 和 :nth-of-type(n)
                import re
                m = re.match(
                    r"([a-zA-Z]+)(?::nth-of-type\((\d+)\))?",
                    part,
                )
                if not m:
                    return None
                tag = m.group(1).lower()
                idx = int(m.group(2)) if m.group(2) else 1

                # 找子元素
                siblings = current.find_all(
                    tag, recursive=False
                )
                if not siblings and current == root:
                    # 可能是直接子元素
                    siblings = current.find_all(tag)
                if not siblings or idx > len(siblings):
                    return None
                current = siblings[idx - 1]

            return current
        except Exception as e:
            logging.debug(f"查找元素失败 {path}：{e}")
            return None


# ==================== 自定义 QWebEnginePage（任务 2.2 + 2.3） ====================
def _make_web_engine_page_class():
    """
    延迟创建 BeeOfficeWebEnginePage 类。

    因为 QWebEnginePage 需要在 QApplication 初始化后才能导入，
    所以用工厂函数延迟创建。

    任务 2.3：_handle_beeoffice_url 里加 beeoffice://image-edit 分支
    """
    try:
        from PySide6.QtWebEngineCore import QWebEnginePage
    except ImportError:
        # 兼容旧版 PySide6
        try:
            from PySide6.QtWebEngineWidgets import QWebEnginePage
        except ImportError:
            return None

    class _BeeOfficeWebEnginePage(QWebEnginePage):
        """
        自定义 QWebEnginePage：拦截 beeoffice:// 协议。

        当 JS 里 `window.location.href = "beeoffice://..."` 时，
        QWebEnginePage.acceptNavigationRequest 会被调用，
        我们可以拦截这个 URL，转发给 owner（BeeShowView）。

        支持的自定义协议：
          - beeoffice://element-edit?data=...  任务 2.2
          - beeoffice://image-edit?data=...    任务 2.3
        """

        def __init__(self, owner, parent=None):
            super().__init__(parent)
            self._owner = owner

        def acceptNavigationRequest(
            self, url, nav_type, is_main_frame
        ):
            url_str = url.toString()
            if url_str.startswith("beeoffice://"):
                # 拦截自定义协议
                try:
                    self._handle_beeoffice_url(url_str)
                except Exception as e:
                    logging.error(f"处理自定义协议失败：{e}")
                # 返回 False 阻止实际导航
                return False
            return super().acceptNavigationRequest(
                url, nav_type, is_main_frame
            )

        def _handle_beeoffice_url(self, url_str: str):
            """处理 beeoffice:// 协议"""
            if url_str.startswith("beeoffice://element-edit"):
                # 任务 2.2：元素编辑回调
                data = parse_element_edit_url(url_str)
                if data and self._owner is not None:
                    handler = getattr(
                        self._owner,
                        "_on_element_edit_applied",
                        None,
                    )
                    if handler:
                        handler(data)

            elif url_str.startswith("beeoffice://image-edit"):
                # 任务 2.3：图片编辑回调
                try:
                    from beeoffice.plugins.beeshow_image_editor import (
                        parse_image_edit_url,
                    )
                    data = parse_image_edit_url(url_str)
                except Exception:
                    data = None
                if data and self._owner is not None:
                    handler = getattr(
                        self._owner,
                        "_on_image_edit_applied",
                        None,
                    )
                    if handler:
                        handler(data)

    return _BeeOfficeWebEnginePage


# 延迟创建单例类
BeeOfficeWebEnginePage = _make_web_engine_page_class()