"""NVIDIAClient 单元测试"""

import json
import unittest
from unittest.mock import patch, MagicMock

import httpx

from text_reconstructor.llm import LLMConfig, NVIDIAClient, create_client


class TestNVIDIAClientCreate(unittest.TestCase):
    def test_create_with_nvidia_backend(self):
        config = LLMConfig(backend="nvidia", api_key="test-key")
        client = create_client(config)
        self.assertIsInstance(client, NVIDIAClient)
        self.assertEqual(client.config.backend, "nvidia")

    def test_create_with_ollama_backend(self):
        from text_reconstructor.llm import OllamaClient
        config = LLMConfig(backend="ollama")
        client = create_client(config)
        self.assertIsInstance(client, OllamaClient)

    def test_default_creates_ollama(self):
        from text_reconstructor.llm import OllamaClient
        client = create_client()
        self.assertIsInstance(client, OllamaClient)


class TestNVIDIAClientChat(unittest.TestCase):
    def _make_response(self, content: str, model: str = "test-model"):
        resp = MagicMock()
        resp.status_code = 200
        resp.json.return_value = {
            "id": "chatcmpl-test",
            "object": "chat.completion",
            "choices": [{"message": {"role": "assistant", "content": content}, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 10, "completion_tokens": 20},
            "model": model,
        }
        resp.raise_for_status = MagicMock()
        return resp

    @patch("httpx.Client")
    def test_chat_basic(self, mock_client_cls):
        mock_client = MagicMock()
        mock_client.post.return_value = self._make_response("测试回复")
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client_cls.return_value = mock_client

        config = LLMConfig(backend="nvidia", api_key="test-key", model="deepseek-ai/deepseek-v4-flash")
        client = NVIDIAClient(config)
        result = client.chat(messages=[{"role": "user", "content": "你好"}])

        self.assertEqual(result.content, "测试回复")
        self.assertEqual(result.prompt_eval_count, 10)
        self.assertEqual(result.eval_count, 20)

    @patch("httpx.Client")
    def test_chat_with_system_prompt(self, mock_client_cls):
        mock_client = MagicMock()
        mock_client.post.return_value = self._make_response("系统回复")
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client_cls.return_value = mock_client

        config = LLMConfig(backend="nvidia", api_key="test-key")
        client = NVIDIAClient(config)
        result = client.chat(
            messages=[{"role": "user", "content": "你好"}],
            system_prompt="你是助手",
        )

        call_args = mock_client.post.call_args
        body = call_args[1]["json"] if "json" in call_args[1] else call_args[0][1]
        self.assertEqual(body["messages"][0]["role"], "system")
        self.assertEqual(body["messages"][0]["content"], "你是助手")

    @patch("httpx.Client")
    def test_chat_json(self, mock_client_cls):
        json_content = '{"key": "value"}'
        mock_client = MagicMock()
        mock_client.post.return_value = self._make_response(json_content)
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client_cls.return_value = mock_client

        config = LLMConfig(backend="nvidia", api_key="test-key")
        client = NVIDIAClient(config)
        result = client.chat_json(messages=[{"role": "user", "content": "输出JSON"}])

        self.assertEqual(result, {"key": "value"})

    @patch("httpx.Client")
    def test_request_headers(self, mock_client_cls):
        mock_client = MagicMock()
        mock_client.post.return_value = self._make_response("ok")
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client_cls.return_value = mock_client

        config = LLMConfig(backend="nvidia", api_key="nvapi-test123")
        client = NVIDIAClient(config)
        client.chat(messages=[{"role": "user", "content": "test"}])

        call_args = mock_client.post.call_args
        headers = call_args[1].get("headers", {})
        self.assertEqual(headers.get("Authorization"), "Bearer nvapi-test123")

    @patch("httpx.Client")
    def test_health_check_success(self, mock_client_cls):
        mock_client = MagicMock()
        mock_response = httpx.Response(200, json={"data": []})
        mock_client.get.return_value = mock_response
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client_cls.return_value = mock_client

        config = LLMConfig(backend="nvidia", api_key="test-key")
        client = NVIDIAClient(config)
        self.assertTrue(client.health_check())

    @patch("httpx.Client")
    def test_health_check_failure(self, mock_client_cls):
        mock_client = MagicMock()
        mock_client.get.side_effect = httpx.ConnectError("connection failed")
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client_cls.return_value = mock_client

        config = LLMConfig(backend="nvidia", api_key="test-key")
        client = NVIDIAClient(config)
        self.assertFalse(client.health_check())


if __name__ == "__main__":
    unittest.main()
