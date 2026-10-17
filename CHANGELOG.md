# 更新日志

本文件记录蜜蜂办公 BeeOffice 的所有重要变更。

格式参考 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.0.0/)，
版本号遵循 [语义化版本](https://semver.org/lang/zh-CN/)。

---

## [Unreleased] - 2026-10-17

### 修复

- **蜜算（阻断级）**：`beesheet_engine.py` 第 1310 行一个孤立反斜杠，
  使整个模块**无法编译**；而 `plugin_manager.discover_plugins` 的
  `except` 把它吞掉，表现为"蜜算功能凭空消失"。已删除该字符。
- **蜜算（公式语义）**：支持 Excel 写法 `=` / `<>` / `^`。
  此前 `=IF(A1=1,…)`、`=IF(A1<>1,…)` 恒返回 `#ERROR`——
  这是电子表格最高频的公式之一。
- **蜜算（复合表达式）**：`=SUM(A1:A3)*2`、`=ROUND(A1,2)+1` 不再退化为文本。
- **蜜算（跨表）**：`=SUM(Sheet2!A1:A3)` 此前恒为 0，现正确求和。
- **蜜算（单格）**：`=SUM(A1)` 此前恒为 0（只认区域），现正确。
- **安全（公式引擎）**：删除跨表分支的裸 `eval`，改走 AST 白名单。
  `=S2!A1+(1).real` 这类属性链不再被求值（原实现可逃逸沙箱）。
- **安全（移动端）**：`/api/*` 增加一次性令牌校验（`?t=`），
  移除 `Access-Control-Allow-Origin: *`。此前任意网页可读取用户
  已打开的全部文档。
- **蜜写（导出）**：Markdown → DOCX 补齐 `<img>` 分支，图片不再丢失；
  纯图片段落居中并留 12pt 间距；图片缺失时保留 `[图片缺失: src]` 占位。
- **设置**：`save()` 改为原子写入（先写 `.tmp` 再替换）。
  原实现直接覆盖写，序列化异常会把配置截断成空文件。
- **打包**：`beeoffice.spec` 不再排除代码正在使用的 matplotlib Qt 后端；
  图表改用 `backend_qtagg`（PySide6/Qt6 正确选择，保留 qt5agg 回退）。
- **版本**：`main.py` 启动横幅改为读取 `__version__`，不再硬编码 "v5.0"。
- **安全（演示同步）**：`SyncServer` 增加一次性令牌（`?t=`），
  HTTP 三个端点与 WebSocket 握手均校验；移除 3 处
  `Access-Control-Allow-Origin: *`。此前同网段任何人或任意网页
  都能拉走整份讲稿。
- **蜜演（竞态）**：`SyncServer._running` 原在 WS 线程启动之后才置位，
  accept 循环可能启动即退出，表现为"服务启动成功但 WS 从不监听"。
- **蜜算（线程）**：`ChunkLoader` 原在 worker 线程直接调用
  `model.load_chunk()` 并 emit `layoutChanged`，属于跨线程修改
  `QAbstractTableModel`。现改为线程只派发请求，由 GUI 线程执行。
- **蜜算（线程）**：导入路径同样存在跨线程操作。`_import_file_from_path`
  把"读文件"和"改模型 + 弹 QMessageBox"揉在一起，`app.py` 又把它丢进
  `AsyncTaskManager`，等于在 worker 线程里 `setModel` 和开模态框。
  现拆为 `_read_sheet_file`（纯 IO，可后台）与
  `_apply_imported_dataframe`（必须 GUI 线程）。
- **蜜算（状态污染）**：导入新文件时未清空 `_formula_cells`，
  旧坐标上的公式会在重算时覆盖新数据。现随导入一并清空。

### 测试

- 新增 `tests/unit/test_formula_excel_semantics.py`（23 项）：
  Excel 运算符、复合表达式、跨表引用、属性链安全回归。
- 新增 `tests/unit/test_docx_image_export.py`（4 项）：
  导出后**重新打开** DOCX 并数图片（产物级验收）。
- `tests/conftest.py`：
  - 未安装 PySide6 时不再阻断全部测试（纯逻辑测试可在 CI 跑）；
  - 补齐 v5.1 新增设置字段，修复 `temp_settings` 导致的 4 个假失败。
- 新增 `tools/check_syntax.py`（211 个文件语法编译检查）。
- 新增 `tools/smoke_formula.py`（9 条 Excel 写法冒烟）。
- 新增 `.github/workflows/test.yml`：fast 任务阻塞、full 任务先观察。
- 新增 `tests/unit/test_mobile_api.py` 的 403 安全回归（无令牌/错令牌）。
- `tests/conftest.py` 的 `temp_settings` 改为 patch `Path.home`，
  **删除复制的默认值清单**——该清单在 settings.py 新增字段后会失效，
  导致 `save()` 抛 `AttributeError` 被宽泛 `except` 吞掉、配置写成空文件。
- 全量测试基线：**739 passed / 0 failed**（Python 3.11.9 + PySide6 6.12，
  157 秒）。此前项目从未有过可复现的全绿基线。

### 变更

- `AppSettings.save()` 现在返回 `bool`（原返回 `None`，调用方均忽略，兼容）。

---

## [5.0.6] - 2026-09-17
# 小脚本 update_changelog_506.py
from pathlib import Path
p = Path("CHANGELOG.md")
text = p.read_text(encoding="utf-8")
text = text.replace(
    "测试数：483 → 513（+30）",
    "测试数：483 → 581（+98）",
)
text = text.replace(
    "覆盖率：34.54% → 35.06%",
    "覆盖率：34.54% → 37.30%",
)
p.write_text(text, encoding="utf-8")

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