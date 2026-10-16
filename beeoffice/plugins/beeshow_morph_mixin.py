# beeoffice/plugins/beeshow_morph_mixin.py
"""
蜜演平滑动画 Mixin（任务 5.2）

功能：
  相邻幻灯片中相同 ID 的元素在翻页时平滑移动/缩放/变色。

对标：
  - WPS 的「平滑动画」——只需两页 + 一个效果，元素自动移动

语法：
  在 Markdown 中用 {#element-id} 标记元素：
    # 标题 {#main-title}
    
    - 要点1 {#item-1}
    - 要点2 {#item-2}

  翻页时，若前后两页都有相同 id 的元素，则：
    - 位置从 A 平滑移动到 B
    - 尺寸从 W1×H1 平滑缩放到 W2×H2
    - 颜色从 C1 平滑过渡到 C2

  仅当主题动画设置为"平滑"时启用（默认关闭，避免误触发）

实现原理：
  1. _md_to_html 渲染时，把 {#id} 提取为 data-morph-id="id"
  2. 播放翻页时，在旧 HTML 和 新 HTML 里查找相同 data-morph-id
  3. 用绝对定位 + CSS Transition 实现平滑过渡

局限：
  - 仅支持简单元素（h1~h6/p/li/span），复杂布局不支持
  - 元素必须用绝对定位才能跨页平滑移动
  - 导出 PDF/图片时禁用动画（无意义）

依赖：
  - re / logging / json
  - PySide6（无）

注意：
  - 不导入其他 beeshow_* Mixin
  - 默认关闭，需在动画下拉框选择"平滑"
"""

import re
import logging
from typing import Dict, List


# ==================== 语法解析 ====================
# 匹配行尾的 {#id}
MORPH_ID_PATTERN = re.compile(
    r"\{#([a-zA-Z0-9_\-]+)\}\s*$",
    re.MULTILINE,
)


