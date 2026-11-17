# BeeOffice v5.8.5

发布日期：2026-11-17  
Release：https://github.com/TomJerryGit/beeoffice/releases/tag/v5.8.5  
发布状态：**Beta / Unsigned**（未签名；未做干净机验收；Win11 未验证）

## 重点更新（Wave 5：四模块 P1 第一轮）

### BeeSheet
- 条件格式管理器：查看/删除/清除全部；
- 组合图、编辑数据源、刷新透视表；
- 页面背景色/水印；
- 真实 XLSX 样式/打印设置保留、新文件基础样式。

### BeeWrite
- 封面页、页面背景色；
- 文档比较入口；
- DOCX 页眉页脚/TOC 域/脚注尾注/题注交叉引用域；
- 真实 WPS Writer 验收通过。

### BeePDF
- 插入空白页、页码、页眉页脚、图片/图章；
- 页面逆序；
- 文本级文档对比；
- 真实 WPS 打开验收通过。

### BeeShow
- 形状/艺术字/文本框；
- 原生形状模型与 PPTX 导出；
- 母版简化版、幻灯片大小、参考线、浏览/备注/阅读入口；
- PPTX 过渡/进入/退出/强调动画，WPS 真实打开验收通过。

### 工程化
- 全量测试 **1644 passed**；
- 安全扫描高危 0；
- 依赖锁与 CycloneDX SBOM 保持；
- 企业模板/真实文档样本回归通过。

## 已知边界

- PPT 形状仍不能拖拽/旋转/层级编辑；
- 母版是全局字体/背景简化版；
- PDF 证书签名/时间戳/OCR/Office 转换未集成；
- Word 加密未实现；
- Excel 公式导入/导出仍以结果为主；
- 安装包未签名。

## 未验证项（重要）

- **未做 Windows 10/11 干净机安装验收**；
- **Windows 11 未验证**；
- 安装包**未签名**，SmartScreen 会提示未知发布者。

## 产物与 SHA-256

| 产物 | 大小 | SHA-256 |
|---|---:|---|
| `BeeOffice-v5.8.5-windows.zip` | 221,007,770 B | `7083E9D155A75CADE60812C64833EEDC4161D55962ADCC703C1F04C8805DA510` |
| `BeeOffice-Setup-v5.8.5.exe` | 152,262,450 B | `85347965D1AFCC97E90C3F46EE5EBF889E8881E7054665AB3A1BDCB7FF4CFEA4` |
