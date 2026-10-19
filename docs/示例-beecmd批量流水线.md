# 示例：beecmd 批量流水线（无 GUI、可审计）

> 目的：演示 `beecmd` 如何在不打开任何界面的情况下完成一件真实工作，
> 并留下可复核的审计流水。这是"本地优先、可编程、可审计"定位的最小形态。
> 复现时间：2026-10-19（v5.0.12 + P1 改动）

## 1. 准备输入

`周报.md`：

```markdown
# 阶段③预演：一份"无 GUI 真实工作"的最小批量流水线

## 一、表格往返

| 项目 | 金额 |
|---|---:|
| 差旅 | 1200 |
| 办公 | 800 |

## 二、结论

- 表格往返校验必须 0 差异；
- 文档转换失败要如实返回非 0 退出码。
```

表格源文件使用仓库已有的 `test+files/表格.xlsx`。

## 2. 任务清单 `jobs.json`

```json
{
  "jobs": [
    {"op": "convert", "src": "test+files/表格.xlsx", "to": "csv", "out": "out/表格.csv"},
    {"op": "convert", "src": "out/表格.csv", "to": "xlsx", "out": "out/表格_往返.xlsx"},
    {"op": "verify", "src": "test+files/表格.xlsx", "artifact": "out/表格_往返.xlsx", "report": "out/verify_sheet.json"},
    {"op": "convert", "src": "周报.md", "to": "docx", "out": "out/周报.docx"},
    {"op": "verify", "src": "周报.md", "artifact": "out/周报.docx", "report": "out/verify_doc.json"},
    {"op": "convert", "src": "周报.md", "to": "pdf", "out": "out/周报.pdf"},
    {"op": "convert", "src": "周报.md", "to": "beshow", "out": "out/周报.beshow"}
  ]
}
```

## 3. 执行（不需要 GUI，不需要 Qt 窗口）

```powershell
$env:PYTHONPATH='D:\beeofficeV'
cd _ptmp\analysis\stage3_demo
python -m beeoffice.beecmd batch jobs.json --audit audit.jsonl
```

实际输出（2026-10-19 15:46）：

```
✅ 表格.xlsx → 表格.csv（csv）
✅ 表格.csv → 表格_往返.xlsx（xlsx）
✅ 报告已写入 verify_sheet.json（不一致 0 处）
✅ 周报.md → 周报.docx（docx）
✅ 报告已写入 verify_doc.json（不一致 0 处）
✅ 周报.md → 周报.pdf（pdf）
✅ 周报.md → 周报.beshow（beshow）
📝 审计流水已追加 7 条 → audit.jsonl
批量完成：7/7 条成功
```

`verify_sheet.json` 关键字段：

```json
{"op": "verify", "ok": true, "mismatches": 0, "mode": "sheet"}
```

`verify_doc.json` 关键字段：

```json
{"op": "verify", "ok": true, "mismatches": 0, "mode": "text"}
```

`audit.jsonl` 每行一条：

```json
{"ts": "2026-10-19T15:46:55", "index": 1, "op": "convert",
 "job": {"op": "convert", "src": "...", "to": "csv", "out": "..."},
 "ok": true, "exit_code": 0}
```

## 4. 边界（如实说明）

- PDF 转换依赖 Qt 打印路径；无字体环境下**产物可生成但文字不可提取**，
  因此本示例没有对 PDF 做 `verify`（`beecmd verify` 会如实返回"不可判定"退出码 3）。
- 本示例仅处理 2 个输入文件；50 份真实文档的损失率统计（P1-1）尚未做。
- `batch` 的失败路径（单条失败不中断整批、失败也写审计）由既有测试覆盖，
  本次演示是全成功路径。
