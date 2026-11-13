# BeeOffice v5.4.6

发布日期：2026-11-13  
发布状态：**Beta / Unsigned**（未签名；未做干净机验收；Win11 未验证）

## 本版本内容

- 包含 v5.4.5 的 `_split_cell` 合并单元格崩溃修复；
- 修复英文 Windows locale 下中文日期 `strftime("%Y年...")` 崩溃；
- 增加 `pandas<3.0`、`pypdf<7.0` 版本上限，稳定 CI 基线；
- M1A 零成本发布门禁：
  - 全量测试阻塞；
  - 安全扫描接入 CI；
  - 核心 100% 覆盖率门槛；
  - `tools/release_check.py`；
  - Release workflow artifact attestation；
  - main 分支保护（快速回归 + 全量测试必过）。

## 验证

- 全量测试通过（GitHub Actions `全量测试（含 GUI，阻塞）`）；
- 安全扫描：高危 **0** 条（2 条 guarded eval）；
- 安装/卸载 Windows Server 冒烟通过；
- Release workflow 构建 + 安装器 + release_check + attestation 通过；
- ZIP `testzip` 通过；
- 打包 exe 在 offscreen 环境存活 12 秒。

## 未验证项（重要）

- **未做 Windows 10/11 干净机安装验收**；
- **Windows 11 未验证**；
- 安装包**未签名**，SmartScreen 会提示未知发布者；
- 未执行静默安装到真实干净用户环境。

> 只能描述为“本机/Server 冒烟通过，未做干净机验收”。

## 产物与 SHA-256

| 产物 | 大小 | SHA-256 |
|---|---:|---|
| `BeeOffice-v5.4.6-windows.zip` | 220,889,586 B | `262A1ADFA232F2441B4FBAF1B79015BB58F2E21338438CCD7885DDFC51934E2C` |
| `BeeOffice-Setup-v5.4.6.exe` | 152,147,914 B | `CFBDC28E40C9F17C9C385B22C4F3962D4348C1D4C9513D5C891978F3F874E31F` |

## 安装

1. 下载安装包并校验 SHA-256；
2. 运行安装器；SmartScreen 提示时选择“更多信息 → 仍要运行”；
3. 安装到当前用户目录，无需管理员权限。
