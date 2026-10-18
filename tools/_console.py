# -*- coding: utf-8 -*-
"""
控制台编码兜底。

背景（2026-10-18 CI 事故）：
    GitHub Actions 的 windows runner 默认控制台编码是 cp1252，
    而我们的工具大量打印中文。`print("检查 251 个文件，失败 0 个")`
    在 cp1252 下直接抛 UnicodeEncodeError，进程以退出码 1 结束——
    CI 报"语法编译检查失败"，但代码根本没问题，是输不出来。

    同样的坑之前在 `beeoffice.spec` 上踩过一次（emoji 导致打包中断）。

用法：
    在工具入口最早处调用一次：

        from _console import enable_utf8_output
        enable_utf8_output()

说明：
    `reconfigure` 是 Python 3.7+ 的 API；对不支持的环境静默跳过，
    绝不让"修编码"本身成为新的崩溃点。
"""
import sys


def enable_utf8_output(streams=("stdout", "stderr")):
    """把标准输出/错误切到 UTF-8，编码失败时用替代字符而不是抛异常。"""
    for name in streams:
        stream = getattr(sys, name, None)
        if stream is None:
            continue
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            # 某些环境（重定向到不支持的对象）没有 reconfigure
            pass


if __name__ == "__main__":  # 便于自检
    enable_utf8_output()
    print("编码兜底已生效：中文输出测试 ✓")
