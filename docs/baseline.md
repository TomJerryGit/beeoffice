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

| 指标 | 基线 | 目标（阶段 2.1） |
|---|---|---|
| `import beeoffice.app` | 658 ms | 不劣化 |
| `PluginManager.discover_plugins()` | **2487 ms**（首次冷启动曾测得 9110 ms） | **< 500 ms** |
| `PluginManager.load_plugins()` | 0 ms | 不劣化 |
| 启动到插件可用合计 | **3177 ms**（冷启动约 8–11 s） | **< 1500 ms** |
| 已注册插件数 | 4（BeeWrite / BeeSheet / BeeShow / PDF 批注） | 4 |

**根因**（优化规划 §2.1）：`plugin_manager.py:36-45` 用 `pkgutil.iter_modules`
把 `beeoffice/plugins/` 下全部 86 个模块逐个 `import`，连带拉起 matplotlib、
PyMuPDF(fitz)、python-docx、pandas 与 QtWebEngine；且这段代码由
`app.py:153` 的 `QTimer.singleShot(50, ...)` 在窗口显示后于**主线程**执行。

## 2. 测试

命令：`python -m pytest tests/unit tests/smoke -q -p no:cacheprovider -o log_file= --basetemp=<可写目录>`

| 指标 | 基线（阶段 0 开始时） | 阶段 0/1.2 之后 |
|---|---|---|
| `tests/unit` + `tests/smoke` | 464 passed, **4 failed** | **473 passed, 0 failed** |
| 失败用例 | `test_settings.py`：`test_save_and_load`、`test_window_size_serialization`、`test_password_encoded`、`test_password_decoded_on_load` | 已全部修复 |
| `pytest --collect-only`（全量） | 710 | 715（新增 5 条原子写回归） |
| `tests/qt` 单独运行 | 97 passed / 17.25 s | 待复测 |
| 全量 `tests/` 一次性运行 | **原生崩溃**（顺序污染，单独跑子集均通过） | **待修**（阶段 4.2） |

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

## 6. 已知问题（已定位，未修）

### 6.1 解释器退出期原生崩溃（`Windows fatal exception code 0x80000003`）

- **现象**：全量 pytest 一次性运行时，进程在退出阶段崩溃；单独运行同一文件往往能打印结果但退出码非 0；与其它文件一起跑时崩溃点会漂移，整轮拿不到 summary。
- **已定位的崩溃栈**（faulthandler 实测）：

  ```
  beeshow_slide_mixin.py:418  _show_slide
  beeshow_slide_mixin.py:156  _update_preview
  beeshow.py:233             _apply_initial_content
  beeshow.py:98              __init__
  tests/test_smoke_beeshow.py:80  test_beeshow_view_instantiable
  ```

  即 `QWebEngineView.setHtml()` 在 offscreen 平台下触发的 Chromium 断点。
- **相关性（阶段 1 验收实测）**：按文件隔离运行 68 个测试文件，报告退出期异常的
  **9 个文件全部是构造 `QWebEngineView` 的蜜演相关测试**：

  ```
  tests/qt/test_app.py
  tests/qt/test_beeshow_play.py                     3 passed 后退出异常
  tests/regression/p0/test_p0_02_play_window.py      4 passed 后退出异常
  tests/regression/p0/test_p0_04_beeshow_webengine.py
  tests/regression/p0/test_p0_08_beeshow_plugin.py   4 passed 后退出异常
  tests/regression/p1/test_p1_12_presenter_no_notes.py
  tests/regression/p1/test_p1_13_reorder.py          1 passed 后退出异常
  tests/regression/p1/test_p1_18_command_context.py
  tests/test_smoke_beeshow.py
  ```

  其余 59 个文件无异常。**没有任何断言失败**（683 passed / 0 failed），
  说明这是 QtWebEngine 在 offscreen 下的退出问题，而非产品逻辑缺陷。
- **性质**：发生在**进程退出**阶段，不是断言失败。
- **当前对策**：`tools/run_tests_isolated.py` 按文件隔离运行，把崩溃降级为"某个文件退出码异常"而不是掩盖真实断言失败。
- **待办**（优化规划 §4.2）：定位并消除（可试的方向：会话级 WebEngine profile
  显式释放、测试结束前 `deleteLater()` + `processEvents()`、或改用
  `QWebEngineProfile.defaultProfile().deleteLater()`），或在 CI 中正式采用
  按文件隔离运行。


### 6.2 尚未处理

- `beeshow_ai_service.py:187-195`：AI 调用失败后静默降级为本地模板，UI 不区分来源（计划 §1.8 的最后一小项，优先级低）。
- 优化规划 §2 及之后的所有内容（启动性能、线程安全、公式正确性批次、架构收敛等）。

