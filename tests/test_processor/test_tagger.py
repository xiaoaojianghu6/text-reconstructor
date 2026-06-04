"""Tagger 单元测试"""
from unittest.mock import MagicMock, patch
import pytest
from text_reconstructor.processor.tagger import (
    Tagger,
    apply_signal_corrections,
    validate_chunk,
    check_pronouns,
)


class TestTagger:
    """Tagger batch_tag 测试（mock OllamaClient）"""

    def _make_mock_chat(self, lines: str):
        mock = MagicMock()
        mock.content = lines
        return mock

    @patch("text_reconstructor.processor.tagger.create_client")
    def test_batch_tag_valid(self, mock_factory):
        mock_instance = MagicMock()
        mock_instance.chat.return_value = self._make_mock_chat(
            "0||nucleus||assertive||cause||none||none||会议||时间不足"
        )
        mock_instance.config = MagicMock()
        mock_instance.config.model = "qwen3.5:0.8b"
        mock_instance.config.base_url = "http://localhost:11434"
        mock_instance.config.temperature = 0.1
        mock_instance.config.think = False
        mock_instance.config.backend = "ollama"
        mock_instance.config.api_key = ""
        mock_instance.config.max_tokens = 512
        mock_factory.return_value = mock_instance
        tagger = Tagger()
        result = tagger.batch_tag(["因为时间不够，我们取消了会议。"])
        assert len(result) == 1
        assert result[0]["text"] == "因为时间不够，我们取消了会议。"
        assert result[0]["role"] == "satellite"
        assert result[0]["relation"] == "cause"
        assert result[0]["scope"] == "会议"

    @patch("text_reconstructor.processor.tagger.create_client")
    def test_batch_tag_empty_llm_response(self, mock_factory):
        """LLM 返回空时用默认值"""
        mock_instance = MagicMock()
        mock_instance.chat.return_value = self._make_mock_chat("")
        mock_instance.config = MagicMock()
        mock_instance.config.model = "qwen3.5:0.8b"
        mock_instance.config.base_url = "http://localhost:11434"
        mock_instance.config.temperature = 0.1
        mock_instance.config.think = False
        mock_instance.config.backend = "ollama"
        mock_instance.config.api_key = ""
        mock_instance.config.max_tokens = 512
        mock_factory.return_value = mock_instance
        tagger = Tagger()
        result = tagger.batch_tag(["测试句子"])
        assert len(result) == 1
        assert result[0]["role"] == "satellite"
        assert result[0]["relation"] == "none"

    @patch("text_reconstructor.processor.tagger.create_client")
    def test_batch_tag_llm_error(self, mock_factory):
        """LLM 异常时回退默认值"""
        mock_instance = MagicMock()
        mock_instance.chat.side_effect = Exception("LLM 挂了")
        mock_instance.config = MagicMock()
        mock_instance.config.model = "qwen3.5:0.8b"
        mock_instance.config.base_url = "http://localhost:11434"
        mock_instance.config.temperature = 0.1
        mock_instance.config.think = False
        mock_instance.config.backend = "ollama"
        mock_instance.config.api_key = ""
        mock_instance.config.max_tokens = 512
        mock_factory.return_value = mock_instance
        tagger = Tagger()
        result = tagger.batch_tag(["测试句子"])
        assert len(result) == 1
        assert result[0]["text"] == "测试句子"
        assert result[0]["role"] == "satellite"

    @patch("text_reconstructor.processor.tagger.create_client")
    def test_batch_tag_signal_corrections(self, mock_factory):
        """batch 模式信号词修正仍生效"""
        mock_instance = MagicMock()
        mock_instance.chat.return_value = self._make_mock_chat(
            "0||satellite||assertive||none||none||none||预算||"
        )
        mock_instance.config = MagicMock()
        mock_instance.config.model = "qwen3.5:0.8b"
        mock_instance.config.base_url = "http://localhost:11434"
        mock_instance.config.temperature = 0.1
        mock_instance.config.think = False
        mock_instance.config.backend = "ollama"
        mock_instance.config.api_key = ""
        mock_instance.config.max_tokens = 512
        mock_factory.return_value = mock_instance
        tagger = Tagger()
        result = tagger.batch_tag(["但是预算有限。"])
        assert result[0]["relation"] == "contrast"
        assert result[0]["_corrected"] is True

    @patch("text_reconstructor.processor.tagger.create_client")
    def test_batch_tag_pronoun_detection(self, mock_factory):
        """batch 模式代词检测仍生效"""
        mock_instance = MagicMock()
        mock_instance.chat.return_value = self._make_mock_chat(
            "0||nucleus||assertive||elaboration||none||none||||"
        )
        mock_instance.config = MagicMock()
        mock_instance.config.model = "qwen3.5:0.8b"
        mock_instance.config.base_url = "http://localhost:11434"
        mock_instance.config.temperature = 0.1
        mock_instance.config.think = False
        mock_instance.config.backend = "ollama"
        mock_instance.config.api_key = ""
        mock_instance.config.max_tokens = 512
        mock_factory.return_value = mock_instance
        tagger = Tagger()
        result = tagger.batch_tag(["简而言之，他在会上提出了一个想法。"])
        assert result[0].get("scope") == "REFERENCE_MISSING"


