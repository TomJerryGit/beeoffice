# BeeOffice v5.8.5 Beta 本地验收记录

日期：2026-11-17
状态：Beta / Unsigned

## 验证

```text
全量测试：1644 passed
release_check.py：通过
ZIP testzip：OK
打包 exe offscreen：12 秒存活
安装器：Inno Setup 编译成功，NotSigned
```

## 产物

| 产物 | 大小 | SHA-256 |
|---|---:|---|
| `BeeOffice-v5.8.5-windows.zip` | 221,007,770 B | `7083E9D155A75CADE60812C64833EEDC4161D55962ADCC703C1F04C8805DA510` |
| `BeeOffice-Setup-v5.8.5.exe` | 152,262,450 B | `85347965D1AFCC97E90C3F46EE5EBF889E8881E7054665AB3A1BDCB7FF4CFEA4` |

## 限制

- 未签名
- 未做 Win10/11 干净机验收
- Win11 未验证
- PPT 形状/母版仍为基础版
