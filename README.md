# 🐝 蜜蜂办公 BeeOffice

> 百花寻觅，酿得甜蜜。

轻量、快速、实而不华的桌面办公套件，基于 PySide6 构建。

[![Python](https://img.shields.io/badge/Python-3.9+-blue.svg)](https://www.python.org/)
[![PySide6](https://img.shields.io/badge/PySide6-6.5+-green.svg)](https://doc.qt.io/qtforpython/)
[![License](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Version](https://img.shields.io/badge/Version-5.1.0-orange.svg)](CHANGELOG.md)

---

## 📖 目录

- [功能特性](#-功能特性)
- [界面预览](#-界面预览)
- [快速开始](#-快速开始)
- [使用指南](#-使用指南)
- [快捷键](#-快捷键)
- [插件系统](#-插件系统)
- [云同步](#-云同步)
- [移动端访问](#-移动端访问)
- [开发指南](#-开发指南)
- [测试](#-测试)
- [打包发布](#-打包发布)
- [常见问题](#-常见问题)
- [贡献指南](#-贡献指南)
- [许可证](#-许可证)

---

## ✨ 功能特性

### 📝 蜜写 BeeWrite

- Markdown 编辑与实时预览
- 支持表格、代码块、任务列表等扩展语法
- 目录（TOC）自动生成
- 导出 DOCX / PDF / HTML
- 从 Word 文档导入
- **图片往返保留**：富文本 ↔ Markdown 往返时图片不丢失
  - 富文本图片自动转为 `![](path)` Markdown 语法
  - Markdown 里的 `![](path)` 切回富文本时自动重新加载
  - 从 DOCX 导入时提取内嵌图片到 `<name>_media/` 目录
  - 粘贴 / 插入的图片保存到文档同目录的 `media/`
- AI 辅助写作（续写、润色、总结、关键词提取）
- 所见即所得模式：段落格式、字符底纹、多级列表、表格可视化编辑
- 批注 / 书签 / 修订模式
- 超链接 / 交叉引用 / 数学公式 / 文本框
- 页眉页脚 / 水印 / 页码 / 页面设置
- 数据变量绑定（`{{ 数据源.字段 }}` 实时替换）

### 📊 蜜算 BeeSheet

- CSV / Excel 数据导入导出
- 完整公式引擎：SUM、AVERAGE、IF、VLOOKUP、SUMIFS 等 80+ 函数
- 自然语言生成公式（如"求和A1到A10"自动生成 `=SUM(A1:A10)`）
- 图表生成：折线图、柱状图、饼图、散点图、面积图、雷达图
- 大文件分块加载（100MB+，**支持取消**）
- 数据清洗（去重、空值处理、分列）
- 数据透视表
- 条件格式（数据条 / 色阶 / 图标集）
- 公式审计（追踪引用 / 从属）
- 冻结窗格 / 筛选 / 排序 / 数据验证 / 名称管理器
- 宏录制与播放

### 🎥 蜜演 BeeShow

- 幻灯片编辑与全屏播放
- 7 种主题 + 自定义背景
- 4 种切换动画：淡入、滑入、缩放
- 演讲者视图（备注 + 下一页预览 + 进度条）
- 排练计时
- 导出 PPTX / PDF / HTML / PNG 图片序列 / GIF
- 拖拽排序幻灯片
- 激光笔 / 画笔（全屏播放时）

### 📄 PDF 批注

- 打开 PDF 进行批注、高亮、下划线、删除线、文字注释
- 支持撤销（**区分页码**）
- 保存为 `.beeanno` 文件（旁挂）或烧录到 PDF
- 多窗口管理

### ☁️ 云同步

- WebDAV 支持
- OneDrive 支持（基于 Microsoft Graph API）
- Google Drive 支持（基于 Google Drive API v3）
- 自动同步与手动同步
- 同步进度显示
- **冲突检测**：双向同步时避免覆盖新文件

### 📱 移动端访问

- 内置 HTTP 服务器，手机浏览器即可查看文档
- 响应式 Web 界面，支持文档列表与预览
- 动态端口分配，避免冲突

### 🔌 插件系统

- 动态发现与加载插件
- 插件市场：安装、卸载、启用/禁用
- 符合 `Plugin` 基类的接口规范

### 🎨 界面与体验

- 明暗双主题
- 4 种强调色（琥珀、海洋、森林、日落）
- 中英文国际化
- 命令面板（Ctrl+Shift+P）
- 标签页拖拽合并
- 未保存状态标记
- 自动保存（每 5 分钟）
- 文件监视（外部修改提示）

---

## 🖼 界面预览

> 截图待补充

---

## 🚀 快速开始

### 环境要求

- Python 3.9 或更高版本
- Windows / macOS / Linux

### 安装

```bash
# 克隆仓库
git clone https://github.com/TomJerryGit/beeoffice.git
cd beeoffice

# 安装依赖
pip install -r requirements.txt

# 启动
python -m beeoffice.main
```

## 📦 打包发布

两种包型，按是否需要「蜜演」选择：

| 版本 | 体积 | 说明 | 构建命令 |
|---|---|---|---|
| 完整版 | 605 MB | 含蜜演（内置 Chromium / WebEngine） | `python build.py` |
| 精简版 | **250 MB** | 不含蜜演，其余三个模块完整 | `$env:BEEOFFICE_LITE=1; python -m PyInstaller beeoffice.spec` |

精简版把 QtWebEngine（单个 DLL 就有 194 MB）从包体里拆了出去。
启动后日志会写明「蜜演未加载：当前为精简版（未打包 QtWebEngine）」，
插件加载器自动跳过蜜演插件，**不会崩溃、不会报错**，其余功能完全不受影响。

两种包型用的是同一份代码，差异只在打包时是否带 WebEngine。