class TestSignalCorrections:
    """信号词后处理测试"""

    def test_cause_signal(self):
        """因为 → cause"""
        chunk = {"relation": "none"}
        result = apply_signal_corrections(chunk, "因为时间不够")
        assert result["relation"] == "cause"
        assert result["_corrected"] is True

    def test_contrast_signal(self):
        """但是 → contrast"""
        chunk = {"relation": "none"}
        result = apply_signal_corrections(chunk, "但是这个方法有问题")
        assert result["relation"] == "contrast"

    def test_sequence_signal(self):
        """然后 → sequence"""
        chunk = {"relation": "none"}
        result = apply_signal_corrections(chunk, "然后我们去了公园")
        assert result["relation"] == "sequence"

    def test_evidence_signal(self):
        """例如 → evidence"""
        chunk = {"relation": "none"}
        result = apply_signal_corrections(chunk, "例如苹果和香蕉")
        assert result["relation"] == "evidence"

    def test_no_signal(self):
        """无信号词时不修正"""
        chunk = {"relation": "none"}
        result = apply_signal_corrections(chunk, "今天天气很好")
        assert result["relation"] == "none"
        assert "_corrected" not in result

    def test_signal_overrides_existing(self):
        """信号词覆盖已存在的错误 relation"""
        chunk = {"relation": "sequence"}
        result = apply_signal_corrections(chunk, "但是实际上")
        assert result["relation"] == "contrast"

    def test_signal_missing_on_correct_value(self):
        """信号词匹配但 relation 已正确时不做无效覆盖"""
        chunk = {"relation": "cause"}
        result = apply_signal_corrections(chunk, "因为这样")
        assert result["relation"] == "cause"


class TestValidateChunk:
    """JSON 校验测试"""

    def test_fill_missing_fields(self):
        """缺失字段补充默认值"""
        result = validate_chunk({}, "测试")
        assert result["text"] == "测试"
        assert result["role"] == "satellite"
        assert result["intent"] == "assertive"
        assert result["relation"] == "none"

    def test_invalid_role(self):
        """无效 role 回退默认"""
        result = validate_chunk({"role": "invalid"}, "测试")
        assert result["role"] == "satellite"

    def test_invalid_relation(self):
        """无效 relation 回退默认"""
        result = validate_chunk({"relation": "invalid"}, "测试")
        assert result["relation"] == "none"

    def test_partial_input(self):
        """部分字段存在时保留"""
        result = validate_chunk({"role": "nucleus", "intent": "directive"}, "测试")
        assert result["role"] == "nucleus"
        assert result["intent"] == "directive"
        assert result["relation"] == "none"  # 缺失则默认

    def test_none_input(self):
        """None 输入应处理"""
        result = validate_chunk(None, "测试")
        assert isinstance(result, dict)
        assert result["text"] == "测试"


class TestPronounCheck:
    """代词检测测试"""

    def test_detects_pronoun_without_ref(self):
        """代词存在且无 scope/dependency → scope=REFERENCE_MISSING"""
        chunk = {"scope": "", "dependency": ""}
        result = check_pronouns(chunk, "他认为这个方案可行")
        assert result["scope"] == "REFERENCE_MISSING"

    def test_pronoun_with_scope_ok(self):
        """代词存在但有 scope → 不标记"""
        chunk = {"scope": "产品方案", "dependency": ""}
        result = check_pronouns(chunk, "它节省成本")
        assert result.get("scope") == "产品方案"

    def test_no_pronoun(self):
        """无代词 → 不修改"""
        chunk = {"scope": "", "dependency": ""}
        result = check_pronouns(chunk, "今天天气很好")
        assert result.get("_has_pronoun") is None
