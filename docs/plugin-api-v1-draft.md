# BeeOffice 插件 API v1 草案（S0，2026-10-28）

> 状态：草案，供 S1 实现；当前 `Plugin` 只支持“一个插件 = 一个编辑器 Tab”，
> 本文定义 WPS 式加载项所需的**扩展点/权限/生命周期**，不改变现有 4 个内置插件。
> 目标：让 AI 助手、PDF 工具箱、模板中心、数据工具箱等可以**注入现有编辑器**，
> 而不是各自再复制一套界面。

---

## 1. 设计原则

1. **插件只依赖稳定 API**，不直接摸 Qt 控件内部（`_ribbon`、`textCursor` 等）；
2. **权限显式声明**：读文档/写文档/网络/文件/AI，安装时展示、运行时二次确认；
3. **所有文档修改走事务**：保证单步撤销、可审计、可回滚；
4. **API 主版本兼容**：`api_version` 不匹配拒绝加载，不静默降级；
5. **内置与第三方同一套接口**：内置 AI/PDF 也用插件 API，避免“两套代码”；
6. **可测试**：提供 mock context + 契约测试模板；
7. **默认安全**：高危能力（宏、网络上传、文件删除）需显式权限；
8. **UI 可组合**：Ribbon/Task Pane/右键/命令面板/状态栏/启动中心。

---

## 2. 插件清单 `manifest.json`

```json
{
  "id": "com.beeoffice.ai-assistant",
  "name": "AI 文档助手",
  "version": "1.0.0",
  "api_version": "1",
  "min_app_version": "5.1.0",
  "entry": "plugin.py",
  "description": "文档问答、改写、翻译、表格洞察",
  "author": "BeeOffice",
  "icon": "icons/ai.svg",
  "permissions": [
    "doc.read",
    "doc.write",
    "ai.network"
  ],
  "activation": "on_demand",
  "ui": {
    "task_pane": {"id": "ai", "title": "AI 助手", "side": "right"},
    "ribbon": [
      {"tab": "AI", "group": "写作", "button": "改写", "command": "ai.rewrite"}
    ]
  }
}
```

字段说明：

| 字段 | 必填 | 说明 |
|---|---|---|
| `id` | 是 | 反向域名，全局唯一 |
| `api_version` | 是 | 主版本；不兼容拒绝加载 |
| `min_app_version` | 是 | 低于此版本拒绝安装 |
| `entry` | 是 | 包内 Python 入口（相对路径） |
| `permissions` | 是 | 权限列表，见 §4 |
| `activation` | 否 | `startup` / `on_demand`（默认） |
| `ui` | 否 | 声明式 UI 贡献；也可在代码里动态注册 |

---

## 3. Python 插件接口

```python
# plugin.py
from beeoffice.plugin_api import BeePlugin, PluginContext

class AIPlugin(BeePlugin):
    id = "com.beeoffice.ai-assistant"
    name = "AI 文档助手"
    version = "1.0.0"

    def activate(self, ctx: PluginContext):
        self.ctx = ctx
        ctx.ribbon.add_tab("AI", order=50)
        group = ctx.ribbon.add_group("AI", "写作")
        ctx.ribbon.add_button(
            group, text="改写", icon="edit", command="ai.rewrite"
        )
        ctx.commands.register("ai.rewrite", self.on_rewrite)
        ctx.events.on("selection.changed", self.on_selection)
        ctx.events.on("doc.closed", self.on_doc_closed)
        ctx.ui.add_task_pane(
            pane_id="ai", title="AI 助手", side="right",
            widget=self.build_pane,
        )

    def on_rewrite(self):
        ctx = self.ctx
        text = ctx.doc.selection_text()
        if not text:
            return
        with ctx.doc.transaction("AI 改写"):
            ctx.doc.replace_selection(
                ctx.ai.run("rewrite", text=text, style="简洁专业")
            )

    def build_pane(self):
        from PySide6.QtWidgets import QLabel
        return QLabel("AI 任务窗格内容")

    def deactivate(self):
        pass
```

### 3.1 PluginContext（最小 v1）

```python
class PluginContext:
    plugin_id: str
    app_version: str
    # UI
    ribbon: RibbonAPI       # add_tab/add_group/add_button/add_large_button
    ui: UiAPI              # add_task_pane, add_status_widget, show_dialog
    commands: CommandAPI    # register(id, handler, shortcut, title)
    # 文档
    doc: DocumentAPI        # kind, path, read(), selection_text(),
                           # replace_selection(), transaction()
    # 事件
    events: EventAPI        # on("doc.opened"/"doc.saved"/"selection.changed"/...)
    # AI
    ai: AIAPI              # run(task, **kwargs), stream(...)
    # 基础
    settings: SettingsAPI  # get/set(scope="plugin")
    jobs: JobAPI           # run_background(func, on_done, on_error)
    log: logging.Logger
```

### 3.2 RibbonAPI

```python
add_tab(title, order=100) -> TabHandle
add_group(tab, title) -> GroupHandle
add_button(group, text, icon, command, tooltip="") -> ButtonHandle
add_large_button(group, text, icon, command, tooltip="") -> ButtonHandle
remove(handle)  # 插件卸载时清理
```

### 3.3 UiAPI

```python
add_task_pane(pane_id, title, side="right", widget=callable|QWidget)
remove_task_pane(pane_id)
add_status_widget(widget, side="right")
show_dialog(title, widget)  # 模态
show_message(kind, text)
```

