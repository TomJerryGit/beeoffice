# BeeOffice 保真度基线（阶段 A）

> 目的：**用数字回答"往返到底丢了什么"**，让后续所有"优化 Office 三件套"的
> 工作有一个可衡量的尺子。
>
> 测量日期：2026-10-11 ｜ 环境：Windows / Python 3.11 / offscreen

---

## 1. 怎么测的

| 组件 | 作用 |
|---|---|
| `tools/ooxml_probe.py` | 读 `.docx/.xlsx/.pptx`，数出**有意义的特征**（段落/样式/表格/合并/图片/超链接/页眉页脚/域/公式/条件格式/冻结窗格/图表/形状/备注…） |
| `tools/fidelity_roundtrip.py` | 生成标准测试文件 → 用**产品代码**做一次往返 → 前后各探一次 → 输出差值 |
| `tests/fidelity/test_ooxml_probe.py` | 25 条：仪器自检 + 当前状态的**特性化**测试 |

**为什么不做 XML 直接 diff**：OOXML 往返后必然出现大量无意义差异（rId 重编号、
`rsid`、时间戳、部件顺序），直接 diff 会淹没真正的丢失。特征计数更稳、更好读，
也更容易写成断言。

**仪器可信吗**：`tools/fidelity_roundtrip.py` 里的 `test_compare_is_not_vacuous`
用一个"故意删光"的文件做对照，必须报出 `lost`；另有一条断言"同一文件与自己比
不应有任何差异"。没有这两条，下面所有数字都可能只是常数。

**复现**：

```bash
python tools/fidelity_roundtrip.py                    # 打印报告
python tools/fidelity_roundtrip.py --keep _ptmp/fid   # 保留生成的文件
python -m pytest tests/fidelity -q                    # 跑基线断言
```

---

## 2. 往返怎么定义（关键）

| 格式 | 往返路径 | 备注 |
|---|---|---|
| DOCX | `bee_export.import_from_docx()` → **Markdown** → `bee_export.export_to_docx()` | 与 `app._open_docx_file` / 导出动作调用的是同一对函数 |
| XLSX | `pd.read_excel(engine='openpyxl')` → `df.to_excel(index=False)` | 即 `beesheet.py` 的导入与 `beesheet_data_mixin._export_xlsx()` |
| PPTX | **无往返** | BeeOffice **没有 PPTX 导入**，只导出 |

---

## 3. 实测结果

### 3.1 DOCX：丢失 6 项 → **现已零丢失**（2026-10-11 五刀修完）

| 状态 | 特征 | 往返前 | 往返后 |
|---|---|---|---|
| ✅ | `hyperlinks` | 1 | 1 |
| ✅ | `header_parts` | 1 | 1 |
| ✅ | `footer_parts` | 1 | 1 |
| ✅ | `page_margins`（twips） | 1417,1701,1417,1701 | 完全相同 |
| ✅ | 段落结构 | 顶层 6 段 | 顶层 6 段（逐段文字一致） |
| ✅ | `merged_cells` | 1 | 1 |
| ✅ | `paragraphs` / `table_cells` / `text_chars` | 14 / 8 / 102 | 14 / 8 / 102 |

**五刀各解决了什么**（全部用同一把尺子测量）：

| 刀 | 改了什么 | 效果 |
|---|---|---|
| 1 | `_para_to_md` 按**文档顺序**遍历，超链接写成 `[文字](url)` | `hyperlinks` 1→0 修复；文字不再少 12 字 |
| 2 | 页面设置与页眉页脚**绕开 Markdown**（`read_docx_extras`） | `header_parts`/`footer_parts`/`page_margins` 全部保住 |
| 3 | 段落之间补空行（列表项除外） | 顶层段落 6→4 变成 6→6 |
| 4 | 表格合并信息加入 extras（新一项） | `merged_cells` 1→0 修复 |
| 5 | 非标准纸张支持精确尺寸 | 200×280 这类自定义纸张不再被静默当成 A4 |

