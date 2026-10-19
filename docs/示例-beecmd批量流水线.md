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

## 5. 模板②：Excel 多表汇总（v0.2 `merge`）

小公司最常见的表格工作之一：每月一张表 → 汇总成一张。
`beecmd merge` 已经能直接做（纯 Python、零 Qt、服务器可跑）：

```powershell
$env:PYTHONPATH='D:\beeofficeV'
cd _ptmp\analysis\stage3_demo
python -m beeoffice.beecmd merge 一月.csv 二月.csv -o 一季度汇总.xlsx
```

实际输出（2026-10-19，两个文件各 2/3 行）：

```
✅ 已汇总 2 个文件 / 5 行 → 一季度汇总.xlsx（append）
```

`info` 校验结果：

```json
{"name": "汇总", "rows": 5, "cols": 14,
 "columns": ["来源文件", "A", "B", "C", ...]}
```

- `append`（默认）：按列名纵向追加，并追加「来源文件」列；列不一致取并集。
- `sheets`：每个输入文件的每个工作表放进同一工作簿（名冲突自动去重）：
  `python -m beeoffice.beecmd merge a.xlsx b.xlsx -o 合并.xlsx --mode sheets`
- `batch` 也支持：
  `{"op": "merge", "srcs": ["1月.xlsx", "2月.xlsx"], "out": "汇总.xlsx"}`
- 回归：`tests/fidelity/test_beecmd_merge.py`（8 条），门禁 `beecmd-merge`。

## 6. 本地 AI 任务：`beecmd ai`（v0.3）

同一套"无 GUI、可审计"的形态也能调用**本地 Ollama**：

```powershell
$env:PYTHONPATH='D:\beeofficeV'
python -m beeoffice.beecmd ai summarize 经营摘要.md `
  --api-base http://127.0.0.1:11434/v1 --model llama3.2 `
  --out AI总结.md --meta ai_meta.json --max-points 4
```

本机实测（llama3.2，CPU 推理）：

```
✅ AI summarize 完成（AI 生成（llama3.2），49.6 s）→ AI总结.md
```

- 失败/未配置 → 退出码 1 且**不写输出文件**（不拿本地规则冒充 AI）；
- `--meta` 记录 model/api_base/source/耗时；`batch` 支持 `{"op": "ai", ...}`；
- 详见 [本地AI任务化-CLI.md](本地AI任务化-CLI.md)，回归 `tests/fidelity/test_beecmd_ai.py`（7 条）。

## 7. 边界（如实说明）

- PDF 转换依赖 Qt 打印路径；无字体环境下**产物可生成但文字不可提取**，
  因此本示例没有对 PDF 做 `verify`（`beecmd verify` 会如实返回"不可判定"退出码 3）。
- 本示例仅处理 2 个输入文件；50 份真实文档的损失率统计（P1-1）尚未做。
- `batch` 的失败路径（单条失败不中断整批、失败也写审计）由既有测试覆盖，
  本次演示是全成功路径。
