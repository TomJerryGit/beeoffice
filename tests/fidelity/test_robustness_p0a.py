# tests/fidelity/test_robustness_p0a.py
"""
P0-A：**稳健性止血**（报告《与 WPS 差距分析》§5 P0-A）。

这三条都是"实机跑出来的"，不是推测：

### 1. 日志目录不可写 → 启动即崩

`main.py` 的 `setup_logging()` 直接调
`logging.basicConfig(filename=...)`，**没有任何保护**。企业只读家目录、
漫游配置损坏、磁盘写满、受限账号/沙箱等情况下，异常会一路抛到 `main()` 外面，
程序在**任何界面出现之前**就退出。

实测 traceback（用正确入口 `python -m beeoffice.main` 复现）::

    PermissionError: [Errno 13] Permission denied:
    'C:\\Users\\Administrator\\.beeoffice_logs\\app.log'

### 2. 图片提取写到文档旁边 → 只读位置静默丢图

原先无条件写 `<文档同级>/<名>_media/`。文档在只读位置（光盘、网络共享、
`Program Files`、只读归档）时写入被拒，图片被**静默降级为占位文字**，
用户看到一份缺图文档，唯一线索是日志里一行 warning。

### 3. 设置保存失败会重试阻塞约 2.4 秒

日志显示三条 ERROR 同一时刻出现，期间启动被拖慢（见 test 里的验证方式）。

**测这些不需要 GUI**：直接调函数 + 故意构造不可写场景即可。
"""
import logging
import sys
from contextlib import contextmanager
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


@contextmanager
def clear_root_handlers():
    """
    清空 root logger 的 handlers，用完后恢复。

    `logging.basicConfig()` 在**已有 handler 时直接返回**，而 pytest 的日志插件
    会在 **fixture setup 之后、测试体之前**装上自己的 handler —— 所以放在
    fixture 里清是没用的（会被重新装上）。必须在**测试体内**、紧挨着调用前清。
    我第一版就是放在 fixture 里，导致"日志文件没建出来"。
    """
    root = logging.getLogger()
    saved = list(root.handlers)
    root.handlers.clear()
    try:
        yield
    finally:
        for handler in list(root.handlers):
            root.removeHandler(handler)
            try:
                handler.close()
            except Exception:  # noqa: BLE001
                pass
        root.handlers[:] = saved


# ==================== 1. 日志不可写也不能崩 ====================

def test_setup_logging_survives_unwritable_dir(tmp_path, monkeypatch):
    """
    **核心回归**：日志目录不可写时，`setup_logging()` 不能抛异常。

    用 monkeypatch 把 LOG_DIR 指到一个"必然是文件而非目录"的路径上，
    这样 `mkdir(parents=True, exist_ok=True)` 会抛 FileExistsError
    —— 与真实权限拒绝等效（都是"建不出目录"）。
    """
    from beeoffice import main as main_mod
    from beeoffice.crash_handler import CrashHandler

    blocker = tmp_path / "not_a_dir"
    blocker.write_text("我是文件，不是目录", encoding="utf-8")
    monkeypatch.setattr(CrashHandler, "LOG_DIR", blocker / "logs")

    with clear_root_handlers():
        main_mod.setup_logging()          # 不应抛异常

    assert main_mod.LOGGING_DEGRADED, "应该记录降级原因，供界面提示用户"
    assert "Error" in main_mod.LOGGING_DEGRADED or \
        "error" in main_mod.LOGGING_DEGRADED.lower()


def test_setup_logging_reports_ok_when_writable(tmp_path, monkeypatch):
    """可写时不应误报降级，且日志文件真的建出来。"""
    from beeoffice import main as main_mod
    from beeoffice.crash_handler import CrashHandler

    monkeypatch.setattr(CrashHandler, "LOG_DIR", tmp_path / "logs")

    with clear_root_handlers():
        main_mod.setup_logging()

    assert main_mod.LOGGING_DEGRADED is None
    assert (tmp_path / "logs" / "app.log").exists(), "日志文件没建出来"


