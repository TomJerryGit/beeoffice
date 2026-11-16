# BeeOffice v5.4.8 Beta 本地验收记录

日期：2026-11-16  
状态：**Beta / Unsigned**  
Release：https://github.com/TomJerryGit/beeoffice/releases/tag/v5.4.8

## 验证

```text
全量测试：1585 passed
安全扫描：高危 0
release_check.py：通过
ZIP testzip：OK
打包 exe offscreen：12 秒存活
安装器：Inno Setup 编译成功，NotSigned
```

## 产物

| 产物 | 大小 | SHA-256 |
|---|---:|---|
| `BeeOffice-v5.4.8-windows.zip` | 220,934,546 B | `075519D0D15581F7C7C2528C9484E7398BFDB3C14FE196FCEC6669F395CC086B` |
| `BeeOffice-Setup-v5.4.8.exe` | 152,185,892 B | `F3747F80BAC89D4387DFA01E0DB7337D03AEE1C62960AE93C1B09331AD8261F6` |

## 限制

- 未签名
- 未做 Win10/11 干净机验收
- Win11 未验证
- 打印缩放/按页页眉页脚未完成
