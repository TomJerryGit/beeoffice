# BeeOffice（蜜蜂办公）5.0.17 GUI 实跑盘点

> 盘点方式：**离屏（QT_QPA_PLATFORM=offscreen）真实启动 BeeApp，并驱动新建/打开/切换对话框/截图**，
> 不是读代码推断。所有数字均为本机实测；截图由 `QWidget.grab().save(png)` 生成。
> 机器可读数据：`app_raw.json`（139 KB），原始分项：`main.json` / `word.json` / `sheet.json` / `show.json`。
> 执行者：app-runner（Agent Teams task-5）；时间：2026-10-21；工作目录 `D:\beeofficeV`。

## 0. 一句话结论

BeeOffice 5.0.17 的可运行性**好于预期**：主窗口冷启动 275 ms、4 个内置插件 21 ms 全部加载、三种编辑器
（蜜写/蜜算/蜜演）都能真实创建，语料 DOCX/XLSX/PPTX 全部打开成功（DOCX 5 万字 2.57 s、PPTX 30 页 657 ms）。
主要问题集中在**大表格的两阶段载入**（20 万行首开 13.7–45 s、内存 584–1247 MB、完整数据 25 s 未就绪且
安全门提示误导）与 **蜜演「新增幻灯片」无效**（页数不变、标题粘连）。另有若干 UI/文案细节问题（见 §7）。

---

## 1. 实测环境与运行方式

### 1.1 环境

| 项 | 值 |
|---|---|
| 产品/版本 | BeeOffice 蜜蜂办公 5.0.17（源码树 `D:\beeofficeV`） |
| 操作系统 | Windows（本机 DSH 受限沙箱：**禁止命名管道**） |
| Python | 3.11.9（`D:\Program Files\Python311\python.exe`） |
| PySide6 | 6.6.0 |
| QPA | `offscreen` + `QT_QPA_FONTDIR=C:\Windows\Fonts`（否则中文全部渲染成豆腐块，实测 202 个字体可用） |
| 语料 | `tests/fidelity/corpus/`（DOCX/XLSX/PPTX，外部内容仅当数据） |
| 隔离 | `HOME/USERPROFILE`→`_tmp/home`、`BEEOFFICE_DRAFT_DIR`→`_tmp/drafts`，**不碰真实用户目录** |

### 1.2 实际运行命令（可复现）

```powershell
cd D:\beeofficeV
$env:PYTHONPATH='D:\beeofficeV'; $env:PYTHONIOENCODING='utf-8'
$env:QT_QPA_PLATFORM='offscreen'; $env:QT_QPA_FONTDIR='C:\Windows\Fonts'

python _ptmp\analysis\compare\_runner_main.py     # 启动/菜单/对话框/插件/QAction
python _ptmp\analysis\compare\_runner_word.py     # 蜜写：富文本/大纲/语料 DOCX/查找/拼写/AI 降级
python _ptmp\analysis\compare\_runner_sheet.py    # 蜜算：两阶段载入/语料 XLSX/功能对话框
python _ptmp\analysis\compare\_runner_show2.py    # 蜜演：主题/加页/PPTX 导入/备注（WebEngine 安全版）
python _ptmp\analysis\compare\_merge_inventory.py # 合并 → app_raw.json
```

`_runner_common.py` 是公共安全网，启动前做以下 monkeypatch（均为**测试脚本内**，未改产品源码）：

1. `BeeApp._restore_session` / `_check_first_run` / `_check_recoverable_drafts` / `_check_auto_sync` / `_autosave` → 空函数；
2. `QMessageBox.question/information/warning/critical/about` → **录制器**：真实 `show()` + `grab()` 截图 + `close()`，
   `question` 统一返回 **Yes**（不会卡死，且每条产品弹框都有截图与原文留档）；
3. `QDialog.exec` / `QMenu.exec` → `show()+截图+close()` 并返回 Accepted/None（非阻塞）；
4. `QFileDialog.getSaveFileName/getOpenFileName/...` → 返回空路径（模拟用户取消）；
5. 结束时 `os._exit()`，绕过 `closeEvent` 的未保存标签检查（避免模态框卡死）。

---

## 2. 启动实测

| 指标 | 实测值 | 说明 |
|---|---|---|
| `BeeApp()` 构造 | **275 ms**（另两次 374 / 124 ms 级） | 含设置载入、菜单、主题、状态栏 |
| 插件发现+加载（50 ms 定时器后） | **21 ms** | 扫描 99 个模块、候选 4 个、跳过 95 个实现模块 |
| 启动后窗口 | 1600×1000（`resize` 后） | 标题「开始 - 🐝 蜜蜂办公」 |
| 启动标签 | `['开始']` | 欢迎页纯文本说明（Ctrl+Shift+P、新建/拖入文档） |
| 主题/强调色 | `light` / `amber` | 状态栏「就绪」 |
| 设置文件 | `_tmp/home/.beeoffice_settings.json` | 隔离成功（未写真实 `~`） |

截图：`screens/01_main_empty.png`（21 KB，空状态主窗口 + 菜单栏 + 状态栏）、`screens/02_menubar.png`。

---

## 3. 截图证据（59 张，共 3.7 MB）

