# beeoffice/plugins/beeshow_constants.py
"""
蜜演常量与播放窗口

本模块提供：
  - SLIDE_THEMES      : 7 种幻灯片主题
  - ICON_LIBRARY      : 图标库（按分类）
  - TEMPLATE_LIBRARY  : 模板库
  - LAYOUTS           : 12 种预定义版式（任务 2.1）
  - LAYOUT_CSS        : 版式相关 CSS（含动态数字/视频/平滑动画样式）
  - _PlayWindow       : 全屏播放窗口（P0-2：转发键盘事件）

从 beeshow.py 抽取，让主文件聚焦业务组装。

v5.1 增量整合：
  - 任务 2.1：LAYOUTS（12 种版式）+ LAYOUT_CSS
  - 任务 5.1：动态数字 CSS（.dynamic-number）
  - 任务 5.3：视频嵌入 CSS（.slide video / .video-placeholder）
  - 任务 5.2：平滑动画 CSS（[data-morph-id]）
"""

from PySide6.QtWebEngineWidgets import QWebEngineView


# ==================== 7 种主题 ====================
SLIDE_THEMES = {
    "简约白": {
        "name": "简约白", "bg": "#FFFFFF",
        "css": """
            :root { --bg: #FFFFFF; --text: #333333; --accent: #FF8F00; --border: #FFB300; --code-bg: #F5F5F5; --table-header: #FFF3E0; }
            body { font-family: 'Segoe UI', '微软雅黑', sans-serif; background: var(--bg); color: var(--text); margin: 0; }
            .slide { width: 100vw; height: 100vh; display: flex; flex-direction: column; justify-content: center; align-items: center; padding: 60px 80px; box-sizing: border-box; }
            h1 { font-size: 3em; color: var(--accent); margin-bottom: 0.3em; }
            h2 { font-size: 2.2em; border-bottom: 3px solid var(--border); padding-bottom: 10px; }
            h3 { font-size: 1.7em; color: var(--accent); }
            ul, ol { font-size: 1.5em; line-height: 2; text-align: left; width: 100%; }
            li { margin: 8px 0; }
            p { font-size: 1.4em; line-height: 1.8; }
            code { background: var(--code-bg); padding: 2px 8px; border-radius: 4px; font-family: Consolas, monospace; font-size: 0.9em; }
            pre { background: var(--code-bg); padding: 20px; border-left: 4px solid var(--border); font-size: 1em; border-radius: 4px; width: 100%; overflow-x: auto; }
            table { border-collapse: collapse; margin: 20px auto; font-size: 1.2em; width: 100%; }
            th, td { border: 1px solid #DDD; padding: 12px 20px; text-align: left; }
            th { background: var(--table-header); font-weight: bold; }
            img, video { max-width: 100%; border-radius: 8px; box-shadow: 0 4px 12px rgba(0,0,0,0.1); }
            blockquote { border-left: 4px solid var(--border); padding-left: 20px; color: #888; font-style: italic; margin: 20px 0; }
            .slide-number { position: fixed; bottom: 20px; right: 30px; color: rgba(128,128,128,0.5); font-size: 14px; }
            .notes { display: none; }
            .laser { position: fixed; width: 20px; height: 20px; background: red; border-radius: 50%; pointer-events: none; z-index: 9999; display: none; box-shadow: 0 0 20px red; }
        """
    },
    "琥珀金": {
        "name": "琥珀金", "bg": "linear-gradient(135deg, #FFB300, #FF8F00)",
        "css": """
            :root { --bg: linear-gradient(135deg, #FFB300, #FF8F00); --text: #FFFFFF; --accent: #FFF; --border: rgba(255,255,255,0.5); --code-bg: rgba(0,0,0,0.2); --table-header: rgba(255,255,255,0.3); }
            body { font-family: 'Segoe UI', '微软雅黑', sans-serif; background: var(--bg); color: var(--text); margin: 0; min-height: 100vh; }
            .slide { width: 100vw; height: 100vh; display: flex; flex-direction: column; justify-content: center; align-items: center; padding: 60px 80px; box-sizing: border-box; }
            h1 { font-size: 3.5em; text-shadow: 2px 2px 4px rgba(0,0,0,0.2); }
            h2 { font-size: 2.5em; border-bottom: 3px solid var(--border); padding-bottom: 10px; }
            ul, ol { font-size: 1.6em; line-height: 2.2; background: var(--code-bg); padding: 30px 50px; border-radius: 12px; width: 100%; }
            p { font-size: 1.5em; }
            table { border-collapse: collapse; margin: 20px auto; font-size: 1.3em; background: var(--code-bg); border-radius: 8px; overflow: hidden; width: 100%; }
            th, td { border: 1px solid rgba(255,255,255,0.3); padding: 12px 20px; }
            th { background: var(--table-header); }
            img, video { max-width: 100%; border-radius: 8px; }
            .slide-number { position: fixed; bottom: 20px; right: 30px; color: rgba(255,255,255,0.6); font-size: 14px; }
            .notes { display: none; }
            .laser { position: fixed; width: 20px; height: 20px; background: red; border-radius: 50%; pointer-events: none; z-index: 9999; display: none; box-shadow: 0 0 20px red; }
        """
    },
    "科技黑": {
        "name": "科技黑", "bg": "#1E1E1E",
        "css": """
            :root { --bg: #1E1E1E; --text: #E0E0E0; --accent: #4FC3F7; --border: #4FC3F7; --code-bg: #2D2D2D; --table-header: #333; }
            body { font-family: 'Segoe UI', '微软雅黑', sans-serif; background: var(--bg); color: var(--text); margin: 0; }
            .slide { width: 100vw; height: 100vh; display: flex; flex-direction: column; justify-content: center; align-items: center; padding: 60px 80px; box-sizing: border-box; }
            h1 { font-size: 3em; color: var(--accent); }
            h2 { font-size: 2.2em; color: #81D4FA; border-bottom: 2px solid var(--border); padding-bottom: 10px; }
            ul, ol { font-size: 1.5em; line-height: 2; width: 100%; }
            code { background: #333; padding: 2px 8px; border-radius: 4px; color: #FFB300; }
            pre { background: var(--code-bg); padding: 20px; border-left: 4px solid var(--border); border-radius: 4px; width: 100%; }
            table { border-collapse: collapse; margin: 20px auto; font-size: 1.2em; width: 100%; }
            th, td { border: 1px solid #555; padding: 12px 20px; }
            th { background: var(--table-header); }
            img, video { max-width: 100%; border-radius: 8px; }
            .slide-number { position: fixed; bottom: 20px; right: 30px; color: rgba(255,255,255,0.4); font-size: 14px; }
            .notes { display: none; }
            .laser { position: fixed; width: 20px; height: 20px; background: red; border-radius: 50%; pointer-events: none; z-index: 9999; display: none; box-shadow: 0 0 20px red; }
        """
    },
    "森林绿": {
        "name": "森林绿", "bg": "#F1F8E9",
        "css": """
            :root { --bg: #F1F8E9; --text: #2E3B1F; --accent: #4CAF50; --border: #81C784; --code-bg: #E8F5E9; --table-header: #C8E6C9; }
            body { font-family: 'Segoe UI', '微软雅黑', sans-serif; background: var(--bg); color: var(--text); margin: 0; }
            .slide { width: 100vw; height: 100vh; display: flex; flex-direction: column; justify-content: center; align-items: center; padding: 60px 80px; box-sizing: border-box; }
            h1 { font-size: 3em; color: var(--accent); }
            h2 { font-size: 2.2em; border-bottom: 3px solid var(--border); padding-bottom: 10px; }
            ul, ol { font-size: 1.5em; line-height: 2; width: 100%; }
            code { background: var(--code-bg); padding: 2px 8px; border-radius: 4px; }
            pre { background: var(--code-bg); padding: 20px; border-left: 4px solid var(--border); border-radius: 4px; width: 100%; }
            table { border-collapse: collapse; margin: 20px auto; font-size: 1.2em; width: 100%; }
            th, td { border: 1px solid #A5D6A7; padding: 12px 20px; }
            th { background: var(--table-header); }
            img, video { max-width: 100%; border-radius: 8px; }
            .slide-number { position: fixed; bottom: 20px; right: 30px; color: rgba(0,0,0,0.3); font-size: 14px; }
            .notes { display: none; }
            .laser { position: fixed; width: 20px; height: 20px; background: red; border-radius: 50%; pointer-events: none; z-index: 9999; display: none; box-shadow: 0 0 20px red; }
        """
    },
    "海洋蓝": {
        "name": "海洋蓝", "bg": "#E3F2FD",
        "css": """
            :root { --bg: #E3F2FD; --text: #0D3B66; --accent: #2196F3; --border: #64B5F6; --code-bg: #BBDEFB; --table-header: #BBDEFB; }
            body { font-family: 'Segoe UI', '微软雅黑', sans-serif; background: var(--bg); color: var(--text); margin: 0; }
            .slide { width: 100vw; height: 100vh; display: flex; flex-direction: column; justify-content: center; align-items: center; padding: 60px 80px; box-sizing: border-box; }
            h1 { font-size: 3em; color: var(--accent); }
            h2 { font-size: 2.2em; border-bottom: 3px solid var(--border); padding-bottom: 10px; }
            ul, ol { font-size: 1.5em; line-height: 2; width: 100%; }
            code { background: var(--code-bg); padding: 2px 8px; border-radius: 4px; }
            pre { background: var(--code-bg); padding: 20px; border-left: 4px solid var(--border); border-radius: 4px; width: 100%; }
            table { border-collapse: collapse; margin: 20px auto; font-size: 1.2em; width: 100%; }
            th, td { border: 1px solid #90CAF9; padding: 12px 20px; }
            th { background: var(--table-header); }
            img, video { max-width: 100%; border-radius: 8px; }
            .slide-number { position: fixed; bottom: 20px; right: 30px; color: rgba(0,0,0,0.3); font-size: 14px; }
            .notes { display: none; }
            .laser { position: fixed; width: 20px; height: 20px; background: red; border-radius: 50%; pointer-events: none; z-index: 9999; display: none; box-shadow: 0 0 20px red; }
        """
    },
    "日落橙": {
        "name": "日落橙", "bg": "#FFF3E0",
        "css": """
            :root { --bg: #FFF3E0; --text: #4E342E; --accent: #FF7043; --border: #FFAB91; --code-bg: #FBE9E7; --table-header: #FFCCBC; }
            body { font-family: 'Segoe UI', '微软雅黑', sans-serif; background: var(--bg); color: var(--text); margin: 0; }
            .slide { width: 100vw; height: 100vh; display: flex; flex-direction: column; justify-content: center; align-items: center; padding: 60px 80px; box-sizing: border-box; }
            h1 { font-size: 3em; color: var(--accent); }
            h2 { font-size: 2.2em; border-bottom: 3px solid var(--border); padding-bottom: 10px; }
            ul, ol { font-size: 1.5em; line-height: 2; width: 100%; }
            code { background: var(--code-bg); padding: 2px 8px; border-radius: 4px; }
            pre { background: var(--code-bg); padding: 20px; border-left: 4px solid var(--border); border-radius: 4px; width: 100%; }
            table { border-collapse: collapse; margin: 20px auto; font-size: 1.2em; width: 100%; }
            th, td { border: 1px solid #FFCCBC; padding: 12px 20px; }
            th { background: var(--table-header); }
            img, video { max-width: 100%; border-radius: 8px; }
            .slide-number { position: fixed; bottom: 20px; right: 30px; color: rgba(0,0,0,0.3); font-size: 14px; }
            .notes { display: none; }
            .laser { position: fixed; width: 20px; height: 20px; background: red; border-radius: 50%; pointer-events: none; z-index: 9999; display: none; box-shadow: 0 0 20px red; }
        """
    },
    "薰衣紫": {
        "name": "薰衣紫", "bg": "#F3E5F5",
        "css": """
            :root { --bg: #F3E5F5; --text: #4A148C; --accent: #9C27B0; --border: #CE93D8; --code-bg: #E1BEE7; --table-header: #E1BEE7; }
            body { font-family: 'Segoe UI', '微软雅黑', sans-serif; background: var(--bg); color: var(--text); margin: 0; }
            .slide { width: 100vw; height: 100vh; display: flex; flex-direction: column; justify-content: center; align-items: center; padding: 60px 80px; box-sizing: border-box; }
            h1 { font-size: 3em; color: var(--accent); }
            h2 { font-size: 2.2em; border-bottom: 3px solid var(--border); padding-bottom: 10px; }
            ul, ol { font-size: 1.5em; line-height: 2; width: 100%; }
            code { background: var(--code-bg); padding: 2px 8px; border-radius: 4px; }
            pre { background: var(--code-bg); padding: 20px; border-left: 4px solid var(--border); border-radius: 4px; width: 100%; }
            table { border-collapse: collapse; margin: 20px auto; font-size: 1.2em; width: 100%; }
            th, td { border: 1px solid #CE93D8; padding: 12px 20px; }
            th { background: var(--table-header); }
            img, video { max-width: 100%; border-radius: 8px; }
            .slide-number { position: fixed; bottom: 20px; right: 30px; color: rgba(0,0,0,0.3); font-size: 14px; }
            .notes { display: none; }
            .laser { position: fixed; width: 20px; height: 20px; background: red; border-radius: 50%; pointer-events: none; z-index: 9999; display: none; box-shadow: 0 0 20px red; }
        """
    },
}


