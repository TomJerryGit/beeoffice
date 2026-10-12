# tests/regression/v5/test_v505_sensitive_surfaces.py
"""
优化规划 §4.2「敏感面测试」：把安全加固钉在测试里

背景
----
阶段 1 加固了几处"无鉴权暴露"的问题，但如果只改了代码、没有测试，
将来一次重构就可能悄悄退回去。本文件覆盖：

1. 移动端 HTTP 服务器**默认只监听回环**（127.0.0.1），`allow_lan=True` 才全网卡
2. 蜜演同步服务器同上（原实现固定 0.0.0.0 且无鉴权，同一 Wi-Fi 下任何人都能
   静默读取全部幻灯片内容）
3. 生产代码里**不得**出现无条件的 `"0.0.0.0"` 字面量
4. 设置文件里不出现**明文**凭据
   ⚠️ 注意：`settings.py` 用的是 base64 编码 —— **这是编码，不是加密**，
   本测试只断言"文件里看不到明文"，决不能被当作安全性证明。
5. 一处"测试掩盖生产行为"的修正：`test_mobile_api.py` 原先由**测试自己**写死
   `server.ip = "127.0.0.1"`，于是即使生产代码绑定 0.0.0.0 它也照样通过。

**未覆盖**（因为功能尚不存在，不能凭空断言）：
   插件市场的哈希校验 —— `plugin_market.py` 目前**没有**任何校验逻辑
   （只有 `build_release.py` 为发布产物算 sha256）。见规划 §3.5。
"""
import json
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]


# ==================== 1. 移动端：默认回环 ====================

def _mobile_stub(allow_lan: bool):
    """
    只测 `_bind_host()` 这一个纯逻辑，因此用 __new__ 绕过重量级构造函数
    （真实构造会找端口、建临时目录、生成首页，与绑定地址无关）。
    """
    from beeoffice.mobile import MobileServer

    srv = MobileServer.__new__(MobileServer)
    srv.allow_lan = allow_lan
    return srv


def test_mobile_default_bind_is_loopback():
    assert _mobile_stub(False)._bind_host() == "127.0.0.1", (
        "移动端默认不得绑定 0.0.0.0（无鉴权会暴露到整个局域网）"
    )


def test_mobile_lan_bind_requires_explicit_opt_in():
    assert _mobile_stub(True)._bind_host() == "0.0.0.0", (
        "allow_lan=True 时才应全网卡监听"
    )


def test_mobile_constructor_defaults_to_not_allow_lan():
    """构造函数的默认值也必须是不开放局域网（防止有人改默认值）。"""
    import inspect

    from beeoffice.mobile import MobileServer

    sig = inspect.signature(MobileServer.__init__)
    assert sig.parameters["allow_lan"].default is False


# ==================== 2. 蜜演同步服务器：默认回环 ====================

def test_sync_server_default_host_is_loopback():
    from beeoffice.plugins.beeshow_sync_server import SyncServer

    assert SyncServer().host == "127.0.0.1"


def test_sync_server_lan_host_requires_opt_in():
    from beeoffice.plugins.beeshow_sync_server import SyncServer

    assert SyncServer(allow_lan=True).host == "0.0.0.0"


def test_sync_server_host_can_be_overridden_for_tests():
    from beeoffice.plugins.beeshow_sync_server import SyncServer

    assert SyncServer(host="10.1.2.3").host == "10.1.2.3"


def test_sync_server_has_an_access_token():
    """加固后 HTTP 与 WebSocket 都要求带令牌，令牌必须存在且不可预测。"""
    from beeoffice.plugins.beeshow_sync_server import SyncServer

    srv = SyncServer()
    assert srv.token and len(srv.token) >= 16


def test_sync_server_tokens_differ_between_instances():
    from beeoffice.plugins.beeshow_sync_server import SyncServer

    assert SyncServer().token != SyncServer().token


# ==================== 3. 源码里不得有无条件的通配绑定 ====================

