# 蜜蜂办公 BeeOffice 全面分析报告

> 分析对象：`D:\beeofficeV`（BeeOffice / 蜜蜂办公）
> 分析方式：静态源码审阅（逐文件阅读 + grep 交叉验证 + 只读行数统计），未运行 GUI
> 分析范围：`beeoffice/` 118 个源文件、`tests/` 77 个文件、构建脚本与文档；`backup/` 与 `__pycache__` 不计入
> 分析时间：2026-10-17

---

## 0. 结论摘要

BeeOffice 是一个**用 PySide6 从零手写的桌面办公套件**，同时提供文字（蜜写）、表格（蜜算）、演示（蜜演）、PDF 批注四个模块，外加云同步、移动端 Web 访问、插件系统、命令面板、主题与国际化。

它的**代码量很惊人**：`beeoffice/` 下 118 个 Python 文件、42,332 行、115 个类、1,320 个函数。功能表看起来可以对标 WPS 的一整条产品线。

但它的**完成度与代码量严重不匹配**。核心结论三句话：

1. **架构清晰、工程骨架完整**——分层、Mixin 拆分、插件基类、异步任务、崩溃处理、设置迁移、打包脚本、测试分层，这些"工程化动作"都做了，且做得比多数个人项目规范。
2. **功能是"接线完成、闭环未验收"**——大量特性只连了 UI 入口，内部实现是占位或半成品：AI 是随机语料、宏只有菜单、激光笔只有状态位、云同步不同步文档、插件市场没有市场。
3. **存在若干会在真实使用中立刻暴露的硬伤**——表格公式连 `=IF(A1=1,…)` 都算不出来、md 模式导出 DOCX 丢图、批注/书签只写不读、PDF 导出假成功、后台线程直接改 Qt 模型、跨表引用分支留了一个可绕过的 `eval`。

**综合评分：4.4 / 10**（可演示，不足交付）。

| 维度 | 评分 | 一句话 |
|---|---|---|
| 功能覆盖（广度） | 8.0 | 对标清单几乎铺满 |
| 功能可用性（深度） | 3.0 | 大量占位；连 `=IF(A1=1,…)` 都算不出来 |
| 架构设计 | 6.5 | 分层正确，但 Mixin 上帝类 |
| 代码质量 | 5.0 | 注释详实，但重复、超长函数、吞异常多 |
| 稳定性 | 3.5 | 异步/线程/生命周期问题集中 |
| 安全性 | 3.0 | eval 残留、本地服务无鉴权、密钥可逆存储 |
| 测试与工程化 | 5.5 | 测试文件多、覆盖仅 35.9%、无 CI、无版本控制 |
| 文档与一致性 | 4.0 | 文档详实但与实现脱节，版本号四处不一致 |

---

## 1. 项目概览

### 1.1 定位与形态

- **形态**：Windows 优先的桌面 GUI 应用（PyInstaller onedir 打包），同时支持 macOS / Linux。
- **技术栈**：Python 3.9+、PySide6（Qt6）、pandas / numpy、python-docx、python-pptx、PyMuPDF、matplotlib、markdown、webdavclient3。
- **入口**：`beeoffice/main.py` → `BeeApp`（`beeoffice/app.py`，1,414 行）。
- **许可**：README 声明 MIT，但**仓库根目录没有 LICENSE 文件**。

### 1.2 规模量化（实测）

| 指标 | 数值 |
|---|---|
| `beeoffice/` Python 文件 | 118 |
| `beeoffice/` 总行数 | 42,332（空行 5,386） |
| 类 / 函数 | 115 / 1,320 |
| `tests/` 文件 | 77（其中 `test_*.py` 64 个） |
| `tests/` 行数 | 8,375 |
| 语句覆盖率（coverage.xml） | 7,613 / 21,231 = **35.86%** |
| 最大文件 | `beesheet_engine.py` 1,620 行 |

子系统行数分布（近似）：

```
蜜算 BeeSheet   ≈  9,100 行（19 文件，公式引擎 + 4 大 Mixin + 模型 + 载入器）
蜜写 BeeWrite   ≈ 12,700 行（25 文件 + 5 共享模块）
蜜演 BeeShow    ≈ 11,800 行（27 文件）
核心 shell      ≈  4,000 行（app/menus/tab_manager/commands/mobile/cloud…）
```

### 1.3 版本状态：四个数字互相矛盾

| 位置 | 声称版本 |
|---|---|
| `beeoffice/__version__.py` | **5.0.4** |
| `CHANGELOG.md` 顶部条目 | **5.0.6**（2026-09-17） |
| `README.md` 徽章 | **5.0.2** |
| `main.py` 启动打印 | "v5.0"（硬编码） |
| `settings.py` / `requirements.txt` 注释 | 已在讨论 **v5.1** 的任务 |

`CHANGELOG` 的 5.0.6 条目里甚至直接粘进了一段 Python 脚本源码（第 10–22 行），本该执行它来改写覆盖率数字——说明这个发布条目是**人工误操作**留下的。同一段落里"测试数 483 → 513（+30）"与"483 → 581（+98）"并存，覆盖率同时写着 35.06%、37.30%，而实测是 35.86%。

> 这不是笔误，是**没有单一版本来源、没有发布检查**的症状，后面会反复出现同类问题。

---

## 2. 架构解剖

### 2.1 分层

```
main.py                 进程入口：日志、崩溃钩子、HighDPI、locale、延时导入
  └─ app.py BeeApp      QMainWindow：标签、文件监视、自动保存、命令、云同步、移动端
       ├─ tab_manager   标签容器（未保存标记、拖拽、分屏、右键菜单）
       ├─ menus.py      菜单构建（428 行）
       ├─ commands.py   命令面板注册（内置 30 条）
       ├─ settings.py   设置 + 版本迁移 + Base64 可逆编码
       ├─ theme.py / i18n.py / shortcuts.py / utils.py
       ├─ plugin_manager.py / plugin_base.py
       ├─ cloud.py + cloud_sync/{base,webdav,onedrive,googledrive}
       ├─ mobile.py     局域网 HTTP 服务
       ├─ async_task.py QThreadPool 封装
       └─ plugins/      四大编辑器 + 30 余个支撑模块
```

分层本身是**合理**的：`app.py` 从 500 行拆分出 menus/commands/webdav/mobile/templates/async_task，`cloud_sync/` 用 ABC 抽象云存储，`utils.get_resource_path()` 兼容打包与源码运行。这些是成熟的工程习惯。

