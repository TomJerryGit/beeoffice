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
| `BeeOffice-v5.8.5-windows.zip` | 221,007,853 B | `38C38598153A1B28408AFDDDAB506617BC607BA08D7926702D97A87595754A7B` |
| `BeeOffice-Setup-v5.8.5.exe` | 152,300,749 B | `7F5496FFD600B205709EA950DFD93BB7BF9FF949C95A2011D9365E50C30B854B` |

## 限制

- 未签名
- 未做 Win10/11 干净机验收
- Win11 未验证
- PPT 形状/母版仍为基础版
