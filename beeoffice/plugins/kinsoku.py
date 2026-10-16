# beeoffice/plugins/kinsoku.py
"""
R2 避尾（行尾不出现开启标点）：**实测结论是"Qt 富文本做不到"**。

⚠️ **本模块不被产品代码使用** —— 它保留下来是为了：
  1. 记录这次实测的**方法与数据**（含一个修正过的仪器）；
  2. 被 `tests/fidelity/test_r2_kinsoku_limitation.py` 当作**金丝雀**：
     如果哪次 Qt 升级后测试失败了，说明引擎开始认"禁断标记"了 → R2 可以重做。

## 实测（详见 `docs/r2-中文排版-spike.md`）
用"排版后读 `QTextLayout` 实际断行"的仪器，判据是**行末的最后一个可见字符**
是否是开启标点；并把**我们插入的标记也剥掉**再判断（这一点是踩坑换来的，见下）。

| 插入的标记 | 避尾违规（21 个宽度合计） | 判定 |
|---|---|---|
| 不处理（基线） | 21 | — |
| `U+2060` WORD JOINER | **21** | ❌ 与基线相同 → **Qt 不认** |
| `U+200D` ZWJ | **21** | ❌ 与基线相同 |
| `U+FEFF` ZWNBSP | 21 | ❌ 与基线相同 |
| `U+00A0` 不换行空格 | 21 | ❌ 与基线相同 |
| `U+2007` 数字空格 | 21 | ❌ 与基线相同 |
| `U+200B` 零宽空格（**负对照**） | 316 | 它提供断行机会 → 证明仪器能分辨差异 |

**结论**：Qt 5/6 的富文本断行**不认**这些"两侧禁断"的行断类（`WJ`/`ZWJ` 都没实现
到这条 CJK 路径上），所以**避尾无法用插入文本标记实现**。
真要做得自己实现行断（自定义 `QAbstractTextDocumentLayout`），
成本远超收益、且会牵动编辑器的绘制与光标逻辑 —— **决定不做**。
（顺带：**避头**是 Qt 自带的，默认 0 违规，本来就不需要做；
标点挤压也无现成开关，同样不做。）

## 两次仪器踩坑（这就是为什么本模块的判据要这么写）
1. 第一版判据没有"把插入的标记剥掉"：于是"行末是零宽 ZWJ"被算成
   "末字符不是开启标点" → 得出**假的 0 违规**，差一点就把一个**无效方案**当成成功；
2. 更早的 spike 第一版则连布局都没触发布局（`documentLayout().documentSize()` 没调），
   行列表为空 → 也是假的 0。
   **两次都是"好消息"来自坏仪器** —— 所以本模块的判据必须自带负对照。
"""

#: 开启标点：出现在**行尾**会很别扭的那一类（避尾要管的就这几个）
OPENING_PUNCTUATION = "（《「『【“‘"
#: 关闭标点：Qt 已自带避头，这里列出只为文档与测试说明
CLOSING_PUNCTUATION = "，。、；：？！）》」』】”’"

#: 实测过的候选标记（全部无效；保留供金丝雀测试复测）
CANDIDATE_MARKERS = {
    "U+2060 WORD JOINER": "\u2060",
    "U+200D ZWJ": "\u200d",
    "U+FEFF ZWNBSP": "\ufeff",
    "U+00A0 不换行空格": "\u00a0",
    "U+2007 数字空格": "\u2007",
}
#: 负对照：**提供**断行机会的零宽空格（违规应显著多于基线）
NEGATIVE_CONTROL = "\u200b"

#: 判据里要剥掉的零宽字符（`U+200D` 只在"紧跟开启标点"时剥，避免误伤 emoji）
LEGACY_ZERO_WIDTH = "\u2060\ufeff\u200b"


def apply_marker(text: str, marker: str = "\u2060") -> str:
    """在开启标点后插入 `marker`（复现当初的候选方案，供测试对照用）。"""
    if not text:
        return text or ""
    out = []
    for index, char in enumerate(text):
        out.append(char)
        if char in OPENING_PUNCTUATION:
            following = text[index + 1] if index + 1 < len(text) else ""
            if following and following not in (marker, "\n"):
                out.append(marker)
    return "".join(out)


def strip_markers(text: str) -> str:
    """
    剥掉"排版用"的隐形字符（判据与清理都用它）。

    `U+200D` **只清紧跟开启标点的那一个**：全局清会拆散 emoji 组合序列
    （👨‍👩‍👧 靠 ZWJ 连接）。
    """
    if not text:
        return text or ""
    out = []
    previous = ""
    for char in text:
        if char in LEGACY_ZERO_WIDTH:
            continue
        if char == "\u200d" and previous in OPENING_PUNCTUATION:
            continue
        out.append(char)
        previous = char
    return "".join(out)


def kin_violations(lines) -> list:
    """
    判据：返回**行尾（剥离标记后）是开启标点**的行。

    ⚠️ 必须剥标记再看末字符 —— 否则"行末是零宽 ZWJ"会被漏判，
    得出假的"已修好"（本模块踩过这个坑）。
    """
    bad = []
    for line in lines:
        visible = strip_markers(line)
        if visible and visible[-1] in OPENING_PUNCTUATION:
            bad.append(visible)
    return bad


def measure_violations(make_lines, text: str, widths) -> int:
    """
    在多个宽度下统计避尾违规总数。

    :param make_lines: `(text, width) -> [每行文本]`
    """
    total = 0
    for width in widths:
        total += len(kin_violations(make_lines(text, width)))
    return total
