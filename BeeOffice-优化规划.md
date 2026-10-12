# 蜜蜂办公 BeeOffice 优化规划

> 配套文档：[BeeOffice-分析报告.md](BeeOffice-分析报告.md)
> 规划原则：**先止血，再提效，最后收敛架构**。所有前期动作的目标都是"让后续改动可回滚、可验证"。

---

## 执行进度（2026-10-10）

**阶段 0 已完成，阶段 1 已完成。**

| 项 | 状态 | 提交 / 证据 |
|---|---|---|
| 0.1 纳入版本控制 | ✅ | `879e58a`，tag `baseline-v5.0.4`，213 个文件入库 |
| 0.2 绿色测试基线 | ✅ | `2d1aabe`：4 failed → 0 failed |
| 0.3 基线指标 | ✅ | [docs/baseline.md](docs/baseline.md) |
| 0.4 产物级测试骨架 | ✅ | 每个 P0 修复都配了行为/产物断言（见下表回归数） |
| 1.1 公式引擎 RCE | ✅ | `da77877`；逃逸载荷由返回 `5.0` 变为不执行；删除死模块 `formula_engine.py` |
| 1.2 settings 原子写 | ✅ | `2d1aabe`；顺手修好 conftest 手抄字段清单的根因 |
| 1.3 禁止覆盖原 docx | ✅ | `da786bf` |
| 1.4 两个网络服务加固 | ✅ | `da786bf`；默认回环 + 令牌 + 去通配 CORS + Host/Origin 校验 |
| 1.5 PNG 序列导出 | ✅ | `7353170` |
| 1.6 蜜演表格数据破坏 | ✅ | `7353170` |
| 1.7 应用版式可撤销 | ✅ | `7353170` |
| 1.8 静默失败最小集 | ✅ | `7353170`（PDF 批注 + 蜜算备份）；本轮补完 `beeshow_ai_service`：新增 `last_source`（ai/local/error/none）与 `describe_last_source()`，调用方如实提示"已插入本地模板（非 AI 生成）"；批量全失败时显式告警。新增 `tests/unit/test_ai_source_marker.py`（14 条） |
| 决策①「先删后补」删除假功能入口 | ✅ | 宏录制/播放、冻结窗格、激光笔/画笔、页眉页脚 stub、蜜写 HTML 导出入口；新增 `tests/unit/test_command_targets_exist.py`（19 条）把"菜单/插件引用了已删方法"变成自动检查 |
| 附带修复：原子写不再挂死 UI | ✅ | `utils.atomic_write_text` 由 `tempfile.mkstemp` 改为 `open(tmp, "x")`。前者在目标目录不可写时会**无限期阻塞**（实测 15s 未返回），后者 0 ms 抛 `PermissionError` |
| 附带修复：启动期定时器绑定窗口 | ✅ | `BeeApp` 的 4 个 `QTimer.singleShot` 改为绑定 self 的单次 QTimer + `closeEvent` 显式 stop（与 v5.0.5 状态栏定时器同一类问题） |
| 附带修复：`tests/qt/test_app.py` 遮蔽 fixture | ✅ | 该文件自建 `app` fixture 遮蔽了 conftest 的同名 fixture，导致不隔离设置、不屏蔽启动模态框、每用例跑一遍插件发现；删除后 **190s 挂起 → 25 passed / 7.8s** |

### 决策①的执行说明（"先删后补"）

已删除的**入口与桩实现**：

| 功能 | 原状态 | 处理 |
|---|---|---|
| 蜜算 宏录制 / 播放 | `BeeSheetView` 从来没有 `_toggle_macro_recording`/`_play_macro`，点击只弹"当前表格不支持宏录制" | 删除菜单、命令面板项、`BeeApp` 转发方法、插件壳方法 |
| 蜜算 冻结窗格 | 只把表头 `setSectionResizeMode(Fixed)`，**无任何滚动冻结效果** | 删除工具栏按钮、两处右键菜单、4 个方法、`_frozen_rows/_frozen_cols` 状态与状态栏显示 |
| 蜜演 激光笔 / 画笔 | 全仓无鼠标事件处理；`L` 只切一个静止红点，`P` 只翻转一个没人读的布尔量 | 删除 `L`/`P` 按键分支、死状态、激光笔/画布 DOM 容器、快捷键帮助中的两行 |
| 蜜写 页眉 / 页脚 | 把 `<!-- header: X -->` 当**正文**插入，提示却写"导出 Word 时生效"；全仓无消费者，且 `set_markdown` 会跳过该行 | 删除工具栏两个按钮与两个方法 |
| 蜜写 导出 HTML | `BeeWriteEditor` 没有 `export_html`，`app._export_html` 的 `hasattr` 判断必然失败 → 菜单点了静默无动作 | 删除菜单项、命令面板项、`BeeApp._export_html`、插件壳方法 |

**保留待「补」**：`bee_export.export_to_html` 是**已实现且有测试覆盖**的（`tests/unit/test_bee_export.py`）。
它缺的只是 `ExportMixin` 上的一个薄封装 + 菜单接线，约 10 行。
本次按决策只删不可达入口，未做接线；测试里有一条断言专门守着这个实现不被误删
（`test_html_export_implementation_still_available_for_later_wiring`）。

**过程中发现并修复的一个自伤问题**：删掉 `BeeWritePlugin.export_html` 后，
它的 `register_commands` 仍引用该方法 —— 由于 `build_command_palette` 对每个插件
单独 try/except，表现是**蜜写插件后面所有命令都注册不上**，只在日志留一行 ERROR。
现已修复，并由新增的 `test_command_targets_exist.py` 把这类引用变成自动检查
（该文件用源码扫描校验 `menus.py` 的 `main_window._xxx` 与各插件
 `register_commands`/`register_menus` 里的 `self._xxx` 都真实存在，无需 GUI）。


**验收验证**（`python tools/run_tests_isolated.py`）：

```
files : 71      passed : 744      failed : 0      error : 0
阶段 1 验收 10 个回归文件合并运行：133 passed
```

