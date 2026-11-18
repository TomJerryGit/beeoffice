# 干净机验收

目标环境：Win10 22H2 / Win11 23H2，无 Python、无 WPS、无开发工具。

## 前置

- 安装包路径
- 非管理员测试账号
- 开启 Defender
- 快照/回滚点

## 执行

```powershell
powershell -ExecutionPolicy Bypass -File tools/clean_machine/validate_install.ps1 `
  -Installer "D:\BeeOffice-Setup.exe" `
  -ExpectedVersion "5.8.14"
```

## 检查项

- 静默安装成功
- 主程序启动并存活
- 新建 Word/Excel/PPT/PDF 链路可用
- 卸载成功
- 残留目录检查
- SmartScreen/Defender 记录

## 输出

`clean-machine-report.json`：OS、版本、步骤、结果、耗时。
