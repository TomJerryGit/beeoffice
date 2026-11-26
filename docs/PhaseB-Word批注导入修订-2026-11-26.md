# Phase B：Word 原生批注导入 + 修订导出

日期：2026-11-26

## 批注导入

- 读取 `word/comments.xml`；
- 解析 `commentRangeStart/End` 之间的正文作为 excerpt；
- 在编辑器纯文本中查找 excerpt，恢复锚点位置；
- 刷新批注面板。

测试：

```text
test_comments_read_back
```

## 修订导出

- 使用 RevisionManager 基线；
- 行级 diff；
- 新增段落包裹 `w:ins`；
- 删除段落写成 `w:del + w:delText`；
- 只在文档段落数与当前文本行数一致时启用，避免表格/图片错位。

测试：

```text
test_revisions_written_to_docx
```

## 全量

```text
1715 passed, 1 skipped
```

## 边界

- 批注锚点是 excerpt 近似定位，不是精确字符偏移；
- 修订是简化行级标记，不包含 Word 的完整修订语义；
- 复杂表格/图片文档可能跳过修订标记；
- Excel 透视表仍未评估/实现。
