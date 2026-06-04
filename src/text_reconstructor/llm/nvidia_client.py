"""NVIDIAClient -- OpenAI 兼容格式调用 NVIDIA Build API

通过 NVIDIA Build API 调用云端大模型（DeepSeek-V4 等），
提供与 OllamaClient 相同的接口，支持工厂切换。
"""

from __future__ import annotations

import json
import logging
import os
import time
from typing import Any, Optional

import httpx

from .adapter import LLMConfig, LLMResponse, LLMError, LLMConnectionError, LLMTimeoutError, LLMResponseError

logger = logging.getLogger(__name__)

NVIDIA_BASE_URL = "https://integrate.api.nvidia.com/v1"
NVIDIA_CHAT_ENDPOINT = "/chat/completions"
RATE_LIMIT_CAPACITY = 40
RATE_LIMIT_REFILL_PER_SEC = RATE_LIMIT_CAPACITY / 60.0


class _TokenBucket:
    def __init__(self, capacity: int, refill_per_sec: float):
        self.capacity = capacity
        self.refill_per_sec = refill_per_sec
        self.tokens: float = capacity
        self.last: float = time.monotonic()

    def acquire(self) -> float:
        now = time.monotonic()
        elapsed = now - self.last
        self.tokens = min(self.capacity, self.tokens + elapsed * self.refill_per_sec)
        self.last = now
        if self.tokens >= 1.0:
            self.tokens -= 1.0
            return 0.0
        wait = (1.0 - self.tokens) / self.refill_per_sec
        self.tokens = 0.0
        return wait


_rate_limiter = _TokenBucket(RATE_LIMIT_CAPACITY, RATE_LIMIT_REFILL_PER_SEC)


class NVIDIAClient:
    """NVIDIA Build API 客户端 (OpenAI 兼容格式)

    接口与 OllamaClient 对齐: chat / chat_json / health_check
    """

    def __init__(self, config: Optional[LLMConfig] = None):
        self.config = config or LLMConfig(
            backend="nvidia",
            model="deepseek-ai/deepseek-v4-flash",
            base_url=NVIDIA_BASE_URL,
            temperature=0.1,
            max_tokens=2048,
        )
        self._api_key = self.config.api_key or os.environ.get("NVIDIA_NIM_API_KEY", "")
        self._chat_url = f"{self.config.base_url.rstrip('/')}{NVIDIA_CHAT_ENDPOINT}"

    def chat(
        self,
        messages: list[dict[str, str]],
        system_prompt: Optional[str] = None,
        response_format: Optional[dict] = None,
        **overrides: Any,
    ) -> LLMResponse:
        full_messages = list(messages)
        if system_prompt:
            full_messages.insert(0, {"role": "system", "content": system_prompt})

        body = {
            "model": overrides.get("model", self.config.model),
            "messages": full_messages,
            "temperature": self.config.temperature,
            "max_tokens": self.config.max_tokens,
            "top_p": self.config.top_p,
            "stream": False,
        }

        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }

        self._wait_for_rate_limit()
        try:
            with httpx.Client(timeout=self.config.timeout) as client:
                resp = client.post(self._chat_url, json=body, headers=headers)
                resp.raise_for_status()
            return self._parse_response(resp.json())
        except httpx.HTTPStatusError as e:
            raise LLMResponseError(
                f"NVIDIA API 返回 {e.response.status_code}: {e.response.text[:500]}"
            ) from e
        except httpx.ConnectError as e:
            raise LLMConnectionError(f"NVIDIA API 不可达: {e}") from e
        except httpx.TimeoutException as e:
            raise LLMTimeoutError(f"NVIDIA API 超时 ({self.config.timeout}s): {e}") from e

    def chat_json(
        self,
        messages: list[dict[str, str]],
        system_prompt: Optional[str] = None,
        **overrides: Any,
    ) -> dict[str, Any]:
        raw = self.chat(messages, system_prompt, **overrides)
        try:
            return json.loads(raw.content)
        except json.JSONDecodeError as e:
            raise LLMResponseError(f"JSON 解析失败: {e}") from e

    async def achat(
        self,
        messages: list[dict[str, str]],
        system_prompt: Optional[str] = None,
        response_format: Optional[dict] = None,
        **overrides: Any,
    ) -> LLMResponse:
        self._wait_for_rate_limit()

        full_messages = list(messages)
        if system_prompt:
            full_messages.insert(0, {"role": "system", "content": system_prompt})

        body = {
            "model": overrides.get("model", self.config.model),
            "messages": full_messages,
            "temperature": self.config.temperature,
            "max_tokens": self.config.max_tokens,
            "top_p": self.config.top_p,
            "stream": False,
        }

        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }

        try:
            async with httpx.AsyncClient(timeout=self.config.timeout) as client:
                resp = await client.post(self._chat_url, json=body, headers=headers)
                resp.raise_for_status()
            return self._parse_response(resp.json())
        except httpx.ConnectError as e:
            raise LLMConnectionError(f"NVIDIA API 不可达: {e}") from e
        except httpx.TimeoutException as e:
            raise LLMTimeoutError(f"NVIDIA API 超时 ({self.config.timeout}s): {e}") from e
        except httpx.HTTPStatusError as e:
            raise LLMResponseError(
                f"NVIDIA API 返回 {e.response.status_code}: {e.response.text[:500]}"
            ) from e

    async def achat_json(
        self,
        messages: list[dict[str, str]],
        system_prompt: Optional[str] = None,
        **overrides: Any,
    ) -> dict[str, Any]:
        raw = await self.achat(messages, system_prompt, **overrides)
        try:
            return json.loads(raw.content)
        except json.JSONDecodeError as e:
            raise LLMResponseError(f"JSON 解析失败: {e}") from e

    def health_check(self) -> bool:
        url = f"{self.config.base_url.rstrip('/')}/models"
        headers = {
            "Authorization": f"Bearer {self._api_key}",
        }
        try:
            with httpx.Client(timeout=10.0) as client:
                resp = client.get(url, headers=headers)
            return resp.status_code == 200
        except Exception:
            return False

    def list_models(self) -> list[dict]:
        return [
            {"id": "deepseek-ai/deepseek-v4-pro", "owned_by": "nvidia-build"},
            {"id": "deepseek-ai/deepseek-v4-flash", "owned_by": "nvidia-build"},
        ]

    def _wait_for_rate_limit(self) -> None:
        wait = _rate_limiter.acquire()
        if wait > 0:
            logger.info("NVIDIA API 速率限制，等待 %.1f 秒", wait)
            time.sleep(wait)

    def _parse_response(self, data: dict) -> LLMResponse:
        choice = data.get("choices", [{}])[0]
        message = choice.get("message", {})
        content = message.get("content", "")
        usage = data.get("usage", {})
        return LLMResponse(
            content=content,
            model=data.get("model", self.config.model),
            prompt_eval_count=usage.get("prompt_tokens", 0),
            eval_count=usage.get("completion_tokens", 0),
        )
