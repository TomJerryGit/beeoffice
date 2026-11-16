# BeeOffice v5.4.7 Beta 本地验收记录

日期：2026-11-16  
Release：https://github.com/TomJerryGit/beeoffice/releases/tag/v5.4.7  
状态：**Beta / Unsigned**

## 验证

```text
全量测试：1563 passed
安全扫描：高危 0 条
release_check.py：通过
ZIP testzip：OK
打包 exe offscreen：12 秒存活
安装器：Inno Setup 编译成功，NotSigned
```

## 产物

| 产物 | 大小 | SHA-256 |
|---|---:|---|
| `BeeOffice-v5.4.7-windows.zip` | 220,911,343 B | `B6CA9DFD5662E44CCE8DFCCC6B8F899F83088523C1B4287F578B61FE6B5070B4` |
| `BeeOffice-Setup-v5.4.7.exe` | 152,144,411 B | `DEE95D5A1B197E55FCC301B44A25AC2F027829E085AB00E9FD89D68302A9423D` |

## 新增 UI

- BeeWrite/BeeShow/BeePDF WPS Ribbon 细化
- 文档标签页隐藏主菜单和主快捷栏
- SVG 图标主题换色
- 边框/底纹图库、单边框、PDF 新标注图形

## 限制

- 未签名
- 未做 Win10/11 干净机验收
- Win11 未验证
- 未执行真实干净用户环境静默安装
