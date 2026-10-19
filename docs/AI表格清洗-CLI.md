# AI 表格清洗（`beecmd clean`，v0.4）

> 日期：2026-10-19 · 代码基线：`45a4d05` 之后（`beecmd` v0.4，尚未打包发行）
> 目标（战略阶段③ P2-1）：把"AI 表格清洗"做成**结构化、可审计、可回滚**的任务，
> 而不是"让模型直接改表"。

---

## 0. 一页结论

| 项 | 结果 |
|---|---|
| 命令 | `python -m beeoffice.beecmd clean 脏数据.csv -o 清洗后.xlsx --api-base http://127.0.0.1:11434/v1 --model llama3.2` |
| 设计 | **AI 只产出"清洗计划 JSON"**；实际修改由**确定性代码**执行（白名单 6 种操作） |
| 本机实测（真实 Ollama `llama3.2`，CPU） | 6 行脏 CSV → **46.5 s** 完成（`attempts=2`：首轮计划不合法 → 自动修复），输出 2 行干净表 |
| 输出 | 清洗后 `.xlsx` + `<out>.plan.json`（可复跑）+ `<out>.report.json`（改动明细） |
| 可回滚 | 原始文件**绝不修改**；`--plan` 可跳过 AI 按已有计划复跑；每次输出到新文件 |
| 可审计 | 报告逐项记录 `op / changed / samples(row,column,before,after)`；`original_untouched=true` |
| 计划白名单 | `trim_whitespace` / `drop_empty_rows` / `drop_duplicate_rows` / `normalize_column_names` / `fill_missing` / `drop_rows_with_missing` |
| 严格性 | 计划必须合法 JSON、op 在白名单内、列必须存在；不合法→修复重试一次→仍不合法保存 `.plan.raw.txt` 并退出码 1，**不写清洗结果** |
| 零 Qt | 子进程验证 `sys.modules` 无 PySide6 |
| 回归 | `tests/fidelity/test_beecmd_table_clean.py` **6 条** + 门禁 `beecmd-clean`（第 45 项） |

---

## 1. 真实调用证据（不是 mock）

输入 `脏数据.csv`（6 行，含首尾空白、空行、重复行、缺失金额）：

```csv
姓名,部门,金额,备注
" 张三 ",销售,100, 
"李四",销售,,需要补全
" 张三 ",销售,100, 
"",,, 
王五,技术,50,
李四,销售,,重复行
```

```powershell
python -m beeoffice.beecmd clean 脏数据.csv -o 清洗后.xlsx --report 清洗报告.json `
  --api-base http://127.0.0.1:11434/v1 --model llama3.2
```

实际输出：

```
✅ 清洗完成（ai，10 项操作 / 9 处修改）：行 6→2 → 清洗后.xlsx
   计划: 清洗后.xlsx.plan.json
   报告: 清洗报告.json
```

（10 项里有若干重复的 `trim_whitespace` 空操作——模型计划不"优雅"，
但**执行由确定性代码完成**，每项 `changed` 可核对；这是设计上的取舍。）

`清洗报告.json`（节选）：

```json
{
  "op": "clean", "plan_source": "ai", "attempts": 2,
  "rows_before": 6, "rows_after": 2,
  "operations": [
    {"op": "trim_whitespace", "changed": 5,
     "samples": [{"row": 0, "column": "姓名", "before": " 张三 ", "after": "张三"}]},
    {"op": "drop_empty_rows", "changed": 1, "samples": []},
    {"op": "drop_duplicate_rows", "changed": 1, "samples": []},
    {"op": "drop_rows_with_missing", "column": "金额", "changed": 2, "samples": []}
  ],
  "original_untouched": true
}
```

清洗后结果（2 行，金额缺失行被删除）：

```
姓名 部门  金额
张三 销售 100
王五 技术  50
```

**判读**：AI 只负责"想清洗步骤"，实际单元格修改由本工具确定性执行；
每一步改了几处、样例行列号都在报告里，原始 CSV 未动。

## 2. 两种运行模式

### 2.1 AI 出计划（默认）

读表 → 生成概况（行列数、列类型、缺失数、重复行数、前 20 行样本，**不传全表**）→
模型输出 `{"operations": [...]}` → 校验 → 执行。首轮不合法时自动修复重试一次
（`--no-retry` 可关）。

### 2.2 按已有计划复跑（`--plan`）

```powershell
python -m beeoffice.beecmd clean 脏数据.csv -o 清洗后_第二次.xlsx --plan 清洗后.xlsx.plan.json
```

- 不联网、不依赖模型，**结果可复现**；
- 适合流水线、审计、回滚：保留原始文件 + 计划 JSON，随时重跑。

## 3. 为什么不让模型直接改表

| 风险 | 本设计的处理 |
|---|---|
| 模型编造单元格值 | 只允许结构化计划；填充值是计划的一部分，报告保留 before/after |
| 模型删错行/列 | 操作白名单 + 列存在性校验；不提供"直接写值/删列"类操作 |
| 无法回滚 | 原始文件不动；输出新文件 + 计划可复跑 |
| 无法审计 | 报告逐项记录 changed 与样例行列号 |
| 模型输出格式不稳定 | 严格 JSON 契约 + 一次修复重试；不合格保存 raw 并失败 |

## 4. 边界（如实）

- 只覆盖 6 种操作：去空白、删空行、删重复行、列名规范化、填缺失、按列删缺失；
  **没有**类型转换、日期解析、模糊去重、跨表对齐、拆分/合并列；
- 模型计划质量不稳定：可能重复/冗余/漏操作（本机实测 10 项中有 5 项是空操作）；
  但它**不能**做白名单外的修改；
- 稀疏表/大表未优化（当前逐行 Python 处理；万行级可用，百万行需要 pandas 向量化）；
- 本地 CPU 推理一次约 45–90 s（含可能的修复重试）；
- 只输出 `.xlsx`（后续可加 CSV 输出）；
- 这是"清洗步骤建议 + 安全执行"，**不是**通用数据清洗引擎。

## 5. 复跑与测试

```powershell
# 不联网回归（6 条：--plan 确定性、拒绝非法计划、AI 模式、修复重试、
# 两次失败不写结果、零 Qt）
python -m pytest tests/fidelity/test_beecmd_table_clean.py -q
python tools\check_gates.py --only beecmd-clean

# 真实本地模型（需 ollama serve + ollama pull llama3.2）
python -m beeoffice.beecmd clean 你的表.xlsx -o 清洗后.xlsx --api-base http://127.0.0.1:11434/v1 --model llama3.2
```