目录：`_ptmp/analysis/compare/screens/`。任务建议单张 30–200 KB，实际分布：
**22 张在 30–200 KB**、33 张 <30 KB（均为小菜单/纯色小对话框，离屏纯色 PNG 压缩率天然高）、
4 张 >200 KB（含全文/图片渲染的 Word/PPTX 截图，必须保留细节）。全部为真实控件 `grab()`，无手工拼图。

### 3.1 主窗口 / 菜单 / 对话框

| 文件 | 大小 | 内容 |
|---|---|---|
| screens/01_main_empty.png | 21 KB | 启动后主窗口空状态（开始页欢迎标签） |
| screens/02_menubar.png | 3 KB | 菜单栏（文件/编辑/工具/视图/帮助） |
| screens/03_menu_1_文件.png | 6 KB | 文件菜单展开（新建/打开/保存/导出/最近打开/退出） |
| screens/03_menu_1_文件__sub_新建.png | 6 KB | 文件 > 新建 子菜单（含 Ctrl+N、Ctrl+T） |
| screens/03_menu_1_文件__sub_导出.png | 3 KB | 文件 > 导出 子菜单（DOCX/PDF/HTML/PPTX/生成报告） |
| screens/03_menu_1_文件__sub_最近打开.png | 3 KB | 文件 > 最近打开（「无最近文件」置灰） |
| screens/03_menu_2_编辑.png | 5 KB | 编辑菜单（撤销/重做/命令面板/查找替换） |
| screens/03_menu_3_工具.png | 10 KB | 工具菜单（AI 辅助/恢复草稿/数据分析/透视表/自然语言公式/关联表格/批量转换/PDF 批注） |
| screens/03_menu_3_工具__sub_AI_辅助.png | 2 KB | 工具 > AI 辅助（续写/润色/总结） |
| screens/03_menu_3_工具__sub_批量转换.png | 2 KB | 工具 > 批量转换（DOCX↔MD） |
| screens/03_menu_4_视图.png | 3 KB | 视图菜单（深色主题/强调色/分屏） |
| screens/03_menu_4_视图__sub_强调色.png | 2 KB | 强调色子菜单（琥珀/海洋/森林/日落） |
| screens/03_menu_5_帮助.png | 12 KB | 帮助菜单（关于/快捷键/日志/内存监控/云存储设置/AI 设置/同步/备份/移动端/插件市场） |
| screens/09_shortcuts_overlay.png | 30 KB | 长按 Ctrl 快捷键浮层（**Markdown 未渲染**，见问题 P2-4） |
| screens/dialog_AI_设置.png | 26 KB | 🤖 AI 设置（服务商/Key/地址/模型/测试连接，620×340） |
| screens/dialog_云存储设置.png | 21 KB | ☁️ 云存储设置（480×400） |
| screens/dialog_备份与恢复.png | 21 KB | 🗂️ 备份与恢复中心（760×460） |
| screens/dialog_插件市场.png | 28 KB | 🔌 插件市场（4 个内置插件列表 + 详情 + 启用开关，720×520） |
| screens/dialog_命令面板.png | 20 KB | Ctrl+Shift+P 命令面板（内置命令列表） |
| screens/dialog_选择模板.png | 32 KB | 📄 从模板新建（分类页 + 预览，750×500） |
| screens/dialog_智能数据分析.png | 29 KB | 蜜算「智能数据分析」本地规则摘要（640×420） |
| screens/dialog_数据透视表.png | 21 KB | 📊 数据透视表配置对话框（560×480） |
| screens/dialog_QDialog_OK_Cancel.png | 3 KB | 蜜算「筛选」对话框（列/包含/OK-Cancel） |
| screens/dialog_QDialog_柱状图_折线图.png | 4 KB | 蜜算「插入图表」类型选择（6 种图表按钮） |
| screens/08_memory_monitor.png | 11 KB | 内存监控（非模态） |
| screens/10_main_after_actions.png | 22 KB | 盘点收尾时主窗口 |
| screens/dialog_msg_about_关于蜜蜂办公.png | 11 KB | 关于（版本 5.0.17/作者/slogan） |
| screens/dialog_msg_warning_保真度提示.png | 13 KB | 保真度提示对话框（问题 P2-3 证据） |
| screens/dialog_msg_question_续写_没有可用的_AI.png | 20 KB | AI 未配置 Key 的降级询问 |
| screens/dialog_msg_information_拼写检查不可用.png | 32 KB | 拼写检查无后端说明（含 3 种启用办法） |
| screens/dialog_msg_warning_无法透视表.png | 10 KB | 大表安全门拦截提示（问题 P0-1） |
| screens/dialog_msg_warning_无法筛选.png | 10 KB | 同因（筛选入口） |

### 3.2 蜜写（Word/Markdown）