### 2.2 插件系统的真相

`PluginManager.discover_plugins()` 用 `pkgutil.iter_modules` 遍历 `beeoffice/plugins/`，**对目录下每一个模块执行 `importlib.import_module`**（`plugin_manager.py:36-45`）。

后果有三层：

1. **所谓的"延迟加载"只是推迟 50 毫秒**。`app.py:153` 用 `QTimer.singleShot(50, self._lazy_load_modules)`，50ms 后一次性 import `plugins/` 下的**全部 85 个模块**。此时 `beesheet_engine.py` 会在模块级 `import pandas, numpy`（12 个模块如此）、`pdf_annotator.py` 会 `import fitz`——也就是说**主窗口刚显示就被同步阻塞数秒**，用户看到的是"窗口出来了但点不动"。
2. **Mixin 文件和工具模块也被当成插件导入**，`beewrite_rich_editor`、`beesheet_model`、`formula_engine` 等等只是被 import，不是插件。真正的 `Plugin` 子类只有 4 个（蜜写/蜜算/蜜演/PDF 的包装器）。
3. **`load_plugins()` 几乎什么都不做**——只调用 `on_load()` 打日志，注释里自己也承认"这里不直接注册"。插件生命周期其实是空的。

### 2.3 Mixin 组合：能力来源，也是"上帝类"的成因

四个主视图全部是"多 Mixin + QWidget"：

| 视图 | Mixin 数 | 主文件行数 |
|---|---|---|
| `BeeWriteEditor` | 10 | 626 |
| `BeeSheetView` | 8 | 1,078 |
| `BeeShowView` | 14 | 260 |

Mixin 之间**没有接口契约**，靠 `self.rich_editor` / `self._edit_mode` / `self.editor` 这类隐式属性名互相探测，大量 `hasattr()` 分支。这类设计的代价在本次审阅中反复出现：**同一个状态被 3~5 个 Mixin 各自维护，改一处必然漏三处**。

`__init__` 里集中初始化 25 个以上字段（`BeeShowView`）、十几个 dict（`BeeSheetView`），任何一个 Mixin 都能读写全部状态——封装边界已经不存在。

### 2.4 全局状态与单例泛滥

- `Theme`、`I18nManager` 用 `__new__` 做单例；
- `cloud.py` 用模块级 `_cloud_storage_instance`；
- `AsyncTaskManager._pool` 是类属性；
- `beewrite_utils.FORMAT_PAINTER` 是**全局可变**格式刷，跨标签页共享（A 文档复制格式会影响 B 文档）；
- `FormulaEngine._error_trace` 是类变量字典，跨实例累计；
- `AppSettings()` 在 `cloud.py`、`cloud_settings.py`、`app.py` 里被反复 `new`，每次都会重新 `load()` 读盘。

---

## 3. 子系统评估

### 3.1 蜜写 BeeWrite（Word / Markdown 编辑器）

**规模**：25 个 `beewrite_*` 模块 10,542 行 + 5 个共享模块 2,138 行，约 390 个方法。

**设计**：双模型——`QPlainTextEdit`（Markdown 源）与 `RichTextEditor`（QTextDocument 富文本）。切换模式时 md→rich 靠 `set_markdown()` 重新解析，rich→md 靠 `to_markdown()` 重新序列化。

**根本性缺陷：md ↔ 富文本往返是有损且不可逆的。**

- 引用块：重建时 `setLeftMargin(20)`（`beewrite_rich_editor.py:804`），回写判定阈值是 `>30`（同文件 :527）——**引用永远识别不回来**；同时正文前缀 `"▎ "` 与 `"> "` 叠加，来回切换会累积或丢失标记。
- 超链接：md→rich 只保留文字染色（:867-872），回写时没有 `[]()`，URL 永久丢失。
- 表格：`split` 后 `if c.strip()` 过滤空单元格（:719、:748），`| a |  | c |` 会变成 2 列，**数据整体左移**。

**导出链路有两套，且都不完整**：

| 路径 | 实现 | 致命问题 |
|---|---|---|
| md 模式 → DOCX | md → python-markdown → BeautifulSoup → python-docx（`bee_export.py:226-256`） | `_write_element` **没有 `<img>` 分支**（:265-346），图片全部静默丢失 |
| 富文本模式 → DOCX | 直接遍历 QTextBlock/fragment（`beewrite_export_mixin.py:804-932`） | 图片、表格可用，但页眉页脚被写成可见文本 |

**持久化只写不读**：批注与书签各有一套 `save_to_file` / `load_from_file`（`beewrite_comment.py:88/98`、`beewrite_bookmark.py:71/81`），但全仓库**只有 `save_to_file` 的调用点**（`beewrite_export_mixin.py:208/215`），没有任何地方调用 `load_from_file`。也就是说：**保存后再打开文档，批注和书签全部消失**。

**其他确认问题**：

- 页眉/页脚写的是 `<!-- header: xxx -->` 注释文本（`beewrite_doc_mixin.py:75,88`），全仓无人解析；富文本编辑器里它就是一行可见的 HTML 注释。
- `export_html` 命令已注册（`beewrite_plugin.py:150-159`），但 `BeeWriteEditor` 根本没有这个方法——点"导出 HTML"永远提示不支持。
- 每敲一个键都触发**全文档 Markdown 序列化**（`textChanged → _update_status_bar → content() → to_markdown()`），且同一个 `textChanged` 挂了 3 个槽（`beewrite.py:268-274`）。
- 所有 DOCX 导入/导出、PDF（WeasyPrint）、`pd.read_csv` 都在 UI 线程执行，`beewrite/` 全目录 **0 处 QThread**。
- `save_as()` 先把 `_current_file_path` 置 `None` 再弹对话框（`beewrite_export_mixin.py:131`），用户一按取消就丢掉当前路径，之后图片基准目录退化到 `Path.home()`。

**AI 辅助名不副实**：`ai_assist.py` 是纯规则实现——"续写"从 12 条硬编码语料随机取（:20-33、:74、:79-87），"润色"是 16 组同义词替换（:106-111），"总结"按句子长度取最长的 3 句。`settings.ai_api_key / ai_api_base / ai_model` 定义了却**从未被蜜写使用**。而且 `_ai_continue` 用 `result.startswith(context)` 判断（`beewrite_ai_mixin.py:61-66`），当上下文末尾没有句号时，原 200 字上下文会被**重复插入一份**。

