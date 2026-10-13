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

### 3.2 XLSX：9 项特征丢了 8 项（7424 B → 5559 B）

| 状态 | 特征 | 往返前 | 往返后 |
|---|---|---|---|
| **丢失** | `sheets` | 2 | 1 |
| **丢失** | `nonempty_cells` | 19 | 14 |
| **丢失** | `formulas` | 4 | 0 |
| **丢失** | `merged_ranges` | 1 | 0 |
| **丢失** | `conditional_formatting` | 1 | 0 |
| **丢失** | `data_validations` | 1 | 0 |
| **丢失** | `freeze_panes` | 1 | 0 |
| **丢失** | `charts` | 1 | 0 |

**保留**：`cell_xfs`（数字格式定义）—— 但那是 pandas 自己写的新样式，不是原文件的。

解读：**这一条最严重**。导出实现是 `df.to_excel()`，本质上把表格当"一张数据表"，
而公式、合并、条件格式、冻结、图表**全都不是 DataFrame 能承载的东西**。
所以不是"导出时忘了写"，而是**这些信息在编辑期就没有地方存**。

`sheets` 从 2 变 1 是因为 `pd.read_excel` 默认只读第一张工作表 —— **第二张表
直接消失**，连数据都没了。

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
| 1 | **蜜算的模型是 DataFrame**（数据即模型），格式无处存身 | 公式/合并/条件格式/冻结/图表全丢；多表只剩一张 | 编辑期引入能承载格式的模型（公式与格式是**单元格属性**，不是数据）；导出改走 **openpyxl 直接写**而不是 `to_excel` |
| 2 | **蜜写用 Markdown 当内部中间层** | 页眉页脚/页边距/合并单元格/超链接/空段落全丢 | 导入时把这些**另行保留**（内部模型或 sidecar），导出时写回；中期目标是 DOCX 直读写 OOXML |
| 3 | **蜜演没有 PPTX 导入** | 无法编辑现成演示稿 | 大工程；短期先如实告知用户"只导出不导入" |

**优先级建议**：

1. **XLSX 多表 + 公式**（收益最大、最容易被用户当成"不能用"）：至少让
   `read_excel(sheet_name=None)` 读全部工作表、并把公式原样带回。
2. **DOCX 页边距 + 页眉页脚 + 合并单元格 + 超链接**：先做"另行保留再写回"，
   不必一步到位改成 OOXML 直写。
3. **PPTX 导入**：留到架构阶段（原规划阶段 B）。

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
