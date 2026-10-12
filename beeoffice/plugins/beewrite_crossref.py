# beeoffice/plugins/beewrite_crossref.py
"""
蜜写交叉引用（简化版）：标题自动编号 + 插入引用

v5.0.1 修复（P1-11）：
  - 文件头注释拼写修正：beewrite_crossref.py → beewrite_crossref.py
    （原文件名本身就是 beewrite_，仅注释少了一个 e）
"""

import re

from beeoffice.plugins.heading_numbering import HeadingNumberer


class CrossRefManager:
    """交叉引用管理器（简化版）"""

    def __init__(self):
        self._headings = []     # [{level, text, number, pos}]
        self._numbering = True  # 是否自动编号

    # ==================== 扫描标题 ====================
    def scan_headings(self, editor):
        """
        扫描编辑器中的所有标题
        :param editor: RichTextEditor
        :return: [{level, text, number, pos}]

        优化规划 §3.3：编号算法原先在本文件与 `beewrite_outline` 里**逐字重复**，
        现统一走 `heading_numbering.HeadingNumberer`（唯一实现 + 纯函数可测）。
        """
        self._headings = []
        doc = editor.document()
        block = doc.begin()

        numberer = HeadingNumberer()

        while block.isValid():
            bf = block.blockFormat()
            level = bf.headingLevel()
            if 1 <= level <= 6:
                text = block.text().strip()
                if text:
                    self._headings.append({
                        "level": level,
                        "text": text,
                        "number": numberer.next_number(level),
                        "pos": block.position(),
                    })

            block = block.next()

        return list(self._headings)

    def get_headings(self):
        return list(self._headings)

    def has_headings(self):
        return len(self._headings) > 0