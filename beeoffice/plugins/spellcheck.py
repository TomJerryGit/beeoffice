# beeoffice/plugins/spellcheck.py
"""
拼写检查核心模块（蜜蜂办公）

范围
----
**只做核心**：后端探测 + 词法切分 + 检查服务 + 用户词典持久化。
本模块**不 import PySide6**（红线：核心逻辑必须能在无 GUI 的测试里跑）。

后端优先级（探测失败就降级，绝不假装可用）
------------------------------------------
1. ``windows-native``：Windows 8+ 自带的 ``ISpellChecker`` COM 接口
   （CLSID ``7AB36653-1796-484B-BDFA-E74F1DB7C1DC`` /
   IID ``8E018A9D-2415-4677-BF08-794EA61F94BB``，服务器是
   ``C:\\Windows\\System32\\MsSpellCheckingFacility.dll``），用 ctypes 手工索引 vtable 调用。
   **注意它必须有英文语言包才有用**，所以这里不只看 ``IsSupported``，
   还要拿 ``hello world the computer`` 做**功能自检**：若该语言的检查器把这些
   正确英文词判成错误，就判定它"不能用于英文"，继续降级。
2. ``pyspellchecker``（``import spellchecker``）
3. ``enchant``（``import enchant``）
4. 都没有 → :class:`UnavailableBackend`，``available is False`` + 中文 ``reason``。

本机（Windows 10 19041）实测结论
--------------------------------
* 原生 COM 服务器**存在且可调用**：``CreateSpellChecker('zh-Latn-CN-x-ext')`` 成功，
  但 ``factory.SupportedLanguages`` **只有 zh-Latn-CN-x-ext 一个**，
  ``IsSupported('en-US')`` 为 FALSE、``CreateSpellChecker('en-US')`` 返回
  ``E_INVALIDARG(0x80070057)``；而 zh-Latn 那个检查器把
  ``hello/world/this/is/test`` **全部**判为错误（``Suggest('teh')`` 只给出
  ``['hehe','eu','eq','reg','hd']`` 这类垃圾）→ 不能当英文拼写检查用，
  自检会拒绝它。
* ``python -c "import spellchecker"`` / ``import enchant`` 均 ``ModuleNotFoundError``。
* 因此本机 ``detect_backend()`` 返回**不可用**后端，``check_text()`` 恒返回 ``[]``。

词法规则（:func:`tokenize_words`，只挑**拉丁字母单词**）
------------------------------------------------------
跳过：中文（含中文标点/全角符号）、代码块与行内代码、URL/邮箱、数字/小数/
千分位/百分比/版本号、Markdown 标记、驼峰与下划线标识符、缩写词（全大写）、
紧贴数字或标识符边界的片段、中文**紧邻**（无分隔）的拉丁片段、单字母词。
规则见各 ``_touches_*`` 函数；具体取值由 ``tests/fidelity/test_spellcheck.py`` 钉住。

技术词白名单
------------
中文技术文档里产品名/命令/缩写（``CentOS`` / ``yum`` / ``iptables`` / ``ens33``）极多，
英文词典一律判错 → 满屏误报。白名单把这类"词典没有、技术语境正确"的词当作已知词：
词表在数据文件 ``beeoffice/data/tech_words.txt``（一行一词，``#`` 注释），
由 :func:`load_tech_words` / :func:`get_tech_words` 惰性加载，
:class:`SpellCheckerService` 默认（``use_tech_words=True``）并入 ``_dictionary``。
它**只减少误报**：不会让任何本来正确的词变成错误。词表缺失/损坏时退化为空白名单（不抛异常）。
只有通过了英文功能自检的后端（:func:`backend_is_english_dictionary`）才会套用白名单。

约定
----
``SpellBackend.check(word) -> bool``：**True = 拼写正确**。
所有后端在内部异常时一律返回 True（宁可不报，也不制造误报）。
"""
from __future__ import annotations

import ctypes
import logging
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Iterable, Sequence

__all__ = [
    "MIN_WORD_LENGTH",
    "MAX_SUGGESTIONS",
    "Misspelling",
    "SpellBackend",
    "UnavailableBackend",
    "PySpellCheckerBackend",
    "EnchantBackend",
    "WindowsNativeSpellBackend",
    "SpellCheckerService",
    "detect_backend",
    "backend_is_english_dictionary",
    "ENGLISH_PROBE_WORDS",
    "tokenize_words",
    "load_user_dictionary",
    "save_user_dictionary",
    "DICTIONARY_HEADER",
    "TECH_WORDS_HEADER",
    "TECH_WORDS_FILE",
    "tech_words_path",
    "load_tech_words",
    "get_tech_words",
    "reset_tech_words_cache",
]

logger = logging.getLogger(__name__)

#: 短于该长度的拉丁字母片段一律不检查（`a` / `ok` / `is` 不报）
MIN_WORD_LENGTH = 3

#: 每个错词最多给几条建议
MAX_SUGGESTIONS = 5

#: pyspellchecker / enchant 默认语言
DEFAULT_LANGUAGE = "en"


# ====================================================================
# 词法：屏蔽区 + 拉丁单词
# ====================================================================

