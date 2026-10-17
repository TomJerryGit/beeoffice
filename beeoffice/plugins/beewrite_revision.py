# beeoffice/plugins/beewrite_revision.py
"""
蜜写修订模式（简化版）：基线快照 + 差异对比
支持：开启修订 → 编辑 → 关闭修订时对比 → 接受/拒绝

v5.0.1 修复（P1-11）：
  - 文件头注释拼写修正：beewrite_revision.py → beewrite_revision.py
    （原文件名本身就是 beewrite_，仅注释少了一个 e）
"""

import difflib
from datetime import datetime


class RevisionManager:
    """修订管理器"""

    def __init__(self):
        self._baseline = None          # 基线文本
        self._baseline_time = None     # 基线时间
        self._active = False           # 修订模式是否开启
        self._differences = []         # 当前差异列表

    # ==================== 状态 ====================
    @property
    def active(self):
        return self._active

    @property
    def has_baseline(self):
        return self._baseline is not None

    @property
    def baseline(self):
        return self._baseline

    @property
    def baseline_time(self):
        return self._baseline_time

    # ==================== 开启/关闭 ====================
    def start_revision(self, current_text):
        """开启修订：记录当前文本为基线"""
        self._baseline = current_text
        self._baseline_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self._active = True
        self._differences = []
        return True

    def stop_revision(self):
        """关闭修订（不对比）"""
        self._active = False
        self._differences = []

    def accept_all(self):
        """接受所有修改：清空基线"""
        self._baseline = None
        self._baseline_time = None
        self._active = False
        self._differences = []

    def reject_all(self):
        """拒绝所有修改：返回基线文本"""
        baseline = self._baseline
        self._baseline = None
        self._baseline_time = None
        self._active = False
        self._differences = []
        return baseline

    # ==================== 差异对比 ====================
    def compute_diff(self, current_text):
        """
        对比基线和当前文本
        返回:
            {
                "additions": int,     # 新增行数
                "deletions": int,     # 删除行数
                "modified": int,      # 修改行数（近似）
                "total_changes": int, # 总变更数
                "diff_text": str,     # unified diff 文本
                "blocks": list,       # 详细差异块
            }
        """
        if self._baseline is None:
            return {
                "additions": 0,
                "deletions": 0,
                "modified": 0,
                "total_changes": 0,
                "diff_text": "（无基线）",
                "blocks": [],
            }

        old_lines = self._baseline.split("\n")
        new_lines = current_text.split("\n")

        diff_lines = list(difflib.unified_diff(
            old_lines, new_lines,
            lineterm="",
            fromfile="基线",
            tofile="当前"
        ))

        additions = 0
        deletions = 0
        for line in diff_lines:
            if line.startswith("+") and not line.startswith("+++"):
                additions += 1
            elif line.startswith("-") and not line.startswith("---"):
                deletions += 1

        # 生成差异块（可选，用于精细显示）
        blocks = self._build_blocks(old_lines, new_lines)

        modified = self._count_modified(old_lines, new_lines)

        return {
            "additions": additions,
            "deletions": deletions,
            "modified": modified,
            "total_changes": additions + deletions,
            "diff_text": "\n".join(diff_lines) if diff_lines else "（无差异）",
            "blocks": blocks,
        }

    def _build_blocks(self, old_lines, new_lines):
        """使用 SequenceMatcher 构建差异块"""
        sm = difflib.SequenceMatcher(None, old_lines, new_lines)
        blocks = []
        for tag, i1, i2, j1, j2 in sm.get_opcodes():
            if tag == "equal":
                continue
            blocks.append({
                "type": tag,  # replace / delete / insert
                "old_start": i1,
                "old_end": i2,
                "new_start": j1,
                "new_end": j2,
                "old_lines": old_lines[i1:i2],
                "new_lines": new_lines[j1:j2],
            })
        return blocks

    def _count_modified(self, old_lines, new_lines):
        """近似统计修改行数"""
        sm = difflib.SequenceMatcher(None, old_lines, new_lines)
        modified = 0
        for tag, i1, i2, j1, j2 in sm.get_opcodes():
            if tag == "replace":
                modified += max(i2 - i1, j2 - j1)
        return modified