9 个文件报告"退出期崩溃"，**全部是构造 QWebEngineView 的蜜演相关测试**
（`test_app.py`、`test_beeshow_play.py`、`p0_02`、`p0_04`、`p0_08`、`p1_12`、
`p1_13`、`p1_18`、`test_smoke_beeshow.py`）——崩溃发生在进程退出阶段，
与改动无关，属计划 §4.2 的已知项，详见 [docs/baseline.md](docs/baseline.md) §6.1。

---

## 阶段 2 进度（2026-10-11 起）

| 项 | 状态 | 证据 |
|---|---|---|
| 2.1 启动冻结 → <1s | ✅ | `plugin_manager.py` 只 import 插件候选而非全量 84 个模块。实测：`discover_plugins()` **2487 ms → 39 ms**、启动到插件可用 **3177 ms → 555 ms**、且子进程实测**不再引入任何重依赖**（matplotlib/fitz/pandas/docx/QtWebEngine 均未进 `sys.modules`）。同时按 Qt 要求在 `QApplication` 前设置 `Qt.AA_ShareOpenGLContexts`。新增 `tests/unit/test_plugin_discovery_is_lazy.py`（4 条，含干净子进程断言）。详见 [docs/baseline.md](docs/baseline.md) §1 |
| 2.2 统一页边距单位为 mm | ✅ | 默认值改 25.4/31.7（原为同数字的 cm 表示）；PDF 路径删除 `*0.264583`（px→mm）；`bee_export.apply_page_settings()` 成为唯一实现，两条导出路径共用。**顺带修掉一个真实缺陷**：Markdown→DOCX 路径（`export_to_docx`）原先完全不应用页面设置，纸张是 python-docx 模板默认值——"导出 Word"的结果取决于编辑器处于哪种模式。新增 `tests/regression/v5/test_v505_page_margin_units.py`（8 条，含两种编辑模式） |
| 2.3 异步回调切回主线程 | ✅ 实测后**无需改代码** | 规划假设"回调可能在 QThreadPool 线程操作 QWidget"，实测**否证**：`AsyncTaskManager`（QRunnable + WorkerSignals）的 `on_started`/`on_result`/`on_finished`/`on_error` 全部在主线程；`LargeFileLoader`（QThread + 裸闭包回调，闭包里直接 `setModel` / `QMessageBox`）的 `finished_loading`/`chunk_ready`/`progress_updated` 也全部在主线程。原因是这些信号对象都在主线程创建，工作线程 emit 时 AutoConnection 判定为跨线程 → 队列投递。工作函数本身确实在工作线程（已断言），异步有效。**改为把这条不变量写成回归测试锁住**（它依赖"信号对象在主线程创建"）：`test_v505_async_callback_thread_affinity.py`（5 条） |
| 2.4 蜜算线程安全与数据一致性 | ✅ | **两处实测确认的缺陷**：① `ChunkLoader`（QThread）在工作线程直接 `model.load_chunk()` 写 `_loaded_df`/`_loaded_chunks` → 与主线程单元格编辑竞争（用户输入可能被 `pd.concat` 结果整体覆盖），且 `_loaded_chunks` 被重绑后会"遗忘"已加载块。现拆为 `build_chunk()`（纯读取，后台可用）与 `apply_chunk()`（写模型，仅主线程），加载器改发 `chunk_ready(ci, df)` 由视图在主线程合并；`all_loaded` 判定也移到主线程（依据 `model.is_streaming`），避免每次滚动都触发 `_auto_resize_columns()`。② `ChunkLoader.progress` **声明了但从未 emit** —— 其唯一消费者 `_on_loading_progress` 负责显示进度条，而进度条创建时 `setVisible(False)`，于是流式加载期间用户完全看不到进度、该槽是死代码；现按"本批已处理/总块数"真实 emit。新增 `test_v505_chunk_loader_thread_safety.py`（9 条，含"不连消费者时模型必须一点没被改"） |
| 2.5 公式正确性批次 | 🟡 | 已完成四项静默产出错公式的缺陷：① `adjust_formula_refs` 把含数字的函数名当引用（`=LOG10(A1)` → `=LOH10(B1)`；根因是 `\d+` 只吃第一位数字，使"排除函数名"的否定前瞻失效），`extract_refs_from_formula` 同源缺陷一并修复；② 自然语言 IF 真假同值；③ 引擎 `_ref` 不支持 `$` 绝对引用（`=SUM($A$1:$A$3)` → 0）与 `_range` 不归一化反向范围（`=SUM(A3:A1)` → 0）；④ 聚合函数只认冒号范围，逗号分隔参数静默返回 0（`=SUM(1,2,3)` → 0、连 `=SUM(1)` 都是 0）。新增 18 + 13 + 17 + 22 条回归。**剩余**：循环引用检测（现在无检测，会栈溢出或返回错误值） |
| 2.6 蜜写链路补齐 | ✅ | ✅ HTML 导出已接线（`ExportMixin.export_html` + 四个入口；8 条回归）。✅ **批注/书签保存后读回**：`_write_md()` 一直写旁挂 JSON，但两个 `load_from_file()` 在**全仓无调用点** → 重开文档批注书签全丢；现新增 `load_md_sidecars()` 并在打开 `.md` 时调用（9 条回归）。✅ **MD→DOCX 图片与超链接**：转换器**完全没有 `<img>` 分支**（且 `_write_inline` 有"文本为空则跳过"的前置判断，`<img>` 恒为空）→ 图片静默丢弃；`<a>` 只染色、`href` 丢失 → 链接不可点也看不出指向。现用 `run.add_picture()` 真正嵌图（相对路径按 Markdown 目录解析）、找不到文件时留**可见占位文字**、并拼 `w:hyperlink`+外部关系生成可点击链接（11 条回归）。✅ **插入的图片/公式不再只留 %TEMP%**：原先图片写到 `%TEMP%/beeoffice_images/` 并把**绝对临时路径**写进文档，系统清理临时目录后图片永久失效、换机器也全部打不开；现复制到文档旁的 `<文档名>_media/`（未保存文档落到应用数据目录），落盘失败优雅降级（10 条回归）。**剩余**：Markdown 里含空格的图片路径（需 `<...>` 包裹写法）尚未专门处理 |
| 2.7 蜜演导出与同步补齐 | 🟡 | 同步观众端画面（§2.7 的 `set_slides_html`）与动态数字导出已在阶段 1 顺带完成；**剩余**：重排序保留注释、PPTX 图片 `base_url`、字体嵌入 rId、`_PlayWindow` 泄漏 |