#: 汉字/假名等"词"字符：紧贴拉丁字母时说明那是夹在中文里的片段（如 使用Linux系统）
_CJK_WORD_RANGES = (
    "\u3040-\u30ff"      # 日文假名
    "\u3400-\u4dbf"      # CJK 扩展 A
    "\u4e00-\u9fff"      # CJK 基本区
    "\uf900-\ufaff"      # CJK 兼容表意
)

#: 中文标点 / 全角符号（**是分隔符**，不该让相邻的英文词被跳过，但要能截断 URL）
_CJK_PUNCT_RANGES = (
    "\u2e80-\u303f"      # CJK 部首补充 + CJK 符号和标点
    "\ufe30-\ufe4f"      # CJK 兼容形式
    "\uff00-\uffef"      # 全角字符
)

#: URL 里不该出现的字符：空白、括注、汉字、中文标点
_URL_STOP_RANGES = _CJK_WORD_RANGES + _CJK_PUNCT_RANGES

_CJK_WORD_RE = re.compile("[" + _CJK_WORD_RANGES + "]")
_LATIN_RUN_RE = re.compile(r"[A-Za-z]+")
_EMAIL_RE = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")
#: 网址（含 scheme 或 www.）；末尾不吃汉字/中文标点，避免把整句中文吞掉
_URL_RE = re.compile(
    r"""(?:[A-Za-z][A-Za-z0-9+.\-]*://|www\.)[^\s<>"'()\[\]{}""" + _URL_STOP_RANGES + r"""]*"""
)
#: 数字：整数、千分位、小数（含版本号 5.0.2 / 2021.10.20）、百分比
_NUMBER_RE = re.compile(r"[0-9][0-9,]*(?:\.[0-9]+)*%?")
#: 代码块围栏
_FENCE = "```"
_FENCE_ALT = "~~~"
#: 撇号：用于识别 don't / it's 这类缩写，避免把 don 当错词
_APOSTROPHES = "'\u2019"
#: 标识符连接符
_IDENTIFIER_JOINERS = "_"


def _fenced_code_spans(text: str) -> list[tuple[int, int]]:
    """围栏代码块（``` / ~~~）整体区间；未闭合则一直到文末。"""
    spans: list[tuple[int, int]] = []
    position = 0
    length = len(text)
    while position < length:
        candidates = [i for i in (text.find(_FENCE, position), text.find(_FENCE_ALT, position)) if i != -1]
        if not candidates:
            break
        start = min(candidates)
        marker = text[start:start + 3]
        end = text.find(marker, start + 3)
        if end == -1:
            spans.append((start, length))
            break
        spans.append((start, end + 3))
        position = end + 3
    return spans


def _inline_code_spans(text: str, blocked: Sequence[tuple[int, int]]) -> list[tuple[int, int]]:
    """行内代码（单反引号）区间；已在围栏代码块里的反引号不算。"""
    spans: list[tuple[int, int]] = []
    position = 0
    while True:
        start = text.find("`", position)
        if start == -1:
            break
        if any(low <= start < high for low, high in blocked):
            position = start + 1
            continue
        end = text.find("`", start + 1)
        if end == -1:
            break
        spans.append((start, end + 1))
        position = end + 1
    return spans


def _merge_spans(spans: Iterable[tuple[int, int]], length: int) -> list[tuple[int, int]]:
    merged: list[tuple[int, int]] = []
    for start, end in sorted(spans):
        start = max(0, start)
        end = min(length, end)
        if end <= start:
            continue
        if merged and start <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
        else:
            merged.append((start, end))
    return merged


def _ignored_spans(text: str) -> list[tuple[int, int]]:
    """所有"不当英文单词看"的区间：代码、URL、邮箱、数字。"""
    spans = _fenced_code_spans(text)
    spans += _inline_code_spans(text, spans)
    for pattern in (_URL_RE, _EMAIL_RE, _NUMBER_RE):
        spans += [match.span() for match in pattern.finditer(text)]
    return _merge_spans(spans, len(text))


def _mask_ignored(text: str) -> str:
    """把忽略区间换成空格（保持长度与下标不变）。"""
    chars = list(text)
    for start, end in _ignored_spans(text):
        for index in range(start, end):
            chars[index] = " "
    return "".join(chars)


def _is_checkable_shape(word: str) -> bool:
    """
    只检查"全小写"或"首字母大写其余小写"的词。

    这样 ``README``（缩写）、``getValue``/``CentOS``（驼峰）、``IPv4`` 之类
    编程/技术标识符不会被当英文单词报错。
    """
    if word.islower():
        return True
    return word[0].isupper() and word[1:].islower()


def _touches_identifier_or_number(text: str, start: int, end: int) -> bool:
    """紧贴数字或标识符连接符（``_``）或撇号内部 → 不是普通英文单词。"""
    previous = text[start - 1] if start > 0 else ""
    following = text[end] if end < len(text) else ""
    if previous.isdigit() or following.isdigit():
        return True
    if previous in _IDENTIFIER_JOINERS and start >= 2 and text[start - 2].isalnum():
        return True
    if following in _IDENTIFIER_JOINERS and end + 1 < len(text) and text[end + 1].isalnum():
        return True
    if previous in _APOSTROPHES and start >= 2 and text[start - 2].isalpha():
        return True
    if following in _APOSTROPHES and end + 1 < len(text) and text[end + 1].isalpha():
        return True
    return False


