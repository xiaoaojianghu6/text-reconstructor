"""InteractiveQuestions -- 对抗机提问式输出

将管线 alerts 和 LLM 审查项统一转换为用户交互式提问列表，
经阈值过滤后输出，供前端右侧边栏展示。
"""

from __future__ import annotations

from dataclasses import dataclass

from text_reconstructor.output.llm_review_extractor import LLMReviewItem

# -- alert type -> (category, needs_input) --
_ALERT_CLASSIFICATION: dict[str, tuple[str, bool]] = {
    "LOW_CONFIDENCE": ("ambiguity", True),
    "DANGLING_DIRECTIVE": ("missing_info", True),
    "LOGIC_CONFLICT": ("contradiction", False),
    "SEMANTIC_CONFLICT": ("contradiction", False),
    "CROSS_FILE_CONFLICT": ("contradiction", False),
    "MISSING_ENTITY": ("missing_info", True),
    "ARGUMENT_GAP": ("missing_info", True),
    "ENTITY_HEDGE": ("contradiction", True),
    "STRUCTURE_CHAOS": ("logic_jump", False),
}

# LOW_CONFIDENCE 强制降级为 "low" 优先级，大部分被阈值过滤
_LOW_PRIORITY_TYPES = {"LOW_CONFIDENCE"}

_SEVERITY_WEIGHT = {"high": 1.0, "medium": 0.6, "low": 0.3}
_CATEGORY_WEIGHT = {
    "contradiction": 1.0,
    "ambiguity": 0.8,
    "missing_info": 0.7,
    "logic_jump": 0.6,
}

# -- LLM 疑点关键词 -> category --
_LOGIC_KEYWORDS = {"逻辑", "跳跃", "推理", "因果", "推导", "论证"}
_MISSING_KEYWORDS = {"前提", "依据", "为什么", "缺少", "遗漏", "背景"}


@dataclass
class InteractiveItem:
    category: str       # "ambiguity" | "missing_info" | "contradiction" | "logic_jump"
    needs_input: bool   # True=有输入框, False=纯提示
    question: str       # 凝练的中文提问
    source_text: str    # 关联的原文片段
    alert_type: str     # 原始 alert type 或 "llm_doubt" / "llm_issue"
    severity: str       # "high" | "medium"
    score: float        # 0.0-1.0 综合评分


class InteractiveQuestions:
    """统一提问式输出: 管线 alerts + LLM 审查 -> 阈值过滤后的提问列表"""

    def __init__(self, threshold: float = 0.6, max_questions: int = 5):
        self.threshold = threshold
        self.max_questions = max_questions

    def format(
        self,
        alerts: list[dict],
        llm_reviews: list[LLMReviewItem] | None = None,
    ) -> list[InteractiveItem]:
        """将 alerts + LLM 审查项转换为经阈值过滤的提问列表"""
        items: list[InteractiveItem] = []
        items.extend(self._from_alerts(alerts))
        items.extend(self._from_llm_reviews(llm_reviews or []))

        scored = [(item, self._compute_score(item)) for item in items]
        scored.sort(key=lambda x: x[1], reverse=True)
        filtered = []
        for item, s in scored:
            if s >= self.threshold:
                item.score = s
                filtered.append(item)
        return filtered[:self.max_questions]

    # -- 来源 1: 管线 alerts --

    def _from_alerts(self, alerts: list[dict]) -> list[InteractiveItem]:
        results: list[InteractiveItem] = []
        for alert in alerts:
            alert_type = alert.get("type", "")
            if alert_type not in _ALERT_CLASSIFICATION:
                continue
            category, needs_input = _ALERT_CLASSIFICATION[alert_type]
            question = self._build_question_from_alert(alert, category)
            if not question:
                continue
            # LOW_CONFIDENCE 强制降级为 low，大部分被阈值过滤
            severity = "low" if alert_type in _LOW_PRIORITY_TYPES else alert.get("severity", "medium")
            results.append(InteractiveItem(
                category=category,
                needs_input=needs_input,
                question=question,
                source_text=alert.get("text", ""),
                alert_type=alert_type,
                severity=severity,
                score=0.0,
            ))
        return results

    def _build_question_from_alert(self, alert: dict, category: str) -> str:
        text = alert.get("text", "")
        detail = alert.get("detail", "")
        if category == "ambiguity":
            return f"输入中「{text}」具体指什么?" if text else ""
        if category == "missing_info":
            return f"「{text}」缺少什么前提?" if text else ""
        if category == "contradiction":
            if detail:
                return detail
            return f"「{text}」存在矛盾"
        return ""

    # -- 来源 2: LLM 审查项 --

    def _from_llm_reviews(self, reviews: list[LLMReviewItem]) -> list[InteractiveItem]:
        results: list[InteractiveItem] = []
        for review in reviews:
            if review.marker_type == "issue":
                results.append(InteractiveItem(
                    category="contradiction",
                    needs_input=False,
                    question=review.content,
                    source_text=review.surrounding,
                    alert_type="llm_issue",
                    severity="high",
                    score=0.0,
                ))
            else:
                category = self._classify_doubt(review.content)
                results.append(InteractiveItem(
                    category=category,
                    needs_input=True,
                    question=f"「{review.content}」-- 需要补充说明?",
                    source_text=review.surrounding,
                    alert_type="llm_doubt",
                    severity="medium",
                    score=0.0,
                ))
        return results

    @staticmethod
    def _classify_doubt(content: str) -> str:
        if any(kw in content for kw in _LOGIC_KEYWORDS):
            return "logic_jump"
        if any(kw in content for kw in _MISSING_KEYWORDS):
            return "missing_info"
        return "ambiguity"

    # -- 评分 --

    def _compute_score(self, item: InteractiveItem) -> float:
        sw = _SEVERITY_WEIGHT.get(item.severity, 0.3)
        cw = _CATEGORY_WEIGHT.get(item.category, 0.5)
        return sw * 0.6 + cw * 0.4
