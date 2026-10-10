"""测试对抗机提问式输出"""

from text_reconstructor.output.interactive_questions import (
    InteractiveItem,
    InteractiveQuestions,
)
from text_reconstructor.output.llm_review_extractor import LLMReviewItem


def _alert(type_: str, severity: str = "high", text: str = "测试文本",
           detail: str = "", **kw) -> dict:
    return {"type": type_, "severity": severity, "text": text, "detail": detail, **kw}


class TestFromAlerts:
    def test_empty_alerts(self):
        iq = InteractiveQuestions()
        result = iq.format([])
        assert result == []

    def test_low_confidence_filtered_by_threshold(self):
        """LOW_CONFIDENCE 强制降级为 low severity，被默认阈值 0.6 过滤"""
        iq = InteractiveQuestions(threshold=0.6)
        result = iq.format([_alert("LOW_CONFIDENCE", "high", "手风琴")])
        assert len(result) == 0  # score = 0.3*0.6 + 0.8*0.4 = 0.50 < 0.6

    def test_low_confidence_shows_with_low_threshold(self):
        """LOW_CONFIDENCE 在低阈值时仍可显示"""
        iq = InteractiveQuestions(threshold=0.0)
        result = iq.format([_alert("LOW_CONFIDENCE", "high", "手风琴")])
        assert len(result) == 1
        assert result[0].severity == "low"  # 强制降级
        assert result[0].needs_input is True

    def test_dangling_directive(self):
        iq = InteractiveQuestions(threshold=0.0)
        result = iq.format([_alert("DANGLING_DIRECTIVE", "high", "需要人工标注")])
        assert len(result) == 1
        assert result[0].category == "missing_info"
        assert result[0].needs_input is True

    def test_logic_conflict(self):
        iq = InteractiveQuestions(threshold=0.0)
        result = iq.format([_alert("LOGIC_CONFLICT", "high", detail="300万与50人矛盾")])
        assert len(result) == 1
        assert result[0].category == "contradiction"
        assert result[0].needs_input is False

    def test_unknown_type_filtered(self):
        iq = InteractiveQuestions(threshold=0.0)
        result = iq.format([_alert("UNKNOWN_TYPE", "high")])
        assert result == []


class TestFromLLMReviews:
    def test_doubt_item(self):
        iq = InteractiveQuestions(threshold=0.0)
        reviews = [LLMReviewItem(
            marker_type="doubt",
            content="分词不准的具体指标",
            position=0,
            surrounding="上下文",
        )]
        result = iq.format([], reviews)
        assert len(result) == 1
        assert result[0].alert_type == "llm_doubt"
        assert result[0].needs_input is True
        assert result[0].category == "ambiguity"

    def test_issue_item(self):
        iq = InteractiveQuestions(threshold=0.0)
        reviews = [LLMReviewItem(
            marker_type="issue",
            content="前后矛盾",
            position=0,
            surrounding="上下文",
        )]
        result = iq.format([], reviews)
        assert len(result) == 1
        assert result[0].alert_type == "llm_issue"
        assert result[0].category == "contradiction"
        assert result[0].needs_input is False
        assert result[0].severity == "high"

    def test_doubt_logic_jump_classification(self):
        iq = InteractiveQuestions(threshold=0.0)
        reviews = [LLMReviewItem(
            marker_type="doubt",
            content="逻辑跳跃，缺乏推理依据",
            position=0,
            surrounding="",
        )]
        result = iq.format([], reviews)
        assert result[0].category == "logic_jump"

    def test_doubt_missing_info_classification(self):
        iq = InteractiveQuestions(threshold=0.0)
        reviews = [LLMReviewItem(
            marker_type="doubt",
            content="缺少前提条件",
            position=0,
            surrounding="",
        )]
        result = iq.format([], reviews)
        assert result[0].category == "missing_info"


class TestThresholdFiltering:
    def test_high_threshold_filters_medium(self):
        iq = InteractiveQuestions(threshold=0.9)
        # ambiguity + medium = 0.6*0.6 + 0.8*0.4 = 0.36+0.32 = 0.68
        result = iq.format([_alert("LOW_CONFIDENCE", "medium", "测试")])
        assert result == []

    def test_high_severity_passes(self):
        iq = InteractiveQuestions(threshold=0.6)
        # contradiction + high = 1.0*0.6 + 1.0*0.4 = 1.0
        result = iq.format([_alert("LOGIC_CONFLICT", "high", detail="矛盾")])
        assert len(result) == 1

    def test_max_questions_limit(self):
        iq = InteractiveQuestions(threshold=0.0, max_questions=2)
        alerts = [_alert("LOGIC_CONFLICT", "high", text=f"冲突{i}", detail=f"细节{i}")
                  for i in range(5)]
        result = iq.format(alerts)
        assert len(result) == 2


class TestMergeSources:
    def test_alerts_and_reviews_merged(self):
        iq = InteractiveQuestions(threshold=0.0)
        alerts = [_alert("LOGIC_CONFLICT", "high", detail="管线矛盾")]
        reviews = [LLMReviewItem(
            marker_type="doubt", content="LLM疑点",
            position=0, surrounding="",
        )]
        result = iq.format(alerts, reviews)
        assert len(result) == 2

    def test_score_ordering(self):
        iq = InteractiveQuestions(threshold=0.0, max_questions=10)
        alerts = [
            _alert("LOW_CONFIDENCE", "medium", "模糊"),    # score ~0.68
            _alert("LOGIC_CONFLICT", "high", detail="矛盾"),  # score 1.0
            _alert("DANGLING_DIRECTIVE", "high", "悬空"),  # score ~0.88
        ]
        result = iq.format(alerts)
        assert result[0].category == "contradiction"
        assert result[0].score == 1.0
