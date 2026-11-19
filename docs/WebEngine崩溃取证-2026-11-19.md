# WebEngine 崩溃取证

日期：2026-11-19

## 已启用

`tools/enable_wer_dumps.ps1`

为以下进程开启 WER LocalDumps（完整 dump）：

- python.exe
- BeeOffice.exe
- QtWebEngineProcess.exe

Dump 目录：

```text
D:\beeofficeV\_ptmp\analysis\crashes
```

## 已确认

- Qt 86 个测试文件逐个隔离全部通过；
- 分段全量 1693 passed；
- 一次性 `pytest tests` 仍偶发 `0x80000003`；
- 崩溃栈曾出现在 plugin_manager / Qt 事件处理附近。

## 下一步

1. 运行一次性全量，收集 dump；
2. 用 WinDbg/Visual Studio 分析调用栈；
3. 二分文件前缀定位首个状态污染；
4. 修复后要求一次性全量 5 连跑。

## 当前状态

仅完成取证环境，**根因尚未修复**。
