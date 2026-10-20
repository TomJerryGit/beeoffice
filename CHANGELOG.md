# 更新日志

本文件记录蜜蜂办公 BeeOffice 的所有重要变更。

格式参考 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.0.0/)，
版本号遵循 [语义化版本](https://semver.org/lang/zh-CN/)。

---
## [Unreleased]

**独立命令行包（`beecmd.exe`）**：

### 新增
- `tools/build_cli.py` + `tools/beecmd_entry.py`：用 PyInstaller 打**独立 `beecmd.exe`**
  （onefile，零 Qt，77.5 MB；ZIP 76.8 MB）。
  冒烟矩阵 **8/8 exit 0**（version / convert×2 / verify / merge / clean / beshow / ai，
  AI 用本地 Ollama `llama3.2` 65.0 s）；ZIP sha256
  `aab09dc326f9dfbcdf01db63c494581db1affcd8e64fa4abda145bbb467f8739`，
  归档 `release-archive/cli/`。详见 `docs/beecmd-独立命令行包.md`。
- 新增 4 条打包器单测 `tests/unit/test_build_cli.py`。

### 修复
- **GBK 控制台崩溃**：独立 exe 在 Windows 默认 cp936 控制台下，成功输出
  `print("✅ …")` 抛 `UnicodeEncodeError`，命令实际完成却 exit 1。
  `beecmd.main()` 现在先执行 `_make_console_safe()`（`errors="replace"`，保留原编码）；
  新增 2 条测试 + 门禁 `beecmd-console`（第 **46** 项）。
  这是打包冒烟发现的真 bug，不是假绿。

---

**50 份用户语料保真 + 多分节页脚修复 + 测试基建**：

### 修复
- **多分节 DOCX 页脚丢失**（50 份用户语料撞出）：`测试文档_5万字.docx` 有 3 节，
  前两节页脚为空、第 3 节放页码域；原实现只看第 1 节，往返后
  `footer_parts 2 → 1` 且前两节凭空出现页码。
  `read_docx_extras()` 现在记录每个分节的页眉/页脚部件（`section_parts`），
  `apply_header_footer()` 逐节还原；实测 `footer_parts 2 → 2`、页码只在第 3 节；
  GUI 的 Markdown 导出路径（`beewrite_export_mixin`）同样传入。
- **全量测试会卡死**：干净 worktree 跑 `test_p0_shortcut_fixes` 时，
  `qtbot.wait` 进入事件循环，App 启动读取**用户 home 的草稿目录**并弹模态框
  `QMessageBox.question` → 900 s 超时。`tests/conftest.py` 新增 autouse fixture，
  把 `BEEOFFICE_DRAFT_DIR` 指到每个测试的 tmp_path（测试结果不再依赖开发机环境）。

### 工具与测试
- `tools/fidelity_report.py --max-size-mb`：跳过 20 万行 xlsx 等"Markdown 往返不可行"
  的大文件，并在报告中写明跳过原因。
- `tests/fidelity/test_corpus.py`：用户语料 fixture 同步 8 MB 护栏；xlsx 不再误跑
  `text_chars` 断言。
- `tests/fidelity/test_fidelity_report.py`：新语料里有带目录域（86 个 `toc_field`）的
  真实文档，检测器**正确**报 medium 级提示；旧断言"所有 corpus 文档零误报"因此假失败。
  现改为：只对**逐项验证过零丢失的 7 份**断言零输出；新语料的能力降级另用
  `test_toc_degradation_is_medium_not_prompt` 钉住（报 medium、不弹窗）。
- 报告 [保真报告-50份真实语料.md](docs/保真报告-50份真实语料.md)：用户投放
  64 个文件 → **41 份可做 OOXML 往返**（18 份跳过：16 pptx 无导入路径 + 2 份大 xlsx），
  **未知类别 0**；差异仍是 `paragraphs`/`text_chars`/`fields` 三类已知项。

### 工程
- 干净 worktree（只含已跟踪文件 + 用户 64 文件语料）最终验证：
  **46/46 门禁 PASS**（12.6 分钟）、**全量 `fidelity+unit` 1474 passed /
  4 skipped / 0 failed**（545.2 s，commit `988097f`）。
- 独立 `beecmd.exe` 打包与 GBK 控制台修复见下文（同日完成）。
---
## [5.0.15] - 2026-10-19

**AI 表格清洗版（`beecmd` v0.4）**：新增"AI 出计划、确定性执行、可回滚"的表格清洗；
不改变 GUI 行为。GUI 安装包按设计不含 `beecmd`/`tools`。

### 新增
- `beecmd clean`：**AI 出计划、确定性执行、可回滚**的表格清洗。
  - AI 只输出 `{"operations":[...]}`（白名单：去空白/删空行/删重复行/列名规范化/
    填缺失/按列删缺失）；实际单元格修改由本工具执行；
  - `--plan` 可跳过 AI 按已有计划复跑；原始文件绝不修改；输出
    `<out>.plan.json` + `<out>.report.json`（逐项 changed 与样例行列号）；
  - 计划严格 JSON、列必须存在；不合规自动修复重试一次，仍不合规则保存
    `.plan.raw.txt` 并失败（不写清洗结果）；
  - 本机实测（Ollama `llama3.2`，CPU）：6 行脏 CSV → 46.5 s（`attempts=2`，
    首轮计划不合法→修复）输出 2 行干净表；报告 `original_untouched=true`。
  - 新增 6 条测试 + 门禁 `beecmd-clean`（第 45 项）。
  - 详见 `docs/AI表格清洗-CLI.md`。

### 调整
- i18n 棘轮排除 `beeoffice/beecmd.py`（CLI 控制台文案，不是 GUI locale）：
  基线 3700/117 → **3599/116**；GUI 侧棘轮不变。
- `beecmd clean` 填充缺失值时先转 object，避免 pandas incompatible-dtype
  FutureWarning（未来版本会变成错误）。

### 工程
- 新增 `beecmd-clean` 门禁后，干净 worktree 验证：**45/45 门禁 PASS**、
  **全量 `fidelity+unit` 1467 passed / 4 skipped / 0 failed**（134.9 s，
  commit `ba07f72`；日志 `_ptmp/analysis/gates_clean_45b.log` / `pytest_clean_full3.log`）。
---
## [5.0.14] - 2026-10-19

**阶段③工程版**：把"可编程、可审计、本地 AI"落成可运行的工具链 ——
`beecmd` v0.3 AI 六任务、三个流水线模板、保真报告生成器、i18n 硬编码棘轮。
本版**不改变 GUI 行为**；GUI 安装包按设计不含 `beecmd`/`tools`（源码级/服务器工具），
需要 CLI 的部署请直接从仓库运行。

### 新增工具
- `tools/i18n_audit.py`：**硬编码中文文案棘轮**。统计引号外中文串（排除 docstring /
  `tr()` 参数 / 日志 / 控制台），与 `tools/i18n_baseline.json` 比较，
  **只许减少、不许增加**。当前基线 **3700 处 / 117 文件**（Top：
  `beesheet_data_mixin` 216、`beesheet_ui_mixin` 214、`beesheet_audit_mixin` 128）。
  新增报告 `docs/i18n-现状与硬编码棘轮.md`（含 Top 文件与"tr 化 vs 中文优先"两条路线）。
  回归：`tests/unit/test_i18n_audit.py` 6 条 + 门禁 `i18n-ratchet`（第 44 项门禁）。
- `beecmd ai`（CLI v0.3）：**本地/云端 AI 任务** —— `summarize` / `polish` /
  `keywords` / `continue` / **`extract`（条款抽取，严格 JSON）** /
  **`outline`（演示大纲）** 六个任务，可脚本调用、可写 JSON 元信息；
  配置顺序为命令行 > `BEEOFFICE_AI_*` 环境变量 > 应用「AI 设置」；
  本地 Ollama 无需 Key。**实测**（本机 `llama3.2` CPU 推理）：
  300 字摘要 → 49.6 s 出 4 条要点；演示大纲 → 74.6 s；条款抽取 → 65.0 s
  （首次输出 JSON 不合法 → 自动修复重试一次后通过）。
  结构化任务有契约：`extract` 必须是合法 JSON、`outline` 必须有 `# 标题`，
  不合规保存 `.raw.txt` 并失败（`--no-retry` 可关自动修复）；
  失败/未配置 → 退出码 1 且不写输出文件（不拿本地规则冒充 AI）；零 Qt。
  新增 **15 条**测试 + 门禁 `beecmd-ai`。
- `tools/pipelines/build_jobs.py`：把目录变成 `beecmd batch` 任务清单的**流水线模板**，
  支持三种：`md-pdf`（批量转 PDF，可带词元级 verify）、`beshow`（批量转蜜演文稿）、
  `sheet-merge`（多表汇总）。6 条单测 `tests/unit/test_pipeline_jobs.py`；
  实测三模板分别 2/2、2/2、1/1 成功，审计流水落盘（见 `docs/模板-三个自动化流水线.md`）。
- `tools/fidelity_report.py`：保真度**报告生成器**（区别于检查器 `fidelity_corpus.py`）：
  按"已知类别/未知类别"分类差异，逐文件给出文字丢失率、空段落解释与增加项，
  输出 Markdown + JSON；只有未知类别/异常时 exit 1。
  首份报告：7 份真实文档 + 9 份压力语料（其中 1 份 pptx 跳过往返），未知类别 0
  （见 `docs/保真基线-真实7份与压力9份.md`）。

### 说明
- 模板①受限：`.docx` → PDF 仍不支持，只覆盖 Markdown 源；
- 模板③只产出 `.beshow`，`.pptx` 导出仍依赖 GUI/WebEngine；
- 真实语料仍只有 7 份（目标 50 份），需要用户提供脱敏样本。

### 工程
- 门禁总数 43 → **44**（新增 `beecmd-ai`、`i18n-ratchet`）。
- 干净 worktree（只含已跟踪文件 + 7 份真实语料）验证：**44/44 门禁 PASS**、
  **全量 `fidelity+unit` 1461 passed / 4 skipped / 0 failed**（351.9 s），
  补上"干净环境全绿"的基线（此前只在被 `test+files/` 污染的脏工作区跑过）。
- 发行：`BeeOffice-v5.0.14-windows.zip`（224.7 MB，3128 条目，
  sha256 `14789185850ae3856b49fd1913b50c3ec6427c81c8330dcfd287fb3c71b9d3e6`），
  tag `v5.0.14` = `b5b3529`；GUI 安装包按设计**不含** `beecmd`/`tools`。
---
## [5.0.13] - 2026-10-19

**P1 正确性/体验版**：公式引擎兼容 Excel 常用写法、首次打开 DOCX 提速数倍，
并新增无界面 `beecmd merge`（多表汇总）—— 本版包含 v5.0.12 之后的全部改动。

### 新增（CLI `beecmd` v0.2：多表汇总）
- `beecmd merge a.xlsx b.xlsx c.csv -o 汇总.xlsx`：
  - `--mode append`（默认）：按列名纵向追加，并追加「来源文件」列；
    列不一致时取并集、缺列留空；
  - `--mode sheets`：每个输入文件的每个工作表进入同一工作簿（名冲突自动去重）；
  - `batch` 支持 `{"op": "merge", "srcs": [...], "out": "...", "mode": ...}`，
    同样写审计流水；
  - 纯 Python、**零 Qt**（服务器/容器可跑），零 Qt 约束有子进程测试；
  - 新增门禁 `beecmd-merge`（`tests/fidelity/test_beecmd_merge.py`，8 条）。

### 修复
- **公式引擎 Excel 兼容语义**（审计 §3.3 L2/L3）：
  - 条件里的单等号/不等号可用：`=IF(A1=1,…)`、`=IF(A1<>2,…)`、
    `=AND(A1=1,B1=2)`、`=NOT(A1=2)`、`=IFS(A1=1,…)`；
  - 函数结果参与四则运算：`=SUM(A1:A8)/2`、`=SUM(A1:A8)+1`、
    `=SUM()+SUM()` 返回数值（原先返回**公式文本**或**静默 0**）；
  - 括号配对判断：修复 `=SUM(A1:A2)+SUM(B1:B2)` 被贪婪正则误判成
    "一次 SUM 调用"而静默返回 0；
  - 字符串字面量保护：`="A1"`、`="SUM(A1:A4)"` 不再被误当成引用/函数；
  - 错误不再退化成公式文本：函数返回 `#N/A` 等错误值参与运算时给出 `#ERROR`。
- **首次打开 DOCX 性能**（审计 §4.4）：
  - 根因：python-docx 的 `paragraph.style` 每次访问都遍历**全部样式**
    （O(styles)）。5 万字文档 1,090 次调用累计 3.5 s 以上，是首次打开的最大热点。
  - 改法：一次性构建 `styleId → 样式名` 映射 + 直接读 `w:pPr/w:pStyle`，
    并保留 python-docx 的 internal→UI 名称翻译（标题样式识别结果不变）。
  - 实测（离屏、同机、单次冷开）：5 万字 DOCX `import_from_docx` 3.58 s → **0.43 s**，
    `read_docx_extras` 4.91 s → **0.26 s**，端到端首次打开 **5.85 s → 0.83 s**；
    2.6 MB 带图 DOCX 首次打开 **1.79 s → 0.83 s**，热开 **0.63 s → 0.26 s**。
  - 打开流程新增第二阶段提示「正在渲染 Word 文档…」，避免长任务被误判卡死。

### 测试
- 新增 `tests/fidelity/test_formula_excel_compat.py`（26 条）；
  与既有 113 条引擎用例、P0-5 安全回归（注入/边界）一起全部通过（181 条）。
- DOCX 导入/保真相关 176 条测试通过。
- 新增 `tests/fidelity/test_beecmd_merge.py`（8 条）并接入门禁。
- 门禁总数 41 → **42**。

### 说明
- 本版发行包按提交重新构建；`v5.0.12` 只含 P0 止血，本版补齐 P1 与多表汇总。
---
## [5.0.12] - 2026-10-19

**P0 止血版**：修掉审计确认的三条"会丢用户数据 / 会发错包"的红线，
每条都配可复现回归；同时把 5.0.11 之后未提交的审计修复一并入库。

### 修复（用户可感知）
- **关闭主窗口不再静默丢数据**（审计 §4.3 G1，实测缺陷）：
  原 `closeEvent` 只停定时器、存设置、关插件，**不遍历标签做未保存检查** ——
  点 X/Alt+F4 会丢掉最近一次自动保存之后的全部修改（新建未保存文档整份丢失）。
  现在逐个标签询问「保存 / 不保存 / 取消」：
  选保存则落盘后才允许关闭（失败/取消另存为都会中止关闭）；
  选不保存且文档从未保存到文件时，**关闭前写一份草稿**，下次启动可恢复；
  取消则窗口保持打开。
- **自动保存覆盖所有标签**（审计 §4.3 G3）：原先只保存当前标签，
  后台标签的修改既不会自动保存也不会进草稿。现在遍历全部脏标签。
- **主文档保存改为原子写**（审计 §4.3 G2）：蜜写 `.docx`/`.md`、
  蜜算 `.xlsx`（含样式回贴）、DOCX 导出全部先写同目录临时文件，
  再 `os.replace` 原子替换 —— 写到一半崩溃/断电/磁盘满不会把用户原文件
  留成半份 zip；失败时原文件保持不变，临时文件自动清理。
- **旁挂 JSON 原子写**：批注/书签的 `.comments.json`/`.bookmarks.json`
  也改为原子写，避免半份 JSON 让下次打开丢全部批注。

### 工程
- 新增回归：`tests/fidelity/test_close_unsaved_guard.py`（8 条）、
  `tests/fidelity/test_atomic_saves.py`（6 条）；
  并更新 `tests/fidelity/test_drafts.py` 的源码断言以匹配重构。
- `tests/conftest.py` 的 `app` / `app_with_plugins` fixture 默认短路关闭检查
  （避免 pytest-qt 在 teardown 关窗时弹模态框挂住）；需要测真实关闭逻辑的
  用例显式换回 `BeeApp._confirm_close_all_tabs`。
- 版本号 5.0.12；发行包将按本提交重新构建（修复 5.0.11 包早于代码的问题）。

### 说明
- 本版包含 `bafe45f` 之后工作区里的审计修复：工具菜单「恢复未保存的内容…」
  手动入口、语言包补齐该 key、`.pptx` 损失清单补组合形状/SmartArt/超链接目标、
  fontTools rId 冲突修复、打印死变量清理、`error-hygiene` 门禁等。
- 第二阶段（公式引擎 Excel 兼容语义、首次打开 DOCX 性能）不在本版范围内。

---
## [5.0.11] - 2026-10-19

**P0（"能用"）收口版**：把审计与战略里标为"门槛"的几项补齐，每项配可复现门禁。

### 新增
- **打开 `.pptx`**（P0-1）：导入成蜜演文稿 —— 标题/正文层级/演讲者备注/页序保留，
  图片/表格/图表/版式**给出损失清单**；保存必须另存为 `.beshow`，**绝不覆盖原 pptx**。
  CLI 同能力：`beecmd convert x.pptx --to beshow`
- **无界面 CLI `beecmd`**：`convert / info / verify / batch`；表格互转往返零差异、
  `verify` 逐格报差异、`batch` 写审计流水；Markdown → docx/pdf（v0.1）；
  表格路径**零 Qt**（可在服务器跑）
- **崩溃恢复的读取端**（P0-5）：未保存内容写入草稿（`.md`/`.xlsx`/`.beshow` + 元信息），
  下次启动列出并可恢复；保存成功后自动清理；7 天过期清理

### 修复
- **打包版"已加载 0 个插件"**（R11）：冻结感知路径 + 静态清单兜底；
  打包版实测 `共加载 4 个插件`（含 PDF 批注）
- **语言包补全**（P0-6）：`en_US` 缺 53 个 key → 英文界面会冒出中文；两包补齐并加门禁

### 说明
- **P0-2（蜜演真机验证）明确放弃**：没有能运行 QtWebEngine 的机器。
  相关结论停留在 **C 级**，风险 R2 **保持开放并接受**（首次使用请自行点一遍播放/导出）。
- i18n 只补"代码已在用的 key"；界面里硬编码的中文未做全量 i18n 化。
---
## [5.0.10] - 2026-10-16

### 新增
- **AI 设置自动列出本机已装模型**：服务商选「本地 Ollama」时，自动读取
  本机 Ollama 已安装的模型并填入「模型名」（刚 `ollama pull` 完可点
  「刷新本机模型」）。此前预设里写死 `qwen2.5`/`llama3.1`/`gemma2`，
  而用户机器上通常一个都没装 —— 每台新机器第一次点开都会撞
  "模型不存在（HTTP 404）"。现在**装了什么就用什么**；
  若用户填的模型本机没有，会自动换成可用的那个并说明"原「…」本机没有"。

### 说明
- 该能力同时支持两种端点：OpenAI 兼容 `GET /v1/models` 与 Ollama 原生
  `GET /api/tags`（前者不通时自动降级）；两者都拿不到就**如实提示**
  去 `ollama serve` / `ollama pull`，不会编造模型名。
- 本版包含 `[5.0.9]` 的全部修复（含 AI 报错归因：404 现在会读响应体，
  「模型不存在」不再被误报成「接口地址不对」）。
---
## [5.0.9] - 2026-10-16

**面向"真能用"的修复批次**：以审计报告（`BeeOffice-功能真伪审计.md`）为依据，
修掉两大类问题 —— "入口在、实现不通"与"设了就丢"。逐项证据见
`docs/baseline.md`、`docs/交付总结-第1至11批.md` 与 `docs/生产能力评估.md`。

### 修复（用户可感知）
- **快捷键**：蜜写 Ctrl+S、蜜算 Ctrl+Z/Y 原先因"同键歧义"**完全不生效**，现已修
- **数据安全**：蜜算/蜜演关闭标签时会提示未保存；两者都建立了"当前文件 + 保存"
  （蜜演新增 `.beshow` 文稿格式），备份与自动保存才覆盖得到
- **导出 PDF**：改走 Qt 打印路径并按模块分流（原先依赖未打包的 WeasyPrint，必然失败）
- **格式落盘**：蜜算的加粗/数字格式/对齐/合并/批注（含作者）/表格样式/数据验证/
  条件格式/冻结窗格/命名区域/图表/数据透视表，从"只在内存里"变为**写盘 + 读回**
- **图表与透视表**：应用内生成的图表现在会写进工作簿；透视表可保存并**刷新**
- **蜜写**：默认（Markdown）模式下 Ctrl+B/I/U 可用；「分节符」导出为真正的 Word 节；
  「目录」插入渲染结果而非 Markdown 源码；表格列对齐不再被编辑抹掉；
  DOCX 保留超链接与单元格多段落
- **AI 报错归因**：404 现在会读响应体 —— Ollama"模型不存在"不再被误报成"接口地址不对"，
  并给出可照抄的 `ollama pull …` 命令
- **打包**：修复拼写检查技术词白名单未随包分发（`beeoffice/data`）、发布脚本路径错误

### 工程
- 新增 33 项开发门禁（`tools/check_gates.py`），覆盖上述每一项修复
- 全仓未用导入清零
---
## [5.0.8] - 2026-10-11

优化规划**阶段 2**（正确性与体验）与**阶段 3.1**（删除死代码）。
阶段 2 的逐项证据见 `BeeOffice-优化规划.md` 的「阶段 2 进度 / 验收」与
`docs/baseline.md`。

### 变更（阶段 2 摘要）
- **性能**：插件发现由「import 全部 84 个模块」改为只 import 插件候选，
  `discover_plugins()` **2487 ms → 39 ms**，启动到插件可用 **3177 ms → 555 ms**，
  且不再在启动时拉起 pandas / matplotlib / PyMuPDF / QtWebEngine。
- **安全**：云同步与蜜演同步默认只监听回环并加令牌鉴权；移除通配 CORS。
- **数据完整性**：批注/书签保存后能读回（原先重开文档全丢）；拖动排序不再
  删除该页的评论/样式/图片标记；插入的图片不再只留在 `%TEMP%`；
  MD→DOCX 不再丢弃图片与超链接。
- **正确性**：页边距单位统一为 mm；导出动态数字不再显示 0；修复
  `=LOG10(A1)` 被改写为 `=LOH10(B1)`、`$` 绝对引用与反向范围返回 0、
  聚合函数逗号参数返回 0、自然语言 IF 真假同值、**循环引用静默产出不断
  变大的数值**（`=A1+1` 写在 A1：0 → 3 → 6）。
- **资源**：蜜演播放窗口不再每次泄漏一个 QtWebEngine 视图；PPTX 导出不再
  每页重启一次 Chromium；视频封面缓存改为跨进程稳定并自动清理。

### 修复（阶段 3.1 附带发现）
- **云同步**：`app._sync_now()` 的"同步正在进行中"守卫**从未生效**。
  它用 `self._sync_worker.isRunning()` 判断，而 `AsyncTaskManager.run()`
  返回的是 `QRunnable`（`Worker`），**没有 `isRunning()`**；AttributeError
  被宽 `except Exception: pass` 静默吞掉。于是重复点击「立即同步」
  （或自动同步与手动同步叠加）会**并发启动多次上传**。
  现改用显式标记 `_sync_in_progress`（进入前置位、结果/错误回调清除）。

### 移除（阶段 3.1：确认零引用后删除）
- `beeoffice/webdav.py`（WebDAV 设置窗口，无任何生产引用）。
- `beeoffice/plugins/webdav_sync.py`（`WebDAVConfig` 明文密码落盘到
  `~/.beeoffice_webdav.json`；`WebDAVSyncWorker` 仅被上面那个模块引用）。
  **活跃的云同步不受影响**：`app._show_webdav_settings` 走
  `cloud_settings`，`app._sync_now` 走 `cloud_sync/webdav.py`。
- `beeoffice/plugins/git_manager.py`（无调用方，`save_file` 可任意路径写）。
- 死成员：`SheetDataModel.MIN_ROWS`、`ViewMixin._undo/_redo`（菜单实际调用
  `editor.undo()`）、`beeshow._ai_service/_pptx_engine/_font_embedder`
  （只写不读）、`pdf_annotator._note_editor`（创建后隐藏且无引用）、
  `beeshow_pptx_engine` 未使用的 `subprocess`/`tempfile` 导入。
- 手误残留：`beesheet_engine.py` 中一处孤立的续行反斜杠。
- 连同只覆盖死代码的测试 `tests/regression/p0/test_p0_10_webdav_conflict.py`。

### 更正（规划清单中与实际不符的条目）
- `SheetDataModel._real_rows` 与 `beeshow._css_cache/_preloaded_slides` **不是**
  死成员（有真实读写），未删除。
- `ChunkLoader.progress` 在阶段 2 已成为**活信号**（不再"声明了但从不 emit"），
  未删除；`LargeFileLoader.chunk_ready` 被 `test_p0_15` 用作观测通道，保留。
- `beesheet_plugin._generate_chart_fallback` 等 `*_fallback` **确实会被调用**
  （`BeeSheetView` 本身没有 `generate_chart` 方法，回退分支就是实际路径），
  未删除。
- `CommentManager.load_from_file` / `clear` 现已分别是生产路径与测试使用的
  接口，未删除。
- **v5.0.3 记录的「持续集成：新增 `.github/workflows/test.yml`（Windows-only）」
  从未成立** —— 仓库里连 `.github` 目录都不存在，那条以及下面的
  「每次 push / PR 自动运行导入检查、测试、覆盖率」都是空头承诺。
  **v5.0.8 真正加入了 CI**（见下方「持续集成」），但与原描述不同：是三平台矩阵，
  且**没有**接入覆盖率（原因见该节说明）。

### 持续集成（阶段 4.1，本次真正建立）
- 新增 `.github/workflows/test.yml`：三平台矩阵（windows / ubuntu / macos）
  × Python 3.11，跑 `tools/check_imports.py` 与
  `tools/run_tests_isolated.py --quiet`，ruff 结果作为**非阻断**的可见指标
  写入 step summary。
- **为什么不直接 `pytest tests`**：9 个构造 `QWebEngineView` 的测试文件在
  offscreen 下会在**进程退出阶段**原生崩溃（Windows `0x80000003`），
  断言全过但退出码非 0，直接跑会让 CI 长期假红。隔离运行器的退出码只反映
  真实的 failed/error，见 `docs/baseline.md` §6.1。
- **为什么不接覆盖率**：隔离运行把测试拆成 89 个进程，单进程覆盖率无法直接
  聚合（需要 `coverage combine`）。因此当前**没有**覆盖率门槛，
  而不是"有覆盖率"。
- 静态检查现状基线（供后续收紧用）：`ruff check beeoffice` 默认规则
  **1571** 个问题；`--select E722`（裸 `except`）**14** 处。
  注意此前"更正"里写的 15 处是 v5.0.4 时的数字，其中 1 处随
  `plugins/formula_engine.py` 在阶段 1 被删除。

## [5.0.7] - 2026-10-10

安全与数据完整性修复（对应《BeeOffice-优化规划.md》阶段 0 与阶段 1；
源码内注释按规划章节标注为 v5.0.5）。

### 安全
- **蜜算**：封堵公式引擎**跨表引用路径**的任意代码执行。
  `beesheet_engine._eval_sheet_ref` 原本在把跨表引用替换成字面值之后，
  对剩余表达式执行裸 `eval()`；清空 `__builtins__` 并不构成沙箱。实测
  `=S!A1+[c for c in ().__class__.__base__.__subclasses__() ...sqrt(16)`
  可返回 `5.0`。现已改走 AST 白名单求值。
- **蜜算**：删除旧版实例式公式引擎 `plugins/formula_engine.py`（569 行，
  生产代码零引用、仅测试引用，且带第二处未加固的裸 `eval`）。
- **移动端**：服务默认只监听 `127.0.0.1`（原为 `0.0.0.0`，等于把当前打开的
  全部文档暴露给整个局域网）；`/api/*` 需一次性令牌；移除通配
  `Access-Control-Allow-Origin`；校验 `Host` 头；首页拆出外部脚本并下发
  `script-src 'self'` 的 CSP。
- **蜜演**：远程同步服务默认回环；HTTP 接口与 WebSocket 握手均需令牌并校验
  `Origin`；移除三处通配 CORS 头；显式拒绝 `HEAD`。

### 修复
- **设置**：`AppSettings.save()` 改为原子写。原实现先以 `"w"` 打开（立即截断
  文件）再在 `json.dump` 的参数位置构造字典，任何构造期异常都会把用户的
  `~/.beeoffice_settings.json` 留成 0 字节空文件，并被宽 `except` 静默吞掉。
- **蜜写**：打开 `.docx` 后保存不再静默覆盖原文件——原文件会被保真度很低的
  重建替换（丢失超链接、列表编号、页眉页脚、脚注、东亚字体等）。现在必须先
  确认，并支持覆盖前自动 `.bak` 备份。
- **蜜演**：修复「导出 PNG 图片序列」永不产出文件却提示成功——原实现对
  `QWebEnginePage` 调用只存在于 `QWidget` 的 `grab()`，异常被吞掉后仍在
  `finally` 里报成功。
- **蜜演**：修复表格「插入列」参数顺序写反（`setItem(insert_at, r, ...)`
  实为 `setItem(row, column, item)`）而覆盖已有单元格；修复「编辑已有表格」
  把两张表格之间及表格之后的正文整体删除。
- **蜜演**：应用版式前增加确认并保存历史快照（原先会静默清空整份文档，
  无确认、无撤销、不限于当前页）。
- **蜜演**：同步演示补上 `set_slides_html()`——此前该方法从未被调用，
  观众端只能看到页码跳动，画面永远是空的。
- **PDF 批注**：新增 `closeEvent` 保护未保存的批注（该类此前完全没有
  `closeEvent`，关窗即丢弃）；旁挂文件容错（缺一个字段不再让整份批注都读不
  出来）+ 格式版本号；保存改原子写并给出失败提示；烧录时应用用户所选颜色；
  缩放增加上下限（原先长按滚轮可放大到 16 倍而崩溃）。
- **蜜算**：自动备份从 `~/.beeoffice_backups/`（用户主目录、跨文档共享、
  关文档与程序都不清理）移到应用数据目录下的会话子目录，关闭文档时清理；
  失败不再 `except: pass`。
- **蜜算**：修正 `math_funcs` 调用参数，`ABS` / `SQRT` / `PI` / `RAND`
  恢复可用（此前因参数个数不匹配，它们在 UI 函数参考表里存在却必然报错）。

### 更正（此前版本的记录与事实不符）
- v5.0.1 记录「修复公式引擎 `IF`/`AND`/`OR`/`NOT`/`IFS` 可执行任意 Python
  代码的安全漏洞（改用 AST 白名单求值）」——该修复只覆盖了 `_safe_eval`
  分支；`_eval_sheet_ref` 的裸 `eval` 一直保留到本次才封堵。
- v5.0.0 记录「去除所有 `except: pass`，改为 `logging.error` 记录」——
  实测仍有 15 处裸 `except:`。
- v5.0.0 在「安全」标题下列出「Base64 编码：WebDAV 密码、云存储 Token 编码
  存储」——Base64 是编码不是加密，不提供机密性；且当时未对文件权限做加固。
- v5.0.0 记录「修复 `_check_conflict` 定义了但从未调用，双向同步会覆盖新文件」
  ——`_check_conflict` 确实被调用了，但它 fail-open：日期解析失败返回
  `unknown` 后照常覆盖。（**v5.0.8 更新**：该函数随死模块
  `plugins/webdav_sync.py` 一并删除——它只被同样无引用的 `beeoffice/webdav.py`
  使用，不在任何活跃的云同步路径上。活跃路径 `app._sync_now` →
  `cloud.get_cloud_storage()` 目前**没有冲突检测**，这一点见分析报告 §4.5/§4.6
  与优化规划新增的 §4.5。）
- v5.0.6 记录的「测试数：483 → 581」「覆盖率：34.54% → 37.30%」与实际不符
  （实际收集 710+；且当时 `tests/unit/test_settings.py` 有 4 个用例长期失败，
  根因正是上面那条 `save()` 缺陷）。本文件原先还把修改这些数字的 Python
  脚本粘贴在标题下方，已删除。

## [5.0.6] - 2026-09-17

### 修复
- 蜜算公式引擎 `_eval` 支持算术表达式
  - `=A1+A2` 现在返回数值而非字符串
  - `=IFERROR(1/A1, SUM(...))` 正确处理除零
  - `=IFS(A1>10, ..., A1+100)` 分支支持算术
- 蜜演插件 `edit_notes` fallback 修正属性名
  - `current_index` → `_current_slide`
  - `speaker_notes` → `_speaker_notes`
- 10 个 `beewrite_*.py` 文件头注释拼写修正

### 测试
- 目录分层：`unit/` / `qt/` / `regression/p0|p1|v5/` / `smoke/` / `helpers/`
- 测试数：483 → 513（+30）
- 覆盖率：34.54% → 35.06%
- 关键模块覆盖率提升：
  - `plugin_manager`: 56% → 80%
  - `cloud`: 14% → 76%
  - `tab_manager`: 38% → 44%
- 新增 4 个回归测试：P0-8、P1-11
- P0-8 测试断言改用 AST，避免误伤 docstring
## [5.0.4] - 2026-09-16

### 优化

- **蜜写**：图片段落导出为 DOCX 时居中对齐 + 段前段后各 12pt
  - 避免图片紧贴表格，视觉上更独立
  - 修复 WPS 打开时图片段落紧贴表格的观感问题
- **蜜写**：图片宽度上限从 600px 提升到 720px
  - 长条图片（如诗词截图 1544×152）缩放后高度更合理，
    可读性更好（高度从 59px 提升到 71px）
  - 使图片宽度接近 A4 页面可用宽度
- **蜜写**：图片插入后所在段落自动居中
  - Qt 编辑器和导出 DOCX 的居中效果一致

### 变更

- `RichTextEditor._insert_image_by_path` 图片插入后应用段落居中
- `RichTextEditor._IMAGE_MAX_WIDTH` 从 600 改为 720
- `ExportMixin._rich_to_docx` 图片段落特殊处理：
  · 图片所在段落居中对齐
  · 段前段后各留 12pt 间距
  · 图片段落不再叠加 rich editor 的 block format

### 涉及文件

- `beeoffice/plugins/beewrite_rich_editor.py`
- `beeoffice/plugins/beewrite_export_mixin.py`
- `beeoffice/__version__.py`

## [5.0.3] - 2026-09-16

### 修复

- **蜜写**：修复打开含图片的 DOCX 时图片丢失的问题
  - `app._open_docx_file.on_result` 调用顺序调整：
    先 `set_current_file_path`（同步目录），
    再 `set_content` / `_switch_mode`（加载内容并解析图片）
  - 原因：`_switch_mode("rich_text")` 内部调 `set_markdown()`，
    解析 `![](相对路径)` 时 `rich_editor._current_file_dir`
    还未同步，导致图片找不到而被替换为 `[图片缺失]` 占位文字

### 涉及文件

- `beeoffice/app.py`
## [5.0.2] - 2026-09-16

### 修复

- **蜜写**：修复图片在富文本 ↔ Markdown 往返中丢失的问题
  - `RichTextEditor.to_markdown()` 现在会识别图片 fragment 并转为
    `![](path)` 语法（图文混排按 fragment 顺序拼接）
  - `RichTextEditor.set_markdown()` 现在会解析 `![](path)` 语法
    并从路径加载图片（相对路径相对于 `_current_file_dir` 解析）
  - `import_from_docx()` 现在会提取 DOCX 内嵌图片到 `<name>_media/` 目录
    - 支持 DrawingML（现代 Word）：`<w:drawing>/<a:blip r:embed="rIdX"/>`
    - 支持 VML（旧版 Word）：`<w:pict>/<v:imagedata r:id="rIdX"/>`
    - 图片不存在时插入占位文字 `[图片缺失: path]`，避免静默丢失
  - 打开 / 保存文档时同步 `_current_file_dir`：
    - 粘贴 / 插入的图片存到文档同目录的 `media/` 而非 `~/media/`
  - 从富文本切到 Markdown 时，含图片会弹确认提示，
    避免用户误以为图片丢失

### 变更

- `RichTextEditor` 新增 3 个方法：
  - `_block_has_image`（检查 block 是否含图片 fragment）
  - `_block_with_images_to_md`（图文混排 block → Markdown）
  - `_insert_image_by_path`（按路径加载并插入图片）
- `BeeWriteEditor` 新增 `set_current_file_path` 方法
- `ExportMixin._write_md` / `_write_docx` 保存成功后调用 `set_current_file_path`
- `ModeMixin` 新增 `_document_has_images` 方法
- `app._open_text_file` / `app._open_docx_file` 打开文档后调用
  `set_current_file_path`
- `bee_export` 新增 `_extract_para_images` 辅助函数

### 涉及文件

- `beeoffice/plugins/beewrite_rich_editor.py`
- `beeoffice/plugins/bee_export.py`
- `beeoffice/plugins/beewrite.py`
- `beeoffice/plugins/beewrite_export_mixin.py`
- `beeoffice/plugins/beewrite_mode_mixin.py`
- `beeoffice/app.py`

---

## [5.0.1] - 2026-09-16

累积发布，包含 v5.0.0 之后的所有 P0 / P1 修复。

### 修复

#### 严重问题（P0）

- **蜜算**：修复「排序」「查找替换」因缺少 `QFormLayout` / `QCheckBox` 导入导致点击即崩溃
- **蜜算**：修复 `SUMIFS` / `AVERAGEIFS` 条件范围行偏移错误，多条件求和结果不正确
- **蜜算**：修复公式引擎 `IF` / `AND` / `OR` / `NOT` / `IFS` 可执行任意 Python 代码的安全漏洞（改用 AST 白名单求值）
- **蜜算**：大文件分块加载新增取消按钮，加载过程中可中断
- **蜜演**：修复全屏播放时所有键盘快捷键失效（新增 `_PlayWindow` 转发键盘事件）
- **蜜演**：修复导出 PDF / 图片序列时 `QWebEngineView` 被 GC 导致随机失败
- **蜜演**：修复插件「从头播放」失效（属性名与实际不符）
- **蜜演**：修复拖拽重排序幻灯片时 Markdown 标题 `#` 丢失
- **蜜写**：修复命令面板「插入目录」始终提示不支持（方法名 `_generate_toc` → `_insert_toc`）
- **蜜写**：修复 AI 续写 / 润色 / 总结在富文本模式下操作错误控件
- **应用**：修复保存多个文件时误弹「文件已被外部修改」对话框（`_is_self_save` 单槽记录 → 多文件时间戳 dict）
- **应用**：修复快捷键帮助文档与实际绑定大面积不符（`Ctrl+W` 误写为新建 Word，实际是关闭标签）
- **移动端**：删除 `os.chdir()` 调用，避免劫持整个进程的工作目录
- **标签管理**：修复 `_close_other_tabs` 索引漂移导致保留标签被误关
- **标签管理**：修复分屏容器被标记为「有未保存修改」导致关闭时误弹提示

#### 一般问题（P1）

- **蜜算**：修复列名超过 26 列时出现 `[` `\` `]` 等乱码（改用 `col_index_to_name`）
- **蜜写**：修复变量面板刷新后重置用户当前选择的数据源
- **蜜写**：修复数据绑定 `render()` 第二返回值恒为空列表（改为返回未解析变量列表）
- **蜜写**：修复 10 个 `beewrite_*` 文件的头注释拼写错误（`bewrite_` → `beewrite_`）
- **蜜演**：修复无备注时点「演讲者模式」无任何反应（改为显示引导提示）
- **PDF**：修复撤销批注不区分页码，会误删其他页的批注
- **命令面板**：蜜演识别改用 `_slides_html + _start_play` 双特征，避免同名方法误判
- **插件市场**：修复 `Qt.Checked.value` 在 PySide6 6.x 上不存在导致状态切换失效
- **设置**：修复旧版 `webdav_pass` 迁移到 `cloud_config` 时的双重解码问题（用 `__decoded__` 标记）
- **云同步**：修复 `_check_conflict` 定义了但从未调用，双向同步会覆盖新文件
- **错误处理**：修复 `friendly_errors` 第一个 pattern 贪婪匹配导致跨行误捕获
- **移动端**：修复多实例共享同一临时目录导致 `index.html` 互相覆盖

### 测试

- 新增 20+ 个回归测试文件（`tests/test_p0_regression/`、`tests/test_p2_regression/`）
- 补齐蜜演播放、移动端 API、命令面板测试
- 修复 `beewrite_editor` fixture 未触发 `closeEvent` 导致的跨测试污染
- `app` fixture 改为轻量，屏蔽插件加载 / 弹窗 / 同步，测试套件耗时降低 30%+
- 测试日志屏蔽预期 ERROR，`pytest.log` 不再被污染
- 收紧 `test_empty_formula` 等宽断言
- 引入 `pytest-cov`，覆盖率报告输出 `coverage.xml`

### 持续集成

- 新增 `.github/workflows/test.yml`（Windows-only）
- 每次 push / PR 自动运行导入检查、测试、覆盖率

### 变更

- `shortcuts.py` 与实际快捷键绑定对齐（详见文件内注释）
- `command_palette.py` 蜜演识别特征调整
- `mobile.py` `MobileServer.temp_dir` 每次实例化使用独立子目录
- `requirements.txt`：合并两份不一致的文件；PyMuPDF 由可选升级为必需

---

## [5.0.0] - 2026-09-10

### 新增

#### 核心功能
- **公式引擎**：支持 SUM、AVERAGE、COUNT、COUNTA、COUNTIF、MAX、MIN、IF、AND、OR、VLOOKUP、CONCATENATE、LEFT、RIGHT、LEN、UPPER、LOWER、ROUND、ABS、INT、MOD、TODAY、NOW 等 20+ 函数
- **自然语言生成公式**：支持"求和A1到A10"、"平均值B列"、"筛选大于100的行"、"如果A1大于10就显示'高'"等中文指令
- **AI 辅助写作**：续写、润色、总结、关键词提取、扩写
- **图表生成**：折线图、柱状图、饼图、散点图
- **大文件分块加载**：支持 100MB+ CSV/Excel 文件
- **数据清洗**：去除重复行、空值处理

#### 蜜演增强
- **动画效果**：淡入、滑入、缩放
- **演讲者备注**：每张幻灯片独立备注
- **排练计时**：实时计时显示

#### 蜜写增强
- **目录自动生成**：根据 Markdown 标题生成目录
- **代码高亮**：支持 fenced code 语法高亮
- **任务列表**：支持 `- [ ]` 复选框渲染

#### 云同步
- **多云存储支持**：WebDAV、OneDrive、Google Drive
- **统一接口**：通过 `CloudStorage` 抽象基类实现
- **同步进度**：实时显示百分比和当前文件
- **失败重试**：最多重试 3 次
- **统一入口**：`cloud_settings.py` 集中配置

#### 移动端
- **响应式 Web 界面**：单页应用风格
- **REST API**：`/api/docs` 和 `/api/view/<id>`
- **动态端口分配**：从 8888 自动探测可用端口
- **多类型文档渲染**：蜜写（Markdown）、蜜算（DataFrame）、纯文本

#### 插件系统
- **插件基类**：`Plugin` 定义统一接口
- **插件管理器**：`PluginManager` 自动发现与加载
- **插件市场**：安装、卸载、启用/禁用
- **内置插件包装**：蜜写、蜜算、蜜演、PDF 批注

#### 界面与体验
- **命令面板**：支持上下文推荐、最近命令、上下键导航
- **标签拖拽合并**：跨窗口拖动合并标签
- **未保存状态标记**：标签前显示 ●
- **自动保存**：每 5 分钟自动保存
- **文件监视**：外部修改提示重新加载
- **快捷键扩展**：Ctrl+W、Ctrl+Tab、Ctrl+Shift+Tab 等

#### 国际化
- **中英文支持**：`zh_CN.json` 和 `en_US.json`
- **统一 `tr()` 函数**：支持默认值回退
- **语言切换菜单**：视图 → 语言

#### 主题
- **深色/浅色模式**
- **4 种强调色**：琥珀、海洋、森林、日落

### 优化

#### 性能
- **异步任务**：`AsyncTaskManager` 基于 QThreadPool，将耗时操作移至后台
- **延迟加载**：插件和重型模块按需加载
- **防抖预览**：蜜写编辑器 200ms 防抖，避免频繁渲染
- **线程池限制**：最大线程数限制为默认值的一半

#### 架构
- **模块拆分**：`app.py` 从 500+ 行拆分为多个职责单一模块
  - `menus.py` — 菜单构建
  - `commands.py` — 命令注册
  - `webdav.py` — WebDAV 入口
  - `cloud_settings.py` — 云存储设置
  - `mobile.py` — HTTP 服务
  - `templates.py` — 模板管理
  - `async_task.py` — 异步任务
  - `plugin_base.py` / `plugin_manager.py` — 插件系统
- **云存储抽象**：`cloud_sync/` 子包，统一接口
- **资源路径解析**：`utils.get_resource_path()` 兼容打包和源码运行

#### 稳定性
- **异常处理**：去除所有 `except: pass`，改为 `logging.error` 记录
- **崩溃处理**：`CrashHandler` 增强，支持无 GUI 环境
- **日志清理**：启动时清理旧崩溃日志，保留最近 20 份
- **端口占用**：移动端服务器使用单例模式和动态端口
- **文件操作**：异步化文件打开、导出、批量转换

#### 安全
- **Base64 编码**：WebDAV 密码、云存储 Token 编码存储
- **URL 校验**：WebDAV 地址强制以 `http://` 或 `https://` 开头
- **设置版本迁移**：`AppSettings.VERSION` 支持旧版本自动迁移

