# BeeOffice 国际化术语表

> 适用范围：`beeoffice/locales/*.json` 与源码中的 `tr("key", "中文默认值")`。
> 目的：让 900+ 条文案在英文侧保持同一套说法，避免"每个模块各译各的"。

---

## 1. 产品名

| 中文 | 英文 | 说明 |
|---|---|---|
| 蜜蜂办公 | BeeOffice | 产品名，不翻译 |
| 蜜写 | BeeWrite | 文档编辑模块 |
| 蜜算 | BeeSheet | 表格模块 |
| 蜜演 | BeeShow | 演示模块 |
| PDF 批注 | PDF Annotation | 不使用 "PDF Comments" |

---

## 2. 最容易混的两个词：Sheet vs Table

这是本产品**必须区分**的一对——中文都叫"表格"，英文却是两个东西：

| 中文语境 | 英文 | 例子 |
|---|---|---|
| **蜜算**里的表格（电子表格） | **Sheet** | `BeeSheet: New Sheet`、`Export Sheet` |
| **蜜写/蜜演**里的表格（Word/幻灯片表格） | **Table** | `Table Properties`、`Insert Table`、`Table Style` |

反面例子（不要这样写）：
- ❌ `BeeSheet: New Table` —— 蜜算不是 Word 表格
- ❌ `Insert Sheet` 在蜜写工具栏 —— 那是插入表格

---

## 3. 批注 / 评论 / 备注

| 中文 | 英文 | 说明 |
|---|---|---|
| 批注（Word 里针对文字） | Comment | 动词用 `Add a comment` |
| 评论（幻灯片里针对整页） | Comment | 与批注同词，中文保持区分即可 |
| 备注（演讲者备注） | **Notes** | `Speaker Notes`，绝不译成 Comment |
| 书签 | Bookmark | |
| 修订 / 修订模式 | Track Changes | `Tracking` 表示进行中 |

---

## 4. 其余核心词

| 中文 | 英文 | 备注 |
|---|---|---|
| 文档 | Document | |
| 幻灯片 / 演示文稿 | Slide / Presentation | 单页用 Slide，整份用 Presentation |
| 大纲 | Outline | |
| 模板 | Template | |
| 图表 | Chart | |
| 导出 | Export | |
| 保存 / 另存为 | Save / Save As | `Save As` 作菜单，`Save as …` 作提示句 |
| 数据验证 | Data Validation | |
| 条件格式 | Conditional Formatting | |
| 名称管理器 | Name Manager | |
| 公式 | Formula | |
| 宏 | Macro | |

---

## 5. 大小写约定

| 场景 | 约定 | 例子 |
|---|---|---|
| 按钮 / 菜单项 / 面板标题 | **Title Case** | `Export PDF`、`Table Properties` |
| 提示句 / 状态栏 / 对话框正文 | **Sentence case** | `Write some slide content first` |
| 带快捷键的提示 | 句首大写 + 括号 | `Save (Ctrl+S)` |

---

## 6. key 命名约定

| 类型 | 形式 | 例子 |
|---|---|---|
| 手工编写 | `<模块>.<功能>` | `tab.close`、`cmd.palette.new_md` |
| 批量迁移生成 | `auto.<模块>.<文本哈希>` | `auto.beewrite_toolbar_mixin.640df3f2` |

哈希 key 由 `tools/i18n_migrate.py` 生成，**相同文案共用一个 key**，
所以同一个中文短语在全项目里只会翻译一次。

---

## 7. 语言包约定（重要）

| 文件 | 内容 | 原因 |
|---|---|---|
| `zh_CN.json` | **只放需要覆盖的 key** | 中文默认值写在代码里（`tr("key", "中文")`），重复维护会漂移 |
| `en_US.json` | **必须全量** | 英文没有"代码内默认值"，缺失就会回退成中文 |

因此两个文件的 key 数量**本来就不相等**（当前 en 841 / zh 246），这不是 bug。

---

## 8. 走查工具

```bash
python tools/i18n_extract.py          # 统计还有多少未国际化
python tools/i18n_migrate.py <文件>    # 批量包 tr()（默认预演，--write 落盘）
python tools/i18n_apply_en.py         # 按中文原文批量写入英文
python tools/i18n_unify.py            # 统一同一中文的多种译法
python tools/i18n_review.py           # 生成对照表 + 自动查冲突
```

最近一次走查结果：**678 条可对照文案，0 处同一中文多译法**。