（第 4 刀与"非标准纸张"是同一批改动里的两件事，为叙述清楚在此分列。）

**表格合并是怎么修的**：Markdown 表格语法**表达不了合并**，所以与前两刀同样
**绕开 Markdown** —— 导入时 `_read_table_merges()` 记下
"第几张表 + 网格行列 + 跨度 + 合并后文字"，导出时 `apply_table_merges()`
用 python-docx 的 `merge()` 还原。两个易错点都已写成测试：

1. **`merge()` 会拼接两个单元格的文字**，所以合并后必须用记录里的原文覆盖，
   否则会变成"合计合计"。
2. **`row.cells` 对合并格会按网格列重复返回同一个单元格** —— 用
   `"".join(row.cells)` 判断"文字是否重复"会得到假阳性（我第一版就误判了）。

**一处仍存在的、用户可见的小瑕疵**（已知，未修）：`_docx_table_to_md()` 在把
合并表格转成 Markdown 时，会把合并单元格的文字**在每一列重复输出**
（`| 合计 | 合计 | 3,234 |`）。导出时因为还原了合并、并用原文覆盖，最终 DOCX 是
正确的；但**用户在蜜写里看到的 Markdown 仍带着重复文字**。这属于"表格在
Markdown 里的表示法"问题，需要与合并信息一起设计，留待后续。

**保留**：`sections`、`style_defined`、`styled_paragraphs`、`headings`、`tables`、
`table_rows`、`images`、`has_numbering`。

**超链接这一项修了什么**（实测机制，不是猜的）：


`import_from_docx()` 把普通段落交给 `_para_to_md()`，而它遍历 `para.runs` ——
python-docx 的 `Paragraph.runs` 只返回 `w:p` 的**直接子** `w:r`，超链接的文字位于
`w:hyperlink/w:r`，所以 **整段超链接被静默丢掉**：链接和链接文字一起消失。

这同时解释了"文字少 12 字"——少的正是链接文字。（我一开始猜是 `para.text`
不含链接文字，**实测否定了这个猜测**：`para.text` 合计 82 字符，与底层 `w:t`
的 82 字符一致，说明 python-docx 已能取到链接文字；真正的漏洞在 `para.runs`。）

修法：按**文档顺序**遍历 `w:p` 子元素，`w:hyperlink` 取文字与目标
（外部 `r:id` → URL，内部 `w:anchor` → `#书签`）写成 `[文字](url)`；
导出路径既有的 `_add_hyperlink()` 再把它还原成真正的 `w:hyperlink`。

**仍然丢失的 1 项及原因**：

- **合并单元格**（并连带 `table_cells` 8→9、`paragraphs` 14→15、`text_chars` 102→104，
  都是它的必然结果）：Markdown 表格语法**表达不了合并**。

这是唯一剩下的结构性损失。修它需要给表格引入**新的承载方式**（例如把合并信息
放进 sidecar，按"第几张表 + 行列 + 跨度"记录），代价比前几刀都大 —— 因为它同时
牵动表格的渲染、编辑与导出。**注意**：`_docx_table_to_md()` 目前会把合并单元格的
文字**在每一列重复输出**（`| 合计 | 合计 | 1,234 |`），这也是同一条根因的表现。

### 3.2 XLSX：9 项特征丢 8 项 → **现已零丢失**（2026-10-11 两刀修完）

**当前**：7455 B → 7462 B，**全部 11 项特征零差异**

| 状态 | 特征 | 往返前 | 往返后 |
|---|---|---|---|
| ✅ | `sheets` | 2 | 2 |
| ✅ | `formulas` | 4 | 4 |
| ✅ | `nonempty_cells` | 21 | 21 |
| ✅ | `merged_ranges` | 1 | 1 |
| ✅ | `conditional_formatting` | 1 | 1 |
| ✅ | `data_validations` | 1 | 1 |
| ✅ | `freeze_panes` | 1 | 1 |
| ✅ | `charts` | 1 | 1 |
| ✅ | `cell_xfs`（数字格式） | 2 | 2 |

