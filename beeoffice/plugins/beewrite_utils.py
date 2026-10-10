# beeoffice/plugins/beewrite_utils.py
"""
蜜写工具函数与全局状态

本模块提供：
  1. 格式刷全局状态（FormatPainterState + FORMAT_PAINTER）
  2. HTML 转义（safe_escape_html）—— 供修订对比 / 双屏对比共用
  3. 字数统计（count_words）—— 支持中英文混合
  4. Markdown 表格解析（parse_md_table）
  5. Markdown 表格渲染（render_md_table）
  6. 光标处 Markdown 表格范围检测（detect_md_table_at_cursor）

设计原则：
  - 纯函数 / 纯工具，不依赖 BeeWriteEditor 实例
  - detect_md_table_at_cursor 接收 editor 参数，
    由 TableMixin 里的实例方法做薄封装
  - 不导入任何 beewrite_* 模块，避免循环依赖
"""
import re


# ==================== HTML 转义 ====================
def safe_escape_html(text: str) -> str:
    """
    将文本中的 HTML 特殊字符转义，并将空格替换为 &nbsp;。
    用于把纯文本塞进 QTextEdit.setHtml() 时避免被当作标签解析。
    """
    if not text:
        return ""
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace(" ", "&nbsp;")
    )


# ==================== 字数统计 ====================
# 需要从统计中剔除的 Markdown 标记字符
_MD_MARKUP_PATTERN = re.compile(r"[#*`>~\-\[\]\(\)]")


def count_words(text: str) -> int:
    """
    统计文本字数：
      - 中文字符：每个字符计为 1
      - 英文单词：按连续字母计为 1
      - 数字串：按连续数字计为 1
    会先去除常见 Markdown 标记，避免干扰。
    """
    if not text:
        return 0
    cleaned = _MD_MARKUP_PATTERN.sub(" ", text)
    cn_chars = len(re.findall(r"[\u4e00-\u9fff]", cleaned))
    en_words = len(re.findall(r"[a-zA-Z]+", cleaned))
    nums = len(re.findall(r"\d+", cleaned))
    return cn_chars + en_words + nums


# ==================== 格式刷状态 ====================
class FormatPainterState:
    """
    全局格式刷状态。

    使用方式：
        FORMAT_PAINTER.copy_from_cursor(cursor)   # 复制光标/选区格式
        FORMAT_PAINTER.apply_to_cursor(cursor)    # 应用到另一个光标
        FORMAT_PAINTER.clear()                     # 清理
    """

    def __init__(self):
        self.active = False
        self.char_format = None
        self.block_format = None

    def copy_from_cursor(self, cursor):
        """从 cursor 复制字符格式与块格式"""
        self.char_format = cursor.charFormat()
        self.block_format = cursor.blockFormat()
        self.active = True

    def apply_to_cursor(self, cursor) -> bool:
        """
        把已复制的格式应用到 cursor。
        若尚未复制任何格式，返回 False。
        """
        if not self.active or not self.char_format:
            return False
        cursor.mergeCharFormat(self.char_format)
        cursor.mergeBlockFormat(self.block_format)
        return True

    def clear(self):
        """清空格式刷状态"""
        self.active = False
        self.char_format = None
        self.block_format = None


# 全局单例
FORMAT_PAINTER = FormatPainterState()


# ==================== Markdown 表格：解析 ====================
def parse_md_table(lines):
    """
    将 Markdown 表格行（含分隔行）解析为二维列表。

    输入形如：
        | A | B |
        |---|---|
        | 1 | 2 |

    返回：
        [["A", "B"], ["1", "2"]]
    空行 / 非表格行会被跳过，分隔行会被剔除。
    """
    rows = []
    for line in lines:
        s = line.strip()
        if not (s.startswith("|") and s.endswith("|")):
            continue
        inner = s.strip("|")
        # 跳过分隔行（如 ---: | ---:）
        if all(c in "-:| " for c in inner) and "-" in inner:
            continue
        cells = [c.strip() for c in s.strip("|").split("|")]
        rows.append(cells)
    return rows


# ==================== Markdown 表格：渲染 ====================
def render_md_table(rows):
    """
    将二维列表渲染为 Markdown 表格文本。
    自动补齐每行列数，并在第二行插入分隔行。

    输入：
        [["A", "B"], ["1", "2"]]
    输出：
        | A | B |
        |---|---|
        | 1 | 2 |
    """
    if not rows:
        return ""
    n_cols = max(len(r) for r in rows)
    out = []
    for i, row in enumerate(rows):
        row = list(row) + [""] * (n_cols - len(row))
        out.append("| " + " | ".join(row) + " |")
        if i == 0:
            out.append("|" + "|".join(["---"] * n_cols) + "|")
    return "\n".join(out)


# ==================== Markdown 表格：光标范围检测 ====================
def _is_table_line(line: str) -> bool:
    """判断一行是否为 Markdown 表格行（以 | 开头结尾且内部含 |）"""
    s = line.strip()
    return s.startswith("|") and s.endswith("|") and "|" in s[1:-1]


def _is_separator_line(line: str) -> bool:
    """判断一行是否为 Markdown 表格分隔行（如 | --- | --- |）"""
    s = line.strip()
    if not (s.startswith("|") and s.endswith("|")):
        return False
    inner = s.strip("|")
    return all(c in "-:| " for c in inner) and "-" in inner


def detect_md_table_at_cursor(editor):
    """
    检测编辑器光标所在的 Markdown 表格范围。

    :param editor: QPlainTextEdit 实例
    :return: (start_line, end_line) 或 None（光标不在表格内）

    说明：
      - 只有当表格块中存在至少一个分隔行时才认为是合法表格
      - 需要调用方保证 editor 非 None
    """
    if editor is None:
        return None

    cursor = editor.textCursor()
    current_line = cursor.blockNumber()
    text = editor.toPlainText()
    lines = text.split("\n")

    if current_line >= len(lines):
        return None

    if not _is_table_line(lines[current_line]):
        return None

    # 向上扩展
    start = current_line
    while start > 0 and _is_table_line(lines[start - 1]):
        start -= 1

    # 向下扩展
    end = current_line
    while end < len(lines) - 1 and _is_table_line(lines[end + 1]):
        end += 1

    # 必须有分隔行才认为是合法表格
    has_separator = any(
        _is_separator_line(lines[i])
        for i in range(start, end + 1)
    )
    if not has_separator:
        return None

    return (start, end)