# -*- coding: utf-8 -*-
"""
蜜演 PPTX 导出：测量失败必须返回失败（P1）

背景：
    `PPTXEngine.export()` 在逐页测量时，遇到 `ms.error` 只是记一条 warning，
    然后照样把这一页交给生成器并返回 True。
    结果：用户拿到一个"能打开但版式错乱"的 pptx，而界面提示"导出成功"。

修复后：
    任意一页测量失败 → 中止导出、不写文件、返回 False，
    由上层 `beeshow_export_mixin` 回退到图片版导出。
"""
import pytest

pytest.importorskip("PySide6.QtWidgets")


class _FailingMeasurer:
    """模拟测量失败的 measurer。"""

    def __init__(self, error="测不到元素"):
        self.error = error
        self.calls = 0

    def measure(self, html):  # noqa: D401 - 与被替换对象签名一致
        self.calls += 1

        class _Result:
            pass

        r = _Result()
        r.error = self.error
        r.elements = []
        r.width = 0
        r.height = 0
        return r


def test_measure_failure_returns_false_and_writes_nothing(tmp_path):
    from beeoffice.plugins.beeshow_pptx_engine import PPTXEngine

    engine = PPTXEngine()
    engine.measurer = _FailingMeasurer()

    out = tmp_path / "should_not_exist.pptx"
    ok = engine.export(["<h1>第一页</h1>", "<h1>第二页</h1>"], str(out))

    assert ok is False, "测量失败时导出必须返回 False"
    assert engine.measurer.calls == 1, "第一页失败后应立即中止，不再测量后续页"
    assert not out.exists(), "测量失败时不应生成文件"


def test_measure_failure_on_second_slide_also_aborts(tmp_path):
    """第 2 页失败同样要中止——不能"前几页成功就算成功"。"""
    from beeoffice.plugins.beeshow_pptx_engine import PPTXEngine

    class _FirstOkThenFail(_FailingMeasurer):
        def measure(self, html):
            self.calls += 1

            class _Result:
                pass

            r = _Result()
            r.error = "" if self.calls == 1 else "第二页测不到"
            r.elements = []
            r.width = 0
            r.height = 0
            return r

    engine = PPTXEngine()
    engine.measurer = _FirstOkThenFail()

    out = tmp_path / "partial.pptx"
    assert engine.export(["<h1>好的一页</h1>", "<h1>坏的一页</h1>"], str(out)) is False
    assert not out.exists()
