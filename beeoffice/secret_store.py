# -*- coding: utf-8 -*-
"""
敏感字段的本地加密存储（P1-39）

问题：
    设置里的 API Key、WebDAV 密码等原来只做 Base64。
    Base64 是**编码不是加密**，任何人打开 settings.json 一眼就能还原。

方案：
    Windows 上用 DPAPI（`CryptProtectData`）。密钥由操作系统按**当前用户账户**
    派生并保管，程序里不保存任何密钥——拷走配置文件到别的账户也解不开。
    其它平台没有等价的原生设施，回退到 Base64，但会带 `b64:` 前缀明确标注
    （不假装安全），也不会让旧数据读不出来。

兼容：
    · `dpapi:` 前缀 → DPAPI 密文
    · `b64:`   前缀 → 回退方案
    · 无前缀        → 历史数据（纯 Base64），仍能读
"""
import base64
import ctypes
import logging
import sys
from ctypes import wintypes

_IS_WINDOWS = sys.platform == "win32"

PREFIX_DPAPI = "dpapi:"
PREFIX_B64 = "b64:"

_CRYPTPROTECT_UI_FORBIDDEN = 0x01


class _Blob(ctypes.Structure):
    _fields_ = [
        ("cbData", wintypes.DWORD),
        ("pbData", ctypes.POINTER(ctypes.c_char)),
    ]


def _make_blob(data: bytes):
    """构造 DATA_BLOB；必须同时返回 buffer，否则它会被 GC 回收。"""
    buf = ctypes.create_string_buffer(data, len(data))
    blob = _Blob(len(data), ctypes.cast(buf, ctypes.POINTER(ctypes.c_char)))
    return blob, buf


def _take_blob(blob: "_Blob") -> bytes:
    try:
        return ctypes.string_at(blob.pbData, blob.cbData)
    finally:
        try:
            ctypes.windll.kernel32.LocalFree(blob.pbData)
        except Exception:
            pass


def _dpapi(data: bytes, protect: bool) -> bytes:
    crypt32 = ctypes.windll.crypt32
    fn = crypt32.CryptProtectData if protect else crypt32.CryptUnprotectData
    fn.argtypes = [
        ctypes.POINTER(_Blob), wintypes.LPCWSTR, ctypes.POINTER(_Blob),
        ctypes.c_void_p, ctypes.c_void_p, wintypes.DWORD,
        ctypes.POINTER(_Blob),
    ]
    fn.restype = wintypes.BOOL

    in_blob, _buf = _make_blob(data)
    out_blob = _Blob()
    if not fn(ctypes.byref(in_blob), None, None, None, None,
              _CRYPTPROTECT_UI_FORBIDDEN, ctypes.byref(out_blob)):
        raise OSError(f"DPAPI 调用失败（错误码 {ctypes.GetLastError()}）")
    return _take_blob(out_blob)


def is_encrypted() -> bool:
    """当前平台是否真的做了加密（而不只是编码）。"""
    return _IS_WINDOWS


def protect(text: str) -> str:
    """加密（Windows）或编码（其它平台）一个敏感字段。"""
    if not text:
        return text
    if _IS_WINDOWS:
        try:
            cipher = _dpapi(text.encode("utf-8"), protect=True)
            return PREFIX_DPAPI + base64.b64encode(cipher).decode("ascii")
        except Exception as e:
            logging.warning(f"DPAPI 加密失败，回退 Base64: {e}")
    return PREFIX_B64 + base64.b64encode(text.encode("utf-8")).decode("ascii")


def unprotect(token: str) -> str:
    """还原一个敏感字段，兼容历史数据。"""
    if not token:
        return token

    if token.startswith(PREFIX_DPAPI):
        if not _IS_WINDOWS:
            logging.warning("配置文件由 Windows DPAPI 加密，当前平台无法解密")
            return ""
        try:
            raw = base64.b64decode(token[len(PREFIX_DPAPI):])
            return _dpapi(raw, protect=False).decode("utf-8", "replace")
        except Exception as e:
            logging.error(f"DPAPI 解密失败: {e}")
            return ""

    if token.startswith(PREFIX_B64):
        try:
            return base64.b64decode(token[len(PREFIX_B64):]).decode(
                "utf-8", "replace"
            )
        except Exception:
            return ""

    # 历史数据：纯 Base64，无前缀
    try:
        return base64.b64decode(token.encode("ascii")).decode("utf-8")
    except Exception:
        return token