# ==================== 图标库 ====================
ICON_LIBRARY = {
    "常用": ["📊", "📈", "📉", "📋", "📌", "📎", "🔍", "💡", "⭐", "✅", "❌", "⚠️", "🔥", "💎", "🎯", "🏆"],
    "箭头": ["➡️", "⬅️", "⬆️", "⬇️", "↗️", "↘️", "🔄", "🔃"],
    "商务": ["💼", "🤝", "📅", "💰", "📧", "📱", "🌐", "🏢", "📝", "🗂️"],
    "表情": ["😊", "🎉", "👍", "👏", "🤔", "💪", "🙏", "🚀"],
}


# ==================== 模板库 ====================
TEMPLATE_LIBRARY = {
    "工作汇报": """# 工作汇报\n\n**汇报人**：  \n**日期**：{date}\n\n---\n\n## 本周工作进展\n\n- 完成任务1\n- 完成任务2\n\n---\n\n## 数据展示\n\n| 指标 | 数值 | 环比 |\n|------|------|------|\n| 销售额 | | |\n| 用户数 | | |\n\n---\n\n## 下周计划\n\n- 计划1\n- 计划2\n\n---\n\n## 需要支持\n\n- \n""",
    "项目路演": """# 项目名称\n\n## 一句话介绍\n\n> \n\n---\n\n## 痛点分析\n\n- 痛点1\n- 痛点2\n\n---\n\n## 解决方案\n\n1. 方案1\n2. 方案2\n\n---\n\n## 市场数据\n\n| 项目 | 数据 |\n|------|------|\n| 市场规模 | |\n| 目标用户 | |\n\n---\n\n## 团队介绍\n\n- \n""",
    "学术答辩": """# 论文题目\n\n**作者**：  \n**导师**：\n\n---\n\n## 研究背景\n\n- \n\n---\n\n## 研究方法\n\n1. \n2. \n\n---\n\n## 实验结果\n\n| 方法 | 准确率 | 召回率 |\n|------|--------|--------|\n| | | |\n\n---\n\n## 结论与展望\n\n> \n""",
}