| 文件 | 大小 | 内容 |
|---|---|---|
| screens/20_word_new.png | 51 KB | 新建 Word 文档（富文本模式 + 双工具栏 + 默认占位文字） |
| screens/21_word_rich.png | 97 KB | 富文本渲染：H1/H2/H3 标题、表格、有序列表、引用块、加粗/斜体、分隔线 |
| screens/22_word_rich_formatted.png | 97 KB | 标题 1 + 加粗 + 居中操作后的效果（验证工具栏命令生效） |
| screens/23_word_outline.png | 109 KB | 左侧大纲面板展开（层级树 + 搜索框 + 展开/折叠全部） |
| screens/24_word_outline_panel.png | 15 KB | 大纲面板特写（问题 P2-1 证据） |
| screens/25_word_corpus_5w.png | 86 KB | 打开语料《测试文档_5万字.docx》（55380 字符，2571.5 ms） |
| screens/26_word_corpus_centos.png | 198 KB | 打开《Linux系统CentOS7在虚拟机VMware下的安装.docx》（3733 字符/24 图，974.3 ms） |
| screens/27_word_corpus_poem.png | 507 KB | 打开《永遇乐·京口北固亭怀古.docx》（934 字符/3 图，783.9 ms） |
| screens/28_word_find_bar.png | 12 KB | 查找替换栏（Ctrl+F，含「安装」搜索词） |
| screens/29_word_after_find_ai.png | 264 KB | 查找 + AI 降级操作后的 Word 界面 |

### 3.3 蜜算（表格）

| 文件 | 大小 | 内容 |
|---|---|---|
| screens/30_sheet_new.png | 48 KB | 新建蜜算表格（公式栏/自绘按钮工具栏/表格/状态栏） |
| screens/31_sheet_small.png | 56 KB | 打开 `表格.xlsx`（真实 6 行×13 列；模型按 DEFAULT_ROWS=1000 补空行显示） |
| screens/32_sheet_200k_items.png | 207 KB | 打开 `测试文档_20 万条.xlsx`（phase1 7151 ms；右上提示「已显示前 500 行，正在后台加载完整数据…」） |
| screens/33_sheet_200k_rows.png | 213 KB | 打开 `测试文档_20万行.xlsx`（phase1 44991 ms；同一后台加载提示） |
| screens/34_sheet_widget.png | 53 KB | 小表完整载入后的表格视图 |
| screens/35_sheet_selected_all.png | 62 KB | 全选数据后的界面（状态栏/信息面板） |
| screens/36_sheet_final.png | 61 KB | 蜜算盘点收尾主窗口 |

### 3.4 蜜演（幻灯片）

| 文件 | 大小 | 内容 |
|---|---|---|
| screens/40_show_new.png | 80 KB | 新建蜜演（欢迎页 2 页；工具栏/编辑区/缩略图真实，WebEngine 预览为哑元故空白） |
| screens/40_show_new_real_webengine_before_fatal.png | 80 KB | **真实 QWebEngineView** 版本截图（随后 Chromium FATAL，退出码 0x80000003） |
| screens/41_show_theme_dark.png | 80 KB | 切换主题「科技黑」（主题名/配色生效） |
| screens/42_show_add_slide.png | 83 KB | 新增幻灯片后界面（问题 P1-2 证据：页数不变、缩略图标题粘连） |
| screens/43_show_pptx_marketing.png | 173 KB | 导入《30_市场营销_新品上市策划方案_PPT.pptx》→ 30 页、7106 字符、657 ms |
| screens/44_show_pptx_semiconductor.png | 178 KB | 导入《33_半导体_晶圆良率分析报告_PPT.pptx》→ 28 页、5070 字符、488 ms |
| screens/dialog_msg_information_已导入_部分元素未保留.png | 15 KB | PPTX 导入损失清单（图表×3、表格×11 等） |
| screens/45_show_notes_panel.png | 179 KB | 演讲稿备注编辑区 |
| screens/46_show_ai_outline.png | 178 KB | AI 大纲（自动化下被输入框桩取消，仅记录界面） |
| screens/47_show_final.png | 176 KB | 蜜演盘点收尾主窗口 |

---

## 4. 菜单结构（实跑抓取，非推断）

菜单栏 5 个顶级菜单，菜单文本项共 **56 条**（不含分隔符）；`findChildren(QAction)` = **150 个 QAction**
（多出的是 QMenu 的 menuAction、子菜单项等）；带快捷键 **11 个**；**禁用 1 个**（「无最近文件」，符合预期）。

```
文件(20)  新建[5]：新建蜜写文档 Ctrl+N / 新建 Word 文档 / 新建蜜算表格 Ctrl+T / 新建蜜演 / 从模板新建 Ctrl+Shift+T
          打开 Ctrl+O / 保存 Ctrl+S / 另存为 Ctrl+Shift+S / 保存为模板
          导出[5]：导出 DOCX / 导出 PDF / 导出 HTML / 导出 PPTX / 生成报告
          最近打开[2]：无最近文件(禁用) / 清除最近列表
          退出
编辑(4)   撤销 Ctrl+Z / 重做 Ctrl+Y / 命令面板 Ctrl+Shift+P / 查找替换 Ctrl+F
工具(13)  AI 辅助[3]：AI 续写 / AI 润色 / AI 总结
          恢复未保存的内容… / 智能数据分析 / 刷新透视表 / 自然语言生成公式 / 关联表格到文档
          批量转换[2]：批量 DOCX 转 MD / 批量 MD 转 DOCX / PDF 批注
视图(7)   深色主题 / 强调色[4]：琥珀/海洋/森林/日落 / 分屏 Ctrl+\
帮助(12)  关于 / 快捷键 / 查看错误日志 / 内存监控
          ☁️ WebDAV 设置 / 🤖 AI 设置 / 立即同步 / 把当前文档加入同步目录
          🗂️ 备份与恢复 / 立即备份当前文件 / 📱 移动端查看 / 🔌 插件市场
```