**演进轨迹**（同一把尺子 `python tools/fidelity_roundtrip.py` 测量）：

| 阶段 | 丢失项 |
|---|---|
| 建立基线 | **8 / 9**（第二张表消失、公式全丢） |
| 第一刀：工作簿对象承载多表 + 公式 | 5 / 9 |
| 第二刀：**打开源工作簿、只更新单元格值** | **0 / 9** ✅ |

**两刀各做了什么**：

1. 新增 `plugins/beesheet_workbook.py`：把"工作簿"作为显式对象承载全部工作表与
   每格公式；`read_workbook()` 用 pandas 读各表值 + openpyxl（`data_only=False`）
   扫公式字符串，`write_workbook()` 把公式格写回**公式**而不是 pandas 的计算值。
2. `write_workbook()` 改为 **"打开源文件 → 只改 `.value` → 另存"**：合并区域、
   条件格式、数据验证、冻结窗格、图表、数字格式都是 openpyxl 不碰的东西，
   因此**天然保留**。只有在没有源文件时（CSV 导入、新建表格）才新建工作簿。

**这一刀暴露的两个 openpyxl 陷阱**（都已写成测试）：

1. **`ws.cell(row, col, value=None)` 是空操作** —— openpyxl 只在
   `value is not None` 时赋值。所以"清空单元格"必须写
   `ws.cell(...).value = None`。踩到时表现为：**用户删掉的一行仍留在导出文件里**
   （`test_openpyxl_cell_value_none_is_a_noop`）。
2. **合并区域内的非锚点格子是只读的**（`MergedCell`），给它赋值会抛
   `AttributeError`。有意思的是它**曾被陷阱 1 掩盖**：早先用 `value=None`
   恰好不会对合并格赋值，所以不报错；一旦改成正确的 `.value = ...` 就暴露了。
   修法是 `_readonly_merged_coords()` 跳过这些格子。

**仍存在的既有约束**（已写成测试，不再是谜题）：

1. **首行一律当表头**：pandas 的固定约定，因此没有表头行的表会丢掉首行
   （`test_headerless_sheet_loses_its_first_row`）。
2. **公式格的值在无缓存时读为 NaN**：openpyxl 写出的 xlsx 不含缓存计算值，
   而 pandas 读的正是缓存值。真实 Excel 文件里有缓存值，故只影响程序生成的文件；
   公式字符串本身不受影响（`test_formula_value_is_nan_without_cached_result`）。
3. **pandas 按"已用区域"判断表格范围**：工作表下方/右方的说明文字会被当作
   数据行吸收进 DataFrame。实测：一个只写了 3 行数据的表，因为第 20 行有一句
   备注，读出来是 **19 行**。用户可见后果是"表格下方有备注的工作表在蜜算里会
   显示一长串空行"（`test_used_range_absorbs_content_below_table`）——
   这是下一个值得处理的项。

### 3.3 PPTX：只出不进

| 特征 | 值（构造的测试文件） |
|---|---|
| slides | 2 |
| shapes | 3 |
| pictures | 1 |
| tables | 1 |
| text_runs | 8 |
| text_chars | 28 |
| notes_slides | 1 |
| slide_layouts | 11 |
| slide_masters | 1 |
| media_files | 1 |

因为没有导入路径，**"打开别人的 PPTX 编辑"这件事目前做不到**，也就谈不上往返保真。
`test_pptx_has_no_import_path` 会在将来实现了导入时失败，提醒把它改成往返测量。

---

## 4. 真实文件与压力语料（2026-10-11 新增）

合成夹具（3.1–3.3 用的那一个）覆盖面很窄。为了检验"零丢失"是否成立于
**真实世界**，新增了两层语料：

