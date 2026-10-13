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

### 3.1 DOCX：丢失 6 项（38786 B → 37566 B）

| 状态 | 特征 | 往返前 | 往返后 |
|---|---|---|---|
| **丢失** | `paragraphs` | 14 | 13 |
| **丢失** | `text_chars` | 102 | 90 |
| **丢失** | `merged_cells` | 1 | 0 |
| **丢失** | `hyperlinks` | 1 | 0 |
| **丢失** | `header_parts` | 1 | 0 |
| **丢失** | `footer_parts` | 1 | 0 |
| 增加 | `table_cells` | 8 | 9 |
| 变化 | `page_margins`（twips） | 1417,1701,1417,1701 | 1440,1800,1440,1800 |

**保留**：`sections`、`style_defined`、`styled_paragraphs`、`headings`、`tables`、
`table_rows`、`images`、`has_numbering`。

解读：

- `merged_cells` 丢失**必然**导致 `table_cells` 从 8 变 9 —— 一个合并格被拆回两格。
  这两条是同一个原因，放在一起看才解释得通。
- **页眉页脚整部件消失**（`word/header1.xml`、`word/footer1.xml` 不再存在）。
- **超链接消失**：`Markdown → DOCX` 这条路上 `[文字](url)` 没有被还原成
  `w:hyperlink`。（阶段 2 修过"导出时写真正可点击的超链接"，但那是 Markdown
  文本里**本来就有的**链接；这里丢的是**从 DOCX 导入**的链接 —— 导入侧没有把它
  转成 Markdown 链接。）
- **页边距变成默认 1 英寸**：根因是 `import_from_docx()` 的返回类型是
  **Markdown 字符串** —— Markdown 根本没有"页面设置"这个概念，信息在第一步
  就没了，不是导出时漏写。
- 文字少 12 字、段落少 1 段：空段落/纯空格段落没有往返。

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

## 4. 结论：按"根因"而不是按"功能点"排序

三条根因，决定了修复顺序：

| # | 根因 | 后果 | 修法 |
|---|---|---|---|
| 1 | **蜜算的模型是 DataFrame**（数据即模型），公式/格式无处存身 | ~~公式/多表~~（**已修**：工作表数与公式数不再丢失）；合并/条件格式/冻结/图表/数字格式仍丢 | ✅ 第一步已完成：`beesheet_workbook` 承载多表与公式。**下一步**：导出改为"复制源文件再改"，即可天然保留合并/条件格式/冻结/图表 |
| 2 | **蜜写用 Markdown 当内部中间层** | 页眉页脚/页边距/合并单元格/超链接/空段落全丢 | 导入时把这些**另行保留**（内部模型或 sidecar），导出时写回；中期目标是 DOCX 直读写 OOXML |
| 3 | **蜜演没有 PPTX 导入** | 无法编辑现成演示稿 | 大工程；短期先如实告知用户"只导出不导入" |

**优先级建议**：

1. ✅ **XLSX 多表 + 公式**（已完成，见 3.2）
2. **XLSX 剩余 5 项**：把 `write_workbook()` 改成"打开源工作簿 → 只更新单元格值"，
   而不是新建工作簿。这样合并区域、条件格式、数据验证、冻结窗格、图表、
   数字格式**都能天然保留**，是最省力的一步。
3. **DOCX 页边距 + 页眉页脚 + 合并单元格 + 超链接**：先做"另行保留再写回"，
   不必一步到位改成 OOXML 直写。
4. **PPTX 导入**：留到架构阶段（原规划阶段 B）。

---

## 5. 局限（必须知道）

- **测试文件是合成生成的**，不是真实世界的复杂文档。真实文件里有分节、文本框、
  编号列表、脚注、批注、SmartArt 等，**实际丢失只会比这里更多**。建议后续把
  真实文件放进 `tests/fidelity/corpus/`（脱敏后）并让探针遍历该目录。
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

**怎么读这张表**：每一行都是一次可复现的测量（`python tools/fidelity_roundtrip.py`），
不是估计值。改善后 `tests/fidelity/test_ooxml_probe.py` 里的旧断言会失败并要求更新 ——
这是有意设计的，避免"基线悄悄过期"。