def _touches_cjk(text: str, start: int, end: int) -> bool:
    """
    紧贴**汉字/假名**的拉丁片段跳过：中文正文里那多半是术语残留或拼音
    （如 ``使用Linux系统``）。注意中文**标点**（，。、！）是分隔符，不算紧贴。
    """
    if start > 0 and _CJK_WORD_RE.match(text[start - 1]):
        return True
    if end < len(text) and _CJK_WORD_RE.match(text[end]):
        return True
    return False


def tokenize_words(text) -> list[tuple[str, int, int]]:
    """
    从 ``text`` 里挑出**需要做拼写检查**的拉丁单词及位置。

    返回 ``[(word, start, end), ...]``（``text[start:end] == word``）。
    只返回拉丁字母单词：中文、数字、URL、邮箱、代码块、标识符、缩写词、
    版本号一律跳过；短于 :data:`MIN_WORD_LENGTH` 的词也不返回。
    """
    if not text:
        return []
    masked = _mask_ignored(text)
    found: list[tuple[str, int, int]] = []
    for match in _LATIN_RUN_RE.finditer(masked):
        word = match.group()
        start, end = match.span()
        if len(word) < MIN_WORD_LENGTH:
            continue
        if not _is_checkable_shape(word):
            continue
        if _touches_identifier_or_number(text, start, end):
            continue
        if _touches_cjk(text, start, end):
            continue
        found.append((word, start, end))
    return found


# ====================================================================
# 后端
# ====================================================================

class SpellBackend:
    """拼写后端抽象：``check(word) -> bool``（True = 拼写正确）、``suggest(word) -> list[str]``。"""

    name = "abstract"
    available = True
    reason = ""

    def check(self, word: str) -> bool:        # pragma: no cover - 抽象
        raise NotImplementedError

    def suggest(self, word: str) -> list[str]:  # pragma: no cover - 抽象
        raise NotImplementedError


class UnavailableBackend(SpellBackend):
    """
    没有可用后端时的占位实现。

    ``check()`` **恒返回 True**：不可用时宁可不报错，也不要把整篇文章标红。
    真正的"不可用"事实由 ``available=False`` + ``reason`` 表达。
    """

    name = "unavailable"
    available = False

    def __init__(self, reason: str = ""):
        self.reason = reason or "没有可用的拼写检查后端"

    def check(self, word: str) -> bool:
        return True

    def suggest(self, word: str) -> list[str]:
        return []


class PySpellCheckerBackend(SpellBackend):
    """pyspellchecker（``from spellchecker import SpellChecker``）后端。"""

    name = "pyspellchecker"

    def __init__(self, engine):
        self._engine = engine

    def check(self, word: str) -> bool:
        try:
            return not self._engine.unknown([word.lower()])
        except Exception as exc:  # 查不动就当他正确，不误报
            logger.debug("pyspellchecker.check(%r) 失败: %s", word, exc)
            return True

    def suggest(self, word: str) -> list[str]:
        key = word.lower()
        out: list[str] = []
        try:
            correction = self._engine.correction(key)
        except Exception:
            correction = None
        if correction:
            out.append(correction)
        try:
            candidates = self._engine.candidates(key) or ()
        except Exception:
            candidates = ()
        # candidates 是 set，排序保证建议顺序稳定（便于测试与 UI 重现）
        for candidate in sorted(candidates, key=lambda item: (len(item), item)):
            if candidate not in out:
                out.append(candidate)
        return out[:MAX_SUGGESTIONS]


class EnchantBackend(SpellBackend):
    """pyenchant（``import enchant``）后端。"""

    name = "enchant"

    def __init__(self, dictionary):
        self._dictionary = dictionary

    def check(self, word: str) -> bool:
        try:
            return bool(self._dictionary.check(word))
        except Exception as exc:
            logger.debug("enchant.check(%r) 失败: %s", word, exc)
            return True

    def suggest(self, word: str) -> list[str]:
        try:
            return list(self._dictionary.suggest(word))[:MAX_SUGGESTIONS]
        except Exception:
            return []


class WindowsNativeSpellBackend(SpellBackend):
    """
    Windows 自带 ``ISpellChecker`` 后端（ctypes，手工 vtable）。

    只有**通过功能自检**（能把 hello/world/the 认成正确词）的语言才会被选中，
    见 :func:`_select_windows_language`。
    """

    name = "windows-native"

    def __init__(self, checker, language_tag: str):
        self._checker = checker
        self.language_tag = language_tag

    def check(self, word: str) -> bool:
        try:
            return bool(self._checker.check_word(word))
        except Exception as exc:
            logger.debug("windows-native.check(%r) 失败: %s", word, exc)
            return True

    def suggest(self, word: str) -> list[str]:
        try:
            return list(self._checker.suggest(word))[:MAX_SUGGESTIONS]
        except Exception:
            return []


# ====================================================================
# Windows 原生 ISpellChecker（ctypes COM）
# ====================================================================