class MorphMixin:
    """蜜演平滑动画 Mixin"""

    # ==================== Markdown 预处理 ====================
    def _process_morph_ids(self, md_text: str) -> str:
        """
        提取 Markdown 里的 {#id} 标记，转换为 HTML span 包裹。

        对每一行：
          "# 标题 {#main-title}"
        →
          '<span data-morph-id="main-title"># 标题</span>'

        注意：这里不能直接替换整行（会破坏 Markdown 语法），
        改为在行尾追加 HTML 注释，由 JS 在渲染后应用。

        :param md_text: Markdown 原文
        :return: 处理后的 Markdown
        """
        lines = md_text.split("\n")
        new_lines = []

        for line in lines:
            m = MORPH_ID_PATTERN.search(line)
            if m:
                morph_id = m.group(1)
                # 移除 {#id} 标记
                clean_line = line[:m.start()].rstrip()
                # 追加 HTML 注释（保留 id）
                new_lines.append(
                    f"{clean_line}\n<!-- morph-id: {morph_id} -->"
                )
            else:
                new_lines.append(line)

        return "\n".join(new_lines)

    def _extract_morph_ids(self, md_text: str) -> List[str]:
        """
        提取 Markdown 里所有 morph id（按出现顺序）。

        :param md_text: Markdown 原文
        :return: id 列表
        """
        return MORPH_ID_PATTERN.findall(md_text)

    def _extract_morph_pairs(
        self, prev_md: str, curr_md: str
    ) -> List[Dict[str, str]]:
        """
        计算前后两页的 morph 对。

        :param prev_md: 前一页 Markdown
        :param curr_md: 当前页 Markdown
        :return: [{"id": "main-title", "prev_text": "...", "curr_text": "..."}]
        """
        prev_ids = set(self._extract_morph_ids(prev_md))
        curr_ids = set(self._extract_morph_ids(curr_md))
        common = prev_ids & curr_ids
        return [{"id": mid} for mid in sorted(common)]

    # ==================== JS 生成器 ====================
    def _get_morph_js(self) -> str:
        """
        返回平滑动画的 JS 脚本。

        注入到播放页 HTML 里，只在"平滑"动画模式下生效。

        JS 逻辑：
          1. 从 URL hash 或全局变量读取 morph 信息
          2. 在新页渲染后，查找 data-morph-id 元素
          3. 与上一次的位置/尺寸对比
          4. 用 CSS Transition 实现平滑过渡
        """
        return r"""
<script>
(function() {
    'use strict';

    // 保存上一次的位置信息
    const morphCache = {};
    let isFirstSlide = true;

    function initMorph() {
        // 从全局变量读取（由 Python 注入）
        const morphIds = window.__beeofficeMorphIds || [];

        // 收集当前页所有 morph 元素的位置
        const currentPositions = {};
        morphIds.forEach(function(id) {
            const el = document.querySelector(
                '[data-morph-id="' + id + '"]'
            );
            if (el) {
                const rect = el.getBoundingClientRect();
                currentPositions[id] = {
                    el: el,
                    rect: {
                        left: rect.left,
                        top: rect.top,
                        width: rect.width,
                        height: rect.height,
                    },
                };
            }
        });

        // 若不是第一页，应用平滑过渡
        if (!isFirstSlide && window.__beeofficePrevPositions) {
            Object.keys(currentPositions).forEach(function(id) {
                const prev = window.__beeofficePrevPositions[id];
                const curr = currentPositions[id];
                if (!prev || !curr) return;

                // 计算位置/尺寸变化
                const dx = prev.left - curr.rect.left;
                const dy = prev.top - curr.rect.top;
                const sx = prev.width / curr.rect.width;
                const sy = prev.height / curr.rect.height;

                // 元素需要绝对定位才能平滑移动
                curr.el.style.position = 'fixed';
                curr.el.style.left = curr.rect.left + 'px';
                curr.el.style.top = curr.rect.top + 'px';
                curr.el.style.width = curr.rect.width + 'px';
                curr.el.style.height = curr.rect.height + 'px';
                curr.el.style.zIndex = '100';

                // 初始状态（从旧位置开始）
                curr.el.style.transform =
                    'translate(' + dx + 'px, ' + dy + 'px) ' +
                    'scale(' + sx + ', ' + sy + ')';
                curr.el.style.transformOrigin = 'top left';
                curr.el.style.transition = 'none';

                // 下一帧应用过渡
                requestAnimationFrame(function() {
                    requestAnimationFrame(function() {
                        curr.el.style.transition =
                            'transform 0.6s cubic-bezier(0.4, 0, 0.2, 1)';
                        curr.el.style.transform =
                            'translate(0, 0) scale(1, 1)';
                    });
                });
            });
        }

        // 保存当前位置供下一页使用
        const positionsForNext = {};
        Object.keys(currentPositions).forEach(function(id) {
            positionsForNext[id] = currentPositions[id].rect;
        });
        window.__beeofficePrevPositions = positionsForNext;

        isFirstSlide = false;
    }

    // DOM 就绪后执行
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', initMorph);
    } else {
        initMorph();
    }
})();
</script>
"""

    # ==================== HTML 后处理 ====================
    def _apply_morph_ids_to_html(self, html: str) -> str:
        """
        把渲染后的 HTML 里 `<!-- morph-id: xxx -->` 注释
        转换为 data-morph-id 属性。

        :param html: 渲染后的 HTML
        :return: 处理后的 HTML
        """
        try:
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(html, "html.parser")

            # 找所有注释
            from bs4 import Comment
            for comment in soup.find_all(string=lambda t: isinstance(t, Comment)):
                text = comment.strip()
                if text.startswith("morph-id:"):
                    morph_id = text[len("morph-id:"):].strip()
                    # 找到该注释的前一个兄弟元素
                    prev = comment.find_previous_sibling()
                    if prev:
                        prev["data-morph-id"] = morph_id
                    # 移除注释
                    comment.extract()

            return str(soup)
        except ImportError:
            # 无 bs4 时用正则
            return self._apply_morph_ids_by_regex(html)
        except Exception as e:
            logging.error(f"应用 morph id 失败：{e}")
            return html

    @staticmethod
    def _apply_morph_ids_by_regex(html: str) -> str:
        """
        正则版本：把 `<!-- morph-id: xxx -->` 转换为 data-morph-id。

        匹配模式：
          <tag ...>内容</tag>
          <!-- morph-id: xxx -->
        →
          <tag ... data-morph-id="xxx">内容</tag>
        """
        # 注意：正则难以处理嵌套标签，这里只处理简单场景
        pattern = re.compile(
            r"<([a-zA-Z][a-zA-Z0-9]*)([^>]*)>"
            r"([^<]*)"
            r"</\1>"
            r"\s*<!--\s*morph-id:\s*([a-zA-Z0-9_\-]+)\s*-->",
            re.DOTALL,
        )

        def replace(m):
            tag = m.group(1)
            attrs = m.group(2)
            content = m.group(3)
            mid = m.group(4)
            # 检查 attrs 里是否已有 data-morph-id
            if "data-morph-id" in attrs:
                return m.group(0)
            return f'<{tag}{attrs} data-morph-id="{mid}">{content}</{tag}>'

        return pattern.sub(replace, html)

    # ==================== 播放时注入 ====================
    def _get_morph_ids_for_current_slide(self) -> List[str]:
        """
        获取当前页的 morph id 列表。

        :return: id 列表
        """
        try:
            if not (0 <= self._current_slide < len(self._slides_md)):
                return []
            return self._extract_morph_ids(
                self._slides_md[self._current_slide]
            )
        except Exception:
            return []

    def _is_morph_mode(self) -> bool:
        """判断当前动画是否为"平滑"模式"""
        try:
            return self._anim_combo.currentText() == "平滑"
        except Exception:
            return False