**下一步**：2.3（异步回调线程归属，风险较高）→ 2.4（蜜算线程安全）→ 2.5 剩余项
→ 2.6 剩余项。每项都要配回归测试并更新 [docs/baseline.md](docs/baseline.md)。



---

## 0. 核心判断（决定了整个排期）

优化顺序不该按"功能重要性"，而该按**不可逆损失**排：

| 问题类型 | 是否可逆 | 举例 | 优先级 |
|---|---|---|---|
| 用户数据被破坏 | **不可逆** | `settings.json` 被清空、原 `.docx` 被覆盖、表格明文残留泄漏 | 最先 |
| 代码被执行 / 数据外泄 | **不可逆** | 公式引擎 RCE、两个 `0.0.0.0` 无认证服务 | 最先 |
| 功能不好用 | 可逆 | 页边距错、PNG 导出失败、启动卡 9 秒 | 之后 |
| 代码不好维护 | 可逆但复利 | 死代码、四份重复实现、God Object | 最后 |

**因此：立刻冻结新功能开发，直到 §1 全部完成。** 项目当前 36 948 行里有大量"写了但没用/写得不对"的代码，继续加功能的边际收益已经是负的。

**另一个必须前置的判断**：项目**没有版本控制**。这意味着当前状态下任何一次改动都不可回滚——所以 §0 不是"工程规范建议"，而是其他一切工作的前提。

---

## 阶段 0：建立安全网（必须先做，约 1 人日）

> 目标：从"改了不知道对不对、错了回不去"变成"每一步都可回滚、可验证"。

### 0.1 纳入版本控制

```bash
cd D:\beeofficeV
git init
# 先补 .gitignore，再提交，否则 backup/ test+files/ 会一起进来
```

`.gitignore` **追加**（现有文件已覆盖日志/凭据，但漏了这些）：

```gitignore
# 与产品无关的历史与临时物
backup/
test+files/
tools/migration/
create_tests.py
boost_coverage.py
finalize_session.py
mslxt.txt
运行文档.txt
pytest_run*.log
_ptmp/
```

```bash
git add -A && git commit -m "chore: baseline before optimization (v5.0.4 working tree)"
git tag baseline-v5.0.4
```

**验收**：`git status` 干净；`backup/`、`test+files/` 未被跟踪；`git tag` 能看到 `baseline-v5.0.4`。

> 注意：`test+files/` 虽然是测试素材，但它同时是 `test_v502_docx_image_extract` 等测试的输入？——先确认再决定是否忽略（若被测试引用，改为保留但收进 `tests/fixtures/`）。**这一步要人工确认，别盲删。**

### 0.2 拿到一个"绿的"测试基线

当前 `tests/unit/test_settings.py` 有 4 个用例失败（见分析报告 §3.2），先修到全绿，否则后面任何改动都无法判断是否引入回归。

```bash
python -m pytest tests -q            # 记录当前真实结果
```

- 修 `tests/conftest.py:63-86` 的 `_patched_settings_init`：不要复制 `AppSettings.__init__` 的字段列表，改为
  ```python
  @pytest.fixture
  def temp_settings(tmp_path, monkeypatch):
      monkeypatch.setattr(AppSettings, "path", property(lambda self: tmp_path / "s.json"))
      yield tmp_path / "s.json"
  ```
  （或直接把 `AppSettings.path` 变成可注入的构造参数 `AppSettings(path=None)`——见 §1.2，推荐后者。）
- 处理全量运行时**原生崩溃**：单独跑各子集都通过，说明是测试间污染。
  ```bash
  python -m pytest tests -p no:randomly --forked   # 或用 pytest-forked 逐用例隔离定位
  ```
  定位到污染源后在 `conftest.py` 补 fixture 清理，不要用 `-p no:xxx` 掩盖。

**验收**：`python -m pytest tests -q` 全绿且不崩溃；结果记入 `docs/baseline.md`。

### 0.3 记录基线指标（后面用来说明"优化有效"）

在 `docs/baseline.md` 记录并附测量方法：

| 指标 | 测量方法 | 基线 |
|---|---|---|
| 启动到可交互 | `python -m beeoffice.main` 打点计时 | ~? ms（含插件发现） |
| 插件发现耗时 | 见分析报告 §3.4 的脚本 | **9.1 s（冷）/ 6.6 s（热）** |
| `import beeoffice.app` | `python -c "import time;...` | **1.6 s** |
| 测试数 / 失败数 | `pytest --collect-only -q` | **710 / 4 failed** |
| 覆盖率 | `pytest tests --cov=beeoffice --cov-fail-under=25` | 声称 37.3% |
| 内存占用 | `utils.get_memory_usage()` 或 psutil | 待测 |

### 0.4 建立"产物级"测试的最小骨架

当前测试最大的问题是**只断言方法存在、从不断言产物**（分析报告 §6.1）。先补 3 个骨架测试，后面每个修复都往里加：

```python
# tests/contracts/test_artifacts.py
def test_docx_export_has_correct_margins(tmp_path): ...      # 断言 section.top_margin == Mm(25.4)
def test_png_sequence_export_writes_files(tmp_path): ...     # 断言目录里有 N 个非空 png
def test_settings_save_is_atomic(tmp_path, monkeypatch): ...  # 断言异常时旧文件不被破坏
```

**验收**：这 3 个测试当前**必须失败**（它们描述的正是待修 bug）。

---

## 阶段 1：止血 —— 安全与数据完整性（约 4–6 人日）

> 目标：让软件"不破坏用户数据、不执行他人代码"。完成后即可发布一个 `v5.0.5-security` 版本。

### 1.1 【严重】封堵公式引擎的任意代码执行

