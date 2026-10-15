# beeoffice/plugins/beesheet_ai_mixin.py
"""
蜜算 AI 助手（R5）：**面向表格**的三件事，全部走"本地优先 + 如实标注来源"。

## 做什么（刻意不追 WPS 那类"一键生成整表"）
1. **自然语言 → 公式建议**：用户用中文说需求（如"C 列 = A 列乘 B 列"），
   给出公式**并解释**。**只给建议，不自动改数据** —— 表格里的数据是用户的钱。
2. **表格问题解释**：先由**本地规则**查出事实（错误值、重复、公式兼容性等），
   再让 AI 用中文解释"这意味着什么、该怎么处理"。事实来自本地规则，AI 只负责解释。
3. **表格摘要**：把表头 + 少量样本 + 统计交给 AI，产出中文摘要。

## 与蜜写保持一致的规则（重要）
* **优先真 LLM**，走后台线程（`AsyncTaskManager`）；
* **没有可用 AI 或调用失败时绝不静默糊弄**：先说明原因并**征求同意**，
  同意后才给**本地规则**结果，且提示里写明"不是 AI 生成"；
* 来源标注沿用 `AIClient.last_source`（`ai` / `local` / `error`）。

## 依赖
`beeoffice.plugins.ai_client`（已有）+ 蜜算既有的审计/翻译能力（延迟 import）。
"""
import logging

from PySide6.QtWidgets import QMenu, QMessageBox

from beeoffice.async_task import AsyncTaskManager

#: 送进模型的样本行数 / 列数上限（表格可能几十万行，绝不能整表发过去）
CONTEXT_ROWS = 8
CONTEXT_COLS = 12
#: 摘要用的统计列上限
STAT_COLS = 8


# ======================================================================
# 纯函数：上下文与提示词（便于单独测试）
# ======================================================================
def build_sheet_context(df, max_rows: int = CONTEXT_ROWS,
                        max_cols: int = CONTEXT_COLS) -> str:
    """
    把表格压成一段**又短又能说明问题**的文字上下文。

    只发：形状（几行几列）+ **列字母与列名的对应** + 带**工作表行号**的少量样本。
    **不发整表** —— 几十万行既超上下文、也没必要。

    ⚠️ **必须给列字母**（实测教训）：第一版只给"制表符分隔的样本"，
    结果真模型把"数量×单价"写成 `=A2*B2`（实际应是 `=C2*D2`）——
    因为它根本不知道哪列是 A/B/C。摘要里也出现"nan 在数量和金额列"这种
    张冠李戴。给出 `A: 订单号、B: 客户…` 与真实行号后，模型才有正确的基础。
    """
    if df is None or getattr(df, "empty", True):
        return "（当前工作表没有数据）"

    from beeoffice.plugins.beesheet_utils import col_index_to_name

    all_columns = list(df.columns)
    cols = all_columns[:max_cols]
    hidden = len(all_columns) - len(cols)
    lines = [
        f"工作表共 {len(df)} 行 × {len(df.columns)} 列"
        f"（第 1 行是表头，数据从第 2 行开始）。",
        "列字母与列名："
        + "、".join(
            f"{col_index_to_name(i)}: {cols[i]}" for i in range(len(cols))
        )
        + (f"（另有 {hidden} 列未列出）" if hidden > 0 else ""),
        f"前 {min(max_rows, len(df))} 行样本（制表符分隔，行首是该行在"
        f"工作表里的真实行号）：",
    ]
    sample = df.head(max_rows)
    for offset, (_, row) in enumerate(sample.iterrows()):
        lines.append(
            f"{offset + 2}\t" + "\t".join(str(row[c]) for c in cols)
        )
    if len(df) > max_rows:
        lines.append(f"（另有 {len(df) - max_rows} 行未列出）")
    return "\n".join(lines)


def build_formula_prompt(description: str, context: str) -> str:
    """公式建议提示词：要求"只给公式 + 一句解释"。"""
    return (
        "你是电子表格助手。用户会用中文描述他想要的**计算**。\n"
        "请给出可直接使用的 Excel 公式，并附一句中文解释。\n"
        "要求：\n"
        "1. 先用一行输出公式本身（不要带 markdown 代码块、不要加引号）；\n"
        "2. 再用一行以「说明：」开头解释它做了什么；\n"
        "3. 如果信息不足，就指出还缺什么，不要编造列名。\n\n"
        f"【表格情况】\n{context}\n\n"
        f"【用户需求】\n{description.strip()}"
    )


