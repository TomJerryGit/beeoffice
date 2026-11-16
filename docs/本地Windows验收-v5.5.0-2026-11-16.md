# BeeOffice v5.5.0 Beta 本地验收记录

日期：2026-11-16
状态：Beta / Unsigned
Release：https://github.com/TomJerryGit/beeoffice/releases/tag/v5.5.0

## 验证

```text
全量测试：1598 passed
安全扫描：高危 0
release_check.py：通过
ZIP testzip：OK
打包 exe offscreen：12 秒存活
安装器：Inno Setup 编译成功，NotSigned
```

## 产物

| 产物 | 大小 | SHA-256 |
|---|---:|---|
| `BeeOffice-v5.5.0-windows.zip` | 220,945,179 B | `BD6CE7F09D893471D08C8CCF1B87206B8AB554125E95BDE9FFFF06680CB9F6C5` |
| `BeeOffice-Setup-v5.5.0.exe` | 152,208,220 B | `188F9EEB9F707B75E2C6767BD0B4D44F3484C7F947CD0CE3940D1A508BC6FA01` |

## 限制

- 未签名
- 未做 Win10/11 干净机验收
- Win11 未验证
- 脚注/题注/目录不是 Word 原生结构
