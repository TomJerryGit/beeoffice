# beeoffice/plugins/friendly_errors.py
"""
友好错误提示系统
将技术性错误信息转换为用户可理解的提示

v5.0.1 修复（P1-8）：
  - PATTERNS[0] 的公式错误 pattern 从 `(.*)` 改为 `([^\n#]+)`
    原实现贪婪匹配到行尾，若错误信息本身含换行或多段 `#ERROR`
    会误捕获大段无关内容（如把代码片段当错误详情）。
    改用 `[^\n#]+` 非贪婪地匹配到换行或下一个 `#` 前，
    只捕获紧跟在 `#ERROR` 后的真实错误详情。
"""
import re
from PySide6.QtWidgets import QMessageBox
from beeoffice.i18n import tr


class FriendlyError:
    """将原始错误转换为友好的用户提示"""

    # 错误模式匹配规则
    PATTERNS = [
        # 公式错误
        # P1-8：非贪婪匹配到行尾 / 下一个 # 前，避免跨行 / 误捕获
        (r"#ERROR:?\s*([^\n#]+)",
         "公式计算错误",
         "公式好像写错了。\n\n{detail}\n\n💡 提示：\n"
         "• 检查函数名是否正确（如 SUM、VLOOKUP）\n"
         "• 检查括号是否成对\n"
         "• 检查单元格引用范围是否有效"),

        # 编码错误
        (r".*codec can't decode.*",
         "文件编码问题",
         "这个文件的编码格式比较特殊。\n\n"
         "已为您自动尝试了多种常见编码。\n\n"
         "💡 解决方法：\n"
         "• 用记事本打开文件，另存为 UTF-8 编码\n"
         "• 或从原系统重新导出为 UTF-8 格式"),

        # 文件不存在
        (r".*No such file.*",
         "找不到文件",
         "文件可能被移动或删除了。\n\n"
         "💡 请检查文件路径是否正确。"),

        # 权限错误
        (r".*Permission denied.*",
         "没有访问权限",
         "无法读取或写入该文件。\n\n"
         "💡 可能的原因：\n"
         "• 文件正在被其他程序使用\n"
         "• 目标文件夹没有写入权限\n"
         "• 文件被设置为只读"),

        # 内存不足
        (r".*MemoryError.*|.*out of memory.*",
         "内存不足",
         "文件太大，设备内存不够用了。\n\n"
         "💡 建议：\n"
         "• 将文件拆分为多个小文件\n"
         "• 关闭其他应用程序后再试"),

        # 格式错误
        (r".*ParserError.*|.*parse.*error.*",
         "文件格式错误",
         "这个文件可能不是标准格式。\n\n"
         "💡 请确认：\n"
         "• CSV 文件的列数是否一致\n"
         "• 文件是否被损坏\n"
         "• 是否选择了正确的文件类型"),

        # 网络错误
        (r".*Connection.*|.*Network.*|.*timeout.*",
         "网络连接失败",
         "无法连接到服务器。\n\n"
         "💡 请检查网络连接后重试。"),

        # 导入错误
        (r".*ModuleNotFoundError.*|.*ImportError.*",
         "缺少依赖",
         "某个功能所需的库未安装。\n\n"
         "{detail}\n\n"
         "💡 请运行：pip install -r requirements.txt"),

        # 通用错误
        (r".*",
         "出了点小问题",
         "遇到了一个意外错误。\n\n"
         "错误详情：{detail}\n\n"
         "💡 如果问题持续出现，请查看错误日志或联系开发者。"),
    ]

    @classmethod
    def translate(cls, error_message: str) -> tuple:
        """
        翻译错误消息
        返回: (标题, 详细提示)
        """
        for pattern, title, template in cls.PATTERNS:
            match = re.search(pattern, error_message, re.IGNORECASE)
            if match:
                detail = match.group(1) if match.groups() else error_message
                # 截断过长的错误信息
                if len(detail) > 200:
                    detail = detail[:200] + "..."
                message = template.format(detail=detail)
                return title, message

        return "未知错误", f"发生了意外错误：\n{error_message}"

    @classmethod
    def show_error(cls, parent, error, context: str = ""):
        """显示友好的错误对话框"""
        raw_message = str(error)
        title, message = cls.translate(raw_message)

        if context:
            message = f"在{context}时，{message}"

        QMessageBox.warning(parent, f"🐝 {title}", message)

    @classmethod
    def show_formula_error(cls, parent, formula: str, detail: str = ""):
        """显示公式错误"""
        QMessageBox.warning(
            parent,
            tr("auto.friendly_errors.fae8ee69", "🐝 公式计算错误"),
            tr("auto.friendly_errors.48067b4b", "公式 `{formula}` 无法计算。\n\n{detail}\n\n💡 常见问题：\n• 函数名拼写是否正确？\n• 参数数量是否正确？\n• 引用的单元格是否有效？\n• 范围格式是否正确（如 A1:B10）？").format(formula=formula, detail=detail)
        )

    @classmethod
    def show_unsaved_warning(cls, parent, filename: str = "未命名") -> bool:
        """显示未保存警告，返回用户是否选择继续"""
        reply = QMessageBox.question(
            parent,
            tr("auto.friendly_errors.ed73c2b2", "🐝 内容还未保存"),
            tr("auto.friendly_errors.2f55dbca", "「{filename}」中的内容可能还没有保存。\n\n建议先导出为 PDF 或保存为 Markdown 文件。\n\n确定要关闭吗？").format(filename=filename),
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )
        return reply == QMessageBox.Yes