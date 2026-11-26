# Phase B：Word 原生批注导出

日期：2026-11-26

## 已实现

- 导出 `.docx` 时生成 `word/comments.xml`；
- 正文中插入：
  - `w:commentRangeStart`
  - `w:commentRangeEnd`
  - `w:commentReference`
- 按批注 excerpt 在段落中定位 run；
- 无锚点批注挂到首个非空段落；
- 保留作者、时间、内容。

## 验证

```text
tests/unit/test_word_docx_comments.py  1 passed
全量：1714 passed
```

## 文件检查

```text
word/comments.xml 存在
document.xml 含 commentRangeStart
comments.xml 含批注正文
python-docx 可重新打开
```

## 未完成

- 修订 `w:ins/w:del` 尚未导出；
- 原生批注导入未实现；
- 跨多个 run / 跨段落的精确锚点仍为近似。
