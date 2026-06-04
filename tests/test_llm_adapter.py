"""OllamaClient 适配层单元测试（mock httpx）"""

from unittest.mock import patch, MagicMock
import json
import pytest
import httpx
from text_reconstructor.llm.adapter import (
    OllamaClient,
    LLMConfig,
    LLMConnectionError,
    LLMTimeoutError,
    LLMResponseError,
)

SAMPLE_CHAT_RESPONSE = {
    "model": "qwen3.5:0.8b",
    "message": {"content": "测试响应内容", "role": "assistant"},
    "total_duration": 1000000000,
    "prompt_eval_count": 10,
    "eval_count": 20,
}

SAMPLE_JSON_RESPONSE = {
    "model": "qwen3.5:0.8b",
    "message": {"content": '{"role": "nucleus", "intent": "assertive"}'},
    "total_duration": 1000000000,
    "prompt_eval_count": 10,
    "eval_count": 20,
}


class TestOllamaClientChat:
    """OllamaClient.chat() 测试"""

    @patch("text_reconstructor.llm.adapter.httpx.Client")
    def test_chat_basic(self, MockClient):
        """chat 返回 LLMResponse"""
        mock_instance = MockClient.return_value.__enter__.return_value
        mock_instance.post.return_value.status_code = 200
        mock_instance.post.return_value.json.return_value = SAMPLE_CHAT_RESPONSE

        client = OllamaClient()
        resp = client.chat([{"role": "user", "content": "你好"}], use_stream=False)

        assert resp.content == "测试响应内容"
        assert resp.model == "qwen3.5:0.8b"
        assert resp.total_duration_ns == 1000000000
        assert resp.eval_count == 20
        assert resp.prompt_eval_count == 10

    @patch("text_reconstructor.llm.adapter.httpx.Client")
    def test_chat_with_system_prompt(self, MockClient):
        """chat 支持 system_prompt 参数"""
        mock_instance = MockClient.return_value.__enter__.return_value
        mock_instance.post.return_value.status_code = 200
        mock_instance.post.return_value.json.return_value = SAMPLE_CHAT_RESPONSE

        client = OllamaClient()
        client.chat(
            [{"role": "user", "content": "test"}],
            system_prompt="你是助手",
            use_stream=False,
        )

        call_kwargs = mock_instance.post.call_args[1]
        body = call_kwargs["json"]
        assert body["messages"][0]["role"] == "system"
        assert body["messages"][0]["content"] == "你是助手"

    @patch("text_reconstructor.llm.adapter.httpx.Client")
    def test_chat_connection_error(self, MockClient):
        """连接失败 → LLMConnectionError"""
        mock_instance = MockClient.return_value.__enter__.return_value
        mock_instance.post.side_effect = httpx.ConnectError("连接被拒绝")

        client = OllamaClient()
        with pytest.raises(LLMConnectionError):
            client.chat([{"role": "user", "content": "hi"}], use_stream=False)

    @patch("text_reconstructor.llm.adapter.httpx.Client")
    def test_chat_timeout(self, MockClient):
        """超时 → LLMTimeoutError"""
        mock_instance = MockClient.return_value.__enter__.return_value
        mock_instance.post.side_effect = httpx.TimeoutException("超时")

        client = OllamaClient()
        with pytest.raises(LLMTimeoutError):
            client.chat([{"role": "user", "content": "hi"}], use_stream=False)

    @patch("text_reconstructor.llm.adapter.httpx.Client")
    def test_chat_http_error(self, MockClient):
        """HTTP 错误 → LLMResponseError"""
        mock_instance = MockClient.return_value.__enter__.return_value
        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.text = "Internal Server Error"
        mock_instance.post.return_value = mock_response
        mock_instance.post.return_value.raise_for_status.side_effect = (
            httpx.HTTPStatusError("500", request=MagicMock(), response=mock_response)
        )

        client = OllamaClient()
        with pytest.raises(LLMResponseError):
            client.chat([{"role": "user", "content": "hi"}], use_stream=False)

    @patch("text_reconstructor.llm.adapter.httpx.Client")
    def test_chat_thinking_field_fallback(self, MockClient):
        """thinking 字段回退（Qwen 特殊处理）"""
        resp_data = dict(SAMPLE_CHAT_RESPONSE)
        resp_data["message"] = {"content": "", "thinking": "模型推理过程", "role": "assistant"}
        mock_instance = MockClient.return_value.__enter__.return_value
        mock_instance.post.return_value.status_code = 200
        mock_instance.post.return_value.json.return_value = resp_data

        client = OllamaClient()
        resp = client.chat([{"role": "user", "content": "hi"}], use_stream=False)

        assert resp.content == "模型推理过程"

    @patch("text_reconstructor.llm.adapter.httpx.Client")
    def test_chat_tokens_per_sec(self, MockClient):
        """tokens_per_sec 属性正确计算"""
        mock_instance = MockClient.return_value.__enter__.return_value
        mock_instance.post.return_value.status_code = 200
        mock_instance.post.return_value.json.return_value = SAMPLE_CHAT_RESPONSE

        client = OllamaClient()
        resp = client.chat([{"role": "user", "content": "hi"}], use_stream=False)

        # 20 tokens / 1.0s = 20.0
        assert resp.tokens_per_sec == 20.0

    def test_health_check_offline(self):
        """连接不存在的端口时 health_check 返回 False"""
        client = OllamaClient(config=LLMConfig(base_url="http://localhost:19999", timeout=0.5))
        assert client.health_check() is False

    def test_list_models_offline(self):
        """连接不存在的端口时 list_models 返回空列表"""
        client = OllamaClient(config=LLMConfig(base_url="http://localhost:19999", timeout=0.5))
        assert client.list_models() == []


