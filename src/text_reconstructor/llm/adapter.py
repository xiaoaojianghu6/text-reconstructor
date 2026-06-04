"""LLM 适配层 - Ollama API 封装

通过 Ollama API 与 Qwen3.5 系列模型交互，提供统一的 JSON structured output 接口。
支持的模型 (Ollama naming):
  - qwen3.5:0.8b  (已有)
  - qwen3.5:4b    (推荐, Q4_K_M ~3.4 GB)
  - qwen3.5:9b    (可选, Q4_K_M ~5.6 GB)
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass, field
from typing import Any, Optional

import httpx

# 确保 localhost 请求不经过代理（避免 SOCKS 冲突）
_NO_PROXY_TRANSPORT = httpx.HTTPTransport(proxy=None)

logger = logging.getLogger(__name__)

OLLAMA_BASE_URL = "http://localhost:11434"
DEFAULT_MODEL = "qwen3.5:0.8b"
DEFAULT_TIMEOUT = 30.0


class LLMError(Exception):
    """LLM 调用基础异常"""


class LLMConnectionError(LLMError):
    """Ollama 服务不可用"""


class LLMTimeoutError(LLMError):
    """请求超时"""


class LLMResponseError(LLMError):
    """响应格式异常"""


@dataclass
class LLMConfig:
    """LLM 客户端配置"""

    model: str = DEFAULT_MODEL
    base_url: str = OLLAMA_BASE_URL
    timeout: float = DEFAULT_TIMEOUT
    temperature: float = 0.1
    max_tokens: int = 2048
    top_p: float = 0.9
    think: bool = False
    backend: str = "ollama"
    api_key: str = ""

    def to_options(self) -> dict[str, Any]:
        return {
            "temperature": self.temperature,
            "num_predict": self.max_tokens,
            "top_p": self.top_p,
        }


@dataclass
class LLMResponse:
    """标准化的 LLM 响应"""

    content: str
    model: str
    total_duration_ns: int = 0
    prompt_eval_count: int = 0
    eval_count: int = 0

    @property
    def duration_ms(self) -> float:
        return self.total_duration_ns / 1_000_000

    @property
    def tokens_per_sec(self) -> float:
        if self.eval_count > 0 and self.total_duration_ns > 0:
            return self.eval_count / (self.total_duration_ns / 1e9)
        return 0.0


class OllamaClient:
    """Ollama API 客户端，封装 /api/chat 端点"""

    def __init__(self, config: Optional[LLMConfig] = None):
        self.config = config or LLMConfig()
        self._chat_url = f"{self.config.base_url.rstrip('/')}/api/chat"

    # ------------------------------------------------------------------
    # 同步接口
    # ------------------------------------------------------------------

    def chat(
        self,
        messages: list[dict[str, str]],
        system_prompt: Optional[str] = None,
        response_format: Optional[dict] = None,
        use_stream: bool = True,
        **overrides: Any,
    ) -> LLMResponse:
        """发送聊天请求 (同步)

        Args:
            messages: [{"role": "user", "content": "..."}]
            system_prompt: 系统提示词（追加到 messages 头部）
            response_format: 若包含 {"type": "json_object"} 则开启 JSON mode
            use_stream: 使用 streaming 模式（消除 HTTP 响应体组装延迟）

        Returns:
            LLMResponse
        """
        body = self._build_body(messages, system_prompt, response_format, **overrides)
        body["stream"] = use_stream
        try:
            with httpx.Client(transport=_NO_PROXY_TRANSPORT, timeout=self.config.timeout) as client:
                if use_stream:
                    return self._chat_stream(client, body)
                resp = client.post(self._chat_url, json=body)
                resp.raise_for_status()
                return self._parse_response(resp.json())
        except httpx.ConnectError as e:
            raise LLMConnectionError(
                f"Ollama 服务未启动 ({self._chat_url}): {e}"
            ) from e
        except httpx.TimeoutException as e:
            raise LLMTimeoutError(f"请求超时 ({self.config.timeout}s): {e}") from e
        except httpx.HTTPStatusError as e:
            raise LLMResponseError(f"Ollama 返回 {e.response.status_code}: {e.response.text}") from e

    def _chat_stream(
        self,
        client: httpx.Client,
        body: dict,
    ) -> LLMResponse:
        """流式收集响应，拼装为 LLMResponse"""
        content_parts: list[str] = []
        total_duration = 0
        eval_count = 0
        prompt_eval_count = 0
        with client.stream("POST", self._chat_url, json=body) as resp:
            resp.raise_for_status()
            for line in resp.iter_lines():
                if not line:
                    continue
                try:
                    data = json.loads(line)
                    msg = data.get("message", {})
                    c = msg.get("content", "") or msg.get("thinking", "")
                    if c:
                        content_parts.append(c)
                    if data.get("done"):
                        total_duration = data.get("total_duration", 0)
                        eval_count = data.get("eval_count", 0)
                        prompt_eval_count = data.get("prompt_eval_count", 0)
                except json.JSONDecodeError:
                    continue
        return LLMResponse(
            content="".join(content_parts),
            model=self.config.model,
            total_duration_ns=total_duration,
            prompt_eval_count=prompt_eval_count,
            eval_count=eval_count,
        )

    def chat_json(
        self,
        messages: list[dict[str, str]],
        system_prompt: Optional[str] = None,
        **overrides: Any,
    ) -> dict[str, Any]:
        """发送请求并强制解析为 JSON (同步)

        Ollama 的 format: json 确保模型输出合法 JSON，但仍需 try/fallback。
        """
        body = self._build_body(messages, system_prompt, {"type": "json_object"}, **overrides)
        try:
            with httpx.Client(transport=_NO_PROXY_TRANSPORT, timeout=self.config.timeout) as client:
                resp = client.post(self._chat_url, json=body)
                resp.raise_for_status()
            raw = self._parse_response(resp.json())
            return json.loads(raw.content)
        except json.JSONDecodeError as e:
            raise LLMResponseError(f"JSON 解析失败: {e}") from e

    # ------------------------------------------------------------------
    # 异步接口
    # ------------------------------------------------------------------

    async def achat(
        self,
        messages: list[dict[str, str]],
        system_prompt: Optional[str] = None,
        response_format: Optional[dict] = None,
        **overrides: Any,
    ) -> LLMResponse:
        body = self._build_body(messages, system_prompt, response_format, **overrides)
        try:
            async with httpx.AsyncClient(transport=_NO_PROXY_TRANSPORT, timeout=self.config.timeout) as client:
                resp = await client.post(self._chat_url, json=body)
                resp.raise_for_status()
                return self._parse_response(resp.json())
        except httpx.ConnectError as e:
            raise LLMConnectionError(
                f"Ollama 服务未启动 ({self._chat_url}): {e}"
            ) from e
        except httpx.TimeoutException as e:
            raise LLMTimeoutError(f"请求超时 ({self.config.timeout}s): {e}") from e
        except httpx.HTTPStatusError as e:
            raise LLMResponseError(
                f"Ollama 返回 {e.response.status_code}: {e.response.text}"
            ) from e

    async def achat_json(
        self,
        messages: list[dict[str, str]],
        system_prompt: Optional[str] = None,
        **overrides: Any,
    ) -> dict[str, Any]:
        body = self._build_body(messages, system_prompt, {"type": "json_object"}, **overrides)
        try:
            async with httpx.AsyncClient(transport=_NO_PROXY_TRANSPORT, timeout=self.config.timeout) as client:
                resp = await client.post(self._chat_url, json=body)
                resp.raise_for_status()
            raw = self._parse_response(resp.json())
            return json.loads(raw.content)
        except json.JSONDecodeError as e:
            raise LLMResponseError(f"JSON 解析失败: {e}") from e

    # ------------------------------------------------------------------
    # 辅助接口
    # ------------------------------------------------------------------

    def health_check(self) -> bool:
        """检查 Ollama 服务是否在线"""
        url = f"{self.config.base_url.rstrip('/')}"
        try:
            with httpx.Client(transport=_NO_PROXY_TRANSPORT, timeout=5.0) as client:
                resp = client.get(url)
            return resp.status_code == 200
        except Exception:
            return False

    def list_models(self) -> list[dict]:
        """列出 Ollama 中已拉取的模型"""
        url = f"{self.config.base_url.rstrip('/')}/api/tags"
        try:
            with httpx.Client(transport=_NO_PROXY_TRANSPORT, timeout=5.0) as client:
                resp = client.get(url)
            resp.raise_for_status()
            return resp.json().get("models", [])
        except Exception:
            return []

    # ------------------------------------------------------------------
    # 内部方法
    # ------------------------------------------------------------------

    def _build_body(
        self,
        messages: list[dict[str, str]],
        system_prompt: Optional[str] = None,
        response_format: Optional[dict] = None,
        **overrides: Any,
    ) -> dict:
        full_messages = list(messages)
        if system_prompt:
            full_messages.insert(0, {"role": "system", "content": system_prompt})

        body: dict[str, Any] = {
            "model": overrides.get("model", self.config.model),
            "messages": full_messages,
            "stream": False,
            "think": overrides.get("think", self.config.think),
            "options": dict(self.config.to_options(), **{
                k: v for k, v in overrides.items()
                if k in ("temperature", "num_predict", "top_p")
            }),
        }
        if response_format and response_format.get("type") == "json_object":
            body["format"] = "json"
        return body

    def _parse_response(self, data: dict) -> LLMResponse:
        """解析 Ollama 响应，兼容 Qwen 系列的 thinking 字段。

        Qwen3.5 可能在 message.thinking 中输出推理过程，
        而 message.content 为空。此时回退到 thinking 内容。
        """
        msg = data.get("message", {})
        content = msg.get("content", "") or msg.get("thinking", "")
        return LLMResponse(
            content=content,
            model=data.get("model", self.config.model),
            total_duration_ns=data.get("total_duration", 0),
            prompt_eval_count=data.get("prompt_eval_count", 0),
            eval_count=data.get("eval_count", 0),
        )
