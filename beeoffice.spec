# -*- mode: python ; coding: utf-8 -*-
"""
BeeOffice PyInstaller 打包配置（参考模板）

构建命令：
    python build_release.py         # 推荐（自动清理 + 校验和）
    # 或直接：
    pyinstaller beeoffice.spec --clean --noconfirm

产物结构（onedir 模式）：
    dist/BeeOffice/
    ├── BeeOffice.exe              # Windows 可执行文件
    ├── _internal/                 # Python 运行时与依赖
    └── ...

说明：
  - 本 spec 基于 Python 3.11 + PyInstaller 6.x + PySide6 6.5+
  - 若使用更低版本 Python（3.9/3.10），请核对 PyInstaller 参数兼容性
  - 打包耗时约 3~10 分钟，视机器性能而定
"""
import sys
from pathlib import Path
from PyInstaller.utils.hooks import collect_submodules


# ==================== 项目根目录 ====================
# SPECPATH 由 PyInstaller 注入，指向 spec 文件所在目录
# 若单独运行 Python 解析（非 PyInstaller 环境），回退到 cwd
try:
    PROJECT_ROOT = Path(SPECPATH)
except NameError:
    PROJECT_ROOT = Path.cwd()

print(f"🐝 项目根目录: {PROJECT_ROOT}")


# ==================== 数据文件 ====================
datas = []

# 语言包（beeoffice/locales/*.json）
locales_dir = PROJECT_ROOT / "beeoffice" / "locales"
if locales_dir.exists():
    datas.append((str(locales_dir), "beeoffice/locales"))
    print(f"   + locales:   {locales_dir}")
else:
    print(f"   ⚠ locales 不存在: {locales_dir}")

# 资源目录（beeoffice/resources/*）
resources_dir = PROJECT_ROOT / "beeoffice" / "resources"
if resources_dir.exists():
    datas.append((str(resources_dir), "beeoffice/resources"))
    print(f"   + resources: {resources_dir}")

# 数据目录（beeoffice/data/*，含拼写检查的技术词白名单 tech_words.txt）
# ⚠️ 这是生产能力评估 R1：原先**漏了这个目录**，而
# `spellcheck.tech_words_path()` 会加载 `beeoffice/data/tech_words.txt`
# → 打包版的拼写检查技术词白名单静默失效（技术文档"误报变多"）。
# 现在既补打包声明，也让 `tech_words_path()` 走冻结感知的路径解析。
data_dir = PROJECT_ROOT / "beeoffice" / "data"
if data_dir.exists():
    datas.append((str(data_dir), "beeoffice/data"))
    print(f"   + data:      {data_dir}")
else:
    print(f"   ⚠ data 不存在: {data_dir}")

# 图标（若有）
for icon_name in ("icon.ico", "icon.icns", "icon.png"):
    icon_path = resources_dir / icon_name
    if icon_path.exists():
        datas.append((str(icon_path), "beeoffice/resources"))
        print(f"   + icon:      {icon_path}")


# ==================== 隐藏导入 ====================
hiddenimports = [
    # PySide6 WebEngine（蜜演 beeshow.py 使用 QWebEngineView）
    "PySide6.QtWebEngineWidgets",
    "PySide6.QtWebEngineCore",
    "PySide6.QtWebEngine",
    # PySide6 打印支持（蜜写打印预览）
    "PySide6.QtPrintSupport",
    # PySide6 SVG（图表导出可能使用）
    "PySide6.QtSvg",
    "PySide6.QtSvgWidgets",
    # 云存储 SDK（延迟导入，静态分析可能漏掉）
    "webdav3.client",
    "requests",
    # matplotlib Agg 后端（蜜写公式渲染、蜜算图表）
    "matplotlib.backends.backend_agg",
    # 大 xlsx 快速读值引擎（beesheet_workbook 延迟导入；PyInstaller 静态分析漏掉）
    "python_calamine",
]

# 自动收集插件包下所有子模块
# 防止 plugin_manager 动态 import 时被 PyInstaller 静态分析遗漏
try:
    plugin_submodules = collect_submodules("beeoffice.plugins")
    hiddenimports += plugin_submodules
    print(f"   + plugins:   {len(plugin_submodules)} 个子模块")
except Exception as e:
    print(f"   ⚠ 收集插件子模块失败: {e}")

# 云存储适配器
try:
    cloud_sync_submodules = collect_submodules("beeoffice.cloud_sync")
    hiddenimports += cloud_sync_submodules
    print(f"   + cloud_sync:{len(cloud_sync_submodules)} 个子模块")
except Exception as e:
    print(f"   ⚠ 收集云存储子模块失败: {e}")


# ==================== 排除（减小体积） ====================
excludes = [
    # 测试相关
    "pytest",
    "pytest_qt",
    "pytest_cov",
    "_pytest",
    # 开发工具
    "black",
    "ruff",
    "mypy",
    "pyinstaller",
    # GUI 库（只保留 PySide6）
    "PyQt5",
    "PyQt6",
    "PySide2",
    "tkinter",
    # 科学计算中未使用的
    "IPython",
    "jupyter",
    "notebook",
    "nbformat",
    # matplotlib 的非 Qt 后端
    "matplotlib.backends.backend_tkagg",
    "matplotlib.backends.backend_wx",
    "matplotlib.backends.backend_wxagg",
    "matplotlib.backends.backend_qt5",
    "matplotlib.backends.backend_qt5agg",
]


# ==================== Analysis ====================
a = Analysis(
    [str(PROJECT_ROOT / "beeoffice" / "main.py")],
    pathex=[str(PROJECT_ROOT)],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=excludes,
    noarchive=False,
)


# ==================== PYZ ====================
pyz = PYZ(a.pure)


# ==================== EXE ====================
# 查找图标（若存在）
_icon_path = None
for name in ("icon.ico", "icon.icns"):
    candidate = resources_dir / name
    if candidate.exists():
        _icon_path = str(candidate)
        break

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="BeeOffice",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,                # 隐藏控制台窗口
    disable_windowed_traceback=False,
    argv_emulation=False,         # macOS 用；Windows 下无影响
    target_arch=None,
    codesign_identity=None,       # macOS 签名用
    entitlements_file=None,       # macOS 权限用
    icon=_icon_path,
)


# ==================== COLLECT ====================
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="BeeOffice",
)