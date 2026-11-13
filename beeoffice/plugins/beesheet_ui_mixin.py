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
    self._merged_cells / self._frozen_rows / self._frozen_cols 等属性，
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
import logging

import pandas as pd

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTableView, QHeaderView,
    QLineEdit, QLabel, QPushButton, QComboBox, QSpinBox,
    QListWidget, QAbstractItemView, QProgressBar, QAbstractButton,
    QGroupBox, QTabBar, QStackedWidget, QFrame, QSizePolicy, QStyle, QToolButton,
)
from PySide6.QtCore import Qt, QTimer, QSettings, QSize
from PySide6.QtGui import QFont, QShortcut, QKeySequence, QColor

from beeoffice.plugins.beesheet_delegate import CellEditorDelegate
from beeoffice.plugins.beesheet_loaders import ChunkLoader
from beeoffice.i18n import tr
from beeoffice.theme import Theme
from beeoffice.ribbon_icons import ribbon_icon


def _t():
    return Theme.tokens()


class RibbonGroup(QWidget):
    """WPS 风格功能区组：按钮在上，组名在下，无重边框。"""

    def __init__(self, title: str, parent=None):
        super().__init__(parent)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(8, 2, 8, 1)
        outer.setSpacing(1)
        self.body = QHBoxLayout()
        self.body.setSpacing(3)
        self.body.setContentsMargins(0, 0, 0, 0)
        outer.addLayout(self.body)
        self.title = QLabel(title)
        self.title.setAlignment(Qt.AlignCenter)
        self.title.setStyleSheet(f"color:{_t()['muted']};font-size:11px;")
        outer.addWidget(self.title)
        self.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Maximum)
        self.setMaximumHeight(76)


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
        btn_style = (f"QPushButton{{background:{_t()['surface_alt']};border:1px solid {_t()['border']};"
                     "padding:4px 10px;border-radius:3px}"
                     f"QPushButton:hover{{background:{_t()['accent_light']}}}")

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
            f"border:1px solid {_t()['border']};padding:2px 6px;"
            f"background:{_t()['surface']};color:{_t()['text']};font-size:12px;"
        )
        t1.addWidget(self._name_box)

        self._fx_btn = QPushButton("fx ▾")
        self._fx_btn.setIcon(ribbon_icon("function"))
        self._fx_btn.setProperty("ribbonIcon", "function")
        self._fx_btn.setToolTip(tr("auto.beesheet_ui_mixin.19e2c0c0", "插入函数"))
        self._fx_btn.setStyleSheet(
            f"QPushButton{{background:{_t()['accent_light']};border:1px solid {_t()['accent']};"
            f"color:{_t()['text']};font-weight:bold;padding:3px 8px;border-radius:3px;}}"
            f"QPushButton:hover{{background:{_t()['accent']};}}"
        )
        self._fx_btn.clicked.connect(self._show_fx_dropdown)
        t1.addWidget(self._fx_btn)

        self.formula_bar = QLineEdit()
        self.formula_bar.setPlaceholderText(
            tr("auto.beesheet_ui_mixin.b3ea4281", "输入值或公式（输入 = 开始，F1 查看函数帮助）")
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

        btn_import = QPushButton(tr("auto.beesheet_ui_mixin.85c5bee6", "导入"))
        btn_import.setStyleSheet(btn_style)
        btn_import.setIcon(ribbon_icon("import"))
        btn_import.setProperty("ribbonIcon", "import")
        btn_import.clicked.connect(self._import_file)
        t1.addWidget(btn_import)

        self._export_btn = QPushButton(tr("auto.beesheet_ui_mixin.6810bfb6", "导出 ▾"))
        self._export_btn.setStyleSheet(btn_style)
        self._export_btn.setIcon(ribbon_icon("export"))
        self._export_btn.setProperty("ribbonIcon", "export")
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
        self._cancel_load_btn.setToolTip(tr("auto.beesheet_ui_mixin.43448f3e", "取消加载"))
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

        self._ribbon_toggle_btn = QPushButton(tr("auto.beesheet_ui_mixin.f1", "▲ 隐藏功能区"))
        self._ribbon_toggle_btn.setStyleSheet("QPushButton{font-size:10px;padding:2px 6px;}")
        self._ribbon_toggle_btn.clicked.connect(lambda: self._toggle_toolbars(self._ribbon_toggle_btn))
        t1.addWidget(self._ribbon_toggle_btn)

        tc.addLayout(t1)

        # ===== 分类功能区（WPS 风格：开始 / 插入 / 数据 / 公式 / 视图） =====
        self._ribbon = QWidget()
        ribbon_layout = QVBoxLayout(self._ribbon)
        ribbon_layout.setContentsMargins(0, 0, 0, 0)
        ribbon_layout.setSpacing(0)

        self._ribbon_tabs = QTabBar()
        self._ribbon_tabs.setFixedHeight(32)
        self._ribbon_tabs.setExpanding(False)
        self._ribbon_tabs.setDrawBase(False)
        _accent = _t()['accent']
        _accent_light = _t()['accent_light']
        _surface = _t()['surface_alt']
        _border = _t()['border']
        _text = _t()['text']
        self._ribbon.setObjectName("BeeRibbon")
        self._ribbon.setFixedHeight(108)
        self._ribbon.setStyleSheet(
            f"QWidget#BeeRibbon{{background:{_surface};border-bottom:1px solid {_border};}}"
            f"QPushButton{{background:transparent;border:1px solid transparent;"
            f"border-radius:4px;padding:5px 9px;color:{_text};}}"
            f"QPushButton:hover{{background:{_accent_light};border-color:{_border};}}"
            f"QPushButton:pressed{{background:{_accent};color:white;}}"
            f"QPushButton:checked{{background:{_accent};color:white;}}"
        )
        self._ribbon_tabs.setStyleSheet(
            f"QTabBar::tab{{padding:7px 20px;margin-right:2px;background:transparent;"
            f"border:none;border-bottom:3px solid transparent;color:{_text};}}"
            f"QTabBar::tab:selected{{border-bottom:3px solid {_accent};font-weight:bold;}}"
            f"QTabBar::tab:hover{{background:{_accent_light};}}"
        )
        ribbon_layout.addWidget(self._ribbon_tabs)

        self._ribbon_stack = QStackedWidget()
        self._ribbon_stack.setFixedHeight(76)
        ribbon_layout.addWidget(self._ribbon_stack)
        ribbon_pages = []

        def add_page(title):
            page = QWidget()
            page_layout = QHBoxLayout(page)
            page_layout.setContentsMargins(4, 2, 4, 2)
            page_layout.setSpacing(8)
            page_layout.setAlignment(Qt.AlignTop | Qt.AlignLeft)
            self._ribbon_tabs.addTab(title)
            self._ribbon_stack.addWidget(page)
            ribbon_pages.append(page_layout)
            return page_layout

        def add_group(page_layout, title):
            group = RibbonGroup(title)
            page_layout.addWidget(group)
            sep = QFrame()
            sep.setFrameShape(QFrame.VLine)
            sep.setStyleSheet(f"color:{_t()['border']};")
            sep.setFixedWidth(1)
            page_layout.addWidget(sep)
            return group.body

        fmt_btn_style = (
            "QPushButton{background:#FFF;border:1px solid #CCC;"
            "padding:3px 8px;border-radius:3px;font-weight:bold;min-width:28px;}"
            "QPushButton:hover{background:#FFE0A0;}"
            "QPushButton:checked{background:#FFB300;color:#000;}"
        )

        icon_by_text = {
            "粘贴": "paste", "查找替换": "find", "自动求和": "sum",
            "图表": "chart", "透视表": "pivot", "批注": "comment",
            "智能填充": "fill", "排序": "sort", "筛选": "filter",
            "清洗": "clean", "数据验证": "validation",
            "插入函数": "function", "函数参考": "book",
            "名称管理": "tag", "追踪引用": "trace", "追踪从属": "trace",
            "自然语言": "natural", "冻结": "freeze", "解冻": "unfreeze",
            "样式": "style", "兼容性": "compat", "统计": "stats",
            "插入行": "insert-row", "删除行": "delete-row",
            "插入列": "insert-col", "删除列": "delete-col",
            "合并单元格": "merge", "冻结当前": "freeze", "单元格样式": "style",
        }
        self._ribbon_buttons = []

        def add_btn(group_layout, text, slot, tip=None):
            btn = QToolButton()
            btn.setText(text)
            icon_name = icon_by_text.get(text)
            if icon_name:
                btn.setIcon(ribbon_icon(icon_name))
                btn.setIconSize(QSize(16, 16))
                btn.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
                btn.setProperty("ribbonIcon", icon_name)
            btn.setStyleSheet("")
            btn.setToolTip(tip or text)
            btn.clicked.connect(slot)
            group_layout.addWidget(btn)
            self._ribbon_buttons.append(btn)
            return btn

        # ---------- 开始 ----------
        page_start = add_page("开始")
        clip_group = add_group(page_start, "剪贴板")
        add_btn(clip_group, tr("auto.beesheet_ui_mixin.a1", "粘贴"), self._smart_paste, "Ctrl+V")
        add_btn(clip_group, tr("auto.beesheet_ui_mixin.a2", "查找替换"), self._show_find_replace, "Ctrl+F")
        add_btn(clip_group, tr("auto.beesheet_ui_mixin.a3", "自动求和"), self._auto_sum, "Alt+=")

        font_group = add_group(page_start, "字体")
        self._fmt_bold_btn = QPushButton("B")
        self._fmt_bold_btn.setCheckable(True)
        self._fmt_bold_btn.setToolTip(tr("auto.beesheet_ui_mixin.6faea341", "加粗（Ctrl+B）"))
        self._fmt_bold_btn.setStyleSheet(fmt_btn_style)
        self._fmt_bold_btn.clicked.connect(self._toggle_cell_bold)
        font_group.addWidget(self._fmt_bold_btn)

        self._fmt_italic_btn = QPushButton("I")
        self._fmt_italic_btn.setCheckable(True)
        self._fmt_italic_btn.setToolTip(tr("auto.beesheet_ui_mixin.e834506e", "斜体（Ctrl+I）"))
        self._fmt_italic_btn.setStyleSheet(fmt_btn_style + "QPushButton{font-style:italic;}")
        self._fmt_italic_btn.clicked.connect(self._toggle_cell_italic)
        font_group.addWidget(self._fmt_italic_btn)

        self._fmt_underline_btn = QPushButton("U")
        self._fmt_underline_btn.setCheckable(True)
        self._fmt_underline_btn.setToolTip(tr("auto.beesheet_ui_mixin.9bc18ae5", "下划线"))
        self._fmt_underline_btn.setStyleSheet(fmt_btn_style + "QPushButton{text-decoration:underline;}")
        self._fmt_underline_btn.clicked.connect(self._toggle_cell_underline)
        font_group.addWidget(self._fmt_underline_btn)

        align_group = add_group(page_start, "对齐")
        for label, slot, tip in [
            ("左对齐", self._align_cell_left, "左对齐"),
            ("居中", self._align_cell_center, "居中"),
            ("右对齐", self._align_cell_right, "右对齐"),
        ]:
            add_btn(align_group, label, slot, tip)

        num_group = add_group(page_start, "数字格式")
        self._num_format_combo = QComboBox()
        self._num_format_combo.addItems(
            ["常规", "数值", "货币", "百分比", "千分位", "日期", "文本"]
        )
        self._num_format_combo.setStyleSheet(
            "QComboBox{border:1px solid #CCC;padding:2px 6px;border-radius:3px;}"
        )
        self._num_format_combo.currentTextChanged.connect(self._apply_num_format)
        num_group.addWidget(self._num_format_combo)
        self._decimal_spin = QSpinBox()
        self._decimal_spin.setRange(0, 6)
        self._decimal_spin.setValue(2)
        self._decimal_spin.setMaximumWidth(60)
        self._decimal_spin.setToolTip(tr("auto.beesheet_ui_mixin.ff827033", "小数位数"))
        num_group.addWidget(QLabel(tr("auto.beesheet_ui_mixin.4562e62f", "小数")))
        num_group.addWidget(self._decimal_spin)

        # ---------- 插入 ----------
        page_insert = add_page("插入")
        obj_group = add_group(page_insert, "对象")
        add_btn(obj_group, tr("auto.beesheet_ui_mixin.b1", "图表"), self._create_chart)
        add_btn(obj_group, tr("auto.beesheet_ui_mixin.b2", "透视表"), self._show_pivot_table)
        add_btn(obj_group, tr("auto.beesheet_ui_mixin.b3", "批注"), self._add_comment)
        tool_group = add_group(page_insert, "数据工具")
        add_btn(tool_group, tr("auto.beesheet_ui_mixin.b4", "智能填充"), self._flash_fill)

        # ---------- 数据 ----------
        page_data = add_page("数据")
        sort_group = add_group(page_data, "排序和筛选")
        add_btn(sort_group, tr("auto.beesheet_ui_mixin.c1", "排序"), self._show_sort_dialog)
        add_btn(sort_group, tr("auto.beesheet_ui_mixin.c2", "筛选"), self._show_filter_dialog)
        clean_group = add_group(page_data, "数据工具")
        add_btn(clean_group, tr("auto.beesheet_ui_mixin.c3", "清洗"), self._show_clean_menu)
        add_btn(clean_group, tr("auto.beesheet_ui_mixin.c4", "数据验证"), self._show_data_validation_dialog)

        # ---------- 公式 ----------
        page_formula = add_page("公式")
        fn_group = add_group(page_formula, "函数")
        add_btn(fn_group, tr("auto.beesheet_ui_mixin.d1", "插入函数"), self._show_function_picker)
        add_btn(fn_group, tr("auto.beesheet_ui_mixin.d2", "函数参考"), self._show_function_reference)
        name_group = add_group(page_formula, "名称与审计")
        add_btn(name_group, tr("auto.beesheet_ui_mixin.d3", "名称管理"), self._show_name_manager)
        add_btn(name_group, tr("auto.beesheet_ui_mixin.d4", "追踪引用"), self._trace_precedents)
        add_btn(name_group, tr("auto.beesheet_ui_mixin.d5", "追踪从属"), self._trace_dependents)
        add_btn(name_group, tr("auto.beesheet_ui_mixin.d6", "自然语言"), self._nl_to_formula)

        # ---------- 视图 ----------
        page_view = add_page("视图")
        freeze_group = add_group(page_view, "冻结窗格")
        add_btn(freeze_group, tr("auto.beesheet_ui_mixin.e1", "冻结"), self._show_freeze_menu)
        add_btn(freeze_group, tr("auto.beesheet_ui_mixin.e2", "解冻"), self._unfreeze_all)
        view_group = add_group(page_view, "显示")
        add_btn(view_group, tr("auto.beesheet_ui_mixin.e3", "样式"), self._show_style_menu)
        add_btn(view_group, tr("auto.beesheet_ui_mixin.e4", "兼容性"), self._check_excel_compatibility)
        self._stat_btn = add_btn(view_group, tr("auto.beesheet_ui_mixin.e5", "统计"), self._show_selection_stats)

        # ---------- 表格工具（上下文页签，选中多个单元格时显示） ----------
        page_table = add_page("表格工具")
        range_group = add_group(page_table, "行列")
        add_btn(range_group, "插入行", lambda: self._insert_row_at(max(0, self.table_view.currentIndex().row())))
        add_btn(range_group, "删除行", lambda: self._delete_row_at(max(0, self.table_view.currentIndex().row())))
        add_btn(range_group, "插入列", lambda: self._insert_column_at(max(0, self.table_view.currentIndex().column())))
        add_btn(range_group, "删除列", lambda: self._delete_column_at(max(0, self.table_view.currentIndex().column())))
        cell_group = add_group(page_table, "单元格")
        add_btn(cell_group, "合并单元格", self._merge_cells)
        add_btn(cell_group, "冻结当前", self._freeze_cell)
        add_btn(cell_group, "单元格样式", self._show_style_menu)
        self._table_tab_index = self._ribbon_tabs.count() - 1
        self._ribbon_tabs.setTabVisible(self._table_tab_index, False)
        self._ribbon_tabs.setTabTextColor(self._table_tab_index, QColor(_t()["accent"]))
        ctx_page = page_table.parentWidget()
        self._table_context_page = ctx_page
        if ctx_page is not None:
            ctx_page.setObjectName("BeeSheetTableContext")
            ctx_page.setStyleSheet(
                f"QWidget#BeeSheetTableContext{{background:{_t()['accent_light']};"
                f"border:1px solid {_t()['accent']};border-radius:6px;}}"
            )

        for page_layout in ribbon_pages:
            page_layout.addStretch(1)

        # 记住上次打开的页签（WPS 行为）
        self._ribbon_settings = QSettings("BeeOffice", "BeeSheetRibbon")
        try:
            saved_tab = int(self._ribbon_settings.value("ribbon/tab", 0))
        except (TypeError, ValueError):
            saved_tab = 0
        if 0 <= saved_tab < self._ribbon_tabs.count():
            self._ribbon_tabs.setCurrentIndex(saved_tab)
            self._ribbon_stack.setCurrentIndex(saved_tab)
        self._ribbon_tabs.currentChanged.connect(self._ribbon_stack.setCurrentIndex)
        self._ribbon_tabs.currentChanged.connect(
            lambda idx: self._ribbon_settings.setValue("ribbon/tab", idx)
        )
        tc.addWidget(self._ribbon)

        # 暂存到 self，供主类的 layout 组装
        self._toolbar_container = tc

    # ==================== 上下文页签 ====================
    def _update_ribbon_context(self, *args):
        """选中多个单元格时显示“表格工具”上下文页签。"""
        if not hasattr(self, "_ribbon_tabs") or not hasattr(self, "_table_tab_index"):
            return
        indexes = self.table_view.selectionModel().selectedIndexes()
        show = len(indexes) > 1
        self._ribbon_tabs.setTabVisible(self._table_tab_index, show)
        if not show and self._ribbon_tabs.currentIndex() == self._table_tab_index:
            self._ribbon_tabs.setCurrentIndex(0)

    # ==================== 主题刷新 ====================
    def apply_theme(self):
        """亮/暗主题切换时刷新 Ribbon 背景、组名与图标颜色。"""
        if not hasattr(self, "_ribbon"):
            return
        tokens = _t()
        accent = tokens["accent"]
        accent_light = tokens["accent_light"]
        border = tokens["border"]
        text = tokens["text"]
        surface = tokens["surface_alt"]
        self._ribbon.setStyleSheet(
            f"QWidget#BeeRibbon{{background:{surface};border-bottom:1px solid {border};}}"
            f"QPushButton{{background:transparent;border:1px solid transparent;"
            f"border-radius:4px;padding:5px 9px;color:{text};}}"
            f"QPushButton:hover{{background:{accent_light};border-color:{border};}}"
            f"QPushButton:pressed{{background:{accent};color:white;}}"
            f"QPushButton:checked{{background:{accent};color:white;}}"
        )
        self._ribbon_tabs.setStyleSheet(
            f"QTabBar::tab{{padding:7px 20px;margin-right:2px;background:transparent;"
            f"border:none;border-bottom:3px solid transparent;color:{text};}}"
            f"QTabBar::tab:selected{{border-bottom:3px solid {accent};font-weight:bold;}}"
            f"QTabBar::tab:hover{{background:{accent_light};}}"
        )
        for group in self._ribbon.findChildren(RibbonGroup):
            group.title.setStyleSheet(f"color:{tokens['muted']};font-size:11px;")
        for btn in self.findChildren(QToolButton):
            name = btn.property("ribbonIcon")
            if name:
                btn.setIcon(ribbon_icon(str(name)))
        ctx = getattr(self, "_table_context_page", None)
        if ctx is not None:
            ctx.setStyleSheet(
                f"QWidget#BeeSheetTableContext{{background:{accent_light};"
                f"border:1px solid {accent};border-radius:6px;}}"
            )

    # ==================== 窄窗口紧凑模式 ====================
    def resizeEvent(self, event):
        """窗口变窄时隐藏分组标题，降低功能区高度，接近 WPS 紧凑模式。"""
        super().resizeEvent(event)
        if not hasattr(self, "_ribbon"):
            return
        compact = self.width() < 980
        for group in self._ribbon.findChildren(RibbonGroup):
            group.title.setVisible(not compact)
        for btn in getattr(self, "_ribbon_buttons", []):
            if btn.icon().isNull():
                continue
            btn.setToolButtonStyle(
                Qt.ToolButtonIconOnly if compact else Qt.ToolButtonTextBesideIcon
            )
        self._ribbon.setFixedHeight(96 if compact else 108)

    # ==================== 表格视图 ====================
    def _build_table_view(self):
        """构建主表格视图 + 事件连接 + 填充柄"""
        self.table_view = QTableView()
        self.table_view.setModel(self.model)
        self.table_view.selectionModel().selectionChanged.connect(self._update_ribbon_context)
        self.table_view.horizontalHeader().setSectionResizeMode(
            QHeaderView.Interactive
        )
        self.table_view.horizontalHeader().setDefaultSectionSize(82)
        self.table_view.horizontalHeader().setMinimumSectionSize(48)
        self.table_view.verticalHeader().setDefaultSectionSize(24)
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
            f"QWidget{{background:{_t()['surface_alt']};"
            f"border-top:1px solid {_t()['border']};}}"
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
        QShortcut(QKeySequence.Undo, self).activated.connect(self.undo)
        QShortcut(QKeySequence.Redo, self).activated.connect(self.redo)
        QShortcut(QKeySequence("Ctrl+D"), self).activated.connect(
            self._shortcut_fill_down
        )
        QShortcut(QKeySequence("Ctrl+R"), self).activated.connect(
            self._shortcut_fill_right
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
        # 线程安全（P0）：chunk_loaded 是"请在 GUI 线程加载第 idx 块"的请求，
        # 由 _on_chunk_loaded 在 GUI 线程执行，避免 worker 直接改 model。
        self._chunk_loader = ChunkLoader(self.model, self)
        self._chunk_loader.chunk_loaded.connect(self._on_chunk_loaded)
        self._chunk_loader.all_loaded.connect(self._on_all_loaded)

        # 自动保存定时器（每 5 分钟）
        self._auto_save_timer = QTimer(self)
        self._auto_save_timer.timeout.connect(self._auto_save)
        self._auto_save_timer.start(300000)

    def _on_chunk_loaded(self, idx):
        """
        在 GUI 线程执行真正的分块加载（P0：修复跨线程修改 model）。

        ChunkLoader 线程只发请求，这里才允许碰 QAbstractTableModel。
        """
        try:
            self.model.load_chunk(idx)
            self.model.layoutChanged.emit()
            self._on_loading_progress(self.model.loading_progress)
        except Exception as e:
            logging.error(f"分块加载失败 idx={idx}: {e}")