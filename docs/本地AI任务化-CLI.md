# 本地 AI 任务化：`beecmd ai`（v0.3）

> 日期：2026-10-19 · 代码基线：工作区（v5.0.13 之后，未打包）
> 目标（战略阶段③）：**AI 不能只活在 GUI 按钮里** —— 要能被脚本调用、可本地、可审计、失败不糊弄。

---

## 0. 一页结论

| 项 | 结果 |
|---|---|
| 命令 | `python -m beeoffice.beecmd ai summarize 文件.md --api-base http://127.0.0.1:11434/v1 --model llama3.2` |
| 本机实测（真实 Ollama `llama3.2:latest`，CPU 推理） | 总结 **49.6 s**；演示大纲 **74.6 s**；条款抽取 **65.0 s**（首次 JSON 不合格，自动修复重试后通过）；均标注 `AI 生成（llama3.2）` 并写元信息 |
| 任务种类 | `summarize` / `polish` / `keywords` / `continue` / **`extract`（条款抽取，严格 JSON）** / **`outline`（演示大纲，`# 页` + `---`）** |
| 配置顺序 | 命令行参数 > `BEEOFFICE_AI_*` 环境变量 > 应用「AI 设置」 |
| 本地模型 | 无需 API Key（`localhost/127.0.0.1` 自动放行） |
| 诚实性 | 未配置/调用失败 → **退出码 1、说明原因、不写输出文件**；`extract`/`outline` 输出不合规 → 保存 `.raw.txt` 并失败，**不把解释文字当结构化结果** |
| 零 Qt | AI 路径只用 `requests`/`urllib`；子进程验证 `sys.modules` 无 PySide6 |
| 回归 | `tests/fidelity/test_beecmd_ai.py` **15 条** + 门禁 `beecmd-ai`（PASS） |

---

## 1. 真实调用证据（不是 mock）

输入 `经营摘要.md`（约 300 字：收入 1200 万、同比 +18%、毛利率 42%、研发投入 260 万、
现金余额 900 万、回款周期 75 天）。

```powershell
cd D:\beeofficeV
$env:PYTHONPATH='D:\beeofficeV'
python -m beeoffice.beecmd ai summarize 经营摘要.md `
  --api-base http://127.0.0.1:11434/v1 --model llama3.2 `
  --out AI总结.md --meta ai_meta.json --max-points 4
```

实际输出：

```
✅ AI summarize 完成（AI 生成（llama3.2），49.6 s）→ AI总结.md
   元信息: ai_meta.json
```

`AI总结.md`：

```markdown
- 2026 年第三季度营业收入同比增长 18%，毛利率增加 2%。
- 主要增长源于企业版订阅和海外市场增长。
- 研发投入和销售费用占收入 21.7% 和 15%。
- 现金流保持为正，期末现金余额 900 万元。
```

`ai_meta.json`：

```json
{
  "tool": "beecmd", "version": "0.3.0", "op": "ai",
  "task": "summarize", "model": "llama3.2",
  "api_base": "http://127.0.0.1:11434/v1",
  "source": "ai", "elapsed_ms": 49575.3
}
```

**判读**：数字（18%、42%→+2pt、21.7%、900 万、180/1200=15%）与原文一致，
是真实模型输出而非模板句；`source=ai` 是机器可复核的来源标记。

### 1.2 演示大纲（`outline`，74.6 s）

```powershell
python -m beeoffice.beecmd ai outline 经营摘要.md --slides 5 `
  --api-base http://127.0.0.1:11434/v1 --model llama3.2 --out 演示大纲.md
```

实际输出（节选）：

```markdown
# 季度经营摘要（本地 AI 任务演示）

- 2026 年第三季度营业收入 1200 万元，同比增长 18%。
- 毛利率 42%，较上季度提升 2 个百分点。

---

# 成本管理

- 研发投入 260 万元（占收入 21.7%）。
...

---

# 总结
...
```

紧接着可直接变成蜜演文稿（**不需要 GUI**）：

```powershell
python -m beeoffice.beecmd convert 演示大纲.md --to beshow -o 演示大纲.beshow
# ✅ 演示大纲.md → 演示大纲.beshow（beshow）
```

（模型输出里混入的英文 `however` 等瑕疵原样保留 —— 本工具不做事实/语言"美化"。）

### 1.3 条款抽取（`extract`，严格 JSON；65.0 s，含一次自动修复重试）

第一次调用 `llama3.2` 返回的"JSON"实际是
`["title":...,...]`（缺 `{}`，不合法）。工具**没有把它当结果**，而是：

1. 保存原始输出到 `条款抽取.json.raw.txt`；
2. 自动发一次"格式修复"请求；
3. 第二次输出合法后，写入结果文件：