| 项 | 内容 |
|---|---|
| 位置 | `beeoffice/plugins/beesheet_engine.py:105-112`、`beeoffice/plugins/formula_engine.py:378` |
| 现状 | 两处裸 `eval()`；`beesheet_engine.py:107` 已实测可逃逸（`=S!A1+...sqrt(16)` → `5.0`） |
| 改法 | ① `_eval_sheet_ref` 的引用替换结果交给 `_safe_eval()`，删除自己的 `eval`；② **删除** `formula_engine.py` 及 `tests/unit/test_formula_engine.py`（生产零引用，仅测试引用）；③ `_safe_eval` 的 AST 白名单补上 `_ast.Tuple`/`_ast.List` 已够用，但**追加禁止 `_ast.Attribute`/`_ast.Subscript` 的显式断言测试** |
| 验证 | 新增负面测试：`=S!A1+().__class__.__base__.__subclasses__()`、`=1!A1+[c for c in ...]`、`=(1).__class__` 全部返回 `#ERROR`；`python -m pytest tests/regression/p0 -q` 全绿 |
| 预估 | 0.5 人日 |

**关键**：这条不是"加固"，是**修一个仍然开着的洞**。CHANGELOG 已宣称修好，所以必须同时纠正文档（见 §4.3）。

### 1.2 【严重】`settings.py` 原子写 + 注入路径

| 项 | 内容 |
|---|---|
| 位置 | `beeoffice/settings.py:208-263`；`tests/conftest.py:63-86` |
| 现状 | `open(...,"w")` 先截断，字典在 `json.dump` 参数位构造 → 任何异常留下 **0 字节文件**（已实测复现） |
| 改法 | ```python\npayload = {...}          # 先构造，失败就失败在这里，文件未动\ntmp = self.path.with_suffix(".tmp")\nwith open(tmp,"w",encoding="utf-8") as f:\n    json.dump(payload, f, indent=2, ensure_ascii=False)\n    f.flush(); os.fsync(f.fileno())\nos.replace(tmp, self.path)   # 原子替换\n``` 另：`__init__(self, path=None)` 支持注入，删掉 conftest 里的字段复制；`save()` 失败必须 `QMessageBox` 告警而非静默 `logging.error` |
| 验证 | `test_settings_save_is_atomic`：monkeypatch 让 payload 构造抛异常 → 断言旧文件**内容不变**；`tests/unit/test_settings.py` 4 例转绿；手工把 `~/.beeoffice_settings.json` 设为只读后保存，应见提示而非静默 |
| 预估 | 0.5 人日 |
| 顺带 | 同样的非原子写还在 `resources/template_manager.py:197,285`、`plugins/pdf_annotator.py:155-159`。抽一个 `utils.atomic_write_json(path, obj)` / `atomic_write_text` 统一替换（§3.4） |

### 1.3 【严重】禁止原地覆盖用户的原 `.docx`

| 项 | 内容 |
|---|---|
| 位置 | `beeoffice/app.py:549-550` + `beewrite_export_mixin.py:258-262` |
| 现状 | 打开 docx 后 `_current_file_path = 原文件` → Ctrl+S 走 `_rich_to_docx(原路径)` 低保真重建覆盖原文件 |
| 改法 | ① 打开 docx 时记 `self._source_docx = path`，**不设** `_current_file_path`（或设为 `None`）；② `_save_as_docx()` 若 `_source_docx` 存在，弹三选一：**另存为（默认）** / 覆盖并自动备份 `.bak` / 取消；③ 覆盖前无条件写 `path.with_suffix(".docx.bak")` |
| 验证 | 新增回归：造一个含超链接+多段单元格的 docx → 打开 → `save()` → 断言**原文件字节未变**、且出现 `.bak` 或走了"另存为" |
| 预估 | 0.5 人日 |

### 1.4 【严重】两个网络服务默认只绑本机 + 加 token

| 项 | 内容 |
|---|---|
| 位置 | `beeoffice/mobile.py:99`（`_ThreadingHTTPServer(("", port), ...)`）、`beeshow_sync_server.py:177`（`host="0.0.0.0"`） |
| 现状 | 两者对局域网完全开放、零认证；mobile 还带 `Access-Control-Allow-Origin: *` |
| 改法 | ① 默认 `127.0.0.1`；"允许局域网"做成显式开关 + 风险提示；② 启动生成 `secrets.token_urlsafe(16)`，URL 与二维码携带 `?t=`，服务端校验；③ **删除** `Access-Control-Allow-Origin: *`（改成不带 CORS 头即可阻断跨站读取）；④ 校验 `Host` 头（防 DNS rebinding）；⑤ 观众端 `innerHTML` 改 `textContent`，服务端 markdown 用 `nh3`/`bleach` 白名单净化 + 加 CSP 头 |
| 验证 | 新增契约测试：**断言生产代码的绑定地址为 `127.0.0.1`**（当前 `tests/unit/test_mobile_api.py:66` 用 `127.0.0.1` 测试反而掩盖了 `0.0.0.0`，必须改掉）；无 token 请求返回 403 |
| 预估 | 1 人日 |

### 1.5 【严重】修 PNG 序列导出

| 项 | 内容 |
|---|---|
| 位置 | `beeshow_export_mixin.py:404` |
| 现状 | `page.grab()`，而 `page` 是 `QWebEnginePage`（实测无 `grab` 成员）→ 永不产出文件却弹"导出成功" |
| 改法 | `view.grab()`；成功提示建立在**真实写入结果**上（`ok = view.grab().save(...)`，失败弹 warning + 明确错误）；`temp` 先 `show()` 或在 `loadFinished` 后延迟一帧再截 |
| 验证 | `test_png_sequence_export_writes_files`：导出 3 页 → 断言目录下 3 个 png 且尺寸 >0 且非纯白；失败路径断言弹的是 warning |
| 预估 | 0.5 人日 |
| 相关 | 同一文件 `:276-282`（`printToPdf` 异步却立刻报成功）、`:94-97`（渐变被替换成白）一并修 |

### 1.6 【高】修蜜演表格插件的两处数据破坏

