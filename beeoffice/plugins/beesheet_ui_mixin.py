# beeoffice/plugins/beesheet_ui_mixin.py
"""
蜜算 UI 构建 Mixin

职责（从 beesheet.py 的 __init__ 抽取）：
  - _build_all_toolbars        : 5 行工具栏构建
  - _init_function_reference   : 函数参考表（80+ 函数）
  - _build_table_view          : 主表格视图 + 事件连接 + 填充柄
  - _build_param_tip           : 参数提示气泡
  - _build_completion_popup    : 函数自动补全下拉
  - _build_info_panel          : 底部信息面板
  - _build_shortcuts           : 全部快捷键绑定
  - _init_loaders_and_timers   : ChunkLoader + 自动保存定时器

从 beesheet.py 抽取，降低主文件复杂度。

依赖：
  - PySide6（QWidget / QVBoxLayout / QHBoxLayout / QTableView /
             QHeaderView / QLineEdit / QLabel / QPushButton / QComboBox /
             QSpinBox / QListWidget / QProgressBar / QAbstractButton /
             QShortcut / QKeySequence）
  - ChunkLoader（分块加载线程）
  - CellEditorDelegate（单元格编辑委托）

注意：
  - 所有方法依赖 self.model / self._undo_stack / self._formula_cells /
    self._merged_cells 等属性，
    这些由主类 BeeSheetView.__init__ 在调用本 Mixin 的方法前初始化
  - 主类调用顺序：
      1. 状态初始化（model / _undo_stack / _dirty / ...）
      2. self._build_all_toolbars()
      3. self._build_table_view()
      4. self._build_param_tip()
      5. self._build_completion_popup()
      6. self._build_info_panel()
      7. self._build_shortcuts()
      8. self._init_loaders_and_timers()
"""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTableView, QHeaderView,
    QLineEdit, QLabel, QPushButton, QComboBox, QSpinBox,
    QListWidget, QProgressBar, QAbstractButton,
)
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QShortcut, QKeySequence

from beeoffice.plugins.beesheet_delegate import CellEditorDelegate
from beeoffice.plugins.beesheet_loaders import ChunkLoader


