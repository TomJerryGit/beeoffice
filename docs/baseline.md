# 优化基线指标

记录时间：2026-10-10（阶段 0 完成后）
代码版本：`__version__.py` = 5.0.4，git tag `baseline-v5.0.4`（commit 879e58a）
环境：Windows，Python 3.11.9，PySide6 6.6.0，`QT_QPA_PLATFORM=offscreen`

> 本文件的作用是给《BeeOffice-优化规划.md》后续阶段提供"优化前"的对照数字。
> 每次改进后请在本文件追加一行，不要覆盖旧值。

## 1. 启动性能

测量脚本（在仓库根目录执行）：

```bash
QT_QPA_PLATFORM=offscreen python -c "
import time
t0=time.perf_counter(); import beeoffice.app; t1=time.perf_counter()
from PySide6.QtWidgets import QApplication
app=QApplication([])
from beeoffice.plugin_manager import PluginManager
m=PluginManager(None)
t2=time.perf_counter(); m.discover_plugins(); t3=time.perf_counter(); m.load_plugins(); t4=time.perf_counter()
print(f'import beeoffice.app      : {1000*(t1-t0):.0f} ms')
print(f'plugin discover_plugins() : {1000*(t3-t2):.0f} ms')
print(f'plugin load_plugins()     : {1000*(t4-t3):.0f} ms')
print(f'total                     : {1000*(t4-t0):.0f} ms')
"
```

| 指标 | 基线 | 阶段 2.1 之后（实测） | 目标 |
|---|---|---|---|
| `import beeoffice.app` | 658 ms | 436 ms | 不劣化 |
| `PluginManager.discover_plugins()` | **2487 ms**（冷启动曾测得 9110 ms） | **39 ms**（含 load_plugins） | **< 500 ms ✅** |
| `PluginManager.load_plugins()` | 0 ms | 0 ms | 不劣化 |
| 启动到插件可用合计 | **3177 ms**（冷启动约 8–11 s） | **555 ms** | **< 1500 ms ✅** |
| 已注册插件数 | 4（BeeWrite / BeeSheet / BeeShow / PDF 批注） | 4 | 4 ✅ |
| 插件发现是否引入重依赖 | 是（matplotlib / fitz / pandas / docx / QtWebEngine） | **否**（子进程实测 `sys.modules` 中一个都没有） | 否 ✅ |
| `test_app.py`（25 个用例所在文件） | 挂起约 190 s | 25 passed / 7.8 s | — |

**根因与修复**（优化规划 §2.1）：`plugin_manager.py` 原用
`pkgutil.iter_modules` 把 `beeoffice/plugins/` 下**全部 84 个模块**逐个
`import`，连带拉起 matplotlib、PyMuPDF(fitz)、python-docx、pandas 与
QtWebEngine；而这段代码由 `app.py` 在窗口 `show()` 之后于**主线程**执行
（`QTimer` 延迟 50 ms），于是界面冻结约 7–9 秒。

修复方式由实测数据决定（关键实验）：

| 测量项 | 结果 |
|---|---|
| `pkgutil.iter_modules` 扫描 84 个模块名（不 import） | **10.6 ms** |
| 逐个 import 4 个插件壳（`*_plugin.py`） | **1–3 ms/个，且不拉任何重依赖** |
| 其余 80 个实现模块 | 重依赖全在这里（pandas/matplotlib/fitz/WebEngine） |

即"插件壳本身很轻，重依赖都在它们的 `create_widget()` 里延迟导入"。
因此只需**不 import 那 80 个实现模块**：用两个廉价信号判定候选
——① 文件名以 `_plugin` 结尾；② 其余模块读源码找 `(Plugin)` 子类声明
（只读文本、不执行）。第②条保留了插件市场安装的、非约定命名插件的可发现性。

同时按 Qt 要求，在 `QApplication` 创建**之前**设置
`Qt.AA_ShareOpenGLContexts`（只设属性、不 import WebEngine，以保持懒加载），
消除 `Attribute Qt::AA_ShareOpenGLContexts must be set before QCoreApplication
is created` 告警。


## 2. 测试

命令：`python -m pytest tests/unit tests/smoke -q -p no:cacheprovider -o log_file= --basetemp=<可写目录>`

| 指标 | 基线（阶段 0 开始时） | 阶段 0/1.2 之后 |
|---|---|---|
| `tests/unit` + `tests/smoke` | 464 passed, **4 failed** | **473 passed, 0 failed** |
| 失败用例 | `test_settings.py`：`test_save_and_load`、`test_window_size_serialization`、`test_password_encoded`、`test_password_decoded_on_load` | 已全部修复 |
| `pytest --collect-only`（全量） | 710 | **733**（删掉死模块 `formula_engine.py` 的 64 条，新增 86 条安全/数据回归） |
| `tests/qt` 单独运行 | 97 passed / 17.25 s | 待复测 |
| 全量 `tests/` 一次性运行 | **原生崩溃**（顺序污染，单独跑子集均通过） | 仍会崩溃，但已有隔离运行方案与定位结论（见 §6.1） |
| 按文件隔离运行（`tools/run_tests_isolated.py`） | — | **100 文件 / 1084 passed / 0 failed / 0 error**（§3.3 幻灯片 HTML 消重完成后实测）。注意 passed 计数会波动（曾见 1006~1084）：9 个构造 `QWebEngineView` 的文件在**本会话沙箱**里因命名管道被拒而在 `setHtml()` 处原生崩溃（见 §6.1 更正），**是否来得及打印 summary 会决定那几十个用例算不算进去**；`failed`/`error` 则始终为 0 |

失败根因（已修复）：`AppSettings.save()` 先以 `"w"` 截断文件再在 `json.dump`
参数位构造 payload，任何构造期异常都会把 `~/.beeoffice_settings.json` 留成
0 字节；而 `tests/conftest.py` 的 fixture 手工复制了 `AppSettings.__init__` 的
字段清单，v5.1 新增 6 个字段后未同步 → 必然触发该异常。

## 3. 安全（阶段 1 前状态）

| 项 | 基线状态 |
|---|---|
| 公式引擎任意代码执行 | **存在且已实测可利用**：`beesheet_engine.py:107`（活代码）、`formula_engine.py:378`（死代码） |
| 网络服务绑定 | `mobile.py:99` → `0.0.0.0`；`beeshow_sync_server.py:177` → `0.0.0.0`；两者零认证，mobile 带 `Access-Control-Allow-Origin: *` |
| 凭据存储 | WebDAV 密码 / OAuth token / AI Key 仅 Base64（非加密） |
| 插件安装 | 无哈希/签名，判别条件为子串匹配 `"Plugin" and "class "` |
| 原 `.docx` 覆盖 | 打开后 Ctrl+S 会原地覆盖原文件且无备份 |

## 4. 代码规模（基线）

| 指标 | 基线（v5.0.4） | 阶段 3.1 之后 |
|---|---|---|
| `beeoffice/` 模块数 | 118 | **114** |
| `beeoffice/` 总行数 | 36 948 | **37 573**（阶段 1/2 新增多于删除） |
| 最大模块 | `beesheet_engine.py` 1444 行 | `beesheet_engine.py` 1710 行 |
| 最大类 | `FormulaEngine`（119 方法） | 同左 |
| 裸 `except:` | 15 处 | 15 处（未处理） |
| `except Exception` | 446 处 | 未重测 |
| docstring 为版本日志的模块 | 45 / 118 | 未重测 |
| 死代码模块 | `formula_engine.py`(569)、`beeoffice/webdav.py`、`plugins/git_manager.py` | **已全部删除**（阶段 1 删 `formula_engine.py`；阶段 3.1 删后两个 + `plugins/webdav_sync.py`） |
| 纳入版本控制的文件数 | 213（首个 commit） | **239** |

## 5. 变更记录