| 项 | 内容 |
|---|---|
| 位置 | `beeshow_table_mixin.py:246-247`、`:530-549` |
| 现状 | ① `setItem(insert_at, r, item)` 参数顺序颠倒（实测签名 `setItem(row, column, item)`）→ 空 item 覆盖已有行；② `_replace_current_table` 把"第一个 `\|` 行到最后一个 `\|` 行"之间的全部内容替换掉 → 删掉正文 |
| 改法 | ① 改 `setItem(r, insert_at, item)`；② 用"连续表格块"匹配（遇到非 `\|` 行即结束），并加**替换前 diff 预览 + 确认** |
| 验证 | 新增回归：含"表格-正文-表格"的文档执行"编辑表格" → 断言中间正文仍在；对 3 列表格执行"插入列" → 断言原单元格数据全部保留 |
| 预估 | 0.5 人日 |

### 1.7 【高】"应用版式"必须可撤销

| 项 | 内容 |
|---|---|
| 位置 | `beeshow_layout_mixin.py:154-156`（`self._editor.setPlainText(skeleton)`） |
| 现状 | 静默清空整份文档，无确认、无撤销、不限于当前页 |
| 改法 | 最少：加确认对话框 + 把操作压入 `_history` 快照栈（项目已有 `history_mixin` 的 50 快照机制，直接复用）；理想：改为"仅对当前页应用版式骨架" |
| 验证 | 回归：应用版式后立刻 Ctrl+Z → 断言文本完全恢复 |
| 预估 | 0.5 人日 |

### 1.8 【中】消除静默失败（最小集合）

不是全面改造（那属于 §3.5），只处理**会让用户以为成功其实失败**的几处：

| 位置 | 现状 | 改法 |
|---|---|---|
| `beesheet.py:1003-1004` | 自动保存 `except Exception: pass` | 记录 + 状态栏提示"自动备份失败" |
| `beesheet.py:991-998` | 表格明文写入 `~/.beeoffice_backups/` 且永不清理 | 改为放应用数据目录，**关闭文档时删除**对应备份，保留数量/总大小上限 |
| `pdf_annotator.py`（全类） | **无 `closeEvent`** → 未保存批注关窗即丢 | 加 `closeEvent`：有未保存批注时询问 |
| `pdf_annotator.py:26-28,101-105` | `from_dict` 缺键即 KeyError → 整份批注读不出 | 改 `.get()` + 字段校验 + `.beeanno` 加版本号，失败时降级为"跳过损坏条目"而非全部丢弃 |
| `pdf_annotator.py:160-172` | 烧录忽略用户选的颜色 | 补 `annot.set_colors(...)` |
| `beeshow_ai_service.py:187-195` | AI 失败静默降级为本地模板 | 返回值带 `source='ai'|'local'|'error'`，UI 明确提示 |

**预估**：1 人日。

### 阶段 1 验收（可发布 `v5.0.5-security`）

- [ ] 4 条 RCE 负面测试通过（含 `!` 路径、属性穿透、推导式）
- [ ] `settings` 原子写测试通过；`tests/unit/test_settings.py` 全绿
- [ ] 原 `.docx` 不被静默覆盖（回归测试）
- [ ] 两个服务默认只监听 `127.0.0.1`，无 token 返回 403，无通配 CORS 头
- [ ] PNG 序列导出产出真实文件
- [ ] 表格"插入列"/"编辑表格"不丢数据（回归测试）
- [ ] `pytest tests -q` 全绿且不崩溃
- [ ] CHANGELOG 纠正 3 条虚假的"已修复"（§4.3）

---

## 阶段 2：正确性与体验（约 5–8 人日）

> 目标：让"宣称的功能真的能用"，并解决最影响体感的两件事（启动卡顿、界面冻结）。

### 2.1 【高】启动冻结 9 秒 → <1 秒

| 项 | 内容 |
|---|---|
| 位置 | `plugin_manager.py:28-45`、`app.py:153,399-409` |
| 改法 | 三选一，按代价从低到高：① 只对**声明了插件的模块**做 import（维护一个 `PLUGIN_MODULES` 白名单或用 `plugin.json` 清单，`importlib.util.find_spec` 探测而不执行）；② 把 `discover_plugins()` 移入 `AsyncTaskManager.run`，完成后信号回主线程注册菜单；③ 真正的按需加载（打开蜜算时才 import `beesheet_*`） |
| 验证 | 基线对比：`discover_plugins()` < 500 ms；启动到可交互 < 1.5 s；补一条"启动期间界面不阻塞"的冒烟测试（在 `_lazy_load_modules` 完成前 `processEvents` 可响应） |
| 预估 | 1.5 人日 |
| 附带 | 全仓缺 `Qt.AA_ShareOpenGLContexts` 与 `QtWebEngineQuick.initialize()`（实测有对应告警），一并补上，并加"蜜演加载失败要提示用户"而非静默消失 |

### 2.2 【高】统一页边距单位（移除 10 倍）偏差

| 项 | 内容 |
|---|---|
| 位置 | `beewrite.py:143-150`（改 `25.4/31.7`）、`beewrite_export_mixin.py:415-423`（删 `* 0.264583`）、`beewrite_doc_mixin.py:198-219`（去掉 `/10` 显示） |
| 验证 | `test_docx_export_has_correct_margins`：导出后 `docx.Document(p).sections[0].top_margin == Mm(25.4)`；PDF 侧断言注入的 CSS 含 `margin: 25.4mm` |
| 预估 | 0.5 人日 |

### 2.3 【高】后台线程不再碰 QWidget

| 项 | 内容 |
|---|---|
| 位置 | `async_task.py:94-101` 的 `worker.signals.result.connect(on_result)`；调用方 `app.py:508-513`、`app.py:586-591` |
| 现状 | 回调是普通函数/lambda，PySide6 按**发射线程直接调用**处理 → 很可能在 QThreadPool 线程里操作 QWidget【报告，需实机确认】 |
| 改法 | 项目自己的回归测试已经不得不把 `AsyncTaskManager.run` 换成同步实现并注"避免线程竞态"（`tests/regression/v5/test_v503_docx_open_order.py:26-27`），说明问题已被感知。修法：`AsyncTaskManager.run` 内部统一用 `QTimer.singleShot(0, lambda: cb(result))` 或 `QMetaObject.invokeMethod` 把回调切回主线程，让调用方无需关心 |
| 验证 | 新增测试：在 worker 里记录 `QThread.currentThread()`，在回调里断言 `== QApplication.instance().thread()` |
| 预估 | 1 人日 |

