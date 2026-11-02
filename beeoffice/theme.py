# beeoffice/theme.py
class Theme:
    """主题管理器：管理明暗模式和强调色"""

    # 可选的强调色
    ACCENT_COLORS = {
        "amber": {"primary": "#FFB300", "light": "#FFF3E0", "dark": "#E65100"},
        "ocean": {"primary": "#2196F3", "light": "#E3F2FD", "dark": "#0D47A1"},
        "forest": {"primary": "#4CAF50", "light": "#E8F5E9", "dark": "#1B5E20"},
        "sunset": {"primary": "#FF7043", "light": "#FBE9E7", "dark": "#BF360C"},
    }

    _instance = None
    _current_theme = "light"
    _current_accent = "amber"

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    @classmethod
    def set_theme(cls, mode: str):
        """设置主题模式：light 或 dark"""
        if mode not in ("light", "dark"):
            mode = "light"
        cls._current_theme = mode

    @classmethod
    def set_accent(cls, accent_name: str):
        """设置强调色"""
        if accent_name in cls.ACCENT_COLORS:
            cls._current_accent = accent_name

    @classmethod
    def get_accent_color(cls, shade: str = "primary") -> str:
        """获取当前强调色的指定色阶"""
        accent = cls.ACCENT_COLORS.get(cls._current_accent, cls.ACCENT_COLORS["amber"])
        return accent.get(shade, "#FFB300")

    @classmethod
    def is_dark(cls) -> bool:
        """当前是否为暗色主题"""
        return cls._current_theme == "dark"

    @classmethod
    def tokens(cls) -> dict:
        """当前主题的颜色 token（控件内联样式统一从这里取值）。"""
        dark = cls.is_dark()
        accent = cls.get_accent_color("primary")
        light = cls.get_accent_color("light")
        dark_color = cls.get_accent_color("dark")
        if dark:
            return {
                "bg": "#1E1E1E", "surface": "#252525",
                "surface_alt": "#2D2D2D", "toolbar": "#2D2D2D",
                "text": "#DDDDDD", "muted": "#999999",
                "border": "#444444", "accent": accent,
                "accent_light": light, "accent_dark": dark_color,
                "danger": "#CF6679", "success": "#81C784",
                "is_dark": True,
            }
        return {
            "bg": "#F5F5F5", "surface": "#FFFFFF",
            "surface_alt": "#FAFAFA", "toolbar": "#FFFFFF",
            "text": "#333333", "muted": "#666666",
            "border": "#D0D0D0", "accent": accent,
            "accent_light": light, "accent_dark": dark_color,
            "danger": "#C62828", "success": "#2E7D32",
            "is_dark": False,
        }

    @classmethod
    def button_qss(cls, kind: str = "normal", small: bool = False) -> str:
        """主题化按钮 QSS；plugins 不再写死 #EEE/#CCC。"""
        t = cls.tokens()
        pad = "2px 7px" if small else "5px 12px"
        radius = "3px" if small else "6px"
        if kind == "primary":
            bg, fg, border = t["accent"], "#000000" if t["is_dark"] else "#FFFFFF", t["accent_dark"]
        elif kind == "danger":
            bg, fg, border = t["danger"], "#FFFFFF", t["danger"]
        elif kind == "ghost":
            bg, fg, border = "transparent", t["text"], t["border"]
        else:
            bg, fg, border = t["surface_alt"], t["text"], t["border"]
        hover = t["accent_light"] if not t["is_dark"] else "#3A3A3A"
        return (
            f"QPushButton{{background:{bg};color:{fg};border:1px solid {border};"
            f"border-radius:{radius};padding:{pad};}}"
            f"QPushButton:hover{{background:{hover};border-color:{t['accent']};}}"
            f"QPushButton:checked{{background:{t['accent']};color:#000;}}"
        )

    @classmethod
    def toolbar_qss(cls) -> str:
        """主题化工具栏 QSS（蜜写/蜜演 QToolBar 共用）。"""
        t = cls.tokens()
        return (
            f"QToolBar{{background:{t['toolbar']};border-bottom:1px solid {t['border']};"
            "padding:2px;spacing:4px}"
            f"QToolBar QToolButton{{padding:4px 8px;border-radius:3px;color:{t['text']};}}"
            f"QToolBar QToolButton:hover{{background:{t['accent_light'] if not t['is_dark'] else '#3A3A3A'};}}"
        )

    @classmethod
    def get_stylesheet(cls) -> str:
        """获取当前主题的完整样式表"""
        accent = cls.get_accent_color("primary")
        al = cls.get_accent_color("light")
        ad = cls.get_accent_color("dark")
        if cls.is_dark():
            return cls._dark_theme(accent, al, ad)
        return cls._light_theme(accent, al, ad)

    # ---------- 亮色主题 ----------
    @classmethod
    def _light_theme(cls, a, al, ad):
        return f"""
        * {{ }}
        QMainWindow {{ background-color: #F5F5F5; }}
        QMenuBar {{ background-color: #FAFAFA; border-bottom: 1px solid #E0E0E0; padding: 2px; font-size: 13px; }}
        QMenuBar::item:selected {{ background-color: {al}; color: {ad}; border-radius: 4px; }}
        QMenu {{ background-color: #FFFFFF; border: 1px solid #E0E0E0; border-radius: 8px; padding: 4px; }}
        QMenu::item {{ padding: 6px 24px; border-radius: 4px; }}
        QMenu::item:selected {{ background-color: {al}; color: {ad}; }}
        QStatusBar {{ background-color: #FAFAFA; border-top: 1px solid #E0E0E0; font-size: 12px; color: #666; }}
        QTabWidget::pane {{ border: none; background-color: #FAFAFA; }}
        QTabBar::tab {{ background-color: #ECECEC; color: #555; padding: 8px 16px; margin-right: 2px; border-top-left-radius: 6px; border-top-right-radius: 6px; }}
        QTabBar::tab:selected {{ background-color: {a}; color: #FFF; font-weight: bold; }}
        QTabBar::tab:hover:!selected {{ background-color: {al}; }}
        QPushButton {{ border: 1px solid #CCC; border-radius: 6px; padding: 6px 14px; background: #FAFAFA; color: #333; font-size: 13px; }}
        QPushButton:hover {{ background: {al}; border-color: {a}; }}
        QPushButton:pressed {{ background: {a}; color: #FFF; }}
        QLineEdit, QTextEdit, QPlainTextEdit {{ border: 1px solid #D0D0D0; border-radius: 6px; padding: 6px 10px; background: #FFF; selection-background-color: {a}; }}
        QLineEdit:focus, QTextEdit:focus, QPlainTextEdit:focus {{ border-color: {a}; }}
        QListWidget {{ border: 1px solid #E0E0E0; border-radius: 6px; background: #FFF; }}
        QListWidget::item:selected {{ background: {al}; color: #333; }}
        QComboBox {{ border: 1px solid #D0D0D0; border-radius: 6px; padding: 4px 8px; background: #FFF; }}
        QComboBox:hover {{ border-color: {a}; }}
        QComboBox::drop-down {{ border: none; }}
        QCheckBox {{ spacing: 6px; }}
        QCheckBox::indicator {{ width: 16px; height: 16px; }}
        QCheckBox::indicator:checked {{ background-color: {a}; border: 1px solid {ad}; border-radius: 3px; }}
        QScrollBar:vertical {{ border: none; background: #F0F0F0; width: 8px; border-radius: 4px; }}
        QScrollBar::handle:vertical {{ background: #CCC; border-radius: 4px; min-height: 20px; }}
        QScrollBar::handle:vertical:hover {{ background: {a}; }}
        QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
        QScrollBar:horizontal {{ border: none; background: #F0F0F0; height: 8px; border-radius: 4px; }}
        QScrollBar::handle:horizontal {{ background: #CCC; border-radius: 4px; min-width: 20px; }}
        QScrollBar::handle:horizontal:hover {{ background: {a}; }}
        QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{ width: 0; }}
        QTableView {{ border: 1px solid #DDD; gridline-color: #E8E8E8; background-color: #FFF; alternate-background-color: #FAFAFA; selection-background-color: #FFE0A0; selection-color: #000; }}
        QHeaderView::section {{ background-color: #EEE; border: none; border-right: 1px solid #CCC; border-bottom: 1px solid #CCC; padding: 4px; }}
        QToolTip {{ background-color: #333; color: #FFF; border: none; padding: 4px 8px; border-radius: 4px; }}
        QProgressBar {{ border: 1px solid #DDD; border-radius: 6px; text-align: center; background: #F5F5F5; }}
        QProgressBar::chunk {{ background-color: {a}; border-radius: 5px; }}
        QSplitter::handle {{ background-color: #E0E0E0; }}
        QSplitter::handle:hover {{ background-color: {a}; }}
        """

    # ---------- 暗色主题 ----------
    @classmethod
    def _dark_theme(cls, a, al, ad):
        return f"""
        * {{ }}
        QMainWindow {{ background-color: #1E1E1E; }}
        QMenuBar {{ background-color: #2D2D2D; color: #CCC; border-bottom: 1px solid #3D3D3D; font-size: 13px; }}
        QMenuBar::item:selected {{ background-color: {a}; color: #000; border-radius: 4px; }}
        QMenu {{ background-color: #2D2D2D; color: #CCC; border: 1px solid #3D3D3D; border-radius: 8px; padding: 4px; }}
        QMenu::item {{ padding: 6px 24px; border-radius: 4px; }}
        QMenu::item:selected {{ background-color: {a}; color: #000; }}
        QStatusBar {{ background-color: #2D2D2D; color: #999; border-top: 1px solid #3D3D3D; font-size: 12px; }}
        QTabWidget::pane {{ border: none; background-color: #252525; }}
        QTabBar::tab {{ background-color: #333; color: #AAA; padding: 8px 16px; margin-right: 2px; border-top-left-radius: 6px; border-top-right-radius: 6px; }}
        QTabBar::tab:selected {{ background-color: {a}; color: #000; font-weight: bold; }}
        QTabBar::tab:hover:!selected {{ background-color: #444; }}
        QPushButton {{ border: 1px solid #444; border-radius: 6px; padding: 6px 14px; background: #333; color: #DDD; font-size: 13px; }}
        QPushButton:hover {{ background: #444; border-color: {a}; }}
        QPushButton:pressed {{ background: {a}; color: #000; }}
        QLineEdit, QTextEdit, QPlainTextEdit {{ border: 1px solid #444; border-radius: 6px; padding: 6px 10px; background: #252525; color: #DDD; selection-background-color: {a}; }}
        QLineEdit:focus, QTextEdit:focus, QPlainTextEdit:focus {{ border-color: {a}; }}
        QListWidget {{ border: 1px solid #3D3D3D; border-radius: 6px; background: #252525; color: #DDD; }}
        QListWidget::item:selected {{ background: {a}; color: #000; }}
        QComboBox {{ border: 1px solid #444; border-radius: 6px; padding: 4px 8px; background: #333; color: #DDD; }}
        QComboBox:hover {{ border-color: {a}; }}
        QComboBox::drop-down {{ border: none; }}
        QCheckBox {{ spacing: 6px; color: #DDD; }}
        QCheckBox::indicator {{ width: 16px; height: 16px; }}
        QCheckBox::indicator:checked {{ background-color: {a}; border: 1px solid {ad}; border-radius: 3px; }}
        QScrollBar:vertical {{ border: none; background: #2A2A2A; width: 8px; border-radius: 4px; }}
        QScrollBar::handle:vertical {{ background: #555; border-radius: 4px; min-height: 20px; }}
        QScrollBar::handle:vertical:hover {{ background: {a}; }}
        QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
        QScrollBar:horizontal {{ border: none; background: #2A2A2A; height: 8px; border-radius: 4px; }}
        QScrollBar::handle:horizontal {{ background: #555; border-radius: 4px; min-width: 20px; }}
        QScrollBar::handle:horizontal:hover {{ background: {a}; }}
        QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{ width: 0; }}
        QTableView {{ border: 1px solid #3D3D3D; gridline-color: #444; background-color: #252525; color: #DDD; alternate-background-color: #2A2A2A; selection-background-color: #FFB300; selection-color: #000; }}
        QHeaderView::section {{ background-color: #333; color: #CCC; border: none; border-right: 1px solid #444; border-bottom: 1px solid #444; padding: 4px; }}
        QToolTip {{ background-color: #555; color: #FFF; border: none; padding: 4px 8px; border-radius: 4px; }}
        QProgressBar {{ border: 1px solid #444; border-radius: 6px; text-align: center; background: #252525; color: #DDD; }}
        QProgressBar::chunk {{ background-color: {a}; border-radius: 5px; }}
        QSplitter::handle {{ background-color: #3D3D3D; }}
        QSplitter::handle:hover {{ background-color: {a}; }}
        """