### 3.2 蜜算 BeeSheet（电子表格 + 公式引擎）

**规模**：19 个文件约 9,075 行——`beesheet_engine.py` 1,620、`beesheet_data_mixin.py` 1,386、`beesheet.py` 1,078、`formula_engine.py` 649（死代码）、8 个 Mixin 与其余支撑模块。

**公式引擎**（`beesheet_engine.py`，1,620 行的单类 `FormulaEngine`）：

- 函数覆盖是**实打实的**：注册表（`:198-246`）加数学别名共 **111 个函数**，含 XLOOKUP/XMATCH/LET/SWITCH/MAXIFS/PMT/IRR/NPV 这类高阶函数，确实超过 README 声称的"80+"。
- 但 UI 的"函数参考表"只列了 **86 项**（`beesheet_ui_mixin.py:59-146`），LET/SWITCH/XMATCH/MAXIFS/IS* 等 15 个函数在界面上**不可发现**——只有读过源码的人才知道能用。
- 解析方式是**正则 + AST 混合**，不是词法/语法分析器：整串先匹配 `^(\w+)\((.*)\)$`（:62），参数按顶层逗号切分后递归。副作用是**运算符沿用 Python 语义而非 Excel 语义**。
- **没有依赖图、没有循环引用检测**。全仓找不到 cycle/dependency 相关代码；在 A1 里写 `=A1+1` 不会报"循环引用"，只会读到上一轮的值。
- **重算不是全量，而是"只算手工录入过的格"**：`_recalc_formulas(max_rounds=3)` 只遍历 `_formula_cells`（本会话通过公式栏录入的），每轮全算、最多 3 轮；结果**只写回数字**（:572），文本型结果永不落地；且直接改 `_loaded_df`，绕过撤销栈与 `_full_df`。更糟的是**导入新文件时不清空 `_formula_cells`**（`beesheet.py:506-535`），换文件后旧坐标上的公式会覆盖新数据。

**Excel 语义偏差（对日常使用的影响比安全问题更大）**

- **`=` 与 `<>` 不被支持——这是最严重的一条。** `_safe_eval` 的 AST 白名单里有 `_ast.Eq`，docstring 也写着"支持 `==`"，但 Excel 用户写的是 `=`。`=IF(A1=1,"是","否")` 会被替换成 `1=1` 再交给 `ast.parse` → SyntaxError → 返回 `#ERROR`。**这是电子表格出现频率最高的公式之一，当前版本必然失败**；`<>` 在 Python 3 已移除，同样不可用（只有 `!=` 能过）。测试没有发现它，因为针对在用引擎的测试**全部只用 `>` / `<`**，唯一使用 `=` 的那条用例（`tests/unit/test_formula_engine.py:409`）测的是那套**死代码引擎**。
- **复合表达式退化为文本**：`=SUM(A1:A3)*2`、`=ROUND(A1,2)+1`、`=2^3`、`=A1&"x"` 都不会被求值——整串匹配 `^(\w+)\((.*)\)$` 失败，`_safe_eval` 又因 `^`/`&` 不在白名单而失败，最终**把公式字符串原样当成单元格内容**。
- **文本结果无法落地**：公式栏只接受 `int/float`（`beesheet_formula_mixin.py:36-47`），delegate 记下公式后也只重算数字（`beesheet_delegate.py:92-102`）。于是 `TODAY()`、`CONCATENATE()`、返回文本的 `VLOOKUP()` 在界面上显示的是**公式原文**。
- **多条件函数语义错误**：`COUNTIFS` 对每个条件范围**各自计数再相加**（`:922-935`），不是逐行 AND；`SUMIFS/AVERAGEIFS` 的条件区只取第一列（`:968、1000`）。
- **跨表聚合恒为 0**：`=SUM(Sheet2!A1:A3)` 被替换成 `SUM(1,2,3)`，`_vals()` 解析不了裸数字列表 → 返回 `0`（`:96-112、264-277`）；跨表 VLOOKUP 直接 `#ERROR`。
- **错误值体系缺失**：只有 `#ERROR: msg`（截断 80 字符）、`#N/A` 和裸 `#ERROR`，没有 `#DIV/0!` / `#VALUE!` / `#REF!` / `#NAME?`，用户无法用 `ISERROR` 区分错误类型。
- **引用替换会误伤字符串**：`_safe_eval` 的 `ref_pattern = \$?[A-Za-z]{1,3}\$?\d+`（:504）不跳过引号，`=IF(A1="B2",…)` 里作为文本的 `"B2"` 会被替换成单元格值。
- 其余单点偏差：`A0` 被当成 `iloc[-1]`（取最后一行，`beesheet_model.py:373-378`）；`INDEX(range,0)` 允许负索引回绕；VLOOKUP 近似匹配返回"首个 ≥"而非"最大 ≤"；`WEEKDAY` 周一记 1；`WORKDAY` 不减周末；`EDATE` 按"月×30 天"算；`EOMONTH` 用 +31 天 hack；`STDEV/VAR` 用总体而非样本；`FIND` 未找到返回 0；`RIGHT(n=0)` 返回整串；`ROUND` 用银行家舍入。

**安全：P0-5 修复只做了一半（重要）**

`_safe_eval()` 确实做了 AST 白名单（`:513-550`，禁止 Attribute/Subscript/Lambda/推导式，函数只允许 abs/round/int/float/min/max），并且有专门的回归测试（`tests/regression/p0/test_p0_05_safe_eval_boundary.py`）。**但另一条路径完全绕过了它**：

```python
# beesheet_engine.py:105-108
new_expr = re.sub(sheet_pattern, replace_sheet, expr)
try:
    return eval(new_expr, {"__builtins__": {}}, {})   # ← 裸 eval，无 AST 校验
```

触发条件：公式里出现 `!`（即跨表引用），`_eval()` 会直接进 `_eval_sheet_ref()`（`:58-59`）。`__builtins__` 置空**挡不住**对象图遍历：

```
=Sheet1!A1+().__class__.__bases__[0].__subclasses__()
```

`Sheet1!A1` 被替换成数值后，剩余部分原样交给 `eval`，属性访问 + 下标访问均可用——这是经典的 Python 沙箱逃逸。`beesheet.py:148` 又把 `_get_sheet_data` 挂到了 model 上，使 `hasattr(model, '_get_sheet_data')` 恒为真，这条路径**在正常使用中是可达的**。