### 2.4 【高】蜜算线程安全与数据一致性

| 项 | 内容 |
|---|---|
| 位置 | `beesheet_loaders.py:42`（后台线程直接 `model.load_chunk()`）、`beesheet_engine.py:35`（`_error_trace` 类变量）、`beesheet_model.py`（`_full_df`/`_loaded_df` 漂移） |
| 改法 | ① `ChunkLoader` 后台只**算出** chunk，通过信号回主线程再 `load_chunk`；② `_error_trace` 改实例属性；③ 所有编辑路径统一同时更新 `_loaded_df` 与 `_full_df`（或在 `get_value` 里做"未加载区回退"时用脏集校验） |
| 验证 | 回归：后台加载大 CSV 的同时读 `model.data()` 不崩；编辑后滚到未加载区域读到新值；两个表格标签的公式错误互不污染 |
| 预估 | 1.5 人日 |

### 2.5 【中】蜜算公式引擎正确性批次（按性价比排序）

| 序 | 缺陷 | 位置 | 一行/小改可修 |
|---|---|---|---|
| 1 | 填充/复制把 `LOG10` 改成 `LOH10`（**静默产出错公式**） | `beesheet_utils.py:49` | ✅ 正则排除"数字紧跟字母"的函数名 |
| 2 | `ABS/SQRT/PI/RAND` 全废 | `beesheet_engine.py:191-194` | ✅ 修正 `math_funcs` 调用参数 |
| 3 | `$A$1` 绝对引用在 `_ref` 路径失效 | `:249,257` | ✅ 正则加 `\$?` |
| 4 | 聚合不支持常量/多参数（`=SUM(1,2,3)` → 0） | `_sum/_avg` + `_vals` | 中 |
| 5 | 循环引用无检测 | 引擎全局 | 大（需依赖图） |
| 6 | 自然语言真假日同值 | `nl_formula.py:170-175,237-241` | ✅ 兜底分支返回 `""` |
| 7 | 错误值不传播（`#ERROR` 被当 0） | `_vals:273-276` | 中 |
| 8 | 文本/日期/CEILING/FLOOR 语义错 | 多处 | 中 |
| 9 | `_recalc_formulas(max_rounds=3)` 不收敛不报错、错误值不写回 | `beesheet_formula_mixin.py:560-584` | 中 |

**建议**：1–3、6 立即修（各几分钟）；4、7 排进本阶段；5、8、9 排进 §3，并把结果写成 Excel 对照测试（用 openpyxl 造"期望值表"驱动）。

**预估**：2 人日。

### 2.6 【中】蜜写链路补齐

| 项 | 位置 | 改法 |
|---|---|---|
| 批注/书签只写不读 | `beewrite_export_mixin.py:206-217` vs `beewrite_comment.py:98` | 打开 `.md` 时调 `load_from_file`（或直接把批注存进文档 front-matter，避免旁挂文件丢失） |
| HTML 导出不可达 | `app.py:864-867` | 补 `ExportMixin.export_html()`，或在 UI 移除入口（**不要留静默空转**） |
| 页眉页脚 stub | `beewrite_doc_mixin.py:74-89` | 要么落地（`sectPr/headerReference`），要么**删除入口与提示文案** |
| MD→DOCX 丢图/超链接 | `bee_export.py:265-346` | 补 `img` 分支与 `w:hyperlink`；或统一走 `_rich_to_docx` |
| 行内/含空格路径图片丢失 | `beewrite_rich_editor.py:668-670` | 用统一的图片语法解析器，支持 `![](a)![](b)` 与含空格路径（`<...>` 或 URL 转义） |
| 图片落在 `%TEMP%` | `beewrite_image.py:428`、`beewrite_formula.py:313` | 导出/保存时把图片复制到文档旁的 `media/`，MD 里写相对路径 |

**预估**：2 人日。

### 2.7 【中】蜜演导出与同步补齐

- 动态数字：导出前对 `_slides_html` 的 span 读 `data-final` 替换正文（`beeshow_export_mixin.py:104-111,244-249`）。
- 同步服务：`_start_sync_mode` 补 `set_slides_html(self._slides_html)`（`sync_mixin.py:92`）→ 观众端才真的能看到画面。
- 重排序丢注释：`_slides_md` 改为保留含 `<!-- comments/style/image -->` 的原文，或在重排时按页搬运注释（`slide_mixin.py:124-143,311-333`）。
- PPTX：`page.set_content` 传 `base_url`（图片才不会被丢弃）、`run.font.name` 必须设置、字体嵌入的 `rId` 必须从 rels 实际读取、每页不要重启一次 Chromium（复用一个 browser/context）。
- `_PlayWindow` 去父 + `WA_DeleteOnClose`（当前每次 F5 泄漏一个 WebEngine 视图）；`%TEMP%/beeoffice_video_posters` 改用稳定 hash 并加清理。

**预估**：2.5 人日。

### 阶段 2 验收

- [ ] 启动到可交互 < 1.5 s，插件发现 < 500 ms（对比基线）
- [ ] 后台回调全部在主线程（测试断言）
- [ ] 页边距 DOCX = 25.4 mm、PDF CSS = 25.4 mm
- [ ] 表格填充含 `LOG10` 公式不产出错公式
- [ ] 蜜演同步观众端能看到幻灯片内容
- [ ] 蜜写批注/书签重开后仍在

---

## 阶段 3：架构收敛（约 8–12 人日，可与阶段 2 部分并行）

> 目标：减少"同一件事有 N 种写法"，让后续改动成本下降。**这一阶段不改变用户可见行为**，所以每步都必须有测试兜底。

### 3.1 删除死代码（先做，立即减小面积）

| 目标 | 理由 |
|---|---|
| `plugins/formula_engine.py`（569 行） | 生产零引用；且带一个裸 `eval` |
| `beeoffice/webdav.py` + `plugins/webdav_sync.py` 的 `WebDAVConfig` | 无 UI 入口；**明文密码落盘** |
| `plugins/git_manager.py` | 无调用方；`save_file` 可任意路径写 |
| 零散死成员 | `SheetDataModel.MIN_ROWS`、`_real_rows`、`ChunkLoader.progress`、`LargeFileLoader.chunk_ready`、`ViewMixin._undo/_redo`、`CommentManager.load_from_file` 以外的未用方法、`beeshow._css_cache/_preloaded_slides/_ai_service/_pptx_engine/_font_embedder`、`pdf_annotator._note_editor`、`beesheet_plugin._*_fallback`、`beeshow_pptx_engine.py:67-68` 死导入 |
| 手误残留 | `beesheet_engine.py:1310` 孤立续行反斜杠 |

