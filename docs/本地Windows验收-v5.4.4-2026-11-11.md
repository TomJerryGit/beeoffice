# BeeOffice v5.4.4 候选包本地验收（2026-11-11）

## 构建产物

| 产物 | 大小 | SHA-256 |
|---|---:|---|
| `BeeOffice-v5.4.4-windows.zip` | 225,789,134 B | `CF845A4440B8B59F458389D0F17971E7F341CA657C0203F134812B51EAE17080` |
| `BeeOffice-Setup-v5.4.4.exe` | 155,799,601 B | `AFA82FA7484990A68AE080E6C63BC13DF0A335075A455BCC77EB2741FCC00612` |

- 版本：**5.4.4**
- Python：3.11 / PySide6 6.6
- 构建时间：2026-11-11
- 安装包编译器：Inno Setup 6（ISCC `/DMyAppVersion=5.4.4`）

## 构建命令

```powershell
python beeoffice/build_release.py
ISCC.exe /DMyAppVersion=5.4.4 installer/BeeOffice.iss
```

## 冒烟结果

- `pytest tests`：**1352 passed**
- 覆盖率：**60%**
- 高对比度 AST 审计：**0 文件 / 0 处**
- 打包后 `dist/BeeOffice/BeeOffice.exe` 在 offscreen 环境启动，12 秒进程存活，随后主动终止：**通过**

## 限制

- 安装包**未签名**，Windows SmartScreen 会提示未知发布者。
- 未在 Windows 10/11 **干净虚拟机**完成安装验收；当前仅本机 Windows 10 和打包产物启动冒烟。
- Win7 安装器外壳可运行，但应用本体缺 Python DLL，不作为支持平台。
