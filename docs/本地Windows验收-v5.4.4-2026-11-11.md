# BeeOffice v5.4.4 候选包本地验收（2026-11-11）

## 验收范围（已调整）

- **Windows 10/11 干净机验收：决定不做。**
  原因：本机仅有 8 GB 内存、VMware Workstation 14，且无 Win10 ISO；Win11 还需要 TPM/Secure Boot。继续搭干净 VM 的成本与收益不匹配。
- 本机 Windows 10 冒烟和打包产物启动冒烟仍然有效，但**不等于干净机验收**。
- 发布说明不得写“Win10 已验证”；只能写“本机 Windows 10 冒烟通过，未做干净机验收”。

## 风险接受决定（2026-11-11）

用户已明确选择：**接受“仅本机冒烟、无干净机验收”的风险**，并允许在此前提下继续发布评估。

接受范围：

- 不执行 Windows 10/11 干净机安装/启动验收；
- 不验证干净系统缺少 VC++/补丁/运行库时的行为；
- 不验证未签名安装包在企业策略/SmartScreen 下的完整拦截行为；
- 不验证 Windows 11 的 TPM/Secure Boot 与兼容性；
- 发布说明必须披露：**未签名、未做干净机验收、Win11 未验证**。

此决定是**风险接受**，不是“验收通过”；不得在发布说明中写“干净机通过”。

## 构建产物

| 产物 | 大小 | SHA-256 |
|---|---:|---|
| `BeeOffice-v5.4.4-windows.zip` | 220,889,336 B | `D568C4B797B90C2550F8436177D1B45D865EFB84D737A072D2A867CED469F0C6` |
| `BeeOffice-Setup-v5.4.4.exe` | 152,138,541 B | `3975A02AA930FE95E8D4823614896F62D7AA902FEAD65471D81BED1B632CC68F` |

- 版本：**5.4.4**
- Python：3.11 / PySide6 6.6
- 构建时间：2026-11-12
- 源码提交：`3a85b61`（含 formula_engine 裸 eval / build_release exec 安全修复）
- 安装包编译器：Inno Setup 6（ISCC `/DMyAppVersion=5.4.4`）

## 构建命令

```powershell
python build.py
python tools/build_installer.py --skip-build
# ZIP：将 dist/BeeOffice 以顶层目录 BeeOffice/ 打包为 BeeOffice-v5.4.4-windows.zip
```

## 冒烟结果

- `pytest tests`：**1540 passed**
- 全仓覆盖率：**66.54%**；核心模块：**12/12 = 100%**
- 高对比度 AST 审计：**0 文件 / 0 处**
- 安全扫描（`tools/security_scan.py`）：**高危 0 条**（2 条 guarded eval）
- ZIP 完整性：`testzip()` **OK**，3050 个条目
- 打包后 `dist/BeeOffice/BeeOffice.exe` 在 offscreen 环境启动，12 秒进程存活，随后主动终止：**通过**
- 安装器由 Inno Setup 6 编译成功；**未执行安装器静默安装测试**

## 发布记录

- GitHub Release：https://github.com/TomJerryGit/beeoffice/releases/tag/v5.4.4
- 发布时间：2026-11-12
- 发布资产：ZIP、安装包、两个 SHA-256 文件

## 本次重建说明

旧候选包构建于安全修复之前，已作废；2026-11-12 从提交 `3a85b61` 重建 ZIP 与安装器，并重新计算 SHA-256。

## 限制

- 安装包**未签名**，Windows SmartScreen 会提示未知发布者。
- **未做 Windows 10/11 干净机安装验收**；当前仅本机 Windows 10 和打包产物启动冒烟。
- Win10 干净机验收计划已取消；`docs/win10-clean-acceptance/` 仅保留为将来参考，不代表已执行。
- Win11 未验证。
- Win7 安装器外壳可运行，但应用本体缺 Python DLL，不作为支持平台。

## 遗留风险

- 干净系统缺少 VC++ 运行库、Windows 更新补丁时的启动/安装问题未验证。
- 安装包未签名，SmartScreen/企业策略拦截行为只在开发机验证。
- Win11 的 TPM/Secure Boot、较新补丁兼容性完全未验证。
- 发布前必须由用户确认接受上述风险；不得把本记录描述为“干净机通过”。
