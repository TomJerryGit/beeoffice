# beeoffice/shortcuts.py
"""
快捷键帮助模块

【P0-7 修复说明】
  本文件描述的快捷键与代码实际绑定一一对应。
  如修改了某个 QShortcut，请同步更新此处。

验证来源：
  - 全局：beeoffice/app.py、beeoffice/menus.py
  - 蜜写：beeoffice/plugins/beewrite.py
  - 蜜算：beeoffice/plugins/beesheet.py
  - 蜜演：beeoffice/plugins/beeshow.py

注意事项：
  - Ctrl+Z / Ctrl+Y 使用 Qt 内置 QKeySequence.Undo / Redo；
    Mac 上 Redo 会自动映射为 Cmd+Shift+Z，本表仅列 Windows 键位
  - 同一按键在不同控件里语义可能不同（如 Ctrl+B 在蜜写/蜜算都是加粗）
  - 蜜演的 B/L/P/R/F 只在「全屏播放」状态下生效
"""

SHORTCUTS = {
    "全局": [
        ("Ctrl+Shift+P", "打开命令面板"),
        ("Ctrl+N", "新建蜜写文档"),
        ("Ctrl+T", "新建蜜算表格"),
        ("Ctrl+Shift+T", "从模板新建"),
        ("Ctrl+O", "打开文件"),
        ("Ctrl+S", "保存当前文件"),
        ("Ctrl+Shift+S", "另存为"),
        ("Ctrl+W", "关闭当前标签"),
        ("Ctrl+Tab", "切换到下一个标签"),
        ("Ctrl+Shift+Tab", "切换到上一个标签"),
        ("Ctrl+Z", "撤销（当前控件）"),
        ("Ctrl+Y", "重做（当前控件）"),
        ("Ctrl+F", "查找替换"),
        ("Ctrl+\\", "分屏"),
        ("Ctrl+Q", "退出应用"),
    ],
    "蜜写 BeeWrite": [
        ("Ctrl+S", "保存文档"),
        ("Ctrl+B", "加粗"),
        ("Ctrl+I", "斜体"),
        ("Ctrl+U", "下划线"),
        ("Ctrl+K", "插入超链接"),
        ("Ctrl+P", "打印预览"),
        ("Ctrl+Shift+V", "无格式粘贴"),
        ("Ctrl+Shift+I", "插入图片"),
        ("Ctrl+Shift+E", "插入数学公式"),
        ("Ctrl+Shift+R", "修订模式（开 / 关）"),
        ("Ctrl+Alt+M", "添加批注"),
        ("Ctrl+Shift+B", "添加书签"),
        ("Ctrl+B, G", "打开书签列表"),
        ("Ctrl+Shift+O", "大纲面板（开 / 关）"),
        ("F11", "阅读模式（开 / 关）"),
        ("F3", "查找下一个"),
        ("Shift+F3", "查找上一个"),
        ("Escape", "关闭查找栏"),
        ("Alt+↓ / Alt+↑", "Markdown 表格：插入行"),
        ("Alt+← / Alt+→", "Markdown 表格：插入列"),
    ],
    "蜜算 BeeSheet": [
        ("Ctrl+Z", "撤销"),
        ("Ctrl+Y", "重做"),
        ("Ctrl+D", "向下填充"),
        ("Ctrl+R", "向右填充"),
        ("Ctrl+H", "查找替换"),
        ("Ctrl+G", "定位到单元格"),
        ("Ctrl+E", "智能填充"),
        ("F2", "编辑当前单元格"),
        ("F1", "查看当前函数的帮助"),
        ("Alt+=", "自动求和"),
        ("Ctrl+;", "插入当前日期"),
        ("Ctrl+Shift+:", "插入当前时间"),
        ("Ctrl+B", "单元格加粗"),
        ("Ctrl+I", "单元格斜体"),
        ("Ctrl+U", "单元格下划线"),
        ("Ctrl+[", "追踪引用单元格"),
        ("Ctrl+]", "追踪从属单元格"),
        ("Ctrl+Shift+[", "清除审计高亮"),
    ],
    "蜜演 BeeShow": [
        ("F5", "从头开始播放"),
        ("Escape", "退出播放"),
        ("→ / ↓ / Space", "下一张"),
        ("← / ↑", "上一张"),
        ("PageDown / PageUp", "下一张 / 上一张"),
        ("Home / End", "第一张 / 最后一张"),
        ("F", "全屏切换"),
        ("B", "黑屏"),
        ("L", "激光笔（开 / 关）"),
        ("P", "画笔（开 / 关）"),
        ("R", "排练计时（开 / 关）"),
    ],
    "PDF 批注": [
        ("鼠标拖拽", "在 PDF 页面上拖动以绘制批注区域"),
        ("🎨 颜色", "切换批注颜色"),
        ("◀ / ▶", "上一页 / 下一页"),
        ("💾 保存批注", "保存为 .beeanno 文件"),
        ("🔥 烧录", "将批注写入 PDF"),
        ("↩ 撤销", "撤销最后一处批注"),
    ],
    "编辑通用": [
        ("Ctrl+X", "剪切"),
        ("Ctrl+C", "复制"),
        ("Ctrl+V", "粘贴"),
        ("Ctrl+A", "全选"),
    ],
}


def get_shortcut_help() -> str:
    """生成 Markdown 格式的快捷键帮助文本"""
    lines = ["# 🐝 蜜蜂办公快捷键\n"]
    for category, items in SHORTCUTS.items():
        lines.append(f"## {category}\n")
        for key, desc in items:
            lines.append(f"- `{key}` — {desc}")
        lines.append("")
    return "\n".join(lines)


def get_shortcut_dict() -> dict:
    """返回快捷键字典，供其他模块使用"""
    return SHORTCUTS


def get_shortcuts_by_category(category: str) -> list:
    """获取指定分类下的所有快捷键"""
    return SHORTCUTS.get(category, [])