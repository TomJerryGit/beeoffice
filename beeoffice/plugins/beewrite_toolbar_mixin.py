# beeoffice/plugins/beewrite_toolbar_mixin.py
"""
蜜写工具栏构建 Mixin

本次更新：
  - 对齐符号改为文字 + 箭头，避免 Windows 字体显示为 ≪ ≫ ≪
  - 段落对齐用 ⬅/↔/➡，单元格对齐用 ▦ 前缀区分
  - 状态栏行列标签加最小宽度，避免被截断
  - 格式刷按钮配色：未激活灰底，激活橙底
  - _build_toolbar2 末尾加折叠按钮
  - 保存按钮改为动态文字：蜜写文档显示"💾 保存 MD"，Word 文档显示"💾 保存 Word"
"""
from PySide6.QtWidgets import (
    QToolBar,
    QComboBox,
    QLabel,
    QPushButton,
    QHBoxLayout,
)
from beeoffice.i18n import tr


_TOOLBAR_STYLE = (
    "QToolBar{background:#FFF;border-bottom:1px solid #EEE;"
    "padding:2px 4px;spacing:4px}"
    "QToolButton{padding:4px 8px;border:1px solid transparent;"
    "border-radius:3px;font-size:12px}"
    "QToolButton:hover{background:#FFF3E0;border-color:#FFB300}"
    "QToolButton:checked{background:#FFB300;color:#000}"
    "QComboBox,QSpinBox{border:1px solid #CCC;border-radius:3px;"
    "padding:2px 4px;min-width:50px}"
)


