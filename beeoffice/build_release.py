# build_release.py
"""
蜜蜂办公 BeeOffice 发布包构建脚本
功能：
    1. 清理旧构建
    2. 调用 PyInstaller 打包
    3. 生成 ZIP 压缩包
    4. 输出版本信息与校验和
"""
import subprocess
import sys
import shutil
import hashlib
import platform
from pathlib import Path
from datetime import datetime


# ---------- 版本信息读取 ----------
def get_version() -> str:
    """从 beeoffice/__version__.py 读取版本号"""
    version_file = Path(__file__).parent / "beeoffice" / "__version__.py"
    if not version_file.exists():
        return "0.0.0"
    try:
        namespace = {}
        content = version_file.read_text(encoding="utf-8")
        exec(content, namespace)
        return namespace.get("__version__", "0.0.0")
    except Exception:
        return "0.0.0"


# ---------- 环境检查 ----------
def check_pyinstaller() -> bool:
    """检查 PyInstaller 是否已安装"""
    try:
        import PyInstaller  # noqa: F401
        return True
    except ImportError:
        return False


# ---------- 清理 ----------
def clean_build_dirs(root: Path):
    """清理旧的构建目录和压缩包"""
    # 清理 build 和 dist 目录
    for dir_name in ("build", "dist"):
        target = root / dir_name
        if target.exists():
            print(f"🧹 清理目录: {target}")
            try:
                shutil.rmtree(target)
            except Exception as e:
                print(f"⚠️ 清理 {target} 失败: {e}")

    # 清理旧的 ZIP 包
    for zip_file in root.glob("BeeOffice-v*.zip"):
        print(f"🧹 删除旧包: {zip_file.name}")
        try:
            zip_file.unlink()
        except Exception as e:
            print(f"⚠️ 删除 {zip_file} 失败: {e}")


# ---------- PyInstaller 打包 ----------
def run_pyinstaller(root: Path) -> bool:
    """执行 PyInstaller 打包"""
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
        print(f"❌ 打包异常: {e}")
        return False


# ---------- 生成压缩包 ----------
def create_zip(root: Path, version: str) -> Path:
    """
    将 dist/BeeOffice 打包为 ZIP
    :return: ZIP 文件路径，失败返回 None
    """
    dist_dir = root / "dist" / "BeeOffice"
    if not dist_dir.exists():
        print(f"❌ 打包目录不存在: {dist_dir}")
        return None

    system = platform.system().lower()
    if system == "windows":
        platform_tag = "windows"
    elif system == "darwin":
        platform_tag = "macos"
    else:
        platform_tag = "linux"

    zip_name = f"BeeOffice-v{version}-{platform_tag}"
    zip_path = root / zip_name

    print(f"📦 正在生成压缩包: {zip_name}.zip")
    try:
        shutil.make_archive(
            base_name=str(zip_path),
            format="zip",
            root_dir=str(dist_dir.parent),
            base_dir="BeeOffice",
        )
        final_path = Path(f"{zip_path}.zip")
        print(f"✅ 压缩包已生成: {final_path.name}")
        return final_path
    except Exception as e:
        print(f"❌ 生成压缩包失败: {e}")
        return None


# ---------- 校验和 ----------
def compute_sha256(file_path: Path) -> str:
    """计算文件的 SHA-256 校验和"""
    sha256 = hashlib.sha256()
    try:
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                sha256.update(chunk)
        return sha256.hexdigest()
    except Exception as e:
        print(f"⚠️ 计算校验和失败: {e}")
        return ""


# ---------- 显示统计信息 ----------
def print_summary(root: Path, zip_path: Path, version: str, start_time: float):
    """打印构建摘要"""
    import time
    elapsed = time.time() - start_time

    print()
    print("=" * 60)
    print("  ✅ 发布包构建完成！")
    print("=" * 60)
    print()
    print(f"📦 版本:       v{version}")
    print(f"🖥️  平台:       {platform.system()} {platform.release()}")
    print(f"🐍 Python:     {sys.version.split()[0]}")
    print(f"⏱️  耗时:       {elapsed:.1f} 秒")

    if zip_path and zip_path.exists():
        size_mb = zip_path.stat().st_size / (1024 * 1024)
        print(f"📁 压缩包:     {zip_path.name}")
        print(f"📊 大小:       {size_mb:.1f} MB")

        # SHA-256 校验和
        sha256 = compute_sha256(zip_path)
        if sha256:
            print(f"🔐 SHA-256:    {sha256[:32]}...")
            print()
            print(f"   完整校验和: {sha256}")

            # 同时写入 .sha256 文件
            sha_file = zip_path.with_suffix(".zip.sha256")
            try:
                sha_file.write_text(f"{sha256}  {zip_path.name}\n", encoding="utf-8")
                print(f"   已保存至: {sha_file.name}")
            except Exception as e:
                print(f"   ⚠️ 保存校验和失败: {e}")

    print()
    print("📌 下一步:")
    print("   1. 在干净的机器上测试可执行文件")
    print("   2. 上传到 GitHub Releases")
    print("   3. 附上压缩包和 .sha256 校验文件")
    print()


# ---------- 主流程 ----------
def main():
    """主流程"""
    import time
    start_time = time.time()

    print("=" * 60)
    print("  🐝 蜜蜂办公 BeeOffice 发布包构建工具")
    print("=" * 60)
    print()

    # 基本信息
    root = Path(__file__).parent.resolve()
    version = get_version()

    print(f"📁 项目目录:   {root}")
    print(f"📦 版本号:     v{version}")
    print(f"🖥️  运行平台:   {platform.system()} {platform.release()}")
    print(f"🐍 Python:     {sys.version.split()[0]}")
    print(f"🕐 开始时间:   {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print()

    # 检查 PyInstaller
    if not check_pyinstaller():
        print("❌ 未安装 PyInstaller")
        print("   请执行: pip install pyinstaller")
        sys.exit(1)
    print("✅ PyInstaller 已安装")
    print()

    # 清理
    clean_build_dirs(root)
    print()

    # 打包
    if not run_pyinstaller(root):
        print()
        print("❌ 打包失败")
        sys.exit(1)
    print()

    # 检查输出
    dist_dir = root / "dist" / "BeeOffice"
    if not dist_dir.exists():
        print(f"❌ 未找到输出目录: {dist_dir}")
        sys.exit(1)
    print(f"✅ 打包目录已生成: {dist_dir}")
    print()

    # 生成 ZIP
    zip_path = create_zip(root, version)
    if not zip_path:
        print()
        print("⚠️ 压缩包生成失败，但可执行文件仍然可用")
        print(f"   可执行文件位置: {dist_dir}")
        sys.exit(1)

    # 显示摘要
    print_summary(root, zip_path, version, start_time)


if __name__ == "__main__":
    main()