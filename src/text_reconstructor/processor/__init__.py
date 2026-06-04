"""Processor 包 — 文本预处理

提供句子分割 + LLM 结构化标注。
"""

from .chunker import SentenceSplitter
from .tagger import Tagger, validate_chunk, apply_signal_corrections, \
    apply_intent_corrections, infer_scope, check_pronouns

__all__ = [
    "SentenceSplitter",
    "Tagger",
    "validate_chunk",
    "apply_signal_corrections",
]
