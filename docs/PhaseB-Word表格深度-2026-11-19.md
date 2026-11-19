# Phase B：Word 表格深度

日期：2026-11-19

## 已实现

- 表头跨页重复：`w:tblHeader` 读取/导出；
- 列宽：读取/导出；
- 表格对齐：读取并应用；
- 表格样式面板新增“首行跨页重复”。

## 验证

测试文件：

```text
tests/unit/test_word_table_style.py  4 passed
```

全量：

```text
1694 passed
```

## 合并单元格/嵌套表格（增量）

- 合并单元格导入：同一底层 tc 只保留左上角文本，不再重复；
- 合并单元格导出：按 QTextTable 的 rowSpan/columnSpan 写回 DOCX；
- 嵌套表格导入：压平为单元格内 `<br>` 文本，内容不丢失；
- 嵌套表格导出：仍为文本，未生成原生嵌套表格。

测试：

```text
tests/unit/test_word_table_merge_nested.py  3 passed
```

## 仍待补

- 合并单元格完整语义；
- 嵌套表格原生导出；
- 行高/单元格内边距；
- 表格标题/题注联动；
- 复杂表格样式（完整 Word 表格样式名）；
- 真实 Office 2016 表格打开验收。

## 说明

这是 Phase B 的第一个增量，不是完整 Word 排版引擎。
