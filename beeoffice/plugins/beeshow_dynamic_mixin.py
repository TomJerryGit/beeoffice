# beeoffice/plugins/beeshow_dynamic_mixin.py
"""
蜜演动态数字 Mixin（任务 5.1）

功能：
  把 Markdown 中的 {{number: 12345}} 语法渲染为会从 0 滚动到目标值的
  动态数字。

对标：
  - WPS 演示的「动态数字」——数值动态变化

语法：
  {{number: 12345}}
  {{number: 12345, duration: 2000}}
  {{number: 12345, prefix: ¥, suffix: 元}}
  {{number: 12345, decimals: 2}}
  {{number: 12345, duration: 2000, prefix: ¥, suffix: 元, decimals: 2}}

参数：
  - number   : 目标数值（必填）
  - duration : 动画时长毫秒（默认 1500）
  - prefix   : 前缀（如 ¥ / $ / 共）
  - suffix   : 后缀（如 元 / 人 / %）
  - decimals : 小数位数（默认 0）

渲染：
  生成 <span class="dynamic-number" data-*>0</span>
  配合 _get_dynamic_number_js() 注入的 JS 实现滚动动画。

注意：
  - 不导入其他 beeshow_* Mixin
  - 导出 PDF / 图片时，JS 不执行 → 显示最终值（由服务端渲染保障）
  - 导出 PPTX 时，测量器读到的是 "0"，需要在 render 后回填
    （本期简化：导出 PPTX 时用最终值替换）
"""

import re
import logging
from typing import Dict, Any



# ==================== 语法解析 ====================
# 匹配 {{number: ...}}
DYNAMIC_NUMBER_PATTERN = re.compile(
    r"\{\{\s*number\s*:\s*(.+?)\s*\}\}",
    re.IGNORECASE,
)


