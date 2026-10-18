# beeoffice/plugins/beeshow_comment_mixin.py
"""
蜜演评论与批注 Mixin（任务 4.2）

职责：
  - _add_comment          : 给当前页添加评论
  - _show_comment_panel   : 显示 / 隐藏评论面板
  - _refresh_comment_panel: 刷新评论列表
  - _edit_comment         : 编辑评论
  - _delete_comment       : 删除评论
  - _toggle_comment_resolved : 切换已解决状态
  - _jump_to_comment_page : 跳转到评论所在页

存储：
  _slide_comments = {
      0: [
          {"id": 1, "author": "当前用户", "text": "...", 
           "time": "2026-09-17 10:30", "resolved": False},
          ...
      ],
      2: [...],
  }

序列化：
  评论以 HTML 注释形式保留在编辑器里：
    <!-- comments: [{...}, {...}] -->
  位置：追加到对应幻灯片末尾。
  _update_preview 时解析。

对标：
  - WPS 365「批注、评论与任务分配直接沉淀在文档中」

依赖：
  - json / logging / datetime
  - PySide6（QInputDialog / QMessageBox）
  - beeshow_comment_panel（CommentPanel）

注意：
  - 不导入其他 beeshow_* Mixin
  - 评论数据通过 HTML 注释持久化，保证与 Markdown 内容共存
"""

import json
import logging
import re
from datetime import datetime
from typing import Dict, List, Any

from PySide6.QtWidgets import QInputDialog, QMessageBox

from beeoffice.plugins.beeshow_comment_panel import CommentPanel
from beeoffice.i18n import tr


