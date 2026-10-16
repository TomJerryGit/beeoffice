# tests/fidelity/test_packaging.py
"""
打包链回归：R1（数据文件必须进包且路径解析正确）+ R5（发布脚本路径正确）。

## R1：打包版拼写白名单静默失效
`beeoffice.spec` 的 `datas` 原先只有 `locales` / `resources`，**没有 `beeoffice/data`**；
而 `spellcheck.tech_words_path()` 用的是
`Path(__file__).resolve().parents[1] / "data" / ...` ——
**完全没走仓库里已有的冻结感知助手** `utils.get_resource_path()`（用 `sys._MEIPASS`）。
两层叠加的结果：**打包版的拼写检查技术词白名单静默失效**
（技术文档"误报变多"，用户不知道是打包漏了数据）。

## R5：发布脚本一跑就报"未找到 spec"
`beeoffice/build_release.py` 里 `root = Path(__file__).parent`
（= `beeoffice/`）→ 去找 `beeoffice/beeoffice.spec`（不存在）。
而 spec / dist / build 都在**仓库根**。`get_version()` 同样找错目录。
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


# ==================== R1-a：spec 必须打包 data 目录 ====================

def test_spec_bundles_data_directory():
    """
    **R1 的回归**：`beeoffice.spec` 必须声明打包 `beeoffice/data`。

    这条测试直接读 spec 源码断言 —— 它才拦得住"将来有人删了这一行"
    （本轮就是漏了这一行，实际运行时代码却会去加载它）。
    """
    spec = (ROOT / "beeoffice.spec").read_text(encoding="utf-8")
    assert "beeoffice/data" in spec, (
        "spec 里没有打包 beeoffice/data —— 打包版拼写检查白名单会失效"
    )
    # 数据文件本身必须存在（否则打包声明也没用）
    assert (ROOT / "beeoffice" / "data" / "tech_words.txt").is_file()


def test_tech_words_path_uses_frozen_aware_resolution():
    """源码模式下路径要正确、文件要存在。"""
    from beeoffice.plugins.spellcheck import tech_words_path

    path = tech_words_path()
    assert path.is_file(), f"技术词表路径不存在: {path}"
    assert path.name == "tech_words.txt"


def test_tech_words_path_follows_meipass_when_frozen(monkeypatch, tmp_path):
    """
    **R1 的回归**：打包运行时（`sys.frozen` + `sys._MEIPASS`）
    必须从包里读，而不是从源码相对路径读。
    """
    import importlib

    bundle = tmp_path / "bundle"
    (bundle / "beeoffice" / "data").mkdir(parents=True)
    marker = bundle / "beeoffice" / "data" / "tech_words.txt"
    marker.write_text("# 包内词表\nKubernetes\nMEIPASS_ONLY\n", encoding="utf-8")

    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "_MEIPASS", str(bundle), raising=False)

    import beeoffice.plugins.spellcheck as spellcheck

    importlib.reload(spellcheck)
    try:
        resolved = spellcheck.tech_words_path()
        assert str(bundle) in str(resolved), (
            f"打包模式下没走 _MEIPASS：{resolved}"
        )
        words = spellcheck.load_tech_words()
        assert "meipass_only" in words, "没有从包内读到词表"
    finally:
        monkeypatch.undo()
        importlib.reload(spellcheck)


def test_builtin_tech_words_load_from_source():
    """源码运行：内置词表要能读出内容（空表会让白名单形同不存在）。"""
    from beeoffice.plugins.spellcheck import load_tech_words

    words = load_tech_words()
    assert len(words) > 50, f"词表条数异常：{len(words)}"
    assert "kubernetes" in {w.lower() for w in words} or len(words) > 100


# ==================== R5：发布脚本的路径必须指向仓库根 ====================

def test_build_script_resolves_repo_root():
    """
    **R5 的回归**：脚本里的 `REPO_ROOT` 必须是仓库根
    （spec / dist / build 都在那里），而不是脚本所在目录。
    """
    import importlib.util

    script = ROOT / "beeoffice" / "build_release.py"
    spec = importlib.util.spec_from_file_location("build_release_under_test", script)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    assert Path(module.REPO_ROOT) == ROOT, (
        f"REPO_ROOT 指错了：{module.REPO_ROOT}"
    )
    # spec 文件在仓库根（脚本必须能找到它，否则一跑就报"未找到 spec"）
    assert (Path(module.REPO_ROOT) / "beeoffice.spec").is_file()


def test_get_version_reads_real_version():
    """版本号必须读得出来（原先路径错 → 恒返回 0.0.0）。"""
    import importlib.util

    script = ROOT / "beeoffice" / "build_release.py"
    spec = importlib.util.spec_from_file_location("build_release_under_test2", script)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    version = module.get_version()
    assert version and version != "0.0.0", f"读到的版本号是 {version!r}"