定级说明（避免夸大）：文件导入路径（`beesheet_loaders.py:153` 用 `data_only=True`，pandas 的 `read_excel` 同样只取缓存值）不会把公式字符串带进来，所以这**不是"打开恶意 xlsx 即中招"的远程 RCE**；但用户手动输入、或任何保留公式文本的导入路径都会触发。考虑到项目自己在 CHANGELOG 里把"消除公式引擎任意代码执行"列为 P0 修复，这个残留属于**同类漏洞未清干净**。

**线程亲和性违规（P0）**

`app.py:508` 把 `widget._import_file_from_path` 丢进 `AsyncTaskManager.run()` 执行。但该函数内部：

- `self.model.set_full_dataframe(df)`（`beesheet.py:528`）→ 触发 `layoutChanged.emit()`（`beesheet_model.py:92`），**在 worker 线程里改 Qt 模型**；
- `self.table_view.setModel(self.model)`、`self._set_status(...)`（:529、533）也在 worker 线程操作控件；
- 行数超 20 万时还会执行 `QMessageBox.question(...)`（:523-526）——**在非 GUI 线程弹模态框**。

Qt 明确要求 `QAbstractItemModel` 只能在其所属线程操作。这是随机崩溃/界面错乱的经典来源，且它恰好出现在"打开大文件"这条最常用的路径上。

**做得对的地方**：

- `LargeFileLoader(QThread)` 是真线程，CSV 用 `chunksize` 分块、每块前 `isInterruptionRequested()`，Excel 每 1000 行检查一次，取消按钮可用（`beesheet_loaders.py:96-183`）。
- 撤销/重做是命令模式（`EditCellCommand/SortCommand/TrimCommand`，栈上限 100），比"存整个 DataFrame 快照"省内存。

**但"分块加载"名不副实，而且还有第二处线程违规**：

- 所有 chunk 被 append 进 list，最后 `pd.concat(chunks)` 一次性拼回（`beesheet_loaders.py:105`）——峰值内存约为文件数据的 **2 倍**，只降低了卡顿、没有降低内存。
- `chunk_ready` 信号**没有任何接收者**，分块渲染实际上是假的。
- 滚动加载用的 `ChunkLoader` **在工作线程里直接改 model**（`beesheet_loaders.py:38-47`），没有锁，UI 线程同时在读——这是和导入路径并列的第二处 Qt 线程亲和性违规。
- 分块拼接用 `ignore_index=False` 却按 `iloc` 定位（`beesheet_model.py:102-106、190`），**跳转后再回翻会行错位**。
- 筛选/排序/删行只改 `_loaded_df`、不更新 `_total_rows`（`beesheet_data_mixin.py:298、390`），导致 `rowCount()` 虚高、状态栏显示加载中。

**其他"看起来有、其实没有"的功能**：

- **冻结窗格是假的**：只改了 `resizeMode` 与计数，不创建冻结视图，`beesheet.py:151` 的注释自己写着"冻结视图已禁用"（`beesheet_context_menu_mixin.py:128-168`）。
- **插件里挂的"数据分析/图表/宏"三个入口全是空的**：`_analyze_data`、`ChartDialog` 在全仓不存在（`beesheet_plugin.py:191、308、323`）。

**两套公式引擎，一套是死代码（重要）**

仓库里存在两个 `class FormulaEngine`：

| 文件 | 行数 | 使用者 |
|---|---|---|
| `beesheet_engine.py` | 1,620 | 生产代码全部用这个（`beesheet.py:71` 等 3 处 import） |
| `formula_engine.py` | 649 | **只有 `tests/unit/test_formula_engine.py` 用**，生产代码零引用 |

`formula_engine.py` 里也有 `eval`（:378），覆盖率高达 88.3%（因为测试在测它），但它**对产品没有任何作用**。这既浪费维护成本，又制造"公式引擎测得很充分"的假象。

**打包配置与代码自相矛盾**

`beesheet_chart_mixin.py:70` 导入 `matplotlib.backends.backend_qt5agg`，而 `beeoffice.spec` 的 `excludes` 里明确排除了 `matplotlib.backends.backend_qt5agg`（:125）。**打包出来的 exe 里，蜜算图表功能必然 ImportError**。源码运行时能用，所以开发期不会发现。

### 3.3 蜜演 BeeShow（幻灯片）

**规模**：27 个文件、约 11,837 行，14 个 Mixin。

**数据模型极其原始**：唯一真源是一个 `QPlainTextEdit` 里的 Markdown 文本，按 `\n---` 切页（`beeshow_slide_mixin.py:104`），派生 `_slides_html`（HTML 串）和 `_slides_md`，备注/标题是**平行 dict**（`beeshow.py:104-110`）。没有 JSON IR、没有 python-pptx 文档对象、没有稳定 ID。

这个选择直接导致两个系统性后果：

1. **任何一次"改一页"都是一次全文重写**：全子系统有 18 处 `re.split("\n---")` + `setPlainText` + `_update_preview`（拖拽、删页、备注、评论、表格、插图……）。而解析时会丢弃空段（`slide:111-114`），索引却按原始 parts 计——**文档中出现空段时，页号错位，备注/评论会写到别的页上**。
2. **渲染内核有三套**：预览和播放用 `QWebEngineView.setHtml`，PPTX 导出另起 Playwright/Chromium 重画，HTML 导出纯字符串拼接。三者必然不一致。

**导出功能存在"假成功"（P0）**

```python
# beeshow_export_mixin.py:276-293
def on_load(ok):
    if ok:
        temp.page().printToPdf(path)          # 异步，没有回调
        QMessageBox.information(self, "导出成功", f"已保存: {path}")   # 立刻宣布成功
    ...
    temp.deleteLater()                        # 立刻销毁渲染页
```

`printToPdf` 是异步 API，正确做法是连接 `pdfPrintingFinished` 信号。当前实现**在文件还没写出来时就弹"导出成功"，并且马上 `deleteLater()` 掉正在打印的页面**。大文档下 PDF 很可能根本没生成或只写了一部分。

图片序列导出用 `page.grab()`（:404）——`QWebEnginePage` 没有 `grab()` 方法（那是 `QWebEngineView` 的），异常被 `except` 吞掉只记日志（:407-408），循环结束仍然弹"成功"（:415-418）。**高概率所有图片导出都是空的**。

**PPTX 导出**：思路是对的——用 JS 量 DOM 的 `getBoundingClientRect` 和字号，再映射成原生 textbox/picture/table（`beeshow_pptx_engine.py:140-646`），这样导出的文本可编辑，比截图方案好。

