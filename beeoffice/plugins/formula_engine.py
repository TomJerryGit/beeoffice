# beeoffice/plugins/formula_engine.py
"""
蜜算公式引擎 - 支持常见 Excel 公式

支持函数：
    统计类：SUM, AVERAGE, COUNT, COUNTA, COUNTIF, MAX, MIN
    条件类：IF, AND, OR
    查找类：VLOOKUP
    文本类：CONCATENATE, LEFT, RIGHT, LEN, UPPER, LOWER
    数学类：ROUND, ABS, INT, MOD
    日期类：TODAY, NOW

用法：
    from beeoffice.plugins.formula_engine import FormulaEngine
    engine = FormulaEngine(lambda row, col: cell_value)
    result = engine.evaluate("=SUM(A1:A10)", current_row, current_col)

本次更新：
  - evaluate("=") 返回空字符串（不再抛异常）
  - _flatten_args_to_values 对"有参数但全部无法转数字"抛 ValueError
"""
import re
import math
import logging
from datetime import datetime
from typing import Callable, Any, List, Union


class FormulaEngine:
    """公式引擎：解析并计算 Excel 风格公式"""

    def __init__(self, data_provider: Callable[[int, int], Any]):
        """
        :param data_provider: 回调函数，参数为 (row, col)，返回单元格的值
        """
        self.data_provider = data_provider

    # ---------- 主入口 ----------
    def evaluate(self, expr: str, current_row: int = 0, current_col: int = 0) -> Any:
        """
        计算表达式，返回结果
        :param expr: 公式字符串（以 = 开头）
        :param current_row: 当前单元格行号（用于相对引用，暂未使用）
        :param current_col: 当前单元格列号
        """
        if not isinstance(expr, str):
            return expr
        if not expr.startswith("="):
            return expr

        expr = expr[1:].strip()

        # 空公式：直接返回空字符串，不抛异常
        if not expr:
            return ""

        # 去除末尾分号
        if expr.endswith(";"):
            expr = expr[:-1].strip()

        # 统一中文括号和逗号
        expr = expr.replace("（", "(").replace("）", ")")
        expr = expr.replace("，", ",")

        upper_expr = expr.upper()

        try:
            # ---------- 统计函数 ----------
            if upper_expr.startswith("SUM("):
                return self._eval_sum(expr)
            if upper_expr.startswith("AVERAGE("):
                return self._eval_average(expr)
            if upper_expr.startswith("COUNTIF("):
                return self._eval_countif(expr)
            if upper_expr.startswith("COUNTA("):
                return self._eval_counta(expr)
            if upper_expr.startswith("COUNT("):
                return self._eval_count(expr)
            if upper_expr.startswith("MAX("):
                return self._eval_max(expr)
            if upper_expr.startswith("MIN("):
                return self._eval_min(expr)

            # ---------- 条件函数 ----------
            if upper_expr.startswith("IF("):
                return self._eval_if(expr, current_row, current_col)
            if upper_expr.startswith("AND("):
                return self._eval_and(expr, current_row, current_col)
            if upper_expr.startswith("OR("):
                return self._eval_or(expr, current_row, current_col)

            # ---------- 查找函数 ----------
            if upper_expr.startswith("VLOOKUP("):
                return self._eval_vlookup(expr, current_row, current_col)

            # ---------- 文本函数 ----------
            if upper_expr.startswith("CONCATENATE("):
                return self._eval_concatenate(expr, current_row, current_col)
            if upper_expr.startswith("LEFT("):
                return self._eval_left(expr, current_row, current_col)
            if upper_expr.startswith("RIGHT("):
                return self._eval_right(expr, current_row, current_col)
            if upper_expr.startswith("LEN("):
                return self._eval_len(expr, current_row, current_col)
            if upper_expr.startswith("UPPER("):
                return self._eval_upper(expr, current_row, current_col)
            if upper_expr.startswith("LOWER("):
                return self._eval_lower(expr, current_row, current_col)

            # ---------- 数学函数 ----------
            if upper_expr.startswith("ROUND("):
                return self._eval_round(expr, current_row, current_col)
            if upper_expr.startswith("ABS("):
                return self._eval_abs(expr, current_row, current_col)
            if upper_expr.startswith("INT("):
                return self._eval_int(expr, current_row, current_col)
            if upper_expr.startswith("MOD("):
                return self._eval_mod(expr, current_row, current_col)

            # ---------- 日期函数 ----------
            if upper_expr.startswith("TODAY("):
                return datetime.now().strftime("%Y-%m-%d")
            if upper_expr.startswith("NOW("):
                return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

            # ---------- 纯算术表达式 ----------
            return self._eval_math(expr, current_row, current_col)

        except Exception as e:
            logging.error(f"公式计算失败 [{expr}]: {e}")
            raise ValueError(f"公式错误: {e}")

    # ---------- 统计函数 ----------
    def _eval_sum(self, expr: str) -> Any:
        match = re.match(r"SUM\((.+)\)", expr, re.IGNORECASE)
        if not match:
            raise ValueError("SUM 参数错误")
        args = self._parse_args(match.group(1))
        values = self._flatten_args_to_values(args, need_number=True)
        return sum(values)

    def _eval_average(self, expr: str) -> Any:
        match = re.match(r"AVERAGE\((.+)\)", expr, re.IGNORECASE)
        if not match:
            raise ValueError("AVERAGE 参数错误")
        args = self._parse_args(match.group(1))
        values = self._flatten_args_to_values(args, need_number=True)
        if not values:
            return 0
        return sum(values) / len(values)

    def _eval_count(self, expr: str) -> int:
        match = re.match(r"COUNT\((.+)\)", expr, re.IGNORECASE)
        if not match:
            raise ValueError("COUNT 参数错误")
        args = self._parse_args(match.group(1))
        values = self._flatten_args_to_values(args, need_number=False)
        return sum(1 for v in values if self._is_number(v))

    def _eval_counta(self, expr: str) -> int:
        match = re.match(r"COUNTA\((.+)\)", expr, re.IGNORECASE)
        if not match:
            raise ValueError("COUNTA 参数错误")
        args = self._parse_args(match.group(1))
        values = self._flatten_args_to_values(args, need_number=False)
        return sum(1 for v in values if v not in (None, ""))

    def _eval_countif(self, expr: str) -> int:
        match = re.match(r"COUNTIF\((.+)\)", expr, re.IGNORECASE)
        if not match:
            raise ValueError("COUNTIF 参数错误")
        parts = self._split_top_level(match.group(1), ",")
        if len(parts) != 2:
            raise ValueError("COUNTIF 需要两个参数")
        range_str, criteria = parts
        values = self._get_range_values(range_str)
        return sum(1 for v in values if self._match_criteria(v, criteria))

    def _eval_max(self, expr: str) -> Any:
        match = re.match(r"MAX\((.+)\)", expr, re.IGNORECASE)
        if not match:
            raise ValueError("MAX 参数错误")
        args = self._parse_args(match.group(1))
        values = self._flatten_args_to_values(args, need_number=True)
        if not values:
            return 0
        return max(values)

    def _eval_min(self, expr: str) -> Any:
        match = re.match(r"MIN\((.+)\)", expr, re.IGNORECASE)
        if not match:
            raise ValueError("MIN 参数错误")
        args = self._parse_args(match.group(1))
        values = self._flatten_args_to_values(args, need_number=True)
        if not values:
            return 0
        return min(values)

    # ---------- 条件函数 ----------
    def _eval_if(self, expr: str, row: int, col: int) -> Any:
        # 提取 IF 的参数
        inner = expr[3:-1]
        parts = self._split_top_level(inner, ",")
        if len(parts) not in (2, 3):
            raise ValueError("IF 需要 2 或 3 个参数")
        condition = self._eval_condition(parts[0], row, col)
        if condition:
            return self._parse_value(parts[1], row, col)
        if len(parts) == 3:
            return self._parse_value(parts[2], row, col)
        return False

    def _eval_and(self, expr: str, row: int, col: int) -> bool:
        inner = expr[4:-1]
        parts = self._split_top_level(inner, ",")
        for p in parts:
            if not self._eval_condition(p, row, col):
                return False
        return True

    def _eval_or(self, expr: str, row: int, col: int) -> bool:
        inner = expr[3:-1]
        parts = self._split_top_level(inner, ",")
        for p in parts:
            if self._eval_condition(p, row, col):
                return True
        return False

    # ---------- 查找函数 ----------
    def _eval_vlookup(self, expr: str, row: int, col: int) -> Any:
        inner = expr[8:-1]
        parts = self._split_top_level(inner, ",")
        if len(parts) < 3:
            raise ValueError("VLOOKUP 需要至少 3 个参数")
        lookup_val = self._parse_value(parts[0], row, col)
        range_str = parts[1].strip()
        col_idx = int(self._parse_value(parts[2], row, col))

        # 解析表范围
        table = self._get_table_data(range_str)
        if not table:
            raise ValueError("VLOOKUP 表范围无效")

        # 查找
        for r in table:
            if r and str(r[0]) == str(lookup_val):
                if 0 < col_idx <= len(r):
                    return r[col_idx - 1]
                raise ValueError("VLOOKUP 列索引越界")
        raise ValueError("VLOOKUP 未找到匹配值")

    def _get_table_data(self, range_str: str) -> List[List[Any]]:
        """获取表格数据，返回行列表"""
        range_str = range_str.strip()
        match = re.match(r"([A-Za-z]+)(\d+):([A-Za-z]+)(\d+)", range_str)
        if not match:
            return []
        col_start_str, row_start_str, col_end_str, row_end_str = match.groups()
        col_start = self._col_to_index(col_start_str)
        col_end = self._col_to_index(col_end_str)
        row_start = int(row_start_str) - 1
        row_end = int(row_end_str) - 1

        data = []
        for r in range(row_start, row_end + 1):
            row_data = []
            for c in range(col_start, col_end + 1):
                row_data.append(self.data_provider(r, c))
            data.append(row_data)
        return data

    # ---------- 文本函数 ----------
    def _eval_concatenate(self, expr: str, row: int, col: int) -> str:
        inner = expr[12:-1]
        parts = self._split_top_level(inner, ",")
        return "".join(str(self._parse_value(p, row, col) or "") for p in parts)

    def _eval_left(self, expr: str, row: int, col: int) -> str:
        inner = expr[5:-1]
        parts = self._split_top_level(inner, ",")
        text = str(self._parse_value(parts[0], row, col) or "")
        if len(parts) == 1:
            return text[0] if text else ""
        n = int(self._parse_value(parts[1], row, col))
        return text[:n]

    def _eval_right(self, expr: str, row: int, col: int) -> str:
        inner = expr[6:-1]
        parts = self._split_top_level(inner, ",")
        text = str(self._parse_value(parts[0], row, col) or "")
        if len(parts) == 1:
            return text[-1] if text else ""
        n = int(self._parse_value(parts[1], row, col))
        return text[-n:] if n > 0 else ""

    def _eval_len(self, expr: str, row: int, col: int) -> int:
        inner = expr[4:-1]
        text = str(self._parse_value(inner, row, col) or "")
        return len(text)

    def _eval_upper(self, expr: str, row: int, col: int) -> str:
        inner = expr[6:-1]
        text = str(self._parse_value(inner, row, col) or "")
        return text.upper()

    def _eval_lower(self, expr: str, row: int, col: int) -> str:
        inner = expr[6:-1]
        text = str(self._parse_value(inner, row, col) or "")
        return text.lower()

    # ---------- 数学函数 ----------
    def _eval_round(self, expr: str, row: int, col: int) -> Any:
        inner = expr[6:-1]
        parts = self._split_top_level(inner, ",")
        if len(parts) != 2:
            raise ValueError("ROUND 需要两个参数")
        num = self._parse_value(parts[0], row, col)
        digits = int(self._parse_value(parts[1], row, col))
        if isinstance(num, str):
            num = float(num)
        return round(num, digits)

    def _eval_abs(self, expr: str, row: int, col: int) -> Any:
        inner = expr[4:-1]
        value = self._parse_value(inner, row, col)
        if isinstance(value, str):
            value = float(value)
        return abs(value)

    def _eval_int(self, expr: str, row: int, col: int) -> int:
        inner = expr[4:-1]
        value = self._parse_value(inner, row, col)
        if isinstance(value, str):
            value = float(value)
        return int(value)

    def _eval_mod(self, expr: str, row: int, col: int) -> Any:
        inner = expr[4:-1]
        parts = self._split_top_level(inner, ",")
        if len(parts) != 2:
            raise ValueError("MOD 需要两个参数")
        a = self._parse_value(parts[0], row, col)
        b = self._parse_value(parts[1], row, col)
        if isinstance(a, str):
            a = float(a)
        if isinstance(b, str):
            b = float(b)
        if b == 0:
            raise ValueError("MOD 除数不能为 0")
        return a % b

    # ---------- 算术表达式 ----------
    def _eval_math(self, expr: str, row: int, col: int) -> Any:
        """解析简单算术表达式，替换单元格引用为具体值"""
        def replace_cell(match):
            cell_ref = match.group(0)
            value = self._get_cell_value_by_ref(cell_ref)
            if value is None or value == "":
                return "0"
            try:
                return str(float(value))
            except (TypeError, ValueError):
                return "0"

        # 替换单元格引用
        expr_with_values = re.sub(r"\b[A-Za-z]+\d+\b", replace_cell, expr)

        # 安全求值
        allowed_names = {
            "abs": abs,
            "round": round,
            "int": int,
            "float": float,
            "min": min,
            "max": max,
        }
        try:
            result = eval(expr_with_values, {"__builtins__": {}}, allowed_names)
            return result
        except Exception as e:
            raise ValueError(f"算术表达式错误: {e}")

    # ---------- 条件判断 ----------
    def _eval_condition(self, expr: str, row: int, col: int) -> bool:
        """计算布尔条件"""
        expr = expr.strip()

        # 处理比较运算符
        compare_match = re.match(r"(.+?)(>=|<=|<>|!=|==|>|<)(.+)", expr)
        if compare_match:
            left_raw = compare_match.group(1)
            op = compare_match.group(2)
            right_raw = compare_match.group(3)

            left = self._parse_value(left_raw, row, col)
            right = self._parse_value(right_raw, row, col)

            # 尝试数值比较
            try:
                left_num = float(left) if not isinstance(left, (int, float)) else left
                right_num = float(right) if not isinstance(right, (int, float)) else right
                left_cmp, right_cmp = left_num, right_num
            except (TypeError, ValueError):
                left_cmp, right_cmp = str(left), str(right)

            if op == ">=":
                return left_cmp >= right_cmp
            if op == "<=":
                return left_cmp <= right_cmp
            if op in ("==", "="):
                return left_cmp == right_cmp
            if op in ("!=", "<>"):
                return left_cmp != right_cmp
            if op == ">":
                return left_cmp > right_cmp
            if op == "<":
                return left_cmp < right_cmp

        # 处理布尔常量和单元格引用
        upper = expr.upper()
        if upper in ("TRUE", "真"):
            return True
        if upper in ("FALSE", "假"):
            return False

        value = self._parse_value(expr, row, col)
        if value in (None, ""):
            return False
        return bool(value)

    # ---------- 值解析 ----------
    def _parse_value(self, raw_value: Any, row: int, col: int) -> Any:
        """解析参数值：单元格引用、字符串常量、数值或嵌套函数"""
        if not isinstance(raw_value, str):
            return raw_value

        raw_value = raw_value.strip()
        if not raw_value:
            return None

        # 嵌套函数（如 SUM(A1:A2)、IF(...)）
        upper = raw_value.upper()
        for func_prefix in ("SUM(", "AVERAGE(", "COUNT(", "MAX(", "MIN(", "IF(",
                            "AND(", "OR(", "ROUND(", "ABS(", "CONCATENATE("):
            if upper.startswith(func_prefix):
                return self.evaluate("=" + raw_value, row, col)

        # 单元格引用（如 A1、$B$2）
        clean_ref = raw_value.replace("$", "")
        if re.match(r"^[A-Za-z]+\d+$", clean_ref):
            return self._get_cell_value_by_ref(clean_ref)

        # 范围引用（如 A1:A10）在 SUM 等函数中已被处理，这里作为字符串返回
        if re.match(r"^[A-Za-z]+\d+:[A-Za-z]+\d+$", clean_ref):
            return raw_value

        # 字符串常量
        if (raw_value.startswith('"') and raw_value.endswith('"')) or \
           (raw_value.startswith("'") and raw_value.endswith("'")):
            return raw_value[1:-1]

        # 数值
        try:
            if "." in raw_value or "e" in raw_value.lower():
                return float(raw_value)
            return int(raw_value)
        except ValueError:
            return raw_value

    # ---------- 单元格与范围 ----------
    def _get_cell_value_by_ref(self, cell_ref: str) -> Any:
        """根据单元格引用（如 A1）获取值"""
        match = re.match(r"^([A-Za-z]+)(\d+)$", cell_ref)
        if not match:
            return None
        col_str, row_str = match.groups()
        col_idx = self._col_to_index(col_str)
        row_idx = int(row_str) - 1
        return self.data_provider(row_idx, col_idx)

    def _get_range_values(self, range_str: str) -> List[Any]:
        """获取范围内的所有值"""
        range_str = range_str.strip()
        match = re.match(r"([A-Za-z]+)(\d+):([A-Za-z]+)(\d+)", range_str)
        if match:
            col_start_str, row_start_str, col_end_str, row_end_str = match.groups()
            col_start = self._col_to_index(col_start_str)
            col_end = self._col_to_index(col_end_str)
            row_start = int(row_start_str) - 1
            row_end = int(row_end_str) - 1

            values = []
            for r in range(row_start, row_end + 1):
                for c in range(col_start, col_end + 1):
                    values.append(self.data_provider(r, c))
            return values

        # 单个单元格
        if re.match(r"^[A-Za-z]+\d+$", range_str):
            val = self._get_cell_value_by_ref(range_str)
            return [val] if val not in (None, "") else []
        return []

    @staticmethod
    def _col_to_index(col_str: str) -> int:
        """将列字母（A、B、AA）转为 0 基索引"""
        col_str = col_str.upper()
        idx = 0
        for ch in col_str:
            idx = idx * 26 + (ord(ch) - ord("A") + 1)
        return idx - 1

    # ---------- 参数处理 ----------
    def _flatten_args_to_values(self, args: List[str], need_number: bool = False) -> List[Any]:
        """将参数列表展开为值列表"""
        values = []
        for arg in args:
            arg = arg.strip()
            if not arg:
                continue

            # 范围引用
            if ":" in arg and re.match(r"^[A-Za-z]+\d+:[A-Za-z]+\d+$", arg):
                values.extend(self._get_range_values(arg))
            # 单元格引用
            elif re.match(r"^[A-Za-z]+\d+$", arg.replace("$", "")):
                v = self._get_cell_value_by_ref(arg.replace("$", ""))
                values.append(v)
            # 字符串常量
            elif (arg.startswith('"') and arg.endswith('"')) or \
                 (arg.startswith("'") and arg.endswith("'")):
                values.append(arg[1:-1])
            # 嵌套函数
            elif arg.upper().endswith(")") and "(" in arg:
                v = self.evaluate("=" + arg)
                values.append(v)
            # 数值
            else:
                try:
                    v = float(arg) if "." in arg else int(arg)
                    values.append(v)
                except ValueError:
                    # 既不是数字也不是引用/函数 → 记录下来，后面决定是否抛异常
                    values.append(arg)

        # 过滤空值
        values = [v for v in values if v not in (None, "", " ")]

        if need_number:
            numeric_values = []
            for v in values:
                try:
                    numeric_values.append(float(v))
                except (TypeError, ValueError):
                    pass
            # 有参数但全部无法转数字 → 抛异常
            if values and not numeric_values:
                raise ValueError(f"参数必须是数字，但得到: {values}")
            return numeric_values
        return values

    def _parse_args(self, arg_str: str) -> List[str]:
        """按顶层逗号拆分参数"""
        return self._split_top_level(arg_str, ",")

    @staticmethod
    def _split_top_level(s: str, delimiter: str) -> List[str]:
        """按顶层分隔符拆分字符串（忽略括号内的分隔符）"""
        parts = []
        depth = 0
        current = []
        in_quote = False
        quote_char = ""

        for ch in s:
            if in_quote:
                current.append(ch)
                if ch == quote_char:
                    in_quote = False
                continue

            if ch in ('"', "'"):
                in_quote = True
                quote_char = ch
                current.append(ch)
            elif ch in "([":
                depth += 1
                current.append(ch)
            elif ch in ")]":
                depth -= 1
                current.append(ch)
            elif ch == delimiter and depth == 0:
                parts.append("".join(current).strip())
                current = []
            else:
                current.append(ch)

        if current:
            parts.append("".join(current).strip())
        return parts

    # ---------- 条件匹配 ----------
    @staticmethod
    def _match_criteria(value: Any, criteria: str) -> bool:
        """COUNTIF 等函数的条件匹配"""
        criteria = criteria.strip().strip('"').strip("'")

        # 处理 >= <= > < 等
        match = re.match(r"^(>=|<=|<>|!=|>|<|=)(.+)$", criteria)
        if match:
            op = match.group(1)
            target = match.group(2).strip()
            try:
                v_num = float(value) if not isinstance(value, (int, float)) else value
                t_num = float(target)
                if op == ">=":
                    return v_num >= t_num
                if op == "<=":
                    return v_num <= t_num
                if op == ">":
                    return v_num > t_num
                if op == "<":
                    return v_num < t_num
                if op in ("=", "=="):
                    return abs(v_num - t_num) < 1e-9
                if op in ("!=", "<>"):
                    return abs(v_num - t_num) >= 1e-9
            except (TypeError, ValueError):
                pass

        # 普通相等
        try:
            return float(value) == float(criteria)
        except (TypeError, ValueError):
            return str(value) == criteria

    # ---------- 数字判断 ----------
    @staticmethod
    def _is_number(value: Any) -> bool:
        """判断值是否为数字（含数字字符串）"""
        if isinstance(value, (int, float)):
            return True
        if isinstance(value, str):
            try:
                float(value)
                return True
            except ValueError:
                return False
        return False