### 3.4 DocumentAPI

```python
kind -> "writer" | "sheet" | "show" | "pdf" | ...
path -> Path | None
read() -> DocumentSnapshot      # 只读快照，不暴露 Qt 内部对象
selection_text() -> str
replace_selection(text)         # 必须在 transaction 内
transaction(label) -> context manager  # 单步撤销
insert_at_cursor(text)
selected_range() -> RangeRef
```

> S1 只实现 Writer/Sheet 的只读 + 选区替换；Show 后续。

### 3.5 EventAPI

- `doc.opened` / `doc.saved` / `doc.closed`
- `selection.changed`
- `theme.changed`
- `command.invoked`（可选审计）

### 3.6 AIAPI

```python
ai.run(task, **payload) -> str
ai.stream(task, **payload) -> Iterator[str]
ai.provider_info() -> dict
```

- 统一走 `beeoffice` 现有 AI 配置（本地 Ollama / OpenAI 兼容）；
- 插件不直接读 API Key；
- 网络权限由宿主控制，每次外发提示数据范围。

---

## 4. 权限模型

| 权限 | 允许 | 风险 | 提示 |
|---|---|---|---|
| `doc.read` | 读当前文档/选区 | 中 | 首次安装 |
| `doc.write` | 事务内修改文档 | 高 | 首次 + 每次安装 |
| `doc.export` | 另存/导出 | 中 | 首次 |
| `ai.network` | 调 AI/网络 | 高 | 首次 + 外发前 |
| `filesystem.read` | 读用户选择文件 | 中 | 文件选择器 |
| `filesystem.write` | 写文件 | 高 | 对话框确认 |
| `command.execute` | 执行外部程序 | 极高 | 默认拒绝 |
| `macro` | 宏/脚本 | 极高 | 默认关闭 + 白名单 |

规则：
- 安装时展示权限清单，用户可拒绝；
- 运行时敏感操作二次确认（如网络上传全文）；
- 插件不能调用其他插件私有函数；
- 所有写操作记录审计日志（插件 id、命令、文档、时间）。

---

## 5. 生命周期

```
install -> validate manifest -> permission prompt -> load entry
        -> activate(ctx) -> [commands/events/UI active]
        -> deactivate() -> cleanup hooks
        -> uninstall (remove files/settings optional)
```

- `activation: startup` 仅核心插件；第三方默认 `on_demand`；
- 激活失败回滚 UI 贡献，记录错误，不阻塞主程序；
- 禁用/卸载时调用 `deactivate()` 并移除 Ribbon/Task Pane/事件。

---

## 6. 打包与分发

`*.beeplugin` = zip：

```
manifest.json
plugin.py
icons/
assets/
tests/ (可选)
```

- 安装：校验 zip 路径穿越、manifest、API 版本、签名/hash；
- 插件市场复用现有 `PluginMarketDialog`；
- 支持禁用/更新/回滚版本；
- 第三方插件默认放在用户目录，不写入安装目录。

---

## 7. 安全与隔离

- v1：同进程，但**不暴露 Qt 对象**；仅通过 DocumentAPI/事务；
- 高风险插件（宏/外部命令）默认禁用，需 `command.execute` 权限；
- 可选 v2：子进程 + JSON-RPC，崩溃隔离；
- 网络/文件操作全部经宿主代理，便于审计与限流；
- 契约测试：插件必须能在 `MockPluginContext` 下 activate/deactivate。

---

## 8. 与现有 `Plugin` 的关系

| 现有 | 新 API |
|---|---|
| `Plugin.create_widget()` 整页编辑器 | `BeePlugin.activate(ctx)` 扩展点 |
| `register_menus()` | `ctx.ribbon` / `ctx.commands` |
| `register_commands()` | 同左（命令面板） |
| 无权限 | manifest permissions |
| 无任务窗格 | `ctx.ui.add_task_pane()` |
| 无事件 | `ctx.events` |
| 无文档事务 | `ctx.doc.transaction()` |

迁移路径：
1. 保留现有 4 个内置插件；
2. 新增 `plugin_api.py` 适配层，内置 AI/PDF/模板先用新 API 写；
3. 现有 `Plugin` 保留兼容，逐步标记 legacy；
4. 插件市场只接受 v1 新格式（旧包提示升级）。

---

## 9. S1 实现验收

- [ ] `plugin_api.py`：manifest 解析/校验、PluginContext 核心 API；
- [ ] Ribbon/Task Pane/Command/Event 四个扩展点可用；
- [ ] 文档只读 + Writer/Sheet 选区替换 + 事务撤销；
- [ ] 2 个示例插件：AI 改写、PDF 合并（无 UI 依赖）；
- [ ] 契约测试 + 权限测试；
- [ ] 插件安装/禁用/卸载不重启；
- [ ] 启动增量 <100ms（不激活第三方插件）。

---

## 10. 待定问题

1. 插件是否需要独立 Python 依赖隔离（venv）？v1 先用主环境，安装时校验 requirements；
2. 文档 API 是否需要暴露表格/形状对象，还是只暴露文本+选区？v1 先只读写文本；
3. 插件市场是否允许上传代码，还是只允许本地安装？先只本地/内置；
4. 宏控制台是否复用同一权限模型？复用，`macro` 权限单列；
5. 是否需要插件 UI 的 QSS 隔离？v1 用统一主题 token，不允许全局 QSS。
