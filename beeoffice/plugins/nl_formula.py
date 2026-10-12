# beeoffice/plugins/nl_formula.py
"""
自然语言公式解析器：将中文指令转换为 Excel 公式或特殊操作

支持示例：
    "求和A1到A10"       -> "=SUM(A1:A10)"
    "平均值B列"         -> "=AVERAGE(B:B)"
    "最大值A1到A5"      -> "=MAX(A1:A5)"
    "筛选大于100的行"    -> "FILTER:>:100"
    "计数C列"           -> "=COUNT(C:C)"
    "查找A1在B到C列"     -> "VLOOKUP"

v5.0.8 修复（优化规划 §2.5）：
  - IF 指令的真值与假值此前会变成同一个值：
        如果A1大于10就显示'高'  ->  =IF(A1>10,"高","高")
    原因是 `_extract_value` 在找不到「否则」时**无条件**落到"取全文第一个引号
    内容"的兜底分支，把真值又取了回来。现在只有当**未指定关键词**时才使用该
    兜底；指定了关键词却没命中时返回空串，由上层用默认假值 "否" 补上。
    注：本文档上方此前已写"修复 IF 真假值同值问题"，但代码里该缺陷一直存在
    （旧测试只断言 `"IF" in result` 与 `'"高"' in result`，因此没被发现）。
"""
import re
import logging