```json
[
  {"title": "营业收入", "value": "1200 万元",
   "quote": "2026 年第三季度，公司实现营业收入 1200 万元，同比增长 18%；"},
  {"title": "毛利率", "value": "42%",
   "quote": "毛利率 42%，较上季度提升 2 个百分点。"},
  ...
  {"title": "期末现金余额", "value": "900 万元",
   "quote": "现金流保持为正，期末现金余额 900 万元"}
]
```

元信息 `attempts=2`；若两次都不合法，仍然失败并保留 raw —— **结构化任务不假装绿**。

---

## 2. 为什么这样设计（四个约束）

1. **不把"本地规则"叫 AI**：`AIClient` 在不可用时返回 `available=False`，
   CLI 直接报错退出；不会像旧版"AI 续写"那样插随机模板句还说"完成"。
2. **本地模型不按云端口径超时**：`ai_client.default_timeout_for()` 对
   localhost 用 300 s；实测 49.6 s，云端 30 s 会误判"Ollama 不能用"。
3. **可审计**：`--meta` 记录 model/api_base/source/elapsed_ms/attempts；
   `batch` 里也可以混入 `{"op": "ai"}` 任务，与 convert/verify/merge 同一条审计流水。
4. **结构化任务有契约**：`extract` 必须能解析成 JSON 数组/对象、`outline` 必须有
   `# 标题`；不合规时**自动修复重试一次**（`--no-retry` 可关），仍不合规则
   保存 `.raw.txt` 并退出码 1 —— 绝不把解释文字包装成"结构化结果"。

## 3. 用法

```powershell
# 总结
python -m beeoffice.beecmd ai summarize 报告.md --model llama3.2 `
  --api-base http://127.0.0.1:11434/v1

# 润色 / 关键词 / 续写
python -m beeoffice.beecmd ai polish   草稿.md -o 草稿_润色.md --model llama3.2 --api-base ...
python -m beeoffice.beecmd ai keywords 报告.md -o 关键词.md --count 8 ...
python -m beeoffice.beecmd ai continue 开头.md -o 续写.md --length 200 ...

# 结构化任务
python -m beeoffice.beecmd ai extract 合同.md -o 条款.json --limit 10 --model llama3.2 --api-base ...
python -m beeoffice.beecmd ai outline 报告.md -o 演示大纲.md --slides 8 --model llama3.2 --api-base ...
#   不合规 → 自动修复重试一次；加 --no-retry 可关闭

# 环境变量（服务器/流水线）
$env:BEEOFFICE_AI_API_BASE='http://127.0.0.1:11434/v1'
$env:BEEOFFICE_AI_MODEL='llama3.2'
python -m beeoffice.beecmd ai summarize 报告.md -o 总结.md

# 批量（与其它任务共用审计）
# jobs.json: {"jobs": [{"op":"ai","task":"summarize","src":"a.md","out":"a.summary.md","model":"llama3.2","api_base":"http://127.0.0.1:11434/v1"}]}
python -m beeoffice.beecmd batch jobs.json --audit audit.jsonl
```

## 4. 边界（如实）

- 只有**单轮文本任务**：没有流式输出、没有多轮对话、没有任务 DSL/并行；
- 任务种类 6 个（总结/润色/关键词/续写/条款抽取/演示大纲）；**表格清洗**尚未做
  （需要把表结构/样本送模型并回写，是另一个工程）；
- 本地 CPU 推理慢：总结 49.6 s、大纲 74.6 s、抽取 65.0 s（含重试）；GPU/更小模型会更快；
- `llama3.2` 对**严格 JSON** 不可靠（实测首次不合格），要靠一次修复重试；
  更大模型或支持 JSON mode 的端点会更稳；
- 模型需用户自行 `ollama pull`；云服务需要 Key；
- 没有对模型输出做事实核查（AI 仍可能编数字）——`--meta` 只记录来源，不证明正确。

## 5. 复跑

```powershell
# 不联网的回归（15 条，含 extract/outline 契约与重试）
python -m pytest tests/fidelity/test_beecmd_ai.py -q
python tools\check_gates.py --only beecmd-ai

# 真实本地模型（需先 ollama serve + ollama pull llama3.2）
python -m beeoffice.beecmd ai summarize 你的文件.md --api-base http://127.0.0.1:11434/v1 --model llama3.2
python -m beeoffice.beecmd ai outline   你的文件.md --api-base http://127.0.0.1:11434/v1 --model llama3.2 --slides 6
python -m beeoffice.beecmd ai extract   你的文件.md --api-base http://127.0.0.1:11434/v1 --model llama3.2 --limit 10
```