| 日期 | 阶段 | 变更 | 指标变化 |
|---|---|---|---|
| 2026-10-10 | 0.1 | 首次纳入 git；`.gitignore` 排除开发遗留物 | 213 文件入库，tag `baseline-v5.0.4` |
| 2026-10-10 | 0.2 + 1.2 | `AppSettings` 原子写（`utils.atomic_write_json`）+ 路径注入；conftest fixture 改为委托真实 `__init__`；`on_save_error` 用户可见提示 | 4 failed → 0 failed；新增 5 条回归 |
| 2026-10-10 | 1.1 | 封堵公式引擎跨表引用路径的裸 `eval`（改走 AST 白名单）；删除死模块 `formula_engine.py`（569 行，含第二处裸 eval）；修正 `math_funcs` 参数使 ABS/SQRT/PI/RAND 恢复可用 | 逃逸载荷由返回 `5.0` 变为不执行；`=S!A1*2` 由 0 → 14；新增 20 条回归 |
| 2026-10-10 | 1.3 | 禁止静默覆盖原 `.docx`：新增 `_source_docx` 标记 + 三选一确认 + `.bak` 自动备份 | 新增 7 条回归 |
| 2026-10-10 | 1.4 | 移动端与蜜演同步服务：默认绑 `127.0.0.1`、一次性令牌鉴权、移除通配 CORS、Host/Origin 校验、CSP `script-src 'self'`；顺带修复同步观众端拿不到幻灯片内容 | 新增 16 + 18 条回归 |
| 2026-10-10 | 1.5–1.7 | PNG 序列导出改为对视图 `grab()` 并基于真实结果提示；蜜演表格 `setItem` 参数顺序与表格替换范围；应用版式加确认 + 快照 | 新增 8 条回归 |
| 2026-10-10 | 1.8 | PDF 批注：新增 `closeEvent` 保护未保存批注、旁挂文件容错 + 版本号、原子保存、烧录应用颜色、缩放加限；蜜算自动备份移入应用数据目录会话子目录 + 关闭清理 + 失败可见 | 新增 16 条回归 |
| 2026-10-10 | 1.8 收尾 | `beeshow_ai_service` 新增 `last_source`（ai/local/error/none）与 `describe_last_source()`；UI 如实提示「已插入本地模板（非 AI 生成）」；批量全失败显式告警 | 新增 14 条回归 |
| 2026-10-10 | 1.5 补测 | PNG 序列导出补产物级回归：假 QWebEngineView 驱动真实 `_export_images`，断言产出 3 个非空 PNG、失败时告警而非假报成功、AST 校验取图接收者是 view 而非 page | 新增 5 条回归 |
| 2026-10-10 | 决策① | 删除假功能入口（宏录制/播放、冻结窗格、激光笔/画笔、页眉页脚 stub、蜜写 HTML 导出入口） | 新增 `test_command_targets_exist.py` 19 条 |
| 2026-10-10 | 附带 | `atomic_write_text` 由 `mkstemp` 改 `open(tmp,"x")`（前者在不可写目录会挂起）；`BeeApp` 启动期定时器绑定窗口 + `closeEvent` 停止；删除 `tests/qt/test_app.py` 遮蔽 conftest 的本地 `app` fixture | `test_app.py`：约 190 s 挂起 → 25 passed / 7.8 s |
| 2026-10-11 | 2.1 | 插件发现只 import 候选模块（`*_plugin` 约定 + 源码 `(Plugin)` 兜底），不再全量 import 84 个模块；`QApplication` 前设置 `Qt.AA_ShareOpenGLContexts` | `discover_plugins()` **2487 → 39 ms**；启动到插件可用 **3177 → 555 ms**；引入的重依赖 **5 → 0** |
| 2026-10-11 | 2.2 | 页边距单位统一为 mm（默认值 25.4/31.7；PDF 删除 `*0.264583`）；`bee_export.apply_page_settings()` 成为唯一实现 | 默认 DOCX 边距 2.54mm → **25.4mm**、PDF 0.67mm → **25.4mm**；新增 8 条回归 |
| 2026-10-11 | 2.2 附带 | Markdown→DOCX 路径原先**完全不应用页面设置**（纸张是 python-docx 模板默认值），`export_to_docx` 增加可选 `page_settings` | 「导出 Word」不再因编辑模式而异 |
| 2026-10-11 | 2.6 | 蜜写「导出 HTML」接线并可用（`ExportMixin.export_html` + 菜单/命令面板/插件/主窗口四个入口） | 新增 8 条回归；`test_command_targets_exist.py` 改为断言"已接线" |
| 2026-10-11 | 2.5 | `adjust_formula_refs` 不再把含数字的函数名当引用（`=LOG10(A1)` 由 `=LOH10(B1)` 修正为 `=LOG10(B1)`）；`extract_refs_from_formula` 同源缺陷一并修；自然语言 IF 真假同值修正 | `如果A1大于10就显示'高'` 由 `=IF(A1>10,"高","高")` → `=IF(A1>10,"高","否")`；新增 18 + 13 条回归 |
| 2026-10-11 | 2.5 | 引擎支持 `$` 绝对引用与反向范围；聚合函数支持逗号分隔参数（原先连 `=SUM(1)` 都返回 0） | `=SUM($A$1:$A$3)` 与 `=SUM(A3:A1)` 由 0 → 6；`=SUM(1,2,3)` 由 0 → 6；新增 17 + 22 条回归 |
| 2026-10-11 | 2.4 | `ChunkLoader` 不再在工作线程写模型（拆为 `build_chunk` 后台读取 + `apply_chunk` 主线程合并）；`progress` 信号由"声明了但从不 emit"改为真实发出（原先进度条永远隐藏、`_on_loading_progress` 是死代码） | 新增 9 条回归 |
| 2026-10-11 | 2.3 | 实测**否证**了"回调跑在工作线程"的假设（`AsyncTaskManager` 与 `LargeFileLoader` 的回调均在主线程），因此不改代码，改为把该不变量写成回归测试 | 新增 5 条回归 |
| 2026-10-11 | 2.6 | 批注/书签保存后读回：新增 `load_md_sidecars()` 并在打开 `.md` 时调用（此前两个 `load_from_file()` 全仓零调用点，重开文档批注书签全丢） | 新增 9 条回归（含完整往返） |
| 2026-10-11 | 2.6 | MD→DOCX 不再丢图片与超链接：`<img>` 此前无任何分支处理（静默丢弃），`<a>` 只染色、`href` 丢失；现真正嵌图 + 可见占位 + `w:hyperlink` 可点击链接 | 新增 11 条回归 |
| 2026-10-11 | 2.5 | 循环引用不再静默产出不断变化的错数：`=A1+1` 写在 A1 时原先 0→一次重算 3→再触发 6（互引用 1/2→7/8 并继续增长）；现用迭代式 DFS 三色标记找出环上单元格并在重算时跳过 + 状态栏提示 | 循环引用值不再自增；合法链式依赖不受影响；新增 12 条回归 |
| 2026-10-11 | 2.7 | 拖动排序不再永久删除该页的评论/样式/图片标记：`_slides_md` 原先存的是**剥离标记后**的文本，而重排用它重建整个编辑器文本；顺带修复"样式标记被当成演讲备注" | 新增 12 条回归 |
| 2026-10-11 | 2.7 | `_PlayWindow` 不再泄漏 WebEngine 视图：原先以 owner 为 Qt 父对象且无 `WA_DeleteOnClose`，连按 F5/反复播放会留下隐藏窗口（每个 = 一个渲染进程）；现去父 + 关闭即销毁 + 新建前先关旧的 | 子进程实测 `parent is None`、`close()` 后对象已销毁；新增 4 条回归 |
| 2026-10-11 | 2.7 | 导出时动态数字不再显示 0：`_render_dynamic_numbers_for_export()` 被以 **HTML** 调用却只按 Markdown 模式替换，静默匹配不到；现按 `data-final` 回填 span 内文 | 新增 8 条回归 |
| 2026-10-11 | 2.7 | PPTX 四项：整份导出复用**一个**浏览器会话（原每页 launch 一次，假 playwright 实测 3 页由 3 次 → **1 次**）；注入 `<base href="file:///…">` 让相对路径图片能加载（原先图片整张消失）；文本框设 `a:latin`+`a:ea` 字体（原先无字体名，中文易被换字形、字体嵌入无对应）；测量前等图片加载完成 | 新增 12 条回归 |
| 2026-10-11 | 2.7 | 视频封面缓存文件名由 `abs(hash(path))`（字符串 hash **每进程随机化** → 缓存永不命中、`%TEMP%` 每导出一次多一个文件）改为 sha1(路径+mtime+大小)，并加 7 天清理与命中复用 | 新增 8 条回归（跨 PYTHONHASHSEED 子进程实测稳定） |
| 2026-10-11 | 3.1 | 删除死代码：`beeoffice/webdav.py`、`plugins/webdav_sync.py`、`plugins/git_manager.py` 及只覆盖死代码的 `test_p0_10`；清理 `MIN_ROWS`、`ViewMixin._undo/_redo`、`beeshow._ai_service/_pptx_engine/_font_embedder`、`pdf_annotator._note_editor`、`beeshow_pptx_engine` 未用导入、`beesheet_engine` 孤立续行反斜杠。**实测 4 项"死成员"其实活着**（`_real_rows`、`_css_cache/_preloaded_slides`、`ChunkLoader.progress`、`*_fallback`），未删 | 模块数 118 → **114**；导入检查 78 → **75/75 成功**；`beeoffice/` 移除约 13 KB 源码 |
| 2026-10-11 | 3.1 附带 | 云同步"同步正在进行中"守卫从未生效（对 `QRunnable` 调不存在的 `isRunning()`，AttributeError 被宽 except 吞掉 → 重复点击会并发上传）；改用显式 `_sync_in_progress` | 新增 7 条回归 |
| 2026-10-11 | 4.1 | **真正建立 CI**：`.github/workflows/test.yml`（三平台矩阵；跑 `check_imports.py` + 隔离运行器；ruff 非阻断）。此前 `.github` 目录根本不存在，CHANGELOG 的"新增 test.yml"是空头承诺 | 基线指标：`ruff check beeoffice` **1571** 问题、`E722` 裸 except **14** 处 |
| 2026-10-11 | 3.3 | **消重：标题编号**。两处逐字重复的多级计数算法（`beewrite_crossref` 与 `beewrite_outline`）统一到新模块 `heading_numbering.py`。顺带修掉一个真实缺陷：**Markdown 模式（默认模式）下大纲面板永远是空的**（`QPlainTextEdit` 的 `headingLevel()` 实测全为 0，而按 `#` 解析的兜底分支因 `hasattr(...,"document")` 为真而永不触发）；同处还修了兜底分支 `number` 恒为空串与 `pos` 用行号而非字符偏移两个问题 | 新增 `tests/unit/test_heading_numbering.py`（23 条）；导入检查 75 → **76/76 成功** |
| 2026-10-11 | 3.3 | **消重：图片路径兜底**（2 份 → 1 份）。新增 `plugins/image_utils.py`（`normalize_image_ref` / `resolve_image_path` / `iter_block_images` / `iter_image_formats`）；`beewrite_export_mixin`、`beewrite_rich_editor`、`bee_export` 三处解析逻辑收敛到它；`_block_has_image()` 改走 `iter_block_images()`（4 处 fragment 扫描的第 1 处）。**过程中修掉一个真实缺陷**：`urlparse("D:\\a\\b.png")` 把盘符当 URL scheme 丢掉 → 绝对路径被判成相对路径 → 导出 DOCX 时图片消失（`bee_export` 里同一写法被"同盘巧合"掩盖）。安全网先行：`test_v505_image_path_resolution.py`（10 条，含端到端导出断言）**先于**改动写好，正是它抓到了该回归 | 新增 10 + 25 条回归；导入检查 76 → **77/77 成功** |
| 2026-10-11 | 3.3 | **消重：Markdown 表格解析**。规范纯函数早已在 `beewrite_utils`，但 `beewrite_rich_editor._insert_md_table()` 自己又写了一套分裂规则且**丢弃空单元格** → `\| 甲 \|  \| 3 \|` 的 `3` 左移到第 2 列（静默数据错位）。现改走 `parse_md_table()`。**顺带更正规划判断**：另几处（`_table_to_md`、`bee_export._docx_table_to_md`）是不同方向的转换，不是重复实现 | 新增 8 条回归 |
| 2026-10-11 | 3.3 | **消重：表格样式样板**。`beewrite_rich_editor` 里 `QTextTableFormat` 设置与表头样式（select+mergeCharFormat）**逐字重复 4 遍**（对应 4 个插入入口），现抽成 `_make_table_format()` / `_style_header_cell()`；新增测试同时防"样板长回来"（断言源文件里 `setHeaderRowCount`/`setCellPadding` 各只出现 1 次）。**记录一个既有差异**（非本次引入）：`_insert_table()` 插空表格时表头字重读不到（空 block 无法 format），已用测试钉住现状 | 新增 10 条回归 |
| 2026-10-11 | 3.3 | **消重：图片 fragment 扫描 4 处全部收敛**（`beewrite_rich_editor._block_has_image`、`beewrite_export_mixin._count_document_images`/`_block_has_image`、单元格内图片插入）→ `image_utils.iter_block_images()` / `iter_image_formats()`。**有意保留 2 处交错处理**（`_write_block_runs`、`_block_with_images_to_md`）：它们按 fragment 顺序把图片与文本交替输出，不是单纯扫描。新增端到端断言"表格单元格里的图片必须出现在导出的 DOCX 里" | 新增 8 条回归；导入检查保持 **77/77 成功** |
| 2026-10-11 | 3.3 | **消重：Markdown→DOCX 的第三份实现**（`_write_plain_to_docx` + `_write_inline_md`，约 55 行）已删除。盘点确认它是"缺 markdown/bs4 时的逐行降级"，而那两个包是**必需**依赖 → 分支不可达且零测试覆盖。改为缺依赖时**明确失败并记录原因**（原先会悄悄产出低保真文档）。并存的两套（`_write_html_to_docx` 与 `_rich_to_docx`）输入类型不同，**不建议合并**，已在规划写明理由 | 新增 5 条回归 |
| 2026-10-11 | 4.5 | **云同步：上传过滤 + 如实计数**（分析报告 §4.6 实测的缺口；规划原先没有对应条目，本会话补入 §4.5）。原先 `sync_files()` 是无过滤的 `rglob` 循环：该目录内任何内容都会**明文**上传到用户的云盘（含凭据类文件），且无论上传 0 个还是失败多少，UI 一律报"同步完成"。现抽出不依赖 Qt 的 `cloud_sync/policy.py`（`should_upload` / `is_sensitive_settings` / `upload_tree` / `describe_result`）：拒收密钥证书类扩展名与常见凭据文件名、拒收含 `ai_api_key`/`password`/`token` 等字段的 JSON、跳过临时/空/超大文件，并把提示改为"已上传 N，跳过 K（含原因），失败 F" | 新增 29 条回归（用临时目录 + 假 storage，无需 GUI）；导入检查 77 → **78/78 成功** |
| 2026-10-11 | 4.5 | **更正一处错误引用**：此前规划/CHANGELOG 里写的"见规划 §4.5"是错的 —— 规划阶段 4 原只有 4.1–4.4，§4.5/§4.6 在**分析报告**里。已把引用改为"分析报告 §4.5/§4.6"，并在规划里**真正补入 §4.5**（含双向同步/冲突策略的验收清单与预估），使该缺口进入排期 | — |
| 2026-10-11 | 4.2 | **敏感面测试 + 改掉"掩盖生产行为"的测试**。新增 `test_v505_sensitive_surfaces.py`（14 条）：移动端与蜜演同步服务器**默认只绑定回环**（`allow_lan` 是唯一开关）、源码中不得出现无条件的 `"0.0.0.0"` 字面量（并反向确认扫描非恒真）、设置文件不含明文口令/访问令牌（**base64 是编码不是加密**，只断言无明文）。另修正 `test_mobile_api.py`：夹具原先**自己写死** `server.ip = "127.0.0.1"`，使生产绑定 `0.0.0.0` 也测不出来；现改为取生产算出的 `_bind_host()` 并据此绑定。**未加**插件哈希校验测试 —— `plugin_market.py` 目前没有任何校验逻辑（不能凭空断言） | 新增 14 条回归；`test_mobile_api.py` 12 条从 ERROR 恢复为通过 |
| 2026-10-11 | 4.2 | **修掉恒真断言**（规划点名的 `test_md_conversion.py::test_empty_heading_not_output`）。实测确认它确实无法失败：原夹具下 `to_markdown()` 返回 `''` → `lines == []` → 循环**一次都不执行**；另两种构造下空标题被丢弃、也不会出现 `"#"`。已改为"输出非空 + 前置条件确有空标题块 + 正文保留 + 无空标题行"，另用一次性验证证明判定条件能捕获注入的 `"#"` 行 | 该测试由恒真变为可失败 |
| 2026-10-11 | 4.2 | **更正规划一条过期说法**：原写"`test_smoke_beeshow.py:90-221,322-342` 有大量 `assert hasattr`"。AST 复核：实际路径是 `tests/test_smoke_beeshow.py`，其中**已无任何 `assert hasattr`**；全仓"仅由 hasattr 断言构成的测试"只剩 **4 个**，其中 2 个是本会话有意加的行为测试配套守卫。故本条实质已完成，不为凑计划去改这些有效守卫 | — |
| 2026-10-11 | 4.2 | **查明"9 个文件退出期崩溃"的真正根因，并更正旧记录**。原先记为"`offscreen` 下 QtWebEngine 退出期崩溃、由渲染/GPU 子线程在收尾时抛出"。最小复现（6 个变体）证明：只创建视图**不** `setHtml()` → 退出码 **0**、无 FATAL；一旦 `setHtml()` → 必崩，且 `AA_ShareOpenGLContexts`、Chromium `--no-sandbox/--disable-gpu`、`deleteLater`+事件循环、父窗口、`QT_QPA_FONTDIR` **全部无效**。崩溃点真正的错误是 `FATAL:platform_channel.cc(85)] Check failed: . : 拒绝访问。 (0x5)` —— **Chromium 的 mojo 平台通道无法创建命名管道**，即**本会话沙箱**禁止命名管道所致；崩溃发生在 `setHtml` **调用之中**，不是退出阶段。结论：**不是产品缺陷、不是 offscreen 缺陷，普通机器/CI runner 上预计不复现**（待 CI 证实）。据此移除了 `tests/conftest.py` 里基于错误假设加入的 `AA_ShareOpenGLContexts` | 该崩溃不再是"待消除的产品缺陷"；passed 计数波动的疑因也在本地沙箱 |
| 2026-10-11 | 4.2 | **更正隔离运行器的动机表述**：CI 用按文件隔离是绕开 ① `qapp` 级挂死（实测 `test_app.py` 曾 190 s 无 summary）② 顺序污染，**不是**绕开上述沙箱崩溃。顺序污染本身**仍未定位**（本地无法区分，沙箱崩溃会掩盖结论） | — |
| 2026-10-11 | 3.3 | **幻灯片 HTML 拼接 6 处 → 1 处（§3.3 全部完成）**。新增 `plugins/beeshow_html.py::render_slide_html()`（不依赖 Qt），`_export_pdf` / `_export_html` / `_export_images` / `_show_play_slide` / `_show_slide` / `_wrap_html` 六处全部收敛。骨架级差异（`@page`、`body{margin:0}`、固定 1280×960、`<base href>`、页码/JS 位）仍由各调用方**显式传入**，避免"统一"顺手改掉某条路径的版式。安全网（上一轮已写好）合并后 **59 条相关回归全绿**。核对：蜜演里已无手写 `<!DOCTYPE html>` 骨架（`beeshow_sync_viewer.py` 的观众端页面除外，那是独立页面） | 导入检查 78 → **79/79 成功** |
| 2026-10-11 | 3.3 | **§3.3 七项全部完成**：标题编号、图片路径兜底、图片 fragment 扫描、Markdown 表格、表格样式/单元格颜色、Markdown→DOCX、幻灯片 HTML 拼接；WebDAV 2 套→1 套由阶段 3.1 完成 | — |
| 2026-10-11 | 4.3 | **版本号单一来源 + LICENSE + README 诚实化**。新增 `tools/sync_version.py`（默认只检查、`--write` 才改）并以 `__version__.py` 为唯一来源核对 README 徽章与 CHANGELOG，已接入 CI。实测引入前：README 徽章写 **5.0.2** 而源码是 **5.0.7**、CHANGELOG 已到 `[5.0.8]` 而源码仍 5.0.7 → 统一为 **5.0.8**。补 `LICENSE`（MIT）—— 此前 README 徽章链接的文件**根本不存在**。`__version__.py` 移除内嵌的版本历史（指向 CHANGELOG）。README 就地标注 4 类实测确认的假功能（页眉页脚/冻结窗格/宏录制播放/激光笔画笔）与不实的"冲突检测"声明，并新增"功能实现状态说明" | 新增 8 条回归；CI 增加版本检查步骤（8 → 9 步） |
| 2026-10-11 | 4.3 | **工具自身的编码缺陷（已修）**：`sync_version.py` 打印 `✓` 时在 GBK stdout 下抛 `UnicodeEncodeError` → 退出码变 1，会让 CI 步骤无端失败（实测发现于子进程调用）。改为 reconfigure UTF-8 + 仅用 ASCII 标记 | — |
| 2026-10-11 | 4.3 | **剩余**：分析报告 §5.1 的完整功能清单尚未整体搬入 README；约 45/118 个模块仍在 docstring 里内嵌补丁历史 | — |
| 2026-10-11 | 3.3 | 状态：**6/7 完成**（标题编号、图片路径+扫描、Markdown 表格、表格样式、WebDAV）；WebDAV 2 套 → 1 套（随 3.1）。**剩余 1 项：幻灯片 HTML 模板拼接 6 处**（牵动预览/播放/三种导出，测试可观测性最差，建议 CI 通过后再做） | — |
| 2026-10-15 | A | **第十六批：打包版"0 个插件"修复（R11）—— 并在真实产物中验收**。**现象**：5.0.10 打包版冒烟日志 `插件目录不存在 + 已加载 0 个插件`，而源码运行能加载 4 个（蜜写/蜜算/蜜演/**PDF 批注**）。**根因两处**：① `plugins_path = Path(__file__).parent / "plugins"` 不看冻结环境（与 R1 的 `tech_words_path` 同一类错误）；② `discover_plugins()` 见目录不存在就**提前 return** → 静默 0 个。**关键澄清**：插件模块其实**已经**被打进包（spec 里 `collect_submodules("beeoffice.plugins")`，构建日志 `+ plugins: 99 个子模块`），缺的只是"怎么知道该 import 哪些名字"。**修法**：`_resolve_plugins_path()` 走 `get_resource_path()`（冻结感知）；`iter_plugin_module_names()` 在目录不可用时返回**静态清单** `BUILTIN_PLUGIN_MODULES`（4 个）并记录 `source: builtin-manifest`；去掉提前 return。**测试 3 条**（清单必须 == 源码树 `*_plugin.py`，加插件忘改会被拦 ✓；目录不存在时仍加载 4 个插件 ✓；`_MEIPASS` 下路径解析 ✓）。**真机验收**：重新打包 → 冒烟日志 `共加载 4 个插件`（含 PDF 批注）✓，SHA 一致 ✓。**教训**：之前那堆"乱码日志"是我**用 UTF8 读 GBK 控制台输出**造成的 ✗ —— 是我的测量错误，不是应用问题；换 `-Encoding Default` 才读对 | 新增 3 条测试 |
| 2026-10-15 | A | **第十五批：`beecmd` v0（无界面 CLI）—— 战略地基**。战略文档 §5.2 指出"能力全绑 GUI、无法被脚本调用"是最大缺口；本批落地 `beeoffice/beecmd.py`（**纯 Python、零 Qt**）。四个动词：`convert`（xlsx/xls/csv/json/md/html ↔ xlsx；md → `.beshow`）、`info`（工作表/尺寸/列名）、`verify`（**逐格对比**，输出 JSON 报告；退出码 0/1/2 区分成功/出错/不一致）、`batch`（JSON 任务清单 + **`audit.jsonl` 审计流水**，单条失败不中断整批且**失败也记录**）。**实测**：xlsx→csv/json/md/html 后 `verify` **零差异**；csv→xlsx→verify 零差异；故意改坏一个格子 → 精确报 `R1C3: 1.5 → 9.99` 且退出码 2；batch 3 成功 1 失败 → 退出码 1、审计 4 条含失败；md→beshow 带格式标记。**架构约束有测试**：表格路径**不 import PySide6**（子进程写文件验证 —— 沙箱不允许子进程管道捕获，这本身也是踩出来的）。**踩坑**：PowerShell/记事本写的 JSON 带 BOM → 首次 batch 直接 `JSONDecodeError: Unexpected UTF-8 BOM` → 统一改 `utf-8-sig` 读取并加回归测试。v0.1 待接（依赖 Qt offscreen）：md↔docx、→pdf。测试 **15 条**；门禁 **37 项**（新增 `beecmd`） | 新增 15 条测试 |
| 2026-10-15 | A | **第十四批：AI 设置自动列出"本机已装模型"（真机反馈驱动）**。**问题**：设置界面「本地 Ollama」的模型建议是**写死的** `["qwen2.5","llama3.1","gemma2"]`（`MODEL_SUGGESTIONS` + 预设默认 `qwen2.5`），而用户机器上通常**一个都没装** → 每台新机器第一次点开就撞 `模型不存在（HTTP 404）`（第十三批刚把这条提示改准，本批从**源头**消掉它）。**修法**：新增 `list_local_models(api_base, timeout, getter)` —— 问 Ollama 要清单：先试 OpenAI 兼容 `GET {base}/models`（`{"data":[{"id":…}]}`），失败再退 **Ollama 原生** `GET {host}/api/tags`（`{"models":[{"name":…}]}`，注意原生 API 在**根**路径、要把结尾 `/v1` 去掉）；两条都失败就**如实说明**（提示 `ollama serve`/`ollama pull`），**绝不编造模型名**。界面侧三条触发路径：切到本地 Ollama / 打开时已是本地 / 新增「**刷新本机模型**」按钮（刚 pull 完不必重开）；并且当用户填的模型**本机没有**时自动换成第一个可用项并**说明换过**（"原「qwen2.5」本机没有"）；非本机地址**不探测**（那接口只有 Ollama 有）。**真机实测**：切到本地 Ollama → 下拉 `['llama3.2:latest']`、自动选中、提示说明换过 ✓（本机确实只装了这一个）。测试 **14 条**（两种响应形态解析、端点降级、空列表不编造、**真实本地 HTTP 服务**端到端含"只有原生 API"的服务、界面自动填入/尊重用户选择/无模型给可操作提示/远端不探测）；新增门禁 `ai-local-models` | 新增 14 条测试 |
| 2026-10-15 | A | **第十三批：AI 报错归因修对（真机截图驱动）**。**用户真机反馈**：用「本地 Ollama」测连接，填的 `http://localhost:11434/v1` **完全正确**，却弹 **"接口地址不对（HTTP 404）"**。**真因**：Ollama 对未知模型返回 **404 + body** `{"error":"model \"qwen2.5\" not found, try pulling it first"}`（模型名 `qwen2.5` 没带 tag），提示把用户引向反复改地址 —— **方向错了永远修不好**。为什么看不出来：① 主传输层用 `requests`，`raise_for_status()` 的异常**字符串里不含响应体**；② 仓库对 404 有**两套口径**（`beeshow_ai_service` 甩锅地址、`ai_client` 说"地址或模型名"），用户撞上的是差的那套。**修法**：新增纯函数模块 `ai_errors.py`（**唯一实现**）—— 传输层把**响应体带上来**（requests 与 urllib 两条路径都抓），判断按**证据**分级：body 含 `model ... not found` → 判"模型不存在"并给出**可照抄**的 `ollama pull qwen2.5（注意带 tag，如 qwen2.5:7b）`；body 是 `404 page not found` → 判"地址不对"并给 Ollama 正确写法；**拿不到 body 就两种可能都列，不赌方向**；本地 401 → 提示"Key 留空"；拒连 → `ollama serve`。`beeshow_ai_service` 与 `ai_client` 都改为调用它。顺带修截图里的 UI 小问题：服务商切到「本地 Ollama（无需 Key）」时**清空并置灰** Key 框（原先留着旧 Key，既没用又像"必须填"）。**验证**：映射表 11 条单测；**端到端**用**真实本地 HTTP 服务**返回 Ollama 原样 404 → 模型名错时精确归因且含 `ollama pull`、模型名对时连接成功（happy path 未破）；既有 AI 测试 **109 passed**；新增门禁 `ai-error-messages` | 新增 11 条测试 |
| 2026-10-15 | A | **第十二批：打包链修通（生产能力评估 R1 + R5）**。**R1（打包版拼写白名单静默失效）两处根因都修了**：① `beeoffice.spec` 的 `datas` 原先只有 `locales`/`resources`，**漏了 `beeoffice/data`** → 补上；② `spellcheck.tech_words_path()` 原先写死 `Path(__file__).resolve().parents[1]/"data"`，**完全没用仓库里已有的冻结感知助手** `utils.get_resource_path()`（走 `sys._MEIPASS`）→ 改为走它（解析失败才退回旧路径）。**实测**：源码模式 526 词；模拟 `sys.frozen`+`_MEIPASS` 时路径正确指向包内并读到词。**R5（发布脚本从未跑通）**：根因是 `main()` 用 `Path(__file__).parent`（=`beeoffice/`）去找 `beeoffice.spec`（在**仓库根**）→ 必然"未找到 spec 文件"；`get_version()` 同样找错（恒返回 0.0.0）。引入 `REPO_ROOT` 统一修正后**端到端跑通**：PyInstaller 6.22.3 构建成功 → `dist/BeeOffice` → ZIP **224.6 MB** + `.sha256`（v5.0.8）。**验收（真实产物）**：`dist/BeeOffice/_internal/beeoffice/` 下 `data`/`locales`/`resources` 齐备 ✓（正是冻结解析器要的路径）；**无头冒烟 exe 存活 15 秒、i18n 正常加载、无 traceback** ✓。**冒烟时发现新问题 R11（已记入评估）**：日志显示"插件目录不存在 + 已加载 0 个插件" —— 插件发现依赖**磁盘目录扫描**，而冻结包里只有 data/locales/resources，没有 `plugins` 目录；**核心三模块是显式 import、可能不受影响，但需真机确认**（如实标注 A 于机制 / C 于核心影响）。测试 **6 条**（spec 必须打包 data、`_MEIPASS` 下解析正确、源码词表可读、`REPO_ROOT` 正确、版本号可读）；新增门禁 `packaging` | 新增 6 条测试 |
| 2026-10-15 | A | **第十一批：F401 全仓清零（187 处自动 + 10 处手工）**。**先纠正自己的估算**：我之前说"约 30 次编辑"，实际是 **196 处 / ~100 个文件** —— 逐文件先读后改根本做不完，于是按工具规则**申请了一次放宽权限**，用被沙箱拒绝的**同一个命令**（`ruff check beeoffice tests tools --select F401 --fix`）一次性完成：**187 处自动修复，111 个文件 +45/−178 行**。**手工处理 10 处**：ruff **不敢自动改 try/except 内的导入**（怕改掉探测语义）—— 我核实这些名字（`Inches`/`WD_ALIGN_PARAGRAPH`/`Pt`/`Emu`/`RGBColor`/`PP_ALIGN`）在全文件确实未使用，逐个删除并把"探测"意图写进注释（真要用到时 **F821 门禁会立刻拦下**）。**`--fix` 的两处副作用都查出来并修了**：① 它把 `tests/test_smoke_beeshow.py` 里 `ICON_LIBRARY/TEMPLATE_LIBRARY/LAYOUT_CSS/_PlayWindow` **删了** —— 而那正是该冒烟测试要验的**兼容契约**（拆分模块后旧名字仍可导入）→ 改为**补断言**（既消 F401 又真正验证契约，比 noqa 更好）；② 它把 `beesheet_commands.py` 的 `if TYPE_CHECKING:` **删空**（TC005 抓出）→ 移除空块。**审查动作**：确认**没有任何 `__init__.py` 被动过**、被删名字**无一**以字符串形式出现在同文件（动态用法信号）。**验证**：`tests/fidelity` + `tests/unit` = **1286 passed / 3 skipped**，门禁 **33 项全绿** —— 111 个文件的改动**零回归**。新增门禁 `lint-clean`（F401=0 且 TC005=0，防止重新长回来） | 新增 2 条测试；全仓 196 处未用导入清零 |
| 2026-10-15 | A | **第十批（蜜写剩余三条，审计 §2.13）**。① **Markdown 表格双击编辑抹掉列对齐**：`parse_md_table()` 把分隔行**整个丢弃**、`render_md_table()` **硬编码** `---` → `|:---|:---:|---:|` 编辑一次就变 `|---|---|---|`。新增 `parse_md_table_aligns()`（解析成 left/center/right）+ `render_md_table(rows, aligns=None)`（按对齐写 `:---`/`:---:`/`---:`，**不传时保持旧行为**）；mixin 把"解析即记住对齐"集中在 `_parse_md_table()`，于是双击编辑/增删行列等所有整表重渲染都自动带上对齐。② **富文本→DOCX：超链接与单元格多段落丢失**：run 导出只处理图片与文本 → 链接 URL **整条丢掉**（文字在、点不动）→ 新增 `_add_hyperlink()`（手工拼 `w:hyperlink` + 外部关系；失败**退回普通文本不丢字**）并在 `_write_block_runs` 里识别 anchor；单元格原先 `docx_cell.text = cell_block.text()` **只取首段** → 改为按该单元格的**每个块**写段落并复用 `_write_block_runs`（顺带获得超链接/图片支持）。③ **`set_markdown` 忽略嵌套列表缩进**：正则捕获了 `lm.group(1)` 却**从未使用** → 多级列表被压平 → 按缩进（2 空格/1 制表符 = 1 级）换算 `level` 并 `QTextListFormat.setIndent()`。**验证**：对齐往返（`['left','center','right']` → `|:---|:---:|---:|`）、DOCX 里确有外部关系 URL + `w:hyperlink`、单元格两段都在（`['第一段','第二段']`）、三级列表缩进 `[1,2,3]`。测试 **9 条**（含各自核心回归 + 旧行为兼容）；新增门禁 `beewrite-remnants` | 新增 9 条测试 |
| 2026-10-15 | A | **第九批（收尾）：蜜算图表两处静默坏行为 + 蜜写「目录」插字面源码**。① **取消图表对话框也会画一张柱状图**：`_create_chart` 里 `selected` 初值就是 `"bar"`，而判断是 `if selected["value"]` —— **恒为真**（审计 §2.14）→ 初值改 `None` 并只在 `Accepted` 时生成；② **缺 matplotlib 时"插入图表"什么都不发生**：`_generate_chart` 捕获 `ImportError` 后直接 `return`，连提示都没有 → **在让用户选之前**先探测（`importlib.util.find_spec`，不初始化后端）并给"pip install matplotlib"的可操作提示，`_generate_chart` 里也留兜底提示；③ **「📑 目录」把 Markdown 源码插进所见即所得编辑器**：用户看到 `## 目录`/`- [第一章](#第一章)` 的**字面字符**，导出 Word 还会当正文段落写进去（审计 §2.13）→ 新增 `_toc_html()` 解析标题生成**渲染后目录**（按层级缩进、HTML 转义），并用 `insertHtml` 插入；顺带修 markdown 模式分支原先**直接 return、什么都不做**（现在插入 Markdown 目录源码——那里源码才是正确形态）。测试 **8 条**（取消不画图、缺库提示、探测为真、规格仍记录、WYSIWYG 无字面源码、HTML 转义、markdown 模式可用、无标题有提示）；新增门禁 `polish-gaps` | 新增 8 条测试 |
| 2026-10-15 | A | **第八批：条件格式读回 + 蜜写四处"按下去没用/东西会变样"**。**条件格式读回**：第四/五批只写不读 → 用户设了数据条/色阶、保存、重开就看不到。实现时实测发现关键一点：openpyxl **写**用 `DataBarRule`/`ColorScaleRule`，但**读回来的是通用 `Rule` 对象**，信息在 `rule.dataBar`/`rule.colorScale` 的 `cfvo` 列表里 —— 我第一版按类名判断，**永远读不回来**（实测纠正）。端点为"自动最小/最大"（色阶常见）时**按该列数据推算**，视图渲染不了的类型（公式/图标集）**跳过且不编造**。**蜜写四处（审计 §2.13）**：① **默认模式（markdown）下 Ctrl+B/I/U 毫无反应**（`if self._edit_mode != "rich_text": return` 且无提示，而快捷键帮助里写着"Ctrl+B 加粗"）→ 实现 markdown 包裹（`**`/`*`/`<u>`，再按一次取消；无选中时插入空标记并把光标放中间**并给提示**）；② **「§ 分节符」不是分节、还污染导出**（只插入可见文字 `════ 分节符（新节开始） ════`，那行字**原样进 DOCX/PDF**）→ 改为在块上打**用户属性标记**（无可见文字）+ 导出时 `doc.add_section()` 生成**真正的 Word 节**（实测导出得到 2 个 section ✓）；**「分页符」同病一并修**（导出器本来就认 `PageBreak_AlwaysBefore`，所以删掉装饰文字不丢分页 ✓）；③ **「导出 Word」与「另存为 Word」保真度不同**（前者只传 content+path，丢页面设置/页眉页脚/合并/书签/相对图片）→ `app._export_docx` 改为优先调用控件的 `_write_docx()`，与另存为走**同一条富文本路径**；④ **拼写检查「全部替换」会抛异常**（`self.items.index(item)` 用在 `_replace_item()` 重建列表之后 → 拿错行或 `ValueError`；老测试用常量文本桩+等长替换词，永远测不到）→ 只收集"词→替换词"，每轮从**当前列表**取最新对象（**新偏移**）。**踩坑两处**：我第一版收集"对象（含偏移）"→ 第二次替换用**过期偏移**（被自己的回归测试当场抓到，改为只收集词）；测试里手工 `ColorScaleRule` 没给颜色 → openpyxl 保存时把规则丢了（"组数 0"），白怀疑了一轮产品代码。**F401 收尾部分完成**：清了本批所触文件的未用导入（含我重构产生的 `pandas`/`Font`），全仓仍有 **~108 处**未清（见下）。测试 **12 条**；新增门禁 `write-gaps` | 新增 12 条测试 |
| 2026-10-15 | A | **第七批：数据透视表落盘（可刷新）**。**修前**：`_show_pivot_table` 只把**结果值**放进新标签页，`config`（行/列/值/聚合/小计）**当场丢弃** → 关掉标签页就重算不了，存成文件后只剩死数字，看不出怎么汇总、也无法刷新。**先试了写"原生 Excel 透视表"**（`openpyxl.pivot` 的 `TableDefinition` + `CacheDefinition`）：两次分别被拒（`dataCaption should be str`、`PivotField.items ... expected FieldItem`）—— 其 pivot 对象图又深又缺文档，而**半填的 pivot 会让 Excel 弹"修复文件"**，那比没有原生透视表糟得多 → **改走"规格 + 可刷新"**（并在模块与报告里如实写明原因）。**修法**：新增 `beesheet_pivot.py`（纯逻辑）—— 计算语义**只有一份**（对话框改为调用它，避免两处漂移）；落盘用两张**隐藏表**（`beeoffice_pivot` 存版本标记/目标工作表/字段配置 JSON/来源表名，`beeoffice_pivot_data` 存**数据快照**，使文件自洽可重算）；`refresh_pivot_package()` 按"当前表格 → 文件内快照"取数据重算并**删行后**重写；界面新增「工具 → 刷新透视表」（未保存时提示先保存、无规格时明确说明）。**顺带修掉一个继承来的真 bug**：`build_pivot` 原先只对 `MultiIndex` 调 `reset_index()` → **只有一个行字段时（最常见）**`reset_index(drop=True)` 把行标签**整个丢掉**（修前列 `['销量_1月','销量_2月']`，产品 A/B 消失；修后 `['产品','销量_1月','销量_2月']`）—— 落盘端到端测试把它暴露出来。**两个我自己的 bug**：① 刷新时只把值置 None 就 `append` → `append` 写到原区域**之后**（透视表首行空、数据跑下面），改为**删行**再写；② 刷新传的是 `model.df`（**被补齐到 1000 行**）→ 空值参与 sum 把结果算错（本该 1 变 0）→ 抽出共享的 `drop_empty_rows()` 让"生成/刷新"两边同语义。测试 **15 条**（含行标签回归、刷新后表头/数据位置、数据变少不残留旧行、快照兜底、外来文件不猜）；新增门禁 `pivot-persistence` | 新增 15 条测试 |
| 2026-10-15 | A | **第六批：冻结窗格 / 图表 / 命名区域 / 批注作者四项落盘**。**先测量再动手**：造一个同时带这四种特性的真实工作簿走写路径 —— 经**工作簿路径**（只改 `.value`）**四项全保留**（文档没说假话）；又专门查了"第四批加的样式后处理（`load_workbook`+`save`）会不会弄丢图表"（openpyxl 有'读不回图表'的坏名声）：**实测图表部件/绘图部件/表→绘图关系/绘图→图表关系/图表标题全在** ✓ 无回归。所以真实缺口是：**读侧**从不读进视图（定位对话框看不到名称、状态栏不显示冻结、作者全丢）、**`df.to_excel` 新路径**没有源结构、**图表从未进过 xlsx**（应用内只是 matplotlib 预览 + 存 PNG）、以及⚠️**我在第四批引入的回归**：`_apply_comments` 把作者**硬编码成 "BeeOffice"** → 导入带作者的批注再保存会**覆盖原作者**。**修法**：① 批注作者按"视图记录 → 文件已有同内容则**原样不动** → 才是新批注用设置里的 `user_name`"三级规则，**绝不硬编码**；② 命名区域读+写，并做 **A1 行号 ±1 换算**（应用里行号 = 视图行+1，而文件第 1 行是表头 —— 不换算会**指错行**）；③ 冻结窗格读+写（界面上的冻结仍disabled，本项是**状态保留**，文件里原有的不丢、状态栏能看到）；④ 图表生成时记规格、保存时写成**原生 Excel 图表**（bar/line/pie/area/scatter/radar）。**图表的关键取舍（踩坑）**：两条写路径对图表完全不同 —— 工作簿路径每次从**源文件**重开（已写的图天然在 → 只写未写过的，否则叠加两张），`df.to_excel` 路径每次**重建文件**（必须全部重写，否则第二次保存图表**直接消失**）；我第一版"写成功就清空规格"正是后者的反面，**被测试当场抓到**。测试 **13 条**（含重建路径不丢图 / 工作簿路径不重复 / 原作者不被覆盖 / 行号往返）；新增门禁 `freeze-chart-names-author` | 新增 13 条测试 |
| 2026-10-15 | A | **第五批：蜜算表格样式 + 数据验证落盘（写 + 读回）**。**修前**：`_table_style`（预设"琥珀蜜蜂/海洋蓝/…"其实就是 `{header_bg, stripe_bg, stripe}`）与 `_data_validations`（`{(row,col): [选项…]}`，delegate 靠它弹下拉）和第四批那批一样**只在内存里**，导出链零引用 → 保存即消失。**修法**（同一套"写盘后后处理"管线）：表格样式 → 第一条数据行 + 隔行斑马纹填充（**照实复刻屏幕**）；数据验证 → **逐格**的 openpyxl list 验证（不能合并成大范围，那会让不该有下拉的格子也有下拉）；读回从填充色反推预设（模型只按那三个键渲染，等价重建即可）、从 `dataValidation` 反解选项并交给模型引用（实测读回后单元格**确实变回下拉框**）。**如实记录的发现（未擅自改）**：`beesheet_model.data()` 里 `if r == 0: return header_bg`，而模型**没有表头行**（`r` 直接索引数据）→ 那个"表头色"其实涂在**第一条数据行**上，不是列名表头；本批照实复刻以保证"导出文件 == 用户看到的表"，off-by-one 留给后续统一修。**两个我自己的 bug（都有回归测试）**：① `len(getattr(df,"columns",[]) or [])` 对 pandas `Index` 做 `or` → "truth value of a Index is ambiguous" → 整套样式写入被 except 吞成一行日志（**日志救了我**：这正是"格式失败只记日志、不毁数据"的设计价值）；② `for row in ws["A2"]` —— `ws[区域]` 返回 **Cell** 而非元组 → `'Cell' object is not iterable`，表现为"验证写进去了却读不回"，且被 debug 级日志吞掉（用 logging DEBUG 复现才看到）；教训：**我的复现脚本加了归一化却没把修复写回模块**，复现脚本与真代码不一致会骗自己。测试 **10 条**；新增门禁 `table-style-validations` | 新增 10 条测试 |
| 2026-10-15 | A | **第四批：蜜算视图侧格式落盘（写 + 读回）**。**修前**（审计报告 §2.9）：蜜算的格式体系全在视图内存里（`_cell_formats` 加粗/斜体/下划线/对齐/数字格式、`_merged_cells` 合并、`_cell_comments` 批注、`_conditional_formats` 条件格式），而写盘只有"值 + 公式"两条路 —— 这些在导出链上**零引用**，导出即"模块自述本刀不解决"。**修法**：新增 `beesheet_style_export.py`，**两条写路径共用**同一个"写盘后后处理"（打开刚写好的 xlsx 贴样式再存），避免分别改导致行为漂移；`openpyxl` 读回做往返断言。写：加粗/斜体/下划线/对齐、数字格式（分类+小数位+千分位 → Excel 格式串）、合并、批注、条件格式（数据条/色阶）。**读回**（这是闭环的另一半，只写不读等于"存了却看不到"）：导入时恢复 `_cell_formats`/`_merged_cells`/`_cell_comments` 并重新 `setSpan`；**条件格式暂不读回**（反向映射易错、且写盘只新增从不删除，读不回也不丢），**大文件（>5MB）跳过读回**（再开一次 openpyxl 的代价真实）。**两个必须守住的底线（都有测试）**：① **写格式不能丢数据** —— openpyxl 的 `merge_cells` 会清掉非左上角的值，所以合并区内还有数据时**跳过合并**并计数（数据优先于外观）；② **视图的合并语义要与它自己的文档一致** —— `_merge_cells` 文档写着"其余置空"但**实现从未真的清**，导致合并既存不下来（被守卫跳过）又留着看不见的值，现在真的清空并**明确告知清掉了几个值**。**踩坑**：`_parse_number_format` 只剥逗号没剥 `#` 占位符 → `¥#,##0.00` 解析失败 → 货币格式读回时**静默丢失**；**是"往返属性测试"抓到的**（我原先只测了正向 `number_format_code`）—— 写/读成对的逻辑必须测互逆。测试 **21 条**；新增门禁 `format-persistence`；产出文件用 office 技能的共享检查器 + openpyxl 读回双重核对 | 新增 21 条测试 |
| 2026-10-15 | A | **第三批：蜜算 `.xls` 真支持 + 行列操作可撤销 + 云同步双向**。**① `.xls`（原先"假装支持"）**：对话框与 `SHEET_EXTENSIONS` 都列了 `.xls`，但读路径**写死** `engine='openpyxl'`（openpyxl 只认 .xlsx），而 `requirements.txt` 里声明的 `xlrd`（**本机已装 2.0.2**）**全仓无人调用** → 用户选 .xls 必失败。修法：新增 `pick_excel_engine(path)`（按扩展名选 `xlrd`/`openpyxl`，缺 xlrd 时给**可操作**的报错），两处读路径（`read_workbook` 与蜜算导入回退分支）都改用它；`.xls` 的**公式读取**跳过（`_read_formulas` 依赖 zip+XML，二进制 BIFF 走不通）。**同时补上写入守卫**：我们能读但不能写 BIFF，导入 .xls 后按 Ctrl+S 会去写 .xls（`df.to_excel` 无引擎可用）→ 改为**明确提示并另存为 .xlsx，原 .xls 一字不动**。**② 插入/删除行列可撤销 + 过安全门**：原先只改 `_loaded_df`（不压撤销栈 → Ctrl+Z 无效；不过 `_ensure_full_data` → 流式大表会被分块回填覆盖；`_full_df` 与 `_loaded_df` 分叉）。新增 `DataFrameOpCommand`（整表快照式，取舍写在注释里）并接入 6 个操作。**③ 云同步从"空转"变成真的双向同步**：原先上传 `~/.beeoffice_data`（**全仓无写入方**→永远"没有文件需要上传"），三适配器的 `download()` **零调用者**。新增 `cloud_sync/engine.py`：**可配置同步目录**（默认 `~/BeeOffice云同步`）+ 上传（策略白名单）+ **下载** + **增量判断**（远端已最新就跳过，否则每次全量重传）+ 冲突保留本地并单独计数 + 如实文案；`cloud_sync_dir` 进设置、云存储设置界面加"同步目录"行与"选择…"，帮助菜单加「把当前文档加入同步目录」（解决"用户不知道该把文件放哪"）。**测试 20 条**（引擎用假 storage，**完全不需要联网**；`.xls` 因本机无 xlwt/LibreOffice 造不出夹具，按"引擎选择 + 接线"验证）；新增门禁 `xls-undo-sync` | 新增 20 条测试 |
| 2026-10-15 | A | **第二批：让蜜算/蜜演都有"当前文件 + 保存"（备份与自动保存才覆盖得到）**。动机：审计报告 §2.6/§2.7 —— 平台级的「保存前备份 / 5 分钟自动保存 / 未保存提示」全都要求控件有 `_current_file_path` 与 `save()`；而**蜜算从不设路径**、**蜜演整条保存链路不存在**（`def save`/`save_as` 全为 0）。**蜜算**：抽出 `_write_xlsx()` 供"导出/保存/另存"共用（避免三条路各自漂移），新增 `save()`（有当前文件就写回、没有则退化为另存）、`save_as()`、`set_current_file_path()`，并在**导入后记住路径**。**蜜演**：新增 `beeshow_doc.py`（**纯逻辑不依赖 Qt**，故可完整测试）定义 `.beshow` 格式 —— 内容就是编辑器里的 **Markdown** ＋ 一行注释标记（渲染时被忽略、便于识别）＋ **原子写**（`.tmp`→`os.replace`），且 `load()` 对**无标记的旧 Markdown 宽松兼容**（避免"以前存的打不开"）；视图侧接 `save()`/`save_as()`/`open_deck()`/`set_current_file_path()`；`app` 新增 `SHOW_EXTENSIONS=(".beshow",)`、打开路由 `_open_show_file()`，`tab_manager.open_file` 过滤器也加上。**关键守卫**：`_autosave` 现在**必须有 `_current_file_path` 才自动保存** —— 否则蜜算/蜜演第一次自动保存就会弹"另存为"对话框（每 5 分钟一次是灾难）；**自动保存只写回已有文件，绝不替用户决定路径**。**踩坑（我自己的门禁抓到）**：`beesheet_data_mixin.py` 用了 `logging` 却没 import（与当年"用了 tempfile 没 import 导致只读位置文档打不开"同一类），被 `ruff F821` 阻断规则当场拦下。测试 **17 条**（格式往返/原子写/宽松读取/失败如实返回 + 蜜算保存不弹对话框/导入记路径 + 蜜演接口与路由 + 备份覆盖面 + 自动保存**有/无路径**两侧），新增门禁 `save-coverage` | 新增 17 条测试 |
| 2026-10-15 | A | **P0 批次（审计后的第一批修复，5 项）**。背景：并行审计 + 我的独立复核发现一批"入口在、实现不通"的问题，用户批准先做成本最低的 5 项。**① Ctrl+S / Ctrl+Z 同键歧义**：`menus.py` 的窗口级 QAction 与模块级 QShortcut 同键 → Qt 报 `Ambiguous shortcut overload`，**两个槽都不执行**（蜜写 Ctrl+S、蜜算 Ctrl+Z/Ctrl+Y 完全失效）。**我先试了"改成 `WidgetWithChildrenShortcut` 让模块侧胜出"—— 不成立**（Qt 的上下文只决定"是否匹配"、**不做优先级排序**，两个都匹配仍判歧义；用真实 BeeApp 复测才发现的）。最终按"**只留一个来源**"：删掉蜜写 Ctrl+S 与蜜算 Ctrl+Z/Ctrl+Y 的模块 QShortcut，撤销目标改由 `menus._resolve_editor` 解析（新增"自己实现了 undo/redo 的视图直接用视图"分支，蜜算即属此类）；顺带修 `beewrite_mode_mixin.editor` 属性 —— 它原先**恒返回 markdown_editor**，导致所见即所得模式下的"撤销/查找替换"都在操作**隐藏**编辑器。**② 蜜算/蜜演关标签不提示未保存**：两视图原先没有 `content()` → `initial_content=None` → 静默关闭（蜜演尤其致命：它没有保存链路）。补 `content()`（蜜算返回**轻量签名**＝形状+`hash_pandas_object` 摘要，5 万行实测 <1s；蜜演返回编辑器 Markdown）＋ `contentChanged` 接模型/编辑器信号。**③ 导出 PDF**：原先三入口都收敛到 `export_to_pdf`，而它依赖**被注释掉的 weasyprint**（我实测返回 False 且不产文件）。改为各模块实现 `export_pdf(path)`（蜜写/蜜算走 Qt `QPrinter` 的 `PdfFormat`、蜜演走 WebEngine 并接 `pdfPrintingFinished` 报真实结果），`app._export_pdf` 按模块分流；**顺带修掉打印引擎两个真 bug**：页脚画到可用区外 5px → PDF **多一页**；首页标题高度未计入页码计划 → 同样多一页（"缩放到 1 页"也因此失效）。**④ `_analyze_data`**：原先 `hasattr` 探测一个**不存在的方法**且无 else → 点了连提示都没有；实现为**纯本地**分析（形状/统计/缺失/重复/错误值 + 明确标注"不是 AI"）。**⑤ 两个死链**：在线模板的 GitHub 仓库**实测 404** 且选择器**从来没有在线入口**（死代码）→ 删除；「移动端下载」只是打开一个 **404** 的发布页 → 删除菜单项，并给「移动端查看」补上**局域网访问开关**（`MobileServer` 默认只监听回环、界面原先没有开关 → 手机根本连不上）。测试 **10 + 7 + 7 + 门禁**，新增门禁 `p0-shortcuts` / `p0-unsaved-prompt` / `p0-pdf-export`；`tests/fidelity` 全目录 **683 passed / 3 skipped** | 新增 24 条测试 |
| 2026-10-15 | A | **R2 更正：避尾 Qt 做不到 —— 判定"不做"（0 人日），并留金丝雀**。spike 里我写过"避尾只要插 `U+2060` 就行（≈2 人日）"，**那是从"避头"实验推断的、没测过避尾**。实现阶段补测（判据：行末**剥掉插入的标记后**的最后一个可见字符是否开启标点；`U+200B` 作负对照证明仪器能分辨差异）：插 **`U+2060` / `U+200D`(ZWJ) / `U+FEFF` / `U+00A0` / `U+2007` 五种标记，违规数全都是 21 = 基线**（负对照 316）。→ **Qt 富文本断行不认这些"两侧禁断"的行断类（`WJ`/`ZWJ` 都没实现到这条 CJK 路径）**，避尾无法用插入文本标记实现；真正的替代（不换行空格）**有宽度**会在标点后多出空隙，而正确做法需自定义 `QAbstractTextDocumentLayout`（代价远超收益）→ **不做**。**我曾实现过一版（写时插标记＋读时剥离，`toPlainText`/`to_markdown` 均不含零宽字符、与原文逐字一致），实测无收益后完整回退** —— 只改文本而零收益是纯负担。**留下的资产**：`beeoffice/plugins/kinsoku.py` 作为实测证据模块（判据自带剥离逻辑），由 `tests/fidelity/test_r2_kinsoku_limitation.py`（**10 条**）当**金丝雀**：若 Qt 开始认这些标记，测试失败并提示"R2 可重做"。**元教训（本项 5 次"看起来已达标"全部来自坏仪器/坏判据）**：v1 未触发布局→行列表为空；v2 文本构造使断点**在数论上永远撞不上**标点；v4 负对照因"行末是零宽字符"判不到；**v5 判据漏剥插入的标记 → "行末是零宽 ZWJ"被当成"不是开启标点" → 假的 0 违规**，差点把无效方案当成功。已加入门禁 `r2-kinsoku-canary` | 无产品代码改动（实现已回退），新增 10 条测试 |
| 2026-10-15 | A | **R8 + R9：打印缩放到一页 / 兼容性损失提示精确到"哪一处"**。**R8**（`beesheet_print_mixin.py`）：打印设置新增**缩放模式** ——「缩放到 1 页」「适应 1 页宽（默认）」「适应 1 页高」「不缩放（超宽自动分页）」。关键取舍：① **等比缩放 ≠ 压列宽** —— 早期把列宽挤到页宽内会**挤坏文字**，现在缩的是整体比例（列宽与行高一起缩），行高已由测试钉住（`test_scaling_keeps_row_height_proportional`）；② **"不缩放"= 按列横向分页**（每页带行号列、页脚标注"第 X-Y 列"、"…列）"），不是硬挤或丢列；③ 缩到 < 35% 时**页脚提示"可能难以阅读"**。验收按**设备像素级**：真实 `QPrinter` 几何下断言每页 `sum(列宽) ≤ 可用宽度`（即用户提的"所有列都在页内"）+ `PDF 页数 == 计划页数`。**三个真 bug 都是测试抓到的**：① `data["rows"]` 是 `(行号, [单元格…])`，横向分页要切**单元格那一半**（我切了外层元组 → 每页带着整行）；② 抽 `_natural_column_widths` 时**丢了 `usable_w/180` 单位归一化** → 毫米宽对上设备像素 → "永远放得下" → **横向分页永不触发**；③ 浮点 `int(58.9/0.4909)=119` → 刚好塞满的表**多一页**。**R9**（`fidelity_report.py`）：`LossItem` 增加**位置**（`第 3 段：『片段…』`），`detail_lines()`/`format_report()` 自动带上（对话框与导出报告两条路都有）；位置**有上限**（每项 5 处，其余"…等 N 处"）、片段**截断 18 字**、**定位不到的（宏/图表等包级部件）不编造位置**。测试 **21 + 13 条**，已加入门禁 `print-fit-modes`、`loss-locations` | 新增 34 条测试 |
| 2026-10-15 | A | **R5：蜜算 AI 助手 + 用真模型验收输出质量**（`beesheet_ai_mixin.py`；工具栏「🤖 AI ▾」）。蜜算原先 **0 处 AI**。做三件事：① **自然语言 → 公式建议**（只给公式+解释，**绝不自动改数据**）；② **解释表格问题**（事实由**本地规则**查出：错误值/重复行/空单元格，AI 只解释）；③ **表格摘要**。**"本地优先"贯穿**：无可用 AI 或调用失败时**先说明原因并征求同意（默认「否」）**，同意后才给本地结果且标注"不是 AI"；本地公式用关键词匹配（**最长命中优先** —— 否则"满足条件求和"被泛化的"求和"抢走、给出 SUM 而非 SUMIF，测试当场抓到）；本地摘要只做统计并如实写明不是 AI。**上下文构造带上实测教训**：只送"形状 + **列字母与列名对应** + 带**真实行号**的少量样本"，**绝不上整表** —— 第一版漏了列字母，真模型就把"数量×单价"写成 **`=A2*B2`**（应为 `=C2*D2`），摘要也说"nan 在数量和金额列"（列名张冠李戴）；补上列字母与行号后**同一模型**给出：公式 **`=C2*D2`** ✅、摘要"5 行数据、A002 重复两行、缺失值属于 A004、单价 30–100" ✅ **全部正确** —— 这是"真实验收"才抓得到的缺陷（流程测试全绿也发现不了）。**模型能力（如实说）**：本机 `llama3.2`(3B) 单次 **27–84 s**，中文**推理类**任务偏弱（"解释问题"会复读、绕圈、严重度排序不合理），公式与摘要可用；AI 设置里 Ollama 提示已改为**实测措辞**（建议 `qwen2.5:7b` 以上、说明 20–50 s/次）。另修：本地模型超时被云端口径（30 s）卡死 → 本地 300 s / 测试连接 120 s。测试 **28 条**，已加入门禁 `sheet-ai` | 新增 28 条测试 |
| 2026-10-14 | A | **R6：本地备份与恢复中心**（`beeoffice/backup.py` 核心 + `backup_center.py` 界面 + 保存挂点）。WPS 有"备份中心"，我们原先只有 5 分钟自动保存 —— **看不到、回不去**，且自动保存**直接覆盖**（写坏就没了）。做法：① **覆盖前自动留档** —— `_autosave()` 与 `_save_current()` 都先调 `_backup_before_save(reason="before_save")`，备的是**上一个好状态**；② **原子写**（`.tmp` → `os.replace`），备份自身不留半份；③ **恢复也可回退**（`restore()` 先留 `before_restore`）；④ **轮转有上限**（每文件默认留 10 份 + 总容量默认 512 MB，超了**最旧优先**删，**但至少留最新一份**）；⑤ **目录不可写快速失败**（返回 None、只警告一次，沿用 R7 教训）；⑥ **备份失败绝不阻断保存**。入口：帮助菜单「🗂️ 备份与恢复」（列表 + 恢复/另存为/打开目录/删除/清理）+「立即备份当前文件」；恢复后**问用户是否立即重开**（避免"文件换了界面没换"）。**踩到的设计缺陷**：容量上限**会把历史全删光**（测试当场抓到）→ 改为至少保留最新一份。测试 **27 条**（创建/命名可排序/同秒不覆盖/无临时残留/新在前/同名不同目录隔离/垃圾文件忽略/恢复覆盖+恢复前留档/无目标时落到真可写位置/轮转保最新 N/容量不删光/目录不可写返回 None/界面空态与确认"否"不做任何事/**保存挂点三条**）。已加入门禁 `backup-restore` | 新增 27 条测试 |
| 2026-10-14 | A | **R7：图片回退"快速失败" + 两处更正**。**更正 1**：§8.2 里那个"只读目录 + 23 图 → 完整打开 50.7 s"**是我的夹具问题**。改用可靠判据（等 `_current_file_path` 已设置**且正文长度连续 5 次采样不变**）复测同一文件：**可写目录 2969 ms / 只读目录 785 ms**，直接 `import_from_docx` **79 ms** —— 同量级、只读位置**并不更慢**。原判据只等"标签出现就计时"，而 tab **先建、内容后到** → 读到未装载完状态。**该数字作废**。**更正 2**：我一度以为"GUI 里 713 字符 vs Markdown 3592 字符 = 丢了 79% 正文"，也是**误报** —— 那份 Markdown 里 **2903 字符（81%）是图片链接**（只读位置触发回退、链接写成绝对路径）；剔掉图片链接后正文 565 vs 富文本 589 → **无内容丢失**。这是本 session 第三次"仪器误报"（前两次：并行跑性能测试 19ms 测成 108ms；避头尾 spike 两版仪器坏）。**实际修复（可信）**：`_media_cache_root()` 原先在"所有候选都不可写"时**兜底返回 `tempfile.gettempdir()`**（它本身也可能不可写）→ 调用方拿到**已知不可写**目录 → **每张图各失败一次**（23 张图 = 23 次异常，日志一片 error）。改为候选全不可写即返回 `None`，`_resolve_media_dir()` 返回 `(None, "")`，`import_from_docx()` **一次性放弃提取图片**、正文照常导入并给**一条明确说明**（提示把文件复制到可写目录）。新增 `test_r7_media_fallback.py` **6 条**（含"可写回退仍正常出图"的对照组、无图文档不受影响）；**变异验证**：① 恢复旧兜底 → 2 条失败；② 绕过写探测 → **端到端那条失败**（证明它真守住了用户可见行为）。**"可取消+进度"按实测降级为不做**：DOCX 打开实测 0.8–3.0 s，为 1–3 秒操作加取消按钮不划算（蜜算那条是给几十万行大文件用的） | 新增 6 条测试 |
| 2026-10-14 | A | **R4：嵌套表格保真 + 保真度报告可导出**。嵌套表格曾是**唯一剩下的内容级丢失**（往返后 `w:tbl` **2→1**、内层文字一并消失）。做法沿用既有 extras 模式：新增 `_read_nested_tables()`（记录**结构 + 每格文字**，只处理一层）与 `apply_nested_tables()`（在单元格里 `add_table` 重建，重复调用幂等、越界/行列不齐都跳过而不毁导出）；`read_docx_extras()` 增加 `nested_tables` 键，`export_to_docx()` 增加同名参数，并透传 `beewrite_doc_mixin.get_docx_extras()` 与 `beewrite_export_mixin` 的导出调用。**保真范围如实说明**：只保结构+文字；内层**字体/边框/底色不保**；内层内容**在编辑器里看不到**（Markdown 表达不了，与合并单元格/书签同取舍）。顺带完成 `fidelity_report.write_report_file()` —— 保真度报告**可导出成文件**（竞品普遍不做；写失败返回 False 而不假装成功）。**必要的一致性修正**：嵌套表格既已能保，检测器里那条**从"内容丢失(HIGH)"降为"仅格式不保(MEDIUM)"**并改写措辞，同时加 `test_nested_table_wording_matches_reality` 钉住"措辞与事实一致"——否则就是对用户的误报。测试 12 条 | 新增 12 条测试 |
| 2026-10-14 | A | **R10：回归门禁固化**（`tools/check_gates.py` + CI 步骤）。动机：本轮每次修复背后都有一次真实踩坑，而**只写在文档里不够 —— 下一轮改代码的人不会读文档**。**14 项门禁**，逐条写明"守的是哪次踩坑"（DOCX O(N²)、公式逐格扫描、惰性载入写坏文件、蜜算热路径不变量、真实文档零丢失、损失提示不误报、嵌套表格、打印不变量、AI 不得静默插模板、撤销边界、拼写白名单、AI 设置落盘、ruff bug 类、蜜算耗时）。**刻意分两类**：确定性门禁（调用次数/结构/文件内容）**失败即红**；**计时门禁默认只报告**（`--strict-timing` 才卡），因为绝对耗时会被机器负载污染（本项目已两次被骗：2817ms→5199ms、19ms→108ms）。已接入 CI「回归门禁」步骤。**门禁自身有牙（已验证）**：把 O(N²) 塞回 `set_markdown` → `docx-open-on2` 立刻 FAIL 并报"调用了 to_markdown 1 次 —— O(N²) 回来了"，随后还原。**踩坑**：runner 第一版用 `target.split()` 拆参数，把 `-k 'a or b'` 拆坏（引号失效 → pytest 报 `file or directory not found: or` → **假失败**），改用 `shlex.split()` 后 14 项全绿（全套约 1.5 分钟） | 新增门禁 runner + CI 步骤 |
| 2026-10-14 | A | **R2 spike：中文"避头尾"可行性判定**（只判定不实现；见 `docs/r2-中文排版-spike.md`）。方法：排版后读 `QTextLayout` 的实际断行，统计"行首出现收尾标点 / 行尾出现开启标点"，并用 `U+200B` 人为造断点作**负对照**。**结论（裸 `QTextDocument` 与真实蜜写编辑器一致）**：① **避头是 Qt 自带的**（默认 0 违规；负对照 115 / 237 处）→ 不用做，也不必插 `U+2060`；② **避尾没做**（默认 21 违规；负对照 316 / 537 处）→ 只需在 6 个开启标点后插 `U+2060`；③ **标点挤压**：`QTextOption` 无任何相关开关，需自定义 layout → **建议不做**。**因此 R2 从"2–3 人日大项"缩小为"只做避尾"**，但代价在**副作用**而非插入本身：零宽字符会进 `toPlainText()` → **字数统计 / Markdown 与 DOCX 导出 / 保存都要剥离**，且属"程序改了用户文本"（影响 undo/redo 与光标）→ **≈2 人日**，只能人眼验收。**排期**：排在 R1 真机验证之后，且**先写"导出与统计不含零宽字符"的测试**再改插入逻辑（否则把"排版好了"换成"导出文件混入看不见的字符"）。**spike 元教训（重要）**：前两版都得出"Qt 已完美（0 违规）"却是**仪器坏了** —— v1 读 `block.layout().lineCount()` 前**未强制触发布局** → 行列表为空（`violations([])` 当然是 0）；v2 修了布局，但文本 33 字一循环、行宽恰好每行 12 字，`12n ≡ 标点位置 (mod 33)` **无解** → 断点**在数论上永远撞不上**标点，测试**不可能失败**；v4 避尾的负对照又因插在标点后的 `U+200B` 成了行末字符而判不到（判据改为**先剥离零宽字符**再看首尾）。**"0 违规"这类好消息，必须先证明仪器能报出违规** | 无代码改动 |
| 2026-10-14 | A | **R1：蜜算表格两阶段载入 + "保存安全门"**（`beesheet.py` / `beesheet_model.py` / `beesheet_data_mixin.py` / `beesheet_chart_mixin.py` / `beesheet_rowcol_mixin.py`）。**先定的安全前提**：`write_workbook` 是"打开源工作簿只更新值"，拿**部分载入**的数据去写会**前 N 行被覆盖、其余行留旧值** —— 实测（新测试钉死）：部分载入 10 行 → 排序 → 保存，结果前 10 行倒序、第 11–40 行仍是旧值，**文件与界面不一致**。选定的设计让安全**是构造出来的**：① 阶段 1 只读前 500 行立刻显示；② **加载期间 `flags()` 一律只读**，于是阶段 2 的整体替换不可能丢用户改动（不需要任何"合并/重放编辑"逻辑）；③ **`ensure_fully_loaded()` 安全门**挂在**保存 / 导出 CSV / 排序 / 筛选 / 透视表 / 插入图表 / 批量填充**共 7 个入口，补全失败则**拒绝操作并说明**（绝不写半份数据）；④ 只对 **>1 MB 的 xlsx** 启用（1.4 MB 实测急切载入 2.27 s 才值得；小文件与 CSV 保持原路径）。**踩坑**：`lazy` 变量在 CSV 分支未初始化会 NameError；`_ensure_full_data` 里重复 import 模块级已有的 `QApplication` 被**我自己加的 ruff F811 阻断规则**抓住。测试 **11 + 12 条**：模型只读/补全/失败不撒谎、阈值、阶段 1 可见且只读、阶段 2 完成恢复可编辑、**门在导出/保存/排序上真的拦住**（端到端）、以及**"两阶段后保存 == 直接全量保存"逐格一致** | 新增 23 条测试 |
| 2026-10-14 | A | **R3：拼写检查「技术词白名单」**（子代理完成，我独立复核）。背景：装真词典后对 7 份真实中文技术文档**误报 619 处**（CentOS 313、yum 217…）。新增 `beeoffice/data/tech_words.txt`（**611 词条 / 526 去重**，按操作系统/命令/数据库/云与虚拟化/编程概念等分组，含 `CentOS7`/`ens33`/`WinSCP` 等大小写数字混写形式），`spellcheck.py` 增量接入：`load_tech_words()`（UTF-8/BOM、忽略注释空行、全小写、缺失/损坏都只记 debug 返回空集）、惰性缓存 + PEP 562 `TECH_WORDS`（import 时不读盘、永不因词表崩）、经既有 `add_to_dictionary` 并入 `_dictionary`（复用 `knows()` 一条判断路）、新增 `use_tech_words=True` 开关、`save_dictionary` **不再把白名单写进用户词典**。**语料实测（不依赖后端）**：可检查拉丁词 1592 处/335 词，**命中白名单 723 处/106 词**，技术词漏检 **0**。**设计取舍（子代理提出并给理由）**：白名单**只套在通过"英文词典功能自检"的后端**上 —— 因为既有 `test_spellcheck.py` 断言"全判错桩后端必须报出每一个可分词"，无条件套白名单会把 830 变 473 而该文件不允许改；真实词典路径（GUI 默认）**照常享受白名单**，产品收益不受影响。**三次变异验证**：清空词表 → 13 条失败；开关失效 → 3 条失败；去掉英文自检门 → 既有那条断言失败（830→473）。**未验证**："误报 < 50" 只有残余量估计（本机无英文后端，已 skip），需真机装词典后复测 | 新增 29 条测试 |
| 2026-10-14 | A | **更正：性能测试"退化"是 CPU 争抢导致的假警报**。并行做 R1/R3 时 `test_beesheet_hotpath` 报"整视口重绘 108–115 ms（优化后约 19ms）"，我**没有直接采信**：先量化 `flags()` 单次成本（4.93 µs，216 次/帧 ≈ 1.07 ms，我新增的只占 0.02–0.06 ms），再等子代理结束、**空载复测 → 17 passed / 5.4 s 通过**，确认是并行跑测试抢 CPU。**这是本项目第二次栽在"被污染的机器上测性能"**（第一次是 xlsx 预检时把 2817ms 测成 5199ms）；纪律再次明确：**性能测试必须在空载下跑，且看到矛盾数字先查测量条件** | 无代码改动 |
| 2026-10-14 | A | **蜜写「AI 辅助」接真 LLM（方案 A）**。改造前：三个功能**完全不联网**（续写 = `random.choice(12 条硬编码句库)`，与上下文无关）却提示"✅ AI 续写完成"。新增 `ai_client.py`（通用文本 AI 客户端，OpenAI 兼容，配置取自「🤖 AI 设置」的 `ai_api_key/api_base/model`；本地地址免 Key；`last_source` 区分 **ai/local/error**；`unavailable_reason()` 具体指出缺哪一项；输入截断 6000 字）。`beewrite_ai_mixin.py` 重写：**① 优先真 LLM 走后台线程**（`AsyncTaskManager`，生成要几秒不能卡界面）、成功时状态栏写 `AI 生成（模型名）`；**② 没有可用 AI 或调用失败时绝不静默插模板** —— 先弹框说明原因并**征求同意（默认「否」）**，同意后才用本地规则且状态栏明写"**不是 AI 生成**"；**③ AI 菜单里直接加「⚙️ AI 设置…」**（否则用户在写作场景不知道去哪填 Key，配置变更后清空客户端缓存）。**顺带修一个会误导人的提示**：`AIClient` 对空地址/空模型会回落到 DeepSeek 默认值，于是"自定义网关 + 只填 Key"的用户会遇到 404，而原提示只说"地址不对" → 改为同时提醒**接口地址与模型名**。**测试** 27 条（全用桩客户端/假传输层，**不联网**）：客户端可用性/来源标注/失败不抛异常/空内容/截断/本地不发 Authorization、四个提示词要点（续写带上下文且只要结果、润色保原意与数字、总结**必须压缩**、关键词计数）、Mixin 三条规则与菜单入口。**变异验证**：注释掉"征求同意"那一步 → **3 条守护"不得静默插入"的测试立刻失败**；另修掉我自己写错的测试替身（用 `self.__class__ = type(...)` 合成类会丢掉替身自己的方法，11 条用例因此失败） | 新增 27 条测试 |
| 2026-10-14 | A | **审计发现：蜜写的「AI 辅助」不是 AI**（用户问"AI 功能用的什么产品"时查出来的，**本行只记录，未改代码**）。全量清点后有**三类**完全不同性质的东西都挂着 "AI" 招牌：① **蜜演 AI 大纲/细化/讲稿** = 真 LLM，默认 **DeepSeek**（`https://api.deepseek.com/v1` + `deepseek-chat`，OpenAI 兼容协议，`_call_llm`）；② **蜜写 AI 续写/润色/总结**（工具菜单「AI 辅助」）= **纯本地规则，完全不联网** —— `ai_assist.py` 只 import `re/random/logging/typing`，实测：**续写 = `random.choice(CONTINUATION_POOL)` 从 12 条硬编码句库里随机抽 1–2 句**（同一输入连续 6 次得到 6 段互不相同且与上下文无关的话，如"随着技术的不断发展，这一趋势将持续下去。"），**润色 = 同义词替换**（"挺好"→"挺优秀"、"小问题"→"微小问题"，而它自己 docstring 说要清理的口语"我觉得吧"原样留着），**总结 = 按句长取前 3 句**（3 句的输入会原样返回全部，零压缩）；③ **蜜演 AI 配图** = 图库搜索 API（Unsplash/Pexels，无 Key 退回 picsum 占位图），**不是 AI 模型**。**关键关联**：刚做的 AI 设置界面**只对蜜演生效**，蜜写的三个"AI"功能**根本不读那些设置**。**风险**：用户点"AI 续写"会往文档里插入与上下文无关的模板句，且提示是"✅ AI 续写完成"；蜜演有 `last_source`(ai/local/error) 如实标注来源的机制，蜜写**没有**。**建议（待产品决策）**：A. 把蜜写三个功能接到同一个 LLM 服务（复用刚建的 AI 设置），规则版降级为无 Key 时的兜底并**如实标注来源**（推荐）；B. 最小改动：菜单/提示改名为"续写（模板句）/本地润色/提取式摘要"，不再叫 AI | 无代码改动 |
| 2026-10-14 | A | **AI 设置界面**（新功能，`ai_settings.py`）。起因：查"AI 功能用的什么产品"时发现蜜演的 AI（AI 大纲/细化/讲稿）此前**没有任何可视化配置入口** —— `ai_api_key`/`ai_api_base`/`ai_model` 只有存储层读写，用户得**手动改 `~/.beeoffice_settings.json`**（连失败提示都是这么教用户的），于是点了「AI 大纲」只看到降级模板却不知去哪填 Key。新增对话框：**服务商预设下拉**（DeepSeek 默认 / OpenAI 兼容自定义 / 本地 Ollama）、API Key（可显示/隐藏）、接口地址、模型名（下拉可编辑）、**「测试连接」**（后台线程 + `max_tokens=8` + 超时 12s）、隐私说明（"只发给你选的服务，想完全离线用本地 Ollama"）；入口 = 帮助菜单「🤖 AI 设置」。**失败提示要可操作**：401/403 → 检查 Key 与余额、404 → 地址应以 `/v1` 结尾、429 → 额度/频率、拒连且是本地 → 提示 `ollama serve`、解析失败 → 地址写错。**校验分服务商**：DeepSeek 缺 Key 拦下并告知去 platform.deepseek.com 申请，**Ollama 免 Key 不拦**；保存写回 `AppSettings`（Key 仍是 base64，**不是加密**，已在文档写明）。**踩到两个坑**：① 生产函数原名 `test_ai_connection` → **被 pytest 当成测试用例收集**（还因返回 tuple 报警告），改名 `probe_ai_connection` 并检查全仓无同类命名；② 变异验证时把 Ollama 的 `needs_key` 改成 True，`_save()` 走到 `QMessageBox.warning` **真弹模态框 → 用例挂死 120 秒**，遂补 autouse 夹具全局拦截模态框（拼写检查那边犯过同样的错）。**变异验证**：去掉 `settings.save()` → 两条持久化测试失败（证明验证的是**落盘**而非内存）；`needs_key` 改 True → 两条策略测试在 1.5s 内失败（不再挂起） | 新增 36 条测试 |
| 2026-10-14 | A | **P1-B ★：拼写检查（按需形态）**。核心模块 `spellcheck.py`（856 行，仅标准库，不 import PySide6）：后端按优先级探测 Windows 原生 `ISpellChecker`（ctypes COM）→ `pyspellchecker` → `pyenchant` → 明确降级；`tokenize_words` 跳过中文/数字/URL/代码块/驼峰标识符；`SpellCheckerService`（ignore / add_to_dictionary / check_text）。**形态由实测数据决定**：装上真英文词典后对 `tests/fidelity/corpus/` 7 份**真实中文技术文档**逐字实测，**误报 619 处**（`CentOS`/`mysql`/`yum`/`Xshell`/`VMware`/`ens33` 全被判错；单份最高 313 处）→ **不做常驻红波浪线**（否则用户满屏红字），改为**按需对话框** `beewrite_spellcheck_dialog.py`：列表（词/建议可改/所在行）+ 替换/全部替换/忽略/**全部忽略**/**加入词典**（写 `~/.beeoffice_dictionary.txt` 永久生效）+ 双击定位；入口 = 工具栏「🔤 拼写检查」。**本机后端实测不可用**且原因是具体的：Windows 原生接口 `CoCreateInstance` 成功但只装了 `zh-Latn-CN-x-ext`（无英文语言包，`IsSupported("en-US")`=FALSE），而该中文检查器把 `hello/world/this/is/test` 全部判错 —— 实现因此不信任"dll 注册/语言存在"，改用 `hello world the computer document` 做**功能自检**后才启用；不可用时入口弹框说明原因与启用办法，**不假装检查过**。**测试**：`test_spellcheck.py` 55 passed/1 skipped（由子代理完成，含 10 次"改坏实现验证测试有牙"记录）+ `test_spellcheck_dialog.py` 18 passed（桩后端，确定性验证替换偏移/忽略/词典持久化/定位/不可用提示）。**踩坑**：服务实际调用 `backend.check()` 而非 `check_word()`（我桩写错 → 列表恒空）；`replace_all` 在"无可替换"时弹**模态框**导致用例**挂死**（已加全局拦截）；`setText` 后再 `refresh()` 会把提示覆盖掉（用户永远看不到"词典保存失败"）。**未验证**：真词典下的**建议质量**（本机无可用后端）；619 这份数据说明**默认词典对技术文档不友好**，建议后续内置技术词白名单 | 新增 18 + 55 条测试 |
| 2026-10-14 | A | **P1-B ★★：蜜演打印**（新功能，`beeshow_print_mixin.py`）。蜜演此前也没有打印。入口 = 工具栏「🖨️ 打印」+ `Ctrl+P`；四种方式：**幻灯片**（每页 1 张）、**讲义**（每页 2/3/4/6/9 张，`HANDOUT_LAYOUTS` 网格）、**备注页**（缩略图 + `_speaker_notes` 备注）、**大纲**（标题列表，取自 `_slides_md` 并去 Markdown 前缀）；页脚页码、缺图画占位框。取画面复用已有路子：`render_slide_html` → `QWebEngineView.loadHtml` → `printToPdf` → `QPdfDocument` 栅格化 → QPainter 拼版。**分层**：① `_build_print_plan()` 纯数据；② `_paint_plan()` 只吃 QImage；③ `_slides_pdf()` 唯一依赖 WebEngine，失败返回 `False` 并由调用方明确提示（**绝不静默变空白打印**）。本沙箱 QtWebEngine 不可用，不分层则无法验证。**测试 31 条首次全过**：计划（分页/网格位置/末页部分/非法值退回 4/备注/大纲/页码/空演示）、**像素级绘制验证**（4 张不同颜色合成图 → 渲染 PDF → PyMuPDF 逐像素回读四格中心，证明第 N 张落在第 N 格）、栅格化（颜色/宽高比/坏路径）、WebEngine 层优雅失败、选项解析。**"有牙"验证**：临时把网格行列算反 → 像素测试立刻失败并报"右上格颜色 (0,0,254) ≠ 期望 (0,255,0)"，随后恢复。**未验证**：`_slides_pdf()` 的 WebEngine 渲染本身需真实环境确认 | 新增 31 条测试 |
| 2026-10-14 | A | **P1-B ★★★：蜜算打印**（新功能，`beesheet_print_mixin.py`）。实机清点发现打印只实现在蜜写，**蜜算 0 处** —— 表格打印是办公刚需。实现：**分页**、**跨页重复标题行**、**缩放适应页宽**、行号/列标（A/B/C…）、页脚（工作表名 + `第 X / Y 页`）、**选区优先**、超行数截断（`MAX_PRINT_ROWS`）、列多自动横向；入口 = 工具栏「🖨️ 打印预览」+ `Ctrl+P` + `QPrintPreviewDialog`。**架构**：排版决策放在纯数据 `_build_print_plan()`（可测），绘制层只负责画 —— 因为**本沙箱 Qt 一个字体都没有**（`QFontDatabase.families()` 返回 **0**，`PySide6/lib/fonts` 不存在），PDF 与栅格输出**都画不出字**（连蜜写原有的 `QTextDocument.print_()` 也一样），"渲染 PDF 再提文字"的验证方式**在本环境不可用**；改用"**PDF 实际页数 == 计划页数**"这个与字体无关的不变量把绘制与计划锁在一起。**踩过两个坑**：① 单位混用（painter 按毫米缩放 ×47 而字号是磅，1200dpi 下算成 2350px，**一个字都没画出来**）→ 改为**设备像素 + 真实磅值**；② `set_full_dataframe` 会把数据**补齐到默认行数**，拿 `len(df)` 当已用区域导致 **2 行的表打印 24 页** → 改为**向量化**计算真实已用区域。**首次实现 20 条测试全过**（含页数不变量、重复标题行、选区、截断、列宽不退化） | 新增 20 条测试 |
| 2026-10-14 | A | **更正：蜜写表格"删除一行 127ms"是我的误判**。原先那个数字是**单次测量**、混入首次布局/缓存冷启动。改 10 次取中位数并按规模扫描：6 行 **0.46ms** / 50 行 3.11ms / 200 行 11.66ms / 800 行 59.47ms（含重绘分别为 1.11 / 4.02 / 5.29 / 4.65ms）。**重绘是常数 ~5ms，慢的是操作本身且为 O(行数)** —— 这是 Qt `QTextTable` 结构编辑的固有代价，不是我们的代码问题；常见规模（≤50 行）**约 3ms 完全跟手**。**因此不做优化**（要动就得换掉 `QTextTable` 或延后重排，风险高收益窄）。**这是本项目第二次被"单次测量"骗**（上一次是"设置保存重试 2.4s"，实测仅 0.5ms）；方法学教训：性能数字必须**多次取中位数**，并把"操作"与"重绘"分开计时 | 无代码改动 |
| 2026-10-14 | A | **P1-B 实机试用定位 + 顺手修两处**。用户要求"运行程序进行试用定位"，于是**跑程序实测**而非读代码猜（详见 `docs/p1b-试用定位.md`）。**三项更正我先前的说法**：① "打印薄弱" —— 实为**蜜写完整**（工具栏「🖨️ 打印预览」+ Ctrl+P + 右键菜单 + `QPrintPreviewDialog`）而**蜜算/蜜演 0 处实现**；② "拼写检查薄弱" —— 实为**根本不存在**（13 处匹配全是 changelog 注释、审计提示、错误提示语，无字典/算法/UI）；③ "打字 4.34ms" —— 那次控件**隐藏**、不含真实绘制；**可见状态实测 13.66ms**（滚动 8.04ms 良好）。**实测缺陷 1（数据安全，已修）**：装载文档后 `isUndoAvailable()` 即为 True（`set_markdown` 逐块插入也进撤销栈），**用户什么都不改按 Ctrl+Z 就会删掉正文**（689→677→676）→ 新增 `reset_undo_history()` 在**文件加载完成**时清栈（不放进 `set_markdown`，否则用户编辑中途切模式会丢自己的历史）；端到端验证 `isUndoAvailable: False`、撤销后 689→689 未改动、且输入后撤销仍精确回退 ✓。**实测缺陷 2（最差失败模式，已修）**：打开 `.doc/.pptx` 等不支持类型时**只写一行日志** —— 不弹提示、不开标签、**还记进"最近文件"**，用户以为程序坏了 → 改为明确弹框说明支持格式并**不再记入最近文件**（真正的 `.doc` 读取需 LibreOffice/COM 依赖，**建议不做**，提示另存更合适）。**其它定位**：蜜写表格插入 50 行 559ms、插入一行 35ms、**删除一行 127ms（可感知顿挫）**；蜜算打印为最高优先待做项（表格分页/缩放/重复标题行） | 新增 8 条测试 |
| 2026-10-14 | A | **P1-A：导出前「损失提示」**。新增 `beeoffice/plugins/fidelity_report.py`：打开文件时分析**源文件**里"保不住"的构造，**导出前**弹一次确认列出明细（纯能力降级只在状态栏提示，不打断）。**规则全部来自逐项往返实测**（新增 `tests/fidelity/_docx_features.py` 直接注入 OOXML 造出脚注/批注/文本框/公式/嵌套表格/修订/内容控件/目录域/VML 夹具）：内容真会丢的（high）= 嵌套表格、文本框、公式(OMML)、脚注/尾注、批注、VML 图形、宏、OLE、SmartArt、图表；只丢能力的（medium）= 目录域（文字在、不能更新）、内容控件（文字在、结构没了）、修订痕迹（内容去向正确、痕迹没了）。**两条验收线**：① 不漏报（9 类各有夹具）；② **不误报** —— 10 份已实测零丢失的真实文档必须**零输出**。**第一版在此翻车**：按"`word/footnotes.xml` 部件存在"判定脚注，而**每个 DOCX 默认都带 `footnotes.xml`/`endnotes.xml`**（只含分隔符，id -1/0）→ 7 份真实文档中 **3 份被误报**；改为按**实际引用**（`w:footnoteReference`/`w:endnoteReference`/`w:commentReference`）计数后全部干净。另外旧格式 `.doc/.xls/.ppt`、`.pptx`（蜜演无导入）、加密/损坏文件各有说明。顺带修掉自己的接线 bug：`_attach_fidelity_report` 里写成 `if hasattr(widget, "_fidelity_report")` —— 首次打开时该属性不存在 → 报告永远挂不上（被测试抓出） | 新增 36 条测试 |
| 2026-10-14 | A | **P0-B（收尾）：蜜算公式扫描的字节级预检（1.85×）**。逐格扫描找公式在 5000×50 上要 **2635 ms**，但绝大多数数值表格**一个公式都没有**。改为先在 worksheet XML 字节里找 `<f`（**29.9 ms**，约 90× 快），找不到就整张表跳过。映射用 `xl/workbook.xml` + `rels` **按关系精确对应**（不假设 sheet1.xml 是首表）；预检失败返回空 dict → **退回全表扫描**（宁可慢，不能漏公式）；只判"有没有"、不解析公式内容，以完整保留**共享公式**（`t="shared"`）的既有正确性。**严格验证**：同一次运行内**交替**测"旧行为（预检未知→全表扫描）"与"新行为"，抵消机器波动 —— 5000×50 **9578.8 → 5177.2 ms（1.85×）**、50000×20 **23573.5 → 12615.9 ms（1.87×）**、含 4 公式的 `xlsx_rich` 无变化且**公式数一致** ✓。**⚠️ 同时更正我先前的错误说法**：报告里"`read_only` 有 500× 杠杆"是**合成测量**——那只比了 `load_workbook` 的**解析**（3.010 s vs 0.006 s），而**没测"物化单元格"**。真实拆解显示成本在把 25 万格变成 Python 对象（`pd.read_excel` 2275 ms / `ws.values`→DataFrame 2648 ms / `list(ws.values)`→DataFrame 2487 ms，三条路同量级），`read_only` 省下的是那 8 ms 的解析。**合成基准 ≠ 真实路径，这是本项目第 N 次栽在这上面**。**剩余未解决**：值物化是纯 Python 读取器的地板；再上台阶需惰性/分块加载，但牵涉**保存安全**（只加载一部分就保存会把不完整数据写回源文件），属需专门设计的改动 | 新增 8 条测试 |
| 2026-10-14 | A | **P0-B（后半）：DOCX 打开 17.7 s → 1.38 s，根因是 O(N²) 状态栏统计**。分段计时把 7 秒精确落在 `rich_editor.set_markdown()`；但**孤立测该方法只要 0.12 s**（矛盾），于是**抓调用栈**定案：`set_markdown` 逐块插入 → 每块触发 `textChanged → _update_status_bar` → `self.content()` → **`rich_editor.to_markdown()` 整篇转换**，**只为数字数**（实测打开一份文档时 `to_markdown` 被调用 **1032 次 / 6.2 s**）→ N 个块即 N 次全篇转换。修法两处：① 统计改取**纯文本**（`toPlainText()`），不做 Markdown 转换；② **批量加载期间合并刷新**（`set_markdown` 置 `_loading_markdown`，状态栏更新改 `QTimer.singleShot(0)` 延迟合并，交互路径行为不变）。**实测：`set_markdown` 6976.9 → 278.2 ms（25×）、打开总耗时 8000 → 1379 ms；2.5 MB 文档 4889 → 1262 ms**。与 WPS 的差距从 **5.9–15.5 倍缩到 1.2–1.5 倍**。⚠️ **一处有意的行为变化**：字数/字符原先统计 Markdown 源码（含 `#`/`**`/`![]()`），现统计**用户看到的正文** —— 蜜写相关测试（含 `test_v505_status_timer.py`）全部通过。**方法学教训**：孤立基准与真实路径不一致时，差异本身就是线索（我先是按日志时间差推断"渲染管线慢"，方向对但太粗） | 无新增测试（既有 94 条蜜写测试覆盖） |
| 2026-10-14 | A | **P0-B：蜜算绘制热路径优化（滚动 337 ms → 23.6 ms，14.3×）**。报告 §4.5 实测蜜算滚动 **337 ms/帧（≈3 fps）**、单次重绘 172 ms。**profile 真实重绘**（而不是合成基准）后定位：每帧 `data()` 被调用 **1,512 次**、`flags()` 216 次，瓶颈是这两者的单次成本。三项改动：① `len(self._loaded_df)` 每次 `data()` 只算**一次**（原 3 次；它走 pandas `__len__`→RangeIndex，实测占该函数约 25%）；② role 用**预绑定常量**比较、`flags()` 的两个标志值**预先算好**（原先每次现算枚举 `|`，实测 32 µs/次 ×1080/帧）；③ 取值改走 **numpy 按列视图**。**"按列"是同时做到"快"与"对"的关键**：`_loaded_df` 有**约 40 处就地修改**，而整帧 `to_numpy()` 只在**单 dtype** 时是视图、**混合 dtype 时是副本**（会让用户改完单元格后仍显示旧值）；每列必然单一 dtype，`Series.to_numpy()` 即该列视图 ✓。失效判定用"对象身份 + 列数"，纯值修改无需重建。（实测 `ndarray.flags.owndata` 在所有情况下均为 False，**不能**用它判断视图/副本。）**另一个坑**：走视图后取到 `np.int64`，而 NumPy 标量**不是** Python `int` —— 原来只写 `isinstance(val,(int,float))` 会让数字**不再右对齐**，故新增 `_NUMERIC_TYPES`。**同时更正两处我自己的错误结论**：（a）"设置保存失败重试阻塞 2.4 s"是**从日志时间差推断**的，实测 `atomic_write_json` 被拒仅 **0.5 ms** 快速失败 —— 该问题不存在，已撤回；（b）`sizeHintForIndex` 1.787 ms 是**合成测量**（我显式逐格调用它），**正常绘制路径并不逐格调用**，真实开销在 `data()`/`flags()`，据此"算平"的账是错的 | 新增 18 条测试（含新鲜度回归与性能门禁） |
| 2026-10-14 | A | **P0-A：稳健性止血**。① **日志目录不可写 → 启动即崩**：`main.py` 的 `setup_logging()` 直接调 `logging.basicConfig(filename=…)` 且**无 try 保护**，用正确入口 `python -m beeoffice.main` 复现出真实 traceback（`PermissionError: … .beeoffice_logs\app.log`）——企业只读家目录/漫游配置损坏/磁盘满时**程序会在任何界面出现前退出**。现包 try/except，失败退回标准错误并记 `LOGGING_DEGRADED` 由状态栏提示（实测进程不再退出）。② **图片提取写到文档旁边**：文档在只读位置时 `mkdir`/写入被拒，图片**静默降级为占位文字**。新增 `_resolve_media_dir()`：同级可写则行为不变（保持相对链接），不可写则回退用户缓存目录并把链接写成**绝对路径** | 新增 6 条测试 |
| 2026-10-13 | A | **第十一刀：段落样式（含定义）往返 + 一个只有渲染才看得见的缺陷**。① `styled_paragraphs` 3/7 份丢失（`yum源更新.docx` 有 **41 段 `HTML Preformatted`**，即 Word 给代码文本的**等宽**样式）。难点：**python-docx 默认模板里没有这些样式**（实测 164 个样式里既无 `HTML Preformatted` 也无 `Normal (Web)`），必须连**样式定义**一起搬（含 `w:basedOn` 链）。两个坑：（a）注入定义**必须用 python-docx 自己的解析器** `docx.oxml.parse_xml` —— `lxml.etree.fromstring` 造出的是裸 `_Element`，没有元素类的 `.type`，`doc.styles[name]` 抛 `AttributeError`，且被宽 except 吞掉，表现为"定义注入成功却一段都没应用上"；（b）**同一段落不能被用两次** —— 正文里有内容完全相同的段落（41 段代码记录里就有），只按"第一个文字相同"匹配会让它们全落到同一段上（43 段只装上 36 段）。修复后 3 份全部保住（43 → 43）。② 同轮把导出的 DOCX 用**内置 LibreOffice 渲染**，发现一个**所有结构指标都看不见**的缺陷：源里 `bold=True` 且**结尾带空格**的 run 被转成 `**…媒体 **`，而 Markdown 规定强调的收尾定界符不能紧跟在空白之后 → **星号原样显示在页面上**（`**` 也是字符，字数不变，探针报"零丢失"）。新增 `_wrap_emphasis()` 把首尾空白移到标记外面，重新渲染确认已恢复加粗。③ 7 份导出文件全部通过 skill 自带 `check_office.py` 完整性检查，且 python-docx API 均可正常读取（验证样式注入与部件搬运未损坏文件） | 新增 16 条测试 |
| 2026-10-13 | A | **第十刀：页眉页脚部件搬运 + HYPERLINK 域 → 真超链接**。**两个假设都被实测推翻**：① `fields: 6 → 0` 我以为是"目录/页码/日期域丢失"，把指令打出来才发现全是 `' HYPERLINK "https://…"'` —— **以域形式存的超链接**，丢的是链接目标；修法是用状态机识别复杂域（`w:fldChar` begin/separate/end + `w:instrText`）与简单域（`w:fldSimple`），把 URL 附到域结果区的 run 上。结果 `fields 6→0` 且 `hyperlinks 0→6` —— **信息没丢，只是换成更规范的真 `w:hyperlink`**。② `footer_parts 1→0` 我以为是"只搬文字没搬域"，真正原因是 **python-docx 不进入 `w:sdt`（内容控件）**：那 3 份的页码在**嵌套内容控件**里，`footer.paragraphs` 只返回一个**空段落**，于是被判成"没有页脚"→ 整个部件不写。修法：页眉/页脚改为**整段搬运部件 XML**（仅在含关系引用/图片时退回文字，避免悬空 rId 导致文档损坏），并把段落文字读取统一改为新的 `_paragraph_text()`（能进嵌套容器）。**验证**：输出页脚里 `PAGE`/`NUMPAGES` **域指令都在**、`w:sdt` 也在 —— 是活页码而非写死数字（写死数字换页就错，比丢页脚更糟，故单独有测试）。顺带确认 7 份文档**正文里 0 个 `w:sdt`**，故该问题目前只影响页眉页脚 | 新增 10 条测试 |
| 2026-10-13 | A | **第九刀：DOCX 书签往返**。7 份真实文档里有 5 份带书签，往返后 `bookmarks 1 → 0`。新增 `_read_bookmarks()` / `apply_bookmarks()`（走既有的 extras 通路），**7 份全部保住**。**同时更正一处我先前的判断**：把 5 份的书签名逐个打印后确认**全是 `_GoBack`**（Word 的"上次编辑位置"内部标记，非用户内容、无链接指向、**不会死链**）——我最初推测"多半是目录锚点 `_Toc…`"是错的。**命中数量 ≠ 严重程度**。仍按"往返不改动用户文件"的原则保留它。修的过程中又踩到两个真实细节并写成测试：① 书签所在段落**可能是空段落**（实测两份真实文档的 `_GoBack` 就在空段），空段落在 Markdown 里会丢 → 索引锚点必然失效，故额外记录 `prev_text`（最近的前一个非空段落）；② **同一段落里的多个书签会顺序颠倒**（每次都插在同一位置，实测 `b1,b2` → `b1,b3,b2`），修法是插入时跳过已有的 `bookmarkStart`。**注意语料里只有 `_GoBack`，因此书签功能的测试自己构造了真名书签**（`ch1`）| 新增 16 条测试 |
| 2026-10-13 | A | **第八刀：导入时转义 Markdown/HTML 特殊写法**（用户在 `tests/fidelity/corpus/` 放入两份真实教程后撞出，属**最严重的一类**）。根因：`import_from_docx()` 把原文**直接**塞进 Markdown，任何"长得像 Markdown/HTML"的文字都被重新解释 —— 实测：行首 `#`（shell 注释）被判成标题，文档**凭空多出 13 个"标题 1"**；行内 `<UP,BROADCAST,RUNNING,MULTICAST>` 被当 HTML 标签，**内容整段消失**；行内 `a*b*c` 被当强调变成 `abc`；行首缩进触发代码块并把多段并成一段。修法：新增 `_escape_inline_text()`（行内：`<` `>` `&` 用 **HTML 实体**而非反斜杠 —— Python-Markdown 可转义集合不含它们，实测 `\<UP,…>` 无效；`* _ \` [ ]` 用反斜杠）与 `_escape_block_markers()`（行级：行首块级标记 + 缩进用 `&#32;`/`&#9;` 实体**保留而非 strip**）。**修复后：文字丢失 178→2 字、37→16 字；标题数恢复正常；缩进逐字保住**。**过程中我自己引入并修掉一个 bug**：最初把行级 `lstrip` 也放在按 **run** 调用的行内函数里，而真实文档里 `'原', '  ', '因：'` 是三个 run，纯空格 run 被抹掉导致"原  因"→"原因"——正是这两份真实文件暴露的（合成夹具没有这种 run 切分）。**仍丢失**：页码页脚（页脚装的是**页码域**而非文字，现有传递只搬文字；修它需复制部件 XML）、空段落（Markdown 无法表示） | 新增 28 条测试 + 用户语料 5 条性质断言 |
| 2026-10-11 | A | **第七刀：DOCX 多分节往返**（corpus 撞出的第一项）。`docx_sections.docx`（2 节，第二节横向）原先 `sections 2 → 1`，用户可见后果是**横向页变纵向**、页边距随第一节。新增 `_read_sections()`（逐节读纸张/方向/边距）与 `apply_sections()`（导出时重建）。**难点在定位**：承载 `w:sectPr` 的段落通常是**空段落**，而空段落在 Markdown 里会丢（顶层 5→4），故"按段落索引插回"必然错位 —— 改用**文字锚点**（该节最后一个**非空**段落的文字），对索引偏移免疫。`sections` 提供时由 `apply_sections` 一并处理第一节，不再走单节的 `apply_page_settings`，避免互相覆盖。**实测 `sections` 2→2，第二节仍横向 297×210、左边距 15mm 不变**；真实文件仍 3/3 零差异 | 新增 16 条测试（含"锚点在缺失空段落时仍定位正确"与产品级 `_write_docx`） |
| 2026-10-11 | A | **corpus：拿真实文件与压力语料去撞**。新增 `tools/fidelity_corpus.py`（遍历语料、逐个往返、报丢失；**先在临时目录做副本**再跑，避免往语料目录写 `<名>_media/`）与 `tools/fidelity_corpus_gen.py`（生成 9 个各专攻一维的压力文件）+ `tests/fidelity/test_corpus.py`（14 条）。**真实文件（仓库自带 `test+files/`）3 个全部零差异**（含 2.5 MB / 94 段落 / 2 张图的那个）。**压力语料撞出 3 类新丢失**：`docx_sections` 分节 2→1（横向节会变纵向）、`docx_tables` 表格 4→3（**嵌套表格**整块消失）、`docx_inline` 书签 1→0（内部跳转成死链）；`docx_lists`/`docx_headers`/`xlsx_wide`(200列)/`xlsx_tall`(5000行) 均零丢失。**一次差点误判**：首轮报 2.5 MB 文件 `images 2→0`，查出是该文件 `<名>_media/` **早已存在**（仓库自带，时间戳 2026-09-17）而进程无权覆盖 → 属测量环境假象，修的是工具而非产品。另记录一个行为（非丢失）：非矩形工作表会被 pandas 规范成矩形（非空单元格 25→27） | 新增 14 条测试 + 2 个工具 + corpus README |
| 2026-10-11 | A | **第六刀：DOCX 表格合并往返（最后一项）**。Markdown 表格语法表达不了合并，故沿用"绕开 Markdown"：新增 `_read_table_merges()`（按**网格列号**记录 `表格索引/行/列/colspan/rowspan/合并后文字`，含 `w:vMerge` 纵向合并的行跨度累计）与 `apply_table_merges()`（导出时用 python-docx `merge()` 还原，并用原文覆盖以抵消 `merge()` 的文字拼接）。接法与页面设置同路（extras → `apply_docx_extras`/`get_docx_extras` → `_write_docx` → `export_to_docx(table_merges=)`）。**实测 DOCX 往返零丢失**：`merged_cells` 1→1，连带 `table_cells` 8→8、`paragraphs` 14→14、`text_chars` 102→102 全部回到基线。**至此 DOCX 与 XLSX 往返均为零丢失**。两个易错点已写成测试：① `merge()` 会拼接文字（会变成"合计合计"）；② `row.cells` 对合并格按网格列重复返回同一单元格（用它判断"文字重复"会假阳性，我第一版就误判了）。**已知未修的小瑕疵**（已记入 fidelity.md）：`_docx_table_to_md()` 仍把合并格文字在每一列重复输出，用户在蜜写里看到的 Markdown 带重复文字（导出结果正确） | 新增 15 条测试 |
| 2026-10-11 | A | **第五刀：DOCX 段落边界**。`import_from_docx()` 原先每段输出**一行**、行间不留空行；而 Markdown 语义是**连续非空行属于同一段**，于是"正文段/图片段/链接段"被渲染成一段、重导出后粘在一起 —— **实测顶层段落 6 → 4**。修法：段落之间补空行，**列表项之间除外**（空行会把一个列表拆成多个）。修完顶层 6 → 6 且逐段文字一致。**实测 DOCX 只剩 1 项丢失**（`merged_cells`；`paragraphs`/`table_cells`/`text_chars` 的 +1/+1/+2 都是合并格被拆开的连带结果，已解释清楚） | 新增 6 条测试 |
| 2026-10-11 | A | **第四刀：DOCX 页面设置 + 页眉页脚往返**。思路是**绕开 Markdown**：新增 `read_docx_extras()`（读纸张精确尺寸/方向/四条页边距/页眉页脚文字）与 `apply_header_footer()`（写回）。接法：`app._open_docx_file` → `widget.apply_docx_extras()`（页面设置进 `_page_settings`、页眉页脚另存）→ `_write_docx` 传给 `export_to_docx(header_text=, footer_text=)`。顺带补一处静默改变：`apply_page_settings()` 原先只认 5 种命名纸张，非标准尺寸会被当成 A4；现支持 `page_width_mm`/`page_height_mm` 精确尺寸。**实测 DOCX 丢失 6 项 → 2 项**（`header_parts`/`footer_parts` 1→1，`page_margins` 1417,1701,1417,1701→**完全相同**）。剩 2 项：合并单元格（Markdown 表格语法表达不了）、段落少 1 段（空段落） | 新增 15 条测试（含产品级 `_write_docx` 端到端与 AST 接线检查） |
| 2026-10-11 | A | **第三刀：DOCX 超链接往返修复**。`import_from_docx()` 把普通段落交给 `_para_to_md()`，而它遍历 `para.runs` —— python-docx 的 `Paragraph.runs` **只返回 `w:p` 的直接子 `w:r`**，超链接文字位于 `w:hyperlink/w:r`，于是**整段超链接被静默丢掉**（链接与链接文字一起消失）。这同时解释了基线里"文字少 12 字"。修法：新增 `_iter_para_children()` 按**文档顺序**遍历，`w:hyperlink` 取目标（`r:id`→URL / `w:anchor`→`#书签`）写成 `[文字](url)`，导出侧既有的 `_add_hyperlink()` 再还原为真正的 `w:hyperlink`。**实测 DOCX 丢失 6 项 → 4 项**（`hyperlinks` 1→1、文字 102→104 不再减少）。**同时更正一处我自己的误判**：最初猜"`para.text` 不含链接文字"，实测否定（`para.text` 82 字符 = 底层 `w:t` 82 字符），真凶是 `para.runs`。另**否决**了上一轮列出的"表格下方备注被吸成空行"候选 —— 核查后认定那是 pandas/Excel 的正常已用区域行为，强行"修"会丢掉用户真实写的备注（属静默数据丢失），理由已记入 docs/fidelity.md §8.1 | 新增 10 条测试 |
| 2026-10-11 | A | **第二刀：蜜算 xlsx 往返零丢失**。`write_workbook()` 从"新建工作簿写值"改为**"打开源工作簿 → 只更新单元格值 → 另存"**（`preserve_structure` 可关；无源文件时仍走新建，覆盖 CSV 导入/新建表格）。合并区域、条件格式、数据验证、冻结窗格、图表、自定义数字格式都是 openpyxl 不碰的东西，因此**天然保留**。**实测 xlsx 往返从丢 5/9 项降到 0/9 项**（11 项特征零差异，7455→7462 B）。过程中踩到并修掉两个 openpyxl 陷阱：① `ws.cell(row,col,value=None)` **是空操作**（只在 value 非 None 时赋值），导致"用户删掉的行仍留在导出文件里"——改为 `.value = None` 赋值；② 合并区域内非锚点格子是只读的 `MergedCell`，赋值抛 `AttributeError`，且**曾被陷阱①掩盖**——新增 `_readonly_merged_coords()` 跳过。另发现 pandas 按**已用区域**判定表格范围（只写 3 行数据、第 20 行有备注的表读出来是 19 行），已特性化钉住 | 新增 13 条测试（含 2 条直接钉住 openpyxl 陷阱） |
| 2026-10-11 | A | **第一刀：蜜算多工作表 + 公式**（保真度根因 1）。新增 `plugins/beesheet_workbook.py`：以显式"工作簿"对象承载**全部工作表**与**每格公式**（openpyxl 扫公式 + pandas 读各表值；写出时公式格写公式字符串而非 pandas 计算值）。接入 `beesheet.py::_import_file_from_path`（读全部表，首表进模型，其余留待写回）与 `beesheet_data_mixin._export_xlsx`（有工作簿则全量写回，否则回退 `df.to_excel`），并保留 `pd.read_excel` 回退。**实测 xlsx 往返丢失从 8/9 项降到 5/9 项**：`sheets` 2→2、`formulas` 4→4、非空单元格 21→21 不再丢失。仍丢：合并区域、条件格式、数据验证、冻结窗格、图表、自定义数字格式（下一步改为"打开源工作簿只更新值"即可天然保留）。另显式钉住两个既有约束：首行一律当表头、无缓存时公式格的值读为 NaN | 新增 24 条测试（模块 18 + 接线 6）；导入检查 79 → **80/80 成功** |
| 2026-10-11 | A | **建立保真度基线（阶段 A）**：新增 `tools/ooxml_probe.py`（OOXML 特征探针）、`tools/fidelity_roundtrip.py`（用**产品代码**跑 DOCX/XLSX 往返并前后对比）、`tests/fidelity/test_ooxml_probe.py`（25 条：仪器自检 + 特性化基线）、`docs/fidelity.md`（实测报告）。**实测结论**：DOCX 往返丢 6 项（合并单元格、超链接、页眉/页脚部件、页边距变默认、文字少 12 字）；XLSX **9 项特征丢 8 项**（公式/合并/条件格式/数据验证/冻结窗格/图表全丢，多工作表只剩第一张）；PPTX **无导入路径**故无往返可测。根因三条：蜜算"数据即模型"导致格式无处存身、蜜写以 Markdown 为中间层、蜜演只出不进。已验证 `import_from_docx` 里**零处**提及 hyperlink/Relationships，即导入侧确实丢弃超链接 | 新增 25 条测试；仪器含"非恒真"自检 |
| 2026-10-11 | 2.6 | 插入的图片/公式图片不再只留 `%TEMP%`（系统清理后文档图片永久失效、换机打不开）：复制到文档旁 `<文档名>_media/`，未保存文档落到应用数据目录，失败优雅降级 | 新增 10 条回归 |
| 2026-10-11 | 附带 | 蜜演 PNG 导出的"导出中"提示定时器建在循环**之后**，导致停表语句是空操作、导出结束 3 秒后仍弹模态框（实测令 pytest 超时卡死）；改为循环前建立 | `tests/regression/v5` + 导出相关：195 passed，无挂起 |
| 2026-10-11 | 附带 | 蜜演 PNG 导出的「导出中」提示由 `QTimer.singleShot` 改为绑定 self 的单次 QTimer，并在导出完成时 `stop()`（原先导出结束后仍会弹，实测以失效父对象调用 `QMessageBox` 被 Qt 记为 event loop 异常） | `tests/regression/v5` + `test_export_pdf.py`：72 passed / 0 error |

