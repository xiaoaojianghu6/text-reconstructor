"""DetailAnchor - 细节锚定提取器

从原文中自动提取高价值实体（URL、数据、强特征比喻），
用于 FCR 事实覆盖率验证，确保重构输出100%保留这些实体。
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field


@dataclass
class DetailAnchor:
    text: str
    anchor_type: str  # "url" | "number" | "metaphor"
    source_index: int = -1


_URL_PATTERN = re.compile(r'https?://[^\s,，。；;）)、]+')
_NUMBER_PATTERN = re.compile(
    r'\d+(?:\.\d+)?[%％]'
    r'|\d+[万亿千百]+(?:元|块|美元|万)?'
    r'|\d+到\d+(?:元|块|美元)?'
    r'|\d+(?:\.\d+)?(?:万|亿)?(?:元|块|美元|人|个|次|条|篇|页|小时|天|周|月|年)'
)
_METAPHOR_MARKERS = re.compile(
    r'(?:像|如同|好比|仿佛|就像|好似|犹如|宛若)'
)
_QUOTED_TERMS = re.compile(r'[""「」『』](.{2,10})[""「」『』]')


def extract_anchors(text: str, source_index: int = -1) -> list[DetailAnchor]:
    """从单段文本中提取锚定实体"""
    anchors: list[DetailAnchor] = []

    for m in _URL_PATTERN.finditer(text):
        anchors.append(DetailAnchor(m.group(), "url", source_index))

    for m in _NUMBER_PATTERN.finditer(text):
        anchors.append(DetailAnchor(m.group(), "number", source_index))

    for m in _METAPHOR_MARKERS.finditer(text):
        end = min(len(text), m.end() + 8)
        phrase = text[m.start():end]
        anchors.append(DetailAnchor(phrase, "metaphor", source_index))

    for m in _QUOTED_TERMS.finditer(text):
        anchors.append(DetailAnchor(m.group(1), "quoted_term", source_index))

    return anchors


def extract_from_sentences(sentences: list[str]) -> list[DetailAnchor]:
    """从句子列表提取全部锚点"""
    all_anchors: list[DetailAnchor] = []
    for i, s in enumerate(sentences):
        all_anchors.extend(extract_anchors(s, i))
    return all_anchors
