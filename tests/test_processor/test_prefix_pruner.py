"""PrefixPruner 单元测试"""

from text_reconstructor.processor.prefix_pruner import (
    clean_sentence_prefix,
    clean_batch,
)


class TestCleanPrefix:
    def test_remove_ordinal_first(self):
        assert clean_sentence_prefix("第一，我们需要做好规划") == "我们需要做好规划"

    def test_remove_ordinal_second(self):
        assert clean_sentence_prefix("第二点，执行方案") == "执行方案"

    def test_remove_ordinal_with_ge(self):
        assert clean_sentence_prefix("第三个问题是") == "问题是"

    def test_remove_zairanhou(self):
        assert clean_sentence_prefix("再然后我们发现") == "我们发现"

    def test_remove_wofaxian(self):
        assert clean_sentence_prefix("我发现啊这个问题") == "这个问题"

    def test_remove_haiyou(self):
        assert clean_sentence_prefix("还有就是这个功能") == "这个功能"

    def test_no_prefix(self):
        text = "直接进入网站的时候由于没有滑动逻辑"
        assert clean_sentence_prefix(text) == text

    def test_mid_sentence_ordinal_preserved(self):
        """句中的序数词不移除"""
        text = "这是第一种方案"
        assert clean_sentence_prefix(text) == text

    def test_empty_string(self):
        assert clean_sentence_prefix("") == ""

    def test_only_prefix(self):
        """只有前缀时保留原文本"""
        result = clean_sentence_prefix("第二")
        assert result == "第二"


class TestCleanBatch:
    def test_batch_processing(self):
        texts = [
            "第一，开始",
            "正常句子",
            "还有这个",
        ]
        result = clean_batch(texts)
        assert result[0] == "开始"
        assert result[1] == "正常句子"
        assert result[2] == "这个"