_WIN_CLSID_FACTORY = "7AB36653-1796-484B-BDFA-E74F1DB7C1DC"
_WIN_IID_FACTORY = "8E018A9D-2415-4677-BF08-794EA61F94BB"
_CLSCTX_INPROC_SERVER = 1
_COINIT_MULTITHREADED = 0

#: 功能自检词：全是正确英文单词。任何把它们判错的检查器都不能用于英文。
SANITY_WORDS = ("hello", "world", "the", "computer", "document")


class _Guid(ctypes.Structure):
    _fields_ = [
        ("data1", ctypes.c_ulong),
        ("data2", ctypes.c_ushort),
        ("data3", ctypes.c_ushort),
        ("data4", ctypes.c_ubyte * 8),
    ]


def _parse_guid(text: str) -> "_Guid":
    parts = text.strip("{}").split("-")
    guid = _Guid()
    guid.data1 = int(parts[0], 16)
    guid.data2 = int(parts[1], 16)
    guid.data3 = int(parts[2], 16)
    for index, byte in enumerate(bytes.fromhex(parts[3] + parts[4])):
        guid.data4[index] = byte
    return guid


def _com_call(pointer, index: int, restype, argtypes: tuple):
    """按 vtable 下标取 COM 方法（index 0..2 是 IUnknown 的三个方法）。"""
    vtable = ctypes.cast(pointer, ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p))).contents
    prototype = ctypes.WINFUNCTYPE(restype, ctypes.c_void_p, *argtypes)
    return prototype(vtable[index])


def _com_release(pointer) -> None:
    try:
        _com_call(pointer, 2, ctypes.c_ulong, ())(pointer)
    except Exception:  # pragma: no cover - 释放失败不该影响功能
        pass


def _free_string(ole32, value) -> None:
    try:
        ole32.CoTaskMemFree(ctypes.cast(value, ctypes.c_void_p))
    except Exception:  # pragma: no cover
        pass


class _WindowsSpellChecker:
    """``ISpellChecker`` 最小包装（vtable：3 get_LanguageTag，4 Check，5 Suggest）。"""

    def __init__(self, pointer, language_tag: str, ole32):
        self._pointer = pointer
        self._ole32 = ole32
        self.language_tag = language_tag

    # ---- ISpellingError 的四个 getter ----
    def _read_error(self, item, text):
        start = ctypes.c_uint32()
        length = ctypes.c_uint32()
        action = ctypes.c_int()
        replacement = ctypes.c_wchar_p()
        _com_call(item, 3, ctypes.c_long, (ctypes.POINTER(ctypes.c_uint32),))(item, ctypes.byref(start))
        _com_call(item, 4, ctypes.c_long, (ctypes.POINTER(ctypes.c_uint32),))(item, ctypes.byref(length))
        _com_call(item, 5, ctypes.c_long, (ctypes.POINTER(ctypes.c_int),))(item, ctypes.byref(action))
        _com_call(item, 6, ctypes.c_long, (ctypes.POINTER(ctypes.c_wchar_p),))(item, ctypes.byref(replacement))
        word = text[start.value:start.value + length.value]
        result = (word, start.value, length.value, action.value, replacement.value or "")
        if replacement.value:
            _free_string(self._ole32, replacement)
        return result

    def errors(self, text: str) -> list[tuple[str, int, int, int, str]]:
        """``ISpellChecker::Check`` → [(word, start, length, corrective_action, replacement)]。"""
        enum = ctypes.c_void_p()
        hr = _com_call(self._pointer, 4, ctypes.c_long,
                       (ctypes.c_wchar_p, ctypes.POINTER(ctypes.c_void_p)))(
            self._pointer, text, ctypes.byref(enum))
        if hr != 0 or not enum.value:
            return []
        out: list[tuple[str, int, int, int, str]] = []
        next_error = _com_call(enum, 3, ctypes.c_long, (ctypes.POINTER(ctypes.c_void_p),))
        while True:
            item = ctypes.c_void_p()
            hr = next_error(enum, ctypes.byref(item))
            if hr != 0 or not item.value:
                break
            out.append(self._read_error(item, text))
            _com_release(item)
        _com_release(enum)
        return out

    def check_word(self, word: str) -> bool:
        return not self.errors(word)

    def suggest(self, word: str) -> list[str]:
        enum = ctypes.c_void_p()
        hr = _com_call(self._pointer, 5, ctypes.c_long,
                       (ctypes.c_wchar_p, ctypes.POINTER(ctypes.c_void_p)))(
            self._pointer, word, ctypes.byref(enum))
        if hr != 0 or not enum.value:
            return []
        out: list[str] = []
        next_string = _com_call(enum, 3, ctypes.c_long,
                                (ctypes.c_ulong, ctypes.POINTER(ctypes.c_wchar_p),
                                 ctypes.POINTER(ctypes.c_ulong)))
        while True:
            buffer = ctypes.c_wchar_p()
            fetched = ctypes.c_ulong()
            hr = next_string(enum, 1, ctypes.byref(buffer), ctypes.byref(fetched))
            if hr != 0 or not fetched.value or not buffer.value:
                break
            out.append(buffer.value)
            _free_string(self._ole32, buffer)
        _com_release(enum)
        return out

    def is_usable_for_english(self) -> bool:
        """
        功能自检：这些词都是正确英文单词，一个都不该被报错。

        本机的 zh-Latn-CN-x-ext 检查器会把它们**全部**判错 —— 正是靠这条
        （而不是靠"dll 文件名/注册表项存在"）否决原生后端。
        """
        flagged = {item[0].lower() for item in self.errors(" ".join(SANITY_WORDS))}
        if flagged:
            logger.debug("windows-native 自检失败，被误判的词: %s", sorted(flagged))
        return not flagged


