# 蜜蜂办公 BeeOffice 代码分析报告

- **分析对象**：`D:\beeofficeV`（BeeOffice v5.0.4，Python + PySide6 桌面办公套件）
- **分析日期**：2026-10-10
- **分析方式**：只读静态分析 + 在本机 Python 3.11.9 / PySide6 6.6.0 环境下的实际运行验证
- **证据约定**：`【实测】` = 本次分析中实际运行代码复现；`【代码】` = 直接阅读源码确认；`【报告】` = 由模块深度分析得出但未由本文作者二次复现；`【推断】` = 需要运行时/实机确认

---

## 0. 结论摘要

这是一个**功能覆盖面极广、但完成度与质量严重不均衡**的个人项目。它把"办公套件"的几乎每一个功能点都写了进来（文字/Markdown 编辑、表格、演示、PDF 批注、云同步、移动端、插件市场、AI），代码量约 3.7 万行、118 个模块、710 个测试。但本次分析发现的问题集中在四个层面：

**① 安全问题（最紧急）**

- **公式引擎存在可复现的任意代码执行**：CHANGELOG 声称 v5.0.1 已用"AST 白名单"修复公式引擎的任意代码执行漏洞，但修复只覆盖了 `IF/AND/OR/NOT/IFS` 的条件求值路径；另外两处裸 `eval()` 原封不动地留在代码里，其中一处（`beesheet_engine.py:107`，跨表引用路径，**活代码**）已被本次分析实际利用成功。【实测】
- **两个网络服务绑定 `0.0.0.0` 且零认证**：移动端文档服务（`mobile.py:99`）与蜜演远程同步服务（`beeshow_sync_server.py:177`）对局域网完全开放，前者还带 `Access-Control-Allow-Origin: *`，可被同机浏览器中的任意网页跨域读取全部已打开文档。【代码/报告】
- **云凭据仅 Base64 编码**：WebDAV 密码、OAuth token、AI API Key 都是"Base64 当加密"，而 CHANGELOG 把它列为"安全"改进。【代码】
- **插件市场无签名/哈希/权限模型**：安装即持久化任意代码执行，判别条件只是"文件里含 `Plugin` 和 `class ` 两个子串"。【代码】

**② 数据安全问题**

- **`AppSettings.save()` 会摧毁用户配置文件**：先以 `"w"` 模式截断文件，再构造要写入的字典；一旦中途抛异常（已实际触发），文件被留成空文件，用户设置（含云配置）静默全丢。【实测】
- **打开 `.docx` 后按 Ctrl+S 会原地覆盖原始 Word 文档**，且重建过程的保真度很低（超链接、列表编号、页眉页脚、脚注、东亚字体全部丢失），无备份、无确认。【代码】
- **"导出 PNG 图片序列"永远不会产出文件却报"导出成功"**：对 `QWebEnginePage` 调用只存在于 `QWidget` 上的 `grab()`，异常被吞掉，`finally` 里照样弹成功框。【实测 + 代码】

**③ 性能问题**

- **启动后界面冻结 7–9 秒**：插件发现机制会 `import` `plugins/` 目录下的全部 86 个模块，把 matplotlib、PyMuPDF、python-docx、pandas 乃至 QtWebEngine 全部拉起。实测 `discover_plugins()` 单独耗时 **9.1 秒（冷）/ 6.6 秒（热）**，而它是在窗口 `show()` 之后 50ms 由主线程同步执行的。【实测】

**④ 工程问题**

- **项目不在任何版本控制之下**（无 `.git`），也没有 `LICENSE`（README 标注 MIT）和 CHANGELOG 里声称的 `.github/workflows/test.yml`。变更历史靠 `backup/` 目录里 7 份带日期的源码副本和源码文件顶部的"更新日志式 docstring"（**45/118 个模块**如此）承载。
- **README/CHANGELOG 与代码事实存在系统性偏差**：宏录制、冻结窗格、激光笔/画笔、PNG/GIF 导出、页眉页脚、HTML 导出等宣称的功能是空壳或桩实现；CHANGELOG 记录为"已修复"的问题中至少 3 项实际未修复（详见 §5）。
- **测试套件给出了虚假的安全感**：710 个测试中存在大量"只断言方法存在"的烟雾测试和"恒真断言"；公式安全测试只覆盖了已加固的那条路径。

**结论**：作为学习/个人作品，它的功能广度令人印象深刻；但**目前的状态不建议用于任何真实文档处理场景**，尤其是打开来源不可信的 `.xlsx`/`.md`/`.docx` 文件（任意代码执行 + 局域网数据外泄 + 原文件被破坏）。

---

## 1. 项目概况

### 1.1 身份与规模

| 项目 | 值 |
|---|---|
| 名称 | 蜜蜂办公 BeeOffice（口号"百花寻觅，酿得甜蜜"） |
| 版本 | `__version__.py` = **5.0.4**；README badge = 5.0.2；CHANGELOG 最新条目 = **5.0.6**；代码注释提到 v5.1/v5.2 任务 —— 四处不一致 |
| 作者 | TomJerryGit（1265338136@qq.com） |
| 技术栈 | Python 3.9+ / PySide6 6.5+ / Qt6（含 QtWebEngine） |
| 规模 | **118 个模块，36 948 行**（`beeoffice/`，不含测试） |
| 测试 | 71 个测试文件，`pytest --collect-only` = **710 个测试**（CHANGELOG 声称 581） |
| 版本控制 | **无**（无 `.git`） |
| 许可 | README 写 MIT，**仓库内无 LICENSE 文件** |

### 1.2 目录结构

```
beeofficeV/
├── beeoffice/                 核心包（118 模块 / 36.9k 行）
│   ├── app.py                 主窗口（1414 行 / 87 个方法，God Object）
│   ├── main.py                入口
│   ├── plugin_base.py         插件基类
│   ├── plugin_manager.py      插件发现与生命周期
│   ├── settings.py            设置持久化（含 Base64"加密"）
│   ├── tab_manager.py         多标签
│   ├── async_task.py          QThreadPool 异步封装
│   ├── mobile.py              移动端 HTTP 服务（0.0.0.0）
│   ├── cloud*.py / webdav.py  云同步（含遗留实现）
│   ├── cloud_sync/            WebDAV / OneDrive / GoogleDrive 适配器
│   ├── locales/               zh_CN / en_US（各 169 键，无缺失）
│   ├── resources/             模板管理
│   └── plugins/               **86 个模块**
│       ├── beewrite_*.py      18 个（蜜写 / Markdown-富文本）
│       ├── beesheet_*.py      19 个（蜜算 / 表格公式，≈10 600 行）
│       ├── beeshow_*.py       27 个（蜜演 / 幻灯片）
│       ├── pdf_annotator*.py  PDF 批注
│       └── formula_engine.py  **569 行死代码**（两个同名引擎之一）
├── tests/                     单元 14 / Qt 11 / 回归 39 / 烟测 2
├── backup/                    7 份带日期的历史源码副本（最大 230KB）
├── tools/migration/           12 个一次性修补脚本
├── test+files/                示例文档与图片
├── create_tests.py (48KB)     批量生成测试的脚本
├── boost_coverage.py          覆盖率提升脚本
├── CHANGELOG.md / 运行文档.txt / mslxt.txt
└── beeoffice.spec / build.py  打包配置
```

### 1.3 开发过程的可观察痕迹

这几乎可以确定是**"与 AI 对话式生成代码"的产物**，证据链清晰：

1. `运行文档.txt`（46KB）本身是对话记录：大量行是"`beeoffice/app.py` → 请给出最新版源代码，一行代码都不用遗漏"。
2. **45/118 个模块的 docstring 是版本更新日志**（"v5.0.2 图片修复：…"、"v5.0.5 修复：…"），把补丁说明写进了源码头部。
3. **CHANGELOG.md 第 9–22 行直接把一段 Python 修补脚本粘在了 `## [5.0.6]` 标题下面**，内容是批量把"测试数：483 → 513"替换成"581"、把"覆盖率 34.54% → 35.06%"替换成"37.30%"——而且替换只改了数字，没改后面 `(+30)` 的说明，导致文档自相矛盾。
4. 零 TODO/FIXME 标记（全仓仅 1 处功能性 `NotImplementedError`），所有"未完成"都以"任务 x.y 增量"的措辞写在注释里，债务不可追踪。
5. 完全没有版本控制：变更靠 `backup/beesheet_v2_backup_20260910.py` 这类文件名管理，`beeoffice/plugins/__pycache__/` 里还留着 `beesheet - bak 20260910.cpython-311.pyc` 这种带空格的编译残留。

**这不是道德评价，而是风险评价**：没有 VCS 意味着任何一次误改都不可回滚；"注释声称已修复"的体例（§5.3）使缺陷难以被发现；而 AI 生成长文本时不会主动做跨模块一致性检查，正是本报告里大量"同一功能 N 份实现""单位三处不一致""文档与代码相反"的成因。

---

## 2. 架构评估

### 2.1 分层设计（合理之处）

职责划分本身是清晰的，这是项目的优点：

