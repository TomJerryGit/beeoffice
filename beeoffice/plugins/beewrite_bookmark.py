# beeoffice/plugins/beewrite_bookmark.py
"""
蜜写书签管理：存储、跳转、列表

v5.0.1 修复（P1-11）：
  - 文件头注释拼写修正：beewrite_bookmark.py → beewrite_bookmark.py
    （原文件名本身就是 beewrite_，仅注释少了一个 e）
"""
import json
import logging
from pathlib import Path
from datetime import datetime


class BookmarkManager:
    """书签管理器（位置锚点方式）"""

    def __init__(self):
        # {name: {"pos": int, "line": int, "time": str}}
        self._bookmarks = {}

    # ==================== 增删改查 ====================
    def add(self, name, pos, line):
        """添加书签"""
        self._bookmarks[name] = {
            "pos": pos,
            "line": line,
            "time": datetime.now().strftime("%Y-%m-%d %H:%M"),
        }

    def remove(self, name):
        """删除书签"""
        if name in self._bookmarks:
            del self._bookmarks[name]
            return True
        return False

    def get(self, name):
        """获取书签"""
        return self._bookmarks.get(name)

    def get_all(self):
        """获取全部书签"""
        return dict(self._bookmarks)

    def has(self, name):
        """是否存在"""
        return name in self._bookmarks

    def clear(self):
        """清空"""
        self._bookmarks.clear()

    def update_position(self, name, new_pos):
        """编辑后更新位置（供外部调用）"""
        if name in self._bookmarks:
            self._bookmarks[name]["pos"] = new_pos

    def count(self):
        """书签数量"""
        return len(self._bookmarks)

    # ==================== 序列化 ====================
    def to_dict(self):
        return dict(self._bookmarks)

    def from_dict(self, data):
        if isinstance(data, dict):
            self._bookmarks = dict(data)

    def save_to_file(self, path):
        # P0 止血：旁挂 JSON 也原子写（写到一半崩溃不会留下坏文件）
        from beeoffice.utils import atomic_write_json

        if atomic_write_json(path, self._bookmarks):
            return True
        logging.error(f"书签保存失败: {path}")
        return False

    def load_from_file(self, path):
        try:
            p = Path(path)
            if not p.exists():
                return False
            with open(p, "r", encoding="utf-8") as f:
                data = json.load(f)
            self.from_dict(data)
            return True
        except Exception as e:
            logging.error(f"书签加载失败: {e}")
            return False