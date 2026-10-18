# -*- coding: utf-8 -*-
"""
蜜写 AI 续写：不得重复插入原文（P1-28）

缺陷：
    上下文取自"光标前 200 字"，常常从句子中间开始。
    模型回显时会补全整句，于是 `result.startswith(context)` 判假，
    整段（含已存在的上下文）被原样插入 —— 用户看到原文被贴了两遍。

修复：
    改为找 context 后缀与 result 前缀的**最长重叠**并剥掉。
"""
import pytest

pytest.importorskip("PySide6.QtWidgets")


@pytest.fixture(scope="module")
def strip():
    from beeoffice.plugins.beewrite import BeeWriteEditor

    return BeeWriteEditor._strip_echoed_context


def test_exact_echo_is_removed(strip):
    assert strip("今天天气", "今天天气不错") == "不错"


def test_partial_echo_is_removed(strip):
    """上下文从句子中间开始：模型补全了整句。"""
    # 文档是"第一段。今天天气"，上下文末尾是"今天天气"，
    # 模型返回的"今天天气不错。"把上下文重复了一遍。
    assert strip("第一段。今天天气", "今天天气不错。") == "不错。"


def test_no_overlap_keeps_result(strip):
    assert strip("已有的内容", "完全新的句子") == "完全新的句子"


def test_empty_result(strip):
    assert strip("上下文", "") == ""


def test_empty_context(strip):
    assert strip("", "新内容") == "新内容"


def test_full_echo_with_space(strip):
    assert strip("abc def", "abc def ghi") == " ghi"
