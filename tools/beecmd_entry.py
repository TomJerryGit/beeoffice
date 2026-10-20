# tools/beecmd_entry.py
"""
PyInstaller 入口：把 `beecmd` 打成**单文件 exe**（无 GUI、无 Python 环境也能跑）。

为什么单独一个入口文件：
* PyInstaller 需要一个"顶层脚本"作为分析起点；
* 放在 `tools/` 而不是 `beeoffice/`，避免 GUI 包意外带上打包入口；
* 真正的实现仍在 `beeoffice/beecmd.py`，本文件只做转发。
"""
import sys

from beeoffice.beecmd import main

if __name__ == "__main__":
    sys.exit(main())
