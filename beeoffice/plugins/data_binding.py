# beeoffice/plugins/data_binding.py
"""
蜜写数据绑定：解析 {{ 数据源.字段 }} 占位符并替换为实际值

v5.0.1 修复（P1-7）：
  - BindingEngine.render() 第二个返回值从恒为空的 [] 改为
    "未解析变量列表"（list[dict]）。
    原实现返回值第二项没有实际意义，调用方无法感知哪些占位符
    未被成功替换。现返回 VariableParser.extract_variables 生成的
    原始变量 dict，方便上层 UI 高亮/提示未绑定变量。

兼容性：
  - 返回值仍为 2-tuple，现有调用 `rendered, _ = render(...)` 不受影响
  - 未解析的占位符在输出文本中保留原文（行为与 v5.0.0 一致）

v5.0.5 修复：
  - DataSourceManager.get_value 支持负数行号索引（-1 / -2 / ...）
    原 docstring 承诺支持 "字段名.-1"，但实现里 `int(parts[1]) - 1`
    会把 "-1" 转成 -2，导致 0 <= row_num 校验失败，功能形同虚设。
    现改为：负数先转换（row_num = len(df) + row_num），正数按 1 基处理。
  - 裸 `except:` 改为 `except (ValueError, TypeError, KeyError):`
    避免吞掉 KeyboardInterrupt / SystemExit 等系统异常。
"""
import re
from pathlib import Path

#: pandas 是**重量级**依赖（实测首次 import ~0.6 s）。蜜写首次打开 DOCX 时
#: 会 import data_binding，而绝大多数文档**没有数据绑定** —— 把 pandas 延迟到
#: 真正读取数据源/格式化值时再导入，首开不再为它买单（v5.0.17 首开优化）。
_PANDAS = None


def _pandas():
    global _PANDAS
    if _PANDAS is None:
        import pandas as pd

        _PANDAS = pd
    return _PANDAS


class VariableParser:
    """解析 {{ 数据源.字段 }} 占位符"""

    PATTERN = re.compile(r'\{\{\s*([^}]+)\s*\}\}')

    @classmethod
    def extract_variables(cls, text):
        """
        提取文本中的所有变量占位符

        :param text: 模板文本
        :return: list[dict]，每项形如：
            {
                "raw": "{{ 数据源.字段 }}",   # 完整原文
                "expression": "数据源.字段",   # 去掉 {{ }} 后的表达式
                "source": "数据源",            # 数据源名
                "ref": "字段",                 # 字段/引用
                "start": 12,                   # 在文本中的起始位置
                "end": 30,                     # 在文本中的结束位置（不含）
            }
        """
        variables = []
        for match in cls.PATTERN.finditer(text):
            expression = match.group(1).strip()
            parts = expression.split('.', 1)
            source = parts[0].strip() if len(parts) > 0 else ""
            ref = parts[1].strip() if len(parts) > 1 else ""
            variables.append({
                "raw": match.group(0),
                "expression": expression,
                "source": source,
                "ref": ref,
                "start": match.start(),
                "end": match.end(),
            })
        return variables