- **插件不注册菜单**：4 个插件壳都只实现 `create_widget()` 与 `register_commands()`，**没有覆盖
  `register_menus()`**；菜单栏完全由 `beeoffice/menus.py` 集中定义，插件只向命令面板注册命令。
- 「帮助 → ☁️ WebDAV 设置」与代码注释/对话框标题（云存储设置）不一致，见问题 P2-5。

---

## 5. 插件盘点

`PluginManager.discover_plugins()` 实测统计：**扫描 99 个模块 → 候选 4 个 → 跳过 95 个实现模块**
（只 import `*_plugin.py` 壳，避免拉起 pandas/matplotlib/PyMuPDF/QtWebEngine）；4 个全部加载、全部启用。

| 插件名 | 版本 | 描述 | 模块/类 | 启用 | 注册能力 |
|---|---|---|---|---|---|
| 蜜算 BeeSheet | 1.0 | 表格处理、公式引擎、图表生成、数据分析 | `beeoffice.plugins.beesheet_plugin.BeeSheetPlugin` | ✅ | `create_widget` + `register_commands`（16 个公开方法） |
| 蜜演 BeeShow | 1.0 | 演示文稿制作、动画效果、演讲备注、排练计时 | `beeoffice.plugins.beeshow_plugin.BeeShowPlugin` | ✅ | `create_widget` + `register_commands`（17 个） |
| 蜜写 BeeWrite | 1.0 | Markdown 编辑与 Word/PDF/HTML 导出 | `beeoffice.plugins.beewrite_plugin.BeeWritePlugin` | ✅ | `create_widget` + `register_commands`（18 个） |
| PDF 批注 | 1.0 | 打开 PDF 文件进行批注、高亮、注释 | `beeoffice.plugins.pdf_annotator_plugin.PdfAnnotatorPlugin` | ✅ | `create_widget` + `register_commands`（14 个） |

插件市场对话框（`screens/dialog_插件市场.png`）展示「已安装插件：蜜算/蜜演/蜜写/PDF 批注」、
版本 1.0、作者 TomJerryGit、状态「已启用」，底部按钮：安装插件 / 卸载插件 / 刷新 / 启用此插件。
插件目录 `beeoffice/plugins/` 共 **100 个 .py 模块**，其中 96 个是编辑器实现模块，不参与插件发现。
打包版依据 `BUILTIN_PLUGIN_MODULES` 静态清单兜底（源码运行走目录扫描，与代码注释一致）。

---

## 6. 功能盘点（全部实跑）

### 6.1 蜜写（Word / Markdown）

| 操作 | 结果 | 耗时 |
|---|---|---|
| 新建 Word 文档（`_new_word_doc`，自动切 rich_text） | ✅ | 1209.3 ms |
| 写入富文本（H1/H2/H3、表格、有序列表、引用、加粗/斜体）并渲染 | ✅ 324 字符 / 9308 字节 HTML | 1046.2 ms |
| 标题 1 + 加粗 + 居中（真实 QTextCursor 操作 + 工具栏方法） | ✅ 三项均生效 | — |
| 大纲面板展开 | ✅ 4 个标题项（H1+H2 ×3）、面板 193×739、刷新 906 ms | 906.1 ms |
| 打开 5 万字 DOCX | ✅ 55380 字符 / 1094 段 / 0 图 | **2571.5 ms** |
| 打开 CentOS7 安装 DOCX（2.6 MB） | ✅ 3733 字符 / 97 段 / **24 图** | **974.3 ms** |
| 打开 永遇乐 DOCX（2.6 MB） | ✅ 934 字符 / 108 段 / 3 图 | **783.9 ms** |
| Ctrl+F 查找栏 | ✅ `find_bar` 存在且可见，可输入 | — |
| 拼写检查 | ❌ 无可用后端（本机无英文语言包/pyspellchecker/enchant），产品给出完整原因与 3 种启用办法 | 929.8 ms |
| AI 续写（未配置 Key） | ✅ 明确询问「是否改用本地规则」，不联网、不崩溃 | 1027.0 ms |
| 保真度分析（打开时自动） | ✅ 5 万字文件报告「目录域 86 处（medium）」，状态栏提示；其余语料零告警 | 29–54 ms/文件 |

### 6.2 蜜算（表格）