# ==================== 版式系统（任务 2.1） ====================
# 版式元数据：
#   id          : 唯一标识（用于 _apply_layout）
#   name        : 中文名（UI 显示）
#   icon        : emoji 图标
#   description : 一句话说明
#   skeleton    : Markdown 骨架（含 {title} 占位符）
LAYOUTS = {
    "title_only": {
        "name": "标题页",
        "icon": "📌",
        "description": "大标题 + 副标题",
        "skeleton": "# 演示标题\n\n> 副标题 / 演讲人 / 日期\n",
    },
    "title_content": {
        "name": "标题+正文",
        "icon": "📄",
        "description": "最常用的正文页",
        "skeleton": "# 页面标题\n\n- 要点1\n- 要点2\n- 要点3\n",
    },
    "two_column": {
        "name": "两栏对比",
        "icon": "⚖️",
        "description": "左右对比布局",
        "skeleton": (
            "# 对比标题\n\n"
            "<div class=\"columns\">\n"
            "<div class=\"column\">\n\n"
            "## 左栏\n\n- 项目1\n- 项目2\n\n"
            "</div>\n"
            "<div class=\"column\">\n\n"
            "## 右栏\n\n- 项目1\n- 项目2\n\n"
            "</div>\n"
            "</div>\n"
        ),
    },
    "three_column": {
        "name": "三栏卡片",
        "icon": "🎴",
        "description": "并排展示 3 个要点",
        "skeleton": (
            "# 三个要点\n\n"
            "<div class=\"columns\">\n"
            "<div class=\"column\">\n\n"
            "### 要点1\n\n说明文字\n\n"
            "</div>\n"
            "<div class=\"column\">\n\n"
            "### 要点2\n\n说明文字\n\n"
            "</div>\n"
            "<div class=\"column\">\n\n"
            "### 要点3\n\n说明文字\n\n"
            "</div>\n"
            "</div>\n"
        ),
    },
    "data_table": {
        "name": "数据表格",
        "icon": "📊",
        "description": "对比数据的表格页",
        "skeleton": (
            "# 数据对比\n\n"
            "| 指标 | 本期 | 上期 | 环比 |\n"
            "|------|------|------|------|\n"
            "| 数值1 | - | - | - |\n"
            "| 数值2 | - | - | - |\n"
            "| 数值3 | - | - | - |\n"
        ),
    },
    "image_caption": {
        "name": "图片+说明",
        "icon": "🖼️",
        "description": "大图配文字说明",
        "skeleton": (
            "# 页面标题\n\n"
            "![](图片路径.png)\n\n"
            "**说明**：在此输入图片说明\n"
        ),
    },
    "quote": {
        "name": "引用页",
        "icon": "💬",
        "description": "突出展示一句金句",
        "skeleton": (
            "# 引用\n\n"
            "> 这里是引用的名言或金句。\n"
            ">\n"
            "> —— 作者\n"
        ),
    },
    "timeline": {
        "name": "时间线",
        "icon": "📅",
        "description": "展示项目阶段与进度",
        "skeleton": (
            "# 项目时间线\n\n"
            "- **2026 Q1** 需求分析\n"
            "- **2026 Q2** 设计开发\n"
            "- **2026 Q3** 测试上线\n"
            "- **2026 Q4** 迭代优化\n"
        ),
    },
    "process": {
        "name": "流程步骤",
        "icon": "🔢",
        "description": "有序的步骤讲解",
        "skeleton": (
            "# 操作流程\n\n"
            "1. 第一步：说明\n"
            "2. 第二步：说明\n"
            "3. 第三步：说明\n"
            "4. 第四步：说明\n"
        ),
    },
    "summary": {
        "name": "总结页",
        "icon": "🎯",
        "description": "回顾要点 / 下一步",
        "skeleton": (
            "# 总结\n\n"
            "## 本次回顾\n\n"
            "- 要点1\n"
            "- 要点2\n\n"
            "## 下一步\n\n"
            "- 行动项1\n"
            "- 行动项2\n"
        ),
    },
    "ending": {
        "name": "结束页",
        "icon": "🐝",
        "description": "感谢观看 / 联系方式",
        "skeleton": (
            "# 感谢聆听\n\n"
            "> 联系方式 / 二维码\n"
        ),
    },
    "blank": {
        "name": "空白页",
        "icon": "⬜",
        "description": "从零开始自由编排",
        "skeleton": "# 新页面\n\n",
    },
}


