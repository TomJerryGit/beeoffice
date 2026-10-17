# -*- coding: utf-8 -*-
"""
打包产物瘦身：删除运行期不需要、但 PyInstaller 会照搬的大文件。

当前处理：
    PySide6/resources/*devtools*   —— QtWebEngine 的 DevTools 前端资源
        实测：qtwebengine_devtools_resources.debug.pak 72.3 MB
              qtwebengine_devtools_resources.pak       11.1 MB
        只有打开 Chromium 开发者工具时才会用到，删除后不影响渲染与导出。

用法：
    python tools/slim_dist.py                 # 默认处理 dist/BeeOffice
    python tools/slim_dist.py <产物目录>

退出码：
    0 成功（无论是否真的删了东西）
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# (glob, 说明)
PATTERNS = [
    ("**/PySide6/resources/*devtools*",
     "QtWebEngine DevTools 资源（不影响渲染/导出）"),
    # 项目用自己的 JSON 语言包（beeoffice/locales），全程没有 QTranslator，
    # 因此 Qt 自带的 53 MB .qm 翻译文件是纯死重。
    ("**/PySide6/translations/*.qm",
     "Qt 自带翻译（项目未使用 QTranslator）"),
]


def human(n: int) -> str:
    return f"{n / 1024 / 1024:.1f} MB"


def slim(dist_dir: Path) -> int:
    removed = 0
    for pattern, desc in PATTERNS:
        for f in dist_dir.glob(pattern):
            try:
                size = f.stat().st_size
                f.unlink()
                removed += size
                print(f"  - {f.name}  ({human(size)})   {desc}")
            except OSError as e:
                print(f"  ! 删除失败 {f}: {e}")
    return removed


def main(argv):
    dist = Path(argv[0]) if argv else ROOT / "dist" / "BeeOffice"
    if not dist.exists():
        print(f"产物目录不存在: {dist}")
        print("请先执行打包：python build.py 或 pyinstaller beeoffice.spec")
        return 1

    before = sum(f.stat().st_size for f in dist.rglob("*") if f.is_file())
    print(f"瘦身前: {human(before)}  目录: {dist}")

    removed = slim(dist)

    after = sum(f.stat().st_size for f in dist.rglob("*") if f.is_file())
    print(f"\n已删除: {human(removed)}")
    print(f"瘦身后: {human(after)}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