class TestOllamaClientChatJson:
    """OllamaClient.chat_json() 测试"""

    @patch("text_reconstructor.llm.adapter.httpx.Client")
    def test_chat_json_valid(self, MockClient):
        """chat_json 返回解析后的 dict"""
        mock_instance = MockClient.return_value.__enter__.return_value
        mock_instance.post.return_value.status_code = 200
        mock_instance.post.return_value.json.return_value = SAMPLE_JSON_RESPONSE

        client = OllamaClient()
        result = client.chat_json([{"role": "user", "content": "标注"}])

        assert result["role"] == "nucleus"
        assert result["intent"] == "assertive"

    @patch("text_reconstructor.llm.adapter.httpx.Client")
    def test_chat_json_format_enforced(self, MockClient):
        """chat_json 强制 format=json"""
        mock_instance = MockClient.return_value.__enter__.return_value
        mock_instance.post.return_value.status_code = 200
        mock_instance.post.return_value.json.return_value = SAMPLE_JSON_RESPONSE

        client = OllamaClient()
        client.chat_json([{"role": "user", "content": "标注"}])

        call_kwargs = mock_instance.post.call_args[1]
        body = call_kwargs["json"]
        assert body.get("format") == "json"

    @patch("text_reconstructor.llm.adapter.httpx.Client")
    def test_chat_json_invalid_json(self, MockClient):
        """JSON 解析失败 → LLMResponseError"""
        bad_response = dict(SAMPLE_JSON_RESPONSE)
        bad_response["message"] = {"content": "不是 JSON", "role": "assistant"}
        mock_instance = MockClient.return_value.__enter__.return_value
        mock_instance.post.return_value.status_code = 200
        mock_instance.post.return_value.json.return_value = bad_response

        client = OllamaClient()
        with pytest.raises(LLMResponseError, match="JSON 解析失败"):
            client.chat_json([{"role": "user", "content": "标注"}])


class TestLLMConfig:
    """LLMConfig 序列化测试"""

    def test_to_options_defaults(self):
        """默认 options 序列化"""
        config = LLMConfig()
        opts = config.to_options()
        assert opts["temperature"] == 0.1
        assert opts["num_predict"] == 2048
        assert opts["top_p"] == 0.9

    def test_to_options_custom(self):
        """自定义 options 序列化"""
        config = LLMConfig(temperature=0.5, max_tokens=512, top_p=0.8)
        opts = config.to_options()
        assert opts["temperature"] == 0.5
        assert opts["num_predict"] == 512
        assert opts["top_p"] == 0.8

    def test_duration_ms(self):
        """duration_ms 属性"""
        from text_reconstructor.llm.adapter import LLMResponse
        resp = LLMResponse(content="test", model="m", total_duration_ns=2_500_000_000)
        assert resp.duration_ms == 2500.0


class TestOllamaClientStream:
    """流式响应测试"""

    @patch("text_reconstructor.llm.adapter.httpx.Client")
    def test_stream_accumulates_content(self, MockClient):
        """流式响应正确拼装 content"""
        mock_instance = MockClient.return_value.__enter__.return_value
        stream_lines = [
            '{"message":{"content":"你好"}}',
            '{"message":{"content":"世界"}}',
            '{"message":{"content":""},"done":true,"total_duration":2000000000,"eval_count":5,"prompt_eval_count":3}',
        ]
        mock_stream = MagicMock()
        mock_stream.iter_lines.return_value = stream_lines
        mock_instance.stream.return_value.__enter__.return_value = mock_stream

        client = OllamaClient()
        resp = client.chat([{"role": "user", "content": "hi"}], use_stream=True)

        assert resp.content == "你好世界"
        assert resp.total_duration_ns == 2000000000
        assert resp.eval_count == 5
        assert resp.prompt_eval_count == 3

    @patch("text_reconstructor.llm.adapter.httpx.Client")
    def test_stream_json_decode_error_skipped(self, MockClient):
        """流式响应中 JSON 解析错误的行被跳过"""
        mock_instance = MockClient.return_value.__enter__.return_value
        stream_lines = [
            "not json",
            '{"message":{"content":"OK"}}',
            '{"message":{"content":""},"done":true,"total_duration":1000000000,"eval_count":1,"prompt_eval_count":1}',
        ]
        mock_stream = MagicMock()
        mock_stream.iter_lines.return_value = stream_lines
        mock_instance.stream.return_value.__enter__.return_value = mock_stream

        client = OllamaClient()
        resp = client.chat([{"role": "user", "content": "hi"}], use_stream=True)

        assert resp.content == "OK"

    @patch("text_reconstructor.llm.adapter.httpx.Client")
    def test_stream_thinking_fallback(self, MockClient):
        """流式响应中 thinking 字段回退"""
        mock_instance = MockClient.return_value.__enter__.return_value
        stream_lines = [
            '{"message":{"thinking":"推理过程","content":""}}',
            '{"message":{"content":"最终答案"}}',
            '{"message":{"content":""},"done":true,"total_duration":1000000000,"eval_count":2,"prompt_eval_count":1}',
        ]
        mock_stream = MagicMock()
        mock_stream.iter_lines.return_value = stream_lines
        mock_instance.stream.return_value.__enter__.return_value = mock_stream

        client = OllamaClient()
        resp = client.chat([{"role": "user", "content": "hi"}], use_stream=True)

        assert resp.content == "推理过程最终答案"