| 层 | 内容 | 工具 |
|---|---|---|
| **真实文件** | `test+files/` 里仓库自带的真实 Word/Excel 样例 | `tools/fidelity_corpus.py` |
| **压力语料** | `tools/fidelity_corpus_gen.py` 生成，9 个文件各专攻一个维度 | 同上 |
| **自定义** | 脱敏文件放 `tests/fidelity/corpus/` | 同上 |

### 4.1 真实文件：**零丢失** ✅

| 文件 | 特征概览 | 结果 |
|---|---|---|
| `永遇乐·京口北固亭怀古.docx` | 92 段落（多为空段）、217 字、2 表 87 格、4 标题、编号 | **零差异** |
| `Test永遇乐·京口北固亭怀古.docx` | 2.5 MB、94 段落、2 张图片 | **零差异** |
| `表格.xlsx` | 1 表 28 个非空单元格 | **零差异** |

**一次差点误判**：第一次运行报 `Test...docx` 的 `images 2 → 0`，看起来像
图片丢失。查下去发现是**测量环境假象** —— 该文件的 `<名>_media/` 目录
**早已存在**（时间戳 2026-09-17，仓库自带），而当前进程无权覆盖里面的
PNG，于是图片提取失败。修法不是改产品，而是**让工具在临时目录里操作副本**。
顺带修掉了工具会往语料目录写 `_media/` 的问题。

### 4.2 压力语料：撞出 **3 类新丢失**（这就是语料的价值）

| 文件 | 专攻维度 | 结果 |
|---|---|---|
| `docx_lists.docx` | 项目符号 / 编号列表 | **零差异** ✅ |
| `docx_headers.docx` | 页眉含表格 + 非标准纸张 | **零差异** ✅ |
| `xlsx_wide.xlsx` | 200 列 × 50 行 | **零差异** ✅ |
| `xlsx_tall.xlsx` | 5000 行 | **零差异** ✅ |
| `xlsx_rich.xlsx` | 3 表 + 公式 + 合并 + 条件格式 + 验证 + 冻结 + 图表 | 无丢失（见下方行为记录） |
| `docx_inline.docx` | 超链接（外部 + 内部书签）、粗斜体 | **`bookmarks` 1 → 0** |
| `docx_sections.docx` | 两个分节（第二节横向） | **`sections` 2 → 1**、`paragraphs` 5 → 4 |
| `docx_tables.docx` | 横向/纵向合并、**嵌套表格** | **`tables` 4 → 3**、`text_chars` 52 → 50 |
| `pptx_basic.pptx` | — | 跳过往返（无导入路径） |

**这三类丢失就是下一刀的方向**，按"用户可见程度 × 实现难度"排序：

1. ~~**多分节（`sections`）**~~ —— ✅ **已修（第七刀，2026-10-11）**，详见 4.3。
   仍剩 `paragraphs` 5 → 4：承载 `sectPr` 的那个**空段落**在 Markdown 里
   没有对应表达（空行 ≠ 空段落），属已知项，用户可见影响很小（少一个空行）。
2. **嵌套表格（`tables` 4 → 3）** —— 单元格里的表格在 Markdown 里没有对应表达，
   **整块内容消失**。按内容损失程度，这是剩下最该修的一项。
3. **书签（`bookmarks`）** —— 书签消失，**指向它的内部跳转变成死链**。
   （超链接字符串本身已能保留，缺的是锚点目标。）

**行为记录（不是丢失）**：`xlsx_rich.xlsx` 的非空单元格 25 → 27（+2）。
原因是它的"说明"表**非矩形**（首行 1 格、次行 3 格），pandas 读成矩形
DataFrame 后写回就被规范化了。这是"用 pandas 读写表格"的固有行为，
已写成测试记录（`test_irregular_sheet_is_rectangularised`）。

