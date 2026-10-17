# build.py
"""
蜜蜂办公 BeeOffice 一键打包脚本
调用 PyInstaller 使用 beeoffice.spec 生成可执行文件
"""
import subprocess
import sys
import shutil
import platform
from pathlib import Path


def check_pyinstaller() -> bool:
    """检查 PyInstaller 是否已安装"""
    try:
        import PyInstaller  # noqa: F401
        return True
    except ImportError:
        return False


def clean_build_dirs(root: Path):
    """清理旧的构建目录"""
    for dir_name in ("build", "dist"):
        target = root / dir_name
        if target.exists():
            print(f"🧹 清理旧目录: {target}")
            try:
                shutil.rmtree(target)
            except Exception as e:
                print(f"⚠️ 清理 {target} 失败: {e}")


def run_pyinstaller(root: Path) -> bool:
    """
    执行 PyInstaller 打包
    :return: 是否成功
    """
    spec_file = root / "beeoffice.spec"
    if not spec_file.exists():
        print(f"❌ 未找到 spec 文件: {spec_file}")
        return False

    cmd = [
        sys.executable, "-m", "PyInstaller",
        str(spec_file),
        "--clean",
        "--noconfirm",
    ]

    print("🐝 开始打包 BeeOffice...")
    print(f"   命令: {' '.join(cmd)}")
    print()

    try:
        result = subprocess.run(cmd, cwd=str(root))
        return result.returncode == 0
    except Exception as e:
        print(f"❌ 打包过程异常: {e}")
        return False


def check_output(root: Path) -> bool:
    """检查输出文件是否生成"""
    system = platform.system()

    if system == "Windows":
        exe_path = root / "dist" / "BeeOffice" / "BeeOffice.exe"
    elif system == "Darwin":
        # macOS 可能生成 .app 或可执行文件
        exe_path = root / "dist" / "BeeOffice" / "BeeOffice"
        app_path = root / "dist" / "BeeOffice.app"
        if app_path.exists() or exe_path.exists():
            return True
    else:
        exe_path = root / "dist" / "BeeOffice" / "BeeOffice"

    if exe_path.exists():
        print(f"✅ 可执行文件已生成: {exe_path}")
        # 显示文件大小
        try:
            size_mb = exe_path.stat().st_size / (1024 * 1024)
            print(f"   文件大小: {size_mb:.1f} MB")
        except Exception:
            pass
        return True
    else:
        print(f"❌ 未找到可执行文件，请检查 dist/ 目录")
        return False


def main():
    """主流程"""
    print("=" * 50)
    print("  🐝 蜜蜂办公 BeeOffice 打包工具")
    print("=" * 50)
    print()

    # 项目根目录
    root = Path(__file__).parent.resolve()
    print(f"📁 项目目录: {root}")
    print(f"🖥️  运行平台: {platform.system()} {platform.release()}")
    print(f"🐍 Python 版本: {sys.version.split()[0]}")
    print()

    # 检查 PyInstaller
    if not check_pyinstaller():
        print("❌ 未安装 PyInstaller")
        print("   请执行: pip install pyinstaller")
        sys.exit(1)
    print("✅ PyInstaller 已安装")
    print()

    # 清理旧构建
    clean_build_dirs(root)
    print()

    # 执行打包
    success = run_pyinstaller(root)
    print()

    if not success:
        print("❌ 打包失败，请检查上方的错误信息")
        sys.exit(1)

    # 检查输出
    if not check_output(root):
        print("❌ 打包完成但未找到输出文件")
        sys.exit(1)

    # 产物瘦身：删掉运行期不需要的 Qt 资源（DevTools / 自带翻译）
    # 失败不影响打包结果，只是包体会大一些。
    try:
        sys.path.insert(0, str(Path(__file__).parent / "tools"))
        from slim_dist import slim as _slim
        removed = _slim(root / "dist" / "BeeOffice")
        print(f"🧹 瘦身：已清理 {removed / 1024 / 1024:.1f} MB 无用资源")
    except Exception as e:
        print(f"⚠️  瘦身步骤跳过（{e}）")

    # 完成
    print()
    print("=" * 50)
    print("  ✅ 打包完成！")
    print("=" * 50)
    print()
    print(f"📦 输出目录: {root / 'dist' / 'BeeOffice'}")
    print()
    print("提示：")
    print("  - Windows: 双击 BeeOffice.exe 运行")
    print("  - macOS:   双击 BeeOffice.app 运行")
    print("  - Linux:   终端执行 ./BeeOffice")
    print()


if __name__ == "__main__":
    main()