class DataSourceManager:
    """数据源管理器：注册、查询数据源"""

    def __init__(self):
        self._sources = {}

    def register_dataframe(self, name, df):
        """注册一个 DataFrame 作为数据源"""
        self._sources[name] = df

    def register_file(self, name, filepath):
        """
        从文件加载数据源

        :param name: 数据源名称（用于 {{ name.xxx }} 引用）
        :param filepath: CSV / Excel 文件路径
        :raises FileNotFoundError: 文件不存在
        """
        path = Path(filepath)
        if not path.exists():
            raise FileNotFoundError(f"数据源文件不存在: {filepath}")
        pd = _pandas()
        if path.suffix.lower() == '.csv':
            import chardet
            with open(path, 'rb') as f:
                raw = f.read(10000)
            df = pd.read_csv(
                path,
                encoding=chardet.detect(raw).get('encoding', 'utf-8')
            )
        else:
            df = pd.read_excel(path)
        self._sources[name] = df

    def get_value(self, source, ref):
        """
        获取引用值

        支持的 ref 格式：
          - "字段名"          → 最后一行该字段的值
          - "字段名.行号"     → 指定行（1 基，正数）
          - "字段名.-1"       → 最后一行（等效于 "字段名"）
          - "字段名.-2"       → 倒数第二行

        v5.0.5 修复：
          原实现 `int(parts[1]) - 1` 会把 "-1" 转成 -2，
          然后 `0 <= row_num` 校验失败，-1 索引永远取不到。
          现改为：先判断正负——
            - 负数：row_num = len(df) + row_num（Python 负索引语义）
            - 正数：row_num -= 1（1 基转 0 基）

        :return: 格式化后的字符串；解析失败时返回 "[...]" 形式的提示
        """
        if source not in self._sources:
            return f"[数据源 '{source}' 未找到]"
        df = self._sources[source]

        # ---------- 先处理 "字段名.行号" 格式 ----------
        if '.' in ref:
            parts = ref.rsplit('.', 1)
            try:
                row_num = int(parts[1])
                # 负数索引：-1 = 最后一行，-2 = 倒数第二行
                if row_num < 0:
                    row_num = len(df) + row_num
                else:
                    row_num -= 1  # 正数按 1 基处理

                if parts[0] in df.columns and 0 <= row_num < len(df):
                    val = df.iloc[row_num][parts[0]]
                    return self._format_value(val)
            except (ValueError, TypeError, KeyError):
                # 解析失败（如 parts[1] 不是数字）→ 走下面的默认分支
                pass

        # ---------- 无行号：取该字段最后一行 ----------
        if ref in df.columns:
            val = df.iloc[-1][ref]
            return self._format_value(val)

        return f"[无法解析引用 '{ref}']"

    @staticmethod
    def _format_value(val):
        """值格式化：NaN → 空串；整数浮点 → 无小数点；其他浮点 → 2 位小数"""
        if _pandas().isna(val):
            return ""
        if isinstance(val, float):
            if val == int(val):
                return str(int(val))
            return f"{val:.2f}"
        return str(val)

    @property
    def source_names(self):
        """返回所有已注册数据源的名称"""
        return list(self._sources.keys())


class BindingEngine:
    """数据绑定引擎：将模板中的占位符替换为实际值"""

    def __init__(self, source_manager):
        self.source_manager = source_manager

    def render(self, template_text):
        """
        渲染模板，替换所有数据变量。

        P1-7：第二个返回值从恒为空的 [] 改为未解析变量列表。

        :param template_text: 含 {{ 数据源.字段 }} 占位符的模板文本
        :return: (rendered_text, unresolved)
            - rendered_text: str，替换后的文本。
              未解析的占位符保留原文（不删除）。
            - unresolved: list[dict]，未能成功替换的变量列表。
              每项格式与 VariableParser.extract_variables 的 dict 相同。
        """
        variables = VariableParser.extract_variables(template_text)
        result = template_text
        unresolved = []

        # 倒序替换，避免 start/end 位置错乱
        for var in sorted(variables, key=lambda x: x["start"], reverse=True):
            try:
                value = self.source_manager.get_value(
                    var["source"], var["ref"]
                )
                # 未解析（返回 "[xxx]" 形式）→ 记录并保留原占位符
                if value.startswith("[") and value.endswith("]"):
                    unresolved.append(var)
                else:
                    result = (
                        result[:var["start"]]
                        + value
                        + result[var["end"]:]
                    )
            except Exception:
                unresolved.append(var)

        # 按原文顺序返回未解析列表（方便上层 UI 展示）
        unresolved.sort(key=lambda x: x["start"])
        return result, unresolved

    def preview(self, template_text):
        """
        预览所有变量及其当前值（供变量面板使用）

        :return: list[dict]，每项形如：
            {
                "variable": "{{ 数据源.字段 }}",
                "source": "数据源",
                "ref": "字段",
                "value": "替换后的值 或 [错误提示]",
                "status": "resolved" | "unresolved" | "error",
            }
        """
        variables = VariableParser.extract_variables(template_text)
        previews = []
        for var in variables:
            try:
                value = self.source_manager.get_value(
                    var["source"], var["ref"]
                )
                status = (
                    "unresolved"
                    if value.startswith("[")
                    else "resolved"
                )
            except Exception:
                value = "[错误]"
                status = "error"
            previews.append({
                "variable": var["raw"],
                "source": var["source"],
                "ref": var["ref"],
                "value": value,
                "status": status,
            })
        return previews