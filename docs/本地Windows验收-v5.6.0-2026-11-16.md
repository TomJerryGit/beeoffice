# BeeOffice v5.6.0 Beta 本地验收记录

日期：2026-11-16
状态：Beta / Unsigned
Release：https://github.com/TomJerryGit/beeoffice/releases/tag/v5.6.0

## 验证

```text
全量测试：1611 passed
安全扫描：高危 0
release_check.py：通过
ZIP testzip：OK
打包 exe offscreen：12 秒存活
安装器：Inno Setup 编译成功，NotSigned
```

## 产物

| 产物 | 大小 | SHA-256 |
|---|---:|---|
| `BeeOffice-v5.6.0-windows.zip` | 220,957,088 B | `B8E77A5A19CC83399EF57A528A40A345C610BA014DCF3FC463F5F5AF918E56DF` |
| `BeeOffice-Setup-v5.6.0.exe` | 152,234,686 B | `535DD2D4E058E5449673208CEB78BAE35CF463D730387898E9426232FE846D6C` |

## 限制

- 未签名
- 未做 Win10/11 干净机验收
- Win11 未验证
- 连续阅读仍为基础模式
