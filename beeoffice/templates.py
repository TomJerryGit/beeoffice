# beeoffice/templates.py
"""
模板管理界面：选择模板创建文档、预览模板内容
"""
import logging
from datetime import datetime

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QTabWidget,
    QListWidget, QListWidgetItem, QTextBrowser, QSplitter,
    QPushButton, QWidget, QInputDialog, QMessageBox
)
from PySide6.QtCore import Qt
from beeoffice.i18n import tr


def show_template_picker(parent):
    """
    显示模板选择对话框
    :param parent: 主窗口实例（BeeApp）
    """
    try:
        from beeoffice.resources.template_manager import TemplateManager
        tm = TemplateManager()
        templates = tm.get_all_templates()
    except Exception as e:
        logging.error(f"加载模板失败: {e}")
        QMessageBox.warning(parent, tr("auto.templates.b859c7be", "错误"), tr("auto.templates.610db40f", "加载模板失败：\n{e}").format(e=e))
        return

    dialog = QDialog(parent)
    dialog.setWindowTitle(tr("auto.templates.09b31282", "📄 选择模板"))
    dialog.resize(750, 500)
    layout = QVBoxLayout(dialog)

    # 顶部提示
    layout.addWidget(QLabel(tr("auto.templates.cf33314c", "选择一个模板开始撰写（双击新建，单击预览）")))

    # 主体：左侧标签页 + 右侧预览
    splitter = QSplitter(Qt.Horizontal)

    tabs = QTabWidget()
    tabs.setDocumentMode(True)

    # 按分类组织模板
    categories = {}
    for tpl in templates:
        cat = tpl.get("category", "其他")
        categories.setdefault(cat, []).append(tpl)

    # 固定分类顺序，其余分类按字母排序附加
    preferred_order = ["工作", "会议", "项目", "数据", "财务", "餐饮", "电商", "教培", "其他"]
    ordered_cats = [c for c in preferred_order if c in categories]
    extra_cats = [c for c in categories.keys() if c not in preferred_order]
    ordered_cats.extend(sorted(extra_cats))

    # 右侧预览
    preview = QTextBrowser()
    preview.setOpenExternalLinks(False)
    preview.setStyleSheet("QTextBrowser { font-size: 14px; padding: 8px; background: #FFF; border: 1px solid #DDD; border-radius: 6px; }")

    def on_item_selected(lst):
        """列表选中时更新预览"""
        item = lst.currentItem()
        if item is None:
            preview.clear()
            return
        tpl = item.data(Qt.UserRole)
        if not tpl:
            preview.clear()
            return
        content = tpl.get("content", "")
        # 替换 {date} 占位符
        content = content.replace("{date}", datetime.now().strftime("%Y年%m月%d日"))
        try:
            import markdown
            html = markdown.markdown(
                content,
                extensions=["tables", "fenced_code", "nl2br"]
            )
        except Exception:
            # Markdown 不可用时纯文本展示
            html = "<pre>" + content.replace("<", "&lt;").replace(">", "&gt;") + "</pre>"
        preview.setHtml(html)

    def on_item_double_clicked(item):
        """双击创建文档"""
        tpl = item.data(Qt.UserRole)
        if tpl:
            _create_from_template(parent, tpl)
            dialog.accept()

    # 构建每个分类的标签页
    for cat_name in ordered_cats:
        lst = QListWidget()
        lst.setAlternatingRowColors(True)
        lst.setStyleSheet(
            "QListWidget::item { padding: 8px; } "
            "QListWidget::item:selected { background: #FFE0A0; color: #000; }"
        )
        for tpl in categories[cat_name]:
            icon = "📦" if tpl.get("source") == "builtin" else "👤"
            item = QListWidgetItem(tr("auto.templates.b245f581", "{0} {1}").format(icon, tpl.get('name', '未命名')))
            item.setData(Qt.UserRole, tpl)
            lst.addItem(item)

        # 信号连接（使用默认参数绑定 lst，避免闭包捕获问题）
        lst.itemSelectionChanged.connect(lambda l=lst: on_item_selected(l))
        lst.itemDoubleClicked.connect(on_item_double_clicked)

        tabs.addTab(lst, f"  {cat_name}  ")

    # 若第一个分类有内容，默认选中第一项
    if tabs.count() > 0:
        first_list = tabs.widget(0)
        if isinstance(first_list, QListWidget) and first_list.count() > 0:
            first_list.setCurrentRow(0)

    splitter.addWidget(tabs)
    splitter.addWidget(preview)
    splitter.setSizes([400, 350])
    layout.addWidget(splitter)

    # 底部按钮
    btn_layout = QHBoxLayout()
    new_cat_btn = QPushButton(tr("auto.templates.72a7fce2", "+ 新建分类"))
    open_btn = QPushButton(tr("auto.templates.5396434d", "使用此模板"))
    cancel_btn = QPushButton(tr("auto.templates.4d0b4688", "取消"))

    def use_current_template():
        """使用当前选中模板新建文档"""
        current_tab = tabs.currentWidget()
        if not isinstance(current_tab, QListWidget):
            return
        item = current_tab.currentItem()
        if not item:
            QMessageBox.information(dialog, tr("auto.templates.ab3656a9", "提示"), tr("auto.templates.f61088ef", "请先选择一个模板"))
            return
        tpl = item.data(Qt.UserRole)
        if tpl:
            _create_from_template(parent, tpl)
            dialog.accept()

    def add_new_category():
        """新建分类（用于快速保存模板时的分类选择，本处仅提示）"""
        text, ok = QInputDialog.getText(dialog, tr("auto.templates.04c08442", "新建分类"), tr("auto.templates.c2413931", "输入分类名称："))
        if ok and text.strip():
            # 新建一个空分类标签
            new_lst = QListWidget()
            new_lst.setAlternatingRowColors(True)
            new_lst.itemSelectionChanged.connect(lambda l=new_lst: on_item_selected(l))
            new_lst.itemDoubleClicked.connect(on_item_double_clicked)
            tabs.addTab(new_lst, f"  {text.strip()}  ")
            tabs.setCurrentWidget(new_lst)

    new_cat_btn.clicked.connect(add_new_category)
    open_btn.clicked.connect(use_current_template)
    cancel_btn.clicked.connect(dialog.reject)

    btn_layout.addWidget(new_cat_btn)
    btn_layout.addStretch()
    btn_layout.addWidget(open_btn)
    btn_layout.addWidget(cancel_btn)
    layout.addLayout(btn_layout)

    dialog.exec()