## 6. 已知问题（已定位，未修）

### 6.1 解释器退出期原生崩溃（`Windows fatal exception code 0x80000003`）

- **现象**：含 `QWebEngineView` 的测试文件在**进程退出**阶段崩溃，退出码非 0
  （`-2147483645`）。测试本身全部通过，与断言无关。
- **精确定位的崩溃栈**（faulthandler 实测，`tests/qt/test_app.py::test_new_beeshow`）：

  ```
  beeshow_slide_mixin.py:418  _show_slide            ← self._preview.setHtml(full_html)
  beeshow_slide_mixin.py:156  _update_preview
  beeshow.py:231             _apply_initial_content
  beeshow.py:98              __init__
  app.py:754                 _new_beeshow
  tests/qt/test_app.py:109   test_new_beeshow
  ```

  即 `QWebEngineView.setHtml()` 触发的 Chromium 断点
  （`0x80000003` = `STATUS_BREAKPOINT`）。

- **⚠️ 2026-10-11 更正：真正原因是沙箱禁止命名管道，与 offscreen 无关**
  本节原先写"offscreen 下退出期崩溃、由渲染/GPU 子线程在进程收尾时抛出"，
  **不正确**。用最小复现（`QWebEngineView()` + `setHtml()`，共 6 个变体）查清：

  | 变体 | 退出码 | 备注 |
  |---|---|---|
  | 只创建视图、**不** setHtml | **0** | 无任何 FATAL |
  | setHtml | -2147483645 | 必崩 |
  | setHtml + `AA_ShareOpenGLContexts` | -2147483645 | 无效 |
  | setHtml + Chromium `--no-sandbox --disable-gpu` | -2147483645 | 无效 |
  | setHtml + `deleteLater()` + `processEvents()` | -2147483645 | 无效 |
  | setHtml + 跑事件循环 / 加父窗口 / 指定 `QT_QPA_FONTDIR` | -2147483645 | 均无效 |

  崩溃点打出的真正错误是：

  ```
  [nnnn:nnnn:...:FATAL:platform_channel.cc(85)] Check failed: . : 拒绝访问。 (0x5)
  ```

  即 **Chromium 的 mojo 平台通道无法创建命名管道（`ERROR_ACCESS_DENIED`）**。
  这正是本会话沙箱的限制（沙箱禁止命名管道），**不是** BeeOffice 的缺陷，
  也不是 `offscreen` 平台本身的缺陷；**崩溃发生在 `setHtml` 调用之中**，
  而不是"退出阶段"。

