# Phase B：Excel 原生图表插入与数据源更新

日期：2026-11-19

## 已实现

- 从选区插入原生 Excel 图表：
  - 柱状图
  - 折线图
  - 饼图
- 图表规格保存在 `_native_chart_specs`；
- 导出 XLSX 时由 openpyxl 写入原生 Chart；
- “编辑数据源”可更新图表范围；
- 测试验证图表写入与范围更新。

## 验证

```text
tests/unit/test_beesheet_native_chart.py  1 passed
全量：1698 passed
```

## 已有图表读取与编辑

- 打开 xlsx 时读取图表类型/标题/数据源范围；
- 编辑数据源后标记 `modified`；
- 导出时更新原图表 series/category 引用；
- 不新增重复图表。

测试：

```text
tests/unit/test_beesheet_native_chart.py  2 passed
```

## 图表样式/图例/坐标轴

- 标题；
- 图例位置 right/left/top/bottom/none；
- 图表样式 1–48；
- X/Y 轴标题；
- 宽高；
- 测试检查生成的 chart XML。

## 已知边界

- 只对本次会话新增的图表生效；
- 已有 XLSX 原生图表的数据源编辑未做；
- 图表位置/尺寸/样式/坐标轴编辑未做；
- 图表预览仍是旧 matplotlib 流程，不是原生对象预览。

## 下一步

1. 读取已有 xlsx 图表并映射数据源；
2. 图表样式/位置编辑；
3. 组合图/次坐标轴；
4. 大数据量性能。