但实现有三个坑：

- 每页都重新 `launch` 一次 Chromium（:292-306、:714-720），10 页就是十几次浏览器启动，全在 GUI 线程同步跑；
- **测量失败仍然返回成功**：只打 warning，继续生成，最后 `return True`（:717-725）——用户拿到的是空白 PPTX；
- 字体子集化的关系 ID 对不上：rels 用 `max+1`（`beeshow_font_subset.py:438-450`），`embeddedFontLst` 却硬编码 `rId100+i`（:488），算出来的 `existing_ids` 根本没用（:477-479）。PowerPoint 打开时大概率报"需要修复"（推测，需实测）。

**同步演示服务默认不安全（P0）**

`beeshow_sync_server.py` 默认 `host="0.0.0.0"`（:177），HTTP 8765 + 手写 WebSocket 8766：

- `/api/slide/<idx>` 直接吐整篇幻灯片 HTML，且带 `Access-Control-Allow-Origin: *`（:335-357）；
- WS 握手不校验 `Origin`（:470-518）。

也就是说：**同一局域网内任何人、或用户浏览器里打开的任意网页，都能读取整份演示文稿**。没有任何 token、口令或配对机制。

另外有一个启动竞态：`_running` 在 WS 线程启动之后才置 `True`（:218-223），而 accept 循环条件是 `while self._running`（:401），线程很可能立刻退出，导致 WS 根本没监听。

**其他确认问题**：

- `_start_play()` 强制 `_current_slide = 0`（`beeshow_play_mixin.py:73`），所以插件菜单的"从当前页播放"永远从头开始；更有意思的是**测试把这个行为固化成了预期**（`tests/qt/test_beeshow_play.py:18-28`）。
- `_PlayWindow(self)` 带 parent 构造（`play:78`、`constants:469-471`），**没有设置 `Qt.Window` 标志**，而 `showFullScreen()` 只对顶层窗口生效——"全屏播放"很可能不是真全屏（需实机确认）。
- 激光笔/画笔是空壳：L 键只切 `display`（`play:420-427`），P 键只翻转 `_drawing_active`（:428-430），没有 mouseMove 绘制逻辑，`_broadcast_laser` 无任何调用者（`beeshow_sync_mixin.py:133`）。
- 排练计时只用一个 100ms QTimer 刷总时长标签（`play:448、478-487`），不按页计时、不写回备注、不参与导出。
- 每翻一页 `setHtml` 整页重载（`play:250`），morph（平滑迁移）依赖的 `__beeofficePrevPositions` 必然被清空，动画永远走首屏分支。
- 所有 `setHtml` 都没有传 `baseUrl`（`slide:418`、`play:250`、`export:293`），相对路径图片没有基准；视频 `src` 直接写 `C:\...`（`video:235`）不是合法 URL——预览里图片/视频大概率加载不出来（推测偏事实）。
- 全子系统 106 处 `except Exception`，多处只 `pass`。
- AI 大纲/演讲稿是**真调用 LLM**（`beeshow_ai_service.py`，OpenAI 兼容协议，30s 超时、2 次重试），这是全项目唯一名副其实的 AI 功能——但它读取的 `settings.ai_api_key` **在 UI 上没有任何配置入口**（只有云存储对话框，没有 AI 设置页）。用户只能手改 `~/.beeoffice_settings.json`。

### 3.4 PDF 批注

**规模**：173 行的 `pdf_annotator.py` + 包装器。

功能完整度反而是四个模块里最高的：打开、高亮/下划线/删除线/文字批注、按页撤销、`.beeanno` 旁挂 JSON、烧录进 PDF。PyMuPDF 渲染成 QPixmap 放进 QGraphicsScene，逻辑直白。

问题：

- 代码风格是**每行多条语句**（`self._doc=None; self._filepath=None; ...`），可读性差，与项目其他文件的详细注释风格完全割裂，像是另一时期快速写的。
- 缩放只靠滚轮，每滚一次就**整页重新 `get_pixmap` 并重绘全部批注**（:53），高倍缩放时明显卡顿。
- 批注坐标存的是 PDF 空间坐标（`fitz.Rect`），UI 上也做了 `*self._scale` 换算，这点是对的。
- `.beeanno` 文件没有版本号字段，格式一旦变动无法迁移。

### 3.5 云同步

**宣传与实现差距最大的一块。**

README / CHANGELOG 写的是："WebDAV / OneDrive / Google Drive 支持、自动同步、冲突检测、失败重试 3 次"。

实际：

| 声明 | 实际 |
|---|---|
| OneDrive / Google Drive 支持 | 只是让你**粘贴一个 Access Token**（`cloud_settings.py:67-80`）。没有 OAuth 授权流程，**没有 token 刷新**——token 约 1 小时过期，之后功能静默失效 |
| 自动/手动同步 | `app.py:1148-1170` 把 `~/.beeoffice_data` 整个目录上传到 `/beeoffice`。**用户文档不在这个目录里**，所以"云同步"不同步文档 |
| 冲突检测 | 只在 `plugins/webdav_sync.py` 的 `WebDAVSyncWorker` 里实现，而它**只同步 `templates` 子目录**（:35-45）。两条同步链路互不相干 |
| 失败重试 3 次 | 全仓库未找到重试逻辑 |

其他：

- `cloud_settings._test_connection()` 在 GUI 线程做同步网络请求（`requests.get(..., timeout=10)`、`webdav3.client.check()` 无超时）——点"测试连接"界面会冻结。
- Google Drive 上传时 `files={...: open(local_path,"rb")}`（`googledrive.py:303-307`）**没有关闭文件句柄**。
- 凭据"加密"只是 Base64（`settings.py:77-95`），任何能读到 `~/.beeoffice_settings.json` 的程序都能直接解出 API Key 和 WebDAV 密码。CHANGELOG 把它列在"安全"一栏，属于高估。

### 3.6 移动端 Web 访问

`mobile.py` 启动一个 `ThreadingHTTPServer`，绑定 `("", port)`（:99）——**所有网卡**，无鉴权，从 8888 起找端口。

三个问题：