- **相关性**：报告退出期异常的 9 个文件**全部**是构造 `QWebEngineView` 的蜜演相关
  测试（`test_app.py`、`test_beeshow_play.py`、`p0_02`、`p0_04`、`p0_08`、
  `p1_12`、`p1_13`、`p1_18`、`test_smoke_beeshow.py`）；其余 60 个文件无异常。
  **没有任何断言失败。**
- **已验证无效的缓解手段**：`QTWEBENGINE_CHROMIUM_FLAGS='--disable-gpu
  --disable-software-rasterizer --no-sandbox'`、`AA_ShareOpenGLContexts`、
  `deleteLater` + 事件循环、父窗口、`QT_QPA_FONTDIR` —— 全部仍然崩溃。
- **性质**：**本会话沙箱特有**（禁止命名管道），不是产品缺陷，也不是平台缺陷。
  在普通机器 / CI runner 上命名管道可用，**这些文件预计不会崩溃**——因此
  本会话观察到的"passed 计数波动（1006~1083）"很可能只是本地沙箱假象；
  这一点只能在 GitHub CI 上证实。
- **当前对策**：`tools/run_tests_isolated.py` 按文件隔离运行，把崩溃降级为
  "某个文件退出码异常"，避免它掩盖真实断言失败。**注意：CI 的动机与此不同**——
  CI 用按文件隔离是为了绕开已实测的 `qapp` 级挂死（见 §6.1.1）与顺序污染，
  **不是**为了绕开这个沙箱崩溃。