```
main.py            → QApplication 引导、日志、崩溃钩子、高 DPI
app.py (BeeApp)    → 主窗口、标签、菜单、文件打开/保存/导出、状态栏、文件监视
  ├── menus.py        菜单构建
  ├── commands.py     命令面板注册（含插件命令回填）
  ├── tab_manager.py  标签容器 + 未保存检测 + 拖拽合并
  ├── settings.py     JSON 持久化 + 版本迁移
  ├── theme.py / i18n.py / icon.py / shortcuts.py
  ├── async_task.py   QRunnable + 信号回主线程
  └── plugin_manager → Plugin 子类实例化 → 各功能视图
```

`async_task.py` 的 `Worker(QRunnable)` + `WorkerSignals` 是标准写法；`i18n` 的 zh/en 两份语言包 169 个键完全对齐（无缺失）；`Theme` 的明暗 + 4 强调色实现干净；`utils.py` 的 `get_app_data_dir` / `is_frozen` / `safe_filename` / 长路径 `\\?\` 处理都是正确的跨平台做法。`crash_handler.py` 会判断 `QApplication.instance()` 是否为空以支持无 GUI 环境，崩溃日志保留最近 20 份——这些都是认真设计过的。

### 2.2 主要架构问题

**（1）`app.py` 是 1414 行、87 个方法的 God Object。**
`menus.py`/`commands.py`/`mobile.py` 被拆了出去，但所有业务逻辑仍堆在主窗口上，包括文件 IO、导出、云同步 worker、宏播放、AI 调用、批量转换。CHANGELOG 声称"app.py 从 500+ 行拆分为多个职责单一模块"，实际结果是 **1414 行**。

**（2）插件机制名不副实。**

- `PluginManager.discover_plugins()` 用 `pkgutil.iter_modules` 遍历 `plugins/` 下**全部 86 个模块并逐个 import**，而不是只加载声明了插件的模块。这带来两个后果：
  - **启动阻塞 9.1 秒**【实测】。`_lazy_load_modules` 由 `QTimer.singleShot(50, ...)` 触发，在 `window.show()` 之后 50ms 于**主线程**同步执行 → 用户看到窗口出现后界面冻结约 7–9 秒。此时 matplotlib、PyMuPDF(fitz)、python-docx、pandas、QtWebEngine 全部被拉起。
  - **任何模块导入失败都会静默吞掉**（`logging.error` 后继续）。若 QtWebEngine 初始化失败，`beeshow_constants.py:22` 顶层导入即抛错 → **蜜演插件从应用中"消失"**，用户完全不知道，日志里才有痕迹。
- 全项目只注册了 **4 个插件**（BeeWrite / BeeSheet / BeeShow / PDF），且它们是内置功能而非第三方扩展。
- 插件拿到的 `self.parent` 就是 `BeeApp` 本体，可访问 settings（含凭据）、tab_manager、任意文件系统——**没有任何能力边界或权限模型**。插件市场安装 = 下次启动执行任意代码（§4.4）。
- 插件类名是唯一的身份标识（`get_plugin_by_name`），无 ID/版本约束。
- `load_plugins()` 里留着自己都没想清楚的注释："这里不直接注册，由 commands.py 在构建时遍历插件注册 / 但也可以在此处进行预注册"。

**（3）同一能力存在多份互不复用的实现。**

| 能力 | 实现份数 | 位置 |
|---|---|---|
| 公式引擎 | **2** | `beesheet_engine.py`（活，1620 行）+ `formula_engine.py`（**死代码**，649 行，仅测试引用） |
| WebDAV | **2** | `cloud_sync/webdav.py`（在用）+ `webdav.py`/`plugins/webdav_sync.py`（遗留，含明文密码落盘） |
| Markdown→DOCX | **3** | `bee_export.export_to_docx` / `_rich_to_docx` / `_write_plain_to_docx` |
| Markdown 表格转换 | **3–4** | `beewrite_rich_editor.py` / `beewrite_table_mixin.py` / `beewrite_utils.py` / `beewrite_md_table_dialog.py` |
| 图片 fragment 扫描 | **4** | `beewrite_rich_editor.py:263` / `beewrite_export_mixin.py:957`（逐字复制）/ `beewrite_mode_mixin.py:127` / `beewrite_export_mixin.py:934` |
| 幻灯片 HTML 模板拼接 | **5** | `slide_mixin:413` / `play_mixin:240` / `export_mixin:264,347,388` |
| 表格→Markdown | **3** | 同上 |
| 标题编号算法 | **2** | `beewrite_crossref.py:21` vs `beewrite_outline.py:185`（计数器归零逻辑一字不差） |

两个公式引擎**同名不同 API**（`FormulaEngine`），连测试文件的 docstring 都要专门写"请勿混用"——这是模块级命名事故。

**（4）Mixin 式组装靠隐式约定维持。**
三个编辑模块都用"10–8 个 Mixin 拼成一个巨大的视图类"（`BeeWriteEditor` 有 10 个 Mixin、`BeeSheetView` 有 8 个），Mixin 之间零继承、无 ABC/Protocol，共享状态全靠 `__init__`（BeeWrite 的 `__init__` 单函数 245 行）建立隐式属性契约，并大量使用 `hasattr(self, '_xxx')` / `except AttributeError: pass` 做"功能是否挂载"的探测。

- 目前跨 Mixin **无重名方法**（已用 AST 全量比对），所以 MRO 是安全的——但这纯属运气/约定，任何新增 Mixin 重名都会静默覆盖。
- 更糟的是这个模式的副作用：`except AttributeError: pass` 会把**方法内部真正写错的 AttributeError** 也当成"功能未启用"吞掉（`beeshow_slide_mixin.py:98-102, 192-207, 432-436` 等 10 余处）。一个属性名拼写错误会表现为"这个功能没反应"。
- Mixin 划分的动机也被源码自证：多个文件都写着"不导入其他 `beewrite_*` 模块以避免循环依赖"——拆分主要是为了**绕开循环导入**，而非领域建模。

**（5）`id(widget)` 用作字典键。**
`tab_manager.py:33/93/143`、`beewrite_doc_mixin.py:363-369` 用 `id(widget)` 作为标签状态字典的键。CPython 中 `id()` 在对象回收后会被复用，虽然代码里有 `pop` 清理降低概率，但这在原理上是不安全的键选择。

---

## 3. 本文实际验证的严重缺陷

以下 6 项由本文作者在本机**实际运行代码复现**，不是静态推断。

### 3.1 【严重·实测】公式引擎任意代码执行

**背景**：`CHANGELOG.md:140` 记录 v5.0.1 修复了

> 蜜算：修复公式引擎 `IF` / `AND` / `OR` / `NOT` / `IFS` 可执行任意 Python 代码的安全漏洞（改用 AST 白名单求值）

**事实**：修复确实给 `_safe_eval()`（`beesheet_engine.py:465-550`）加上了严格的 AST 节点白名单（不含 `Attribute`/`Subscript`/`Lambda`/推导式），`IF/AND/OR/NOT/IFS` 走的正是这条路。但引擎里另有**两处裸 `eval()` 未被纳入**：

```python
# beeoffice/plugins/beesheet_engine.py:105-112   ← 活代码路径
new_expr = re.sub(sheet_pattern, replace_sheet, expr)
try:
    return eval(new_expr, {"__builtins__": {}}, {})     # ← 无 AST 校验
except:
    ...
```

```python
# beeoffice/plugins/formula_engine.py:378          ← 遗留/死代码路径
result = eval(expr_with_values, {"__builtins__": {}}, allowed_names)
```

**`{"__builtins__": {}}` 不是沙箱**。下面的复现脚本走的是引擎公开 API `FormulaEngine.evaluate()`：

```python
import pandas as pd
from beeoffice.plugins.beesheet_engine import FormulaEngine

class M:
    def __init__(self): self.df = pd.DataFrame([[1]])
    def _get_sheet_data(self, name): return self.df
    def get_value(self, r, c): return 1

payload = ("=S!A1+[c for c in ().__class__.__base__.__subclasses__() "
           "if c.__name__=='catch_warnings'][0]()._module.__builtins__"
           "['__import__']('math').sqrt(16)")