class UIMixin:
    """蜜算 UI 构建相关功能的 Mixin"""

    # ==================== 函数参考表 ====================
    def _init_function_reference(self):
        """初始化函数参考表（80+ Excel 函数，按分类组织）"""
        self.FUNCTION_REFERENCE = {
            "SUM": ("SUM(范围)", "统计"),
            "AVERAGE": ("AVERAGE(范围)", "统计"),
            "MAX": ("MAX(范围)", "统计"),
            "MIN": ("MIN(范围)", "统计"),
            "COUNT": ("COUNT(范围)", "统计"),
            "COUNTA": ("COUNTA(范围)", "统计"),
            "COUNTBLANK": ("COUNTBLANK(范围)", "统计"),
            "MEDIAN": ("MEDIAN(范围)", "统计"),
            "MODE": ("MODE(范围)", "统计"),
            "STDEV": ("STDEV(范围)", "统计"),
            "VAR": ("VAR(范围)", "统计"),
            "LARGE": ("LARGE(范围,排名)", "统计"),
            "SMALL": ("SMALL(范围,排名)", "统计"),
            "RANK": ("RANK(值,范围)", "统计"),
            "IF": ("IF(条件,真,假)", "逻辑"),
            "IFERROR": ("IFERROR(表达式,错误值)", "逻辑"),
            "IFNA": ("IFNA(表达式,NA值)", "逻辑"),
            "AND": ("AND(条件1,...)", "逻辑"),
            "OR": ("OR(条件1,...)", "逻辑"),
            "NOT": ("NOT(条件)", "逻辑"),
            "IFS": ("IFS(条件1,结果1,...)", "逻辑"),
            "VLOOKUP": ("VLOOKUP(值,范围,列,[精确])", "查找"),
            "HLOOKUP": ("HLOOKUP(值,范围,行,[精确])", "查找"),
            "XLOOKUP": ("XLOOKUP(值,查找范围,返回范围)", "查找"),
            "INDEX": ("INDEX(范围,行,[列])", "查找"),
            "MATCH": ("MATCH(值,范围)", "查找"),
            "CHOOSE": ("CHOOSE(索引,值1,...)", "查找"),
            "COUNTIF": ("COUNTIF(范围,条件)", "条件"),
            "SUMIF": ("SUMIF(条件范围,条件,[求和范围])", "条件"),
            "AVERAGEIF": ("AVERAGEIF(条件范围,条件,[平均范围])", "条件"),
            "COUNTIFS": ("COUNTIFS(范围1,条件1,...)", "条件"),
            "SUMIFS": ("SUMIFS(求和范围,范围1,条件1,...)", "条件"),
            "ROUND": ("ROUND(数,位)", "数学"),
            "ROUNDUP": ("ROUNDUP(数,位)", "数学"),
            "ROUNDDOWN": ("ROUNDDOWN(数,位)", "数学"),
            "ABS": ("ABS(数)", "数学"),
            "SQRT": ("SQRT(数)", "数学"),
            "POWER": ("POWER(底,幂)", "数学"),
            "MOD": ("MOD(除数,被除数)", "数学"),
            "INT": ("INT(数)", "数学"),
            "CEILING": ("CEILING(数,基数)", "数学"),
            "FLOOR": ("FLOOR(数,基数)", "数学"),
            "SIN": ("SIN(弧度)", "数学"),
            "COS": ("COS(弧度)", "数学"),
            "TAN": ("TAN(弧度)", "数学"),
            "EXP": ("EXP(数)", "数学"),
            "LN": ("LN(数)", "数学"),
            "PI": ("PI()", "数学"),
            "RAND": ("RAND()", "数学"),
            "RANDBETWEEN": ("RANDBETWEEN(小,大)", "数学"),
            "LEFT": ("LEFT(文本,数)", "文本"),
            "RIGHT": ("RIGHT(文本,数)", "文本"),
            "MID": ("MID(文本,始,数)", "文本"),
            "LEN": ("LEN(文本)", "文本"),
            "TRIM": ("TRIM(文本)", "文本"),
            "UPPER": ("UPPER(文本)", "文本"),
            "LOWER": ("LOWER(文本)", "文本"),
            "PROPER": ("PROPER(文本)", "文本"),
            "CONCATENATE": ("CONCATENATE(文本1,...)", "文本"),
            "TEXTJOIN": ("TEXTJOIN(分隔符,文本1,...)", "文本"),
            "FIND": ("FIND(找什么,在哪里)", "文本"),
            "SEARCH": ("SEARCH(找什么,在哪里)", "文本"),
            "SUBSTITUTE": ("SUBSTITUTE(文本,旧,新)", "文本"),
            "TEXT": ("TEXT(值,格式)", "文本"),
            "VALUE": ("VALUE(文本)", "文本"),
            "REPT": ("REPT(文本,次数)", "文本"),
            "TODAY": ("TODAY()", "日期"),
            "NOW": ("NOW()", "日期"),
            "YEAR": ("YEAR(日期)", "日期"),
            "MONTH": ("MONTH(日期)", "日期"),
            "DAY": ("DAY(日期)", "日期"),
            "DATE": ("DATE(年,月,日)", "日期"),
            "DATEDIF": ("DATEDIF(开始,结束,单位)", "日期"),
            "EDATE": ("EDATE(日期,月数)", "日期"),
            "EOMONTH": ("EOMONTH(日期,月数)", "日期"),
            "WEEKDAY": ("WEEKDAY(日期)", "日期"),
            "NETWORKDAYS": ("NETWORKDAYS(开始,结束)", "日期"),
            "PMT": ("PMT(利率,期数,现值)", "财务"),
            "FV": ("FV(利率,期数,每期,[现值])", "财务"),
            "PV": ("PV(利率,期数,每期,[终值])", "财务"),
            "NPV": ("NPV(利率,范围)", "财务"),
            "IRR": ("IRR(范围)", "财务"),
            "RATE": ("RATE(期数,每期,现值)", "财务"),
            "NPER": ("NPER(利率,每期,现值)", "财务"),
            "SLN": ("SLN(原值,残值,年限)", "财务"),
            "DB": ("DB(原值,残值,年限,期)", "财务"),
        }

    # ==================== 5 行工具栏构建 ====================
    def _build_all_toolbars(self):
        """
        构建 5 行工具栏 + 主表格 + 底部信息面板。

        抽取自原 __init__ 的 UI 构建段，保持控件创建顺序不变。
        """
        # 按钮通用样式
        btn_style = ("QPushButton{background:#EEE;border:1px solid #CCC;"
                     "padding:4px 10px;border-radius:3px}"
                     "QPushButton:hover{background:#FFE0A0}")

        # 顶层工具栏容器
        tc = QVBoxLayout()
        tc.setContentsMargins(0, 0, 0, 0)
        tc.setSpacing(1)

        # ===== 第 1 行：名称框 + fx + 公式栏 + 导入导出 + 进度 =====
        t1 = QHBoxLayout()
        t1.setContentsMargins(4, 2, 4, 2)
        self._name_box = QLabel("A1")
        self._name_box.setMinimumWidth(60)
        self._name_box.setStyleSheet(
            "border:1px solid #CCC;padding:2px 6px;background:#FFF;font-size:12px;"
        )
        t1.addWidget(self._name_box)

        self._fx_btn = QPushButton("fx ▾")
        self._fx_btn.setToolTip("插入函数")
        self._fx_btn.setStyleSheet(
            "QPushButton{background:#FFF3E0;border:1px solid #FFB300;"
            "color:#E65100;font-weight:bold;padding:3px 8px;border-radius:3px;}"
            "QPushButton:hover{background:#FFE0B2;}"
        )
        self._fx_btn.clicked.connect(self._show_fx_dropdown)
        t1.addWidget(self._fx_btn)

        self.formula_bar = QLineEdit()
        self.formula_bar.setPlaceholderText(
            "输入值或公式（输入 = 开始，F1 查看函数帮助）"
        )
        t1.addWidget(self.formula_bar)

        self._preview_label = QLabel("")
        self._preview_label.setMinimumWidth(100)
        self._preview_label.setStyleSheet(
            "QLabel{color:#0D47A1;font-weight:bold;padding:2px 8px;"
            "background:#E3F2FD;border-radius:4px;font-size:13px;}"
        )
        self._preview_label.hide()
        t1.addWidget(self._preview_label)

        btn_import = QPushButton("📂 导入")
        btn_import.setStyleSheet(btn_style)
        btn_import.clicked.connect(self._import_file)
        t1.addWidget(btn_import)

        self._export_btn = QPushButton("💾 导出 ▾")
        self._export_btn.setStyleSheet(btn_style)
        self._export_btn.clicked.connect(self._show_export_menu)
        t1.addWidget(self._export_btn)

        t1.addStretch()

        self._progress_bar = QProgressBar()
        self._progress_bar.setMaximumWidth(150)
        self._progress_bar.setMaximumHeight(16)
        self._progress_bar.setVisible(False)
        t1.addWidget(self._progress_bar)

        # P0-15：加载取消按钮
        self._cancel_load_btn = QPushButton("✕")
        self._cancel_load_btn.setFixedWidth(24)
        self._cancel_load_btn.setToolTip("取消加载")
        self._cancel_load_btn.setStyleSheet(
            "QPushButton{background:#FFEBEE;border:1px solid #F44336;"
            "color:#B71C1C;font-weight:bold;border-radius:3px;}"
            "QPushButton:hover{background:#FFCDD2;}"
        )
        self._cancel_load_btn.setVisible(False)
        self._cancel_load_btn.clicked.connect(self._cancel_large_file_load)
        t1.addWidget(self._cancel_load_btn)

        self.status_label = QLabel("")
        t1.addWidget(self.status_label)
        self.status_label.setCursor(Qt.PointingHandCursor)
        self.status_label.mouseDoubleClickEvent = \
            lambda e: self._show_selection_stats()

        self._stat_btn = QPushButton("📊 统计")
        self._stat_btn.setToolTip("选中多个单元格时显示详细统计")
        self._stat_btn.setStyleSheet(
            "QPushButton{background:#E3F2FD;border:1px solid #2196F3;"
            "color:#0D47A1;padding:3px 10px;border-radius:3px;font-size:12px;}"
            "QPushButton:hover{background:#BBDEFB;}"
        )
        self._stat_btn.clicked.connect(self._show_selection_stats)
        t1.addWidget(self._stat_btn)

        # P1-B：打印预览（实机清点发现蜜算此前**完全没有打印入口**）
        self._print_btn = QPushButton("🖨️ 打印预览")
        self._print_btn.setToolTip(
            "打印当前工作表（分页、跨页重复标题行、缩放适应页宽）\n"
            "选中多个单元格时只打印选中区域"
        )
        self._print_btn.setStyleSheet(
            "QPushButton{background:#E8F5E9;border:1px solid #4CAF50;"
            "color:#1B5E20;padding:3px 10px;border-radius:3px;font-size:12px;}"
            "QPushButton:hover{background:#C8E6C9;}"
        )
        self._print_btn.clicked.connect(self._print_preview)
        t1.addWidget(self._print_btn)

        # R5：AI 助手（公式建议 / 解释问题 / 表格摘要）。
        # 定位"本地优先、可解释"：不追"一键生成整表"，只给建议与解释。
        self._ai_btn = QPushButton("🤖 AI ▾")
        self._ai_btn.setToolTip(
            "AI 助手：\n"
            "· 用中文描述需求 → 公式建议（只给建议，不改数据）\n"
            "· 解释表格问题（事实由本地规则查出）\n"
            "· 生成表格摘要\n"
            "未配置 AI 时会先说明并征求同意，再用本地规则"
        )
        self._ai_btn.setStyleSheet(
            "QPushButton{background:#EDE7F6;border:1px solid #7E57C2;"
            "color:#4527A0;padding:3px 10px;border-radius:3px;font-size:12px;}"
            "QPushButton:hover{background:#D1C4E9;}"
        )
        self._ai_btn.clicked.connect(self._show_sheet_ai_menu)
        t1.addWidget(self._ai_btn)

        tc.addLayout(t1)

        # ===== 第 2 行：排序 / 筛选 / 图表 / 透视表 / 求和 / 插入函数 =====
        self._t2 = QHBoxLayout()
        self._t2.setContentsMargins(4, 2, 4, 2)
        for text, slot in [
            ("🔤 排序", self._show_sort_dialog),
            ("🔍 筛选", self._show_filter_dialog),
            ("📊 图表", self._create_chart),
            ("📊 透视表", self._show_pivot_table),
        ]:
            btn = QPushButton(text)
            btn.setStyleSheet(btn_style)
            btn.clicked.connect(slot)
            self._t2.addWidget(btn)

        btn_sum = QPushButton("Σ 自动求和")
        btn_sum.setToolTip("自动求和（Alt+=）：选中数据后点击，在下方填入 SUM")
        btn_sum.setStyleSheet(btn_style)
        btn_sum.clicked.connect(self._auto_sum)
        self._t2.addWidget(btn_sum)

        btn_fx = QPushButton("ƒx 插入函数")
        btn_fx.setToolTip("从函数列表中选择并插入")
        btn_fx.setStyleSheet(btn_style)
        btn_fx.clicked.connect(self._show_function_picker)
        self._t2.addWidget(btn_fx)

        self._t2.addStretch()
        tc.addLayout(self._t2)

        # ===== 第 3 行：清洗 / 函数 / 查找替换 / 自然语言 / 验证 / 名称 / 审计 =====
        self._t3 = QHBoxLayout()
        self._t3.setContentsMargins(4, 2, 4, 2)
        for text, slot in [
            ("🔧 清洗", self._show_clean_menu),
            ("📚 函数", self._show_function_reference),
            ("🔍 查找替换", self._show_find_replace),
            ("💬 自然语言", self._nl_to_formula),
            ("📋 数据验证", self._show_data_validation_dialog),
            ("🏷️ 名称管理", self._show_name_manager),
            ("🔍 追踪引用", self._trace_precedents),
            ("🔍 追踪从属", self._trace_dependents),
            ("✨ 智能填充", self._flash_fill),
        ]:
            btn = QPushButton(text)
            btn.setStyleSheet(btn_style)
            btn.clicked.connect(slot)
            self._t3.addWidget(btn)
        self._t3.addStretch()
        tc.addLayout(self._t3)

        # ===== 第 4 行：样式 / 兼容性 + 折叠按钮 =====
        self._t4 = QHBoxLayout()
        self._t4.setContentsMargins(4, 2, 4, 2)
        for text, slot in [
            ("🎨 样式", self._show_style_menu),
            ("✓ 兼容性", self._check_excel_compatibility),
        ]:
            btn = QPushButton(text)
            btn.setStyleSheet(btn_style)
            btn.clicked.connect(slot)
            self._t4.addWidget(btn)
        btn_toggle = QPushButton("▲ 隐藏")
        btn_toggle.setStyleSheet("QPushButton{font-size:10px;padding:2px 6px;}")
        btn_toggle.clicked.connect(lambda: self._toggle_toolbars(btn_toggle))
        self._t4.addStretch()
        self._t4.addWidget(btn_toggle)
        tc.addLayout(self._t4)

        # ===== 第 5 行：单元格格式（加粗/斜体/下划线/对齐/数字格式） =====
        self._t5 = QHBoxLayout()
        self._t5.setContentsMargins(4, 2, 4, 2)
        fmt_btn_style = (
            "QPushButton{background:#FFF;border:1px solid #CCC;"
            "padding:3px 8px;border-radius:3px;font-weight:bold;min-width:28px;}"
            "QPushButton:hover{background:#FFE0A0;}"
            "QPushButton:checked{background:#FFB300;color:#000;}"
        )
        self._fmt_bold_btn = QPushButton("B")
        self._fmt_bold_btn.setCheckable(True)
        self._fmt_bold_btn.setToolTip("加粗（Ctrl+B）")
        self._fmt_bold_btn.setStyleSheet(fmt_btn_style)
        self._fmt_bold_btn.clicked.connect(self._toggle_cell_bold)
        self._t5.addWidget(self._fmt_bold_btn)

        self._fmt_italic_btn = QPushButton("I")
        self._fmt_italic_btn.setCheckable(True)
        self._fmt_italic_btn.setToolTip("斜体（Ctrl+I）")
        self._fmt_italic_btn.setStyleSheet(
            fmt_btn_style + "QPushButton{font-style:italic;}"
        )
        self._fmt_italic_btn.clicked.connect(self._toggle_cell_italic)
        self._t5.addWidget(self._fmt_italic_btn)

        self._fmt_underline_btn = QPushButton("U")
        self._fmt_underline_btn.setCheckable(True)
        self._fmt_underline_btn.setToolTip("下划线")
        self._fmt_underline_btn.setStyleSheet(
            fmt_btn_style + "QPushButton{text-decoration:underline;}"
        )
        self._fmt_underline_btn.clicked.connect(self._toggle_cell_underline)
        self._t5.addWidget(self._fmt_underline_btn)

        self._t5.addWidget(QLabel(" | "))

        for label, slot, tip in [
            ("⫷", self._align_cell_left, "左对齐"),
            ("⫸", self._align_cell_center, "居中"),
            ("⫹", self._align_cell_right, "右对齐"),
        ]:
            btn = QPushButton(label)
            btn.setToolTip(tip)
            btn.setStyleSheet(fmt_btn_style)
            btn.clicked.connect(slot)
            self._t5.addWidget(btn)

        self._t5.addWidget(QLabel(" | "))

        self._num_format_combo = QComboBox()
        self._num_format_combo.addItems(
            ["常规", "数值", "货币", "百分比", "千分位", "日期", "文本"]
        )
        self._num_format_combo.setStyleSheet(
            "QComboBox{border:1px solid #CCC;padding:2px 6px;border-radius:3px;}"
        )
        self._num_format_combo.currentTextChanged.connect(self._apply_num_format)
        self._t5.addWidget(QLabel("格式:"))
        self._t5.addWidget(self._num_format_combo)

        self._decimal_spin = QSpinBox()
        self._decimal_spin.setRange(0, 6)
        self._decimal_spin.setValue(2)
        self._decimal_spin.setMaximumWidth(60)
        self._decimal_spin.setToolTip("小数位数")
        self._t5.addWidget(QLabel("小数:"))
        self._t5.addWidget(self._decimal_spin)

        self._t5.addStretch()
        tc.addLayout(self._t5)

        # 暂存到 self，供主类的 layout 组装
        self._toolbar_container = tc

    # ==================== 表格视图 ====================
    def _build_table_view(self):
        """构建主表格视图 + 事件连接 + 填充柄"""
        self.table_view = QTableView()
        self.table_view.setModel(self.model)
        self.table_view.horizontalHeader().setSectionResizeMode(
            QHeaderView.Interactive
        )
        self.table_view.setAlternatingRowColors(True)
        self.table_view.horizontalHeader().setSectionsClickable(True)
        self.table_view.horizontalHeader().sectionClicked.connect(
            self._on_header_clicked
        )
        self.table_view.horizontalHeader().sectionDoubleClicked.connect(
            lambda c: self.table_view.resizeColumnToContents(c)
        )
        self.table_view.verticalScrollBar().valueChanged.connect(
            self._on_scroll_changed
        )
        self.table_view.installEventFilter(self)
        self.table_view.setContextMenuPolicy(Qt.CustomContextMenu)
        self.table_view.customContextMenuRequested.connect(
            lambda pos: self._show_fill_menu(
                self.table_view.viewport().mapToGlobal(pos)
            )
        )
        self.table_view.clicked.connect(self._on_cell_clicked)
        self.table_view.doubleClicked.connect(self._on_cell_double_clicked)
        self.table_view.setCornerButtonEnabled(True)

        corner_btn = self.table_view.findChild(QAbstractButton)
        if corner_btn:
            corner_btn.clicked.connect(self.table_view.selectAll)

        header = self.table_view.horizontalHeader()
        header.setContextMenuPolicy(Qt.CustomContextMenu)
        header.customContextMenuRequested.connect(self._show_header_context_menu)

        vheader = self.table_view.verticalHeader()
        vheader.setContextMenuPolicy(Qt.CustomContextMenu)
        vheader.customContextMenuRequested.connect(self._show_row_header_menu)

        # 单元格编辑委托
        self._delegate = CellEditorDelegate(self)
        self.table_view.setItemDelegate(self._delegate)

        # 公式栏事件
        self.formula_bar.returnPressed.connect(self._on_formula_enter)
        self.formula_bar.textChanged.connect(self._on_formula_text_changed)
        self.formula_bar.cursorPositionChanged.connect(
            self._on_formula_cursor_moved
        )
        self.formula_bar.editingFinished.connect(self._clear_highlight)

        # 选中变化事件
        self.table_view.selectionModel().currentChanged.connect(
            self._on_cell_selected
        )
        self.table_view.selectionModel().selectionChanged.connect(
            self._on_selection_changed
        )

        # ===== 填充柄 =====
        self._fill_handle = QWidget(self.table_view)
        self._fill_handle.setFixedSize(6, 6)
        self._fill_handle.setStyleSheet(
            "QWidget{background:#FFB300;border:1px solid #E65100;}"
        )
        self._fill_handle.setCursor(Qt.CrossCursor)
        self._fill_handle.hide()
        self._fill_handle.mousePressEvent = self._fill_handle_press
        self._fill_handle.mouseMoveEvent = self._fill_handle_move
        self._fill_handle.mouseReleaseEvent = self._fill_handle_release
        self._fill_start_range = None
        self._fill_direction = None
        self._fill_target = None

    # ==================== 参数提示气泡 ====================
    def _build_param_tip(self):
        """构建参数提示气泡（输入函数时显示语法提示）"""
        self._param_tip = QLabel(self)
        self._param_tip.setWindowFlags(Qt.ToolTip | Qt.FramelessWindowHint)
        self._param_tip.setStyleSheet(
            "QLabel{background:#333;color:#FFF;padding:6px 10px;"
            "border-radius:4px;font-size:12px;}"
        )
        self._param_tip.hide()
        self._last_func_tip = ""

    # ==================== 函数自动补全下拉 ====================
    def _build_completion_popup(self):
        """构建函数自动补全下拉列表"""
        self._completion_popup = QListWidget()
        self._completion_popup.setWindowFlags(Qt.Popup | Qt.FramelessWindowHint)
        self._completion_popup.setMaximumHeight(350)
        self._completion_popup.itemClicked.connect(self._on_completion_selected)
        self._completion_popup.hide()

    # ==================== 底部信息面板 ====================
    def _build_info_panel(self):
        """构建底部信息面板（显示单元格坐标 / 值 / 公式 / 批注）"""
        self._info_panel = QWidget()
        self._info_panel.setStyleSheet(
            "QWidget{background:#FAFAFA;border-top:1px solid #DDD;}"
        )
        info_layout = QHBoxLayout(self._info_panel)
        info_layout.setContentsMargins(8, 4, 8, 4)
        info_layout.setSpacing(12)

        self._info_cell = QLabel("")
        self._info_value = QLabel("")
        self._info_formula = QLabel("")
        self._info_comment = QLabel("")
        for w in [self._info_cell, self._info_value,
                  self._info_formula, self._info_comment]:
            w.setStyleSheet("QLabel{color:#555;font-size:12px;}")
        info_layout.addWidget(self._info_cell)
        info_layout.addWidget(self._info_value)
        info_layout.addWidget(self._info_formula)
        info_layout.addWidget(self._info_comment)
        info_layout.addStretch()
        self._info_panel.setMaximumHeight(28)
        self._info_panel.setVisible(False)

    # ==================== 快捷键绑定 ====================
    def _build_shortcuts(self):
        """绑定所有快捷键"""
        # ⚠️ **这里不再注册 Ctrl+Z / Ctrl+Y**（实测踩过）：
        # `menus.py:247,252` 已为「撤销/重做」注册了窗口级 QAction，这里再注册一遍
        # 会同键 → Qt 报 `Ambiguous shortcut overload: Ctrl+Z / Ctrl+Y`，
        # **两个都不触发** → 蜜算里按 Ctrl+Z 完全失效。
        # （改成 `WidgetWithChildrenShortcut` 也**不行**：Qt 的上下文只用于匹配、
        #   不做优先级排序，两个都匹配就判歧义。）
        # 现在统一由菜单动作负责：`menus._resolve_editor` 认"自己实现了
        # undo/redo 的视图"，于是对蜜算会直接把视图给它，调用它的命令栈。
        QShortcut(QKeySequence("Ctrl+D"), self).activated.connect(
            self._shortcut_fill_down
        )
        QShortcut(QKeySequence("Ctrl+R"), self).activated.connect(
            self._shortcut_fill_right
        )
        # P1-B：打印预览（与蜜写保持一致用 Ctrl+P）
        QShortcut(QKeySequence("Ctrl+P"), self).activated.connect(
            self._print_preview
        )
        QShortcut(QKeySequence("Ctrl+H"), self).activated.connect(
            self._show_find_replace
        )
        QShortcut(QKeySequence("F2"), self).activated.connect(self._f2_edit)
        QShortcut(QKeySequence("F1"), self).activated.connect(self._f1_help)
        QShortcut(QKeySequence("Ctrl+;"), self).activated.connect(
            lambda: self._insert_date_time('date')
        )
        QShortcut(QKeySequence("Ctrl+Shift+:"), self).activated.connect(
            lambda: self._insert_date_time('time')
        )
        QShortcut(QKeySequence("Alt+="), self).activated.connect(self._auto_sum)
        QShortcut(QKeySequence("Ctrl+B"), self).activated.connect(
            self._toggle_cell_bold
        )
        QShortcut(QKeySequence("Ctrl+I"), self).activated.connect(
            self._toggle_cell_italic
        )
        QShortcut(QKeySequence("Ctrl+U"), self).activated.connect(
            self._toggle_cell_underline
        )
        QShortcut(QKeySequence("Ctrl+G"), self).activated.connect(
            self._show_goto_dialog
        )
        QShortcut(QKeySequence("Ctrl+E"), self).activated.connect(
            self._flash_fill
        )
        QShortcut(QKeySequence("Ctrl+["), self).activated.connect(
            self._trace_precedents
        )
        QShortcut(QKeySequence("Ctrl+]"), self).activated.connect(
            self._trace_dependents
        )
        QShortcut(QKeySequence("Ctrl+Shift+["), self).activated.connect(
            self._clear_audit
        )

    # ==================== 加载器 + 定时器 ====================
    def _init_loaders_and_timers(self):
        """初始化分块加载器和自动保存定时器"""
        # 分块加载器（滚动时按需加载）
        # 优化规划 §2.4：数据在工作线程准备（chunk_ready），
        # 模型合并在主线程完成（_on_chunk_ready → model.apply_chunk）。
        self._chunk_loader = ChunkLoader(self.model, self)
        self._chunk_loader.chunk_ready.connect(self._on_chunk_ready)
        self._chunk_loader.progress.connect(self._on_loading_progress)

        # 自动保存定时器（每 5 分钟）
        self._auto_save_timer = QTimer(self)
        self._auto_save_timer.timeout.connect(self._auto_save)
        self._auto_save_timer.start(300000)