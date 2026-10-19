# 本地 AI 任务化：`beecmd ai`（v0.3）

> 日期：2026-10-19 · 代码基线：工作区（v5.0.13 之后，未打包）
> 目标（战略阶段③）：**AI 不能只活在 GUI 按钮里** —— 要能被脚本调用、可本地、可审计、失败不糊弄。

---

## 0. 一页结论

| 项 | 结果 |
|---|---|
| 命令 | `python -m beeoffice.beecmd ai summarize 文件.md --api-base http://127.0.0.1:11434/v1 --model llama3.2` |
| 本机实测（真实 Ollama `llama3.2:latest`，CPU 推理） | **49.6 s** 返回 4 条要点总结，来源标注 `AI 生成（llama3.2）`，元信息 JSON 记录耗时/模型/来源 |
| 任务种类 | `summarize` / `polish` / `keywords` / `continue`（复用 `ai_client` 的提示词构造） |
| 配置顺序 | 命令行参数 > `BEEOFFICE_AI_*` 环境变量 > 应用「AI 设置」 |
| 本地模型 | 无需 API Key（`localhost/127.0.0.1` 自动放行） |
| 诚实性 | 未配置/调用失败 → **退出码 1、说明原因、不写输出文件**（绝不拿本地规则冒充 AI） |
| 零 Qt | AI 路径只用 `requests`/`urllib`；子进程验证 `sys.modules` 无 PySide6 |
| 回归 | `tests/fidelity/test_beecmd_ai.py` **7 条** + 门禁 `beecmd-ai`（PASS） |

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

---

## 2. 为什么这样设计（三个约束）

1. **不把"本地规则"叫 AI**：`AIClient` 在不可用时返回 `available=False`，
   CLI 直接报错退出；不会像旧版"AI 续写"那样插随机模板句还说"完成"。
2. **本地模型不按云端口径超时**：`ai_client.default_timeout_for()` 对
   localhost 用 300 s；实测 49.6 s，云端 30 s 会误判"Ollama 不能用"。
3. **可审计**：`--meta` 记录 model/api_base/source/elapsed_ms；
   `batch` 里也可以混入 `{"op": "ai"}` 任务，与 convert/verify/merge 同一条审计流水。

## 3. 用法

```powershell
# 总结
python -m beeoffice.beecmd ai summarize 报告.md --model llama3.2 `
  --api-base http://127.0.0.1:11434/v1

# 润色 / 关键词 / 续写
python -m beeoffice.beecmd ai polish   草稿.md -o 草稿_润色.md --model llama3.2 --api-base ...
python -m beeoffice.beecmd ai keywords 报告.md -o 关键词.md --count 8 ...
python -m beeoffice.beecmd ai continue 开头.md -o 续写.md --length 200 ...

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
- 任务种类 4 个（总结/润色/关键词/续写），尚未覆盖"表格清洗/条款抽取/演示大纲"；
- 本地 CPU 推理慢（49.6 s/次，300 字输入、4 条要点）；GPU/更小模型会更快；
- 模型需用户自行 `ollama pull`；云服务需要 Key；
- 没有对模型输出做事实核查（AI 仍可能编数字）——`--meta` 只记录来源，不证明正确。

## 5. 复跑

```powershell
# 不联网的回归
python -m pytest tests/fidelity/test_beecmd_ai.py -q
python tools\check_gates.py --only beecmd-ai

# 真实本地模型（需先 ollama serve + ollama pull llama3.2）
python -m beeoffice.beecmd ai summarize 你的文件.md --api-base http://127.0.0.1:11434/v1 --model llama3.2
```