class _WindowsSpellCheckerFactory:
    """``ISpellCheckerFactory`` 最小包装（vtable：3 get_SupportedLanguages，4 IsSupported，5 CreateSpellChecker）。"""

    def __init__(self):
        ole32 = ctypes.WinDLL("ole32.dll")  # type: ignore[attr-defined]
        self._ole32 = ole32
        try:
            ole32.CoInitializeEx(None, _COINIT_MULTITHREADED)
        except Exception:  # RPC_E_CHANGED_MODE 等：本线程已在别的套间，仍可用
            pass
        clsid = _parse_guid(_WIN_CLSID_FACTORY)
        iid = _parse_guid(_WIN_IID_FACTORY)
        pointer = ctypes.c_void_p()
        hr = ole32.CoCreateInstance(ctypes.byref(clsid), None, _CLSCTX_INPROC_SERVER,
                                    ctypes.byref(iid), ctypes.byref(pointer))
        if hr != 0 or not pointer.value:
            raise OSError("CoCreateInstance(SpellCheckerFactory) 失败：HRESULT=0x%08X"
                          % (hr & 0xFFFFFFFF))
        self._pointer = pointer

    def supported_languages(self) -> list[str]:
        enum = ctypes.c_void_p()
        hr = _com_call(self._pointer, 3, ctypes.c_long, (ctypes.POINTER(ctypes.c_void_p),))(
            self._pointer, ctypes.byref(enum))
        if hr != 0 or not enum.value:
            return []
        tags: list[str] = []
        next_string = _com_call(enum, 3, ctypes.c_long,
                                (ctypes.c_ulong, ctypes.POINTER(ctypes.c_wchar_p),
                                 ctypes.POINTER(ctypes.c_ulong)))
        while True:
            buffer = ctypes.c_wchar_p()
            fetched = ctypes.c_ulong()
            hr = next_string(enum, 1, ctypes.byref(buffer), ctypes.byref(fetched))
            if hr != 0 or not fetched.value or not buffer.value:
                break
            tags.append(buffer.value)
            _free_string(self._ole32, buffer)
        _com_release(enum)
        return tags

    def is_supported(self, language_tag: str) -> bool:
        supported = ctypes.c_int(-1)
        hr = _com_call(self._pointer, 4, ctypes.c_long,
                       (ctypes.c_wchar_p, ctypes.POINTER(ctypes.c_int)))(
            self._pointer, language_tag, ctypes.byref(supported))
        return hr == 0 and bool(supported.value)

    def create_checker(self, language_tag: str) -> "_WindowsSpellChecker":
        pointer = ctypes.c_void_p()
        hr = _com_call(self._pointer, 5, ctypes.c_long,
                       (ctypes.c_wchar_p, ctypes.POINTER(ctypes.c_void_p)))(
            self._pointer, language_tag, ctypes.byref(pointer))
        if hr != 0 or not pointer.value:
            raise OSError("CreateSpellChecker(%r) 失败：HRESULT=0x%08X"
                          % (language_tag, hr & 0xFFFFFFFF))
        return _WindowsSpellChecker(pointer, language_tag, self._ole32)


def _is_english_language_tag(language_tag: str) -> bool:
    """``en`` / ``en-US`` / ``en_GB`` 都算英文语言标签。"""
    return str(language_tag).lower().replace("_", "-").split("-")[0] == "en"


def _select_windows_language(tags: Sequence[str], probe_usable: Callable[[str], bool]):
    """
    纯策略（可单测）：从 ``tags`` 里挑一个**真的能检查英文**的语言。

    :param tags: ``ISpellCheckerFactory.SupportedLanguages`` 的结果
    :param probe_usable: ``tag -> bool``，返回该语言的检查器是否通过功能自检
    :return: ``(language_tag | None, reason)``；reason 只在 None 时非空（中文）
    """
    tags = list(tags)
    if not tags:
        return None, "Windows 原生拼写检查：系统没有安装任何拼写检查语言（SupportedLanguages 为空）"
    english = [tag for tag in tags if _is_english_language_tag(tag)]
    for tag in english + [tag for tag in tags if tag not in english]:
        if probe_usable(tag):
            return tag, ""
    if english:
        detail = ("英文语言包 " + "、".join(english)
                  + " 的检查器未通过自检：它会把 hello/world/the 这类正确英文单词判为拼写错误")
    else:
        detail = "系统里没有英文（en-*）语言包，只有 " + "、".join(tags)
    return None, ("Windows 原生拼写检查不可用于英文检查：可用的拼写检查语言为 "
                  + "、".join(tags) + "；" + detail)


