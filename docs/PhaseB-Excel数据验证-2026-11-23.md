# Phase B：Excel 数据验证导出

日期：2026-11-23

## 已实现

- 下拉列表验证写入 `DataValidation(type="list")`；
- 数值范围写入 `DataValidation(type="decimal", operator="between")`；
- 新文件导出和已有文件导出都支持；
- 示例：

```python
{"row": 0, "col": 0, "type": "list", "options": ["北京", "上海"]}
{"row": 1, "col": 0, "type": "range", "min": 0, "max": 10}
```

## 验证

```text
tests/unit/test_beesheet_spill_export.py  2 passed
全量：1710 passed
```

## 已知边界

- 文本长度/自定义公式验证未导出；
- 多个不相邻单元格逐个写规则，未合并为连续区域；
- 导入已有验证规则未映射回编辑器。