- **待办**：不再把它当作"待消除的产品缺陷"；已从 tests/conftest.py 移除基于
  错误假设加入的 `AA_ShareOpenGLContexts`。若在无沙箱环境仍复现，再按
  "Chromium 命名管道被拦截"方向排查（例如安全软件/组策略限制）。

### 6.1.1 已修复：两个曾被误判为「环境问题」的真实缺陷

排查 6.1 的过程中发现，`tests/qt/test_app.py` 长达约 190 秒且拿不到 summary，
**并不**只是 WebEngine 的退出问题，而是两个真实缺陷叠加：

1. **原子写用 `mkstemp` 导致 UI 线程挂死**（本次引入后立即修复）
   `utils.atomic_write_text` 原用 `tempfile.mkstemp(dir=目标目录)`。当目标目录
   不可写（受限账户 / 被安全软件或沙箱拦截）时，`os.open()` 这条路径**会无限期
   阻塞**；而普通 `open()` 会在约 0 ms 抛出 `PermissionError`。实测数据：

   | 调用 | 结果 |
   |---|---|
   | `open(home/'x.tmp', 'w')` | `PermissionError`，1 ms |
   | `open(home/'x.tmp', 'x')` | `PermissionError`，0 ms |
   | `tempfile.mkstemp(dir=home)` | **挂起**（15 s 未返回） |

   由于保存设置发生在 UI 线程，后果是界面卡死而非报错。
   现改为 `open(tmp, 'x')` 独占创建同目录临时文件，`fsync` 后再 `os.replace`，
   既保持原子性又能快速失败：`atomic_write_json(不可写目录)` 现在 **2 ms 返回 False**
   并记录明确日志。