def _create_from_template(parent, tpl_info):
    """
    根据模板信息创建新文档
    :param parent: 主窗口实例
    :param tpl_info: 模板 dict，包含 name、content 等字段
    """
    try:
        from beeoffice.plugins.beewrite import BeeWriteEditor
    except Exception as e:
        logging.error(f"导入 BeeWriteEditor 失败: {e}")
        QMessageBox.warning(parent, tr("auto.templates.b859c7be", "错误"), tr("auto.templates.691635ca", "无法创建文档：\n{e}").format(e=e))
        return

    content = tpl_info.get("content", "")
    # 替换日期占位符
    content = content.replace("{date}", datetime.now().strftime("%Y年%m月%d日"))

    editor = BeeWriteEditor()
    if hasattr(editor, "set_content"):
        editor.set_content(content)

    name = tpl_info.get("name", "新文档")
    # 添加为标签页
    try:
        parent.tab_manager.addTab(editor, f"📝 {name}")
        parent.tab_manager.setCurrentWidget(editor)
        # 文件路径未知，暂不监视
        if hasattr(parent, "set_global_status"):
            parent.set_global_status(tr("auto.templates.e0eeb39f", "已从模板创建: {name}").format(name=name), 3000)
    except Exception as e:
        logging.error(f"添加标签页失败: {e}")
        QMessageBox.warning(parent, tr("auto.templates.b859c7be", "错误"), tr("auto.templates.4ee03918", "添加标签页失败：\n{e}").format(e=e))


def save_as_template_dialog(parent, content):
    """
    将内容保存为模板（供外部调用）
    :param parent: 主窗口实例
    :param content: 要保存的内容（字符串）
    """
    if not content or not content.strip():
        QMessageBox.information(parent, tr("auto.templates.ab3656a9", "提示"), tr("auto.templates.f85a9a32", "内容为空，无法保存为模板"))
        return

    # 输入模板名称
    name, ok = QInputDialog.getText(parent, tr("auto.templates.827613c8", "保存为模板"), tr("auto.templates.fd89b161", "模板名称："))
    if not ok or not name.strip():
        return
    name = name.strip()

    # 输入分类
    category, ok = QInputDialog.getText(parent, tr("auto.templates.827613c8", "保存为模板"), tr("auto.templates.e568c7d4", "分类（如：工作、会议）："), text=tr("auto.templates.1a26edf9", "其他"))
    if not ok:
        return
    category = category.strip() or "其他"

    # 保存
    try:
        from beeoffice.resources.template_manager import TemplateManager
        tm = TemplateManager()
        if tm.save_user_template(name, content, category):
            QMessageBox.information(parent, tr("auto.templates.51991a5d", "成功"), tr("auto.templates.10d545e5", "模板「{name}」已保存到分类「{category}」").format(name=name, category=category))
        else:
            QMessageBox.warning(parent, tr("auto.templates.3e3c8068", "失败"), tr("auto.templates.d8fc29f5", "保存模板失败"))
    except Exception as e:
        logging.error(f"保存模板失败: {e}")
        QMessageBox.warning(parent, tr("auto.templates.3e3c8068", "失败"), tr("auto.templates.68b212fe", "保存模板失败：\n{e}").format(e=e))