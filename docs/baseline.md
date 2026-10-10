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