2. **`tests/qt/test_app.py` 自定义 `app` fixture 遮蔽了 conftest 的同名 fixture**
   该文件过去自己定义了
   ```python
   @pytest.fixture(scope="function")
   def app(qtbot):
       window = BeeApp()
       qtbot.addWidget(window)
       return window
   ```
   导致：① 不做设置隔离（直接读写真实 `~/.beeoffice_settings.json`）；
   ② 不屏蔽启动期模态框 —— `_restore_session` 的 100 ms 定时器真的弹出
   「是否恢复上次会话」对话框，把整个文件挂死；③ 不跳过插件发现 ——
   25 个用例各自跑一遍 `discover_plugins()`，耗时约 190 秒。
   删除该本地 fixture 后：**25 passed / 7.8 秒**（原为挂起 / ~190 秒）。

   同时把 `BeeApp` 的 4 个启动期 `QTimer.singleShot(...)` 改为**绑定到窗口**的
   单次 QTimer，并在 `closeEvent` 中显式 `stop()` —— 这与 v5.0.5 为状态栏
   `_status_timer` 所做的修复是同一类问题（`singleShot` 不绑定接收者生命周期，
   窗口关闭后回调仍会执行）。



### 6.2 尚未处理

- 优化规划 §2 及之后的所有内容（启动性能、线程安全、公式正确性批次、架构收敛等）。
- 发布前项（§4）：真实 CI、代码签名、依赖锁定、`LICENSE`、README 功能表诚实化。
- 「补」的落点：蜜写 HTML 导出（`bee_export.export_to_html` 已实现且有测试，
  只差约 10 行封装 + 菜单接线）；以及按用户反馈逐个补齐已删除的假功能。

