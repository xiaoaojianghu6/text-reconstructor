"""LLM 客户端工厂 -- 根据 backend 配置创建对应的客户端"""

from __future__ import annotations

from typing import Optional

from .adapter import LLMConfig, OllamaClient


def create_client(config: Optional[LLMConfig] = None):
    """创建 LLM 客户端

    Args:
        config: LLM 配置，None 时使用默认 Ollama 配置

    Returns:
        OllamaClient 或 NVIDIAClient (OpenAI 兼容) 实例
    """
    if config is None:
        config = LLMConfig()

    if config.backend == "nvidia":
        from .nvidia_client import NVIDIAClient
        return NVIDIAClient(config)

    if config.backend == "deepseek":
        from .nvidia_client import NVIDIAClient
        ds_config = LLMConfig(
            backend="deepseek",
            model=config.model or "deepseek-chat",
            base_url=config.base_url or "https://api.deepseek.com/v1",
            api_key=config.api_key or "",
            temperature=config.temperature,
            max_tokens=config.max_tokens,
            timeout=config.timeout,
            top_p=config.top_p,
            think=config.think,
        )
        return NVIDIAClient(ds_config)

    return OllamaClient(config)
