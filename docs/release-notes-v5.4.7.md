# BeeOffice v5.4.7

发布日期：2026-11-16  
Release：https://github.com/TomJerryGit/beeoffice/releases/tag/v5.4.7  
发布状态：**Beta / Unsigned**（未签名；未做干净机验收；Win11 未验证）

## 重点更新

### WPS 风格界面

- BeeSheet：开始 / 插入 / 数据 / 公式 / 视图 分类 Ribbon；
- BeeSheet 表格工具上下文页签，选中多格自动出现；
- 边框/底纹图库：外边框、单边框（上/下/左/右）、底纹颜色；
- BeeWrite：开始页拆为模式 / 字体 / 段落；插入页拆为列表 / 表格与对象 / 页面 / 引用与审阅；
- BeeShow：开始页拆为主题 / 编辑 / 导出 / 放映 / 工具；
- BeePDF：开始 / 标注 Ribbon，支持高亮、下划线、删除线、批注、文本框、箭头、签名、矩形、圆形、直线，并可烧录进 PDF；
- 文档标签页打开后自动隐藏主菜单和主快捷栏，扩大编辑区域；
- 自定义 SVG 图标集，亮/暗主题自动换色；
- 主窗口“文件”入口、快捷工具栏、打印/分享、快捷栏显隐与拖拽排序。

### 工程化

- 全量测试 **1563 passed**；
- 依赖锁 `requirements.lock` / `requirements-dev.lock`；
- CycloneDX SBOM：`sbom/cyclonedx-bom.json`；
- 安全扫描高危 0 条；
- CI 全量测试/安全扫描/核心覆盖率门禁；
- 安装/卸载 Windows Server 冒烟。

## 未验证项（重要）

- **未做 Windows 10/11 干净机安装验收**；
- **Windows 11 未验证**；
- 安装包**未签名**，SmartScreen 会提示未知发布者；
- 未执行真实干净用户环境静默安装。

## 产物与 SHA-256

| 产物 | 大小 | SHA-256 |
|---|---:|---|
| `BeeOffice-v5.4.7-windows.zip` | 220,911,343 B | `B6CA9DFD5662E44CCE8DFCCC6B8F899F83088523C1B4287F578B61FE6B5070B4` |
| `BeeOffice-Setup-v5.4.7.exe` | 152,144,411 B | `DEE95D5A1B197E55FCC301B44A25AC2F027829E085AB00E9FD89D68302A9423D` |

## 安装

1. 下载安装包并校验 SHA-256；
2. 运行安装器；SmartScreen 提示时选择“更多信息 → 仍要运行”；
3. 安装到当前用户目录，无需管理员权限。