| 操作 | 结果 | 耗时/内存 |
|---|---|---|
| 新建蜜算表格 | ✅ | 2103.4 ms |
| 打开 `表格.xlsx`（真实 6×13） | ✅ 完整载入（界面补足 1000 显示行） | 1238.5 ms / RSS 174 MB |
| 打开 `测试文档_20 万条.xlsx`（2.39 MB / 200001×13） | ⚠️ 仅载入前 1000 行（两阶段载入），**25 s 内完整数据未就绪** | phase1 **7151 ms** / RSS 324→528 MB |
| 打开 `测试文档_20万行.xlsx`（17.73 MB / 200001×13） | ⚠️ 仅载入前 1000 行；首开很慢（两次实测 13.7 s / **45.0 s**） | RSS **584–1247 MB** |
| 载入中执行整表操作（透视/筛选/图表） | ❌ 被安全门拦截：「无法透视表 — 没有可用的完整数据加载器…请重新打开该文件后再试」 | 见问题 P0-1 |
| 智能数据分析 | ✅ 真实对话框（本地规则摘要 + 值得注意项） | 3451 ms（含对话框渲染/截图） |
| 数据透视表 | ✅ 真实 PivotTableDialog（行/列/值/聚合配置） | 1105 ms |
| 筛选 | ✅ 对话框（列/包含/OK-Cancel） | 831 ms |
| 插入图表 | ✅ 图表类型选择（柱状/折线/饼/散点/面积/雷达 6 种，matplotlib 可用） | — |
| 自然语言生成公式 | ✅ 入口存在并返回（自动化下对话框被非阻塞桩关闭） | 430 ms |
| 保存（无路径 → 另存为取消） | ⚠️ 状态栏显示「保存失败」（应为「已取消」，见 P2-2） | — |

界面实测元素：`QTableView` 1556×715 视口、13 列、公式栏为 `QLineEdit`、状态栏 `QLabel`；
蜜算工具栏是**自绘按钮排**（`_build_all_toolbars`，非 QToolBar，故 `findChildren(QToolBar)` 为空）。
列名（20 万条/20 万行）：订单编号、订单日期、客户编号、客户名称、商品类别、商品名称、单价、数量、金额、
支付方式、订单状态、收货省份、收货城市。

### 6.3 蜜演（幻灯片）

| 操作 | 结果 | 耗时 |
|---|---|---|
| 新建蜜演 | ✅ 欢迎页 2 页（标题「欢迎使用蜜演 🎥」「功能一览」）+ 30 页 PPT 导入均可解析 | 1513.8 ms |
| 主题切换（7 种：简约白/琥珀金/科技黑/森林绿/海洋蓝/日落橙/薰衣紫） | ✅ 主题状态 `简约白→科技黑` | — |
| 动画选项 | 5 种：无/淡入/滑入/缩放/平滑（信息栏实测） | — |
| 缩略图列表 | ✅ 每页生成「序号. 标题」条目 | — |
| **新增幻灯片** | ❌ **页数不变（2→2）**，新页与第 1 页粘连（见 P1-2） | — |
| 导入 PPTX《30_市场营销_新品上市策划方案》142 KB | ✅ **30 页 / 7106 字符 / 30 条备注**；损失清单弹框「图表×3、表格×11 不保留」 | **657.0 ms** |
| 导入 PPTX《33_半导体_晶圆良率分析报告》161 KB | ✅ 28 页 / 5070 字符 / 28 条备注；「图表×8、表格×7」 | **487.8 ms** |
| 演讲稿备注面板 | ✅ 存在并可见 | — |
| F5 全屏播放 / 导出 PDF / 导出图片 | ⛔ **本机无法实测**：依赖 QWebEngineView(Chromium)，沙箱禁止命名管道 → 实例化即 FATAL（见 §8） | — |
| 保存（无路径 → 另存为取消） | ⚠️ 同样显示「保存失败」 | — |

### 6.4 对话框清单（全部由真实入口打开，`QDialog.exec` 安全网截图）

| 对话框 | 实际标题/大小 | 入口 | 结果 |
|---|---|---|---|
| AISettingsDialog | 🤖 AI 设置 620×340 | 帮助 → 🤖 AI 设置 | ✅ 服务商/Key/接口地址/模型/刷新本机模型/测试连接/隐私说明 |
| CloudSettingsDialog | ☁️ 云存储设置 480×400 | 帮助 → ☁️ WebDAV 设置 | ✅ |
| BackupCenterDialog | 🗂️ 备份与恢复 760×460 | 帮助 → 备份与恢复 | ✅ |
| PluginMarketDialog | 🔌 插件市场 720×520 | 帮助 → 插件市场 | ✅ 4 插件列表+详情+启用开关 |
| CommandPalette | 命令面板 450×280 | Ctrl+Shift+P | ✅ 内置命令（新建 Markdown/Word/表格/幻灯片、打开/保存/另存为…） |
| 模板选择 QDialog | 📄 选择模板 750×500 | 文件 → 从模板新建 | ✅ 14 个模板/6 分类（工作 6、数据 3、财务 2、会议 1、项目 1、其他 1） |
| MemoryMonitor | 内存监控 | 帮助 → 内存监控 | ✅ 非模态 |
| 快捷键浮层 | 快捷键（长按 Ctrl） | 长按 Ctrl 1 s | ✅ 但 Markdown 未渲染（P2-4） |
| 智能数据分析 | 640×420 | 工具 → 智能数据分析 | ✅ |
| PivotTableDialog | 📊 数据透视表 560×480 | 工具 → 刷新透视表 | ✅ |
| 筛选对话框 | 列/包含/OK/Cancel | 蜜算筛选按钮 | ✅ |
| 图表类型选择 | 柱状图…雷达图 | 蜜算插入图表 | ✅ |
| 保真度提示 | 保真度提示（warning） | 打开含丢失构造文件后导出 | ✅ 文案矛盾（P2-3） |
| 关于 | 关于蜜蜂办公（about） | 帮助 → 关于 | ✅ |
| 拼写检查不可用 | information | Word 工具栏拼写检查 | ✅ 说明清楚（环境缺后端） |
| AI 不可用 | question「续写：没有可用的 AI」 | 工具 → AI 续写（无 Key） | ✅ 降级询问 |
| PPTX 导入损失清单 | information「已导入（部分元素未保留）」 | 蜜演打开 .pptx | ✅ 如实列出丢弃元素 |