print(FormulaEngine.evaluate(payload, M()))
```

实际输出：

```
RESULT: 5.0          # = S!A1(1) + sqrt(16)(4.0)
```

对第二个 eval 点同样成功（`formula_engine.py` 的实例式引擎）：

```
formula_engine.py _eval_math RESULT: 9.0    # sqrt(81)
```

**独立验证**：`eval("().__class__.__base__.__subclasses__()", {"__builtins__": {}}, {})` 返回 **209 个类**——即清空 builtins 完全挡不住基于属性穿透的沙箱逃逸，而 `catch_warnings` 路线只是最经典的一条。

**影响**：公式字符串来自用户打开的表格文件。**打开一个来源不可信的 `.xlsx`/`.csv`，其单元格里的公式（以 `=` 开头且含 `!` 或算术表达式）就会被求值**，从而以本地用户身份执行任意 Python 代码（读写文件、联网、持久化）。这是办公软件最经典的攻击面（同类 CVE 在 Excel/WPS 上多次出现）。

**为什么测试没发现**：`tests/regression/p0/test_p0_05_formula_safe.py` 与其扩展 `test_p0_05_safe_eval_boundary.py` 只测 `_safe_eval` 路径（IF/AND/OR/NOT/IFS），测试文件的 docstring 甚至明确写了"修复在 `beesheet_engine.py` 中"——但它们从未构造含 `!` 的公式，也从未碰过 `formula_engine.py`。

**修复建议**：
1. `_eval_sheet_ref()` 改为先做引用替换、再走 `_safe_eval()`，不要自己 `eval`；
2. `formula_engine.py` 若确认是死代码就**删除**（它同时带来维护与安全负担），保留测试改为测活引擎；
3. 中长期：把整个引擎从"正则 + eval"改写为 tokenizer + AST 求值器，公式解析绝不应接触 CPython `eval`；
4. 补充针对 `!`、算术、`()` 属性穿透的负面测试。

---

### 3.2 【严重·实测】`AppSettings.save()` 会摧毁用户配置文件

```python
# beeoffice/settings.py:222-263
try:
    with open(self.path, "w", encoding="utf-8") as f:      # ← 先截断
        json.dump({
            ...
            "ai_api_key": self._encode(self.ai_api_key),   # ← 字典在 with 内构造
            ...
        }, f, indent=2, ensure_ascii=False)
except Exception as e:
    logging.error(f"保存设置文件失败: {e}")                 # ← 静默吞掉
```

`open(..., "w")` **先截断文件**，而要写入的字典是在 `json.dump(...)` 的参数位置上求值的。因此**任何**在构造字典时抛出的异常，都会把用户的 `~/.beeoffice_settings.json` 留成一个 **0 字节文件**。

**这个 bug 已经在实际发生**。我用与 `tests/conftest.py` 的 `temp_settings` fixture 相同的方式构造设置对象（该 fixture 用一份"手写的字段列表"替换 `__init__`），得到：

```
ERROR:root:保存设置文件失败: 'AppSettings' object has no attribute 'ai_api_key'
file exists after save: True
content head:                      ← 空文件
reloaded theme: light              ← 用户设置全部回退默认值
```

**根因链**：
1. `settings.py` 在 v5.1 新增了 `ai_api_key` / `ai_api_base` / `ai_model` / `user_name` / `unsplash_api_key` / `pexels_api_key` 六个字段；
2. `save()` 无条件写这六个字段；
3. `tests/conftest.py:63-86` 的 `_patched_settings_init()` 是一份**手工复制的字段列表**，从未同步更新 → 缺这六个属性 → `AttributeError` → 文件被截断成空；
4. `except Exception` 把异常降级成一行日志。

**证据（测试套件层面）**：`tests/unit/test_settings.py` 有 4 个用例因此**长期失败**：

```
FAILED tests/unit/test_settings.py::TestSettingsBasic::test_save_and_load
FAILED tests/unit/test_settings.py::TestSettingsBasic::test_window_size_serialization
FAILED tests/unit/test_settings.py::TestSensitiveEncoding::test_password_encoded
FAILED tests/unit/test_settings.py::TestSensitiveEncoding::test_password_decoded_on_load
========================= 4 failed, 1 passed =========================
```

我确认过这**不是**我的沙箱环境导致的（改用可写 `--basetemp` 后仍然失败），而是真实缺陷。也就是说：CHANGELOG 声称的"覆盖率 37.30%"与"测试数 581"对应的套件，此刻 `test_settings.py` 是红的——而它的失败恰恰暴露了上面这个数据摧毁路径。

**影响**：
- 真实用户路径下，只要 `save()` 期间出现任何异常（属性缺失、磁盘满、序列化失败、并发写），**设置文件被清空**，下次启动云配置、AI Key、最近文件、会话全部丢失。`load()` 也有宽 `except` → 静默回退默认值，用户看到的是"我的设置全没了"。文件 `~/.beeoffice_settings.json` 现存 1235 字节。
- 这个模式在项目里反复出现：`tab_manager`、`template_manager`、`pdf_annotator` 的 `.beeanno` 写盘都是"直接 `open(...,"w")` + `json.dump`"，**全部非原子写**。

**修复建议**：
1. **立即**：`save()` 改为"先在内存构造完整 dict（在 `open` 之前），再原子写"：

   ```python
   payload = {...}                                   # 先构造，失败就失败在这里
   tmp = self.path.with_suffix(".tmp")
   with open(tmp, "w", encoding="utf-8") as f:
       json.dump(payload, f, indent=2, ensure_ascii=False)
       f.flush(); os.fsync(f.fileno())
   os.replace(tmp, self.path)                        # 原子替换
   ```
2. 用 `getattr(self, "ai_api_key", "")` 或 `dataclasses`/显式字段表消除"字段名单三处复制"的问题；
3. `conftest.py` 的 fixture 改为 `monkeypatch.setattr(AppSettings, "path", ...)`，**不要复制 __init__ 实现**；
4. 把 `except Exception` 改为至少 `QMessageBox` 告警（"设置保存失败"），不能静默。

---

### 3.3 【严重·实测】"导出 PNG 图片序列"永不产出文件，却报成功

```python
# beeoffice/plugins/beeshow_export_mixin.py:401-418
def capture(page, idx=i, out=output_dir, view=temp):
    try:
        page.grab().save(str(Path(out) / f"slide_{idx+1:03d}.png"))   # ← page 是 QWebEnginePage
    except Exception as e:
        logging.error(f"截图失败 slide {idx+1}: {e}")                  # ← 只写日志
    finally:
        ...
        if idx == total - 1:
            QMessageBox.information(self, "导出成功", f"已保存到: {output_dir}")   # ← 照样报成功

temp.page().loadFinished.connect(lambda ok, t=temp, idx=i: capture(t.page(), idx))
```

`capture()` 收到的 `page = temp.page()` 是 **QWebEnginePage**，而 `grab()` 只存在于 `QWidget`/`QWebEngineView` 上。本机反射验证：

```
QWebEnginePage has grab: False
members containing grab: []
```

**影响**：README 宣称的"导出 … PNG 图片序列"是**功能不存在 + 假成功提示**。用户得到空目录和"已保存到: …"的成功弹窗，会以为文件丢了或去找 IT。

**修复**：改用 `temp.grab()`（视图对象），并把成功提示建立在**实际写入结果**上：

```python
def capture(view=temp, idx=i, out=output_dir):
    ok = False
    try:
        ok = view.grab().save(str(Path(out) / f"slide_{idx+1:03d}.png"))
    except Exception as e:
        logging.exception(...)
    ...
    if idx == total - 1:
        (QMessageBox.information if ok else QMessageBox.warning)(...)
```

另外 `temp` 从未 `show()`，隐藏 widget 的 `grab()` 在某些平台会拿到空白帧【推断】，建议 `temp.show()` 后再截或在 `loadFinished` 后延时。

---

### 3.4 【高·实测】启动后界面冻结 7–9 秒

```python
# beeoffice/app.py:153
QTimer.singleShot(50, self._lazy_load_modules)      # 窗口已显示，50ms 后在主线程执行

# beeoffice/app.py:399-409
def _lazy_load_modules(self):
    from beeoffice.plugin_manager import PluginManager
    self.plugin_manager = PluginManager(self)
    self.plugin_manager.discover_plugins()          # ← 逐个 import plugins/ 下全部 86 个模块
    ...
```

实测：

```
import beeoffice.app:            1600 ms
plugin discover+load:            6610 ms   (热缓存)  / 9110 ms (冷)
TOTAL to usable plugins:         8262 ms
```

**为什么这么慢**：`discover_plugins()` 不区分"含插件的模块"与"普通实现模块"，把 `beesheet_data_mixin.py`、`beeshow_image_editor.py`、`bee_export.py` 等全部 import 一遍，连带拉起 matplotlib / fitz / docx / pandas / QtWebEngine。

**影响**：用户看到主窗口出现后，界面无响应 7–9 秒（Windows 会显示"未响应"）。README 自称"轻量、快速"，实测与该定位矛盾。而项目其实已经有 `async_task.py` 的线程池可用。

**修复建议**：
1. 插件发现改为阅读 `plugins/` 下的**清单**（如 `plugin.json`）或只 `iter_modules` 拿名字、不做全量 import；用 `importlib.util.find_spec` 判断而非执行；
2. 至少要移到后台线程（`AsyncTaskManager.run`），发现完成后通过信号回主线程注册；
3. 真正的懒加载：只有用户打开蜜算/蜜演时才 import 对应模块；
4. `QtWebEngine` 应在 `QApplication` 创建**之前**设置 `Qt.AA_ShareOpenGLContexts` 并调用 `QtWebEngineQuick.initialize()`（全仓 grep 无这两处，与实测到的 "Attribute Qt::AA_ShareOpenGLContexts must be set before QCoreApplication is created" 告警一致）。

---

### 3.5 【高·代码】打开 `.docx` 后 Ctrl+S 原地覆盖原文件

```python
# beeoffice/app.py:549-550   打开 DOCX 的回调里
widget._doc_kind = "word"
widget._current_file_path = path          # ← 记成原始 .docx 路径
```

```python
# beeoffice/plugins/beewrite_export_mixin.py:258-262
def _save_as_docx(self) -> bool:
    current = getattr(self, "_current_file_path", None)
    if current and current.lower().endswith(".docx"):
        return self._write_docx(current)      # ← 直接写回同一个文件
