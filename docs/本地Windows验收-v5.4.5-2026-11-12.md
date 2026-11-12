# BeeOffice v5.4.5 热修复候选包本地验收（2026-11-12）

## 范围

- 仅本机 Windows 10 冒烟与打包产物启动冒烟；
- **未做 Windows 10/11 干净机验收**；
- **Windows 11 未验证**；
- 用户已接受“仅本机冒烟、无干净机验收”的发布风险（见 v5.4.4 记录）。

## 构建产物

| 产物 | 大小 | SHA-256 |
|---|---:|---|
| `BeeOffice-v5.4.5-windows.zip` | 220,889,130 B | `EE4667E30F9A4E4361A09303D6748CDF2B9958541A7F7B7C54387A5A03CF6E78` |
| `BeeOffice-Setup-v5.4.5.exe` | 152,149,938 B | `03CECA2B8ADB713E49E24BAE7B737BA636428ABAB70082CBDCAB4E06AFA1822A` |

- 版本：5.4.5
- 构建日期：2026-11-12
- 安装器编译器：Inno Setup 6
- 安装器签名：NotSigned

## 验证

```text
全量测试：1550 passed
核心覆盖率：12/12 = 100%
全仓覆盖率：约 66.5%
安全扫描：高危 0 条（2 条 guarded eval）
ZIP testzip：OK
打包 exe offscreen：12 秒存活
安装器编译：成功
```

## 修复内容

- `RichTextEditor._split_cell` 使用 `columnSpan()` 替代不存在的 `colSpan()`；
- 拆分合并单元格不再抛 `AttributeError`。

## 限制

- 安装包未签名，SmartScreen 会提示未知发布者；
- 未执行安装器静默安装测试；
- 无干净机验收，Win11 未验证。