def test_setup_logging_falls_back_to_stderr(tmp_path, monkeypatch):
    """
    降级后 root logger 必须仍有可用 handler（否则日志彻底静默）。

    `basicConfig` 无 filename 时加的是 **StreamHandler(stderr)**，
    所以断言 root 上存在 handler，而不是去抓 capsys
    （capsys 抓不到 logging 自己的 stderr 处理器）。
    """
    from beeoffice import main as main_mod
    from beeoffice.crash_handler import CrashHandler

    blocker = tmp_path / "f"
    blocker.write_text("x", encoding="utf-8")
    monkeypatch.setattr(CrashHandler, "LOG_DIR", blocker / "logs")

    with clear_root_handlers():
        main_mod.setup_logging()
        assert main_mod.LOGGING_DEGRADED is not None
        assert logging.getLogger().handlers, "降级后没有任何日志 handler"


# ==================== 2. 图片回退目录 ====================

def test_media_dir_uses_adjacent_when_writable(tmp_path, monkeypatch):
    """默认行为不能变：同级可写时仍用 `<名>_media/` 且链接是相对路径。"""
    from beeoffice.plugins.bee_export import _resolve_media_dir

    docx = tmp_path / "样本.docx"
    docx.write_bytes(b"x")

    media_dir, prefix = _resolve_media_dir(docx)

    assert media_dir == tmp_path / "样本_media"
    assert prefix == "样本_media/", "相对链接不能变（否则老文档链接会断）"
    assert media_dir.is_dir()


def test_media_dir_falls_back_when_adjacent_blocked(tmp_path, monkeypatch):
    """
    **核心回归**：同级位置不可写时回退到缓存目录，且链接写成绝对路径。

    构造方式：把 `<名>_media` 做成一个**文件**，`mkdir(exist_ok=True)` 会
    抛 FileExistsError（exist_ok 只忽略"已存在的目录"）—— 等效于权限拒绝。
    """
    from beeoffice.plugins import bee_export

    docx = tmp_path / "样本.docx"
    docx.write_bytes(b"x")
    blocker = tmp_path / "样本_media"
    blocker.write_text("占位文件，挡住目录创建", encoding="utf-8")

    cache = tmp_path / "cache"
    monkeypatch.setattr(bee_export, "_media_cache_root", lambda: cache)

    media_dir, prefix = bee_export._resolve_media_dir(docx)

    assert media_dir != blocker
    assert media_dir.parent == cache, f"没回退到缓存目录: {media_dir}"
    assert prefix.endswith("/") and Path(prefix.rstrip("/")) == media_dir, (
        f"回退后链接应是绝对路径: {prefix}"
    )
    assert not prefix.startswith("样本_media"), "回退后不能再写相对链接"


def test_image_extraction_writes_to_fallback(tmp_path, monkeypatch):
    """
    端到端：同级不可写时，图片真的落到回退目录，**且 Markdown 里保留图片**。

    这就是"静默丢图"的修复验证 —— 原先这种情况下图片会变成占位文字。
    """
    import io

    from docx import Document
    from PIL import Image

    from beeoffice.plugins import bee_export

    # 用 Pillow 造一张**真的**1×1 PNG（手拼字节容易造出非法 PNG，
    # python-docx 会解析失败 —— 我第一版就是这么错的）
    buffer = io.BytesIO()
    Image.new("RGB", (4, 4), (200, 30, 30)).save(buffer, format="PNG")
    png = buffer.getvalue()

    src = tmp_path / "带图.docx"
    doc = Document()
    doc.add_paragraph("正文")
    doc.add_paragraph().add_run().add_picture(io.BytesIO(png))
    doc.save(str(src))

    # 挡住同级 media 目录
    (tmp_path / "带图_media").write_text("占位", encoding="utf-8")
    cache = tmp_path / "cache"
    monkeypatch.setattr(bee_export, "_media_cache_root", lambda: cache)

    md = bee_export.import_from_docx(str(src))

    assert "![](" in md, f"图片在 Markdown 里没了（静默丢图）: {md[:300]}"
    written = list(cache.rglob("image_*"))
    assert written, "回退目录里没有图片文件"