def _probe_windows_native() -> SpellBackend:
    """探测 Windows 原生拼写检查；不可用/不能查英文时返回 :class:`UnavailableBackend`。"""
    if sys.platform != "win32":
        return UnavailableBackend(f"Windows 原生拼写检查仅在 Windows 上可用（当前平台 {sys.platform}）")
    try:
        factory = _WindowsSpellCheckerFactory()
    except Exception as exc:
        return UnavailableBackend(f"Windows 原生拼写检查不可用（{type(exc).__name__}: {exc}）")
    try:
        tags = factory.supported_languages()
    except Exception as exc:
        return UnavailableBackend(f"Windows 原生拼写检查不可用（枚举语言失败：{type(exc).__name__}: {exc}）")

    created: dict[str, _WindowsSpellChecker] = {}

    def probe_usable(language_tag: str) -> bool:
        try:
            checker = factory.create_checker(language_tag)
        except Exception:
            return False
        if not checker.is_usable_for_english():
            return False
        created[language_tag] = checker
        return True

    language_tag, reason = _select_windows_language(tags, probe_usable)
    if language_tag is None:
        return UnavailableBackend(reason)
    return WindowsNativeSpellBackend(created[language_tag], language_tag)


# ====================================================================
# 其它后端探测
# ====================================================================

def _probe_pyspellchecker() -> SpellBackend:
    try:
        from spellchecker import SpellChecker  # type: ignore
    except Exception as exc:
        return UnavailableBackend(
            f"pyspellchecker 未安装（import spellchecker 失败：{type(exc).__name__}: {exc}）")
    try:
        engine = SpellChecker(language=DEFAULT_LANGUAGE)
    except Exception as exc:
        return UnavailableBackend(f"pyspellchecker 已安装但 en 词典初始化失败（{type(exc).__name__}: {exc}）")
    return PySpellCheckerBackend(engine)


def _probe_enchant() -> SpellBackend:
    try:
        import enchant  # type: ignore
    except Exception as exc:
        return UnavailableBackend(
            f"pyenchant/enchant 未安装（import enchant 失败：{type(exc).__name__}: {exc}）")
    try:
        dictionary = enchant.Dict("en_US")
    except Exception as exc:
        return UnavailableBackend(f"enchant 已安装但 en_US 词典不可用（{type(exc).__name__}: {exc}）")
    return EnchantBackend(dictionary)


#: 探测顺序 = 优先级
_BACKEND_PROBES: tuple[tuple[str, Callable[[], SpellBackend]], ...] = (
    ("windows-native", _probe_windows_native),
    ("pyspellchecker", _probe_pyspellchecker),
    ("enchant", _probe_enchant),
)


def detect_backend(probes=None) -> SpellBackend:
    """
    按优先级探测后端，返回第一个可用的；全部不可用则返回 :class:`UnavailableBackend`
    （``available is False``，``reason`` 是**中文**说明，且带上每个后端的失败原因）。

    :param probes: 仅测试用；``[(名称, 无参探测函数), ...]``，默认 :data:`_BACKEND_PROBES`
    """
    reasons: list[str] = []
    for name, probe in (_BACKEND_PROBES if probes is None else probes):
        try:
            backend = probe()
        except Exception as exc:
            logger.debug("后端 %s 探测异常: %s", name, exc)
            reasons.append(f"{name} 探测时异常（{type(exc).__name__}: {exc}）")
            continue
        if backend is None:
            reasons.append(f"{name} 不可用")
            continue
        if getattr(backend, "available", False):
            return backend
        reasons.append(getattr(backend, "reason", "") or f"{name} 不可用")
    return UnavailableBackend("未检测到可用的拼写检查后端：" + "；".join(reasons))


#: 判定"后端到底是不是能用的英文词典"的功能自检词：连它们都判错的后端不是英文词典
ENGLISH_PROBE_WORDS = ("hello", "world", "the")


def backend_is_english_dictionary(backend: SpellBackend) -> bool:
    """
    后端是否是一个**能用的英文词典**？判据是功能自检，**不看类名/名字**。

    沿用 Windows 原生后端那套思路（``_WindowsSpellChecker.is_usable_for_english``）：
    ``hello`` / ``world`` / ``the`` 这类最普通的正确英文词，一个都不该被判错。

    为什么 :class:`SpellCheckerService` 要用它决定**是否加载技术词白名单**：

    * 白名单的用途是"补英文词典的缺口"（CentOS / yum / iptables / ens33 词典里没有）。
    * 一个连 hello/world/the 都判错的后端（本机只有 zh-Latn 检查器；测试里"把所有词都
      判错"的桩后端也是）根本不是英文词典。这时把白名单并进词典，会把"它把所有词都
      判错"这个**诊断事实**掩盖掉 —— 而
      ``tests/fidelity/test_spellcheck.py::test_corpus_live_pipeline_reports_when_backend_flags_everything``
      正是用这个事实证明词法切分管道是活的（不是空管道造成的假绿）。
    * 后端 ``check()`` 抛异常 → 视为不可信 → 不加载白名单，保持既有降级行为。
    """
    for word in ENGLISH_PROBE_WORDS:
        try:
            if not backend.check(word):
                return False
        except Exception as exc:
            logger.debug("后端英文自检 check(%r) 异常，按「不是英文词典」处理: %s", word, exc)
            return False
    return True