1. **CORS 全开 + 无鉴权**：`Access-Control-Allow-Origin: *`（:296、:315）。用户浏览任意网页时，该网页的 JS 就能 `fetch('http://<内网IP>:8888/api/docs')` 拉走所有打开的文档内容并外传。这是比"同局域网可见"更严重的风险。
2. **跨线程操作 Qt 对象**：请求处理在 `ThreadingHTTPServer` 的工作线程里，却直接调用 `parent.tab_manager.widget(i)`、`widget.toPlainText()`、`widget.model.df`（:286-341）。Qt 控件只能在 GUI 线程访问。
3. `socket.gethostbyname(socket.gethostname())`（:71）在很多 Windows 环境返回 `127.0.1.1` 或错误地址，手机根本连不上；端口探测先绑 `self.ip` 再绑 `""`（:82 vs :99），也存在竞争。

### 3.7 插件市场

名字叫"市场"，实际只有两个按钮：**从 ZIP 安装** / **从文件夹安装**。没有远端目录、没有版本检查、没有签名。

- 校验逻辑是字符串包含判断：`return "Plugin" in content and "class " in content`（`plugin_market.py:360`）。任何文本里出现这两个词就能通过。
- 安装只复制 `.py` 文件，**扁平化**到 `plugins/` 目录——带子包或数据文件的插件装不进去。
- 卸载会**删除源文件**（:394-407）。由于内置的四大插件也在列表里，用户点一次"卸载 蜜写"，`beewrite_plugin.py` 就**从源码目录被删掉**了。这是真实的数据丢失风险。

---

## 4. 缺陷清单

### P0（阻断使用 / 数据丢失 / 安全）

| # | 问题 | 位置 |
|---|---|---|
| 1 | 引擎**不支持 Excel 的 `=` / `<>` 比较符**，`=IF(A1=1,…)`、`=IF(A1<>1,…)` 恒返回 `#ERROR` | `beesheet_engine.py:504-523`、`:563` |
| 2 | 公式的**文本结果无法落地**（TODAY / CONCATENATE / 文本型 VLOOKUP 显示公式原文） | `beesheet_formula_mixin.py:36-47`、`beesheet_delegate.py:92-102` |
| 3 | md 模式导出 DOCX **丢失全部图片**（`_write_element` 无 img 分支） | `bee_export.py:265-346` |
| 4 | 批注/书签**只写不读**，重开文档即丢 | `beewrite_export_mixin.py:208/215`；全仓无 `load_from_file` 调用 |
| 5 | 异步导入时在 **worker 线程修改 Qt 模型并弹 QMessageBox** | `beesheet.py:523-533` + `app.py:508` |
| 6 | 跨表引用分支使用**裸 `eval`**，可绕开 AST 白名单 | `beesheet_engine.py:107` |
| 7 | 导入新文件**不清空 `_formula_cells`**，旧公式会覆盖新数据 | `beesheet.py:506-535`、`:122` |
| 8 | PDF 导出声称成功但未等待 `printToPdf` 完成即销毁页面 | `beeshow_export_mixin.py:276-293` |
| 9 | 图片序列导出调用不存在的 `page.grab()`，异常被吞，仍报成功 | `beeshow_export_mixin.py:404-418` |
| 10 | 同步演示服务默认 `0.0.0.0` + 无鉴权 + `ACAO:*` | `beeshow_sync_server.py:177,335-357` |
| 11 | 移动端服务 `ACAO:*` + 无鉴权 + 跨线程访问控件 | `mobile.py:99,296,315,286-341` |
| 12 | 插件"卸载"会删除内置插件的源文件 | `plugin_market.py:394-407` |

### P1（功能错误 / 明显体验缺陷）

| # | 问题 | 位置 |
|---|---|---|
| 13 | 复合表达式退化为文本（`=SUM(A1:A3)*2`、`=2^3`、`=A1&"x"`） | `beesheet_engine.py:62,74-82` |
| 14 | `COUNTIFS` 各条件范围独立计数后相加；`SUMIFS/AVERAGEIFS` 条件区只取首列 | `beesheet_engine.py:922-935,968,1000` |
| 15 | 跨表聚合恒为 0（`=SUM(Sheet2!A1:A3)`），跨表 VLOOKUP 直接报错 | `beesheet_engine.py:96-112,264-277` |
| 16 | 滚动分块按 `iloc` 定位却用 `ignore_index=False` 拼接 → 跳转回翻行错位 | `beesheet_model.py:102-106,190` |
| 17 | `ChunkLoader` 在 worker 线程直接改 model（第二处线程违规） | `beesheet_loaders.py:38-47` |
| 18 | 冻结窗格只改 `resizeMode`，不建冻结视图（注释自认"已禁用"） | `beesheet_context_menu_mixin.py:128-168`、`beesheet.py:151` |
| 19 | 插件"数据分析 / 图表 / 宏"三个入口指向不存在的方法 | `beesheet_plugin.py:191,308,323,168` |
| 20 | UI 函数参考表仅 86 项，缺 LET/SWITCH/XMATCH/MAXIFS/IS* 等 15 个函数 | `beesheet_ui_mixin.py:59-146` |
| 21 | 命令 `export_html` 注册了但方法不存在 | `beewrite_plugin.py:150-159` |
| 22 | 引用块往返破坏（重建 20，判定 >30） | `beewrite_rich_editor.py:804 / 527` |
| 23 | 超链接 URL 在模式切换中丢失 | `beewrite_rich_editor.py:867-872` |
| 24 | 表格空单元格导致列错位、数据左移 | `beewrite_rich_editor.py:719,748` |
| 25 | 页眉页脚写成可见 HTML 注释文本 | `beewrite_doc_mixin.py:75,88` |
| 26 | 每按键全量序列化整篇文档 + 三个槽重复触发 | `beewrite.py:268-274` |
| 27 | `save_as` 取消后丢失当前路径 | `beewrite_export_mixin.py:131` |
| 28 | AI 续写在上下文无句号时**重复插入原文** | `beewrite_ai_mixin.py:61-66` |
| 29 | 宏录制/播放**完全未实现**（仅菜单与 hasattr 空跳） | `app.py:1325-1333`、`beesheet_plugin.py:302-325` |
| 30 | 打包 `excludes` 排除了代码正在使用的 `backend_qt5agg` → 图表必崩 | `beeoffice.spec:125` vs `beesheet_chart_mixin.py:70` |
| 31 | `formula_engine.py` 整文件为死代码，却配了完整测试 | `formula_engine.py` / `tests/unit/test_formula_engine.py` |
| 32 | 启动 50ms 后 import 全部插件模块，主线程阻塞 | `app.py:153` + `plugin_manager.py:36-45` |
| 33 | "全屏播放"未设窗口标志，很可能非顶层全屏 | `beeshow_play_mixin.py:78,89` |
| 34 | 从当前页播放永远从头（测试还固化了该行为） | `beeshow_play_mixin.py:73` |
| 35 | PPTX 测量失败仍返回成功 → 空白文件 | `beeshow_pptx_engine.py:717-725` |
| 36 | 幻灯片空段导致**页号错位**，备注/评论写错页 | `beeshow_slide_mixin.py:111-114` |
| 37 | 云同步不同步用户文档；OneDrive/GDrive 无 token 刷新 | `app.py:1148-1170`、`cloud_sync/*` |
| 38 | "测试连接"在 GUI 线程做同步网络请求 | `cloud_settings.py:204-262` |
| 39 | 设置中的 API Key / 密码仅 Base64（可逆） | `settings.py:77-95` |
| 40 | 插件校验是字符串包含，且安装会扁平化丢子包 | `plugin_market.py:355-362` |