**预估**：1 人日（含确认无引用）。

### 3.2 拆 `app.py`（1414 行 / 87 方法）

按已有边界继续外移，**每次只搬一个域 + 保留委托方法**，避免大爆炸：

| 新模块 | 从 app.py 搬走的内容 |
|---|---|
| `document_io.py` | `_open_recent` / `_open_sheet_file` / `_open_docx_file` / `_open_text_file` / `_save_*` / `_restore_session` / `_autosave` |
| `export_actions.py` | `_export_docx/_pdf/_html` / `_run_async_export` / `_run_batch_convert` / `_generate_report` |
| `sync_actions.py` | `_sync_now` / `_check_auto_sync` / `_show_webdav_settings` |
| `integrations.py` | `_start_mobile_server` / `_open_mobile_download` / `_show_plugin_market` / `_open_pdf_annotator` / `_show_memory_monitor` |

目标：`app.py` **< 500 行**，只留窗口壳、标签、菜单、状态栏、快捷键。

**预估**：3 人日。

### 3.3 消重（合并同功能多实现）

| 能力 | 现状 | 目标 |
|---|---|---|
| Markdown→DOCX | 3 份 | 1 份（Markdown 路径与富文本路径共用 `_write_inline`/`_write_table` 抽象） |
| Markdown 表格转换 | 3–4 份 | 1 个 `md_table.py` 纯函数模块 |
| 图片 fragment 扫描 / 路径兜底 | 4 份 / 2 份 | `image_utils.py` |
| 标题编号 | 2 份 | `heading_numbering.py` |
| 幻灯片 HTML 模板拼接 | 5 处 | `render_slide_html(slide, theme, layout)` 单点 |
| 单元格颜色应用 | 3 套 | 1 套 |
| WebDAV | 2 套 | 1 套（`cloud_sync/webdav.py`） |

**预估**：4 人日。

### 3.4 统一基础设施

```python
# utils.py 新增（替换 4+ 处直接 open(...,"w")）
def atomic_write_json(path, obj) -> bool
def atomic_write_text(path, text) -> bool
```

同时：
- 统一错误处理规范：**禁止 `except: pass` 与 `except Exception: pass`**；提供 `errors.py` 的 `log_exception()` 与"用户可见错误"通道。当前 15 处裸 `except:` + 446 处 `except Exception`，用 ruff 规则 `E722`/`BLE001` 逐步收紧（先只对 `beeoffice/` 开，`--diff` 增量）。
- 引入 `ruff` + `black`（`requirements-dev.txt` 已有 black），先只跑 `--check` 记录现状，不要求一次全绿。
- 库代码里的 66 处 `print()` 改 `logging`。
- 单个方法 > 100 行的（`_build_all_toolbars` 243 行等）逐个提取。

**预估**：2 人日。

### 3.5 插件系统收紧

- 定义 `plugin.json` 清单：`id / name / version / api_version / entry / permissions / sha256 / signature`。
- `PluginManager` 只按清单加载，不再全量 import（同时解决 §2.1 的性能问题）。
- 引入**能力门面**：不再把 `parent`（BeeApp）直接给插件，而是给一个受限的 `PluginContext`（只暴露 `register_command` / `register_menu` / `add_tab` / 受控的 settings 读）。
- 插件目录移到 `%APPDATA%\BeeOffice\plugins`，禁止覆盖应用自带的模块。
- 安装流程：校验 sha256 → 校验签名（Ed25519 + 内置公钥）→ 展示所需权限 → 二次确认。

**预估**：3 人日。

---

## 阶段 4：工程化与可信度（约 4–6 人日）

### 4.1 真正做到 CI

CHANGELOG 声称有 `.github/workflows/test.yml`，实际**不存在**。

```yaml
# .github/workflows/test.yml
name: test
on: [push, pull_request]
jobs:
  test:
    strategy:
      matrix: { os: [windows-latest, ubuntu-latest, macos-latest] }
    runs-on: ${{ matrix.os }}
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: '3.11' }
      - run: pip install -r requirements.txt -r requirements-dev.txt
      - run: pip install ruff black
      - run: ruff check beeoffice          # 先允许失败，作为可见指标
      - run: python -m pytest tests -q --cov=beeoffice --cov-report=xml
      - run: python tools/check_imports.py
```

Windows-only 是原计划；**建议加 Linux 与 macOS**——因为多处平台分支（`platform.system()` 三分支、`subprocess.run(['open'|'xdg-open'])`）从未被验证。

### 4.2 测试改造（这是"可信度"的根）

| 动作 | 说明 |
|---|---|
| **删掉"存在性断言"测试** | `test_smoke_beeshow.py:90-221,322-342` 这类 `assert hasattr(...)` 全部替换为行为断言 |
| **删掉恒真断言** | `test_md_conversion.py::test_empty_heading_not_output` 无法失败 |
| **断言产物而非调用** | 导出类测试必须检查文件存在、大小、关键属性（边距/字体/图片数） |
| **改掉掩盖生产行为的测试** | `tests/unit/test_mobile_api.py:66` 的 `127.0.0.1` + 补绑定地址断言 |
| **给每个 P0 修复配回归测试** | 见各阶段"验证"列 |
| **解决顺序污染** | 用 `pytest-forked` 或显式 fixture teardown 定位全量崩溃 |
| **敏感面测试** | 凭据不得明文落盘、插件哈希校验失败必须拒绝、`0.0.0.0` 不得出现 |

**预估**：3 人日（持续投入）。

### 4.3 文档与版本号单一来源

