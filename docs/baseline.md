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