### P2（代码质量 / 可维护性）

- **吞异常**：`except Exception: pass` / 仅 log 的模式在四个子系统里合计上百处（蜜演一个子系统就 106 处）。
- **超长函数**：`_build_all_toolbars` 244 行、`_build_toolbar2` 198 行、`_show_history_panel` 193 行、`_show_paragraph_dialog` 163 行、`_build_main_toolbar` 161 行、`_enter_split_view` 153 行。
- **重复实现**：26 进制列号转换 **5 份**（`beesheet_engine.py:121/141/248`、`beesheet_utils.py:62`、`beesheet_formula_mixin.py:217`）、`A1:B10` 区域正则 5 份、SUMIFS 家族 4 份近似实现、`_block_has_image` 三份、标题清洗逻辑三份、幻灯片"切分+重写"18 处、`blockSignals+setPlainText` 12 处。
- **死代码**：`_css_cache`、`_preloaded_slides`、`_pptx_engine`、`_font_embedder`、`_broadcast_laser`、`_record_presentation`、`_generate_qrcode`、`git_manager.py` 整文件（零引用）。
- **i18n 覆盖率极低**：42,332 行代码里只有 **145 处 `tr()` 调用**，语言包 181 行（约 150 个键）。`tab_manager.py`、`mobile.py`、`cloud_settings.py`、`plugin_market.py` 里几乎全是硬编码中文。README 的"中英文国际化"只在菜单层成立。
- **注释与代码脱节**：注释写得非常详细（几乎每个函数都有"v5.0.x 修复了什么"），但注释描述的修复经常没有落实到另一条路径上（P0-5 的 `eval` 就是典型）。

---

## 5. 工程质量

### 5.1 测试

**数量可观，质量参差。**

- 64 个 `test_*.py`，分 `unit / qt / regression(p0|p1|v5) / smoke / helpers` 五层，这个分层设计是专业的。
- `tests/conftest.py` 374 行，处理了 QtWebEngine 的 profile 释放、`deleteLater` 时序、fixture 之间的状态污染——说明作者被 Qt 的坑磨过，经验是真的。
- 但**覆盖率的构成有问题**：21,231 条语句只覆盖 35.86%，且 `formula_engine.py`（死代码）88%、`nl_formula.py` 97%、`beesheet_ui_mixin.py` 100% 拉高了均值；真正的业务核心 `beesheet_data_mixin.py` 6.6%、`beesheet_formula_mixin.py` 6.3%、`beewrite_paragraph_mixin.py` 6.4%、`plugin_market.py` 8.1%。
- **测试固化 bug**：`test_beeshow_play.py` 把"从当前页播放→从头播放"断言成了期望行为。
- **测试只断言结构不验产物**：`test_p0_04_beeshow_webengine.py:54-58` 只检查对象属性，不断言导出的 PDF/PPTX 是否真的可用。

### 5.2 CI / 版本控制

- **没有 `.github/` 目录**。CHANGELOG 5.0.1 明确写"新增 `.github/workflows/test.yml`（Windows-only）"——**该文件不存在**。
- **`D:\beeofficeV` 不是 git 仓库**（无 `.git`）。一个 42,000 行、迭代到 5.0.x 的项目没有版本控制，意味着：没有 diff、没有回滚、没有分支、CHANGELOG 靠手写。`backup/` 目录里 5 个带日期的手工副本（`beesheet - bak 20260910V2.py` 等）就是这个缺失的替代品。
- `__pycache__`（cpython-311 与 312 两份）、`.coverage`、`coverage.xml`（805 KB）、`.pytest_cache` 都留在工作区里。

### 5.3 构建与打包

- `beeoffice.spec` + `build.py` + `build_release.py` 三件套齐全，会收集 `beeoffice.plugins` 全部子模块作为 hiddenimports（对动态 import 是对的）。
- 但 `excludes` 与代码冲突（见 P1-19），且 `icon` 在 `resources/` 下并不存在（该目录只有 3 个 `.py`），打包出来是无图标的 exe。
- `run_py.bat` 硬编码了开发者本机路径（`D:\Program Files\Python311\...`、`D:\PyCharm\yootk\venv`），不可移植。
- 当前环境 `python` 是 3.8.9 且**未安装 PySide6**，按 README 的 `python -m beeoffice.main` 无法直接启动；说明实际开发用的是另一个解释器（`__pycache__` 显示 3.11/3.12）。

### 5.4 文档

- `README.md` 144 行，功能表详尽；`CHANGELOG.md` 430 行，按 Keep a Changelog 组织；`运行文档.txt` 941 行变更清单；`mslxt.txt` 是蜜演 v5.1 的 6 周路线图。
- 文档的问题不是"少"，而是**"承诺 > 实现"**：AI 辅助、云同步、宏、插件市场、分屏、激光笔、全屏播放，都是名实不符的重灾区。第 3 节的对照表就是证据。
- `README` 的"界面预览"写着"截图待补充"；MIT 徽章链到一个不存在的 LICENSE。

---

## 6. 值得肯定的部分

为了不让上面的问题清单掩盖真实水平，明确列出**做得好的地方**：