```

而 `_write_docx` → `_rich_to_docx`（`beewrite_export_mixin.py:804-932`）是一个**保真度很低的重建**，从 `QTextDocument` 重新生成 docx，至少丢失：

- **超链接**（只设颜色下划线，从不读 `isAnchor`）
- **列表编号/项目符号**（不生成 `w:numPr`）
- **页眉/页脚/页码/水印/脚注/批注/域/章节**
- **东亚字体**（只设 `run.font.name`，无 `w:eastAsia` → 中文回退到默认西文字体）
- **表格单元格内除第一段以外的全部内容**（用 `cell.firstCursorPosition().block()`）
- 文本框（QTextFrame 被当普通段落压平）

**影响**：用户"打开 Word 文档 → 改一个字 → Ctrl+S"，原始文件被一个低保真副本**永久替换**，无备份、无"另存为"确认、无警告。这是不可逆的数据破坏。

**修复建议**：
1. 打开 `.docx` 后**不要**把 `_current_file_path` 设为源文件；或设置一个 `_source_docx` 只读引用；
2. `_save_as_docx()` 遇到"源是 docx"时必须**提示**：原文件将被重新生成、格式可能丢失，并提供"另存为"默认选项；
3. 保存前自动写 `.bak`；
4. 长期：用 python-docx 做**增量修改**，而不是整体重建。

---

### 3.6 【高·代码】页边距单位三处不一致，默认导出边距错 10 倍

| 位置 | 代码 | 把存储值当作 |
|---|---|---|
| `beewrite.py:143-150` | `margin_top = 2.54`, `margin_left = 3.17` | （字面像 **cm**：2.54cm=1英寸、3.17cm=1.25英寸，正是中文 Word 默认值） |
| `beewrite_doc_mixin.py:198-219` | `value / 10` 显示 | **mm** → 对话框初始显示 0.25 cm |
| `beewrite_export_mixin.py:843-850` | `section.top_margin = Mm(page_settings.get("margin_top", 25.4))` | **mm** → 实际写入 **2.54 mm** |
| `beewrite_export_mixin.py:415-423` | `margin_top * 0.264583`（px→mm） | **px** → PDF 输出 **0.67 mm** |

对照代码里的 fallback 默认值 `25.4 / 31.7`（典型的 mm 表示）与 `tests/qt/test_export_pdf.py:19-26` 使用的 `25.4`，可以确认**设计意图是 mm**，`beewrite.py:146` 的 `2.54` 是错的。

**影响**：导出的 DOCX 上下边距约 2.5mm（几乎贴边），PDF 约 0.7mm；页面设置对话框一打开就显示错误的 0.25cm。用户在 UI 里改也无法自洽。

**修复建议**：统一以 **mm** 为唯一存储单位（改 `beewrite.py:143-150` 为 `25.4/31.7`），显示层与导出层都直接用 mm；PDF 的 `* 0.264583` 删除。补一个"导出后读取 docx section 属性断言边距"的测试。

---

### 3.7 【中·代码】其他已确认的数据/功能缺陷（摘要）

| 缺陷 | 位置 | 说明 |
|---|---|---|
| 蜜算自动保存失败完全静默 | `beesheet.py:1003-1004` | `except Exception: pass` → 用户以为有备份其实没有 |
| 蜜算表格明文长期驻留主目录 | `beesheet.py:991-998` | `~/.beeoffice_backups/*.json`（最近 10 份），关闭文档/程序都不清理，含完整表格内容 |
| "文本转数字"的撤销执行的是去空格 | `beesheet_data_mixin.py:242` + `TrimCommand.execute:78` | 复用 `TrimCommand` 当撤销载体，撤销语义完全错误 |
| 填充/复制把 `LOG10` 改写成 `LOH10` | `beesheet_utils.py:49` | 正则把含数字的函数名误判为单元格引用 → **静默产出错公式** |
| 循环引用无检测 | `beesheet_engine.py` 全文 | `=A1→=B1→=A1` 返回公式文本；`_recalc_formulas(max_rounds=3)` 硬编码 3 轮，不收敛也不报错，错误值不写回 → 单元格留陈旧数字 |
| 跨表引用整体失效 | `beesheet_engine.py:105-112` | `=S2!A1` → 0，`=SUM(S2!A1:B1)` → 0（静默返回 0） |
| `ABS/SQRT/PI/RAND` 全部不可用 | `beesheet_engine.py:191-194` | `math_funcs` 调用参数个数与 lambda 签名不匹配，且这 4 个都在 UI 函数参考表里 |
| 宏录制/播放零实现 | `beesheet_plugin.py:302-330` | 只有 `hasattr` 守卫，`BeeSheetView` 根本没有这两个方法 → 点了只弹"当前表格不支持宏录制" |
| 冻结窗格是假实现 | `beesheet_context_menu_mixin.py:128-147` | 只把列宽模式设为 `Fixed`，无任何滚动冻结效果（`beesheet.py:151` 注释自认"冻结视图（禁用）"） |
| 自然语言"如果…就显示X"真假日同值 | `nl_formula.py:170-175` + `_extract_value:237-241` | 兜底分支无条件返回第一个引号内容 → `如果A1大于10就显示'高'` 生成 `=IF(A1>10,"高","高")`。**而 `nl_formula.py:14-15` 的 docstring 宣称"本次更新修复 IF 公式中真假值都是同一个值的问题"** |
| 批注/书签只写不读 | `beewrite_export_mixin.py:206-217` vs `beewrite_comment.py:98-109` | 保存时写 `.comments.json`/`.bookmarks.json`，打开时从不调用 `load_from_file` → **重开文档批注书签全丢** |
| 页眉页脚是假功能 | `beewrite_doc_mixin.py:74-89` | 把 `<!-- header: X -->` 当**普通文字**插进正文，提示文案却写"导出 Word 时生效"；全仓无任何消费者；而 `set_markdown` 会跳过 `<!--` 行 → 切模式即丢 |
| HTML 导出不可达 | `app.py:864-867` + `menus.py:212` + `commands.py:49` | `BeeWriteEditor` **没有** `export_html` 方法，`hasattr` 判断失败 → 静默什么都不做 |
| 激光笔/画笔全是桩 | `beeshow_play_mixin.py:420-433` | 全仓 `beeshow*` 无 `mouseMoveEvent`/`mousePressEvent`；L 只切一个静止红点，P 只翻转没人读的布尔量 |
| 同步演示观众看不到画面 | `sync_server.py:612-626` | `set_slides_html()` **全仓无调用方** → `/api/slide/N` 恒返回 `"<p>（无此页）</p>"`，页码却在跳 |
| 版式应用会清空整份文档 | `beeshow_layout_mixin.py:154-156` | `self._editor.setPlainText(skeleton)`，无确认、无撤销、不限于当前页 |
| 表格"插入列"参数写反 | `beeshow_table_mixin.py:246-247` | `setItem(insert_at, r, item)`，实测签名为 `setItem(row, column, item)` → 空 item 覆盖第 `insert_at` 行各列，**静默丢数据** |
| 编辑已有表格会删掉中间正文 | `beeshow_table_mixin.py:530-549` | 表格范围取"第一个 `\|` 行"到"最后一个 `\|` 行"，中间正文被整体删除 |
| 动态数字在 PDF/PPTX 中恒为 0 | `beeshow_export_mixin.py:104-111` | 导出时对**已渲染**HTML 跑 `{{number:...}}` 正则（0 命中），正文是硬编码的 `0` |
| PDF 导出成功提示早于落盘 | `beeshow_export_mixin.py:276-282` | `printToPdf` 是异步的，紧接着就弹"导出成功" |
| PDF 批注颜色不落盘 | `pdf_annotator.py:160-172` | PyMuPDF 的 annot API 需 `set_colors()`，代码只把颜色用于屏幕叠加层 → 烧录永远是库默认色 |
| 未保存批注关窗即丢 | `pdf_annotator.py` 全类 | **没有 `closeEvent`** → 未"保存批注/烧录"的批注静默丢失；`.beeanno` 无版本、`from_dict` 缺键即 KeyError 导致整份批注读不出来 |
| 自动保存可能弹模态"另存为" | `app.py:356-364` + `beewrite_export_mixin.py:178-184` | 每 5 分钟对当前标签调 `save()`，无路径时走 `QFileDialog` → 打字中被弹窗打断【推断】 |

---

## 4. 安全审计

严重程度：**严重 / 高 / 中 / 低 / 信息**。

### 4.1 【严重】移动端 HTTP 服务：`0.0.0.0` + 零认证 + CORS `*`

```python
# beeoffice/mobile.py:99
server = _ThreadingHTTPServer(("", port), handler)      # "" = INADDR_ANY = 0.0.0.0
```

```python
# beeoffice/mobile.py:274-284
def do_GET(self):
    if self.path.startswith("/api/docs"):   self._handle_docs_api()
    elif self.path.startswith("/api/view/"): self._handle_view_api()
    else: super().do_GET()
```

```python
# beeoffice/mobile.py:296 / 315
self.send_header("Access-Control-Allow-Origin", "*")
```

**问题**：服务对局域网完全开放、无任何鉴权、无来源校验，而 `Access-Control-Allow-Origin: *` 使**同机浏览器中的任意网页**都能 `fetch('http://127.0.0.1:8888/api/docs')` 并读取响应体（Firefox/Safari 及旧版浏览器不拦；Chrome 的 Private Network Access 预检可能拦截读取，但请求本身仍会发出）。`/api/view/<id>` 的 id 就是标签页序号，遍历即可拖走**当前所有已打开文档的渲染后正文**。

**修复**：默认绑 `127.0.0.1`；启动生成 `secrets.token_urlsafe(16)` 一次性 token 并要求 `?t=` 或 `Authorization`；**删除 CORS 头**；校验 `Host` 头（防 DNS rebinding）；提供"停止服务"按钮与超时自动停止。

**注意**：`tests/unit/test_mobile_api.py:66` 把监听地址改成 `127.0.0.1` 来测试——**这掩盖了生产路径的 `0.0.0.0` 绑定**，应补一条断言生产绑定的测试。

### 4.2 【严重】蜜演远程同步服务：`0.0.0.0:8765/8766`，零认证

```python
# beeoffice/plugins/beeshow_sync_server.py:177
def __init__(self, http_port=8765, ws_port=8766, host: str = "0.0.0.0", ...)
# 调用侧不覆盖 host：beeshow_sync_mixin.py:73-76  SyncServer(http_port=8765, ws_port=8766)
```

HTTP 与 WebSocket 都监听全部网卡；UI 主动把 `http://<局域网IP>:8765/sync` 展示给用户去扫码（`sync_mixin.py:195-205`）。`/api/info`、`/api/slide/<idx>` 三个响应都带 `Access-Control-Allow-Origin: *`；WebSocket 握手只做 RFC6455 的 `Sec-WebSocket-Key → Accept`，**不校验 Origin/token**。

**另外的资源耗尽面**（LAN 可达 ⇒ 真实可利用）：
- `_ws_accept_loop` 对每个连接无条件起一个线程，**无连接数上限、无速率限制、握手无超时**（`sync_server.py:399-431, 479-486`）——恶意客户端只发一半请求头即可挂住一个线程。
- `broadcast()` 逐个 `viewer.send()` → `socket.sendall()`（`sync_server.py:541-547`），而广播是从 **UI 线程**发起的（`_show_slide` → `_broadcast_slide`）→ TCP 背压下不读数据的观众能**卡死演示者界面**。
- 启动竞态：`start()` 先起 WS 线程（`:221`）之后才 `self._running = True`（`:223`），accept 循环条件 `while self._running:` → 线程抢先求值则整个 WS 服务静默失效。
- `ViewerHandler` 只重写了 `do_GET`，**继承的 `do_HEAD` 仍然可用**（CPython `http.server` 行为），可枚举进程 CWD 树下文件/目录的存在性、大小、修改时间（`translate_path` 会丢弃 `..`，取不到内容）。

**修复**：默认 `127.0.0.1` 或显式"允许局域网"开关；会话级随机 token（二维码携带）；校验 `Origin`/`Host`；连接数上限与握手超时；`broadcast` 移出 UI 线程（队列 + 单发线程）；提供自动停止。

### 4.3 【高】云凭据仅 Base64 编码

```python
# beeoffice/settings.py:77-95
def _encode(self, s):
    """Base64 编码敏感信息"""
    return base64.b64encode(s.encode("utf-8")).decode("utf-8")
```

落盘字段：`webdav_pass`(:237)、`cloud_config.password`/`access_token`(:217-218)、`ai_api_key`(:249)、`unsplash_api_key`(:255)、`pexels_api_key`(:258)。全仓无 `keyring`、无 DPAPI/`win32crypt`、无 `cryptography`，也无 `chmod`/`umask`。

`CHANGELOG.md:280` 把"**Base64 编码**：WebDAV 密码、云存储 Token 编码存储"列在 `#### 安全` 标题下——这是对安全性的错误表述。任何以该用户身份运行的进程（含被投毒的依赖、第三方插件）都能直接读出明文凭据；Linux/macOS 下默认 umask 022 会让同机其他用户可读。

**修复**：Windows 用 DPAPI（`CryptProtectData`），macOS 用 Keychain，Linux 用 Secret Service（或用 `cryptography.Fernet` + 机器绑定密钥并明确文档说明）；保存后 `os.chmod(path, 0o600)`；修正 CHANGELOG 措辞。

**另**：遗留模块 `plugins/webdav_sync.py:142,159-161` 把密码**明文**写入 `~/.beeoffice_webdav.json`（连 Base64 都没有）。该模块已无 UI 入口（`menus.py:396` / `commands.py:75` 都指向 `cloud_settings`），但仍随包发布且可被 import。**建议直接删除** `beeoffice/webdav.py` 与 `WebDAVConfig`。

### 4.4 【高】插件市场：无签名/哈希/权限模型，安装即持久化任意代码执行

```python
# beeoffice/plugins/plugin_market.py:355-360
@staticmethod
def _contains_plugin_class(py_file: Path) -> bool:
    content = py_file.read_text(encoding="utf-8", errors="ignore")
    return "Plugin" in content and "class " in content        # ← 子串匹配
```

```python
# beeoffice/plugins/plugin_market.py:256-286
zf.extractall(tmp_dir)                                        # 无大小/数量上限（zip bomb）
...
dest = plugins_dir / py_file.name                             # 直接落进应用 plugins 目录
shutil.copy2(py_file, dest)
```

```python
# beeoffice/plugin_manager.py:36-42     下次启动
for module_info in pkgutil.iter_modules([str(plugins_path)]):
    module = importlib.import_module(f"beeoffice.plugins.{module_info.name}")
```

判别条件只是"文件里含 `Plugin` 和 `class ` 两个子串"——写进注释即可通过。`plugin_base.py` 没有任何权限/能力声明，插件构造函数直接拿到 `self.parent`（= `BeeApp`），从而拿到 `settings`（含凭据）、`tab_manager`、以及完整文件系统与网络能力。

**恶意插件可做的事**（均由代码事实直接推出）：读取 `~/.beeoffice_settings.json` 并解码出 WebDAV 密码/OAuth token/AI Key；读取 `~/.beeoffice_backups/*.json` 全部表格数据；任意文件读写与网络外发；覆盖 `beeoffice/plugins/` 下任何同名模块实现持久化。用户侧唯一屏障是"点击安装"这个动作和文件覆盖确认框。

**修复**：定义 `plugin.json` 清单（id/version/api_version/permissions/sha256/签名），安装前校验哈希与签名（Ed25519 + 内置公钥）；未签名插件必须二次确认并展示所需权限；插件改放用户目录（`%APPDATA%\BeeOffice\plugins`）；引入白名单门面 API 而非直接给 `parent`；**禁止覆盖已有模块，只允许新增文件**；解压前校验 `ZipInfo.file_size` 总量与成员数（如 ≤20MB/≤50 个），并用 `filter="data"`（Python 3.12+）。

**Zip Slip 澄清**：解压**不存在** Zip Slip（CPython 的 `_extract_member` 已剥离盘符/绝对路径/`..`，符号链接成员被写成普通文件），且安装只按 `py_file.name`（basename）落盘——这一点是安全的。

### 4.5 【中高】WebDAV 冲突检测 fail-open，静默覆盖远端新文件

```python
# beeoffice/plugins/webdav_sync.py:127-138
def _check_conflict(self, client, local_path, remote_path):
    try:
        remote_dt = datetime.strptime(remote_mtime, '%a, %d %b %Y %H:%M:%S %Z')
        ...
    except: return "unknown"                  # ← 裸 except
```

调用方只把 `remote_newer` 当"跳过上传"（`:82-87`），`unknown` 会继续执行覆盖。而 `%Z` 在 Windows/C locale 下只匹配本机时区名，服务端返回 `... GMT` 时会抛异常 → 返回 `unknown` → **直接覆盖远端**。这正是该模块声称要防止的数据丢失。裸 `except:` 还会吞掉 `KeyboardInterrupt`/`SystemExit`。

**修复**：未知/解析失败按"不安全"处理（跳过并提示，绝不默认覆盖）；改用 `email.utils.parsedate_to_datetime()`；冲突时保留双份（`file.conflict-2026xxxx`）；裸 `except:` 全部改 `except Exception:` 并记录。

### 4.6 【中】"云同步"名不副实：单向、无加密、无过滤、无冲突处理

```python
# beeoffice/app.py:1148-1160
def sync_files():
    local_dir = Path.home() / ".beeoffice_data"
    remote_dir = "/beeoffice"
    for file in local_dir.rglob("*"):
        ...
        if not storage.upload(str(file), remote_path):
```

**只有 upload**：`cloud_sync/*` 的 `download()` 从未被调用过。启动 3 秒后自动执行（`app.py:156` + `:1191-1198`）。而 `~/.beeoffice_data` 在全仓库只此一处被引用 → 实际同步内容基本为空。

**影响**：(a) 用户勾选"云同步"后得到"同步完成"的假象，却没有任何文档被备份或恢复；(b) 该目录内未来任何内容都会**明文**上传到用户的 WebDAV/OneDrive/Google Drive，无白名单、无加密。

**修复**：实现双向同步并接入冲突策略；上传前按扩展名/大小白名单过滤，禁止密钥类文件；UI 明示同步方向与目录，把"同步完成"改为具体计数（上传 N / 下载 M / 跳过 K）。

### 4.7 【中】移动端与观众端的 XSS

```python
# beeoffice/mobile.py:324-329
import markdown
return markdown.markdown(content, extensions=["tables", "fenced_code", "nl2br"])
```

```javascript
// beeoffice/mobile.py:223
<div class="content">${data.html}</div>          // innerHTML 注入
```

`markdown` 默认**放行原始 HTML**且无净化。用户从邮件/聊天收到一个 `.md` 并在桌面端打开，再在手机上"查看"，文档里的 `<img src=x onerror="...">` 会以本地服务同源身份在手机浏览器执行：读取 `/api/docs` 拿到全部文档并外传。观众端同样（`beeshow_sync_viewer.py:333`）。

**修复**：服务端用 `nh3`/`bleach` 白名单净化，并加 `Content-Security-Policy: default-src 'none'; ...` 与 `X-Content-Type-Options: nosniff`；观众端改 `textContent`。

### 4.8 【中】AI 端点基址无校验 + 失败静默降级

```python
# beeoffice/plugins/beeshow_ai_service.py:136, 336-349
self.api_base = config.get("api_base", self.DEFAULT_API_BASE).rstrip("/")
url = f"{self.api_base}/chat/completions"
headers = {"Authorization": f"Bearer {self.api_key}"}
```

`ai_api_base` 用户可配置且**连 `http://`/`https://` 前缀校验都没有**（对比 `cloud_settings.py:159` 对 WebDAV 至少有前缀校验）。配成 `http://` 时 Bearer Key 与提示词明文过网，也没主机白名单。

`beeshow_ai_service.py:187-195`：AI 失败后 `logging.warning` + **静默降级为本地模板**（返回"背景/核心内容/数据支撑/总结"这类占位要点，`:453-490`），UI 不区分来源 → 用户会把占位内容当作 AI 输出直接用于演示。

另外：AI Key **没有任何 UI 入口**（`beeshow_notes_mixin.py:248` 提示"设置 → AI 服务"，但该菜单不存在；已 grep 确认无 `_show_ai_settings`）——用户必须手工编辑 `~/.beeoffice_settings.json` 并自己写 Base64。

**修复**：强制 `https://`（本机 `127.0.0.1` 场景显式确认开关）；返回值携带来源标记（`ai`/`local`/`error`），UI 明确提示；补真正的 AI 设置界面（Key 走密钥环）。

### 4.9 【中】未净化 HTML 进入 QtWebEngine

`beeshow_slide_mixin.py:227-230` 用 `markdown.markdown(..., extensions=['fenced_code','tables','md_in_html'])`——`md_in_html` 是**刻意**开启的（版式系统就依赖裸 `<div class="columns">`），且全仓**无任何** `QWebEngineSettings` 配置（JS 默认开启）。渲染这些内容的 `QWebEnginePage` 会把 `beeoffice://element-edit|image-edit` 路由回 Python 处理器（`element_editor.py:700-746`）。

⇒ **打开/导入一个不可信的 `.md` 演示文稿，即可让其中的脚本在嵌入的 Chromium 中执行**，并通过 `beeoffice://` 回调触发对 Markdown 源的改写，也可自由联网外泄幻灯片内容。完整链条依赖 Qt 默认的 `file://` 访问策略【推断，需实机验证】。

**修复**：对 Markdown→HTML 结果做白名单净化；`_preview.settings().setAttribute(QWebEngineSettings.JavascriptEnabled, False)` 并用受控通道（自行注入的脚本已可用 `runJavaScript` 管理）；`LocalContentCanAccessFileUrls=False`。

### 4.10 【低】其余

- `beeshow_video_mixin.py:376-388`：ffmpeg 的 `-i` 取自文档 HTML 的 `src` → 打开不可信文档再导出 PDF 可发起任意 URL 请求/读本地路径（列表传参已避免 shell 注入，但 ffmpeg 自身支持 `http://`/`concat:`/`file:`）。建议加 `-protocol_whitelist file` 并校验路径在文档目录内。
- `resources/template_manager.py:380`：在线模板的 `download_url` 取自 GitHub API 响应，未校验主机；`templates.py:83` 的 `QTextBrowser` 预览会加载远端图片（跟踪信标）。
- `crash_handler.py:11,113-116`：崩溃日志含文件绝对路径与异常文本（云同步异常可能带含凭据的 URL），弹窗却引导用户"把文件发送给开发者"的个人 QQ 邮箱，缺脱敏与告知。
- `plugins/git_manager.py:17-19`：`save_file()` 把 `filepath` 直接拼到 `repo_path`（绝对路径/`..` 可越出仓库）。**当前无调用方**（死代码）。
- `beeshow_pptx_engine.py:67-68`：未使用的 `subprocess`/`tempfile` 死导入。

### 4.11 做得好的地方（已确认）

- 全仓**无** `verify=False` / `ssl._create_unverified_context` / `import ssl`，requests 与 urllib 都走默认证书校验。
- 全仓**无** `pickle` / `marshal` / `yaml.load`；无 `shell=True` / `os.system`，所有 subprocess 均为列表传参。
- **无任何硬编码密钥/Token/私钥**（对 `sk-*`/`ghp_*`/`AIza*`/`AKIA*`/`BEGIN PRIVATE KEY` 全量 grep 无命中）。
- 凭据不写日志（只有 "access_token 为空" 这类不含值的提示）。
- `ai_assist.py` + `beewrite_ai_mixin.py` 全部为**本地规则实现**（正则/词表），完全不联网，蜜写的"AI 辅助"不会外发文档（代价是名不符实，见 §5）。
- Google Drive 查询做了 `_escape_query`（转义 `\` 与 `'`），避免 Drive 查询注入。
- `utils.safe_filename()` / `template_manager._safe_filename()` 对文件名做了非法字符/控制字符/长度处理。
- `mobile.py` 已移除历史上的 `os.chdir()` 劫持（有回归测试）。
- `.gitignore` 覆盖 `.env`/`.coverage`/日志/发布产物/用户数据文件。
- 插件包解压不存在 Zip Slip（见 §4.4 澄清）。

---

## 5. 功能宣称 vs 实现（README / CHANGELOG 对账）

### 5.1 README 宣称但代码里是空壳/桩/假实现的

| README 宣称 | 实际情况 |
|---|---|
| 蜜算"宏录制与播放" | **零实现**，只有 `hasattr` 守卫壳，点击弹"当前表格不支持宏录制" |
| 蜜算"冻结窗格" | **假实现**，只把列宽模式设为 `Fixed`，无滚动冻结效果 |
| 蜜写"页眉页脚" | **假实现**，把 `<!-- header: X -->` 当正文文字写入，无任何消费者 |
| 蜜写"导出 HTML" | **不可达**，编辑器无 `export_html` 方法，菜单/命令静默空转 |
| 蜜写"批注 / 书签" | 能写盘但**打开时从不读回** → 重开文档即丢失 |
| 蜜写"修订模式" | 非 Word 修订：拒绝修改用 `setPlainText(baseline)`，**丢失全部富文本格式** |
| 蜜演"导出 PNG 图片序列" | **永不产出文件却报成功**（§3.3） |
| 蜜演"导出 GIF" | 只是把纯文本画到 1024×768 白底图上，无主题/颜色/图片/表格/版式 |
| 蜜演"激光笔 / 画笔" | **全为桩**，无任何鼠标事件处理 |
| 蜜演"远程同步/扫码跟随" | 观众端**画面永远是空的**（`set_slides_html` 无调用方），只有页码在跳 |
| 蜜演"动态数字" | 预览可用，**PDF/PPTX 导出恒为 0** |
| 蜜演"平滑动画" | 死的（播放窗口每翻一页 `setHtml` 换整份文档） |
| 蜜写"AI 辅助写作" | 本地规则实现，非 AI（`beewrite_ai_mixin.py:17` 自认"无外部 API 依赖"） |
| 蜜写"任务列表" | 未启用 markdown 的 tasklist 扩展 |
| 蜜算"数据清洗（空值处理）" | 只有去重/去空格/转数字/分列，**无任何 fillna/dropna 入口** |
| "云同步" | 只有单向上传一个基本为空的目录（§4.6） |
| "轻量、快速" | 启动后界面冻结 7–9 秒（§3.4） |

### 5.2 CHANGELOG 记录了但代码里不存在的

- **`.github/workflows/test.yml`（Windows-only CI）**：仓库内**无 `.github` 目录**。
- **`LICENSE`**：README 标注 MIT，仓库内**无该文件**。

### 5.3 CHANGELOG 声称"已修复"但实际未修复

这是本项目最需要警惕的一类问题——**文档给出了虚假的安全感**：

| CHANGELOG 声称 | 事实 |
|---|---|
| v5.0.1：「修复公式引擎 IF/AND/OR/NOT/IFS 可执行任意 Python 代码的安全漏洞（改用 AST 白名单求值）」 | 只修了 `_safe_eval`；另两处裸 `eval()` 仍在，其中 `beesheet_engine.py:107` **已被实际利用成功**（§3.1） |
| v5.0.0：「修复 `_check_conflict` 定义了但从未调用，双向同步会覆盖新文件」 | `_check_conflict` 确实被调用了，但它 **fail-open**：日期解析失败返回 `unknown` 后照样覆盖（§4.5） |
| v5.0.0：「去除所有 `except: pass`，改为 `logging.error` 记录」 | 全仓仍有 **15 处裸 `except:`**（`beesheet_engine.py` 8 处、`beesheet_model.py` 3 处、`webdav_sync.py` 3 处……）和大量 `except Exception: pass` |
| v5.0.0：「移除 `settings.py` 中直接明文存储密码的方式」 | 改为 Base64——**不是加密**，且新增了 3 个同样处理的 API Key（§4.3） |
| v5.0.6：「测试数：483 → 581，覆盖率：34.54% → 37.30%」 | 实际 `--collect-only` = **710**；而 `tests/unit/test_settings.py` 有 **4 个用例长期失败**（§3.2）；且 CHANGELOG 第 9-22 行把改这些数字的脚本本身粘进了文档 |
| v5.0.1：「app.py 从 500+ 行拆分为多个职责单一模块」 | 实际 **1414 行 / 87 个方法** |
| `nl_formula.py:14-15`：「本次更新修复 IF 公式中真假值都是同一个值的问题」 | **bug 依然存在**（`如果A1大于10就显示'高'` → `=IF(A1>10,"高","高")`），`nl_formula.py:317` 自报的期望样例也是错的 |

### 5.4 版本号不一致

`__version__.py` = 5.0.4，README badge = 5.0.2，CHANGELOG 最新 = 5.0.6，代码注释提到 v5.1/v5.2 任务。用户无法从任何一个地方确定"我装的是哪一版"。

---

## 6. 测试与工程质量

### 6.1 测试套件的实际状态

| 指标 | 值 |
|---|---|
| 测试文件 | 71 个（unit 14 / qt 11 / regression 39 / smoke 2 + helpers） |
| `--collect-only` | **710 个** |
| `tests/unit` + `tests/smoke` | **464 passed / 4 failed**（失败全部在 `test_settings.py`，见 §3.2）【实测】 |
| `tests/qt` 单独运行 | **97 passed / 17.25 s**【实测】 |
| 全量 `tests/` 一次性运行 | **进程原生崩溃**（非断言失败）：两次运行分别崩在 `tests/qt/test_beewrite_ai_mixin.py` 与 `tests/regression/p0/test_p0_05_safe_eval_boundary.py` 附近，而这两个文件**单独运行都通过** → 属**测试间污染 / 顺序依赖**，不是单点缺陷【实测，崩溃点两次不同，故不宜归因到某个具体用例】 |
| 覆盖率 | CHANGELOG 声称 37.30%（`coverage.xml` 存在，805KB） |

**测试方法学问题**（比失败数量更值得关注）：

1. **大量"存在性断言"式的烟雾测试**。`tests/test_smoke_beeshow.py:90-221, 322-342` 主体是 `assert hasattr(obj, 'method')`——**功能完全失效也能全绿**。
2. **恒真断言**。`tests/qt/test_md_conversion.py::test_empty_heading_not_output` 永远无法失败，因为 `to_markdown` 在 heading 分支**之前**就对空文本 `continue` 了（`beewrite_rich_editor.py:507-511`）。
3. **从不检查产物**。`test_p0_04_beeshow_webengine.py:31-58` 只断言 `_export_pdf` 后 `_export_views` 非空，**不检查是否真的产出了文件**——这正是 PNG/GIF/PPTX 导出缺陷得以逃逸的通道。`tests/qt/test_export_pdf.py` 只断言注入字符串含 `210mm`/`counter(page)`，**从不调用 `export_to_pdf`、不断言 margin** → 测不出 §3.6 的 10 倍边距 bug。
4. **测的是死代码**。`tests/unit/test_formula_engine.py:29` 导入的是 `formula_engine.py`（生产零引用），而非真正在用的 `beesheet_engine.py`。
5. **安全测试只覆盖已加固路径**。P0-5 的两个测试文件构造的都是 `IF(...)`，从未构造含 `!` 的公式，也从未触及第二个引擎 → 漏掉了 §3.1 的 RCE。
6. **用 Fake 自证**。`tests/regression/p1/test_p1_14_pdf_undo.py` 用自实现的 Fake 类测试同义反复；同目录 `test_p1_14_pdf_undo_real.py:5-7` 的注释自己指出了这一点（后者是好的）。
7. **测试掩盖生产行为**。`tests/unit/test_mobile_api.py:66` 把监听地址改成 `127.0.0.1`，掩盖了生产代码的 `0.0.0.0` 绑定。
8. **fixture 复制产品实现**。`conftest.py:63-86` 手工复制了 `AppSettings.__init__` 的字段列表，产品类一加字段测试就崩（§3.2）——这是 §3.2 那个数据摧毁 bug 的直接触发器。

### 6.2 代码质量量化

| 指标 | 值 |
|---|---|
| 模块数 / 总行数 | 118 / **36 948** |
| 最大模块 | `beesheet_engine.py` 1444 行、`beesheet_data_mixin.py` 1292、`app.py` 1224、`beewrite_rich_editor.py` 1130、`beewrite_export_mixin.py` 1027 |
| 最大类 | `FormulaEngine`（`beesheet_engine.py`）**119 个方法**；`BeeApp` 87 个方法；`BeeSheetView` 42 + 8 个 Mixin 共约 170 |
| 最大方法 | `UIMixin._build_all_toolbars` **243 行**、`BeeWriteEditor.__init__` 245 行、`_rich_to_docx` 129 行、`_qtexttable_to_docx` 123 行 |
| 文档字符串是版本日志的模块 | **45 / 118** |
| 裸 `except:` | **15 处** |
| `except Exception` | **446 处** |
| 库代码里的 `print()` | **66 处** |
| TODO/FIXME/HACK | **0 处**（全部改写为"任务 x.y"注释） |
| 死代码模块 | `formula_engine.py`（569 行）、`beeoffice/webdav.py` + `plugins/webdav_sync.py`、`plugins/git_manager.py` |

**具体死代码清单**（部分）：
`SheetDataModel.MIN_ROWS`、`_real_rows`（只写不读）、`ChunkLoader.progress`（信号从不 emit）、`ChunkLoader.chunk_ready.total_chunks`（恒为 -1）、`LargeFileLoader.chunk_ready`（未被连接）、`ViewMixin._undo/_redo`、`CommentManager.load_from_file/clear/to_dict`、`BookmarkManager.load_from_file/update_position`、`CrossRefManager.get_headings/has_headings`、`RevisionManager.baseline`、`bee_export.export_to_md`（仅测试）、`bee_export.export_html_to_docx`（零调用）、`beeshow._css_cache`/`_preloaded_slides`/`_ai_service`/`_pptx_engine`/`_font_embedder`（恒 None）、`pdf_annotator._note_editor`、`beesheet_plugin._generate_chart_fallback`/`_nl_to_formula_fallback`（永不执行）。

**一处语法性手误**：`beesheet_engine.py:1310` 有一行**孤立的续行反斜杠**（该行内容恰为 `\`），位于 `get_errors` 与 `clear_errors` 之间。它是合法的行续接（`compile()` 无错），属残留。

### 6.3 公式引擎的质量剖面（BeeSheet 深度分析摘要）

引擎是"**正则前缀分派 + 正则重写 + Python eval**"的伪解析器，不是 tokenizer/AST。实测行为：

| 输入 | 返回 | 应有 |
|---|---|---|
| `=2^10` | `'2^10'`（字符串） | 1024 |
| `="a"&"b"` | `'"a"&"b"'` | `ab` |
| `=1=1` | `'1=1'` | TRUE |
| `=SUM(1)` / `=SUM(1,2,3)` | **0** | 1 / 6 |
| `=SUM($A$1:$A$3)` | **0** | 求和 |
| `=SUM(A3:A1)` | **0** | 求和（不归一 min/max） |
| `=SUM(S2!A1:B1)` | **0** | 跨表求和 |
| `=ABS(-3)` / `=SQRT(4)` / `=PI()` / `=RAND()` | `#ERROR: missing 1 required positional argument` | 3 / 2 / π / 随机 |
| `=SUM(A1:A2)`（A2=`#ERROR`） | `1.0`（**错误值不传播**） | `#ERROR` |
| `=ROUND(2.675,2)` | **2.67** | 2.68 |
| `=YEAR(45000)` | **2026**（`_parse_date` 失败静默返回 `datetime.now()`） | Excel 序列号换算 |
| `=TEXT(1.5,"0.00")` | `'1.5'`（**完全忽略格式串**） | `1.50` |
| `=FIND("z","abc")` | **0** | `#VALUE!` |
| `=RIGHT("abc",0)` | `'abc'`（`[-0:]`） | `""` |
| `=CEILING(-2.1,1)` / `=FLOOR(-2.1,1)` | `-2.0` / `-3.0`（**与 Excel 符号语义相反**） | -2.0 / -3.0 需按 Excel 规则 |
| 循环引用 `=A1→=B1→=A1` | `'=B1'`（公式文本当值） | 循环引用错误 |

函数数量：`_get_all_functions` 100 个 + `math_funcs` 11 个 = **111 个**（README 说"80+"，成立）；但 UI 函数参考表只有 86 项，**25 个引擎函数用户无法发现**；`_check_excel_compatibility` 的白名单还漏掉 `XMATCH/LET/SWITCH/XOR/MAXIFS/MINIFS/TEXTBEFORE/TEXTAFTER/VALUETOTEXT/IS*` → 已实现的函数被报"未在兼容列表中"（假阳性）。

**线程安全**：`FormulaEngine._error_trace` 是**类变量**（`beesheet_engine.py:35`）跨实例跨线程共享；`ChunkLoader.run` 在**后台线程**直接改 `_loaded_df`（`pd.concat`），而主线程 `data()` 正在 `_loaded_df.iloc` 读取——pandas 非线程安全，排队信号无法修复建模层竞态。

**`_full_df` / `_loaded_df` 漂移**：几乎所有编辑（删行列、列移动、批量转换、粘贴、填充、筛选）只写 `_loaded_df`，未加载行的 `get_value` 会回退到 `_full_df` → **编辑后滚到未加载区域会看到旧数据**。

### 6.4 参考：本次分析中遇到的 Windows 文件权限问题（环境事实）

工作区 `D:\beeofficeV` 及其**所有子目录**带不继承的 ACL，导致会话初始时任何命令都无法执行、`tests/pytest.log` 与 `__pycache__` 不可写。已通过 DSH 的 `diagnose-windows-sandbox-acl` 修复工作区**根目录**（为当前用户补上完全控制权，已验证 `writeOwner: false → true`）；子目录仍不可写，因此：

- 本次测试运行使用 `-o log_file=<可写路径>` 与 `-p no:cacheprovider` 绕开；
- 某些测试（`py_compile`、需要写 `tests/` 或 `beeoffice/plugins/__pycache__` 的）受此限制，**不构成产品缺陷**；
- 已确认 §3.2 的 4 个测试失败**与权限无关**（改用可写 `--basetemp` 后仍失败）。

**回滚命令**（如需恢复根目录原始权限）：

```
pwsh -NoProfile -File 'D:\dsh-acl-recovery\acl-backup-c53a49fb13cd48a3aa8dd5361b877705.json.ps1' -Path 'D:\beeofficeV' -AllowRoot 'D:\beeofficeV' -Restore 'D:\dsh-acl-recovery\acl-backup-c53a49fb13cd48a3aa8dd5361b877705.json'
```

调研报告存于 `D:\dsh-acl-recovery\acl-report-60e16c3f9ff34f46b63521221f16fbc6.jsonl`。

---

## 7. 修复优先级建议

### P0 — 立即（安全 + 数据完整性）

1. **堵住公式引擎的 RCE**：`beesheet_engine.py:107` 的裸 `eval` 改走 `_safe_eval`；删除死引擎 `formula_engine.py`（或同样加固）。补含 `!` 与属性穿透的负面测试。
2. **`AppSettings.save()` 改原子写**（先构造 payload，再 `temp + fsync + os.replace`），把 `except` 改为用户可见告警。顺手修 `conftest.py` 的 fixture 与 `tests/unit/test_settings.py` 的 4 个失败。
3. **修复"打开 `.docx` → Ctrl+S 覆盖原文件"**：打开时不设 `_current_file_path`，或保存时强制提示 + 自动 `.bak`。
4. **两个网络服务默认绑 `127.0.0.1`**（`mobile.py:99`、`beeshow_sync_server.py:177`），加大 `secrets` token 鉴权，**删除 `Access-Control-Allow-Origin: *`**，校验 `Host`/`Origin`。
5. **纠正 `beeshow_export_mixin.py:404` 的 `page.grab()` → `temp.grab()`**，并让成功提示基于真实写入结果。

### P1 — 近期（正确性 + 安全加固）

6. 插件发现不再 import 全部模块（清单/`find_spec`），并移出主线程 → 消除 7–9 秒启动冻结。
7. 凭据改用 DPAPI / Keychain / Secret Service；修正 CHANGELOG 中"Base64 = 安全"的表述。
8. 插件市场引入 manifest + 哈希校验 + 权限声明；禁止覆盖已有模块；解压加上限。
9. `beeshow_table_mixin.py` 两处数据破坏 bug（`setItem(insert_at, r, ...)` 参数顺序、`_replace_current_table` 的范围）；`beeshow_layout_mixin.py` 的"应用版式清空全文"加确认/撤销。
10. 蜜写页边距单位统一为 mm（`beewrite.py:143-150` 改 `25.4/31.7`）。
11. `async_task` 的回调改经 `QTimer.singleShot(0, ...)`/`invokeMethod` 回主线程（当前很可能是**在 QThreadPool 线程里操作 QWidget**）【报告，需实机确认】。
12. 蜜演动态数字在导出路径失效（改为读 `data-final` 替换正文）；`_start_sync_mode` 补 `set_slides_html(self._slides_html)`。
13. WebDAV 冲突检测改为 fail-safe；删除遗留的明文密码模块 `beeoffice/webdav.py` + `WebDAVConfig`。
14. 删除/重做假功能：宏录制、冻结窗格、页眉页脚 stub、激光笔/画笔、HTML 导出入口（或补齐）。

### P2 — 中期（工程健康）

15. **纳入版本控制**（`git init` + `.gitignore` 补上 `backup/`、`tools/`、`test+files/`、`create_tests.py`、`boost_coverage.py`、`finalize_session.py`、`运行文档.txt`、`mslxt.txt`），删除 `backup/`。
16. 补 `LICENSE`；统一版本号来源（只保留 `__version__.py`）；CHANGELOG 去掉粘贴进去的脚本。
17. `app.py` 按职责继续拆分；`FormulaEngine`（119 方法）按函数域拆类。
18. 消重：两个/三个/四个同功能实现归并（§2.3 表格）；抽出公共 `image_scan`、`md_table`、`heading_numbering`。
19. 线程安全：`ChunkLoader` 后台只算 chunk、回主线程写 model；`_error_trace` 改为实例属性。
20. 测试改造：删掉"存在性断言"和"恒真断言"；断言**产物**（导出文件真的存在、内容正确、边距正确）；对 `0.0.0.0` 绑定、凭据不明文落盘、插件哈希校验失败必须拒绝等敏感面补测试；解决测试顺序污染导致的全量崩溃。
21. 统一原子写工具函数，替换所有 `open(...,"w") + json.dump` 直接覆盖。

---

## 附录 A：分析方法与证据边界

- **静态分析**：4 个并行深度分析任务分别覆盖 BeeSheet（19 模块 ≈10 600 行）、BeeWrite（18 模块）、BeeShow + PDF（29 模块 ≈10k 行）、安全与基础设施（云同步/移动端/AI/插件/设置/打包）。
- **动态验证**（本文作者在本机执行）：公式引擎两处 eval 的逃逸复现；`AppSettings.save()` 数据摧毁复现；`QWebEnginePage.grab` 反射检查；`QTableWidget.setItem` 签名检查；插件发现耗时测量；`import beeoffice.app` 耗时测量；`pytest --collect-only` 计数；`tests/unit`+`tests/smoke`、`tests/qt` 分别运行；工作区写权限探测。
- **证据边界**：未运行 GUI 交互流程；未用 Word/WPS/PowerPoint 打开导出文件；未做真机（局域网）网络测试；未做内存/性能剖析。凡属此类的结论在正文中已标注 `【推断】`。
- **未修改任何产品文件**。分析期间在仓库根目录创建的临时文件（`pytest_run*.log`、`_t1.log`、`_t2.log`、`_ptmp/`）已全部删除，仅保留本报告。

## 附录 B：一句话总评

> 这是一个**野心极大、功能清单极长、工程纪律极弱**的 AI 辅助个人项目。它的模块划分与部分基础设施（异步封装、i18n、主题、崩溃处理、跨平台路径）是有功力的；但**安全修复只做了表面那一层、数据写入大量非原子、多个宣称功能实为空壳、文档系统性地记录了并未发生的修复**。在补齐 P0 项之前，它不适合处理任何来源不可信的文件，也不适合承担任何不可丢失的文档。