# ==================== 版式 CSS ====================
# 与主题 CSS 拼接使用：full_css = theme_css + LAYOUT_CSS
# 主题管配色，版式管布局
LAYOUT_CSS = """
/* ===== 两栏 / 三栏布局 ===== */
.columns {
    display: flex;
    gap: 32px;
    width: 100%;
    margin: 20px 0;
    align-items: flex-start;
}
.column {
    flex: 1;
    text-align: left;
}
.column h2, .column h3 {
    margin-top: 0;
    border-bottom: 2px solid rgba(128,128,128,0.3);
    padding-bottom: 6px;
}

/* ===== 表格 ===== */
.slide table {
    border-collapse: collapse;
    margin: 24px auto;
    width: 100%;
}
.slide th {
    font-weight: bold;
}
.slide tr:nth-child(even) td {
    background: rgba(128,128,128,0.05);
}

/* ===== 引用 ===== */
.slide blockquote {
    border-left: 5px solid currentColor;
    padding-left: 24px;
    margin: 32px 0;
    font-style: italic;
    opacity: 0.85;
}

/* ===== 列表 ===== */
.slide ul, .slide ol {
    padding-left: 1.5em;
}
.slide li {
    margin: 10px 0;
}

/* ===== 图片 ===== */
.slide img {
    display: block;
    margin: 20px auto;
    max-width: 100%;
    border-radius: 8px;
}
.slide img + p, .slide img + em {
    text-align: center;
    color: rgba(128,128,128,0.8);
    font-size: 0.9em;
    margin-top: 8px;
}

/* ===== 标题页居中（用于 title_only 版式） ===== */
.slide h1:only-child,
.slide > h1:first-child:last-child {
    text-align: center;
    margin-top: 30vh;
}

/* ===== 响应式（窄屏） ===== */
@media (max-width: 800px) {
    .columns {
        flex-direction: column;
    }
}

/* ===== 动态数字（任务 5.1） ===== */
.dynamic-number {
    font-weight: bold;
    font-variant-numeric: tabular-nums;
    /* tabular-nums 让数字等宽，滚动时不会抖动 */
    display: inline-block;
    min-width: 1em;
}

/* 大屏演示时字号跟随上下文 */
.slide h1 .dynamic-number {
    font-size: 1.1em;
}
.slide .dynamic-number {
    color: inherit;
}

/* ===== 视频嵌入（任务 5.3） ===== */
.slide video {
    max-width: 100%;
    border-radius: 8px;
    box-shadow: 0 4px 12px rgba(0,0,0,0.15);
    background: #000;
}

/* 视频占位符 */
.slide .video-placeholder {
    white-space: pre-line;
    line-height: 1.6;
}

/* ===== 平滑动画（任务 5.2） ===== */
[data-morph-id] {
    will-change: transform;
    backface-visibility: hidden;
}

/* 平滑过渡时的临时样式 */
[data-morph-id].morphing {
    pointer-events: none;
    z-index: 1000 !important;
}
"""


# ==================== 播放窗口（P0-2） ====================
class _PlayWindow(QWebEngineView):
    """
    蜜演全屏播放窗口。

    P0-2：独立 QWebEngineView 时，键盘焦点在 WebView 上，
          BeeShowView.keyPressEvent 收不到事件。此处转发给主视图处理。
    """

    def __init__(self, owner):
        super().__init__(owner)
        self._owner = owner

    def keyPressEvent(self, event):
        # P0-2：转发给主视图，由其处理翻页 / ESC / 激光笔等
        if self._owner is not None:
            self._owner.keyPressEvent(event)
        else:
            super().keyPressEvent(event)

    def keyReleaseEvent(self, event):
        if self._owner is not None:
            self._owner.keyReleaseEvent(event)
        else:
            super().keyReleaseEvent(event)