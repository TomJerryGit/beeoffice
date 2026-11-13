# BeeOffice v5.4.6 Beta 本地/CI 验收记录

日期：2026-11-13  
Release：https://github.com/TomJerryGit/beeoffice/releases/tag/v5.4.6  
状态：**Beta / Unsigned**

## 验证范围

- 本机 Windows 10 打包产物 offscreen 启动 12 秒；
- GitHub Actions Windows Server 安装/卸载冒烟；
- 全量测试、安全扫描、核心覆盖率、发布检查；
- **未做 Win10/11 干净机验收**；
- **Win11 未验证**。

## 产物

| 产物 | 大小 | SHA-256 |
|---|---:|---|
| `BeeOffice-v5.4.6-windows.zip` | 220,889,586 B | `262A1ADFA232F2441B4FBAF1B79015BB58F2E21338438CCD7885DDFC51934E2C` |
| `BeeOffice-Setup-v5.4.6.exe` | 152,147,914 B | `CFBDC28E40C9F17C9C385B22C4F3962D4348C1D4C9513D5C891978F3F874E31F` |

- 版本：5.4.6
- 安装器签名：NotSigned
- ZIP testzip：OK
- 打包 exe offscreen：12 秒存活

## CI

- `快速回归（语法/公式/安全）`：success
- `全量测试（含 GUI，阻塞）`：success
- `windows-install-smoke`：success
- `windows-release`（构建 + 安装器 + release_check + attestation）：success

## 限制

- 未签名；
- 无干净机验收；
- Win11 未验证；
- 未执行真实干净用户环境静默安装。
