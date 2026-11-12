# BeeOffice v5.4.5

发布日期：2026-11-12  
发布状态：**Beta / Unsigned**（未签名；未做干净机验收；Win11 未验证）

## 热修复内容

- 修复 `RichTextEditor._split_cell` 调用不存在的 `colSpan()` 导致的崩溃；
- 正确使用 PySide6 `QTextTableCell.columnSpan()`；
- 新增表格插入/合并/拆分/快捷键/右键菜单回归测试。

## 验证范围

- 全量测试 **1550 passed**；
- 核心模块覆盖率 **12/12 = 100%**；
- 全仓覆盖率约 **66.5%**；
- 安全扫描：高危 **0** 条（2 条 guarded eval）；
- 本机 Windows 10 冒烟通过；
- 打包后 `BeeOffice.exe` 在 offscreen 环境启动，12 秒进程存活；
- ZIP `testzip()` 完整性通过；
- 安装器由 Inno Setup 6 编译成功。

## 未验证项（重要）

- **未做 Windows 10/11 干净机安装验收**；
- 未验证干净系统缺少 VC++/补丁/运行库时的行为；
- **Windows 11 未验证**；
- 安装包**未签名**，SmartScreen 会提示未知发布者；
- 未执行安装器静默安装测试。

> 本版本只能描述为“本机 Windows 10 冒烟通过，未做干净机验收”，不得写成“Win10/Win11 已验证”或“干净机通过”。

## 系统要求

- Windows 10 x64
- Windows 11：未验证

## 产物与 SHA-256

| 产物 | 大小 | SHA-256 |
|---|---:|---|
| `BeeOffice-v5.4.5-windows.zip` | 220,889,130 B | `EE4667E30F9A4E4361A09303D6748CDF2B9958541A7F7B7C54387A5A03CF6E78` |
| `BeeOffice-Setup-v5.4.5.exe` | 152,149,938 B | `03CECA2B8ADB713E49E24BAE7B737BA636428ABAB70082CBDCAB4E06AFA1822A` |

```powershell
Get-FileHash .\BeeOffice-Setup-v5.4.5.exe -Algorithm SHA256
Get-FileHash .\BeeOffice-v5.4.5-windows.zip -Algorithm SHA256
```

## 安装

1. 下载 `BeeOffice-Setup-v5.4.5.exe`；
2. 校验 SHA-256；
3. 运行安装器；SmartScreen 提示时选择“更多信息 → 仍要运行”；
4. 安装到当前用户目录，无需管理员权限。

## 已知风险

- 未签名；
- 无干净机验收；
- 无 Win11 验证；
- 干净系统缺少运行库时的启动问题未覆盖。
