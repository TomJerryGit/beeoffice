# -*- coding: utf-8 -*-
"""
敏感字段加密存储（P1-39）

缺陷：
    API Key / WebDAV 密码只做 Base64——**编码不是加密**，
    打开 settings.json 一眼就能还原。

修复：
    Windows 用 DPAPI（CryptProtectData），密钥由系统按当前用户账户派生，
    程序不保存任何密钥；其它平台回退 Base64 并带 `b64:` 前缀明确标注。
"""
import base64

import pytest

from beeoffice import secret_store


def test_roundtrip_recovers_plaintext():
    plain = "sk-测试密钥-1234567890"
    token = secret_store.protect(plain)
    assert token != plain
    assert secret_store.unprotect(token) == plain


def test_ciphertext_does_not_contain_plaintext():
    """密文里不得出现明文，也不得等于 Base64（否则等于没加密）。"""
    plain = "my-secret-password"
    token = secret_store.protect(plain)
    assert plain not in token
    naive = base64.b64encode(plain.encode()).decode()
    assert token != naive
    assert not token.endswith(naive)


def test_legacy_base64_still_decodes():
    """历史配置是纯 Base64（无前缀），必须还能读出来。"""
    legacy = base64.b64encode("旧密码".encode("utf-8")).decode("ascii")
    assert secret_store.unprotect(legacy) == "旧密码"


def test_empty_values_pass_through():
    assert secret_store.protect("") == ""
    assert secret_store.unprotect("") == ""


def test_b64_prefix_roundtrip():
    token = secret_store.PREFIX_B64 + base64.b64encode(
        "回退".encode("utf-8")
    ).decode("ascii")
    assert secret_store.unprotect(token) == "回退"


@pytest.mark.skipif(
    not secret_store.is_encrypted(), reason="仅 Windows 有 DPAPI"
)
def test_windows_uses_dpapi_prefix():
    token = secret_store.protect("abc")
    assert token.startswith(secret_store.PREFIX_DPAPI)


def test_settings_roundtrip_uses_new_codec(tmp_path):
    """Settings 存取一轮后，配置文件里不应出现明文密码。"""
    from beeoffice.settings import AppSettings

    path = tmp_path / "settings.json"

    s = AppSettings()
    s.path = path
    s.ai_api_key = "超级机密-key"
    s.save()

    raw = path.read_text(encoding="utf-8")
    assert "超级机密-key" not in raw, "配置文件里不应出现明文密钥"

    reloaded = AppSettings()
    reloaded.path = path
    reloaded.load()
    assert reloaded.ai_api_key == "超级机密-key"