def build_audit_prompt(findings: str) -> str:
    """审计解释提示词：事实由本地规则给出，AI 只解释与给建议。"""
    return (
        "你是电子表格审阅助手。下面是**本地规则**已经查出的表格问题（事实）：\n\n"
        f"{findings.strip()}\n\n"
        "请用中文：\n"
        "1. 概括这些问题说明了什么（按严重程度排序）；\n"
        "2. 每条给出**具体可执行**的处理建议；\n"
        "3. 不要重复罗列事实，不要编造没有提到的问题。"
    )


def build_summary_prompt(context: str) -> str:
    """表格摘要提示词：要点式、必须压缩。"""
    return (
        "请用中文总结这张工作表：先一句话概括它记录了什么，"
        "再用不超过 5 条要点说明关键信息（数量级、极值、缺失等）。"
        "必须压缩，不要逐行复述。\n\n"
        f"【表格情况】\n{context}"
    )


#: 本地关键词 → 公式（无 AI 时的兜底；**只是关键词匹配，不是理解**）
_LOCAL_FORMULA_HINTS = [
    (("求和", "合计", "总计", "加总"), "=SUM(范围)"),
    (("平均", "均值"), "=AVERAGE(范围)"),
    (("最大", "最高"), "=MAX(范围)"),
    (("最小", "最低"), "=MIN(范围)"),
    (("计数", "个数", "多少条", "多少行"), "=COUNT(范围)"),
    (("非空", "多少个有"), "=COUNTA(范围)"),
    (("四舍五入", "保留两位", "保留 2 位"), "=ROUND(数值, 2)"),
    (("条件求和", "满足条件求和"), "=SUMIF(条件区域, 条件, 求和区域)"),
    (("查找", "匹配", "对应"), "=VLOOKUP(查找值, 区域, 第几列, FALSE)"),
    (("如果", "条件判断"), "=IF(条件, 真值, 假值)"),
    (("拼接", "连接", "合并文本"), '=A2 & B2  或  =CONCAT(A2, B2)'),
    (("取整", "去掉小数"), "=INT(数值)"),
    (("去重", "重复项"), "=UNIQUE(范围)（Excel 365/WPS 新版）"),
]


def local_formula_hint(description: str):
    """
    本地兜底：**关键词匹配**给一个公式模板。

    ⚠️ 用**最长命中关键词优先**，而不是"按表顺序第一个命中" ——
    否则「满足条件求和」会被更靠前的泛化关键词「求和」抢走，
    给出 `SUM` 而不是 `SUMIF`（测试 `test_local_formula_hint_matches_keywords`
    当场抓到）。更具体的说法应当赢。

    :return: (公式, 命中的关键词) 或 (None, "")
    """
    text = (description or "").strip()
    if not text:
        return None, ""
    best = None
    for keywords, formula in _LOCAL_FORMULA_HINTS:
        for keyword in keywords:
            if keyword in text:
                if best is None or len(keyword) > len(best[1]):
                    best = (formula, keyword)
    if best is None:
        return None, ""
    return best


def local_sheet_summary(df) -> str:
    """本地兜底摘要：**只做统计，不做语义总结**（措辞必须诚实）。"""
    if df is None or getattr(df, "empty", True):
        return "（当前工作表没有数据）"
    lines = [f"共 {len(df)} 行 × {len(df.columns)} 列。"]
    numeric = df.select_dtypes(include="number")
    if not numeric.empty:
        lines.append("数值列统计：")
        for name in list(numeric.columns)[:STAT_COLS]:
            column = numeric[name].dropna()
            if column.empty:
                continue
            lines.append(
                f"· {name}：最小 {column.min():g}，最大 {column.max():g}，"
                f"平均 {column.mean():.4g}，缺失 {int(numeric[name].isna().sum())}"
            )
    missing_total = int(df.isna().sum().sum())
    if missing_total:
        lines.append(f"全表空单元格合计：{missing_total} 个。")
    return "\n".join(lines)


