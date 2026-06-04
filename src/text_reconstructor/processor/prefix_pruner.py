"""PrefixPruner - 句子级前缀去噪

移除线性表达中的序数词脚手架（"第一"、"第二"、"再然后"等）。
在图谱完成逻辑重组后，这些脚手架不再有结构意义。
"""

from __future__ import annotations

import re

_PREFIX_PATTERN = re.compile(
    r"^("
    r"第[一二三四五六七八九十]+(?:个|点|部分|步)?\s*[,，、]?\s*"
    r"|其次\s*[,，、]?\s*"
    r"|再然后\s*[,，、]?\s*"
    r"|我发现[啊]?[,，、]?\s*"
    r"|就是说\s*[,，、]?\s*"
    r"|还有就是\s*[,，、]?\s*"
    r"|哦对了\s*[,，、]?\s*"
    r"|然后呢\s*[,，、]?\s*"
    r"|还有[啊]?[,，、]?\s*"
    r"|另外[啊]?[,，、]?\s*"
    r")"
)


def clean_sentence_prefix(text: str) -> str:
    """移除句子开头的序数词脚手架"""
    cleaned = _PREFIX_PATTERN.sub("", text)
    return cleaned.strip() if cleaned else text


def clean_batch(texts: list[str]) -> list[str]:
    """批量去噪"""
    return [clean_sentence_prefix(t) for t in texts]