class CommentMixin:
    """蜜演评论与批注 Mixin"""

    # ==================== 评论数据 ====================
    def _init_comments_state(self):
        """初始化评论状态（由 BeeShowView._init_state 调用）"""
        # {page_index: [comment_dict, ...]}
        self._slide_comments: Dict[int, List[Dict[str, Any]]] = {}
        # 评论 ID 计数器
        self._comment_next_id = 1
        # 评论面板（延迟创建）
        self._comment_panel = None

    def _add_comment(self):
        """
        给当前页添加评论。

        流程：
          1. 检查当前页有效性
          2. 弹出输入对话框（默认显示已有评论的编辑版）
          3. 写入 _slide_comments
          4. 同步到编辑器（HTML 注释）
          5. 刷新面板
        """
        if not self._slides_html:
            QMessageBox.information(self, tr("auto.beeshow_comment_mixin.ab3656a9", "提示"), tr("auto.beeshow_comment_mixin.63565334", "请先编写幻灯片内容"))
            return

        if not (0 <= self._current_slide < len(self._slides_html)):
            return

        page_idx = self._current_slide
        title = (
            self._slide_titles[page_idx]
            if page_idx < len(self._slide_titles)
            else f"第 {page_idx + 1} 页"
        )

        # 弹出输入对话框
        text, ok = QInputDialog.getMultiLineText(
            self, "💬 添加评论",
            f"第 {page_idx + 1} 页「{title}」的评论：",
            ""
        )
        if not ok or not text.strip():
            return

        comment = {
            "id": self._comment_next_id,
            "author": self._current_author(),
            "text": text.strip(),
            "time": datetime.now().strftime("%Y-%m-%d %H:%M"),
            "resolved": False,
            "page": page_idx,
        }
        self._comment_next_id += 1

        self._slide_comments.setdefault(page_idx, []).append(comment)

        # 同步回编辑器
        self._sync_comments_to_editor()

        # 刷新面板
        self._refresh_comment_panel()

        # 自动显示面板
        if self._comment_panel is not None:
            self._comment_panel.setVisible(True)

        self._set_status(
            tr("auto.beeshow_comment_mixin.082f3ad3", "💬 已添加评论 #{0}").format(comment['id']), 2000
        )

    def _current_author(self) -> str:
        """获取当前作者名（从设置读取，默认'当前用户'）"""
        try:
            from beeoffice.settings import AppSettings
            settings = AppSettings()
            return getattr(settings, "user_name", "") or "当前用户"
        except Exception:
            return "当前用户"

    # ==================== 评论面板 ====================
    def _show_comment_panel(self):
        """显示 / 隐藏评论面板"""
        if self._comment_panel is None:
            # 首次创建
            self._comment_panel = CommentPanel(self)
            self._comment_panel.jump_requested.connect(
                self._jump_to_comment_page
            )
            self._comment_panel.edit_requested.connect(
                self._edit_comment
            )
            self._comment_panel.delete_requested.connect(
                self._delete_comment
            )
            self._comment_panel.resolve_requested.connect(
                self._toggle_comment_resolved
            )
            self._comment_panel.close_requested.connect(
                lambda: self._comment_panel.setVisible(False)
            )
            # 加到主布局右侧
            self._add_panel_to_layout(self._comment_panel)

        # 切换可见性
        if self._comment_panel.isVisible():
            self._comment_panel.setVisible(False)
        else:
            self._refresh_comment_panel()
            self._comment_panel.setVisible(True)

    def _add_panel_to_layout(self, panel):
        """
        把面板加到主布局右侧。

        若主布局已用 splitter，则 addWidget 到 splitter 末尾；
        否则用 QHBoxLayout 包裹。这里简化处理：直接 addWidget
        到当前 splitter。
        """
        try:
            # 找到主 splitter（beeshow.py 中创建的）
            if hasattr(self, "_main_splitter"):
                self._main_splitter.addWidget(panel)
                sizes = self._main_splitter.sizes()
                sizes[-1] = 300  # 新面板宽 300
                self._main_splitter.setSizes(sizes)
                return
            # 回退：加到布局末尾
            if self.layout() is not None:
                self.layout().addWidget(panel)
        except Exception as e:
            logging.error(f"添加评论面板失败：{e}")

    def _refresh_comment_panel(self):
        """刷新评论面板列表"""
        if self._comment_panel is None:
            return
        # 展平所有页的评论，附带页索引
        all_comments = []
        for page_idx in sorted(self._slide_comments.keys()):
            for c in self._slide_comments[page_idx]:
                # 附页标题
                title = (
                    self._slide_titles[page_idx]
                    if page_idx < len(self._slide_titles)
                    else f"第 {page_idx + 1} 页"
                )
                all_comments.append({
                    **c,
                    "page_title": title,
                    "page_index": page_idx,
                })
        self._comment_panel.refresh(all_comments)

    # ==================== 评论操作 ====================
    def _jump_to_comment_page(self, comment_id: int):
        """跳转到评论所在页"""
        page_idx = self._find_comment_page(comment_id)
        if page_idx is None:
            return
        if 0 <= page_idx < len(self._slides_html):
            self._current_slide = page_idx
            self._show_slide(page_idx)
            self._set_status(
                tr("auto.beeshow_comment_mixin.5fd13247", "📍 已跳转到第 {0} 页").format(page_idx + 1), 2000
            )

    def _edit_comment(self, comment_id: int):
        """编辑评论"""
        comment, page_idx = self._find_comment(comment_id)
        if comment is None:
            return

        text, ok = QInputDialog.getMultiLineText(
            self, "💬 编辑评论",
            f"第 {page_idx + 1} 页的评论：",
            comment["text"]
        )
        if not ok or not text.strip():
            return

        comment["text"] = text.strip()
        comment["time"] = (
            datetime.now().strftime("%Y-%m-%d %H:%M")
            + "（已编辑）"
        )
        self._sync_comments_to_editor()
        self._refresh_comment_panel()
        self._set_status(tr("auto.beeshow_comment_mixin.25e590f3", "✅ 评论已更新"), 2000)

    def _delete_comment(self, comment_id: int):
        """删除评论（带确认）"""
        comment, page_idx = self._find_comment(comment_id)
        if comment is None:
            return

        reply = QMessageBox.question(
            self, tr("auto.beeshow_comment_mixin.a602a2cf", "删除评论"),
            tr("auto.beeshow_comment_mixin.ca605041", "确定删除这条评论吗？\n\n「{0}」").format(comment['text'][:50]),
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return

        self._slide_comments[page_idx].remove(comment)
        # 空列表则清理键
        if not self._slide_comments[page_idx]:
            del self._slide_comments[page_idx]

        self._sync_comments_to_editor()
        self._refresh_comment_panel()
        self._set_status(tr("auto.beeshow_comment_mixin.34c04064", "✅ 评论已删除"), 2000)

    def _toggle_comment_resolved(self, comment_id: int):
        """切换已解决状态"""
        comment, page_idx = self._find_comment(comment_id)
        if comment is None:
            return

        comment["resolved"] = not comment.get("resolved", False)
        self._sync_comments_to_editor()
        self._refresh_comment_panel()

        status = "已解决" if comment["resolved"] else "未解决"
        self._set_status(tr("auto.beeshow_comment_mixin.0168ca80", "✅ 评论已标记为{status}").format(status=status), 2000)

    # ==================== 查找辅助 ====================
    def _find_comment(self, comment_id: int):
        """查找评论及其所在页"""
        for page_idx, comments in self._slide_comments.items():
            for c in comments:
                if c.get("id") == comment_id:
                    return c, page_idx
        return None, None

    def _find_comment_page(self, comment_id: int):
        """查找评论所在页"""
        _, page_idx = self._find_comment(comment_id)
        return page_idx

    # ==================== 序列化 ====================
    def _sync_comments_to_editor(self):
        """
        把 _slide_comments 同步回 _editor 的 HTML 注释。

        格式：
          每页末尾追加 <!-- comments: [...] -->
        """
        try:
            text = self._editor.toPlainText()
            parts = re.split(r'\n---', text)
            new_parts = []

            for i, part in enumerate(parts):
                # 移除旧 comments 注释
                part = re.sub(
                    r'<!--\s*comments:.*?-->',
                    '',
                    part,
                    flags=re.DOTALL,
                ).strip()

                # 追加新 comments 注释
                comments = self._slide_comments.get(i, [])
                if comments:
                    # 去掉冗余字段（page），只保留必要信息
                    slim = [
                        {
                            "id": c["id"],
                            "author": c["author"],
                            "text": c["text"],
                            "time": c["time"],
                            "resolved": c.get("resolved", False),
                        }
                        for c in comments
                    ]
                    json_str = json.dumps(
                        slim, ensure_ascii=False, separators=(",", ":")
                    )
                    part = part + f"\n<!-- comments: {json_str} -->"

                new_parts.append(part)

            self._editor.blockSignals(True)
            self._editor.setPlainText('\n---\n'.join(new_parts))
            self._editor.blockSignals(False)
        except Exception as e:
            logging.error(f"同步评论到编辑器失败：{e}")

    def _load_comments_from_editor(self, md_text: str):
        """
        从编辑器文本解析评论（在 _update_preview 时调用）。

        :param md_text: 编辑器全文
        """
        try:
            self._slide_comments = {}
            max_id = 0
            parts = re.split(r'\n---', md_text)

            for i, part in enumerate(parts):
                m = re.search(
                    r'<!--\s*comments:\s*(.*?)\s*-->',
                    part,
                    flags=re.DOTALL,
                )
                if not m:
                    continue
                try:
                    data = json.loads(m.group(1))
                    if isinstance(data, list):
                        comments = []
                        for c in data:
                            if not isinstance(c, dict):
                                continue
                            comments.append({
                                "id": int(c.get("id", 0)),
                                "author": str(c.get("author", "")),
                                "text": str(c.get("text", "")),
                                "time": str(c.get("time", "")),
                                "resolved": bool(
                                    c.get("resolved", False)
                                ),
                            })
                            max_id = max(max_id, comments[-1]["id"])
                        if comments:
                            self._slide_comments[i] = comments
                except Exception as e:
                    logging.warning(tr("auto.beeshow_comment_mixin.9194de8b", "解析第 {0} 页评论失败：{1}").format(i + 1, e))

            self._comment_next_id = max_id + 1
        except Exception as e:
            logging.error(f"从编辑器加载评论失败：{e}")

    # ==================== 统计 ====================
    def _get_comment_count(self) -> int:
        """返回评论总数（用于工具栏徽章）"""
        return sum(
            len(comments)
            for comments in self._slide_comments.values()
        )

    def _get_unresolved_comment_count(self) -> int:
        """返回未解决评论数"""
        return sum(
            1
            for comments in self._slide_comments.values()
            for c in comments
            if not c.get("resolved", False)
        )