### 6.5 能力矩阵（AI / PDF / 云同步 / 公文 / 图表 / 数据绑定）

| 能力 | 入口/证据 | 实测结论 |
|---|---|---|
| AI 辅助 | 工具→AI 辅助[续写/润色/总结]；帮助→🤖 AI 设置；`ai_client.py`、`beewrite_ai_mixin/beesheet_ai_mixin/beeshow_ai_mixin`；环境变量 `BEEOFFICE_AI_API_*` | ✅ 入口齐全；未配置 Key 时**明确询问是否用本地规则**（实测 Word 续写），不联网不崩溃；服务商 deepseek/custom/ollama |
| PDF | 插件「PDF 批注」；工具→PDF 批注；`pdf_annotator.py`（17 KB）；导出 PDF 菜单 | ✅ 插件启用、菜单/模块存在；**导出 PDF 未实测**（依赖 WeasyPrint/QtWebEngine 路径），仅记录入口 |
| 云同步 | 帮助→☁️ WebDAV 设置 / 立即同步 / 把当前文档加入同步目录；`cloud_settings.py`、`cloud.py` | ✅ 设置对话框真实打开（480×400）；同步动作存在（本机无服务器，未测传输） |
| 公文 | 产品代码（`beeoffice/**/*.py` + resources）检索「公文」 | ❌ **未发现**任何公文排版/红头模板/公文格式能力（0 命中） |
| 图表 | `beesheet_chart_mixin.ChartMixin`；matplotlib 可用；蜜算插入图表 | ✅ 6 种图表类型对话框真实弹出；大表需先完整载入 |
| 数据绑定 | `plugins/data_binding.py`、`plugins/variable_panel.py`；工具→关联表格到文档；`BeeWriteEditor.register_sheet_source` | ✅ 代码与菜单入口存在；本机只验证了入口，未做端到端绑定渲染 |
| 模板 | `templates.py` + TemplateManager；14 个模板 / 6 分类 | ✅ 模板选择对话框真实打开并列出 |
| 插件市场 | 帮助→插件市场 | ✅ 展示 4 个内置插件与启用状态 |

---

## 7. 发现的问题（全部有截图/JSON 证据与复现步骤）

### P0-1（高）大表两阶段载入：完整数据 25 s 未就绪，整表操作被安全门拦下且提示误导

- **现象**：打开 2.39 MB / 200001 行的 `测试文档_20 万条.xlsx` 后，界面右上提示「已显示前 500 行，正在后台
  加载完整数据…」；阶段 1 用时 7151 ms。等 25 s 后 `model.is_fully_loaded` 仍为 `false`。此时点筛选/透视/图表，
  产品弹出 **「无法透视表 — 没有可用的完整数据加载器……请重新打开该文件后再试」**，操作被取消。
- **根因（代码）**：`SheetDataModel.set_partial_dataframe(df, loader=None)` 的 `_full_loader` 为空；
  阶段 2 由 `_start_phase2_full_load()` 的后台线程完成，但期间 `_ensure_full_data()` 找不到 loader，
  直接把「请稍候」说成「请重新打开」。
- **证据**：`sheet.json` → `sheet_opens`、`steps.full_data_gate_while_loading`（`load_error=没有可用的完整数据加载器`）；
  `screens/dialog_msg_warning_无法透视表.png`、`screens/32_sheet_200k_items.png`。
- **复现**：打开该 XLSX → 立刻点「工具 → 刷新透视表」或「智能数据分析」。
- **建议**：安全门在阶段 2 进行中时显示「数据仍在后台加载（预计 X 秒），是否等待？」并支持等待/取消，
  而不是让用户重开文件。

### P1-1（高）20 万行 17.7 MB 表格首开最长 45 s，内存 584–1247 MB

- **现象**：`测试文档_20万行.xlsx` 阶段 1 只读 1000 行用于显示，却耗时 **13748 ms / 44991 ms** 两次实测
  （第二次与阶段 2 后台线程争 CPU）；进程 RSS 从 174 MB 涨到 **584 MB（单开）/ 1247 MB（两张大表并发加载后）**。
- **证据**：`sheet.json sheet_opens`；`screens/33_sheet_200k_rows.png`。
- **建议**：阶段 1 用 `read_only`/限制行数读取；限制并发完整载入数（同一时间只允许一个阶段 2 线程），
  并把后台加载进度显示在状态栏。

