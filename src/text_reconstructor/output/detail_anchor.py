"""DetailAnchor - 细节锚定提取器

从原文中自动提取高价值实体（URL、数据、强特征比喻、承诺动词、数量约束、命名实体），
用于 FCR 事实覆盖率验证和实体对冲扫描。
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass


@dataclass
class DetailAnchor:
    text: str
    anchor_type: str  # url|number|metaphor|quoted_term|commitment_verb|quantity_constraint|named_entity
    source_index: int = -1
    context: str = ""
    confidence: float = 1.0


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

_COMMITMENT_PATTERN = re.compile(
    r'(计划|打算|准备|将要|即将|承诺|保证|预计|有望|拟定|决定|誓要|规划|安排|约定)'
    r'([^，。；、！？\n]{0,12})'
)

_QUANTITY_CONSTRAINT = re.compile(
    r'(\d+(?:\.\d+)?[%％])'
    r'|(\d+(?:\.\d+)?(?:万|亿)?(?:元|块|美元|人|个|次|条|篇|页|小时|天|周|月|年))'
    r'(.{0,8})'
)

_ENTITY_CANDIDATE = re.compile(r'[一-鿿]{2,4}')

_STOP_WORDS = frozenset({
    "的", "了", "是", "在", "有", "和", "就", "不", "人", "都", "一",
    "一个", "上", "也", "很", "到", "说", "要", "去", "你", "会", "着",
    "没有", "看", "好", "自己", "这", "他", "她", "它", "我", "我们",
    "这个", "那个", "什么", "怎么", "为什么", "所以", "因为", "但是",
    "可以", "可能", "如果", "就是", "还是", "或者", "而且", "然后",
    "那么", "这样", "那样", "已经", "还是", "不是", "没有", "只是",
})


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

    for m in _COMMITMENT_PATTERN.finditer(text):
        verb = m.group(1)
        obj = m.group(2).strip()
        full = f"{verb}{obj}" if obj else verb
        anchors.append(DetailAnchor(full, "commitment_verb", source_index, context=obj))

    for m in _QUANTITY_CONSTRAINT.finditer(text):
        val = m.group(1) or m.group(2)
        if not val:
            continue
        ctx = (m.group(3) or "").strip()
        anchors.append(DetailAnchor(
            val, "quantity_constraint", source_index, context=ctx,
        ))

    # named_entity: 提取所有 2-4 字中文片段(重叠)，后续由 extract_from_sentences 频次过滤
    for n in range(2, 5):
        for i in range(len(text) - n + 1):
            seg = text[i:i + n]
            if all('一' <= c <= '鿿' for c in seg) and seg not in _STOP_WORDS:
                anchors.append(DetailAnchor(seg, "named_entity", source_index, confidence=0.5))

    return anchors


def extract_from_sentences(sentences: list[str]) -> list[DetailAnchor]:
    """从句子列表提取全部锚点，对 named_entity 做频次过滤"""
    all_anchors: list[DetailAnchor] = []
    for i, s in enumerate(sentences):
        all_anchors.extend(extract_anchors(s, i))

    # named_entity 频次过滤: 出现 >= 2 次才保留
    ne_counter = Counter(
        a.text for a in all_anchors if a.anchor_type == "named_entity"
    )
    filtered: list[DetailAnchor] = []
    for a in all_anchors:
        if a.anchor_type == "named_entity":
            if ne_counter[a.text] >= 2:
                a.confidence = min(1.0, 0.5 + ne_counter[a.text] * 0.1)
                filtered.append(a)
        else:
            filtered.append(a)

    return filtered