**结论**：五刀修好的那些项在**真实文件**上确实零丢失；但真实世界的构造
远不止那一个合成夹具所覆盖的 —— 压力语料立刻撞出了分节、嵌套表格、书签
三类新问题。这正是"先做 corpus"的意义。


三条根因，决定了修复顺序：

### 4.3 三条根因的当前状态（更新于 2026-10-11）

| # | 根因 | 状态 |
|---|---|---|
| 1 | **蜜算的模型是 DataFrame**（数据即模型） | ✅ **已解决**：`beesheet_workbook` 承载多表与公式；导出改走"打开源工作簿只更新值"，合并/条件格式/冻结/图表/数字格式天然保留。**实测零丢失** |
| 2 | **蜜写用 Markdown 当内部中间层** | 🟡 **大幅改善**：单合成夹具与**真实文件**均零丢失。仍然丢失的是 Markdown 表达不了且尚未另开通路的构造：**多分节、嵌套表格、书签**（见 4.2） |
| 3 | **蜜演没有 PPTX 导入** | ⬜ 未动。这是功能缺失（不是保真缺陷）；短期应如实告知用户"只导出不导入" |

**下一步优先级**（按用户可见程度 × 实现难度）：

1. **多分节** —— 后果最直观：横向的那一节会变成纵向。与页面设置同路（extras
   记录每个 section 的纸张/方向/边距 + 它起始的段落），但导出时要重建分节。
2. **嵌套表格** —— 单元格里的表格整块消失，需要新的表示法。
3. **书签** —— 书签消失导致内部跳转成为死链。
4. **PPTX 导入** —— 留到架构阶段。


---

## 5. 局限（必须知道）

- **合成文件覆盖不全**：3.1–3.3 与压力语料里的文件都是程序生成的。
  已补上**真实文件**一层（`test+files/`，见 4.1）与自定义语料目录
  （`tests/fidelity/corpus/`，放脱敏的真实文件）。
  但仍**远未穷尽**：文本框、脚注、批注、SmartArt、艺术字、域、内容控件、
  数据透视表、宏（.xlsm）等都还没有语料覆盖。
- **PPTX 导出保真未测**：蜜演的导出走"Chromium 测量 + python-pptx 重建"，
  需要 QtWebEngine 实际渲染；本会话沙箱禁止命名管道会让 Chromium 在
  `setHtml()` 处 FATAL 崩溃（见 `docs/baseline.md` §6.1），因此**无法在此环境测量**。
  这需要一台没有该限制的机器（例如 GitHub CI）来补。
- 探针数的是**结构特征**，不能判断"看起来一样不一样"（视觉保真）：
  字体、行距、缩进、颜色是否保持，本套工具**测不到**。

---

## 6. 与既有工作的关系

- 本目录的测试已进入常规测试套件，CI 会跑（`tools/run_tests_isolated.py`）。
- 这套数字可以直接用来验收规划里的优化项：
  例如"蜜写直写 OOXML"做完后，`test_page_margins_do_not_survive` 会失败 ——
  那时就该更新基线并在此文档记录改善。

---

## 7. 进展记录