# ====================================================================
# 自定义词典持久化
# ====================================================================

DICTIONARY_HEADER = "# 蜜蜂办公 拼写检查自定义词典：每行一个词，# 开头为注释，UTF-8 编码"


def _normalise_word(word) -> str:
    return str(word).strip().lower()


def load_user_dictionary(path) -> set[str]:
    """读自定义词典（UTF-8，可带 BOM；空行与 ``#`` 注释忽略）；文件不存在返回空集合。"""
    file = Path(path)
    try:
        raw = file.read_text(encoding="utf-8-sig")
    except FileNotFoundError:
        return set()
    except OSError as exc:
        logger.warning("读取自定义词典失败: %s（%s）", file, exc)
        return set()
    words: set[str] = set()
    for line in raw.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        words.add(line.lower())
    return words


def save_user_dictionary(path, words: Iterable[str]) -> bool:
    """写自定义词典（去重、排序、小写、UTF-8）；成功返回 True。"""
    file = Path(path)
    body = "\n".join(sorted({_normalise_word(word) for word in words if _normalise_word(word)}))
    try:
        if file.parent and str(file.parent) not in ("", "."):
            file.parent.mkdir(parents=True, exist_ok=True)
        file.write_text(DICTIONARY_HEADER + "\n" + (body + "\n" if body else ""), encoding="utf-8")
        return True
    except OSError as exc:
        logger.warning("写入自定义词典失败: %s（%s）", file, exc)
        return False


# ====================================================================
# 技术词白名单（数据文件：beeoffice/data/tech_words.txt）
# ====================================================================
#
# 为什么需要：中文技术文档里全是产品名/命令/协议缩写（``CentOS`` / ``yum`` /
# ``iptables`` / ``ens33``），英文词典不认识它们 → 满屏误报。白名单把这些
# "词典里没有、但技术语境下正确"的词当成已知词，**只减少误报、不新增误报**
# （它永远只是让某个词从"错"变成"对"，不会反过来）。
#
# 词表放在**数据文件**里，代码只负责加载：改词表不用改代码，也不用在 Python 里
# 维护一个巨大的字面量列表。

#: 数据文件名（位于 ``beeoffice/data/`` 下）
TECH_WORDS_FILE = "tech_words.txt"

#: 词表文件头的说明（供人工维护时参考；读取时会忽略 ``#`` 行）
TECH_WORDS_HEADER = "# 蜜蜂办公 拼写检查技术词白名单：每行一个词，# 开头为注释，UTF-8 编码"

#: 惰性缓存：``None`` 表示"还没读过盘"。import 时不读盘，所以文件丢了也绝不会崩。
_TECH_WORDS_CACHE: set[str] | None = None


def tech_words_path() -> Path:
    """内置技术词表的绝对路径（``beeoffice/data/tech_words.txt``）。"""
    return Path(__file__).resolve().parents[1] / "data" / TECH_WORDS_FILE


def load_tech_words(path=None) -> set[str]:
    """
    加载技术词白名单（UTF-8，可带 BOM；空行与 ``#`` 注释忽略），**全部小写归一化**。

    * ``path`` 省略时读内置词表 :func:`tech_words_path`。
    * 文件不存在 / 读不动 / 内容是二进制垃圾时**返回空集合，绝不抛异常**（只记 debug）。
      宁可白名单为空（退化成改动前的行为），也不能让拼写检查整个挂掉。
    """
    file = tech_words_path() if path is None else Path(path)
    try:
        raw = file.read_text(encoding="utf-8-sig")
    except FileNotFoundError:
        logger.debug("技术词表不存在，按空白名单处理: %s", file)
        return set()
    except (OSError, UnicodeDecodeError) as exc:
        logger.debug("读取技术词表失败，按空白名单处理: %s（%s）", file, exc)
        return set()
    words: set[str] = set()
    for line in raw.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        words.add(line.lower())
    return words


def get_tech_words() -> set[str]:
    """内置技术词表（**惰性**：首次调用才读盘，之后走缓存）。返回的是缓存本身。"""
    global _TECH_WORDS_CACHE
    if _TECH_WORDS_CACHE is None:
        _TECH_WORDS_CACHE = load_tech_words()
        logger.debug("技术词表已加载：%d 个词", len(_TECH_WORDS_CACHE))
    return _TECH_WORDS_CACHE


def reset_tech_words_cache() -> None:
    """清空惰性缓存（测试用：改完词表文件后强制重新读盘）。"""
    global _TECH_WORDS_CACHE
    _TECH_WORDS_CACHE = None


def __getattr__(name: str):
    """
    ``TECH_WORDS``：惰性模块属性（PEP 562）。

    只在**第一次访问**时才读盘并缓存，所以 ``import spellcheck`` 永远不会因为
    词表文件缺失/损坏而失败。
    """
    if name == "TECH_WORDS":
        return frozenset(get_tech_words())
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


# ====================================================================
# 检查服务
# ====================================================================

@dataclass
class Misspelling:
    """一处拼写错误：词、原文下标、建议。"""

    word: str
    start: int
    end: int
    suggestions: list[str] = field(default_factory=list)

    def __str__(self) -> str:  # pragma: no cover - 便于调试输出
        return f"{self.word}({self.start}:{self.end})"


