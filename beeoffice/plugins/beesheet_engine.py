# beeoffice/plugins/beesheet_engine.py
"""
蜜算公式引擎：支持 80+ 常用 Excel 函数

v5.0.1 修复：
  - P0-5：_if / _and / _or / _not / _ifs 改用 AST 白名单 _safe_eval，
          修复原实现使用裸 eval() 导致公式可执行任意 Python 代码的安全漏洞
  - P0-11：_sumifs / _avgifs 条件范围行索引修正
          原实现 `sr1 + (r - sr1)` 恒等于 r，条件列永远按求和范围的起始行取值；
          改为按条件范围自己的起始行 + 相对偏移
          range 边界从 `range(1, len(p), 2)` 改为 `range(1, len(p) - 1, 2)` 防越界

v5.0.5 修复（本次）：
  - 新增 _eval_arg 方法：单参数求值（IF 分支 / CHOOSE 结果 /
    IFERROR 兜底值 / IFNA 兜底值 / IFS 分支结果）
    相比 _av：额外支持嵌套函数调用（SUM、IF、VLOOKUP 等）
              额外支持算术表达式（A1+B1、A1*2 等）
              保留字符串常量去引号语义（"正" → 正）
    相比 _eval：字符串常量不保留引号
  - _if / _iferror / _ifna / _ifs / _choose 的"结果/兜底值"分支
    全部改用 _eval_arg，修复 IF 分支不支持嵌套函数调用的缺陷
    例如 =IF(A1>0, SUM(B1:B5), 0) 之前会返回字符串 "SUM(B1:B5)"，
    现在正确返回求和结果
"""
import re
import math
import numpy as np
import pandas as pd
from datetime import datetime, timedelta