class ToolbarMixin:
    """蜜写工具栏构建 Mixin"""

    # ------------------------------------------------------------------
    # 第 1 行工具栏：格式
    # ------------------------------------------------------------------
    def _build_toolbar1(self) -> QToolBar:
        """构建格式工具栏"""
        toolbar = QToolBar()
        toolbar.setStyleSheet(_TOOLBAR_STYLE)

        # ---------- 字体 ----------
        self._font_combo = QComboBox()
        self._font_combo.addItems([
            "微软雅黑", "宋体", "黑体", "仿宋", "楷体",
            "Arial", "Times New Roman", "Consolas",
        ])
        self._font_combo.currentTextChanged.connect(self._on_font_family)
        toolbar.addWidget(QLabel(tr("auto.beewrite_toolbar_mixin.b50d4d83", "字体")))
        toolbar.addWidget(self._font_combo)

        # ---------- 字号 ----------
        self._size_combo = QComboBox()
        self._size_combo.addItems([
            "12", "14", "16", "18", "20", "24", "28", "36", "48", "72",
        ])
        self._size_combo.setCurrentText("14")
        self._size_combo.currentTextChanged.connect(self._on_font_size)
        toolbar.addWidget(QLabel(tr("auto.beewrite_toolbar_mixin.576ccdb1", "字号")))
        toolbar.addWidget(self._size_combo)
        toolbar.addSeparator()

        # ---------- 粗体 / 斜体 / 下划线 / 删除线 ----------
        self._bold_btn = QPushButton("B")
        self._bold_btn.setToolTip(tr("auto.beewrite_toolbar_mixin.640df3f2", "粗体 (Ctrl+B)"))
        self._bold_btn.setCheckable(True)
        self._bold_btn.clicked.connect(self._toggle_bold)
        toolbar.addWidget(self._bold_btn)

        self._italic_btn = QPushButton("I")
        self._italic_btn.setToolTip(tr("auto.beewrite_toolbar_mixin.2c03400c", "斜体 (Ctrl+I)"))
        self._italic_btn.setCheckable(True)
        self._italic_btn.clicked.connect(self._toggle_italic)
        toolbar.addWidget(self._italic_btn)

        self._underline_btn = QPushButton("U")
        self._underline_btn.setToolTip(tr("auto.beewrite_toolbar_mixin.9398606c", "下划线 (Ctrl+U)"))
        self._underline_btn.setCheckable(True)
        self._underline_btn.clicked.connect(self._toggle_underline)
        toolbar.addWidget(self._underline_btn)

        self._strike_btn = QPushButton("S")
        self._strike_btn.setToolTip(tr("auto.beewrite_toolbar_mixin.c85de9e5", "删除线"))
        self._strike_btn.setCheckable(True)
        self._strike_btn.clicked.connect(self._toggle_strikethrough)
        toolbar.addWidget(self._strike_btn)
        toolbar.addSeparator()

        # ---------- 文字色 / 高亮 / 底纹 ----------
        btn_fg = QPushButton(tr("auto.beewrite_toolbar_mixin.c967b894", "🎨 文字色"))
        btn_fg.clicked.connect(self._set_text_color)
        toolbar.addWidget(btn_fg)

        btn_bg = QPushButton(tr("auto.beewrite_toolbar_mixin.2fc3481a", "🖍️ 高亮"))
        btn_bg.clicked.connect(self._set_bg_color)
        toolbar.addWidget(btn_bg)

        btn_char_shade = QPushButton(tr("auto.beewrite_toolbar_mixin.7e1c4f59", "▦ 底纹"))
        btn_char_shade.setToolTip(tr("auto.beewrite_toolbar_mixin.8bdfffbd", "字符底纹 / 边框"))
        btn_char_shade.clicked.connect(self._show_char_shade_dialog)
        toolbar.addWidget(btn_char_shade)
        toolbar.addSeparator()

        # ---------- 段落对齐（改用文字 + 箭头） ----------
        btn_left = QPushButton(tr("auto.beewrite_toolbar_mixin.3acd8eab", "⬅ 左"))
        btn_left.setToolTip(tr("auto.beewrite_toolbar_mixin.d6793ee1", "段落左对齐"))
        btn_left.clicked.connect(self._align_left)
        toolbar.addWidget(btn_left)

        btn_center = QPushButton(tr("auto.beewrite_toolbar_mixin.0739dfaf", "↔ 中"))
        btn_center.setToolTip(tr("auto.beewrite_toolbar_mixin.074025f9", "段落居中"))
        btn_center.clicked.connect(self._align_center)
        toolbar.addWidget(btn_center)

        btn_right = QPushButton(tr("auto.beewrite_toolbar_mixin.ebde918c", "➡ 右"))
        btn_right.setToolTip(tr("auto.beewrite_toolbar_mixin.e566470f", "段落右对齐"))
        btn_right.clicked.connect(self._align_right)
        toolbar.addWidget(btn_right)
        toolbar.addSeparator()

        # ---------- 样式 / 段落 ----------
        self._head_combo = QComboBox()
        self._head_combo.addItems([
            "正文", "标题 1", "标题 2", "标题 3", "标题 4",
        ])
        self._head_combo.currentTextChanged.connect(self._on_heading)
        toolbar.addWidget(QLabel(tr("auto.beewrite_toolbar_mixin.393a6c91", "样式")))
        toolbar.addWidget(self._head_combo)

        btn_para = QPushButton(tr("auto.beewrite_toolbar_mixin.2e58ab4d", "¶ 段落"))
        btn_para.setToolTip(tr("auto.beewrite_toolbar_mixin.e8732395", "段落格式（行距、缩进、段前后）"))
        btn_para.clicked.connect(self._show_paragraph_dialog)
        toolbar.addWidget(btn_para)
        toolbar.addSeparator()

        # ---------- 格式刷（配色：未激活灰底，激活橙底） ----------
        self._fmt_btn = QPushButton(tr("auto.beewrite_toolbar_mixin.c2cb36d3", "🖌️ 格式刷"))
        self._fmt_btn.setToolTip(tr("auto.beewrite_toolbar_mixin.4d946097", "格式刷：复制格式 → 选中文字自动应用"))
        self._fmt_btn.setCheckable(True)
        self._fmt_btn.setStyleSheet(
            "QPushButton{background:#FAFAFA;border:1px solid #DDD;"
            "color:#555;font-weight:bold;padding:4px 12px;border-radius:4px;}"
            "QPushButton:checked{background:#FFB300;color:#000;"
            "border-color:#FF8F00;}"
            "QPushButton:hover{background:#FFF3E0;border-color:#FFB300;}"
        )
        self._fmt_btn.clicked.connect(self._toggle_format_painter)
        toolbar.addWidget(self._fmt_btn)
        toolbar.addSeparator()

        # ---------- AI 辅助 ----------
        self._ai_btn = QPushButton("🤖 AI")
        self._ai_btn.setToolTip(tr("auto.beewrite_toolbar_mixin.955f6245", "AI 辅助：续写 / 润色 / 总结 / 关键词"))
        self._ai_btn.setStyleSheet(
            "QPushButton{background:#E3F2FD;border:1px solid #2196F3;"
            "color:#0D47A1;padding:4px 10px;border-radius:3px}"
            "QPushButton:hover{background:#BBDEFB}"
        )
        self._ai_btn.clicked.connect(self._show_ai_menu)
        toolbar.addWidget(self._ai_btn)

        return toolbar

    # ------------------------------------------------------------------
    # 第 2 行工具栏：插入
    # ------------------------------------------------------------------
    def _build_toolbar2(self) -> QToolBar:
        """构建插入工具栏"""
        toolbar = QToolBar()
        toolbar.setStyleSheet(_TOOLBAR_STYLE)

        # ---------- 列表 ----------
        btn_ul = QPushButton(tr("auto.beewrite_toolbar_mixin.7d9b5150", "• 列表"))
        btn_ul.clicked.connect(self._insert_list)
        toolbar.addWidget(btn_ul)

        btn_ol = QPushButton(tr("auto.beewrite_toolbar_mixin.1cafe2ca", "1. 编号"))
        btn_ol.clicked.connect(self._insert_ordered_list)
        toolbar.addWidget(btn_ol)

        btn_multilist = QPushButton(tr("auto.beewrite_toolbar_mixin.b987a5e0", "1.1.1 多级 ▾"))
        btn_multilist.setToolTip(tr("auto.beewrite_toolbar_mixin.1aa7b084", "多级列表"))
        btn_multilist.clicked.connect(self._show_multilist_menu)
        toolbar.addWidget(btn_multilist)
        toolbar.addSeparator()

        # ---------- 表格 / Excel / 图片 / 公式 ----------
        btn_table = QPushButton(tr("auto.beewrite_toolbar_mixin.800c46ee", "📋 表格 ▾"))
        btn_table.setToolTip(tr("auto.beewrite_toolbar_mixin.953d06b8", "表格操作菜单"))
        btn_table.clicked.connect(self._show_table_menu)
        toolbar.addWidget(btn_table)

        btn_excel = QPushButton(tr("auto.beewrite_toolbar_mixin.d861904c", "📊 插入Excel数据"))
        btn_excel.clicked.connect(self._insert_excel_data)
        toolbar.addWidget(btn_excel)

        btn_image = QPushButton(tr("auto.beewrite_toolbar_mixin.77aa922c", "🖼️ 图片"))
        btn_image.setToolTip(tr("auto.beewrite_toolbar_mixin.e3f6a1c3", "插入/编辑图片"))
        btn_image.clicked.connect(self._insert_image)
        toolbar.addWidget(btn_image)

        btn_formula = QPushButton(tr("auto.beewrite_toolbar_mixin.885e30d5", "∑ 公式"))
        btn_formula.setToolTip(tr("auto.beewrite_toolbar_mixin.1b6b04e2", "插入数学公式（LaTeX）"))
        btn_formula.clicked.connect(self._insert_formula)
        toolbar.addWidget(btn_formula)
        toolbar.addSeparator()

        # ---------- 单元格对齐（用 ▦ 前缀区分段落对齐） ----------
        for label, align, tip in [
            ("▦⬅", "left", "单元格左对齐"),
            ("▦↔", "center", "单元格居中"),
            ("▦➡", "right", "单元格右对齐"),
        ]:
            btn_align = QPushButton(label)
            btn_align.setToolTip(tip)
            btn_align.setStyleSheet(
                "QPushButton{min-width:26px;padding:3px 8px;}"
            )
            btn_align.clicked.connect(
                lambda checked=False, a=align: self._cell_align(a)
            )
            toolbar.addWidget(btn_align)

        # ---------- 合并 / 拆分 / 底色 ----------
        btn_merge = QPushButton(tr("auto.beewrite_toolbar_mixin.6625bce7", "🔗 合并"))
        btn_merge.setToolTip(tr("auto.beewrite_toolbar_mixin.e6e86280", "合并选中的单元格"))
        btn_merge.clicked.connect(self._cell_merge_toolbar)
        toolbar.addWidget(btn_merge)

        btn_split = QPushButton(tr("auto.beewrite_toolbar_mixin.436d96fb", "🔲 拆分"))
        btn_split.setToolTip(tr("auto.beewrite_toolbar_mixin.2cb8f9c2", "拆分合并的单元格"))
        btn_split.clicked.connect(self._cell_split_toolbar)
        toolbar.addWidget(btn_split)

        btn_cell_bg = QPushButton(tr("auto.beewrite_toolbar_mixin.cb6930e0", "🎨 底色"))
        btn_cell_bg.setToolTip(tr("auto.beewrite_toolbar_mixin.d3a9f925", "设置单元格背景色"))
        btn_cell_bg.clicked.connect(self._cell_bg_toolbar)
        toolbar.addWidget(btn_cell_bg)
        toolbar.addSeparator()

        # ---------- 分割线 / 分页符 / 分节符 / 日期 ----------
        btn_line = QPushButton(tr("auto.beewrite_toolbar_mixin.985282b3", "— 分割线"))
        btn_line.clicked.connect(self._insert_horizontal_line)
        toolbar.addWidget(btn_line)

        btn_page = QPushButton(tr("auto.beewrite_toolbar_mixin.ccf731b3", "📄 分页符"))
        btn_page.clicked.connect(self._insert_page_break)
        toolbar.addWidget(btn_page)

        btn_section = QPushButton(tr("auto.beewrite_toolbar_mixin.a90abd6b", "§ 分节符"))
        btn_section.setToolTip(tr("auto.beewrite_toolbar_mixin.47e63c9b", "插入分节符（用于改变页面设置）"))
        btn_section.clicked.connect(self._insert_section_break)
        toolbar.addWidget(btn_section)

        btn_date = QPushButton(tr("auto.beewrite_toolbar_mixin.02456141", "📅 日期"))
        btn_date.clicked.connect(self._insert_date)
        toolbar.addWidget(btn_date)
        toolbar.addSeparator()

        # ---------- 页眉 / 页脚 / 目录 ----------
        btn_header = QPushButton(tr("auto.beewrite_toolbar_mixin.d60394f8", "📋 页眉"))
        btn_header.clicked.connect(self._insert_header)
        toolbar.addWidget(btn_header)

        btn_footer = QPushButton(tr("auto.beewrite_toolbar_mixin.3642bd37", "📋 页脚"))
        btn_footer.clicked.connect(self._insert_footer)
        toolbar.addWidget(btn_footer)

        btn_toc = QPushButton(tr("auto.beewrite_toolbar_mixin.56c3b0ad", "📑 目录"))
        btn_toc.clicked.connect(self._insert_toc)
        toolbar.addWidget(btn_toc)

        btn_compare = QPushButton(tr("auto.beewrite_toolbar_mixin.75b56e4f", "📊 对比"))
        btn_compare.clicked.connect(self._compare_with_original)
        toolbar.addWidget(btn_compare)
        toolbar.addSeparator()

        # ---------- 批注 / 批注栏 ----------
        btn_comment = QPushButton(tr("auto.beewrite_toolbar_mixin.f93c22f0", "💬 批注"))
        btn_comment.setToolTip(tr("auto.beewrite_toolbar_mixin.3c21ab92", "给选中文字添加批注 (Ctrl+Alt+M)"))
        btn_comment.clicked.connect(self._add_comment)
        toolbar.addWidget(btn_comment)

        btn_comment_panel = QPushButton(tr("auto.beewrite_toolbar_mixin.4aad91ea", "📋 批注栏"))
        btn_comment_panel.setToolTip(tr("auto.beewrite_toolbar_mixin.25914250", "显示/隐藏批注面板"))
        btn_comment_panel.clicked.connect(self._toggle_comment_panel)
        toolbar.addWidget(btn_comment_panel)
        toolbar.addSeparator()

        # ---------- 修订 ----------
        self._btn_revision = QPushButton(tr("auto.beewrite_toolbar_mixin.9ded60d7", "📝 修订"))
        self._btn_revision.setCheckable(True)
        self._btn_revision.setToolTip(tr("auto.beewrite_toolbar_mixin.ef083c7a", "开启/关闭修订模式 (Ctrl+Shift+R)"))
        self._btn_revision.clicked.connect(self._toggle_revision)
        toolbar.addWidget(self._btn_revision)

        btn_revision_diff = QPushButton(tr("auto.beewrite_toolbar_mixin.5212c0ff", "📊 查看修改"))
        btn_revision_diff.setToolTip(tr("auto.beewrite_toolbar_mixin.7a22bc5c", "查看当前修改（对比基线）"))
        btn_revision_diff.clicked.connect(self._show_revision_diff)
        toolbar.addWidget(btn_revision_diff)
        toolbar.addSeparator()

        # ---------- 链接 / 交叉引用 ----------
        btn_link_mgr = QPushButton(tr("auto.beewrite_toolbar_mixin.c2b89668", "🔗 链接"))
        btn_link_mgr.setToolTip(tr("auto.beewrite_toolbar_mixin.86598838", "管理文档中的超链接"))
        btn_link_mgr.clicked.connect(self._show_hyperlink_manager)
        toolbar.addWidget(btn_link_mgr)

        btn_crossref = QPushButton(tr("auto.beewrite_toolbar_mixin.7d7a59b5", "🔢 交叉引用"))
        btn_crossref.setToolTip(tr("auto.beewrite_toolbar_mixin.ec77d41b", "引用文档中的标题"))
        btn_crossref.clicked.connect(self._show_crossref_dialog)
        toolbar.addWidget(btn_crossref)
        toolbar.addSeparator()

        # ---------- 文本框 / 水印 / 页码 ----------
        btn_textbox = QPushButton(tr("auto.beewrite_toolbar_mixin.09ca8ed1", "📦 文本框"))
        btn_textbox.setToolTip(tr("auto.beewrite_toolbar_mixin.d54902b0", "插入带背景色的文本框"))
        btn_textbox.clicked.connect(self._insert_textbox)
        toolbar.addWidget(btn_textbox)

        btn_watermark = QPushButton(tr("auto.beewrite_toolbar_mixin.059e4a6c", "💧 水印"))
        btn_watermark.setToolTip(tr("auto.beewrite_toolbar_mixin.f495ea68", "设置导出 PDF 时的水印"))
        btn_watermark.clicked.connect(self._set_watermark)
        toolbar.addWidget(btn_watermark)

        btn_page_num = QPushButton(tr("auto.beewrite_toolbar_mixin.d4937e74", "📄 页码"))
        btn_page_num.setToolTip(tr("auto.beewrite_toolbar_mixin.b27d2dec", "设置导出 PDF 时的页码"))
        btn_page_num.clicked.connect(self._set_page_number)
        toolbar.addWidget(btn_page_num)
        toolbar.addSeparator()

        # ---------- 大纲 / 阅读 / 双屏 ----------
        btn_outline = QPushButton(tr("auto.beewrite_toolbar_mixin.a73823a5", "📑 大纲"))
        btn_outline.setToolTip(tr("auto.beewrite_toolbar_mixin.a6c808cc", "显示/隐藏大纲导航 (Ctrl+Shift+O)"))
        btn_outline.clicked.connect(self._toggle_outline)
        toolbar.addWidget(btn_outline)

        btn_reading = QPushButton(tr("auto.beewrite_toolbar_mixin.30038a78", "📖 阅读"))
        btn_reading.setToolTip(tr("auto.beewrite_toolbar_mixin.3ccad581", "切换阅读模式（F11）"))
        btn_reading.clicked.connect(self._toggle_reading_mode)
        toolbar.addWidget(btn_reading)

        btn_compare_split = QPushButton(tr("auto.beewrite_toolbar_mixin.673a00bd", "📊 双屏"))
        btn_compare_split.setToolTip(tr("auto.beewrite_toolbar_mixin.e9fe01cc", "在当前窗口分屏对比"))
        btn_compare_split.clicked.connect(self._toggle_split_view)
        toolbar.addWidget(btn_compare_split)

        # ---------- 折叠按钮 ----------
        toolbar.addSeparator()
        self._collapse_btn = QPushButton(tr("auto.beewrite_toolbar_mixin.bf03e410", "▲ 收起"))
        self._collapse_btn.setToolTip(tr("auto.beewrite_toolbar_mixin.dd1591b5", "折叠 / 展开插入工具栏"))
        self._collapse_btn.setStyleSheet(
            "QPushButton{font-size:10px;padding:2px 6px;"
            "border:1px solid #DDD;border-radius:3px;}"
            "QPushButton:hover{background:#FFF3E0;border-color:#FFB300;}"
        )
        self._collapse_btn.clicked.connect(self._toggle_toolbars)
        toolbar.addWidget(self._collapse_btn)

        return toolbar

    # ------------------------------------------------------------------
    # 模式切换栏
    # ------------------------------------------------------------------
    def _build_mode_toolbar(self) -> QHBoxLayout:
        """构建模式切换栏（Markdown / 所见即所得）"""
        layout = QHBoxLayout()
        layout.setContentsMargins(4, 4, 4, 4)

        bs = (
            "QPushButton{padding:6px 14px;border:1px solid #DDD;"
            "border-radius:4px;background:#FAFAFA;font-size:12px}"
            "QPushButton:checked{background:#FFB300;color:#000;"
            "border-color:#FF8F00;font-weight:bold}"
            "QPushButton:hover{background:#FFE0B2}"
        )

        self._md_btn = QPushButton("📝 Markdown")
        self._md_btn.setCheckable(True)
        self._md_btn.setChecked(True)
        self._md_btn.setStyleSheet(bs)
        self._md_btn.clicked.connect(self._on_md_clicked)
        layout.addWidget(self._md_btn)

        self._rich_btn = QPushButton(tr("auto.beewrite_toolbar_mixin.bd2172d6", "✨ 所见即所得"))
        self._rich_btn.setCheckable(True)
        self._rich_btn.setStyleSheet(bs)
        self._rich_btn.clicked.connect(self._on_rich_clicked)
        layout.addWidget(self._rich_btn)

        layout.addStretch()
        return layout

    # ------------------------------------------------------------------
    # 导出快捷栏（保存按钮动态文字）
    # ------------------------------------------------------------------
    def _build_quick_toolbar(self) -> QHBoxLayout:
        """构建导出快捷栏（保存按钮文字随 _doc_kind 动态变化）"""
        layout = QHBoxLayout()
        layout.setContentsMargins(4, 2, 4, 2)

        btn_pdf = QPushButton(tr("auto.beewrite_toolbar_mixin.fdcdc1c8", "📄 导出 PDF"))
        btn_pdf.clicked.connect(self.export_pdf)
        layout.addWidget(btn_pdf)

        btn_docx = QPushButton(tr("auto.beewrite_toolbar_mixin.e59ac0c1", "📝 导出 Word"))
        btn_docx.clicked.connect(self.export_docx)
        layout.addWidget(btn_docx)

        # 保存按钮：文字随文档类型变化
        self._save_btn = QPushButton(tr("auto.beewrite_toolbar_mixin.ec9aa4b7", "💾 保存"))
        self._save_btn.setToolTip(tr("auto.beewrite_toolbar_mixin.19162860", "保存 (Ctrl+S)"))
        self._save_btn.clicked.connect(self.save)
        layout.addWidget(self._save_btn)

        btn_tpl = QPushButton(tr("auto.beewrite_toolbar_mixin.c9b2543a", "📋 存为模板"))
        btn_tpl.clicked.connect(self.save_as_template)
        layout.addWidget(btn_tpl)

        btn_page_setup = QPushButton(tr("auto.beewrite_toolbar_mixin.4638ca51", "📄 页面设置"))
        btn_page_setup.clicked.connect(self._show_page_setup_dialog)
        layout.addWidget(btn_page_setup)

        btn_print = QPushButton(tr("auto.beewrite_toolbar_mixin.ef39d897", "🖨️ 打印预览"))
        btn_print.clicked.connect(self._print_preview)
        layout.addWidget(btn_print)

        layout.addStretch()

        # 首次构建后同步一次按钮文字
        self._update_save_btn_text()
        return layout

    def _update_save_btn_text(self):
        """根据文档类型更新保存按钮文字"""
        if not hasattr(self, "_save_btn"):
            return
        kind = getattr(self, "_doc_kind", "markdown")
        if kind == "word":
            self._save_btn.setText(tr("auto.beewrite_toolbar_mixin.8f6815c8", "💾 保存 Word"))
            self._save_btn.setToolTip(tr("auto.beewrite_toolbar_mixin.ee167226", "保存为 Word 文档 (Ctrl+S)"))
        else:
            self._save_btn.setText(tr("auto.beewrite_toolbar_mixin.e566383d", "💾 保存 MD"))
            self._save_btn.setToolTip(tr("auto.beewrite_toolbar_mixin.db84d6ff", "保存为 Markdown 文档 (Ctrl+S)"))

    # ------------------------------------------------------------------
    # 状态栏
    # ------------------------------------------------------------------
    def _build_status_bar(self) -> QHBoxLayout:
        """构建状态栏（字数 / 字符 / 行列）"""
        layout = QHBoxLayout()
        layout.setContentsMargins(8, 2, 8, 2)
        layout.addStretch()

        self._word_count_label = QLabel(tr("auto.beewrite_toolbar_mixin.ea64ed9b", "字数：0"))
        self._word_count_label.setStyleSheet(
            "QLabel{color:#666;font-size:12px;padding:0 12px;}"
        )
        layout.addWidget(self._word_count_label)

        self._char_count_label = QLabel(tr("auto.beewrite_toolbar_mixin.fd608933", "字符：0"))
        self._char_count_label.setStyleSheet(
            "QLabel{color:#666;font-size:12px;padding:0 12px;}"
        )
        layout.addWidget(self._char_count_label)

        self._cursor_pos_label = QLabel(tr("auto.beewrite_toolbar_mixin.001ceca9", "行 1 列 1"))
        self._cursor_pos_label.setMinimumWidth(120)
        self._cursor_pos_label.setStyleSheet(
            "QLabel{color:#666;font-size:12px;padding:0 12px;"
            "border-left:1px solid #DDD;}"
        )
        layout.addWidget(self._cursor_pos_label)

        return layout