### P1-2（高）蜜演「新增幻灯片」页数不变，新页标题与第 1 页粘连

- **现象**：新建蜜演（2 页欢迎页、光标在文首）→ 触发 `add_slide()` 后仍是 **2 页**，缩略图第 1 条变成
  `1. 新幻灯片# 欢迎使用蜜演 🎥`，`slide_titles[0] = "新幻灯片# 欢迎使用蜜演 🎥"`。
- **根因（代码）**：`_add_slide()` 执行 `insertText("\n\n---\n\n## 新幻灯片")` —— 插入串**结尾没有换行/分隔**，
  且插入位置取当前光标（默认在文首），于是 `## 新幻灯片` 与原有 `# 欢迎使用蜜演 🎥` 粘成同一标题，
  正则按 `\n---` 切分后仍只有 2 页。
- **证据**：`show.json steps.add_slide`（before=2/after=2）；`screens/42_show_add_slide.png`。
- **复现**：新建蜜演 → 不点编辑区 → 点「新增幻灯片」。
- **建议**：插入串改为 `\n\n---\n\n## 新幻灯片\n\n`，并在插入后把光标移到新页。

### P2-1（中）大纲自动编号与用户手写编号叠加重复

`screens/23_word_outline.png` 中显示 `1.1 一、目标达成情况`、`1.1.1 1.1 核心指标`：OutlinePanel 自动编号 +
用户 Markdown 自带编号叠加。建议提供「大纲自动编号」开关或检测已有编号时不再叠加。

### P2-2（低）取消保存时状态栏显示「保存失败」

Word/蜜算/蜜演三处实测：另存为对话框取消后，状态栏显示 **「保存失败」**（`word/sheet/show.json` 的
`steps.save_current_stub_cancel.status`），且无任何提示框。取消是正常操作，应显示「已取消保存」。

### P2-3（中）保真度提示文案与报告内容矛盾（note-only 报告）

对 `测试文档_200页.pptx` 的分析结果是 `items=[]`、`summary="未发现无法保真的构造"`，但 `note` 非空
（「蜜演目前只支持导出 PPTX，不支持导入」）→ `should_prompt_before_export()` 返回 True，弹出的对话框却写
**「这份文件里有内容无法完整保留」**。说明性 note 与丢失项应使用不同文案。
证据：`main.json fidelity_prompt`、`screens/dialog_msg_warning_保真度提示.png`。

### P2-4（低）快捷键浮层以纯文本渲染 Markdown

`screens/09_shortcuts_overlay.png` 中显示 `## 全局`、`` `Ctrl+S` `` 反引号原样可见（`QTextEdit.setPlainText`）。
建议改用 `setMarkdown()` 或渲染后 HTML。

### P2-5（低）「云存储设置」菜单项实际仍显示「☁️ WebDAV 设置」

`menus.py` 的 `tr()` 默认值/注释都写「云存储设置」，但 `locales/zh_CN.json:36` 的
`menu.help.webdav_settings` 仍是「☁️ WebDAV 设置」，实际菜单显示旧名；打开的对话框标题是「☁️ 云存储设置」，
菜单与对话框命名不一致。

### P2-6（低）拼写检查在本机不可用

无英文语言包、无 pyspellchecker/enchant。产品提示**清晰完整**（给出 3 种启用办法、说明不联网），
但按钮仍可点击后才提示；若能在启动时探测并置灰/加提示更佳。证据：`screens/dialog_msg_information_拼写检查不可用.png`。

### P3-1（info，非产品缺陷）PySide6 QMenu wrapper 生命周期坑

`menuBar().actions()` 返回的列表被 GC 后，由 `action.menu()` 取到的 QMenu wrapper 会报
`Internal C++ object already deleted`（probe 实测：不保留列表时 5 个 QMenu 有 4 个失效；保留后全部有效）。
写自动化盘点/截图脚本必须持有 `actions()` 列表引用 —— 这条会影响后续 GUI 自动化测试的稳定性。

### P3-2（info，非产品缺陷）离屏渲染限制：字体 / emoji / WebEngine

1. offscreen 平台默认字体库为空（`QFontDatabase` 找不到字体目录），中文渲染成豆腐块；设置
   `QT_QPA_FONTDIR=C:\Windows\Fonts` 后 202 个字体可用（截图里中文正常）。
2. 缺 emoji 字体，工具栏图标位显示 `□`（`🐝/📄/🔌` 等）；真实 Windows GUI 用 Segoe UI Emoji 不受影响。
3. 本机沙箱禁止命名管道 → **真实 QWebEngineView 实例化即 FATAL**：
   `[14680:15708:FATAL:platform_channel.cc(85)] Check failed: . : 拒绝访问。 (0x5)`，退出码
   `-2147483645 (0x80000003)`，与 `tests/conftest.py` 第 33–56 行记录完全一致。因此蜜演右侧预览、
   F5 全屏播放、导出 PDF/图片这些依赖 WebEngine 的路径**本机不可测**（代码路径已确认存在，真机可用）。

---

## 8. 限制与不可测项（如实说明）