### 修复

- 修复命令面板因焦点丢失导致意外关闭的问题
- 修复 `Ctrl+F` 在非编辑控件上崩溃的问题
- 修复移动端服务器重复占用端口的问题
- 修复分屏后控件显示异常的问题
- 修复蜜写保存后未保存标记不消失的问题
- 修复语言包加载失败导致崩溃的问题
- 修复设置文件损坏导致启动失败的问题
- 修复 `window_size` 保存为 tuple 导致 JSON 序列化失败的问题

### 测试

- 引入 `pytest` 和 `pytest-qt`
- 新增测试文件：
  - `tests/test_bee_export.py` — 导出/导入功能
  - `tests/test_settings.py` — 设置读写
  - `tests/test_app.py` — 主窗口 UI
  - `tests/test_formula_engine.py` — 公式引擎
  - `tests/test_nl_formula.py` — 自然语言解析
  - `tests/test_ai_assist.py` — AI 辅助
- 添加 `pytest.ini` 配置
- 添加 `requirements-dev.txt`

### 打包

- 提供 `beeoffice.spec` PyInstaller 打包配置
- 提供 `build.py` 一键打包脚本
- 提供 `build_release.py` 发布包构建脚本
- 支持 Windows、macOS、Linux 三平台
- 生成 ZIP 包及 SHA-256 校验文件