class NLFormulaParser:
    """自然语言公式解析器"""

    # 函数关键字映射
    SUM_KEYWORDS = ["求和", "总计", "合计", "累加", "总和", "总数"]
    AVG_KEYWORDS = ["平均", "均值", "平均值"]
    MAX_KEYWORDS = ["最大", "最大值", "最高"]
    MIN_KEYWORDS = ["最小", "最小值", "最低"]
    COUNT_KEYWORDS = ["计数", "统计个数", "统计数量", "数量"]
    FILTER_KEYWORDS = ["筛选", "过滤", "找出"]
    FIND_KEYWORDS = ["查找", "查询", "搜索", "匹配"]
    IF_KEYWORDS = ["如果", "判断", "条件"]
    CONCAT_KEYWORDS = ["合并", "连接", "拼接"]

    @classmethod
    def parse(cls, instruction: str) -> str:
        """
        解析中文指令，返回公式字符串或特殊指令
        :param instruction: 中文指令
        :return: 公式字符串（以 = 开头）、特殊指令（如 "FILTER:>:100"、"VLOOKUP"）或 None
        """
        if not instruction or not instruction.strip():
            return None

        instruction = instruction.strip()

        # 判断是否包含"如果"类的条件逻辑
        if any(kw in instruction for kw in cls.IF_KEYWORDS):
            result = cls._parse_if(instruction)
            if result:
                return result

        # 判断是否包含筛选
        if any(kw in instruction for kw in cls.FILTER_KEYWORDS):
            return cls._parse_filter(instruction)

        # 判断是否包含查找
        if any(kw in instruction for kw in cls.FIND_KEYWORDS):
            return cls._parse_lookup(instruction)

        # 判断是否包含合并/拼接
        if any(kw in instruction for kw in cls.CONCAT_KEYWORDS):
            return cls._parse_concat(instruction)

        # 统计函数
        if any(kw in instruction for kw in cls.SUM_KEYWORDS):
            range_str = cls._extract_range(instruction)
            return f"=SUM({range_str})" if range_str else "=SUM(A:A)"

        if any(kw in instruction for kw in cls.AVG_KEYWORDS):
            range_str = cls._extract_range(instruction)
            return f"=AVERAGE({range_str})" if range_str else "=AVERAGE(A:A)"

        if any(kw in instruction for kw in cls.MAX_KEYWORDS):
            range_str = cls._extract_range(instruction)
            return f"=MAX({range_str})" if range_str else "=MAX(A:A)"

        if any(kw in instruction for kw in cls.MIN_KEYWORDS):
            range_str = cls._extract_range(instruction)
            return f"=MIN({range_str})" if range_str else "=MIN(A:A)"

        if any(kw in instruction for kw in cls.COUNT_KEYWORDS):
            range_str = cls._extract_range(instruction)
            return f"=COUNT({range_str})" if range_str else "=COUNT(A:A)"

        return None

    # ---------- 范围提取 ----------
    @staticmethod
    def _extract_range(instruction: str) -> str:
        """
        从指令中提取单元格范围
        支持格式：
            "A1到A10" -> "A1:A10"
            "A1至A10" -> "A1:A10"
            "B列"     -> "B:B"
            "第2行"   -> "A2:Z2"
            "A1:A10"  -> "A1:A10" (已是标准格式)
        """
        # 已是标准格式 A1:A10
        std_match = re.search(r"([A-Za-z]+\d+)\s*:\s*([A-Za-z]+\d+)", instruction)
        if std_match:
            return f"{std_match.group(1).upper()}:{std_match.group(2).upper()}"

        # "A1到A10" / "A1至A10" / "A1-A10"
        range_match = re.search(
            r"([A-Za-z]+\d+)\s*(?:到|至|-|~)\s*([A-Za-z]+\d+)",
            instruction
        )
        if range_match:
            return f"{range_match.group(1).upper()}:{range_match.group(2).upper()}"

        # 多列格式："A到C列" -> "A:C"
        col_range_match = re.search(
            r"([A-Za-z]+)\s*(?:到|至|-)\s*([A-Za-z]+)\s*列",
            instruction
        )
        if col_range_match:
            return f"{col_range_match.group(1).upper()}:{col_range_match.group(2).upper()}"

        # 单列："B列" -> "B:B"
        col_match = re.search(r"([A-Za-z]+)\s*列", instruction)
        if col_match:
            col = col_match.group(1).upper()
            return f"{col}:{col}"

        # 单行："第2行" -> "A2:Z2"
        row_match = re.search(r"第\s*(\d+)\s*行", instruction)
        if row_match:
            row = int(row_match.group(1))
            return f"A{row}:Z{row}"

        # 单个单元格引用
        single_match = re.search(r"\b([A-Za-z]+\d+)\b", instruction)
        if single_match:
            return single_match.group(1).upper()

        return ""

    # ---------- 条件判断 ----------
    @classmethod
    def _parse_if(cls, instruction: str) -> str:
        """解析 IF 类指令，如"如果A1大于10就显示'高'" """
        # 提取条件
        cond_match = re.search(
            r"([A-Za-z]+\d+)\s*(大于等于|大于|小于等于|小于|等于|不等于)\s*(\d+)",
            instruction
        )
        if not cond_match:
            return None

        cell = cond_match.group(1).upper()
        op_text = cond_match.group(2)
        value = cond_match.group(3)

        op_map = {
            "大于等于": ">=",
            "大于": ">",
            "小于等于": "<=",
            "小于": "<",
            "等于": "=",
            "不等于": "<>",
        }
        op = op_map.get(op_text, "=")

        # 提取真值和假值
        true_val = cls._extract_value(
            instruction, ["显示", "则", "就", "返回"], position="after"
        )
        false_val = cls._extract_value(
            instruction, ["否则", "不然"], position="after"
        )

        true_val = true_val or '"是"'
        false_val = false_val or '"否"'

        return f'=IF({cell}{op}{value},{true_val},{false_val})'

    @staticmethod
    def _extract_value(instruction: str, keywords: list, position: str = "after") -> str:
        """
        从指令中提取引号内的值或关键字后的文本。

        本次修复：
          按 position 参数定位关键词，返回**该关键词之后**的第一个引号内容。
          而不是盲目返回第一个引号内容——避免 IF 公式中真假值提取错误。

        逻辑：
          1. 找出 keywords 中在 instruction 里**最靠前**出现的关键词
          2. 从该关键词之后搜索引号内容
          3. 若无引号，取关键词到下一个停止符之间的文本（去掉前缀词）

        :param instruction: 指令文本
        :param keywords: 关键词列表，如 ["显示", "则", "就", "返回"]
        :param position: "after"（默认）
        :return: 带引号的值字符串（如 '"高"'），提取失败返回 ""
        """
        if not instruction:
            return ""

        if position == "after":
            # 找出最靠前的关键词及其位置
            best_pos = -1
            best_len = 0
            for kw in keywords:
                idx = instruction.find(kw)
                if idx < 0:
                    continue
                if best_pos < 0 or idx < best_pos:
                    best_pos = idx
                    best_len = len(kw)

            if best_pos >= 0:
                after_text = instruction[best_pos + best_len:]

                # 优先：关键词之后第一个引号内容
                m = re.search(r"['\"]([^'\"]+)['\"]", after_text)
                if m:
                    return f'"{m.group(1)}"'

                # 无引号：取关键词到下一个停止符之间的文本
                end = len(after_text)
                for stop in ["否则", "不然", "，", "。", ",", "."]:
                    si = after_text.find(stop)
                    if 0 <= si < end:
                        end = si
                text = after_text[:end].strip()

                # 去掉常见的前缀动词 / 助词
                for prefix in ["显示", "返回", "则", "就", "是", "为"]:
                    if text.startswith(prefix):
                        text = text[len(prefix):].strip()

                if text:
                    return f'"{text}"'

        # 兜底：返回第一个引号内容。
        #
        # 优化规划 §2.5：这里原先**无条件**执行，导致"给了关键词却一个都没找到"
        # 的情况也退化成"取全文第一个引号内容"。典型后果是 IF 指令的真假值同值：
        #     如果A1大于10就显示'高'
        #   → false_val 找不到「否则」，于是兜底又把 '高' 取回来，
        #     生成 =IF(A1>10,"高","高")。
        # 现在只有在**没有指定关键词**时才使用该兜底（把"随便取第一个引号内容"
        # 当作有意的语义）；指定了关键词却没命中，说明该部分不存在，返回空串，
        # 由上层的 `false_val or '"否"'` 提供默认值。
        if keywords:
            return ""
        quotes = re.findall(r"['\"]([^'\"]+)['\"]", instruction)
        if quotes:
            return f'"{quotes[0]}"'
        return ""

    # ---------- 筛选解析 ----------
    @staticmethod
    def _parse_filter(instruction: str) -> str:
        """
        解析筛选指令，返回 FILTER:操作符:值 格式
        示例："筛选大于100的行" -> "FILTER:>:100"
              "过滤等于北京"   -> "FILTER:=:北京"
        """
        # 数值比较
        op_match = re.search(
            r"(大于等于|大于|小于等于|小于|等于|不等于)\s*(\d+(?:\.\d+)?)",
            instruction
        )
        if op_match:
            op_text = op_match.group(1)
            value = op_match.group(2)
            op_map = {
                "大于等于": ">=",
                "大于": ">",
                "小于等于": "<=",
                "小于": "<",
                "等于": "=",
                "不等于": "<>",
            }
            op = op_map.get(op_text, "=")
            return f"FILTER:{op}:{value}"

        # 字符串比较
        str_match = re.search(
            r"(包含|等于|是)\s*['\"]?([^'\"]+?)['\"]?(?:\s|$|的|行)",
            instruction
        )
        if str_match:
            op_text = str_match.group(1)
            value = str_match.group(2).strip()
            op_map = {
                "包含": "contains",
                "等于": "=",
                "是": "=",
            }
            op = op_map.get(op_text, "=")
            return f"FILTER:{op}:{value}"

        # 无操作符，返回空筛选指令
        return "FILTER:"

    # ---------- 查找解析 ----------
    @staticmethod
    def _parse_lookup(instruction: str) -> str:
        """解析查找指令，返回 VLOOKUP 提示"""
        return "VLOOKUP"

    # ---------- 拼接解析 ----------
    @staticmethod
    def _parse_concat(instruction: str) -> str:
        """解析拼接指令，如"合并A1和B1" """
        cells = re.findall(r"([A-Za-z]+\d+)", instruction)
        if len(cells) >= 2:
            args = ",".join(c.upper() for c in cells)
            return f"=CONCATENATE({args})"
        return None

    # ---------- 辅助方法 ----------
    @staticmethod
    def get_supported_examples() -> list:
        """返回支持的自然语言指令示例"""
        return [
            ("求和A1到A10", "=SUM(A1:A10)"),
            ("平均值B列", "=AVERAGE(B:B)"),
            ("最大值A1到A5", "=MAX(A1:A5)"),
            ("最小值C列", "=MIN(C:C)"),
            ("计数D列", "=COUNT(D:D)"),
            ("筛选大于100的行", "FILTER:>:100"),
            ("筛选小于50的行", "FILTER:<:50"),
            ("如果A1大于10就显示'高'", "=IF(A1>10,\"高\",\"否\")"),
            ("合并A1和B1", "=CONCATENATE(A1,B1)"),
            ("查找A1在B到C列", "VLOOKUP"),
        ]


def parse_nl(instruction: str) -> str:
    """模块级便捷函数"""
    return NLFormulaParser.parse(instruction)