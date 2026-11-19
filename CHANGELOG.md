# 更新日志

本文件记录蜜蜂办公 BeeOffice 的所有重要变更。

格式参考 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.0.0/)，
版本号遵循 [语义化版本](https://semver.org/lang/zh-CN/)。

---

## [5.4.8] - 未发布

> Wave 1：Excel P0（页面/打印闭环，第一增量）。

### BeeSheet
- 新增“页面”页签：打印预览、页面设置、设置/取消打印区域；
- 页面设置：页边距、纸张方向、纸张大小、缩放、网格线、标题；
- 打印预览基于 QPrintPreviewDialog + QTextDocument，支持分页；
- 打印区域只输出选中范围；
- 新增 `tests/qt/test_beesheet_print.py`。

### W2 审阅/公式
- 新增“审阅”页签：保护工作表/工作簿、插入/查看批注、拼写检查；
- 公式页新增“函数分类”“显示公式”“错误检查”“计算选项”；
- 打印设置新增页眉/页脚文字；
- 新增 `tests/qt/test_beesheet_w2.py`。

### W3 数据整理
- 新增“重复与汇总”组：删除重复项、分列、分类汇总、合并计算；
- 分类汇总/合并计算提供结果预览；
- 新增 `tests/unit/test_beesheet_data_tools.py`。

### W4 视图/网格
- 新增视图开关：网格线、行号列标、显示比例、页面布局；
- 分页预览入口复用打印预览；
- 网格行按滚动按需扩展，取消 5000 行硬上限；
- 新增 XLSX 数据级往返测试。

### 已知边界
- 打印缩放/页眉页脚按页重复仍未完成；
- 数据验证“文本长度”类型尚未落地；
- 分类汇总/合并计算当前为结果预览，不直接插入原表；
- 打印缩放值已保存，但当前渲染尚未应用缩放（下一步接入）；
- 页眉/页脚当前只出现在文档首尾，尚未按页重复；
- 拼写检查为基础常见错误词典，不是完整词典。

## [5.8.31] - 未发布

> P1：完整 PPT 母版/版式 XML 保留。

### BeeShow
- 导出以源 PPTX 为母版基底；
- 移除源幻灯片但保留 master/layout/theme；
- 新页按源版式名称选择 layout；
- 测试验证导出页 layout 名称与源一致；
- 占位符仍为近似重建（非完整 ph 语义恢复）。

### 质量
- 分段全量：1691 passed。

## [5.8.30] - 未发布

> P1：PPT 占位符近似重建 + 测试隔离结论。

### BeeShow
- 提取占位符文本/类型/几何；
- 导出时按源占位符文本匹配并重建近似占位符形状；
- 保留页面背景色；
- 完整母版/版式 XML 复制仍为后续项。

### 质量
- 按文件隔离：Qt 86/86 通过；
- 分段全量：1691 passed。

## [5.8.29] - 未发布

> P1：PPT 母版背景/占位符元数据 + 复杂 Excel 样本。

### BeeShow
- 提取母版/版式背景色；
- 提取版式/页面占位符类型与几何信息；
- 导出时恢复每页背景色；
- 占位符对象重建仍为后续项。

### BeeSheet
- 新增复杂 Excel 样本：公式/条件格式/数据验证/图表/打印区域/多工作表；
- 新增复杂样本往返测试。

### 质量
- 分段全量：1691 passed；
- 一次性 Qt 全量仍有 WebEngine 偶发崩溃。

## [5.8.28] - 未发布

> P1：Word TOC 域导入还原。

### BeeWrite
- 导入 DOCX 时识别 TOC 域并插入目录标记；
- 编辑器将标记转换为目录块；
- 导出时恢复 Word TOC 域；
- 新增 TOC 导入导出测试。

### 已知缺口
- PPT 母版/占位符仍未保留；
- 全量 Qt 套件存在 WebEngine 偶发崩溃，需继续排查。

## [5.8.27] - 未发布

> P1：复杂特性覆盖补强。

### BeeSheet
- 修复 pandas 读不到缓存值时公式列被丢弃；
- 导出时按公式坐标补写，保留公式列。

### BeeShow
- 保留备注/切换/时间轴 XML；
- 复杂夹具验证切换、时间轴、备注往返。

### 质量
- 新增复杂 Word/Excel/PPT 夹具测试；
- 全量测试：1688 passed，0 warnings。

### 已知缺口
- Word TOC 域导入尚未还原；
- PPT 母版占位符仍未专项覆盖。

## [5.8.26] - 未发布

> P0：PPT 图表/表格导入导出保留。

### BeeShow
- 导入 PPTX 时提取原生图表数据/位置；
- 导入 PPTX 时提取原生表格内容/位置；
- 图表/表格配置持久化到页注释；
- 导出时重建原生 Chart/Table；
- 用户 5 份真实 PPT 验证：图表 1→1、表格 1→1；
- 新增 `tests/unit/test_pptx_native_object_retention.py`；
- 全量测试：1685 passed。

## [5.8.25] - 未发布

> 质量治理：全量测试警告归零。

### 质量
- 子进程测试显式使用 UTF-8 解码，消除最后一条线程警告；
- 全量测试：1684 passed，0 warnings；
- pytest 保留分类过滤与警告摘要，不再全局屏蔽。

## [5.8.24] - 未发布

> 质量治理：测试警告从 116 降至 1。

### 质量
- matplotlib 图表统一中文字体，消除缺字形警告；
- pandas 单元格混合类型写入前转 object，消除 FutureWarning；
- CSV 分块读取器 finally 关闭，消除 ResourceWarning；
- pypdf 页面先加入 writer 再 merge，消除 replace_contents 弃用警告；
- 测试改用 `setFontFamilies`；
- pytest 移除全局 `--disable-warnings`，改为分类过滤并保留摘要；
- 全量测试：1684 passed，1 warning（测试线程 GBK 解码，待查）。

## [5.8.23] - 未发布

> 质量修复：图表中文字体警告。

### Charts
- matplotlib 统一配置 `Microsoft YaHei / SimHei` 字体；
- 修复图表中文标签缺失字形警告；
- 全量测试：1684 passed，警告从 116 降至约 18–41（取决于警告过滤）。

## [5.8.22] - 未发布

> Word 保真：浮动文本框 + 独立页脚图片 + 真实语料模板。

### BeeWrite
- 文本框支持嵌入/左浮动/右浮动、X/Y 偏移、高度；
- 导出浮动文本框为 `wp:anchor`（WPS Shapes=1，位置生效）；
- 页脚图片按节独立提取/导出，不与页眉共用；
- 新增 `docs/真实语料采集模板-2026-11-18.md`；
- 全量测试：1684 passed。

### 已知边界
- 浮动文本框不支持环绕方式/层级编辑；
- 页脚图片仅支持常规页脚，首页/偶数页页脚图片独立未做；
- 真实语料仍为 6 份合成/代表性样本。

## [5.8.21] - 未发布

> Word 保真：原生文本框 + 每节页眉页脚图片。

### BeeWrite
- QTextFrame 文本框导出为 Word 原生 `wps:txbx`；
- 导入时提取原生文本框文本；
- 每节页眉/页脚图片按节提取与导出；
- WPS 验证：原生文本框 Shapes=1、文本正确；
- 新增 `tests/unit/test_word_textbox.py`、每节图片测试；
- 全量测试：1682 passed。

### 已知边界
- 文本框仅文本/背景/边框，无旋转/浮动定位；
- 每节页脚图片仍与页眉共用提取列表，未完全区分；
- 真实语料仍为 6/20。

## [5.8.20] - 未发布

> Word 保真：表格样式面板 + 页眉页脚图片 + 文本框修复。

### BeeWrite
- 新增表格样式面板：表头填充/边框/斑马纹；
- 表格样式同步到 DOCX 导出；
- 页眉/页脚图片提取与导出；
- 修复文本框插入失败（QTextFrame border/brush 参数错误）；
- 文本框内容可导出（非原生 Word 形状）；
- 新增 `tests/unit/test_word_header_images.py`、表格样式面板测试；
- 全量测试：1680 passed。

## [5.8.19] - 未发布

> Word 保真专项：表格样式。

### BeeWrite
- 新增 `read_docx_table_styles()`；
- 导入 DOCX 表格的表头填充色/边框色/斑马纹；
- 导出时按表格顺序应用样式；
- 新增 `tests/unit/test_word_table_style.py`；
- 全量测试：1678 passed。

## [5.8.18] - 未发布

> Word 保真专项：按文档顺序导入 + 每节页眉页脚。

### BeeWrite
- DOCX 导入改为按 body 顺序处理段落/表格，表格不再统一堆到文末；
- 每节读取/保留页眉页脚文本；
- 导出新节时独立写入页眉页脚（解除与上一节链接）；
- 节设置 UI 支持页眉/页脚；
- WPS 验证：2 节页眉分别为“第一节页眉/第二节页眉”；
- 新增 `tests/unit/test_word_import_order.py`；
- 全量测试：1676 passed。

## [5.8.17] - 未发布

> Word 保真专项：多节导入还原 + 每节独立设置。

### BeeWrite
- 新增 `read_docx_sections()`；
- 导入 DOCX 时按节边界插入分节符；
- 还原每节页面设置（方向/页边距/分栏/行号/边框）；
- 导出时按节使用各自设置；
- 页面页新增“节设置”入口；
- WPS 验证：2 节，分栏分别为 1/2；
- 新增 `tests/unit/test_word_multi_section_import.py`；
- 全量测试：1674 passed。

## [5.8.16] - 未发布

> Word 保真专项：页面边框 + 多节页面设置。

### BeeWrite
- 页面设置新增页面边框（颜色/宽度）；
- 导入/导出 `w:pgBorders`；
- 新增分节符，导出 DOCX 生成新 section；
- 新 section 自动应用页面/分栏/行号/边框设置；
- WPS 验证：2 sections，均 2 栏；
- 新增 `tests/unit/test_word_border_sections.py`；
- 全量测试：1672 passed。

## [5.8.15] - 未发布

> Word 保真专项：页面/分栏/行号。

### BeeWrite
- 新增 `read_docx_page_settings()`；
- 打开 DOCX 恢复方向/纸张/页边距/分栏/行号；
- 导出 DOCX 写入 `w:cols`、`w:lnNumType`；
- 新增 `tests/unit/test_word_page_fidelity.py`；
- 语料新增 `word-002-page-settings.docx`；
- 全量测试：1669 passed。

## [5.8.14] - 未发布

> P1：PPT 多系列图表 + 表格样式写入 PPTX。

### BeeShow
- 图表数据支持多系列（首行「标签,系列1,系列2」）；
- 柱状/折线分组渲染，原生 PPTX 写入多 Series；
- 表格样式（表头色/边框/斑马纹）写入原生 PPTX 表格；
- 表格样式持久化标记；
- 新增多系列/表格样式测试；
- 全量测试：1661 passed。

### 已知边界
- 图表仍为单类别轴/单图表区，无组合图/次坐标轴；
- PPTX 表格结构仍受测量器限制，样式可写入但行列还原有限。

## [5.8.13] - 未发布

> P1：PPT 原生图表对象 + 表格样式面板。

### BeeShow
- 图表改为原生图表对象：
  - 柱状/折线/饼图写入 PPTX 原生 Chart；
  - 图表配置持久化到页注释；
  - 预览仍用 PNG 渲染；
- 表格编辑器新增样式面板：表头色/边框色/斑马纹/应用样式；
- 新增原生图表/表格样式测试；
- 全量测试：1659 passed。

### 已知边界
- 表格样式输出为 HTML 表格，PPTX 导出样式可能简化；
- 原生图表暂不支持二次编辑数据/组合图。

## [5.8.12] - 未发布

> P1：PPT 图表插入/表格增强入口。

### BeeShow
- 新增“图表”插入：柱状图/折线图/饼图；
- 数据行格式“标签,数值”，自动渲染 PNG 并插入当前页；
- 表格视觉编辑器沿用已有 TableMixin；
- 新增 `tests/unit/test_beeshow_chart.py`；
- 全量测试：1657 passed。

### 已知边界
- 图表以 PNG 图片插入，不是 PPT 原生图表对象；
- 图表不能二次编辑数据；
- 表格仍是 Markdown/原生 PPTX 表格，未增强单元格样式面板。

## [5.8.11] - 未发布

> P1：PPT 多对象对齐/分布。

### BeeShow
- 新增对齐：左/水平居中/右/顶/垂直居中/底；
- 新增水平/垂直等距分布；
- 新增“对齐/分布”对话框，支持多选形状；
- 新增对齐/分布测试；
- 全量测试：1654 passed。

### 已知边界
- 对齐基准是选中对象包围盒，不是幻灯片边距；
- 分布只按形状尺寸等距，不处理重叠间距策略。

## [5.8.10] - 未发布

> P1：PPT 版式槽位绑定 + 智能参考线/对象吸附。

### BeeShow
- 新增版式槽位绑定：标题/副标题/正文要点/图片/说明；
- 设计页新增“槽位填充”入口；
- 原生形状拖拽加入智能参考线：
  - 幻灯片水平/垂直中心；
  - 其他形状左/中/右、上/中/下；
  - 5% 网格兜底吸附；
- 新增槽位/参考线测试；
- 全量测试：1653 passed。

### 已知边界
- 槽位填充按版式骨架替换第一组标题/列表/图片，不是逐页槽位模型；
- 智能参考线只在形状拖拽中生效，未做多对象对齐/分布。

## [5.8.9] - 未发布

> P1：PPT 占位符母版 + 四角缩放手柄。

### BeeShow
- 新增母版配置模型：标题/正文字体字号颜色、页脚、日期、页码；
- 母版配置持久化到 deck 注释；
- 新增页脚/日期/页码占位符覆盖层；
- 原生形状新增四角缩放手柄与 5% 网格吸附；
- 新增母版/缩放手柄测试；
- 全量测试：1651 passed。

### 已知边界
- 母版仍是 CSS 占位符样式，不是 PowerPoint 母版占位符对象；
- 版式绑定仍依赖现有 LAYOUTS，未做逐页槽位绑定。

## [5.8.8] - 未发布

> P1：PPT 画布直接拖拽/旋转 + 母版样式。

### BeeShow
- 原生形状支持画布内直接拖拽定位；
- Alt+拖拽旋转形状；
- 母版样式增加页脚文字/页码开关/标题颜色；
- 新增拖拽/母版状态测试；
- 全量测试：1649 passed。

### 已知边界
- 母版仍是全局样式，不是占位符母版；
- 画布拖拽未做吸附/对齐/参考线吸附。

## [5.8.7] - 未发布

> P1：PPT 原生形状编辑增强。

### BeeShow
- 原生形状支持位置/尺寸/旋转/文本/填充/边框编辑；
- 新增形状管理对话框；
- 支持上移/下移层级、删除；
- 形状旋转导出 PPTX；
- 新增形状编辑测试；
- 全量测试：1647 passed。

## [5.8.6] - 未发布

> P1 硬化：XLSX 公式往返。

### BeeSheet
- 打开 xlsx 时读取数据区公式；
- 导出已有工作簿时优先写回公式，不再只保留计算结果；
- WPS 真实验证导出后 C2 公式仍为 `=A2+B2`；
- 新增 `tests/unit/test_xlsx_formula_roundtrip.py`；
- 全量测试：1645 passed。

## [5.8.5] - 未发布

> Wave 5：P1 W5，PPT 原生形状/母版/视图基础。

### BeeShow
- 新增原生形状模型：矩形/椭圆/箭头/文本/艺术字；
- 形状持久化到每页 `beeoffice-shapes` 注释并导出 PPTX 原生形状；
- 设计页新增母版对话框（统一字体/背景）；
- 视图页新增幻灯片浏览/备注页/阅读视图入口；
- 新增 `tests/qt/test_beeshow_w5b.py`。

### 已知边界
- 形状仍不能像 WPS 一样拖拽/旋转/层级编辑；
- 母版是全局字体/背景简化版，不是完整占位符母版；
- 浏览/备注/阅读入口为基础视图切换。

## [5.8.4] - 未发布

> Wave 5：P1 W5，PPT 形状/幻灯片大小/参考线。

### BeeShow
- 插入页签新增形状/艺术字/文本框；
- 设计页签新增幻灯片大小（16:9/4:3），PPTX 导出同步尺寸；
- 新增参考线显示开关；
- 新增 `tests/qt/test_beeshow_w5.py`。

### 已知边界
- 形状是 HTML 块，不是可拖拽的 PPT 原生形状；
- 母版/主题色板/完整视图模式未实现；
- 艺术字为 HTML 文本，不是 WordArt。

## [5.8.3] - 未发布

> Wave 5：P1 W4，PDF 插入/加工/对比。

### BeePDF
- 新增“插入”页签：空白页、页码、页眉页脚、图片/图章、文档对比；
- 页面页新增“逆序”；
- 新增文本级 PDF 对比（新增/删除行）；
- 新增 `tests/unit/test_pdf_wave5_w4.py`；
- 全量测试：1639 passed。

### 已知边界
- 证书签名/时间戳/密文标记未实现；
- OCR/Office 转换仍为可选未集成。

## [5.8.2] - 未发布

> Wave 5：P1 W3，Word 封面/页面背景。

### BeeWrite
- 新增插入封面：标题/副标题/单位 + 封面后分页；
- 新增页面背景色，DOCX 导出写入 `w:background`；
- 审阅页新增“文档比较”入口；
- 新增 `tests/unit/test_word_wave5_w3.py`。

### 已知边界
- DOCX 加密未实现（缺少 msoffcrypto/Office 加密后端）；
- 页面边框/页面装饰图库尚未实现。

## [5.8.1] - 未发布

> Wave 5：P1 W2，Excel 图表/页面装饰。

### BeeSheet
- 图表新增组合图（柱状 + 折线双轴）；
- 新增“编辑数据源”入口；
- 新增“刷新透视表”入口；
- 页面页新增背景色/水印；
- 新增 `tests/unit/test_wave5_w2.py`。

## [5.8.0] - 未发布

> Wave 5：四模块 P1，第一增量。

### BeeSheet
- 新增条件格式管理器：查看规则、删除选中列、清除全部；
- 数据页新增“条件格式管理”入口；
- 新增 `tests/unit/test_conditional_manager.py`。

## [5.7.13] - 未发布

> P0 硬化：企业模板代表性回归。

### 工具
- 新增 `tools/enterprise_template_regression.py`；
- 新增 `tools/validate_enterprise_templates.ps1`；
- Word/Excel/PPT/PDF 代表性模板经 WPS 真实打开通过；
- 修复 xlsx 合并单元格导出时 `MergedCell` 只读问题。

## [5.7.12] - 未发布

> P0 硬化：真实文档样本回归。

### 工具/验收
- 新增 `tools/real_document_regression.py`；
- 新增 `tools/validate_real_docs.ps1`；
- WPS 真实打开：
  - Word：fields=2, footnotes=1, endnotes=1；
  - Excel：打印区域保留；
  - PPT：8 页 16 个动画识别；
  - PDF：20 页批注烧录通过；
- 全量测试：1631 passed。

## [5.7.11] - 未发布

> P0 硬化：XLSX 新文件样式导出。

### BeeSheet
- 全新表格导出现在写入基础样式：
  - 表头加粗/浅橙填充/居中；
  - 单元格细边框；
  - 自适应列宽；
  - 冻结首行；
  - 打印区域/横向页面；
- 全量测试：1631 passed。

## [5.7.10] - 未发布

> P0 硬化：PPT 退出/强调动画。

### BeeShow
- PPTX 动画支持：
  - 进入（fade_in / slide_in / zoom_in）
  - 退出（fade_out / slide_out / zoom_out，presetClass=exit）
  - 强调（pulse / grow / shake，animScale 基础效果）
- WPS COM 验证：3 个效果（进入/退出/强调）均识别；
- 全量测试：1630 passed。

## [5.7.9] - 未发布

> P0 硬化：Word 题注/交叉引用域。

### BeeWrite
- 题注导出为 Word `SEQ` 域 + 书签；
- 交叉引用导出为 Word `REF` 域；
- 支持图/表/公式；
- 新增 `tests/unit/test_caption_fields.py`；
- WPS Writer 验证 FIELDS=2；
- 全量测试：1629 passed。

## [5.7.8] - 未发布

> P0 硬化：Word 原生脚注/尾注。

### BeeWrite
- 新增 `beewrite_docx_notes.py`；
- `[F1]`/`[E1]` 标记导出为 Word 原生 `footnoteReference`/`endnoteReference`；
- 生成 `word/footnotes.xml`、`word/endnotes.xml`；
- WPS Writer COM 验证 Footnotes/Endnotes 均识别；
- 新增 `tools/validate_docx_wps.ps1`；
- 全量测试：1628 passed。

## [5.7.7] - 未发布

> P0 硬化：PPTX 动画真实 WPS 验收。

### BeeShow
- 修正 `p:timing` 中间 par 层，WPS 现可识别元素动画；
- 新增 `tools/validate_pptx_wps.ps1` 真实播放器验收脚本；
- WPS COM 验证：2 页幻灯片过渡 + 每页 1 个动画均被识别；
- 全量测试：1628 passed。

## [5.7.6] - 未发布

> P0 硬化：PPT 元素动画导出。

### BeeShow
- 新增 `beeshow_pptx_animations.py`；
- PPTX 导出写入基础 `p:timing` 进入动画（淡入/滑入/缩放滤镜）；
- 每页动画效果按 entries 生成；
- 新增动画 XML 保留测试；
- 全量测试：1628 passed。

### 已知边界
- 动画仅为基础进入效果，未覆盖退出/强调/路径；
- 需要真实 PowerPoint/WPS 打开验证（当前仅 python-pptx 读取校验）。

## [5.7.5] - 未发布

> P0 硬化：Word 目录 TOC 域。

### BeeWrite
- 目录块写入标记属性；
- DOCX 导出时生成 Word TOC 域（`TOC \o "1-3" \h \z \u`）；
- 打开 Word 后可右键更新目录/页码；
- 新增 `tests/unit/test_toc_field.py`；
- 全量测试：1627 passed。

## [5.7.4] - 未发布

> P0 硬化：PPT 过渡导出保留。

### BeeShow
- 新增 `beeshow_pptx_transitions.py`；
- PPTX 导出写入淡入/推入/擦除/覆盖过渡；
- 新增过渡保留测试；
- 全量测试：1626 passed。

### 已知边界
- 元素级动画（进入/退出/强调）仍未写入 PPTX；
- 过渡方向/速度只做基础映射。

## [5.7.3] - 未发布

> P0 硬化：XLSX 样式/打印设置保真。

### BeeSheet
- 新增 `beesheet_xlsx_export.py`；
- 打开 xlsx 后导出时优先写回原工作簿，保留：
  - 打印区域/冻结窗格/页面设置；
  - 单元格字体/填充/条件格式/合并；
- 全量测试：1625 passed。

## [5.7.2] - 未发布

> P0 硬化：DOCX 页眉页脚导入。

### BeeWrite
- 新增 `read_docx_header_footer()`；
- 打开 DOCX 时恢复普通/首页/偶数页页眉页脚配置；
- 往返测试由 xfail 转为通过；
- 全量测试：1624 passed, 1 xfailed。

## [5.7.1] - 未发布

> P0 硬化阶段，第一增量。

### 测试/文档
- 新增真实文档往返测试 `tests/roundtrip/test_p0_hardening.py`；
- 新增 `docs/P0硬化阶段-2026-11-17.md` 保真矩阵；
- DOCX 标题/表格、PPTX 文本往返通过；
- DOCX 页眉页脚、XLSX 打印设置/条件格式标记为已知边界；
- 全量测试：1623 passed, 2 xfailed。

## [5.7.0] - 未发布

> Wave 4：PPT P0 Beta。

### BeeShow W16
- 放映新增“从当前开始”；
- 20 页 PPTX 导出往返测试；
- 幻灯片复制/隐藏、设计/过渡/画布编辑纳入 Beta；
- 新增 `tests/qt/test_beeshow_w16.py`。

### 已知边界
- 画布覆盖不持久化、不导出 PPTX；
- 过渡/动画 PPTX 保留未验证；
- 母版/主题色板未实现。

## [5.6.3] - 未发布

> Wave 4：PPT P0，W15 画布编辑基础。

### BeeShow
- 预览元素拖动（鼠标拖拽）；
- Alt+滚轮调整元素宽度；
- Delete 删除选中元素；
- 画布撤销/重置；
- 画布覆盖只作用于预览，不修改 Markdown 源；
- 新增 `beeshow_canvas.py` 与测试。

### 已知边界
- 画布覆盖未持久化到 deck 文件；
- 未实现缩放手柄、层级、对齐；
- PPTX 导出不包含画布覆盖。

## [5.6.2] - 未发布

> Wave 4：PPT P0，W14 设计/过渡。

### BeeShow
- 新增“设计”页签：设计面板、过渡、动画入口；
- 统一字体应用到预览；
- 过渡效果可应用到当前页或全部页；
- 新增 `tests/qt/test_beeshow_w14.py`。

### 已知边界
- 过渡/动画目前是网页渲染层配置，PPTX 导出保留仍需验证；
- 母版/主题色板/幻灯片大小未实现。

## [5.6.1] - 未发布

> Wave 4：PPT P0，W13 幻灯片管理。

### BeeShow
- 新增“复制幻灯片”；
- 新增“隐藏幻灯片”，缩略图标记 [隐藏]；
- 幻灯片缩略图/拖拽排序/新建/删除/重命名沿用已有；
- 12 种版式系统沿用已有；
- 新增 `tests/qt/test_beeshow_w13.py`。

## [5.6.0] - 未发布

> Wave 3：PDF P0 Beta。

### BeePDF
- 转换基础：PDF→图片、PDF→TXT、图片→PDF；
- 加密/权限/水印 GUI；
- 20 页批注烧录往返测试；
- W9–W11 页面缩略图、页面管理、批注增强全部纳入 Beta；
- 新增 `tests/unit/test_pdf_w12.py`。

## [5.5.3] - 未发布

> Wave 3：PDF P0，W11 批注增强/保护入口。

### BeePDF
- 批注线宽（1–12）与颜色；
- 批注撤销/重做、显示/隐藏；
- 批注导入/导出 `.beeanno`；
- 连续阅读模式入口；
- 保护页：加密/权限、水印 GUI；
- 新增 `tests/qt/test_pdf_w11.py`。

## [5.5.2] - 未发布

> Wave 3：PDF P0，W10 页面管理 GUI。

### BeePDF
- 新增 PDF 页面管理器：缩略图、拖拽排序、删除、旋转、另存为新 PDF；
- 页面管理输出新文件，不修改原文件；
- 合并/拆分/提取/替换/裁剪/页面大小继续复用 PDF 工具箱；
- 新增 20 页 PDF 缩略图与重排往返测试；
- 新增 `tests/qt/test_pdf_w10.py`。

## [5.5.1] - 未发布

> Wave 3：PDF P0，W9 统一 Ribbon + 页面缩略图。

### BeePDF
- Ribbon 扩展为：开始 / 标注 / 页面 / 保护 / 转换；
- 左侧页面缩略图面板：懒渲染、当前页高亮、点击跳页；
- 页面页提供导航/页面工具/旋转入口；
- 保护/转换页入口复用 PDF 工具箱；
- 新增 `tests/qt/test_pdf_w9.py`。

## [5.5.0] - 未发布

> Wave 2：Word P0 Beta。

### BeeWrite W8
- 视图：全屏、标尺、网格、单页/多页入口；
- 脚注/尾注 DOCX 导出为文末注释区；
- 20 段 DOCX 导出性能基线测试；
- Word P0 Beta 构建。

### 已知边界（Word P0）
- 脚注/尾注不是 Word 原生脚注，只写文末注释区；
- 题注/交叉引用是文本，不是 Word 域；
- 目录是纯文本目录，不是 Word TOC 域；
- 分栏/行号只在导出 HTML 中应用，DOCX 未完全写入；
- 打印缩放/按页页眉页脚仍待后续。

## [5.4.9] - 未发布

> Wave 2：Word P0，W5 样式/段落第一增量。

### BeeWrite
- 新增样式库：正文/标题 1–4/引用/代码；
- 新增清除格式；
- 样式导出 DOCX 保留 Heading 1–4；
- 新增 `tests/qt/test_beewrite_styles.py`。

### W6 页面/页眉页脚
- 页面设置新增分栏（1–4）与行号开关；
- 新增页眉页脚设置对话框：首页不同、奇偶页不同、首页/偶数页页眉页脚；
- DOCX 导出写入 first_page/even_page 页眉页脚；
- 分栏导出写入 HTML `column-count`；
- 新增 `tests/qt/test_beewrite_w6.py`（含 20 段导出）。

### W7 注释/题注/目录
- 新增脚注/尾注（上标编号 + 文末记录）；
- 新增题注（图/表/公式）与交叉引用；
- 新增目录更新（按标题重建）；
- 新增字数统计对话框（字数/字符/段落）；
- 接受/拒绝修订沿用已有修订管理器；
- 新增 `tests/qt/test_beewrite_w7.py`。

### 已有能力
- 段落格式对话框（行距/段前后/缩进/边框/底纹）此前已存在，本增量未重复实现。

## [5.4.7] - 2026-11-13（Beta / Unsigned）

> BeeSheet 功能区重构：从散乱四行按钮改为 WPS 风格分类 Ribbon。

### BeeSheet UI
- 初始网格从 **1000×10** 扩大到 **5000×52**（A–AZ）；
- 默认列宽 82px、行高 24px，可视列数与 WPS 更接近；
- 新增 5 个分类页签：开始 / 插入 / 数据 / 公式 / 视图；
- 每个分类按功能分组（剪贴板、字体、对齐、数字格式、对象、函数、名称与审计、冻结窗格等）；
- 组名改为底部小字、去重边框、组间竖线；Tab/按钮使用主题 accent 状态。
- 去掉 emoji，导入/导出改用系统标准图标；
- 选中多格显示“表格工具”上下文页签；
- 记住上次页签；窄窗口自动隐藏组标题；
- 主窗口 QMenuBar 同步 WPS 扁平样式；
- 新增内置 SVG 图标集 `beeoffice/ribbon_icons.py`；
- 新增主窗口“文件”入口与快捷工具栏。
- SVG 图标支持亮/暗主题自动换色；
- PDF 批注器改为 WPS 式 Ribbon（开始/标注）；
- BeeWrite/BeeShow 已有 Ribbon 复用统一图标工厂；
- 新增边框/底纹图库与单元格边框绘制；
- 主窗口新增打印/分享入口与快捷栏自定义（QSettings）；
- 打开文档标签时自动隐藏主菜单和主快捷栏，扩大编辑区；
- 修复 WPS 拆组后 BeeWrite/BeeShow 字体/字号/主题下拉框被隐藏的问题。
- 边框图库支持上/下/左/右单边框；
- 快捷栏“调整顺序”支持拖拽排序；
- PDF 标注工具图标化，新增文本框/箭头/签名并支持烧录；
- 主窗口快捷栏“调整顺序…”支持拖拽排序；
- 边框图库支持上/下/左/右单边框；
- BeeWrite 插入页按 WPS 拆成四组；开始页拆成模式/字体/段落；
- BeeShow 开始页拆成主题/编辑/导出/放映/工具；
- PDF 新增矩形/圆形/直线；单边框支持工具栏小图标直选。
- PDF 新增文本框/箭头/签名并支持烧录。
- 隐藏/展开功能区按钮保留；
- 删除旧的无引用翻译键 8 个。

### 工程化
- 新增 `requirements.lock` / `requirements-dev.lock`（含 SHA-256）；
- 新增 CycloneDX SBOM：`sbom/cyclonedx-bom.json`；
- CI 全量测试与 Windows release 改用锁文件。

### 验证
- 新增 `tests/qt/test_beesheet_ribbon.py`；
- 相关 GUI/i18n 测试通过。

## [5.4.6] - 2026-11-12（Beta / Unsigned）

> M1A 零成本发布门禁；包含 v5.4.5 之后的质量修复。

### CI / 质量门禁
- 全量测试改为阻塞；新增安全扫描与核心 100% 覆盖率门槛；
- 新增 `tools/release_check.py` 发布检查；
- Release workflow 增加 artifact attestation；
- GitHub main 分支保护：`快速回归`、`全量测试` 必过。

### 修复
- 中文日期 `strftime("%Y年...")` 在英文 Windows locale 下崩溃，改为数字拼接；
- 测试不再依赖中文 `strftime`；
- `pandas<3.0`、`pypdf<7.0` 版本上限，避免 CI 依赖漂移；
- 包含 v5.4.5 的 `_split_cell` 合并单元格崩溃修复。

### 验证
- 全量测试 1550 passed；
- 核心覆盖率 12/12 = 100%；
- 安全扫描高危 0；
- 安装/卸载 Windows Server 冒烟、attestation workflow 通过。

### 发布口径
- **Beta / Unsigned**：未签名、无干净机验收、Win11 未验证。
- GitHub Release: https://github.com/TomJerryGit/beeoffice/releases/tag/v5.4.6

## [5.4.5] - 2026-11-12

> 热修复：拆分合并单元格崩溃。

### 修复
- `RichTextEditor._split_cell` 调用不存在的 `colSpan()`，改为 `columnSpan()`；
- 拆分合并单元格不再抛 `AttributeError`；
- 补充表格插入/合并/拆分/快捷键/右键菜单回归测试。

### 验证
- 全量测试 **1550 passed**；
- 核心模块 **12/12 = 100%**；
- 安全扫描高危 **0** 条；
- 安装包未签名、无干净机验收、Win11 未验证（与 v5.4.4 相同）。

### 发布
- v5.4.4: https://github.com/TomJerryGit/beeoffice/releases/tag/v5.4.4
- v5.4.5: https://github.com/TomJerryGit/beeoffice/releases/tag/v5.4.5

## [5.4.4] - 2026-11-12

> 高对比度内联样式清理第二批；首个从安全修复后源码发布的版本。

### 高对比度
- BeeSheet 审计/对话框/公式/UI/数据/委托等模块迁移 16 处内联样式；
- AST 审计：40 文件 / 86 处 → **32 文件 / 42 处**；
- 分页画布增加重排快路径（尺寸不变时不重复 setPageSize）；
- 新增 `build_release` 纯函数测试 6 项；
- 新增 DataMixin 纯逻辑与云同步 providers 结构化测试 10 项；
- 新增 DataMixin 筛选/清洗/批量/粘贴、FormulaMixin、Google/OneDrive API 分支测试 14 项；
- 新增 app 持久化、筛选弹窗、分片上传测试 11 项；
- 新增 app 保存/关闭/主题同步、BeeSheet 导出/清洗/表头菜单测试 9 项；
- 新增 app 自动保存/标签标题/自我保存/最近文件辅助测试 7 项；
- 新增 app 插件注册/插件加载/最近文件菜单/更新检查分支测试 6 项。
- 高对比度 AST 审计 **清零（0 文件 / 0 处）**；新增 `on_accent` token。
- 新增 DataMixin 导出/行列编辑/条件格式测试 4 项；
- 新增 app PDF/云同步/移动端/内存监控入口测试 6 项；
- 新增 app 演示/批量/AI/宏/插件市场入口测试 3 项；
- 新增 BeeSheet 复制 Markdown/智能粘贴/行头菜单测试 4 项；
- 新增 BeeSheet 审计辅助与透视表配置测试 7 项；
- 新增 legacy WebDAV 设置/同步入口测试 4 项，webdav.py 覆盖率 10%→55%；
- 新增图表生成与 Google/OneDrive 上传/目录分支测试 6 项；
- 新增图表保存/透视表窗口/WebDAV 同步 worker 分支测试 6 项；
- 新增 BeeSheet 数据验证/名称管理/统计面板/公式栏冒烟测试 5 项；
- 新增公式对话框/审计追踪/自动求和/空透视表冒烟测试 3 项；
- 新增透视表预览/生成、图表异常与 utils 纯函数测试 12 项。
- 全量测试 **1550 passed**；全仓覆盖率 **65.06%**。
- 验收范围：**决定不做 Windows 10/11 干净机验收**（本机 8 GB/VMware 14/无 Win10 ISO）；仅保留本机 Win10 与打包产物冒烟，发布说明不得写“干净机通过”。
- 风险接受：用户已确认接受“仅本机冒烟、无干净机验收”的风险；发布须披露未签名、未做干净机验收、Win11 未验证。
- 安全加固：旧 `formula_engine._eval_math` 改用 AST 白名单，拒绝属性/下标逃逸；`build_release.py` 移除 `exec`，改正则读取版本号。
- 新增 `tools/security_scan.py`：只扫裸 exec/eval/pickle/shell=True，排除 tests/dist/build/release-archive；当前高危 0 条。
- 新增 RichTextEditor 转换/TSV 粘贴/表格/标题列表/快捷键/右键菜单测试。
- v5.4.4 发布后修复：RichTextEditor._split_cell 调用不存在的 colSpan()，改为 columnSpan()，避免拆分合并单元格时崩溃；该修复已进入 v5.4.5 热修复包。
- 新增核心覆盖率门槛 `tools/coverage_gate.py`：核心模块 100%，GUI 仅报告；核心模块 **12/12 全部 100%**；GUI 覆盖率继续提升：图片编辑器 98%、模板管理器 94%、链接/图片/公式插入 48%、TabManager 46%→61%；段落 Mixin 7%→83%、链接 Mixin 74%、BeeShow AI 服务 88%；新增 BeeSheet 导入/填充柄、Beewrite 模式/格式测试；模式 Mixin 42%→71%、视图 Mixin 39%→72%、BeeShow 视频 100%、同步 99%、导出 72%、视图 72%；新增插件命令入口测试，BeeSheet 插件 87%、BeeWrite 插件 93%、导出 79%；新增段落/字符格式、过滤/条件格式菜单覆盖。新增闪填模式/来源列测试。新增排序/筛选/自动保存/关闭测试。
- v5.4.4 候选包已于 2026-11-12 从安全修复后源码重建并发布：
  https://github.com/TomJerryGit/beeoffice/releases/tag/v5.4.4
  安装包未签名；未做干净机验收；Win11 未验证。

## [5.4.3] - 2026-11-09

> M3 分页画布：表格/图片原位编辑、格式联动、图片拖拽缩放。

### 分页画布
- 表格单元格可直接在画布内点击并输入；
- 图片可点击选中，Delete 删除；
- 跨页表格/图片提示改为“可在画布内直接编辑”；
- 表格行列插入/删除、图片替换/缩放/删除右键操作；
- 状态栏快路径，画布连续按键约 2.3ms/键；
- 分页画布右键格式/对齐/样式/列表；图片拖拽缩放；Ctrl+B/I/U。
- 全量测试 **1093 passed**；覆盖率 **49%**。

## [5.4.2] - 2026-11-05

> M2 单页编辑原型与高对比度完善。

### 可编辑页面视图（M2 原型）

- 页面视图“编辑本页”：按单页内容区尺寸打开编辑器；
- 打开时自动选中当前页字符范围；
- 应用时用一次 QTextCursor 编辑块替换，保留撤销历史；
- 表格在编辑副本中保留；
- 已知限制：图片/表格跨页未拆分，仍不是严格逐页独立编辑。

### 高对比度

- 视图菜单“高对比度”（持久化）；
- 编辑器内部：Markdown、富文本、预览改为黑底白字；
- 查找替换栏、大纲面板、统一导航栏黑底白字/黄色边框；
- 主题 tokens 高对比度分支，Ribbon 等自动跟随；
- 新增 `tools/high_contrast_audit.py`：AST 审计真实 `setStyleSheet` 硬编码色；
  已从 106 处降到 86 处，剩余按模块继续。

### 显示验收

- 新增 `tools/display_acceptance.py`：
  `QT_SCALE_FACTOR=1.0/1.25/1.5/2.0` 下状态栏与缩放控件均可见；
- 环境仍只有 1 块屏幕，多显示器/混合 DPI 未实测。

### 验证

- 全量 `pytest tests`：**1024 passed**。

---

## [5.4.1] - 2026-11-05

> 蜜写视图与页面体验版本。

### 蜜写页面视图

- 新增只读纸张页面视图：
  - A4 纸张、当前页面设置的页边距；
  - 页眉/页脚绘制；
  - 页码域（第 X 页 / 共 N 页等格式，支持起始页）；
  - 分页滚动、页间间隔、真实页码；
  - 缩放 50%–200%；
  - 点击纸张正文定位到编辑区；
  - 页面设置/页眉页脚变化后自动刷新。
- 入口：页面视图按钮、`Ctrl+Alt+P`。

### 蜜写导航与状态

- 统一左侧导航栏：目录 / 章节 / 书签 / 查找替换；
- 状态栏显示页数；
- 状态栏缩放控件与 `Ctrl+=`、`Ctrl+-`、`Ctrl+0`、`Ctrl+滚轮`；
- 高频动作补快捷键（导出、PDF、宏、检查更新等）；
- Ribbon/按钮补可访问名称；
- 主题补按钮/下拉框焦点边框；
- 最近打开长路径截断显示，tooltip 显示完整路径。

### 验证

- 全量 `pytest tests`：**1002 passed**；
- 新增页面视图/导航/缩放/键盘契约测试；
- 截图基线包含页面视图。

### 已知限制

- 页面视图为只读预览，编辑仍在连续富文本/Markdown 视图；
- 页眉页脚仅单行文本，不解析域；
- 正文修改后需点“刷新”；
- 安装器仍未使用受信任代码签名证书。

---

## [5.4.0] - 2026-11-04

> **性能与发布工程版本。** 在 v5.3.2 基础上完成性能优化、
> 安装器/更新工具链、兼容性与内存基线，并将 PR #1 / #2 合并到 main。

### 性能

- 蜜写批量渲染：状态栏全文统计从“逐块触发”改为“渲染完一次”，
  200 段 Markdown → 富文本从 **12,119 ms 降到 87 ms**；
- 蜜写首次创建：matplotlib / pandas 延迟导入，
  从 **3,646 ms 降到 641 ms**；
- 启动导入：`import beeoffice.app` 从 **2.10 s 降到 1.49 s**；
- 新增 `tools/perf_baseline.py`，记录启动、渲染、表格、演示导出与内存基线。

### 发布工程

- Inno Setup 安装器（`installer/BeeOffice.iss` + `tools/build_installer.py`）；
- 自动更新检查：GitHub Releases 版本比较、HTTPS + sha256 校验、帮助菜单入口；
- Windows 代码签名工具（`tools/sign_windows.py`，支持 PFX/指纹、签名后重算 sha256）；
- 手动触发的 Windows Release 工作流；
- PR #1（本地 UI/PDF 后端整合）与 PR #2（S2 工具链）已合并到 main。

### 兼容性与内存

- 真实语料 roundtrip 抽样 **25 / 25 通过**：
  14 XLSX + 6 DOCX + 3 PPTX + 2 DOCX；
- 全功能扫描 **30 / 30 通过**；
- 8 轮编辑器创建/渲染/销毁内存审计：无线性泄漏，
  首次 +11.5 MB 为字体/文本引擎预热。

### 兼容性说明

- 运行时 PDF 后端仍为 pypdfium2 + pypdf + reportlab；
- PyMuPDF 仅测试使用，运行时无 `import fitz`。

### 验证

- 全量 `pytest tests`：**986 passed**；
- 蜜写/绑定/公式定向：107 passed；
- 性能基线脚本可复测（见 `docs/S3-兼容性与性能基线-2026-11-04.md`）。

### 已知限制

- 安装器当前**未使用受信任代码签名证书**；自签名测试包会触发 SmartScreen，
  不作为正式签名版分发；
- 全量语料 roundtrip 目前抽样 25 个，剩余语料后续补齐。

---

## [5.3.2] - 2026-11-02

> **从本地 UI 发布线搬运功能到 origin/main。** 本版在 v5.3.1 基础上按批次移植，
> 不合并两条独立历史；保留远端 PDF 页面工具与测试基线。

### 集成内容

- 模板与素材中心：本地素材库、导入/预览/复制路径；
- 发布工具链：`verify_release` / `sync_version` / `upload_github_release`；
- 主题 token 与 Ribbon 控件/图标模块；
- Writer Ribbon：文件/开始/插入/页面/引用/审阅/视图 + 表格工具上下文；
- BeeShow Ribbon：文件/开始/插入/放映/视图 + 动画面板；
- PDF 书签/图片签名工具箱、宏控制台（白名单 + 审计）；
- PDF 页面裁剪/插入/替换/压缩；
- 数据工具箱：图表推荐、一键清洗、透视表入口；
- 宏控制台：脚本导入/导出、保存/排序/PDF 合并压缩命令、首次风险确认。

### 验证

- 远端 main 起点基线：925 passed；
- 集成后全量：938 passed；
- 每批独立 commit，定向测试通过后再进入下一批。

---

## [5.3.1] - 2026-10-18

> **国际化收尾：未国际化的中文 UI 字符串清零。**
> 本轮改动集中在语言包与迁移工具链，不含功能变更。

### 概览

| 指标 | 5.3.0 | 5.3.1 |
|---|---|---|
| 未国际化字符串 | 830 条 | **0** |
| `tr()` 调用 | 906 | **1733** |
| 可对照条目 | — | **1446** |
| 英文缺失 / 译法冲突 | — | **0 / 0** |
| 自动化测试 | 892 项 | 892 项 |

### 国际化

- **覆盖率 100%**：所有中文界面文案均通过 `tr()`，`en_US` 1552 键。
- 翻译补齐 1558 条新文案（含 79 条长帮助文本），占位符原样保留。
- 覆盖范围从命令面板、工具栏扩展到错误提示、一次性对话框、崩溃报告等长尾。

### 工具修复（迁移工具链）

- **`logging.warning` 被误判为 `QMessageBox.warning`**：两者属性名相同，
  日志被当成界面文案去翻译。改为识别调用链基名后排除。
- **认不出 `tr(...).format(...)` 链式调用**：已翻译的字符串被继续计为未国际化，
  统计永远降不到 0。改为递归穿透属性调用。
- **跨行节点结束偏移算错**：`end_col_offset` 相对结束行，却按起始行累加，
  替换切片落到字符串中间，重写后语法错误（被写盘前的编译自检拦下）。

### 工具放宽（此前过度保守）

- 支持跨行 f-string 与跨行字面量（字节偏移本就支持）。
- 支持无占位符的 f-string（`f"加载完成"` 等价于普通字符串）。
- 支持格式说明符与转换标志（`{x:.1f}`、`{x!r}`）——`.format` 本就支持，
  之前一律跳过，导致带精度的文案永远迁移不了。

### 说明

本轮译文中的长帮助文本（崩溃提示、插件卸载说明等）未经过真实界面走查，
措辞如需调整，直接改 `beeoffice/locales/en_US.json` 即可，不必改代码。

---

## [5.3.0] - 2026-10-18

> **路线图阶段一~三全部完成。** 14 次提交：补上验收手段的缺口、
> 拆掉一个持续产生 bug 的结构，并完成三组用户可见功能。

### 概览

| 维度 | 5.2.0 | 5.3.0 |
|---|---|---|
| 自动化测试 | 878 项 | **892 项** |
| 语言包键数 | 876 | **798**（清理死键） |
| 仓库体积 | ~120 MB | **22.6 MB** |
| CI 快速回归 | 中文输出假失败 | **稳定通过** |

### 修复

- **蜜算排序崩溃**：`set_full_dataframe` 把数据补齐到 1000 行并用空字符串填充，
  数值列退化成 object（`int` 与 `''` 混合），`sort_values` 抛 `TypeError` 被 Qt 吞掉——
  用户点排序毫无反应。附带修了只更新 `_loaded_df`、`_full_df` 仍为旧顺序的问题。
- **精简版误加载蜜演**：`beeshow_plugin` 的包装模块不 import WebEngine（延迟导入），
  精简版里照样注册，直到点"新建演示"才抛错。改为按可选依赖过滤。
- **CI 假失败**：Windows runner 控制台为 cp1252，工具打印中文抛 `UnicodeEncodeError`，
  退出码 1 看起来像"语法检查失败"。工具侧加编码兜底，CI 侧设 `PYTHONUTF8`。
- **PPTX 遗留导出无返回值**：改为成功 `True` / 异常 `False`，与其它导出 API 一致。
- **`.gitignore` 漏掉 `dist-lite/`、`build-lite/`**：1115 个文件、238.6 MB 构建产物被纳入版本库。

### 新增

- **打包产物冒烟** `tools/smoke_packaged.py`：断言进程存活、启动日志、
  **插件数量**（完整版 4 / 精简版 3）、无崩溃日志。
  反向验证过——旧精简版冒充完整版会正确失败。
- **全功能扫描** `tools/functional_sweep.py`（28 项）与
  `BeeOffice-5.2.0-验收与优化路线图.md`。
- **蜜算列冻结**：与行冻结对称，左侧浮一个只显示首列的视图，纵向滚动与行高同步。
- **同步范围可选**：`cloud_sync_scope` = `recent`（已打开 + 最近）/ `current`（仅当前文档）。
- **同步冲突处理对话框**：冲突列表 + 三个动作（保留本地 / 采用远端 / 两个都留），
  处理后更新基线，下次同步不再误判。
- **宏扩展**：从只录制单元格赋值，扩展为 `set` / `format` / `sheet` 三类有序动作；
  v1 的四元组动作仍可播放。
- **MIT 许可证** + `THIRD_PARTY_NOTICES.md`：明确 PyMuPDF 为 AGPL-3.0，
  分发二进制时的义务单独说明。

### 架构

- **空行补齐下沉到显示层**：数据层只保存真实行，`rowCount()` 返回
  `max(真实行, 1000)`，空白行按需扩展。新增 `_coerce_value()` 按列类型转换
  （数值列写 `"7"` → 7；写文字则升级为 object，与 Excel 一致）。
  这是"排序崩溃"一类缺陷的共同根因。

### 工程

- 清理 89 个无人引用的翻译键，新增守卫测试（白名单仅 2 个动态前缀）。
- 仓库历史改写：`git filter-repo` 移除构建产物，`.git` 209.6 MB → 22.7 MB。
- CI 增加 `QT_QPA_PLATFORM=offscreen` 与 `QTWEBENGINE_CHROMIUM_FLAGS=--no-sandbox`。

---

## [5.2.0] - 2026-10-18

> **P1 缺陷基本清空。** P0 清零之后，这一版把"会算错数、会丢数据、
> 会卡界面、功能是假的"这几类问题逐项修掉。

### 概览

| 维度 | 5.1.0 | 5.2.0 |
|---|---|---|
| 自动化测试 | 768 项 | **846 项** |
| 精简版包体 | — | **250 MB**（完整版 605 MB） |
| i18n 术语冲突 | 4 处 | **0** |
| 缺失英文条目 | 35 条 | **0** |

### 新增

- **蜜演可选组件化**：`BEEOFFICE_LITE=1` 打包即产出不含 WebEngine 的精简版，
  605 MB → **250 MB**（−58.7%）。缺失蜜演时插件自动跳过并在日志说明，
  其余模块完全正常。
- **蜜算宏**：录制单元格编辑并回放（此前只有菜单，点了没反应）。
- **用户文档云同步**：已打开 + 最近文档的双向同步；冲突时保留 `.remote-<时间戳>`
  副本，不覆盖任何一方。
- **冻结首行**：真正的视图级冻结（此前只是锁定行高，滚动照样被顶走）。

### 修复

- **打包版插件全部加载失败（发布阻塞级）**：PyInstaller 把模块放进 PYZ 归档，
  磁盘上没有 `beeoffice/plugins/` 目录，目录扫描必然空转 → 「共加载 0 个插件」。
  界面还在，但蜜写 / 蜜算 / 蜜演 / PDF 批注四个模块全部消失，
  而启动日志看起来一切正常。5.1.0 的打包产物同样受影响（该版本未分发）。
  修复：目录不可用时回退到内置插件清单，并加一条"清单与真实文件必须一致"的测试防漂移。
- **蜜算公式（会算错数）**
  - `COUNTIFS` 把每个条件独立计数后相加（`>1` 且 `x` 被算成 4，正确是 1）
  - `SUMIFS` / `AVERAGEIFS` 条件区只取首列，多列时条件失效
  - 跨表 `VLOOKUP` 一律 `#ERROR`（区域被压平成参数列表，列号取到单元格内容）
- **蜜写往返（会丢内容）**：粗体/斜体/行内代码在切回 Markdown 时被整段抹平；
  引用块被加上斜体标记。
- **蜜算分块（会串行）**：乱序加载时位置与绝对行号错位，界面显示别的行的数据。
- **蜜演 PPTX**：测量失败仍返回成功 → 用户拿到版式错乱但提示"导出成功"的文件。
- **AI 续写**：上下文从句子中间截取时会重复插入原文。
- **测试连接**：在 GUI 线程同步发网络请求，最长冻结 10 秒。
- **敏感字段**：API Key / 密码从 Base64（编码）改为 Windows DPAPI（真加密），
  历史数据仍可读。
- **冻结首行**：该模块从未导入 `QHeaderView`，点击即抛异常被吞掉。
- **状态栏定时器**：`QTimer.singleShot` 在控件销毁后仍触发，Qt6 下可能 abort。

### 国际化

- 新增批量迁移与走查工具：`i18n_migrate` / `i18n_apply_en` / `i18n_unify` / `i18n_review`
- 补齐 35 条「有 `tr()` 但语言包缺英文」的条目（会静默回退中文，最隐蔽）
- 统一 4 处同义不同译；新增 `docs/i18n-glossary.md` 固化术语（Sheet vs Table 等）

### 已知限制

- 蜜算只支持行冻结，列冻结待做
- 冲突副本只保留在本地，不做自动合并（二进制文档无法可靠合并）
- 同步范围固定为「已打开 + 最近」，暂无界面选择

---

## [5.1.0] - 2026-10-18

> **生产级改造第一版：P0 缺陷清零。**
> 从 5.0.4 起共 26 次提交，覆盖数据安全、线程安全、导出正确性、
> 启动性能与国际化。详见下方条目。

### 概览

| 维度 | 5.0.4 | 5.1.0 |
|---|---|---|
| P0 缺陷 | 12 项 | **0** |
| 启动（打包版，可交互） | ≈ 10.4 s | **1.66 s** |
| Excel 读取（5 万行） | 50.9 s | **4.4 s** |
| 包体 | 698 MB | **605 MB** |
| i18n 覆盖 | 8.2% | **52.6%** |
| 自动化测试 | 739 项 | **768 项** |

> **重要更正（5.2.0 补记）**：上表「启动 1.66 s」是在打包版
> **加载 0 个插件**的情况下测得的——当时插件目录扫描在冻结环境里
> 一直空转，四个模块实际上没有加载（详见 5.2.0 的「打包版插件全部加载失败」）。
> 插件真正加载后的启动耗时需在空闲机器上重新基线化。


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
- **安全（插件市场）**：卸载会无条件删除插件文件，而内置插件与用户插件
  混在同一目录——用户点"卸载 蜜写"，`beewrite_plugin.py` 就从源码目录消失。
  现在安装时写入 `# BEEOFFICE_USER_PLUGIN` 标记，卸载只删带标记的文件；
  内置插件只允许"禁用"。
- **蜜演（假成功）**：PDF 导出调用异步的 `printToPdf` 后立刻弹"导出成功"
  并 `deleteLater()` 渲染页。现在等 `pdfPrintingFinished` 回调，
  成功/失败与实际写入结果一致。
- **蜜演（假成功）**：图片序列导出调用 `page.grab()`——`QWebEnginePage`
  没有该方法，异常被吞后仍报成功。改为 `QWebEngineView.grab()`，
  离屏渲染（`WA_DontShowOnScreen`）、等首帧 300ms，
  并按成功/失败张数如实提示。
- **蜜演（体验）**：移除导出图片时"3 秒后弹出模态『导出中』"的逻辑，
  它会抢焦点并阻塞事件循环。
- **蜜写（数据丢失）**：批注 / 书签的 `load_from_file` 从未被调用——
  保存后重开文档，批注与书签全部消失。现在打开文档时调用
  `load_annotations()` 恢复；并且**先清空再加载**，避免打开另一篇文档时
  继承上一篇的批注。
- **蜜算（性能）**：Excel 读取改用 `python-calamine`（Rust 实现）。
  实测同一份 50000 行 × 16 列 xlsx：**4.4s vs openpyxl 50.9s（11.6 倍）**；
  未安装时自动回退 openpyxl。
- **蜜算（性能）**：`LargeFileLoader` 的 xlsx 路径同样改用 calamine；
  单块返回时不再 `pd.concat`，峰值内存从约 2× 降到 1×
  （openpyxl 分块路径保留为回退，取消逻辑不变）。
- **性能（启动）**：`PluginManager.discover_plugins()` 原本 import
  `plugins/` 下**全部 86 个模块**，连带 pandas / numpy / PyMuPDF / matplotlib。
  实测该步骤 **7864 ms**，且发生在窗口 `show()` 之后 50 ms——
  表现为"窗口出来了但点不动"。
  现在只导入 `*_plugin` 包装器与带用户安装标记的插件：
  **53 ms（147 倍）**，其余模块按需导入。
- **打包（体积）**：新增 `tools/slim_dist.py`，删除运行期不需要的资源：
  - QtWebEngine DevTools 资源（83.4 MB）
  - Qt 自带翻译 `.qm`（项目用自己的 JSON 语言包，未使用 QTranslator）
  产物 **698.3 MB → 605.5 MB**。
- **蜜写（往返一致性）**：
  - 引用块：重建用 `leftMargin(20)` 而回写判断 `>30`，引用永远识别不回来；
    现在阈值改为 `>=10` 并剥掉 `▎ ` 前缀，多次往返不再累积。
  - 超链接：md→富文本只染色、不保存 URL；现在写入字符格式锚点
    （`setAnchor` / `setAnchorHref`），回写按 fragment 还原 `[文本](URL)`。
  - 表格：解析时 `if c.strip()` 吞掉空单元格导致列左移；现在保留空单元格，
    回写也不再丢弃"整列为空"的列。

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
- 新增 `tests/qt/test_beeshow_export_acceptance.py`（3 项，产物级验收）：
  PDF 用 PyMuPDF 打开并校验文字；PNG 校验非白像素占比；PPTX 用
  python-pptx 校验页数与文字。三者都替代"人工点一遍"。
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