def test_no_unconditional_wildcard_bind_in_source():
    """
    扫描 `beeoffice/**/*.py`：出现 `"0.0.0.0"` **字符串字面量**的行，
    必须同时出现 `allow_lan`（即"显式开关"）。

    只看带引号的字面量，因此文档注释里提到的 `0.0.0.0` 不会误报。
    """
    offenders = []
    for path in (ROOT / "beeoffice").rglob("*.py"):
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            continue
        for i, line in enumerate(text.splitlines(), 1):
            if '"0.0.0.0"' in line and "allow_lan" not in line:
                offenders.append(f"{path.relative_to(ROOT)}:{i}: {line.strip()}")

    assert not offenders, (
        "发现无条件的通配绑定（必须由 allow_lan 显式开关控制）：\n"
        + "\n".join(offenders)
    )


def test_found_the_expected_opt_in_sites():
    """反向保护：确认上面那条扫描确实扫到了东西（而不是恒真）。"""
    hits = []
    for path in (ROOT / "beeoffice").rglob("*.py"):
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            continue
        for line in text.splitlines():
            if '"0.0.0.0"' in line and "allow_lan" in line:
                hits.append(str(path.relative_to(ROOT)))

    assert len(hits) >= 2, (
        f"应至少有移动端与蜜演同步两处显式开关，实际只找到 {hits}"
    )


# ==================== 4. 设置文件不得存明文凭据 ====================

def test_settings_file_has_no_plaintext_password(tmp_path):
    from beeoffice.settings import AppSettings

    path = tmp_path / "settings.json"
    secret = "SuperSecret_DoNotStore_12345"

    s = AppSettings(path=path)
    s.cloud_config["password"] = secret
    assert s.save() is True

    raw = path.read_text(encoding="utf-8")
    assert secret not in raw, (
        "设置文件里出现了明文口令（base64 是编码不是加密，但至少不应是明文）"
    )

    # 读回来必须还是原值（编码/解码往返正确）
    assert AppSettings(path=path).cloud_config.get("password") == secret


def test_settings_file_has_no_plaintext_access_token(tmp_path):
    from beeoffice.settings import AppSettings

    path = tmp_path / "settings.json"
    token = "ya29.PlainToken_ABCDEFG_98765"

    s = AppSettings(path=path)
    s.cloud_config["access_token"] = token
    assert s.save() is True

    raw = path.read_text(encoding="utf-8")
    assert token not in raw
    assert AppSettings(path=path).cloud_config.get("access_token") == token


def test_settings_save_is_valid_json(tmp_path):
    """编码后仍应是合法 JSON（不能因为编码把文件写坏）。"""
    from beeoffice.settings import AppSettings

    path = tmp_path / "settings.json"
    s = AppSettings(path=path)
    s.cloud_config["password"] = "p@ss w0rd 中文"
    s.save()

    data = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(data, dict)


# ==================== 5. 测试自身不得掩盖生产绑定行为 ====================

def test_mobile_api_test_does_not_hardcode_bind_address():
    """
    §4.2 明确点名的问题：`test_mobile_api.py` 原先由测试自己写死
    `server.ip = "127.0.0.1"`，于是生产代码即使绑定 0.0.0.0 也照样通过。

    这里断言那个文件**不再**写死 ip 赋值，而是断言生产算出来的值。
    """
    text = (ROOT / "tests" / "unit" / "test_mobile_api.py").read_text(
        encoding="utf-8"
    )
    # 只看**非注释行**：上面那条注释里为了说明问题引用了旧的赋值语句，
    # 用整段文本搜索会被自己的注释骗到（这一坑本会话已踩过三次）。
    code = "\n".join(
        line for line in text.splitlines()
        if not line.lstrip().startswith("#")
    )
    assert "server.ip =" not in code, (
        "test_mobile_api.py 又写死了 server.ip —— 会掩盖生产绑定 0.0.0.0 的问题"
    )
    assert "_bind_host()" in code, (
        "test_mobile_api.py 应断言生产代码算出的绑定地址"
    )