### 文档

- 完善 `README.md`：功能特性、快速开始、使用指南、快捷键、插件系统、云同步、移动端、开发指南、测试、打包、FAQ、贡献指南
- 新增 `CHANGELOG.md`：本文件
- 补充开发文档：插件开发规范

### 变更

- **`app.py` 大幅精简**：原有功能拆分到独立模块
- **`settings.py` 结构调整**：新增 `cloud_*` 字段，兼容旧 `webdav_*` 字段
- **`webdav_sync.py` 职责调整**：仅保留 WebDAV 配置和同步 worker，通用云存储在 `cloud_settings.py`
- **`command_palette.py` 关闭逻辑重写**：使用事件过滤器 + 延迟关闭

### 移除

- 移除 `except: pass` 的静默异常处理
- 移除 `settings.py` 中直接明文存储密码的方式

---

## [4.0.0] - 2025-XX-XX

### 新增

- 命令面板（Ctrl+Shift+P）
- WebDAV 云同步
- 蜜演幻灯片模块
- 主题切换（深色/浅色）
- 4 种强调色
- 国际化框架
- 崩溃处理机制
- 内存监控

### 优化

- 启动速度优化
- 高 DPI 适配
- 中文路径兼容
- macOS 字体回退

### 修复

- 修复启动时偶发崩溃
- 修复菜单项显示不全