| 日期 | 变更 | 效果（实测） |
|---|---|---|
| 2026-10-11 | 建立基线（探针 + 往返运行器 + 25 条测试） | DOCX 丢 6 项；XLSX **丢 8/9 项**；PPTX 无导入 |
| 2026-10-11 | **第一刀**：新增 `beesheet_workbook`（多工作表 + 公式），接入导入/导出 | XLSX **丢 8 项 → 丢 5 项** |
| 2026-10-11 | **第二刀**：`write_workbook` 改为"打开源工作簿只更新值" | XLSX **丢 5 项 → 丢 0 项**（11 项特征零差异）✅ |
| 2026-10-11 | **第三刀**：`_para_to_md` 按文档顺序遍历，超链接写成 `[文字](url)` | DOCX **丢 6 项 → 丢 4 项**：`hyperlinks` 1→1、文字不再减少 |
| 2026-10-11 | **第四刀**：页面设置与页眉页脚**绕开 Markdown**（`read_docx_extras` + `apply_header_footer`），并支持非标准精确纸张 | DOCX **丢 4 项 → 丢 2 项**：`header_parts`/`footer_parts`/`page_margins` 全部保住 |
| 2026-10-11 | **第五刀**：段落之间补空行（列表项除外） | DOCX **丢 2 项 → 丢 1 项**：顶层段落 6→4 变成 6→6，逐段文字一致 |
| 2026-10-11 | **第六刀**：表格合并信息加入 extras（`_read_table_merges` + `apply_table_merges`） | DOCX **丢 1 项 → 丢 0 项** ✅ `merged_cells` 1→1，连带 `table_cells`/`paragraphs`/`text_chars` 也回到基线 |
| 2026-10-11 | **第七刀**：**多分节**加入 extras（`_read_sections` + `apply_sections`） | `docx_sections.docx` **丢 2 项 → 丢 1 项**：`sections` 2→2（第二节仍是横向 297×210、左边距 15mm 不变） |
| 2026-10-11 | **收口**：路径收敛到产品代码 | **DOCX 与 XLSX 往返均为零丢失**；PPTX 仍无导入路径；真实文件 3/3 零差异 |

### 4.3 多分节是怎么修的（第七刀）

**难点不在读，在定位。** OOXML 里每个分节的 `w:sectPr` 挂在**该节最后一个
段落**的 `w:pPr` 里（最后一节的挂在 body 上）。而承载它的段落**通常是空段落** ——
python-docx 的 `add_section()` 就是新建一个空段来承载它 —— 偏偏**空段落在
Markdown 里会丢**（实测顶层段落 5 → 4）。

于是"记下段落索引、导出时插回第 N 段"必然错位。改用**文字锚点**：

```
读取：for 每个分节 → 找到承载 sectPr 的段落 → **向前找最后一个非空段落**，
      记下它的文字作为 after_text
导出：按 after_text 在正文里找到那一段，把 sectPr 插进它的 pPr
      （找不到才退回索引）
```

按文字定位对"空段落丢失导致的索引偏移"**免疫** —— 实测 `sections 2 → 2`，
且第二节仍是横向、页边距不变。已写成测试
（`test_anchor_survives_missing_empty_paragraph` 专门模拟"导出文档里没有那个空段"）。

`sections` 一旦提供，就由 `apply_sections()` 一并处理第一节（不再走单节的
`apply_page_settings`），避免两套设置互相覆盖。

**怎么读这张表**：每一行都是一次可复现的测量（`python tools/fidelity_roundtrip.py`），
不是估计值。改善后 `tests/fidelity/test_ooxml_probe.py` 里的旧断言会失败并要求更新 ——
这是有意设计的，避免"基线悄悄过期"。

---

## 8. 被调查后**否决**的候选（记录理由，避免重复讨论）

### 8.1 "表格下方备注被吸成空行"——**不是缺陷，不做**

上一轮我把它列为下一个候选，理由是"表格下方有备注的工作表在蜜算里会显示一长串
空行"。核查后认为**不该改**：

- pandas 与 Excel/WPS 一样按**已用区域**判定范围。在 Excel 里 A20 有内容时，
  你同样会看到第 2–20 行。**这就是电子表格的正常行为**，不是 bug。
- 要"修"成只显示到表格末尾，就得**丢掉第 20 行的备注** —— 那是用户写的真实内容，
  属于静默数据丢失，恰好是这套保真度工作要消灭的东西。
- 往返已经不会丢它（`test_content_below_table_survives_rewrite`）。

保留的只有一条特性化测试（`test_used_range_absorbs_content_below_table`），
用来记录行为、便于将来讨论"是否给用户一个提示"，而不是当作待修缺陷。
