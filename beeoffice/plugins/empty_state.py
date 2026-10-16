# beeoffice/plugins/empty_state.py
"""
空状态引导组件
当用户打开空白标签时，显示友好的操作指引
"""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton
)
from PySide6.QtCore import Qt, Signal


class EmptyStateWidget(QWidget):
    """空状态引导——大图标 + 文案 + 操作按钮"""

    action_triggered = Signal(str)  # 发出操作名称

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet("background: transparent;")

        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignCenter)
        layout.setSpacing(16)

        # 图标
        self.icon_label = QLabel()
        self.icon_label.setAlignment(Qt.AlignCenter)
        self.icon_label.setStyleSheet("font-size: 64px;")
        layout.addWidget(self.icon_label)

        # 标题
        self.title_label = QLabel()
        self.title_label.setAlignment(Qt.AlignCenter)
        self.title_label.setStyleSheet("""
            font-size: 20px; 
            font-weight: bold; 
            color: #333;
            margin-top: 8px;
        """)
        layout.addWidget(self.title_label)

        # 描述
        self.desc_label = QLabel()
        self.desc_label.setAlignment(Qt.AlignCenter)
        self.desc_label.setWordWrap(True)
        self.desc_label.setMaximumWidth(400)
        self.desc_label.setStyleSheet("""
            font-size: 13px; 
            color: #888; 
            line-height: 1.6;
        """)
        layout.addWidget(self.desc_label)

        # 按钮容器
        self.button_layout = QHBoxLayout()
        self.button_layout.setAlignment(Qt.AlignCenter)
        self.button_layout.setSpacing(12)
        layout.addLayout(self.button_layout)

        layout.addStretch()

    def set_state(self, icon: str, title: str, description: str, actions: list):
        """
        设置空状态
        actions: [("按钮文字", "action_name", is_primary), ...]
        """
        self.icon_label.setText(icon)
        self.title_label.setText(title)
        self.desc_label.setText(description)

        # 清空旧按钮
        while self.button_layout.count():
            item = self.button_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        # 创建新按钮
        for text, action_name, is_primary in actions:
            btn = QPushButton(text)
            btn.setMinimumWidth(140)
            btn.setCursor(Qt.PointingHandCursor)

            if is_primary:
                btn.setStyleSheet("""
                    QPushButton {
                        background-color: #FFB300;
                        color: #000;
                        border: none;
                        padding: 10px 20px;
                        border-radius: 6px;
                        font-size: 14px;
                        font-weight: bold;
                    }
                    QPushButton:hover {
                        background-color: #FFA000;
                    }
                """)
            else:
                btn.setStyleSheet("""
                    QPushButton {
                        background-color: #FFFFFF;
                        color: #555;
                        border: 1px solid #DDD;
                        padding: 10px 20px;
                        border-radius: 6px;
                        font-size: 13px;
                    }
                    QPushButton:hover {
                        background-color: #F5F5F5;
                        border-color: #BBB;
                    }
                """)

            btn.clicked.connect(lambda checked=False, a=action_name: self.action_triggered.emit(a))
            self.button_layout.addWidget(btn)


# 预设的空状态场景

def get_beewrite_empty_state():
    """蜜写空状态"""
    return {
        "icon": "📝",
        "title": "开始撰写文档",
        "description": "支持 Markdown 快捷输入，所见即所得编辑。\n"
                       "可以关联数据源，一键生成报告。",
        "actions": [
            ("📄 从模板新建", "new_from_template", True),
            ("📂 打开已有文档", "open_file", False),
            ("📊 关联数据源", "bind_data_source", False),
        ]
    }


def get_beesheet_empty_state():
    """蜜算空状态"""
    return {
        "icon": "📊",
        "title": "开始处理数据",
        "description": "将 CSV 或 Excel 文件拖拽到此处，\n"
                       "或使用示例数据快速体验。",
        "actions": [
            ("📂 导入数据文件", "import_file", True),
            ("🎲 加载示例数据", "load_sample", False),
        ]
    }


def get_unbound_variable_state():
    """未绑定数据源状态（变量面板中）"""
    return {
        "icon": "🔗",
        "title": "未关联数据源",
        "description": "文档中有数据变量需要绑定。\n"
                       "关联 CSV 文件或打开的表格即可自动填充。",
        "actions": [
            ("📂 绑定数据文件", "bind_file", True),
            ("📊 关联已打开的表格", "link_sheet", False),
        ]
    }
