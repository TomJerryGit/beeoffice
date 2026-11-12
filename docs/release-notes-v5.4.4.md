# BeeOffice v5.4.4

发布日期：2026-11-12

## 重点更新

- **安全加固**
  - 旧 `formula_engine._eval_math` 的裸 `eval` 改为 AST 白名单，拒绝属性/下标等逃逸语法；
  - `build_release.py` 移除 `exec`，改为正则读取版本号；
  - 新增 `tools/security_scan.py`：只扫描裸 `exec/eval`、`pickle.load/loads`、`shell=True`，排除 `tests/dist/build/release-archive`。
- **测试与覆盖率**
  - 全量测试 **1540 passed**；
  - 核心模块覆盖率 **12/12 = 100%**；
  - 全仓覆盖率 **66.54%**（GUI 不设 100% 目标）。

## 验证范围

- 本机 **Windows 10** 冒烟通过；
- 打包后 `BeeOffice.exe` 在 offscreen 环境启动，12 秒进程存活；
- ZIP `testzip()` 完整性通过；
- 安装器由 Inno Setup 6 编译成功；
- 安全扫描：高危 **0** 条（2 条 guarded eval）。

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
| `BeeOffice-v5.4.4-windows.zip` | 220,889,336 B | `D568C4B797B90C2550F8436177D1B45D865EFB84D737A072D2A867CED469F0C6` |
| `BeeOffice-Setup-v5.4.4.exe` | 152,138,541 B | `3975A02AA930FE95E8D4823614896F62D7AA902FEAD65471D81BED1B632CC68F` |

```powershell
Get-FileHash .\BeeOffice-Setup-v5.4.4.exe -Algorithm SHA256
Get-FileHash .\BeeOffice-v5.4.4-windows.zip -Algorithm SHA256
```

## 安装

1. 下载 `BeeOffice-Setup-v5.4.4.exe`；
2. 校验 SHA-256；
3. 运行安装器；SmartScreen 提示时选择“更多信息 → 仍要运行”；
4. 安装到当前用户目录，无需管理员权限。

## 已知风险

- 未签名；
- 无干净机验收；
- 无 Win11 验证；
- 干净系统缺少运行库时的启动问题未覆盖。
