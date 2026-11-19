# BeeOffice v5.8.35 Beta

状态：**Unsigned Beta**

## 本版内容

- Word：TOC 域导入还原、页面/分栏/行号/页面边框、多节页面设置、每节页眉页脚、表格样式、原生文本框。
- Excel：公式往返与公式列补写、复杂 Excel 样本（条件格式/图表/打印区域/多工作簿）。
- PPT：原生图表/表格保留、切换/时间轴/备注保留、源母版/版式复用、`.beshow` 持久化源母版路径。
- 质量：警告治理至 0；分段/按文件测试隔离；复杂特性夹具。

## Code signing policy

See [CODE_SIGNING_POLICY.md](../CODE_SIGNING_POLICY.md). Free signing is being
requested from SignPath Foundation; this build remains unsigned until approved.

## 已知限制

- 安装包未签名，SmartScreen 会提示。
- 未做 Microsoft Office 2016/2019/365 视觉验收；仅 Office 2007 结构验收。
- 一次性全量测试仍偶发 Qt WebEngine 崩溃；当前以分段/按文件隔离作为门禁。
- PPT 占位符为近似重建，不是完整 ph 语义恢复。
- 真实复杂 Excel 样本有限。

## 验证

- 分段全量：1693 passed
- WPS + Office 2007 打开验证
- 本地签名流水线测试（自签名，不构成公共信任）

## 说明

这是发布候选/Beta，不是 Stable，不应宣称企业可用。