1. **工程骨架完整**：设置版本迁移（含 `__decoded__` 标记避免二次解码这种细节）、崩溃处理器（无 GUI 环境降级 + 日志滚动清理）、资源路径打包兼容、主题/强调色、命令面板、文件外部修改检测（多文件时间戳 dict）、自动保存。这些是"想过生产环境"的痕迹。
2. **注释习惯极好**：每个修复都写明"原实现是什么、为什么错、改成什么"。对后来者（或 AI 助手）极其友好——本次分析能快速定位问题，很大程度靠这些注释。
3. **公式引擎的函数覆盖是真材实料**：111 个函数，XLOOKUP/XMATCH/LET/SWITCH/IRR/NPV 都实现了，`_safe_eval` 的 AST 白名单方向正确，并且**配了针对性的攻击用例测试**（`(1).__class__.__bases__[0].__subclasses__()` 这类 payload 出现在测试里，说明作者知道威胁模型）。问题不在"会不会写"，而在"没按 Excel 的真实语义验收"——函数写得再多，`=` 不通就白搭。
4. **大文件加载的线程化**：`LargeFileLoader` 是真 QThread，有中断检查、进度信号、取消按钮，这是全项目最规范的一段并发代码。
5. **命令模式的撤销栈**，而不是整表快照。
6. **PPTX 导出选择了"DOM 测量 + 原生元素重画"**而不是截图——这个技术选型是对的，只是实现没闭环。

---

## 7. 改进路线（按投入产出排序）

### 第一优先级：先让"已宣传的功能"真的能用（1~2 周）

1. **修三个数据丢失 bug**：DOCX 导出的 `<img>` 分支、批注/书签的 `load_from_file` 接线、PDF 导出接 `pdfPrintingFinished`。
2. **修线程违规**：`_import_file_from_path` 只让 pandas 在后台跑，`set_full_dataframe` / `setModel` / `QMessageBox` 全部用信号切回 GUI 线程。这是最容易崩的地方。
3. **修公式引擎的语义门槛**：进入求值前把 `=` → `==`、`<>` → `!=` 做词法级归一化（这一个小改动能救回 IF/IFS/COUNTIF 一半的用法）；让公式栏与 delegate 接受字符串结果；修 `COUNTIFS` 的逐行 AND 语义。**先补一组"Excel 写法"的端到端用例**，再动代码——现在的测试集里没有一条 `=IF(A1=1,…)`，这是测试设计的缺口。
4. **删掉 `formula_engine.py`**（连同其测试），或反过来合并——总之不能留两套。同时给 `_eval_sheet_ref` 补 AST 白名单，或者干脆复用 `_safe_eval`。
5. **把 `beeoffice.spec` 的 `excludes` 与代码对齐**，至少去掉 `backend_qt5agg`（并改用 `backend_qtagg`）。
6. **给本地 HTTP 服务加 token**（启动时生成随机串拼进 URL），去掉 `ACAO:*`；`beeshow_sync_server` 默认绑 `127.0.0.1`，需要局域网时再显式放开。

### 第二优先级：恢复工程卫生（1 周）

7. **`git init` 并提交**。把 `backup/`、`__pycache__`、`coverage.xml`、`.coverage`、`create_tests.py`、`boost_coverage.py`、`finalize_session.py`、`mslxt.txt`、`运行文档.txt` 移出仓库或加进 `.gitignore`。
8. **建立单一版本来源**：`__version__.py` 唯一，`main.py` 的 `print` 改读它，README 徽章与 CHANGELOG 由脚本生成。
9. **补 `.github/workflows/test.yml`**（CHANGELOG 已经承诺了），至少跑 `pytest -q` + 导入冒烟。
10. **把版本号/覆盖率数字从 CHANGELOG 里的人工编辑改成脚本产出**——5.0.6 那条粘错的 Python 代码正是手工维护的代价。

### 第三优先级：架构收敛（3~4 周）

11. **给蜜写建立单一事实源**。现在"md 源 + 富文本"两个模型靠有损往返同步，这一类 bug（引用、链接、表格空列）会无限复发。建议：以富文本 `QTextDocument` 为唯一模型，Markdown 只作为导入/导出的序列化格式，并写**往返一致性测试**（`md → rich → md` 幂等）。
12. **给蜜演引入 JSON IR**（每页一个稳定 id + 元素列表），替代"`\n---` 切分 + 全文重写"。这一步做完，页号错位、备注错页、morph 失效会一起消失。
13. **拆分上帝类**：`BeeShowView` 14 个 Mixin、`BeeSheetView` 8 个 Mixin，至少给它们定义 Protocol/抽象基类，把隐式属性契约显式化。

### 第四优先级：产品诚实度（持续）

14. **要么把 AI 做实，要么改名**。"AI 续写"随机插一句"综上所述，我们可以得出结论"，比没有这个功能更伤害信任。既然 `beeshow_ai_service.py` 已经有可用的 LLM 客户端，把它接到蜜写、并补一个 AI 设置页（API Key 目前只能在 JSON 里改）是最小成本的真 AI。
15. **README 的功能表按"已实现 / 部分实现 / 规划中"三态标注**。现在这份文档对用户的误导程度，已经超过了它作为说明的价值。
16. **把宏、激光笔、录制、二维码这类空壳先摘掉**，或者标注"即将推出"。留着菜单但点了没反应，用户会认为软件坏了。

---

## 8. 总体判断

BeeOffice 是一个**野心远大于当前完成度的项目**。

它的作者显然具备相当的工程能力：会用 Mixin 拆 1,800 行的文件、会写 AST 白名单防注入、会处理 QtWebEngine 的 profile 释放、会给设置做版本迁移、会写 64 个测试文件并分层。这些都不是新手会做的事。

但项目同时表现出一种**"清单式开发"**的特征：先照着 WPS/Word 的功能表把入口铺满，再逐个填实现，而填的过程被"先让它不报错"驱动，于是大量功能停在"点了有反应、但结果是错的"这一层——导出报成功但文件是空的、"全屏"不是全屏、AI 是随机语料、云同步不同步文档、宏只有菜单。

结果就是：**42,000 行代码，做出了一个能演示、不能托付的软件**。

要跨过这道坎，关键不在于继续加功能，而在于三件事：

1. **把"成功"的定义改成"产物正确"**——导出要验证文件能打开，同步要验证文件能回来，交付前跑一遍真实文档；
2. **把"版本控制 + CI"补上**——没有 diff 和回归，上面那些"修了 A 坏了 B"（P0-5 只修一半就是活例子）只会越来越多；
3. **敢删**——两套公式引擎、五个手工备份、占位宏、空壳激光笔，删掉它们比加十个新功能更能提升这个项目的质量。

---

*本报告基于静态源码分析，标注"推测"的条目需实机验证。所有行号对应当前工作区文件。*
