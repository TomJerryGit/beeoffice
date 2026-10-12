# tests/unit/test_ai_source_marker.py
"""
优化规划 §1.8 回归：AI 降级必须可辨识，不能静默返回本地模板。

原状态（BeeOffice-分析报告.md §4.8）：
  `BeeshowAIService` 在「未配置 API Key」或「多次调用失败」后**静默**返回
  本地模板大纲（"背景/核心内容/数据支撑/总结"这类占位要点），日志里只有一行
  warning，UI 不区分来源 —— 用户会把占位内容当作 AI 输出直接用于演示。

修复后：服务暴露 `last_source`（"ai" / "local" / "error" / "none"）与
`describe_last_source()`，调用方据此如实提示用户。
"""
import pytest

from beeoffice.plugins.beeshow_ai_service import BeeshowAIService, SlideOutline


def _no_key_service(**extra):
    config = {"api_key": "", "retry": 0}
    config.update(extra)
    return BeeshowAIService(config)


def _failing_service(**extra):
    """有 Key 但调用必然失败（不打网络）。"""
    config = {"api_key": "dummy-key", "retry": 0}
    config.update(extra)
    service = BeeshowAIService(config)

    def _boom(prompt):
        raise RuntimeError("模拟网络/鉴权失败")

    service._call_llm = _boom
    return service


# ==================== 未配置 Key ====================

class TestNoApiKey:
    def test_outline_marks_local(self):
        service = _no_key_service()
        outlines = service.generate_outline(
            topic="测试主题", audience="同事", duration=10, page_count=5
        )
        assert outlines, "本地模板应仍能产出大纲"
        assert service.last_source == "local"
        assert service.source_is_ai() is False
        assert "本地模板" in service.describe_last_source()

    def test_notes_returns_empty_and_marks_local(self):
        service = _no_key_service()
        assert service.generate_notes("标题", "内容") == ""
        assert service.last_source == "local"

    def test_refine_keeps_outline_and_marks_local(self):
        service = _no_key_service()
        current = [SlideOutline(title="占位大纲")]
        assert service.refine_outline(current, "第 3 页加数据") is current
        assert service.last_source == "local"


# ==================== 有 Key 但调用失败 ====================

class TestCallFailure:
    def test_outline_falls_back_but_flagged_local(self):
        """
        失败后仍会给本地模板（保持原有可用性），但来源必须标为 local，
        调用方才能提示"这不是 AI 生成的"。
        """
        service = _failing_service()
        outlines = service.generate_outline(
            topic="测试主题", audience="同事", duration=10, page_count=5
        )
        assert outlines
        assert service.last_source == "local"
        assert service.source_is_ai() is False

    def test_notes_marks_error(self):
        service = _failing_service()
        assert service.generate_notes("标题", "内容") == ""
        assert service.last_source == "error"
        assert service.source_is_ai() is False

    def test_refine_marks_error_and_returns_original(self):
        service = _failing_service()
        current = [SlideOutline(title="原大纲")]
        assert service.refine_outline(current, "改一下") is current
        assert service.last_source == "error"


# ==================== 成功路径 ====================

class TestSuccessPath:
    def test_successful_notes_marked_ai(self):
        service = _failing_service()
        service._call_llm = lambda prompt: "这是一段演讲稿"
        assert service.generate_notes("标题", "内容") == "这是一段演讲稿"
        assert service.last_source == "ai"
        assert service.source_is_ai() is True
        assert service.describe_last_source() == "AI 生成"

    def test_empty_llm_response_is_not_ai(self):
        """LLM 返回空字符串时应标为 error，而不是让 UI 显示"AI 已生成"。"""
        service = _failing_service()
        service._call_llm = lambda prompt: "   "
        assert service.generate_notes("标题", "内容") == ""
        assert service.last_source == "error"


# ==================== 初始状态与可读性 ====================

def test_initial_source_is_none():
    service = _no_key_service()
    assert service.last_source == "none"
    assert service.source_is_ai() is False
    assert service.describe_last_source()


@pytest.mark.parametrize("value", ["ai", "local", "error", "none", "unknown"])
def test_describe_always_returns_text(value):
    service = _no_key_service()
    service.last_source = value
    assert isinstance(service.describe_last_source(), str)
    assert service.describe_last_source()