---

## [3.0.0] - 2025-XX-XX

### 新增

- 蜜算表格模块
- CSV/Excel 导入导出
- 模板管理
- 蜜写 Markdown 编辑器
- 实时预览

### 优化

- 标签页管理
- 快捷键系统
- 状态栏消息

---

## [2.0.0] - 2025-XX-XX

### 新增

- 蜜写基础编辑器
- 导出 DOCX / PDF / HTML
- 查找替换

### 优化

- 界面美化
- 主题样式

---

## [1.0.0] - 2025-XX-XX

### 新增

- 项目初始化
- 主窗口框架
- 基础文件操作
- 简单文本编辑

---

## 版本命名规范

- **主版本号（Major）**：不兼容的 API 变更
- **次版本号（Minor）**：向后兼容的功能新增
- **修订号（Patch）**：向后兼容的问题修复

## 变更类型

- **新增（Added）**：新功能
- **变更（Changed）**：对现有功能的变更
- **弃用（Deprecated）**：即将移除的功能
- **移除（Removed）**：已移除的功能
- **修复（Fixed）**：Bug 修复
- **安全（Security）**：安全相关变更

---

[5.0.2]: https://github.com/TomJerryGit/beeoffice/releases/tag/v5.0.2
[5.0.1]: https://github.com/TomJerryGit/beeoffice/releases/tag/v5.0.1
[5.0.0]: https://github.com/TomJerryGit/beeoffice/releases/tag/v5.0.0
[4.0.0]: https://github.com/TomJerryGit/beeoffice/releases/tag/v4.0.0
[3.0.0]: https://github.com/TomJerryGit/beeoffice/releases/tag/v3.0.0
[2.0.0]: https://github.com/TomJerryGit/beeoffice/releases/tag/v2.0.0
[1.0.0]: https://github.com/TomJerryGit/beeoffice/releases/tag/v1.0.0