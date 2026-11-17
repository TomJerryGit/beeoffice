# BeeOffice v5.7.0 Beta 本地验收记录

日期：2026-11-17
状态：Beta / Unsigned
Release：https://github.com/TomJerryGit/beeoffice/releases/tag/v5.7.0

## 验证

```text
全量测试：1621 passed
安全扫描：高危 0
release_check.py：通过
ZIP testzip：OK
打包 exe offscreen：12 秒存活
安装器：Inno Setup 编译成功，NotSigned
```

## 产物

| 产物 | 大小 | SHA-256 |
|---|---:|---|
| `BeeOffice-v5.7.0-windows.zip` | 220,967,931 B | `04DE21281A413577AAF7E4D21AA52F9F37C23B8B93C462EED907448AC7BBFA0B` |
| `BeeOffice-Setup-v5.7.0.exe` | 152,228,490 B | `FFA3D58A2D8CD04238349FC021910451653C9B66886B67F4941F05A95CB42617` |

## 限制

- 未签名
- 未做 Win10/11 干净机验收
- Win11 未验证
- 画布覆盖不持久化
