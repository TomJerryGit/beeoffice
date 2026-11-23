# Phase B：Excel 公式深度

日期：2026-11-19

## 已实现

- 数组区间运算：
  - `=SUM(A1:A3*B1:B3)`
  - `=AVERAGE(A1:A3+B1:B3)`
  - `=MAX/MIN(...)`
- 跨表数组：
  - `=SUM(S1!A1:A2*S1!B1:B2)`
- 维度不一致时返回失败，不静默给错误结果。

## 验证

```text
tests/unit/test_formula_array_depth.py  2 passed
全量：1701 passed
```

## 动态数组/数组常量/函数覆盖

- FILTER/SORT/UNIQUE/SEQUENCE 返回二维数组；
- 公式提交支持溢出到相邻单元格；
- 支持数组常量 `{1,2;3,4}`；
- 新增函数覆盖审计：`tools/formula_coverage_audit.py`；
- 参考函数集 115/115 覆盖：财务/统计/文本/日期/查找/逻辑/动态数组/数学。

新增测试：

```text
tests/unit/test_formula_array_depth.py  5 passed
tests/qt/test_beesheet_spill.py  1 passed
```

## #SPILL! 冲突检测

- 溢出前检查目标区域；
- 有内容则显示 `#SPILL!`，不覆盖；
- 冲突解除后重算恢复；
- 测试：

```text
tests/qt/test_beesheet_spill.py  3 passed
```

## 已知边界

- 只有 SUM/AVERAGE/MAX/MIN 支持数组区间；
- 不支持动态数组/溢出（FILTER/SORT/UNIQUE/SEQUENCE）；
- 不支持数组常量 `{1,2;3,4}`；
- 错误值/空单元格语义仍简化；
- 跨表命名区域深度有限。

## 下一步

1. 动态数组函数；
2. 数组常量；
3. 函数覆盖审计（财务/统计/文本）；
4. 公式重算性能。