# ======================================================================
# Mixin
# ======================================================================
class SheetAIMixin:
    """蜜算 AI 助手（三个入口 + 设置入口）。"""

    # ------------------------------------------------------------------
    def _show_sheet_ai_menu(self):
        menu = QMenu(self)
        menu.addAction("🧮 用中文描述需求 → 公式建议").triggered.connect(
            self._ai_suggest_formula
        )
        menu.addAction("🔍 解释表格问题").triggered.connect(
            self._ai_explain_issues
        )
        menu.addAction("📝 生成表格摘要").triggered.connect(
            self._ai_summarize_sheet
        )
        menu.addSeparator()
        menu.addAction("⚙️ AI 设置…").triggered.connect(self._open_ai_settings)
        button = getattr(self, "_ai_btn", None)
        if button is not None:
            menu.exec(button.mapToGlobal(button.rect().bottomLeft()))
        else:
            menu.exec(self.mapToGlobal(self.rect().bottomLeft()))

    def _open_ai_settings(self):
        """从表格场景直接去配置 AI（否则用户不知道去哪填）。"""
        from beeoffice.ai_settings import show_ai_settings

        try:
            from beeoffice.settings import AppSettings

            show_ai_settings(self, settings=AppSettings())
        except Exception as e:  # noqa: BLE001
            logging.error(f"[蜜算 AI] 打开设置失败: {e}")
            QMessageBox.warning(self, "打不开 AI 设置", str(e))
            return
        self._ai_client = None          # 配置可能变了
        self._set_status("✅ AI 配置已更新")

    # ------------------------------------------------------------------
    def _get_ai_client(self):
        client = getattr(self, "_ai_client", None)
        if client is None:
            from beeoffice.plugins.ai_client import AIClient

            try:
                from beeoffice.settings import AppSettings

                client = AIClient.from_settings(AppSettings())
            except Exception as e:  # noqa: BLE001
                logging.debug(f"[蜜算 AI] 构造客户端失败: {e}")
                client = AIClient({})
            self._ai_client = client
        return client

    def _ask_use_local(self, action: str, reason: str) -> bool:
        """
        没有可用 AI 时征求同意（默认「否」）—— 与蜜写同一套做法。

        不静默糊弄：用户必须知道"接下来看到的不是 AI 生成的"。
        """
        reply = QMessageBox.question(
            self,
            f"{action}：没有可用的 AI",
            f"{reason}\n\n"
            f"是否改用**本地规则**做{action}？\n"
            "· 本地规则不联网、数据不出本机\n"
            "· 但能力有限：只会按关键词匹配/做统计，不是『理解』\n\n"
            "想真正用 AI，请到「帮助 → 🤖 AI 设置」填写服务商与 API Key"
            "（本地 Ollama 不需要 Key）。",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        return reply == QMessageBox.Yes

    def _run_sheet_ai(self, action, prompt, on_ai_text, build_local,
                      title="蜜算 AI"):
        """
        统一流程：真 LLM 优先 → 失败/未配置则征得同意后用本地规则。

        :param on_ai_text: 拿到 AI 文本后怎么展示/使用
        :param build_local: 本地兜底：callable() -> (文本, 说明) 或 (None, 原因)
        """
        client = self._get_ai_client()

        if not client.available:
            self._sheet_ai_fallback(
                action, client.unavailable_reason(), build_local
            )
            return

        self._set_status(f"⏳ AI 正在{action}…", 0)

        def on_result(result):
            ok, text = result
            if ok:
                try:
                    on_ai_text(text)
                except Exception as e:  # noqa: BLE001
                    logging.error(f"[蜜算 AI] {action}展示失败: {e}")
                    QMessageBox.warning(self, f"{action}失败", str(e))
                    return
                self._set_status(f"✅ {action}完成（{client.describe_source()}）")
            else:
                logging.warning(f"[蜜算 AI] {action}降级：{text}")
                self._sheet_ai_fallback(action, text, build_local)

        def on_error(error):
            logging.error(f"[蜜算 AI] {action}任务异常: {error}")
            self._sheet_ai_fallback(action, f"调用出错：{error}", build_local)

        AsyncTaskManager.run(
            client.chat, prompt, on_result=on_result, on_error=on_error,
        )

    def _sheet_ai_fallback(self, action, reason, build_local):
        """降级：先问，同意了才给本地结果，且**如实标注**。"""
        if not self._ask_use_local(action, reason):
            self._set_status(f"已取消（AI {action}不可用）")
            return
        try:
            text, note = build_local()
        except Exception as e:  # noqa: BLE001
            logging.error(f"[蜜算 AI] 本地{action}失败: {e}")
            QMessageBox.warning(self, f"本地{action}失败", str(e))
            return
        if not text:
            self._set_status(f"⚠️ {note or '本地规则没有产出内容'}")
            return
        self._sheet_ai_show_text(f"{action}（本地）", text, note=note)
        self._set_status(f"✅ 已给出本地结果（不是 AI 生成）：{action}")

    # ------------------------------------------------------------------
    def _sheet_ai_show_text(self, title, text, note=""):
        """把文本结果显示给用户（用只读文本框，便于复制）。"""
        from PySide6.QtWidgets import QDialog, QPlainTextEdit, QPushButton, \
            QVBoxLayout

        dialog = QDialog(self)
        dialog.setWindowTitle(title)
        dialog.resize(640, 420)
        layout = QVBoxLayout(dialog)
        editor = QPlainTextEdit(dialog)
        editor.setReadOnly(True)
        editor.setPlainText(text if not note else f"{text}\n\n—— {note}")
        layout.addWidget(editor)
        close = QPushButton("关闭", dialog)
        close.clicked.connect(dialog.accept)
        layout.addWidget(close)
        dialog.exec()
        return dialog

    def _sheet_source_label(self):
        client = self._get_ai_client()
        return client.describe_source()

    # ==================================================================
    # ① 自然语言 → 公式建议
    # ==================================================================
    def _ai_suggest_formula(self):
        from PySide6.QtWidgets import QInputDialog

        from beeoffice.plugins.beesheet_ai_mixin import (
            build_formula_prompt, build_sheet_context, local_formula_hint,
        )

        description, ok = QInputDialog.getMultiLineText(
            self, "用中文描述需求",
            "例如：把 A 列和 B 列相乘放到 C 列\n"
            "（只给公式建议，不会自动改你的数据）",
        )
        if not ok or not description.strip():
            return

        df = getattr(self.model, "df", None)
        context = build_sheet_context(df)

        def show(text):
            self._sheet_ai_show_text("公式建议", text)

        def build_local():
            formula, keyword = local_formula_hint(description)
            if not formula:
                return None, "本地关键词匹配没找到对应函数，请改用 AI"
            return (
                f"{formula}\n\n说明：按关键词「{keyword}」匹配到上面的模板；"
                f"请把「范围/数值」替换成你的实际区域。",
                "本地关键词匹配结果（不是 AI 理解，可能不适用你的具体情况）",
            )

        self._run_sheet_ai(
            "公式建议", build_formula_prompt(description, context),
            on_ai_text=show, build_local=build_local,
        )

    # ==================================================================
    # ② 解释表格问题（事实来自本地规则，AI 只解释）
    # ==================================================================
    def _collect_local_findings(self) -> str:
        """
        由**本地规则**收集事实：错误值 + 重复行 + 公式兼容性。

        这一步不依赖 AI —— 所以即使 AI 不可用，用户也能拿到"查出了什么"。
        """
        df = getattr(self.model, "df", None)
        findings = []
        if df is None or getattr(df, "empty", True):
            return "（当前工作表没有数据）"

        error_tokens = ("#DIV/0!", "#VALUE!", "#REF!", "#NAME?", "#N/A",
                        "#NULL!", "#NUM!")
        try:
            errors = {}
            for col in df.columns:
                series = df[col]
                if series.dtype == object:
                    for token in error_tokens:
                        count = int((series == token).sum())
                        if count:
                            errors[f"{col} → {token}"] = count
            for desc, count in list(errors.items())[:20]:
                findings.append(f"· 错误值：{desc}（{count} 处）")
        except Exception as e:  # noqa: BLE001
            logging.debug(f"[蜜算 AI] 错误值统计失败: {e}")

        try:
            duplicates = int(df.duplicated().sum())
            if duplicates:
                findings.append(f"· 完全重复的行：{duplicates} 行")
        except Exception as e:  # noqa: BLE001
            logging.debug(f"[蜜算 AI] 重复行统计失败: {e}")

        try:
            blanks = df.isna().sum()
            worst = [(str(name), int(count)) for name, count in blanks.items()
                     if count]
            worst.sort(key=lambda item: item[1], reverse=True)
            for name, count in worst[:10]:
                findings.append(f"· 空单元格：{name} 列 {count} 个")
        except Exception as e:  # noqa: BLE001
            logging.debug(f"[蜜算 AI] 空值统计失败: {e}")

        return "\n".join(findings) if findings else "· 本地规则没有发现明显问题"

    def _ai_explain_issues(self):
        from beeoffice.plugins.beesheet_ai_mixin import build_audit_prompt

        findings = self._collect_local_findings()

        def show(text):
            self._sheet_ai_show_text("表格问题解释", text)

        def build_local():
            return findings, "以上是**本地规则**查出的原始事实（未经 AI 解释汇总）"

        self._run_sheet_ai(
            "解释表格问题", build_audit_prompt(findings),
            on_ai_text=show, build_local=build_local,
        )

    # ==================================================================
    # ③ 表格摘要
    # ==================================================================
    def _ai_summarize_sheet(self):
        from beeoffice.plugins.beesheet_ai_mixin import (
            build_sheet_context, build_summary_prompt, local_sheet_summary,
        )

        df = getattr(self.model, "df", None)
        if df is None or getattr(df, "empty", True):
            QMessageBox.information(self, "提示", "当前工作表没有数据")
            return
        context = build_sheet_context(df)

        def show(text):
            self._sheet_ai_show_text("表格摘要", text)

        def build_local():
            return (
                local_sheet_summary(df),
                "本地统计摘要（不是 AI 生成；只有数字统计，没有语义总结）",
            )

        self._run_sheet_ai(
            "生成表格摘要", build_summary_prompt(context),
            on_ai_text=show, build_local=build_local,
        )
