"""句子分割

输入文本 → SentenceSplitter → 句子列表
"""

from __future__ import annotations

import re

# 中文句末标点
_SENTENCE_END = re.compile(r"[。！？…\?]")
# 用于保留分隔符的分割
_SENTENCE_SPLIT = re.compile(r"([。！？…\?])")

# 短句合并阈值（字符数）
_SHORT_SENTENCE_MIN = 2  # 仅合并 1 字的超短片段（如"嗯""对"等无标点片段）


class SentenceSplitter:
    """句子分割器

    将原始中文文本分割为句子列表。分割策略:
    1. 优先按段间距 (\\n\\n) 分割段落
    2. 段内按句末标点（。！？…?）分割
    3. 短句（<10字）合并到前一句
    """

    def split(self, text: str) -> list[str]:
        """分割文本为句子列表"""
        paragraphs = self._split_paragraphs(text)
        sentences: list[str] = []
        for para in paragraphs:
            para_sentences = self._split_sentences(para)
            sentences.extend(para_sentences)
        return self._merge_short(sentences)

    # ------------------------------------------------------------------
    # 内部方法
    # ------------------------------------------------------------------

    @staticmethod
    def _split_paragraphs(text: str) -> list[str]:
        """按 \\n\\n 或 \\n 分割段落，过滤空段落"""
        # 先按 \\n\\n 分大段，再按 \\n 分行
        parts = re.split(r"\n\s*\n", text.strip())
        result = []
        for p in parts:
            p = p.strip()
            if p:
                result.append(p)
        return result if result else [text.strip()]

    @staticmethod
    def _split_sentences(text: str) -> list[str]:
        """按句末标点分割句子，保留分隔符"""
        if not text:
            return []
        # 用分隔符分割并保留分隔符
        parts = _SENTENCE_SPLIT.split(text)
        sentences: list[str] = []
        i = 0
        while i < len(parts):
            if i + 1 < len(parts) and _SENTENCE_END.match(parts[i + 1]):
                sentences.append(parts[i] + parts[i + 1])
                i += 2
            else:
                chunk = parts[i].strip()
                if chunk:
                    sentences.append(chunk)
                i += 1
        return sentences

    @staticmethod
    def _merge_short(sentences: list[str]) -> list[str]:
        """将超短片段（如无标点的"嗯""对"）合并到前一句"""
        if not sentences:
            return []
        merged = [sentences[0]]
        for sent in sentences[1:]:
            if len(sent) < _SHORT_SENTENCE_MIN and merged:
                merged[-1] += sent
            else:
                merged.append(sent)
        return merged
