# BeeOffice-Win10-Clean-2026 VMware 配置说明

日期：2026-11-11  
目的：在 VMware Workstation 中新建一台**干净 Windows 10**，完成 BeeOffice v5.4.4 安装/启动/核心功能验收。

> **验收范围**：仅 Windows 10 22H2 x64。Windows 11 本轮不验收，发布说明必须写“Win10 已验证；Win11 未验证”。

## 1. 宿主机现状

| 项 | 值 |
|---|---|
| 宿主系统 | Windows 10 Pro 19041 |
| 内存 | 8 GB（紧张） |
| 可用磁盘 | C: 约 50 GB；F: 约 180 GB |
| VMware | Workstation **14.1.3** |
| 虚拟化 | CPU VT 已开启 |

> VMware 14 可运行 Windows 10，但**不建议在同一宿主启用 Hyper-V / Windows Sandbox**，两者可能冲突。

## 2. 准备 ISO

1. 从微软官方下载 **Windows 10 22H2 x64 ISO**：
   - https://www.microsoft.com/software-download/windows10
2. 放到 `F:\ISO\Win10_22H2_x64.iso`。
3. 在宿主机校验：

```powershell
Get-FileHash 'F:\ISO\Win10_22H2_x64.iso' -Algorithm SHA256
```

> 以微软下载页给出的 SHA-256 为准；不要使用第三方精简版/魔改版。

## 3. 新建虚拟机

VMware Workstation → **文件 → 新建虚拟机**：

| 步骤 | 选择 |
|---|---|
| 类型 | 典型（Typical） |
| 安装源 | 安装程序光盘映像文件（ISO） |
| 客户机系统 | Microsoft Windows → Windows 10 x64 |
| 名称 | `BeeOffice-Win10-Clean-2026` |
| 位置 | `F:\VMware\BeeOffice-Win10-Clean-2026` |
| 磁盘 | 60 GB，**单文件** |
| 网络 | NAT |
| 内存 | **3072 MB** |
| CPU | **2 核** |
| 其他设备 | 删除打印机、声卡等无关设备 |

创建完成后，在 VM 设置中确认：

- 开启 3D 加速（可选）
- 关闭“与主机共享文件夹”或显式只读共享
- 不要给 VM 挂载宿主真实业务目录

## 4. 安装 Windows 10

1. 启动 VM，按向导安装 Windows 10 专业版。
2. 使用**本地账户**，不登录 Microsoft 账户。
3. 安装完成后：
   - 不安装 Python、Office、WPS、VC++ 运行库等额外软件
   - 不安装第三方杀毒/管家
   - 确认系统时间、区域正确
4. 安装 VMware Tools（可选，便于共享文件夹和分辨率）。
5. 关机后创建快照：

```text
快照名称：clean-win10-22H2
说明：仅安装 Windows 10，无 BeeOffice、无第三方软件
```

## 5. 把候选包送进 VM

推荐用 VMware 共享文件夹：

1. VM 设置 → 选项 → 共享文件夹 → 添加：
   - 主机路径：`D:\beeofficeV\_ptmp\s4\release-archive`
   - 名称：`release`
   - 只读：**是**
2. VM 内访问 `\\vmware-host\Shared Folders\release`。
3. 复制到 VM 桌面：

```text
BeeOffice-Setup-v5.4.4.exe
BeeOffice-v5.4.4-windows.zip
```

4. 在 VM 内校验安装包：

```powershell
certutil -hashfile BeeOffice-Setup-v5.4.4.exe SHA256
```

期望：

```text
AFA82FA7484990A68AE080E6C63BC13DF0A335075A455BCC77EB2741FCC00612
```

ZIP 期望：

```text
CF845A4440B8B59F458389D0F17971E7F341CA657C0203F134812B51EAE17080
```

## 6. 安装与启动

1. 运行安装包。
2. 安装包**未签名**，SmartScreen 会提示未知发布者：
   - 点击“更多信息”
   - 确认发布者/文件名后点“仍要运行”
3. 建议安装到默认目录，记录安装路径。
4. 安装完成后启动 BeeOffice，确认：
   - 进程正常启动、不闪退
   - 无 `python311.dll`、Qt 平台插件、VC++ 运行库缺失提示
   - “关于”显示版本 **5.4.4**

## 7. 重复验收

- 完成安装启动冒烟后，先关机创建快照 `installed-v5.4.4`。
- 每轮破坏性测试前回滚到 `clean-win10-22H2` 或 `installed-v5.4.4`。
- 卸载测试后回滚，不要在一台 VM 上连续做多轮安装。

## 8. 限制

- 本机 VMware 14 **不支持 Windows 11 的 TPM/Secure Boot**；Win11 验收需 VMware 17+、Hyper-V 或另一台物理机。
- 8 GB 宿主同时跑 VM 和浏览器会卡顿；验收时关闭宿主大内存程序。
- 本文只是配置说明，**不代表验收已通过**；结果必须填写验收清单。
