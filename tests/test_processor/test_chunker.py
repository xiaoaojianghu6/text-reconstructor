"""Chunker 单元测试"""

import pytest
from text_reconstructor.processor.chunker import SentenceSplitter


class TestSentenceSplitter:
    """句子分割器测试"""

    def setup_method(self):
        self.splitter = SentenceSplitter()

    def test_split_simple_sentences(self):
        """基本句号分割"""
        text = "今天天气很好。我们去散步了。"
        result = self.splitter.split(text)
        assert result == ["今天天气很好。", "我们去散步了。"]

    def test_split_mixed_punctuation(self):
        """混合标点分割"""
        text = "你好吗？我很好！这是真的……对吧？"
        result = self.splitter.split(text)
        assert len(result) == 4
        assert "你好吗？" in result
        assert "我很好！" in result

    def test_split_with_newlines(self):
        """换行分段"""
        text = "第一段内容。\n\n第二段内容。"
        result = self.splitter.split(text)
        assert "第一段内容。" in result
        assert "第二段内容。" in result

    def test_merge_short_fragments(self):
        """超短无标点片段应合并"""
        text = "嗯。今天天气很好。"
        result = self.splitter.split(text)
        # "嗯。" 是完整句子（2字+标点），不应合并
        assert "嗯。" in result
        assert len(result) == 2

    def test_empty_text(self):
        """空文本"""
        assert self.splitter.split("") == []

    def test_no_punctuation(self):
        """无标点不分"""
        text = "这是一段没有标点的文本"
        result = self.splitter.split(text)
        assert result == [text]