class FormulaEngine:
    """公式引擎：解析并计算 Excel 风格公式"""

    _error_trace = {}

    @classmethod
    def evaluate(cls, formula, model):
        if not formula.startswith('='):
            return formula
        try:
            result = cls._eval(formula[1:].strip(), model)
            cls._error_trace.pop(formula, None)
            return result
        except Exception as e:
            cls._error_trace[formula] = str(e)
            return f"#ERROR: {str(e)[:80]}"

    @classmethod
    def _eval(cls, expr, model):
        expr_stripped = expr.strip()
        if hasattr(model, '_named_ranges_ref'):
            upper = expr_stripped.upper()
            for name, ref in model._named_ranges_ref.items():
                if upper == name.upper():
                    expr_stripped = ref.upper()
                    break
        if '!' in expr_stripped:
            return cls._eval_sheet_ref(expr_stripped, model)
        # v5.1 B1fix：\(.+\) → \((.*)\)，允许空参数（如 =SUM() / =XMATCH()）
        # 空参数会走 _func 分支，由具体函数决定返回 #ERROR 还是默认值
        m = re.match(r'^(\w+)\((.*)\)$', expr_stripped, re.IGNORECASE)
        if m:
            return cls._func(m.group(1).upper(),
                             cls._substitute_named(m.group(2), model), model)
        ref = cls._ref(expr_stripped.upper())
        if ref:
            return model.get_value(ref[0], ref[1])
        try:
            return float(expr_stripped) if '.' in expr_stripped else int(expr_stripped)
        except (ValueError, TypeError):
            pass

        # 复合表达式（=SUM(A1:A3)*2、=ROUND(A1,2)+1 等）：
        # 先把最内层函数调用就地求值，剩下的纯算术再交给 _safe_eval
        expanded = cls._expand_calls(expr_stripped, model)
        if expanded != expr_stripped:
            try:
                return cls._safe_eval(expanded, model)
            except ZeroDivisionError:
                raise
            except Exception:
                pass

        # v5.0.5：算术表达式（A1+A2、A1*2、1/A1 等）
        try:
            return cls._safe_eval(expr_stripped, model)
        except ZeroDivisionError:
            raise
        except Exception:
            pass

        return expr_stripped

    @classmethod
    def _eval_sheet_ref(cls, expr, model):
        if not hasattr(model, '_get_sheet_data'):
            raise ValueError("跨表引用不可用")

        # 查找类函数依赖"区域形状"，不能把 S1!A1:B3 压平成 "1,一,2,..."：
        # 压平会把一个区域拆成多个参数，导致列号参数拿到单元格内容
        # （历史上表现为 `int('一')` 直接抛错）。
        # 这类调用保留原始参数，交给 _sheet_range 按区域解析。
        look = re.match(
            r'^\s*(VLOOKUP|HLOOKUP)\s*\((.*)\)\s*$',
            expr.strip(),
            re.IGNORECASE | re.DOTALL,
        )
        if look and '!' in look.group(2):
            return cls._func(look.group(1).upper(), look.group(2), model)

        sheet_pattern = r'([^!(),:+\-*/]+)!(\$?[A-Z]+\$?\d+(?::\$?[A-Z]+\$?\d+)?)'

        def replace_sheet(match):
            sheet_name = match.group(1).strip().strip('"').strip("'")
            ref = match.group(2)
            sheet_df = model._get_sheet_data(sheet_name)
            if sheet_df is None:
                raise ValueError(f"找不到工作表: {sheet_name}")
            if ':' in ref:
                values = cls._extract_sheet_range(sheet_df, ref)
                if not values:
                    return "0"
                return ",".join(str(v) for v in values)
            else:
                v = cls._extract_sheet_cell(sheet_df, ref)
                return str(v) if v is not None else "0"

        new_expr = re.sub(sheet_pattern, replace_sheet, expr)

        # 安全（P0）：这里原来对拼好的字符串直接 eval。
        # 即使把 __builtins__ 置空，`().__class__.__bases__[0].__subclasses__()`
        # 这类对象图遍历仍能逃逸，等于公式可执行任意代码。
        # 现在只走 AST 白名单求值；失败后再尝试函数调用与递归求值。
        try:
            return cls._safe_eval(new_expr, model)
        except ZeroDivisionError:
            raise
        except Exception:
            pass

        m = re.match(r'^(\w+)\((.+)\)$', new_expr, re.IGNORECASE)
        if m:
            return cls._func(m.group(1).upper(), m.group(2), model)

        # 跨表引用已被替换成数值；若仍残留 '!'，递归会无限循环，直接报错
        if '!' in new_expr:
            return "#ERROR: 无法解析跨表引用"
        return cls._eval(new_expr, model)

    @classmethod
    def _extract_sheet_cell(cls, df, ref):
        ref = ref.replace('$', '')
        m = re.match(r'^([A-Z]+)(\d+)$', ref.upper())
        if not m:
            return None
        col_str, row_str = m.groups()
        col_idx = 0
        for ch in col_str:
            col_idx = col_idx * 26 + (ord(ch) - ord('A') + 1)
        col_idx -= 1
        row_idx = int(row_str) - 1
        try:
            if 0 <= row_idx < len(df) and 0 <= col_idx < len(df.columns):
                return df.iloc[row_idx, col_idx]
        except:
            pass
        return None

    @classmethod
    def _extract_sheet_range(cls, df, range_ref):
        range_ref = range_ref.replace('$', '')
        m = re.match(r'^([A-Z]+)(\d+):([A-Z]+)(\d+)$', range_ref.upper())
        if not m:
            return []
        c1s, r1s, c2s, r2s = m.groups()

        def col_idx(s):
            idx = 0
            for ch in s:
                idx = idx * 26 + (ord(ch) - ord('A') + 1)
            return idx - 1

        c1, c2 = col_idx(c1s), col_idx(c2s)
        r1, r2 = int(r1s) - 1, int(r2s) - 1
        values = []
        for r in range(min(r1, r2), max(r1, r2) + 1):
            for c in range(min(c1, c2), max(c1, c2) + 1):
                try:
                    if 0 <= r < len(df) and 0 <= c < len(df.columns):
                        v = df.iloc[r, c]
                        if v is not None and not (isinstance(v, float) and pd.isna(v)):
                            values.append(v)
                except:
                    pass
        return values

    @classmethod
    def _substitute_named(cls, args_str, model):
        if not hasattr(model, '_named_ranges_ref'):
            return args_str
        result = args_str
        for name in sorted(model._named_ranges_ref.keys(), key=len, reverse=True):
            ref = model._named_ranges_ref[name]
            pattern = (r'(?<![A-Za-z0-9_\u4e00-\u9fff])' +
                       re.escape(name) +
                       r'(?![A-Za-z0-9_\u4e00-\u9fff])')
            result = re.sub(pattern, ref.upper(), result, flags=re.IGNORECASE)
        return result

    @classmethod
    def _func(cls, name, args, model):
        funcs = cls._get_all_functions()
        f = funcs.get(name)
        if f:
            return f(args, model)
        math_funcs = {
            'SIN': math.sin, 'COS': math.cos, 'TAN': math.tan, 'EXP': math.exp,
            'LN': math.log, 'LOG10': math.log10, 'PI': lambda a, m: math.pi,
            'RAND': lambda a, m: np.random.random(),
            'RANDBETWEEN': lambda a, m: np.random.randint(
                int(cls._av(a.split(',')[0], m)),
                int(cls._av(a.split(',')[1], m)) + 1
            ),
            'ABS': lambda a, m: abs(float(cls._av(a, m))),
            'SQRT': lambda a, m: float(cls._av(a, m)) ** 0.5,
        }
        if name in math_funcs:
            if name in ('RANDBETWEEN',):
                return math_funcs[name](*[args, model])
            return math_funcs[name](cls._av(args, model))
        return f"#ERROR: 未知函数 {name}"

    @classmethod
    def _get_all_functions(cls):
        return {
            'SUM': cls._sum, 'AVERAGE': cls._avg, 'MAX': cls._max, 'MIN': cls._min,
            'COUNT': cls._cnt, 'COUNTA': cls._cnta, 'COUNTBLANK': cls._cntblank,
            'MEDIAN': cls._median, 'MODE': cls._mode, 'STDEV': cls._stdev, 'VAR': cls._var,
            'LARGE': cls._large, 'SMALL': cls._small, 'RANK': cls._rank,
            'IF': cls._if, 'IFERROR': cls._iferror, 'IFNA': cls._ifna,
            'AND': cls._and, 'OR': cls._or, 'NOT': cls._not, 'IFS': cls._ifs,
            'VLOOKUP': cls._vlookup, 'HLOOKUP': cls._hlookup, 'XLOOKUP': cls._xlookup,
            'INDEX': cls._index, 'MATCH': cls._match, 'CHOOSE': cls._choose,
            'COUNTIF': cls._countif, 'SUMIF': cls._sumif, 'AVERAGEIF': cls._avgif,
            'COUNTIFS': cls._countifs, 'SUMIFS': cls._sumifs, 'AVERAGEIFS': cls._avgifs,
            'ROUND': cls._round, 'ROUNDUP': cls._roundup, 'ROUNDDOWN': cls._rounddown,
            'POWER': cls._power, 'MOD': cls._mod, 'INT': cls._int, 'TRUNC': cls._trunc,
            'CEILING': cls._ceiling, 'FLOOR': cls._floor, 'SUMPRODUCT': cls._sumproduct,
            'LEFT': cls._left, 'RIGHT': cls._right, 'MID': cls._mid, 'LEN': cls._len,
            'TRIM': cls._trim, 'UPPER': cls._upper, 'LOWER': cls._lower, 'PROPER': cls._proper,
            'CONCATENATE': cls._concat, 'TEXTJOIN': cls._textjoin,
            'FIND': cls._find, 'SEARCH': cls._search, 'REPLACE': cls._replace,
            'SUBSTITUTE': cls._substitute,
            'TEXT': cls._text, 'VALUE': cls._value, 'REPT': cls._rept, 'EXACT': cls._exact,
            'TODAY': lambda a, m: datetime.now().strftime('%Y-%m-%d'),
            'NOW': lambda a, m: datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'YEAR': lambda a, m: cls._parse_date(cls._av(a, m)).year if cls._av(a, m) else datetime.now().year,
            'MONTH': lambda a, m: cls._parse_date(cls._av(a, m)).month if cls._av(a, m) else datetime.now().month,
            'DAY': lambda a, m: cls._parse_date(cls._av(a, m)).day if cls._av(a, m) else datetime.now().day,
            'DATE': cls._date, 'DATEDIF': cls._datedif, 'EDATE': cls._edate,
            'EOMONTH': cls._eomonth, 'WEEKDAY': cls._weekday, 'WEEKNUM': cls._weeknum,
            'NETWORKDAYS': cls._networkdays, 'WORKDAY': cls._workday,
            'HOUR': cls._hour, 'MINUTE': cls._minute, 'SECOND': cls._second,
            'PMT': cls._pmt, 'FV': cls._fv, 'PV': cls._pv, 'NPV': cls._npv,
            'IRR': cls._irr, 'RATE': cls._rate, 'NPER': cls._nper,
            'SLN': cls._sln, 'DB': cls._db,
            # ---------- v5.1 B1 新增 ----------
            'XMATCH': cls._xmatch,
            'LET': cls._let,
            'SWITCH': cls._switch,
            'XOR': cls._xor,
            'MAXIFS': cls._maxifs,
            'MINIFS': cls._minifs,
            'TEXTBEFORE': cls._textbefore,
            'TEXTAFTER': cls._textafter,
            'VALUETOTEXT': cls._valuetotext,
            'ISBLANK': cls._isblank,
            'ISNUMBER': cls._isnumber,
            'ISTEXT': cls._istext,
            'ISLOGICAL': cls._islogical,
            'ISERROR': cls._iserror,
        }

    @staticmethod
    def _ref(r):
        m = re.match(r'^([A-Z]+)(\d+)$', r)
        if not m:
            return None
        c = sum((ord(x) - 64) * (26 ** i) for i, x in enumerate(reversed(m.group(1))))
        return int(m.group(2)) - 1, c - 1

    @staticmethod
    def _range(s):
        if ':' not in s:
            return None
        a, b = s.split(':', 1)
        ra, rb = FormulaEngine._ref(a.strip()), FormulaEngine._ref(b.strip())
        return (ra, rb) if ra and rb else None

    @staticmethod
    def _vals(r, model):
        rd = FormulaEngine._range(r)
        if rd:
            (r1, c1), (r2, c2) = rd
            vs = []
            for rr in range(r1, r2 + 1):
                for cc in range(c1, c2 + 1):
                    try:
                        vs.append(float(model.get_value(rr, cc)))
                    except:
                        pass
            return vs

        # 不是区域时退化为「逗号分隔的标量列表」，兼容：
        #   =SUM(1,2,3)              Excel 合法写法
        #   =SUM(Sheet2!A1:A3)       跨表替换后变成 SUM(1,2,3)
        #   =SUM(A1)                 单格（原实现会误返回 0）
        vs = []
        for token in FormulaEngine._args(r):
            token = token.strip()
            if not token:
                continue
            ref = FormulaEngine._ref(token.strip('"').upper())
            if ref:
                try:
                    vs.append(float(model.get_value(ref[0], ref[1])))
                except (TypeError, ValueError):
                    pass
                continue
            try:
                vs.append(float(token.strip('"')))
            except ValueError:
                pass
        return vs

    @staticmethod
    def _args(s):
        args, cur, d, q = [], "", False, 0
        for c in s:
            if c == '"':
                d = not d
                cur += c
            elif c == '(' and not d:
                q += 1
                cur += c
            elif c == ')' and not d:
                q -= 1
                cur += c
            elif c == ',' and not d and q == 0:
                args.append(cur.strip())
                cur = ""
            else:
                cur += c
        if cur.strip():
            args.append(cur.strip())
        return args

    @staticmethod
    def _av(arg, model):
        arg = arg.strip().strip('"')
        ref = FormulaEngine._ref(arg.upper())
        if ref:
            return model.get_value(ref[0], ref[1])
        try:
            return float(arg) if '.' in arg else int(arg)
        except:
            return arg

    # ==================== v5.0.5 新增：单参数求值 ====================
    @classmethod
    def _eval_arg(cls, raw, model):
        """
        求值单个参数（IF 分支 / CHOOSE 结果 / IFERROR 兜底值 等）。

        相比 _av：
          - 额外支持嵌套函数调用（SUM、IF、VLOOKUP 等）
          - 额外支持算术表达式（A1+B1、A1*2 等）
          - 保留字符串常量去引号语义（"正" → 正）

        相比 _eval：
          - 字符串常量不保留引号（_eval 会原样返回 '"正"'）

        :param raw: 原始参数（可能是字符串、数字等）
        :param model: 数据模型
        :return: 求值结果
        """
        if not isinstance(raw, str):
            return raw
        s = raw.strip()
        if not s:
            return ""
        # 字符串常量：去引号
        if len(s) >= 2 and s[0] == s[-1] and s[0] in ('"', "'"):
            return s[1:-1]
        # 其余情况统一走 _eval：
        # 函数调用 / 单元格引用 / 算术表达式 / 数字常量
        return cls._eval(s, model)

    @staticmethod
    def _parse_date(s):
        if not s:
            return datetime.now()
        if isinstance(s, datetime):
            return s
        for fmt in ['%Y-%m-%d', '%Y/%m/%d', '%Y.%m.%d']:
            try:
                return datetime.strptime(str(s).strip('"'), fmt)
            except:
                pass
        return datetime.now()

    @staticmethod
    def _check_cond(val, cond):
        try:
            nv = float(val)
            if cond.startswith('>='):
                return nv >= float(cond[2:])
            if cond.startswith('<='):
                return nv <= float(cond[2:])
            if cond.startswith('<>'):
                return nv != float(cond[2:])
            if cond.startswith('>'):
                return nv > float(cond[1:])
            if cond.startswith('<'):
                return nv < float(cond[1:])
            if cond.startswith('='):
                return nv == float(cond[1:])
            return str(val).strip().lower() == cond.strip().lower()
        except:
            return str(val).strip().lower() == cond.strip().lower()

    @staticmethod
    def _allvals(r, model):
        rd = FormulaEngine._range(r)
        if not rd:
            return []
        (r1, c1), (r2, c2) = rd
        vs = []
        for rr in range(r1, r2 + 1):
            for cc in range(c1, c2 + 1):
                vs.append(model.get_value(rr, cc))
        return vs

    @classmethod
    def _sum(cls, a, m):
        v = cls._vals(a, m)
        return sum(v) if v else 0

    @classmethod
    def _avg(cls, a, m):
        v = cls._vals(a, m)
        return sum(v) / len(v) if v else 0

    @classmethod
    def _max(cls, a, m):
        v = cls._vals(a, m)
        return max(v) if v else 0

    @classmethod
    def _min(cls, a, m):
        v = cls._vals(a, m)
        return min(v) if v else 0

    @classmethod
    def _cnt(cls, a, m):
        return len(cls._vals(a, m))

    @classmethod
    def _cnta(cls, a, m):
        return len([x for x in cls._allvals(a, m)
                    if x is not None and str(x).strip() != ''])

    @classmethod
    def _cntblank(cls, a, m):
        return len([x for x in cls._allvals(a, m)
                    if x is None or str(x).strip() == ''])

    @classmethod
    def _median(cls, a, m):
        v = sorted(cls._vals(a, m))
        n = len(v)
        return (v[n // 2] + v[n // 2 - 1]) / 2 if n % 2 == 0 and n > 0 else v[n // 2] if n > 0 else 0

    @classmethod
    def _mode(cls, a, m):
        from collections import Counter
        v = cls._vals(a, m)
        return Counter(v).most_common(1)[0][0] if v else 0

    @classmethod
    def _stdev(cls, a, m):
        v = cls._vals(a, m)
        return float(np.std(v)) if v else 0

    @classmethod
    def _var(cls, a, m):
        v = cls._vals(a, m)
        return float(np.var(v)) if v else 0

    @classmethod
    def _large(cls, a, m):
        p = cls._args(a)
        v = cls._vals(p[0], m)
        k = int(cls._av(p[1], m)) - 1
        return sorted(v, reverse=True)[k] if 0 <= k < len(v) else "#ERROR"

    @classmethod
    def _small(cls, a, m):
        p = cls._args(a)
        v = cls._vals(p[0], m)
        k = int(cls._av(p[1], m)) - 1
        return sorted(v)[k] if 0 <= k < len(v) else "#ERROR"

    @classmethod
    def _rank(cls, a, m):
        p = cls._args(a)
        v = sorted(cls._vals(p[0], m), reverse=True)
        return v.index(float(cls._av(p[1], m))) + 1 if v else "#ERROR"

    # ==================== Excel 运算符归一化 ====================
    @staticmethod
    def _normalize_operators(expr):
        """
        把 Excel 的运算符写法归一化成 Python 能解析的写法。

        背景（P0）：
            本项目用 `ast.parse` 求值条件，但 Excel 用 `=` 表示相等、
            `<>` 表示不等、`^` 表示幂；Python 分别要写 `==`、`!=`、`**`。
            原实现没有做归一化，导致 `=IF(A1=1,…)` 直接 #ERROR ——
            这是电子表格最高频的公式之一。

        规则：
            `<>` → `!=`
            单个 `=` → `==`（不碰 ==、>=、<=、!=）
            `^`  → `**`（Python 源码里已有的 `**` 不会被重复处理）
        引号内的字符串原样保留。
        """
        out = []
        i = 0
        n = len(expr)
        quote = None
        while i < n:
            ch = expr[i]

            # 字符串字面量内部不转换
            if quote is not None:
                out.append(ch)
                if ch == quote:
                    quote = None
                i += 1
                continue
            if ch in ('"', "'"):
                quote = ch
                out.append(ch)
                i += 1
                continue

            # <> → !=
            if ch == '<' and i + 1 < n and expr[i + 1] == '>':
                out.append('!=')
                i += 2
                continue

            # 单个 = → ==
            if ch == '=':
                prev = out[-1] if out else ''
                nxt = expr[i + 1] if i + 1 < n else ''
                out.append('=' if (prev in ('<', '>', '!', '=') or nxt == '=')
                           else '==')
                i += 1
                continue

            # ^ → **
            if ch == '^':
                out.append('**')
                i += 1
                continue

            out.append(ch)
            i += 1
        return ''.join(out)

    # ==================== 复合表达式：就地展开函数调用 ====================
    @classmethod
    def _expand_calls(cls, expr, model, depth=0):
        """
        把最内层的函数调用就地求值，用于 `=SUM(A1:A3)*2` 这类复合表达式。

        背景（P0）：
            `_eval` 只认"整串就是一个函数调用"（`^\\w+\\((.*)\\)$`），
            `SUM(A1:A3)*2` 不匹配，最终把公式原文当成单元格内容返回。

        策略：
            用 `\\w+\\([^()]*\\)` 反复替换最内层调用，直到没有可替换的，
            再把剩下的纯算术表达式交给 `_safe_eval`。
            最多递归 8 层，避免病态嵌套。
        """
        import re as _re

        if depth > 8:
            return expr

        funcs = cls._get_all_functions()
        pattern = _re.compile(r'([A-Za-z_]\w*)\(([^()]*)\)')
        state = {"changed": False}

        def repl(m):
            name = m.group(1).upper()
            if name not in funcs:
                return m.group(0)
            try:
                val = cls._func(name, m.group(2), model)
            except Exception:
                return m.group(0)
            # 求值失败的错误串保持原样，交回上层决定
            if isinstance(val, str) and val.startswith('#'):
                return m.group(0)
            state["changed"] = True
            return repr(val) if isinstance(val, (int, float)) else repr(str(val))

        new_expr = pattern.sub(repl, expr)
        if state["changed"] and new_expr != expr:
            return cls._expand_calls(new_expr, model, depth + 1)
        return new_expr

    # ==================== P0-5：安全条件求值 ====================
    @staticmethod
    def _safe_eval(expr, model):
        """
        安全地评估条件表达式。

        支持：
          - 单元格引用：A1、$A$1
          - 数字、字符串常量
          - 比较运算符：> < >= <= == !=
          - 逻辑运算符：and or not
          - 算术运算符：+ - * / % ** //
          - 白名单函数：abs / round / int / float / min / max

        禁止：
          - __import__、eval、exec、open 等
          - 属性访问（obj.attr）
          - 下标访问（obj[key]）
          - lambda、推导式、赋值
        """
        import ast as _ast
        import re as _re

        # 0. Excel 运算符归一化（= → ==，<> → !=，^ → **）
        expr = FormulaEngine._normalize_operators(expr)

        # 1. 把单元格引用替换为它们的值
        def replace_ref(m):
            ref_str = m.group(0).replace('$', '')
            parsed = FormulaEngine._ref(ref_str)
            if not parsed:
                return "0"
            r, c = parsed
            try:
                v = model.get_value(r, c)
                if v is None or v == '':
                    return "0"
                if isinstance(v, (int, float)):
                    return repr(v)
                return repr(str(v))
            except Exception:
                return "0"

        # 匹配形如 A1 / $A$1 / AA12（1~3 个字母）
        ref_pattern = r'\$?[A-Za-z]{1,3}\$?\d+'
        expr_with_values = _re.sub(ref_pattern, replace_ref, expr)

        # 2. AST 白名单校验
        try:
            tree = _ast.parse(expr_with_values, mode='eval')
        except SyntaxError as e:
            raise ValueError(f"条件语法错误: {e}")

        allowed_nodes = (
            _ast.Expression, _ast.BoolOp, _ast.And, _ast.Or,
            _ast.BinOp, _ast.Add, _ast.Sub, _ast.Mult, _ast.Div,
            _ast.Mod, _ast.Pow, _ast.FloorDiv,
            _ast.UnaryOp, _ast.USub, _ast.UAdd, _ast.Not,
            _ast.Compare, _ast.Eq, _ast.NotEq,
            _ast.Lt, _ast.LtE, _ast.Gt, _ast.GtE,
            _ast.Constant, _ast.Name, _ast.Load,
            _ast.Tuple, _ast.List,
            _ast.Call,
        )
        allowed_calls = {'abs', 'round', 'int', 'float', 'min', 'max'}

        for node in _ast.walk(tree):
            if not isinstance(node, allowed_nodes):
                raise ValueError(
                    f"条件不允许的语法: {type(node).__name__}"
                )
            if isinstance(node, _ast.Call):
                if not isinstance(node.func, _ast.Name):
                    raise ValueError("条件不允许复杂函数调用")
                if node.func.id not in allowed_calls:
                    raise ValueError(
                        f"条件不允许调用 {node.func.id}"
                    )

        # 3. 安全求值
        allowed_globals = {
            "__builtins__": {},
            "abs": abs, "round": round, "int": int,
            "float": float, "min": min, "max": max,
            "True": True, "False": False, "None": None,
        }
        return eval(
            compile(tree, "<formula>", "eval"),
            allowed_globals,
            {},
        )

    # ==================== 条件函数（P0-5：改用 _safe_eval） ====================
    @classmethod
    def _if(cls, a, m):
        p = cls._args(a)
        if len(p) < 3:
            return "#ERROR"
        try:
            cond = cls._safe_eval(p[0].strip(), m)
            # v5.0.5：改用 _eval_arg，支持 IF 分支里的嵌套函数
            # 例如 =IF(A1>0, SUM(B1:B5), 0)
            return cls._eval_arg(p[1], m) if cond else cls._eval_arg(p[2], m)
        except Exception as e:
            return f"#ERROR: {e}"

    @classmethod
    def _iferror(cls, a, m):
        p = cls._args(a)
        if len(p) < 2:
            return "#ERROR"
        try:
            v = cls._eval(p[0].strip(), m)
        except Exception:
            # 求值抛异常（如除零）→ 走兜底值
            return cls._eval_arg(p[1], m)
        # v5.0.5：兜底值改用 _eval_arg，支持嵌套函数
        if isinstance(v, str) and v.startswith('#'):
            return cls._eval_arg(p[1], m)
        return v

    @classmethod
    def _ifna(cls, a, m):
        p = cls._args(a)
        if len(p) < 2:
            return "#ERROR"
        try:
            v = cls._eval(p[0].strip(), m)
        except Exception:
            return cls._eval_arg(p[1], m)
        # v5.0.5：兜底值改用 _eval_arg，支持嵌套函数
        if str(v) == '#N/A':
            return cls._eval_arg(p[1], m)
        return v

    @classmethod
    def _and(cls, a, m):
        p = cls._args(a)
        try:
            return all(cls._safe_eval(x.strip(), m) for x in p)
        except Exception:
            return "#ERROR"

    @classmethod
    def _or(cls, a, m):
        p = cls._args(a)
        try:
            return any(cls._safe_eval(x.strip(), m) for x in p)
        except Exception:
            return "#ERROR"

    @classmethod
    def _not(cls, a, m):
        try:
            return not bool(cls._safe_eval(a.strip(), m))
        except Exception:
            return "#ERROR"

    @classmethod
    def _ifs(cls, a, m):
        p = cls._args(a)
        for i in range(0, len(p) - 1, 2):
            try:
                if cls._safe_eval(p[i].strip(), m):
                    # v5.0.5：分支结果改用 _eval_arg，支持嵌套函数
                    return cls._eval_arg(p[i + 1], m)
            except Exception:
                continue
        return "#ERROR"

    @classmethod
    @staticmethod
    def _sheet_range(spec, model):
        """
        解析区域，支持跨表写法 `Sheet2!A1:B10`。

        返回 (r1, c1, r2, c2, getter)；getter(r, c) 从对应工作表取值。
        解析失败返回 None。

        为什么需要它：`_range()` 只认纯 A1 坐标，
        遇到 `S1!A1:A3` 会返回 None，于是 VLOOKUP 跨表一律 #ERROR。
        """
        spec = (spec or "").strip()
        if not spec:
            return None

        sheet = None
        if "!" in spec:
            sheet, spec = spec.rsplit("!", 1)
            sheet = sheet.strip().strip("'\"")

        rng = FormulaEngine._range(spec.strip())
        if not rng:
            return None
        (r1, c1), (r2, c2) = rng

        if sheet:
            getter_sheet = getattr(model, "_get_sheet_data", None)
            data = None
            if getter_sheet:
                try:
                    data = getter_sheet(sheet)
                except Exception:
                    data = None
            if data is None:
                return None

            def get(r, c):
                try:
                    return data.iloc[r, c]
                except Exception:
                    return None
        else:
            def get(r, c):
                return model.get_value(r, c)

        return r1, c1, r2, c2, get

    @classmethod
    def _vlookup(cls, a, m):
        p = cls._args(a)
        if len(p) < 3:
            return "#ERROR"
        lk = str(cls._av(p[0], m))
        rng = cls._sheet_range(p[1], m)
        ci = int(cls._av(p[2], m))
        exact = len(p) < 4 or 'FALSE' in p[3].upper()
        if not rng:
            return "#ERROR"
        r1, c1, r2, c2, get = rng
        for r in range(r1, r2 + 1):
            cv = str(get(r, c1)).strip()
            if exact and cv == lk:
                tc = c1 + ci - 1
                if tc <= c2:
                    return get(r, tc)
            elif not exact:
                try:
                    if float(cv) >= float(lk):
                        tc = c1 + ci - 1
                        if tc <= c2:
                            return get(r, tc)
                except:
                    pass
        return "#N/A"

    @classmethod
    def _hlookup(cls, a, m):
        p = cls._args(a)
        if len(p) < 3:
            return "#ERROR"
        lk = str(cls._av(p[0], m))
        rng = cls._sheet_range(p[1], m)
        ri = int(cls._av(p[2], m))
        if not rng:
            return "#ERROR"
        r1, c1, r2, c2, get = rng
        for c in range(c1, c2 + 1):
            if str(get(r1, c)).strip() == lk:
                tr = r1 + ri - 1
                if tr <= r2:
                    return get(tr, c)
        return "#N/A"

    @classmethod
    def _xlookup(cls, a, m):
        """
        XLOOKUP(lookup_value, lookup_array, return_array,
                [if_not_found], [match_mode], [search_mode])

        v5.1 B1：
          - if_not_found：未找到时返回的默认值（默认 "#N/A"）
          - match_mode：0=精确 1=精确或下一个更大 -1=精确或下一个更小 2=通配符
          - search_mode：1=正序 -1=逆序 2=升序二分 -2=降序二分
                         （本实现只支持 1 / -1）
        """
        p = cls._args(a)
        if len(p) < 3:
            return "#ERROR"
        lk = cls._eval_arg(p[0], m)
        lr = cls._range(p[1])
        rr = cls._range(p[2])
        not_found = cls._eval_arg(p[3], m) if len(p) >= 4 else "#N/A"
        try:
            match_mode = int(cls._eval_arg(p[4], m)) if len(p) >= 5 else 0
        except (ValueError, TypeError):
            match_mode = 0
        try:
            search_mode = int(cls._eval_arg(p[5], m)) if len(p) >= 6 else 1
        except (ValueError, TypeError):
            search_mode = 1

        if not lr or not rr:
            return "#ERROR"
        (r1, c1), (r2, c2) = lr
        (rr1, rc1), (rr2, rc2) = rr

        # 收集待搜索单元格（保留原始偏移量 orig_idx）
        # 注意：不能用 enumerate 的 idx，因为 search_mode=-1 会反向列表，
        # 那时 idx 是反向后的下标，需要映射回原下标才能定位 return_array。
        items = []
        orig_idx = 0
        for r in range(r1, r2 + 1):
            for c in range(c1, c2 + 1):
                items.append((orig_idx, m.get_value(r, c)))
                orig_idx += 1

        if search_mode == -1:
            items = list(reversed(items))

        # ---------- v5.1 B1fix：match_mode=1/-1 找"最接近的" ----------
        # 修复前：match_mode=±1 用"第一个满足条件"（_match_xlookup），
        #         例如 25 会匹配到 10（第一个 ≤ 25 的值）。
        # 修复后：找 ≤ 或 ≥ lookup 里最接近的那个（Excel XLOOKUP 语义）。
        if match_mode in (1, -1):
            try:
                lnum = float(lk)
            except (ValueError, TypeError):
                return not_found

            best_idx = None
            best_diff = None
            for orig_i, v in items:
                try:
                    cnum = float(str(v).strip())
                except (ValueError, TypeError):
                    continue
                if match_mode == 1 and cnum >= lnum:
                    diff = cnum - lnum
                elif match_mode == -1 and cnum <= lnum:
                    diff = lnum - cnum
                else:
                    continue
                if best_diff is None or diff < best_diff:
                    best_diff = diff
                    best_idx = orig_i

            if best_idx is None:
                return not_found
            if rr1 == rr2:
                target_c = rc1 + best_idx
                if target_c <= rc2:
                    return m.get_value(rr1, target_c)
            else:
                target_r = rr1 + best_idx
                if target_r <= rr2:
                    return m.get_value(target_r, rc1)
            return not_found

        # ---------- match_mode=0/-2：直接返回第一个匹配 ----------
        for orig_i, v in items:
            if cls._match_xlookup(v, lk, match_mode):
                if rr1 == rr2:
                    target_c = rc1 + orig_i
                    if target_c <= rc2:
                        return m.get_value(rr1, target_c)
                else:
                    target_r = rr1 + orig_i
                    if target_r <= rr2:
                        return m.get_value(target_r, rc1)

        return not_found

    @classmethod
    def _match_xlookup(cls, cell_value, lookup_value, match_mode):
        """XLOOKUP / XMATCH 共用的匹配逻辑"""
        if cell_value is None:
            cell_value = ""
        if lookup_value is None:
            lookup_value = ""
        cv = str(cell_value).strip()
        lv = str(lookup_value).strip()

        if match_mode == 0:
            return cv == lv

        if match_mode == 2:
            pattern = cls._wildcard_to_regex(lv)
            return bool(re.match(pattern, cv, re.IGNORECASE | re.DOTALL))

        try:
            cnum = float(cv)
            lnum = float(lv)
        except (ValueError, TypeError):
            return False

        if match_mode == 1:
            return cnum >= lnum
        if match_mode == -1:
            return cnum <= lnum
        return False

    @staticmethod
    def _wildcard_to_regex(pattern):
        """把 Excel 通配符（* / ? / ~）转成正则"""
        result = ["^"]
        i = 0
        while i < len(pattern):
            ch = pattern[i]
            if ch == "~" and i + 1 < len(pattern):
                result.append(re.escape(pattern[i + 1]))
                i += 2
            elif ch == "*":
                result.append(".*")
                i += 1
            elif ch == "?":
                result.append(".")
                i += 1
            else:
                result.append(re.escape(ch))
                i += 1
        result.append("$")
        return "".join(result)

    @classmethod
    def _index(cls, a, m):
        p = cls._args(a)
        if len(p) < 2:
            return "#ERROR"
        rng = cls._range(p[0])
        if not rng:
            return "#ERROR"
        (r1, c1), _ = rng
        ri = int(cls._av(p[1], m)) - 1
        ci = int(cls._av(p[2], m)) - 1 if len(p) >= 3 else 0
        return m.get_value(r1 + ri, c1 + ci)

    @classmethod
    def _match(cls, a, m):
        p = cls._args(a)
        if len(p) < 2:
            return "#ERROR"
        lk = str(cls._av(p[0], m))
        rng = cls._range(p[1])
        if not rng:
            return "#ERROR"
        (r1, c1), (r2, c2) = rng
        pos = 1
        for r in range(r1, r2 + 1):
            for c in range(c1, c2 + 1):
                if str(m.get_value(r, c)).strip() == lk:
                    return pos
                pos += 1
        return "#N/A"

    @classmethod
    def _choose(cls, a, m):
        p = cls._args(a)
        idx = int(cls._av(p[0], m)) - 1
        # v5.0.5：结果值改用 _eval_arg，支持嵌套函数
        return cls._eval_arg(p[idx + 1], m) \
            if 0 <= idx < len(p) - 1 else "#ERROR"

    @classmethod
    def _countif(cls, a, m):
        p = cls._args(a)
        if len(p) < 2:
            return "#ERROR"
        rng = cls._range(p[0])
        cond = p[1].strip().strip('"')
        if not rng:
            return "#ERROR"
        (r1, c1), (r2, c2) = rng
        cnt = 0
        for r in range(r1, r2 + 1):
            for c in range(c1, c2 + 1):
                if cls._check_cond(m.get_value(r, c), cond):
                    cnt += 1
        return cnt

    @classmethod
    def _sumif(cls, a, m):
        p = cls._args(a)
        if len(p) < 2:
            return "#ERROR"
        cr = cls._range(p[0])
        cond = p[1].strip().strip('"')
        sr = cls._range(p[2]) if len(p) >= 3 else cr
        if not cr or not sr:
            return "#ERROR"
        (r1, c1), (r2, c2) = cr
        (sr1, sc1), _ = sr
        total = 0
        for r in range(r1, r2 + 1):
            for c in range(c1, c2 + 1):
                if cls._check_cond(m.get_value(r, c), cond):
                    total += float(m.get_value(sr1 + (r - r1), sc1 + (c - c1)) or 0)
        return total

    @classmethod
    def _avgif(cls, a, m):
        p = cls._args(a)
        if len(p) < 2:
            return "#ERROR"
        cr = cls._range(p[0])
        cond = p[1].strip().strip('"')
        ar = cls._range(p[2]) if len(p) >= 3 else cr
        if not cr or not ar:
            return "#ERROR"
        (r1, c1), (r2, c2) = cr
        (ar1, ac1), _ = ar
        total, cnt = 0, 0
        for r in range(r1, r2 + 1):
            for c in range(c1, c2 + 1):
                if cls._check_cond(m.get_value(r, c), cond):
                    total += float(m.get_value(ar1 + (r - r1), ac1 + (c - c1)) or 0)
                    cnt += 1
        return total / cnt if cnt > 0 else 0

    @classmethod
    def _countifs(cls, a, m):
        """
        多条件计数：**同一偏移位置上所有条件同时成立**才算一次。

        修复（P1-14）：原实现把每对 (范围, 条件) 独立计数后相加，
        等于把 COUNTIFS 当成了 SUM(COUNTIF...)，
        例如 COUNTIFS(A1:A3,">1", B1:B3,"x") 会被算成 2+2=4，正确值是 1。
        """
        p = cls._args(a)
        if len(p) < 2 or len(p) % 2 != 0:
            return "#ERROR"

        ranges = []
        for i in range(0, len(p), 2):
            rng = cls._range(p[i])
            if not rng:
                return "#ERROR"
            ranges.append(rng)

        (r1, c1), (r2, c2) = ranges[0]
        cnt = 0
        for r in range(r1, r2 + 1):
            for c in range(c1, c2 + 1):
                dr, dc = r - r1, c - c1
                matched = True
                for k, rng in enumerate(ranges):
                    cond = p[k * 2 + 1].strip().strip('"')
                    value = m.get_value(rng[0][0] + dr, rng[0][1] + dc)
                    if not cls._check_cond(value, cond):
                        matched = False
                        break
                if matched:
                    cnt += 1
        return cnt

    # ==================== P0-11：多条件求和/平均 ====================
    @classmethod
    def _sumifs(cls, a, m):
        """
        多条件求和（P0-11 修复）

        参数顺序：SUMIFS(求和范围, 条件范围1, 条件1, 条件范围2, 条件2, ...)

        修复点：
          原实现 `sr1 + (r - sr1)` 恒等于 r，条件列永远按求和范围的
          起始行取值。改为按条件范围自己的起始行 + 相对偏移。
          同时把 range 从 `range(1, len(p), 2)` 改为 `range(1, len(p) - 1, 2)`
          防越界。
        """
        p = cls._args(a)
        if len(p) < 3:
            return "#ERROR"
        sr = cls._range(p[0])
        if not sr:
            return "#ERROR"
        (sr1, sc1), (sr2, sc2) = sr
        total = 0
        for r in range(sr1, sr2 + 1):
            for c in range(sc1, sc2 + 1):
                dr, dc = r - sr1, c - sc1
                match = True
                for i in range(1, len(p) - 1, 2):
                    cr = cls._range(p[i])
                    cond = p[i + 1].strip().strip('"')
                    if not cr:
                        continue
                    # P1-14：条件范围按"与求和单元格相同的偏移"取值。
                    # 原实现 cond_col 恒取 cr[0][1]，多列条件区只有首列生效。
                    cond_row = cr[0][0] + dr
                    cond_col = cr[0][1] + dc
                    if not cls._check_cond(m.get_value(cond_row, cond_col), cond):
                        match = False
                        break
                if match:
                    total += float(m.get_value(r, c) or 0)
        return total

    @classmethod
    def _avgifs(cls, a, m):
        """
        多条件平均（P0-11 修复）

        参数顺序：AVERAGEIFS(平均范围, 条件范围1, 条件1, 条件范围2, 条件2, ...)
        """
        p = cls._args(a)
        if len(p) < 3:
            return "#ERROR"
        sr = cls._range(p[0])
        if not sr:
            return "#ERROR"
        (sr1, sc1), (sr2, sc2) = sr
        total, cnt = 0, 0
        for r in range(sr1, sr2 + 1):
            for c in range(sc1, sc2 + 1):
                dr, dc = r - sr1, c - sc1
                match = True
                for i in range(1, len(p) - 1, 2):
                    cr = cls._range(p[i])
                    cond = p[i + 1].strip().strip('"')
                    if not cr:
                        continue
                    # P1-14：与 SUMIFS 同源问题——条件区只取首列，多列时条件失效
                    cond_row = cr[0][0] + dr
                    cond_col = cr[0][1] + dc
                    if not cls._check_cond(m.get_value(cond_row, cond_col), cond):
                        match = False
                        break
                if match:
                    total += float(m.get_value(r, c) or 0)
                    cnt += 1
        return total / cnt if cnt > 0 else 0

    @classmethod
    def _round(cls, a, m):
        p = cls._args(a)
        return round(float(cls._av(p[0], m)), int(cls._av(p[1], m))) if len(p) >= 2 else "#ERROR"

    @classmethod
    def _roundup(cls, a, m):
        p = cls._args(a)
        n, d = float(cls._av(p[0], m)), int(cls._av(p[1], m))
        return math.ceil(n * 10 ** d) / 10 ** d

    @classmethod
    def _rounddown(cls, a, m):
        p = cls._args(a)
        n, d = float(cls._av(p[0], m)), int(cls._av(p[1], m))
        return math.floor(n * 10 ** d) / 10 ** d

    @classmethod
    def _power(cls, a, m):
        p = cls._args(a)
        return float(cls._av(p[0], m)) ** float(cls._av(p[1], m)) if len(p) >= 2 else "#ERROR"

    @classmethod
    def _mod(cls, a, m):
        p = cls._args(a)
        return int(cls._av(p[0], m)) % int(cls._av(p[1], m)) if len(p) >= 2 else "#ERROR"

    @classmethod
    def _int(cls, a, m):
        return int(float(cls._av(a, m)))

    @classmethod
    def _trunc(cls, a, m):
        return int(float(cls._av(a, m)))

    @classmethod
    def _ceiling(cls, a, m):
        p = cls._args(a)
        n, s = float(cls._av(p[0], m)), float(cls._av(p[1], m))
        return math.ceil(n / s) * s

    @classmethod
    def _floor(cls, a, m):
        p = cls._args(a)
        n, s = float(cls._av(p[0], m)), float(cls._av(p[1], m))
        return math.floor(n / s) * s

    @classmethod
    def _sumproduct(cls, a, m):
        p = cls._args(a)
        arrs = [cls._vals(x, m) for x in p]
        length = min(len(a) for a in arrs)
        return sum(arrs[0][i] * arrs[1][i] for i in range(length))

    @classmethod
    def _left(cls, a, m):
        p = cls._args(a)
        return str(cls._av(p[0], m))[:int(cls._av(p[1], m))] if len(p) >= 2 else "#ERROR"

    @classmethod
    def _right(cls, a, m):
        p = cls._args(a)
        return str(cls._av(p[0], m))[-int(cls._av(p[1], m)):] if len(p) >= 2 else "#ERROR"

    @classmethod
    def _mid(cls, a, m):
        p = cls._args(a)
        s = int(cls._av(p[1], m)) - 1
        n = int(cls._av(p[2], m))
        return str(cls._av(p[0], m))[s:s + n] if len(p) >= 3 else "#ERROR"

    @classmethod
    def _len(cls, a, m):
        return len(str(cls._av(a, m)))

    @classmethod
    def _trim(cls, a, m):
        return str(cls._av(a, m)).strip()

    @classmethod
    def _upper(cls, a, m):
        return str(cls._av(a, m)).upper()

    @classmethod
    def _lower(cls, a, m):
        return str(cls._av(a, m)).lower()

    @classmethod
    def _proper(cls, a, m):
        return str(cls._av(a, m)).title()

    @classmethod
    def _concat(cls, a, m):
        return "".join(str(cls._av(x, m)) for x in cls._args(a))

    @classmethod
    def _textjoin(cls, a, m):
        p = cls._args(a)
        delim = str(cls._av(p[0], m)).strip('"')
        return delim.join(str(cls._av(x, m)) for x in p[1:])

    @classmethod
    def _find(cls, a, m):
        p = cls._args(a)
        return str(cls._av(p[1], m)).find(str(cls._av(p[0], m))) + 1

    @classmethod
    def _search(cls, a, m):
        p = cls._args(a)
        return str(cls._av(p[1], m)).lower().find(str(cls._av(p[0], m)).lower()) + 1

    @classmethod
    def _replace(cls, a, m):
        p = cls._args(a)
        s = str(cls._av(p[0], m))
        start = int(cls._av(p[1], m)) - 1
        n = int(cls._av(p[2], m))
        new = str(cls._av(p[3], m))
        return s[:start] + new + s[start + n:]

    @classmethod
    def _substitute(cls, a, m):
        p = cls._args(a)
        return str(cls._av(p[0], m)).replace(str(cls._av(p[1], m)), str(cls._av(p[2], m)))

    @classmethod
    def _text(cls, a, m):
        p = cls._args(a)
        return str(cls._av(p[0], m))

    @classmethod
    def _value(cls, a, m):
        return float(cls._av(a, m))

    @classmethod
    def _rept(cls, a, m):
        p = cls._args(a)
        return str(cls._av(p[0], m)) * int(cls._av(p[1], m))

    @classmethod
    def _exact(cls, a, m):
        p = cls._args(a)
        return str(cls._av(p[0], m)) == str(cls._av(p[1], m))

    @classmethod
    def _date(cls, a, m):
        p = cls._args(a)
        return datetime(int(cls._av(p[0], m)), int(cls._av(p[1], m)),
                        int(cls._av(p[2], m))).strftime('%Y-%m-%d')

    @classmethod
    def _datedif(cls, a, m):
        p = cls._args(a)
        d1 = cls._parse_date(cls._av(p[0], m))
        d2 = cls._parse_date(cls._av(p[1], m))
        unit = str(cls._av(p[2], m)).strip('"').lower()
        if unit == 'd':
            return (d2 - d1).days
        elif unit == 'm':
            return (d2.year - d1.year) * 12 + d2.month - d1.month
        elif unit == 'y':
            return d2.year - d1.year
        return "#ERROR"

    @classmethod
    def _edate(cls, a, m):
        p = cls._args(a)
        d = cls._parse_date(cls._av(p[0], m))
        months = int(cls._av(p[1], m))
        return (d + timedelta(days=months * 30)).strftime('%Y-%m-%d')

    @classmethod
    def _eomonth(cls, a, m):
        p = cls._args(a)
        d = cls._parse_date(cls._av(p[0], m))
        months = int(cls._av(p[1], m))
        nd = d + timedelta(days=months * 30 + 31)
        return (nd.replace(day=1) - timedelta(days=1)).strftime('%Y-%m-%d')

    @classmethod
    def _weekday(cls, a, m):
        return cls._parse_date(cls._av(a, m)).weekday() + 1

    @classmethod
    def _weeknum(cls, a, m):
        return cls._parse_date(cls._av(a, m)).isocalendar()[1]

    @classmethod
    def _networkdays(cls, a, m):
        p = cls._args(a)
        d1 = cls._parse_date(cls._av(p[0], m))
        d2 = cls._parse_date(cls._av(p[1], m))
        return int(np.busday_count(d1.date(), d2.date() + timedelta(days=1)))

    @classmethod
    def _workday(cls, a, m):
        p = cls._args(a)
        d = cls._parse_date(cls._av(p[0], m))
        days = int(cls._av(p[1], m))
        return (d + timedelta(days=days)).strftime('%Y-%m-%d')

    @classmethod
    def _hour(cls, a, m):
        return cls._parse_date(cls._av(a, m)).hour

    @classmethod
    def _minute(cls, a, m):
        return cls._parse_date(cls._av(a, m)).minute

    @classmethod
    def _second(cls, a, m):
        return cls._parse_date(cls._av(a, m)).second

    @classmethod
    def _pmt(cls, a, m):
        p = cls._args(a)
        rate, nper, pv = float(cls._av(p[0], m)), int(cls._av(p[1], m)), float(cls._av(p[2], m))
        return -pv / nper if rate == 0 else -(pv * rate * (1 + rate) ** nper) / ((1 + rate) ** nper - 1)

    @classmethod
    def _fv(cls, a, m):
        p = cls._args(a)
        rate, nper, pmt = float(cls._av(p[0], m)), int(cls._av(p[1], m)), float(cls._av(p[2], m))
        pv = float(cls._av(p[3], m)) if len(p) >= 4 else 0
        return -(pv + pmt * nper) if rate == 0 else -(pv * (1 + rate) ** nper + pmt * ((1 + rate) ** nper - 1) / rate)

    @classmethod
    def _pv(cls, a, m):
        p = cls._args(a)
        rate, nper, pmt = float(cls._av(p[0], m)), int(cls._av(p[1], m)), float(cls._av(p[2], m))
        fv = float(cls._av(p[3], m)) if len(p) >= 4 else 0
        return -(fv + pmt * nper) if rate == 0 else -(pmt * (1 - (1 + rate) ** (-nper)) / rate + fv / (1 + rate) ** nper)

    @classmethod
    def _npv(cls, a, m):
        p = cls._args(a)
        rate = float(cls._av(p[0], m))
        vals = cls._vals(p[1], m)
        return sum(v / (1 + rate) ** (i + 1) for i, v in enumerate(vals))

    @classmethod
    def _irr(cls, a, m):
        v = cls._vals(a, m)
        rate = 0.1
        for _ in range(100):
            npv = sum(cf / (1 + rate) ** t for t, cf in enumerate(v))
            dnpv = sum(-t * cf / (1 + rate) ** (t + 1) for t, cf in enumerate(v) if t > 0)
            if dnpv == 0:
                break
            new_rate = rate - npv / dnpv
            if abs(new_rate - rate) < 1e-6:
                return new_rate
            rate = new_rate
        return rate

    @classmethod
    def _rate(cls, a, m):
        p = cls._args(a)
        nper, pmt, pv = int(cls._av(p[0], m)), float(cls._av(p[1], m)), float(cls._av(p[2], m))
        fv = float(cls._av(p[3], m)) if len(p) >= 4 else 0
        rate = 0.1
        for _ in range(100):
            f = pv * (1 + rate) ** nper + pmt * ((1 + rate) ** nper - 1) / rate + fv
            fp = (nper * pv * (1 + rate) ** (nper - 1) +
                  pmt * (nper * (1 + rate) ** (nper - 1) * rate -
                         ((1 + rate) ** nper - 1)) / (rate ** 2))
            if fp == 0:
                break
            new_rate = rate - f / fp
            if abs(new_rate - rate) < 1e-7:
                return new_rate
            rate = new_rate
        return rate

    @classmethod
    def _nper(cls, a, m):
        p = cls._args(a)
        rate, pmt, pv = float(cls._av(p[0], m)), float(cls._av(p[1], m)), float(cls._av(p[2], m))
        fv = float(cls._av(p[3], m)) if len(p) >= 4 else 0
        return -(pv + fv) / pmt if rate == 0 else math.log((pmt - fv * rate) / (pmt + pv * rate)) / math.log(1 + rate)

    @classmethod
    def _sln(cls, a, m):
        p = cls._args(a)
        cost, salvage, life = float(cls._av(p[0], m)), float(cls._av(p[1], m)), int(cls._av(p[2], m))
        return (cost - salvage) / life if life > 0 else "#ERROR"

    @classmethod
    def _db(cls, a, m):
        p = cls._args(a)
        cost = float(cls._av(p[0], m))
        salvage = float(cls._av(p[1], m))
        life = int(cls._av(p[2], m))
        period = int(cls._av(p[3], m))
        rate = 1 - ((salvage / cost) ** (1 / life)) if cost > 0 else 0
        return cost * rate * (1 - rate) ** (period - 1)

    @classmethod
    def get_errors(cls):
        return dict(cls._error_trace)

    @classmethod
    def clear_errors(cls):
        cls._error_trace.clear()

    # ==================== v5.1 B1：新增函数 ====================

    @classmethod
    def _xmatch(cls, a, m):
        """XMATCH(lookup_value, lookup_array, [match_mode], [search_mode])"""
        p = cls._args(a)
        if len(p) < 2:
            return "#ERROR"
        lk = cls._eval_arg(p[0], m)
        lr = cls._range(p[1])
        try:
            match_mode = int(cls._eval_arg(p[2], m)) if len(p) >= 3 else 0
        except (ValueError, TypeError):
            match_mode = 0
        try:
            search_mode = int(cls._eval_arg(p[3], m)) if len(p) >= 4 else 1
        except (ValueError, TypeError):
            search_mode = 1

        if not lr:
            return "#ERROR"
        (r1, c1), (r2, c2) = lr

        items = []
        orig_idx = 0
        for r in range(r1, r2 + 1):
            for c in range(c1, c2 + 1):
                items.append((orig_idx, m.get_value(r, c)))
                orig_idx += 1

        if search_mode == -1:
            items = list(reversed(items))

        for orig_i, v in items:
            if cls._match_xlookup(v, lk, match_mode):
                return orig_i + 1  # 1 基

        return "#N/A"

    @classmethod
    def _let(cls, a, m):
        """
        LET(name1, value1, [name2, value2, ...], calculation)

        把 name 绑定到 value 的求值结果，在 calculation 中替换后求值。
        支持嵌套引用（后面的 name 可引用前面的 name）。

        已知限制（B3 会改进）：
          - 变量名不能是函数名
          - 字符串值替换后可能冲突（含运算符时）
        """
        p = cls._args(a)
        if len(p) < 3 or len(p) % 2 == 0:
            return "#ERROR"

        bindings = {}
        for i in range(0, len(p) - 1, 2):
            name = p[i].strip().strip('"').strip("'")
            value_expr = p[i + 1].strip()
            for n, v in bindings.items():
                value_expr = cls._substitute_var(value_expr, n, v)
            try:
                value = cls._eval(value_expr, m)
            except Exception:
                value = "#ERROR"
            bindings[name] = value

        calc = p[-1].strip()
        for n, v in bindings.items():
            calc = cls._substitute_var(calc, n, v)

        return cls._eval(calc, m)

    @staticmethod
    def _substitute_var(expr, name, value):
        """把 expr 里的 name 替换为 value（字符串加引号，数字直接转）"""
        if isinstance(value, str):
            replacement = '"' + value + '"'
        elif isinstance(value, bool):
            replacement = "TRUE" if value else "FALSE"
        else:
            replacement = str(value)
        pattern = (
            r'(?<![A-Za-z0-9_\u4e00-\u9fff])' +
            re.escape(name) +
            r'(?![A-Za-z0-9_\u4e00-\u9fff])'
        )
        return re.sub(pattern, replacement, expr)

    @classmethod
    def _switch(cls, a, m):
        """SWITCH(expr, val1, result1, [val2, result2, ...], [default])"""
        p = cls._args(a)
        if len(p) < 3:
            return "#ERROR"
        expr = cls._eval_arg(p[0], m)
        remaining = p[1:]
        has_default = len(remaining) % 2 == 1
        pairs = remaining[:-1] if has_default else remaining
        default = cls._eval_arg(remaining[-1], m) if has_default else "#N/A"

        for i in range(0, len(pairs), 2):
            val = cls._eval_arg(pairs[i], m)
            # v5.1 B1fix：数值归一化比较
            # 30 / 30.0 / "30" / "30.0" 都应视为相等（Excel 行为）
            if cls._switch_values_equal(expr, val):
                return cls._eval_arg(pairs[i + 1], m)

        return default

    @staticmethod
    def _switch_values_equal(a, b):
        """SWITCH 的比较：先尝试数值比较，失败后按字符串比较。"""
        if a is None and b is None:
            return True
        if a is None or b is None:
            return False
        # 布尔值不参与数值比较（避免 True == 1）
        if isinstance(a, bool) or isinstance(b, bool):
            return a is b
        try:
            return float(a) == float(b)
        except (ValueError, TypeError):
            return str(a) == str(b)

    @classmethod
    def _xor(cls, a, m):
        """XOR(cond1, cond2, ...) — 奇数个为 TRUE"""
        p = cls._args(a)
        count_true = 0
        for arg in p:
            try:
                if cls._safe_eval(arg.strip(), m):
                    count_true += 1
            except Exception:
                continue
        return count_true % 2 == 1

    @classmethod
    def _maxifs(cls, a, m):
        """MAXIFS(max_range, criteria_range1, criteria1, ...)"""
        p = cls._args(a)
        if len(p) < 3:
            return "#ERROR"
        mr = cls._range(p[0])
        if not mr:
            return "#ERROR"
        (mr1, mc1), (mr2, mc2) = mr

        values = []
        for r in range(mr1, mr2 + 1):
            match = True
            for i in range(1, len(p) - 1, 2):
                cr = cls._range(p[i])
                cond = p[i + 1].strip().strip('"')
                if not cr:
                    continue
                cond_row = cr[0][0] + (r - mr1)
                cond_col = cr[0][1]
                if not cls._check_cond(m.get_value(cond_row, cond_col), cond):
                    match = False
                    break
            if match:
                try:
                    values.append(float(m.get_value(r, mc1)))
                except (ValueError, TypeError):
                    pass

        return max(values) if values else 0

    @classmethod
    def _minifs(cls, a, m):
        """MINIFS(min_range, criteria_range1, criteria1, ...)"""
        p = cls._args(a)
        if len(p) < 3:
            return "#ERROR"
        mr = cls._range(p[0])
        if not mr:
            return "#ERROR"
        (mr1, mc1), (mr2, mc2) = mr

        values = []
        for r in range(mr1, mr2 + 1):
            match = True
            for i in range(1, len(p) - 1, 2):
                cr = cls._range(p[i])
                cond = p[i + 1].strip().strip('"')
                if not cr:
                    continue
                cond_row = cr[0][0] + (r - mr1)
                cond_col = cr[0][1]
                if not cls._check_cond(m.get_value(cond_row, cond_col), cond):
                    match = False
                    break
            if match:
                try:
                    values.append(float(m.get_value(r, mc1)))
                except (ValueError, TypeError):
                    pass

        return min(values) if values else 0

    @classmethod
    def _textbefore(cls, a, m):
        """TEXTBEFORE(text, delimiter, [instance_num])"""
        p = cls._args(a)
        if len(p) < 2:
            return "#ERROR"
        text = str(cls._eval_arg(p[0], m))
        delim = str(cls._eval_arg(p[1], m))
        try:
            instance = int(cls._eval_arg(p[2], m)) if len(p) >= 3 else 1
        except (ValueError, TypeError):
            instance = 1

        if instance > 0:
            pos = -1
            for _ in range(instance):
                pos = text.find(delim, pos + 1)
                if pos < 0:
                    return "#N/A"
            return text[:pos]
        else:
            pos = len(text)
            for _ in range(-instance):
                pos = text.rfind(delim, 0, pos)
                if pos < 0:
                    return "#N/A"
            return text[:pos]

    @classmethod
    def _textafter(cls, a, m):
        """TEXTAFTER(text, delimiter, [instance_num])"""
        p = cls._args(a)
        if len(p) < 2:
            return "#ERROR"
        text = str(cls._eval_arg(p[0], m))
        delim = str(cls._eval_arg(p[1], m))
        try:
            instance = int(cls._eval_arg(p[2], m)) if len(p) >= 3 else 1
        except (ValueError, TypeError):
            instance = 1

        if instance > 0:
            pos = -1
            for _ in range(instance):
                pos = text.find(delim, pos + 1)
                if pos < 0:
                    return "#N/A"
            return text[pos + len(delim):]
        else:
            pos = len(text)
            for _ in range(-instance):
                pos = text.rfind(delim, 0, pos)
                if pos < 0:
                    return "#N/A"
            return text[pos + len(delim):]

    @classmethod
    def _valuetotext(cls, a, m):
        """VALUETOTEXT(value) — 转文本"""
        v = cls._eval_arg(a, m)
        return "" if v is None else str(v)

    @classmethod
    def _isblank(cls, a, m):
        """ISBLANK(value)"""
        v = cls._eval_arg(a, m)
        return v is None or str(v).strip() == ""

    @classmethod
    def _isnumber(cls, a, m):
        """ISNUMBER(value)"""
        v = cls._eval_arg(a, m)
        if isinstance(v, bool):
            return False
        if isinstance(v, (int, float)):
            return True
        if isinstance(v, str):
            try:
                float(v)
                return True
            except (ValueError, TypeError):
                return False
        return False

    @classmethod
    def _istext(cls, a, m):
        """ISTEXT(value)"""
        v = cls._eval_arg(a, m)
        return isinstance(v, str) and v.strip() != ""

    @classmethod
    def _islogical(cls, a, m):
        """ISLOGICAL(value)"""
        v = cls._eval_arg(a, m)
        return isinstance(v, bool)

    @classmethod
    def _iserror(cls, a, m):
        """ISERROR(value)"""
        try:
            v = cls._eval(a, m)
        except Exception:
            return True
        return isinstance(v, str) and v.startswith("#")