- **纠正 CHANGELOG 里 3 条假的"已修复"**（公式 RCE、`except: pass` 清除、Base64 当加密），并删掉第 9–22 行粘贴进去的脚本。
- 版本号只保留 `__version__.py`，README badge 与 CHANGELOG 从它生成（一个 `tools/sync_version.py` 即可）。
- 补 `LICENSE`（README 标注 MIT）。
- **禁止把补丁说明写进源码 docstring**（45/118 个模块如此）。改为：源码留"为什么这样写"，变更写进 CHANGELOG，历史交给 git。
- README 的"功能特性"逐条标注实现状态（✅ / 🟡 部分 / ❌ 未实现），把 §5.1 那张表搬进去。**用户最需要的是不撒谎的功能清单。**

**预估**：1 人日。

### 4.4 打包与发布

| 项 | 现状 | 改法 |
|---|---|---|
| UPX | `beeoffice.spec:166,183 upx=True` | 关闭（显著提高杀软误报） |
| 代码签名 | `codesign_identity=None` | 至少 Windows Authenticode；否则在下载页明确说明 SmartScreen 会告警 |
| `resources/__pycache__/*.pyc` 被打包 | `beeoffice.spec:49-52` 收整个目录 | 只收 `.json/.ico` |
| 版本读取 | `build_release.py:28 exec(content, namespace)` | 改 `importlib` 或正则 |
| 依赖未锁 | `requirements.txt` 全 `>=` | 加 `requirements.lock`（`pip-compile`）；`run.bat:49` 的在线 `pip install` 改为可选 |
| `PYTHONPATH` 注入 | `run.bat:61` 把脚本目录加入 | 移除，避免同名包劫持 |
| **冻结后插件目录是否存在** | `pkgutil.iter_modules` 依赖磁盘目录，PyInstaller 把纯 py 打进 PYZ，不会物化该目录 → **可能一个插件都不加载**【需实测】 | **必须实测一次打包产物**：确认 `_internal/beeoffice/plugins/` 存在、插件市场能列出内置插件、安装后重启生效 |

**预估**：1.5 人日（含实测）。

---

## 需要你决策的 5 个点

这些是规划里**无法替你决定**的分叉，会显著改变工作量：

| # | 决策 | 选项 A | 选项 B | 影响 |
|---|---|---|---|---|
| 1 | **假功能怎么处置** | 删除入口（诚实、便宜，约 1 人日） | 补齐实现（宏录制、冻结窗格、激光笔/画笔、页眉页脚、GIF、PNG、HTML 导出） | B 需 +8~12 人日 |
| 2 | **高风险面留不留** | 保留移动端 + 蜜演同步 + 云同步 + 插件市场（按 §1.4 加固） | 砍掉移动端与蜜演同步（攻击面归零） | 砍掉可省 1.5 人日，但失去卖点 |
| 3 | **云同步怎么办** | 实现真正的双向同步（`cloud_sync` 的 `download/list` 已具备） | 明确改成"仅上传备份"并改名 + 修 UI 文案 | 前者 +3 人日 |
| 4 | **目标平台** | 只 Windows（现状事实） | 真三平台（需 CI 三平台 + 系统相关分支实测） | 后者 +3~4 人日 |
| 5 | **是否对外发布** | 仅自用（可跳过签名/锁依赖/CI） | 对外发布（§4 全部必要） | 后者 +4~6 人日 |

**我的建议**：1 选 A（先诚实，再按用户反馈逐个补）；2/3 保留但加固（这是它的差异化）；4 先 Windows-only 但加 Linux/macOS 的 CI 只跑测试；5 若要发布，§4 不可省。

---

## 排期总览

| 阶段 | 内容 | 预估 | 累计 | 里程碑 |
|---|---|---|---|---|
| 0 | 版本控制 + 绿基线 + 基线指标 | 1 人日 | 1 | `baseline-v5.0.4` 标签，`pytest` 全绿 |
| 1 | 止血（安全 + 数据完整性） | 4–6 人日 | ~7 | **`v5.0.5-security`：可安全打开外部文件** |
| 2 | 正确性与体验 | 5–8 人日 | ~15 | **`v5.1.0`：宣称的功能真的能用** |
| 3 | 架构收敛 | 8–12 人日 | ~27 | **`v5.2.0`：代码面积显著下降** |
| 4 | 工程化与可信度 | 4–6 人日 | ~33 | **`v6.0.0`：可对外发布** |

按每周 3 人日投入：**阶段 1 约 2–3 周内可完成**。建议**先只承诺阶段 0 + 1**，跑通了再决定后面。

---

## 明确不建议做的事

1. **不要重写整体架构。** 模块划分、`async_task`、`i18n`、`theme`、`crash_handler` 这些是对的，重写会丢掉现有的正确部分而引入新 bug。
2. **不要在阶段 0/1 之前做性能优化或功能开发。** 现在的瓶颈是启动阻塞和 UI 阻塞，不是算法；而数据破坏和 RCE 才是会让人彻底放弃这个软件的原因。
3. **不要"顺手重构"。** 每个 §3 的动作都必须先有测试兜底——这个项目当前的测试恰恰无法兜底（§4.2），所以顺序不能颠倒。
4. **不要相信 docstring 里的"已修复"。** 已发现至少 3 处注释/CHANGELOG 声称修复但实际未修；改为**用测试表达"已修复"**。
5. **不要在没实测打包产物的情况下宣布发布。** 冻结环境里 `pkgutil.iter_modules` 可能让全部插件失效——这会让安装包"打开就是空壳"。

---

## 立即可开工的"前 3 天"具体清单

```
Day 1  上午  git init + 补 .gitignore + baseline 提交 + tag
       下午  修 tests/unit/test_settings.py 的 4 个失败（顺带做 settings 原子写，§1.2）
Day 2  上午  封堵公式引擎 RCE（§1.1）+ 4 条负面测试
       下午  修 PNG 导出（§1.5）+ 产物级测试骨架（§0.4）
Day 3  上午  原 .docx 不被覆盖（§1.3）
       下午  两个服务的绑定与 token（§1.4），跑通阶段 1 的验收清单
```

完成后你就有了：**一个可回滚的仓库、一个全绿的测试基线、以及一个不再能被表格文件执行任意代码、不再吞掉用户设置的版本。** 这三件事的价值高于后面所有功能工作之和。
