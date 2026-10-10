"""测试增量微调引擎"""

from unittest.mock import MagicMock

from text_reconstructor.output.refinement_refiner import (
    Answer,
    RefinementRefiner,
)


def _make_refiner(response: str = "微调后的文本") -> RefinementRefiner:
    mock = MagicMock()
    mock.chat.return_value = MagicMock(content=response)
    return RefinementRefiner(llm_client=mock)


class TestRefinementRefiner:
    def test_empty_input(self):
        r = _make_refiner()
        assert r.refine("") == ""

    def test_no_answers_no_note_returns_original(self):
        r = _make_refiner()
        result = r.refine("原始输出")
        assert result == "原始输出"

    def test_with_answers(self):
        r = _make_refiner("融入了回答")
        answers = [Answer(question_index=0, user_input="手风琴是UI手风琴效果")]
        result = r.refine("上一版输出", answers)
        assert result == "融入了回答"
        # 验证 prompt 包含回答
        call_args = r.client.chat.call_args
        prompt = call_args.kwargs.get("messages", call_args[0][0] if call_args[0] else [])[0]["content"]
        assert "手风琴" in prompt

    def test_with_user_note(self):
        r = _make_refiner("精简后")
        result = r.refine("上一版输出", user_note="精简第三段")
        assert result == "精简后"

    def test_llm_failure_returns_original(self):
        mock = MagicMock()
        mock.chat.side_effect = Exception("API error")
        r = RefinementRefiner(llm_client=mock)
        result = r.refine("原始输出", user_note="改一下")
        assert result == "原始输出"

    def test_llm_empty_response_returns_original(self):
        mock = MagicMock()
        mock.chat.return_value = MagicMock(content="")
        r = RefinementRefiner(llm_client=mock)
        result = r.refine("原始输出", user_note="改一下")
        assert result == "原始输出"

    def test_answers_and_note_combined(self):
        r = _make_refiner("综合修改后")
        answers = [
            Answer(question_index=0, user_input="回答A"),
            Answer(question_index=1, user_input="回答B"),
        ]
        result = r.refine("上一版", answers, "额外指令")
        assert result == "综合修改后"
