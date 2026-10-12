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
| 按文件隔离运行（`tools/run_tests_isolated.py`） | — | **87 文件 / 914 passed / 0 failed / 0 error**（阶段 2 第 3 轮实测）；`failed`/`error` 在多轮运行中始终为 0，passed 计数会随退出期崩溃是否抢在 summary 之前小幅波动 |

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

| 指标 | 值 |
|---|---|
| `beeoffice/` 模块数 | 118 |
| `beeoffice/` 总行数 | 36 948 |
| 最大模块 | `beesheet_engine.py` 1444 行 |
| 最大类 | `FormulaEngine`（119 方法） |
| 裸 `except:` | 15 处 |
| `except Exception` | 446 处 |
| docstring 为版本日志的模块 | 45 / 118 |
| 死代码模块 | `formula_engine.py`(569)、`beeoffice/webdav.py`、`plugins/git_manager.py` |
| 纳入版本控制的文件数 | 213（首个 commit） |

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

  即 `QWebEngineView.setHtml()` 在 `QT_QPA_PLATFORM=offscreen` 下触发的
  Chromium 断点（`0x80000003` = `STATUS_BREAKPOINT`）。崩溃发生在退出阶段，
  由 QtWebEngine 的渲染/GPU 子线程在进程收尾时抛出。
- **相关性**：报告退出期异常的 9 个文件**全部**是构造 `QWebEngineView` 的蜜演相关
  测试（`test_app.py`、`test_beeshow_play.py`、`p0_02`、`p0_04`、`p0_08`、
  `p1_12`、`p1_13`、`p1_18`、`test_smoke_beeshow.py`）；其余 60 个文件无异常。
  **没有任何断言失败。**
- **已验证无效的缓解手段**：
  `QTWEBENGINE_CHROMIUM_FLAGS='--disable-gpu --disable-software-rasterizer --no-sandbox'`
  仍然崩溃（实测退出码 -2147483645）。
- **性质**：环境相关（offscreen + QtWebEngine），不是产品逻辑缺陷；在生产 GUI 会话
  （真实窗口系统 + GPU）下未复现。
- **当前对策**：`tools/run_tests_isolated.py` 按文件隔离运行，把崩溃降级为
  "某个文件退出码异常"，避免它掩盖真实断言失败。CI 中亦应据此按文件运行，
  或以 `pytest -p no:cacheprovider --forked`（需 `pytest-forked`）替代。
- **待办**（优化规划 §4.2）：真正的消除方向——在会话级 fixture 里显式
  `QWebEngineProfile.defaultProfile().deleteLater()` + `processEvents()`，
  或在测试收尾前把所有 `QWebEngineView` 移到主线程销毁。

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