class DynamicMixin:
    """蜜演动态数字 Mixin"""

    # 默认动画时长（毫秒）
    DEFAULT_DURATION = 1500

    # 默认小数位数
    DEFAULT_DECIMALS = 0

    # ==================== Markdown 预处理 ====================
    def _process_dynamic_numbers(self, md_text: str) -> str:
        """
        把 Markdown 中的 {{number: ...}} 替换为 HTML span。

        :param md_text: 原始 Markdown
        :return: 替换后的 Markdown

        处理流程：
          1. 用正则找到所有 {{number: ...}}
          2. 解析参数（number / duration / prefix / suffix / decimals）
          3. 生成 HTML span
          4. 替换回原文
        """
        def replace(match):
            try:
                inner = match.group(1).strip()
                params = self._parse_dynamic_params(inner)
                return self._render_dynamic_span(params)
            except Exception as e:
                logging.warning(f"动态数字解析失败：{e}（原文：{match.group(0)}）")
                # 解析失败时保留原文（用户能看到错误）
                return match.group(0)

        return DYNAMIC_NUMBER_PATTERN.sub(replace, md_text)

    def _parse_dynamic_params(self, inner: str) -> Dict[str, Any]:
        """
        解析 {{number: 12345, prefix: ¥, suffix: 元}} 里的参数。

        :param inner: 大括号内、冒号后的部分
        :return: {"number": ..., "duration": ..., "prefix": ..., ...}
        """
        params = {
            "number": 0,
            "duration": self.DEFAULT_DURATION,
            "prefix": "",
            "suffix": "",
            "decimals": self.DEFAULT_DECIMALS,
        }

        # 处理键值对（key: value），用逗号分隔
        # 注意：值中可能含逗号，用更聪明的切分
        # 简单策略：先按逗号切分，再识别 key:value 或纯数字
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
                params[key] = value
            else:
                # 纯数字（第一个参数）
                if isinstance(params["number"], (int, float)) \
                        and params["number"] == 0:
                    params["number"] = part

        # 类型转换
        try:
            params["number"] = float(params["number"])
            # 整数则转 int（避免显示 "12345.0"）
            if params["number"] == int(params["number"]):
                params["number"] = int(params["number"])
        except (ValueError, TypeError):
            params["number"] = 0

        try:
            params["duration"] = int(params["duration"])
        except (ValueError, TypeError):
            params["duration"] = self.DEFAULT_DURATION

        try:
            params["decimals"] = int(params["decimals"])
        except (ValueError, TypeError):
            params["decimals"] = self.DEFAULT_DECIMALS

        return params

    @staticmethod
    def _split_params(text: str) -> list:
        """
        按逗号切分参数，但忽略引号内的逗号。

        支持：
          number: 12345, prefix: ¥, suffix: 元
          number: 12345, prefix: "Hello, World"
        """
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

    def _render_dynamic_span(self, params: Dict[str, Any]) -> str:
        """
        生成动态数字的 HTML span。

        输出形如：
          <span class="dynamic-number"
                data-to="12345"
                data-duration="1500"
                data-prefix="¥"
                data-suffix="元"
                data-decimals="0"
                data-final="¥12,345元">0</span>

        data-final 是为"没有 JS 时"准备的兜底显示值。
        """
        number = params["number"]
        decimals = params["decimals"]
        prefix = params["prefix"]
        suffix = params["suffix"]
        duration = params["duration"]

        # 最终值（带千分位、小数、前后缀）
        if decimals > 0:
            final_str = f"{number:,.{decimals}f}"
        else:
            final_str = f"{number:,}"
        final_display = f"{prefix}{final_str}{suffix}"

        # HTML 属性中的值需转义
        def esc(s):
            return (
                str(s)
                .replace("&", "&amp;")
                .replace('"', "&quot;")
                .replace("<", "&lt;")
                .replace(">", "&gt;")
            )

        return (
            f'<span class="dynamic-number" '
            f'data-to="{esc(number)}" '
            f'data-duration="{esc(duration)}" '
            f'data-prefix="{esc(prefix)}" '
            f'data-suffix="{esc(suffix)}" '
            f'data-decimals="{esc(decimals)}" '
            f'data-final="{esc(final_display)}">'
            f'{esc(prefix)}0{esc(suffix)}'
            f'</span>'
        )

    # ==================== JS 动画脚本 ====================
    def _get_dynamic_number_js(self) -> str:
        """
        返回动态数字的 JS 脚本片段。

        在 _show_slide / _show_play_slide 拼接到 HTML 里。

        JS 逻辑：
          1. 查找所有 .dynamic-number
          2. 读取 data-* 参数
          3. 用 requestAnimationFrame 从 0 缓动到目标值
          4. 每帧格式化并写入 innerText
        """
        return r"""
<script>
(function() {
    function formatNumber(value, decimals, prefix, suffix) {
        var fixed = decimals > 0
            ? value.toFixed(decimals)
            : Math.round(value).toString();
        // 千分位
        var parts = fixed.split('.');
        parts[0] = parts[0].replace(/\B(?=(\d{3})+(?!\d))/g, ',');
        return prefix + parts.join('.') + suffix;
    }

    function easeOutQuad(t) {
        return 1 - (1 - t) * (1 - t);
    }

    function animateNumber(el) {
        var to = parseFloat(el.dataset.to || "0");
        var duration = parseInt(el.dataset.duration || "1500");
        var prefix = el.dataset.prefix || "";
        var suffix = el.dataset.suffix || "";
        var decimals = parseInt(el.dataset.decimals || "0");
        var start = performance.now();

        function tick(now) {
            var elapsed = now - start;
            var t = Math.min(elapsed / duration, 1);
            var eased = easeOutQuad(t);
            var current = to * eased;
            el.textContent = formatNumber(current, decimals, prefix, suffix);
            if (t < 1) {
                requestAnimationFrame(tick);
            } else {
                el.textContent = formatNumber(to, decimals, prefix, suffix);
            }
        }
        requestAnimationFrame(tick);
    }

    function runAll() {
        var els = document.querySelectorAll('.dynamic-number');
        els.forEach(function(el) {
            // 避免重复动画
            if (el.dataset.animated === "1") return;
            el.dataset.animated = "1";
            animateNumber(el);
        });
    }

    // DOM 就绪后执行
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', runAll);
    } else {
        runAll();
    }

    // 暴露给 Python 调用（强制重播）
    window.replayDynamicNumbers = function() {
        var els = document.querySelectorAll('.dynamic-number');
        els.forEach(function(el) {
            el.dataset.animated = "0";
        });
        runAll();
    };
})();
</script>
"""

    # ==================== 导出预处理 ====================
    def _render_dynamic_numbers_for_export(self, md_text: str) -> str:
        """
        导出 PDF / PPTX 时的预处理：把动态数字替换为**最终值**。

        原因：
          - 导出时不执行 JS
          - 若保留 <span data-to=...>0</span>，PDF 里显示 0 而非最终值

        优化规划 §2.7：调用方传进来的是 **HTML**（`self._slides_html`，
        见 `beeshow_export_mixin._export_pptx` 与 PDF 导出），而本方法原先只按
        Markdown 的 `{{number: ...}}` 模式替换 —— 对 HTML 一路 `re.sub`
        完全匹配不到内容，**静默返回原串**：函数看着被调用了，导出的
        PDF/PPTX 里动态数字却仍然是 **0**。

        现在两种输入都处理：
          - HTML：把 `<span ... data-final="X">…</span>` 的内文换成 X
            （HTML 实体反转义），导出不依赖 JS；
          - Markdown：保留原有的 `{{number: ...}}` 替换，兼容其他调用方。
        """
        if not md_text:
            return md_text

        # 1) HTML：按 data-final 回填 span 内文。
        #    不要求属性顺序，只认 data-final —— 该属性仅由动态数字生成器产出。
        span_pattern = re.compile(
            r'(<span[^>]*\bdata-final="([^"]*)"[^>]*>)(.*?)(</span>)',
            re.DOTALL,
        )

        def _unescape(value: str) -> str:
            return (
                value.replace("&quot;", '"')
                .replace("&lt;", "<")
                .replace("&gt;", ">")
                .replace("&amp;", "&")
            )

        def replace_span(match):
            return (
                f"{match.group(1)}"
                f"{_unescape(match.group(2))}"
                f"{match.group(4)}"
            )

        html_result = span_pattern.sub(replace_span, md_text)

        # 2) Markdown：原有 {{number: ...}} 替换（保持兼容）
        def replace(match):
            try:
                inner = match.group(1).strip()
                params = self._parse_dynamic_params(inner)
                number = params["number"]
                decimals = params["decimals"]
                prefix = params["prefix"]
                suffix = params["suffix"]
                if decimals > 0:
                    s = f"{number:,.{decimals}f}"
                else:
                    s = f"{number:,}"
                return f"{prefix}{s}{suffix}"
            except Exception as e:
                logging.warning(f"导出动态数字失败：{e}")
                return match.group(0)

        return DYNAMIC_NUMBER_PATTERN.sub(replace, html_result)