class SpellCheckerService:
    """
    拼写检查服务：持有后端 + "忽略词" + "自定义词典" + "技术词白名单"。

    * 后端不可用时 ``available is False``、``reason`` 是中文原因、``check_text()`` 恒返回 ``[]``
      （不制造满屏红线）。
    * 只检查拉丁字母单词（见 :func:`tokenize_words`），**中文不做拼写检查**。
    * **技术词白名单**（``use_tech_words=True``，默认开）：启动时把
      :func:`get_tech_words` 的词并进 ``_dictionary``，因此 ``knows()`` 一条路就够，
      不为白名单另起判断逻辑。词表只把词从"错"变成"对"，**不会新增误报**。
      ``use_tech_words=False`` 可以整块关掉（有人只想要纯英文词典行为）。
    * 白名单只在**后端真的是英文词典**时才加载（见 :func:`backend_is_english_dictionary`）：
      连 hello/world/the 都判错的后端不是英文词典，对它套白名单只会掩盖"后端不可用"
      这一诊断事实。此时 ``use_tech_words`` 仍为 True，但 ``tech_words`` 是空集。
    """

    def __init__(self, backend: SpellBackend | None = None, dictionary: Iterable[str] | None = None,
                 suggest: bool = True, max_suggestions: int = MAX_SUGGESTIONS,
                 use_tech_words: bool = True):
        self.backend = detect_backend() if backend is None else backend
        self.available = bool(getattr(self.backend, "available", False))
        self.reason = getattr(self.backend, "reason", "") or ""
        self.suggest = bool(suggest)
        self.max_suggestions = max_suggestions
        self._ignored: set[str] = set()
        self._dictionary: set[str] = set()
        self.use_tech_words = bool(use_tech_words)
        self._tech_words: set[str] = set()
        if self.use_tech_words:
            if backend_is_english_dictionary(self.backend):
                # 复用 add_to_dictionary：白名单词与用户词典共用一个集合、一条 knows() 判断
                self._tech_words = {_normalise_word(word) for word in get_tech_words()}
                self._tech_words.discard("")
                for word in self._tech_words:
                    self.add_to_dictionary(word)
            else:
                logger.debug(
                    "后端 %s 不像英文词典（连 %s 都判错），跳过技术词白名单",
                    self.backend_name, "/".join(ENGLISH_PROBE_WORDS))
        for word in dictionary or ():
            self.add_to_dictionary(word)

    # ---------------- 词表 ----------------
    @property
    def backend_name(self) -> str:
        return getattr(self.backend, "name", "unknown")

    @property
    def tech_words(self) -> frozenset[str]:
        """当前生效的技术词白名单（``use_tech_words=False`` 时是空集）。"""
        return frozenset(self._tech_words)

    def ignore(self, word) -> None:
        """用户点"忽略"：本次会话内不再报这个词。"""
        key = _normalise_word(word)
        if key:
            self._ignored.add(key)

    def add_to_dictionary(self, word) -> None:
        """用户点"添加到词典"：这个词永远算正确。"""
        key = _normalise_word(word)
        if key:
            self._dictionary.add(key)

    def knows(self, word) -> bool:
        """被忽略或被加入词典 → 视为正确。"""
        return _normalise_word(word) in self._ignored or _normalise_word(word) in self._dictionary

    def load_dictionary(self, path) -> int:
        """把词典文件里的词并入当前词典，返回并入的条数。"""
        words = load_user_dictionary(path)
        self._dictionary |= words
        return len(words)

    def save_dictionary(self, path) -> bool:
        """
        把当前词表（忽略词 + 用户词典）写到文件。

        技术词白名单**不写进去**：它是随程序发布的数据文件，不是用户自己攒的词 ——
        写进去会把几百行白名单灌进用户的词典文件（见 ``_tech_words``）。
        """
        return save_user_dictionary(path, self._ignored | (self._dictionary - self._tech_words))

    # ---------------- 检查 ----------------
    def check_word(self, word) -> bool:
        """单个词是否拼写正确（不可用时恒为 True）。"""
        if not self.available or not str(word).strip():
            return True
        if self.knows(word):
            return True
        try:
            return bool(self.backend.check(word))
        except Exception as exc:
            logger.debug("后端 check(%r) 异常: %s", word, exc)
            return True

    def check_text(self, text) -> list[Misspelling]:
        """检查整段文本，返回所有拼写错误（含位置与建议）；后端不可用时返回 ``[]``。"""
        if not self.available or not text:
            return []
        results: list[Misspelling] = []
        for word, start, end in tokenize_words(text):
            if self.knows(word):
                continue
            try:
                correct = bool(self.backend.check(word))
            except Exception as exc:
                logger.debug("后端 check(%r) 异常: %s", word, exc)
                correct = True
            if correct:
                continue
            suggestions: list[str] = []
            if self.suggest:
                try:
                    suggestions = [item for item in self.backend.suggest(word)][:self.max_suggestions]
                except Exception as exc:
                    logger.debug("后端 suggest(%r) 异常: %s", word, exc)
                    suggestions = []
            results.append(Misspelling(word=word, start=start, end=end, suggestions=suggestions))
        return results