| 项目 | 状态 | 原因 |
|---|---|---|
| 蜜演 WebEngine 预览区渲染 | ⛔ 未测 | 沙箱禁命名管道，真实 WebEngine FATAL；用哑元 QWidget 替代后其余 UI 全部真实 |
| F5 全屏播放 / 激光笔 / 远程同步演示 | ⛔ 未测 | 同上（依赖 WebEngine/QWebSocket Server） |
| 导出 PDF / 导出图片序列 | ⛔ 未测 | 依赖 WeasyPrint + WebEngine |
| 云同步真实传输 | ⛔ 未测 | 需要 WebDAV/OneDrive 服务器 |
| AI 真实 LLM 调用 | ⛔ 未测 | 无 API Key；已实测「未配置 Key」的降级路径 |
| 蜜演 AI 大纲完整降级 | ⚠️ 部分 | 需要 QInputDialog 输入主题/受众/页数，自动化被输入框桩取消 |
| 蜜算完整数据（20 万行）载入完成时间 | ⚠️ 未完成 | 25 s 超时未就绪，按问题 P0-1 记录；未继续长时间等待 |
| 真实显示器下的分辨率/DPI/emoji | ⚠️ 未测 | 本次按要求离屏运行 |

---

## 9. 复现步骤（从零到截图）

1. **准备**：确认 Python 3.11 + PySide6 6.6、语料位于 `tests/fidelity/corpus/`；无需网络。
2. **环境变量**：见 §1.2；`HOME/USERPROFILE` 指向临时目录，`BEEOFFICE_DRAFT_DIR` 指向空临时目录。
3. **安全网**：`python _ptmp/analysis/compare/_runner_common.py` 被四个 runner 自动 import；
   它安装 §1.2 的 monkeypatch（modal 录制、文件对话框桩、启动期定时器置空、HOME 隔离）。
4. **执行**：依次跑 `_runner_main.py`（约 15 s）、`_runner_word.py`（约 20 s）、
   `_runner_sheet.py`（约 2–4 min，取决于大表后台载入）、`_runner_show2.py`（约 15 s）。
5. **合并**：`python _ptmp/analysis/compare/_merge_inventory.py` → `app_raw.json`。
6. **已知坑**：
   - 必须设置 `QT_QPA_FONTDIR`，否则中文全变豆腐块；
   - `_runner_sheet.py` 的大表阶段 2 后台载入会持续占用 CPU，脚本可能超过 120 s（本次两轮分别约 2.5/4 min），
     不是挂死；可用进程 RSS/CPU 区分「在干活」与「真的卡住」；
   - 不要调用 `window.close()`（有未保存标签会弹模态框）；脚本用 `os._exit()` 退出；
   - 真实 `QWebEngineView` 在本沙箱会 FATAL，必须走 `_runner_show2.py`（哑元替换）。

---

## 10. 机器可读数据（app_raw.json）

- `meta`：版本/环境/隔离信息/四份来源文件；
- `reproduce`：环境变量、命令、安全网清单；
- `startup` / `menus` / `actions`（150 个 QAction 的 text/shortcut/enabled/visible/tooltip/parent_class）；
- `plugins`（4 个插件元信息 + 发现统计）、`capabilities`（AI/PDF/云同步/公文/图表/数据绑定/插件）；
- `templates`（14 个/6 分类）；
- `dialogs`（全部 exec 对话框 + 录制的 messagebox 原文）、`fidelity`（语料保真分析结果）；
- `runs.word` / `runs.sheet` / `runs.show`（每一步的 ok/耗时/状态/消息、语料打开明细、内存）；
- `corpus_verification`（openpyxl 独立核验的真实行列数）；
- `issues[]`（11 条，含 severity/evidence/repro）；
- `screenshots`（59 张：file/bytes/note/category/widget_size + 尺寸分布统计）。

原始分项：`main.json`（启动/菜单/对话框/插件）、`word.json`（蜜写）、`sheet.json`（蜜算）、
`show.json`（蜜演）、`_tmp/*.log`（运行日志，含 WebEngine FATAL 证据）。

---

## 11. 结论

1. **可运行性**：启动快（275 ms 构造 + 21 ms 插件），三种编辑器、17 个关键对话框、4 个语料格式
   （DOCX/XLSX/PPTX）全部真实打开成功；离屏 + 安全网方案可稳定复现。
2. **最大风险在蜜算的大表格**：两阶段载入的「阶段 2 未完成」窗口期既慢（25 s+）又会让整表操作失败，
   且错误文案把「等待」说成「重开文件」，是本次盘点最值得优先修的产品问题。
3. **蜜演的「新增幻灯片」是明确的逻辑 bug**（页数不变/标题粘连），复现成本极低，应优先修。
4. **UI 细节**有一批低成本高收益项：取消保存的文案、保真提示文案、快捷键浮层 Markdown、菜单旧名、
   大纲编号叠加；另有按钮/图标 emoji 依赖真实字体，不影响真机。
5. **插件**：4 个内置插件全部启用、发现机制健康（99 扫描/4 加载/95 跳过）；插件不注册菜单（菜单集中在
   menus.py），插件能力通过命令面板暴露 —— 与产品架构说明一致。
