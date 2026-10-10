"""测试 LLM 审查标记提取与清理"""

from text_reconstructor.output.llm_review_extractor import (
    LLMReviewItem,
    extract_and_clean,
)


class TestExtractAndClean:
    def test_no_markers(self):
        text = "这是一段普通的文本，没有任何标记。"
        clean, items = extract_and_clean(text)
        assert clean == text
        assert items == []

    def test_single_doubt(self):
        text = "有机可寻[疑点: 含义不明，可能指'有规律可循']的内容。"
        clean, items = extract_and_clean(text)
        assert "疑点" not in clean
        assert "含义不明" not in clean
        assert len(items) == 1
        assert items[0].marker_type == "doubt"
        assert items[0].content == "含义不明，可能指'有规律可循'"

    def test_single_issue(self):
        text = "前面说A[发现的问题: 前后矛盾]后面说非A。"
        clean, items = extract_and_clean(text)
        assert "发现的问题" not in clean
        assert len(items) == 1
        assert items[0].marker_type == "issue"
        assert items[0].content == "前后矛盾"

    def test_mixed_markers(self):
        text = (
            "分词不准[疑点: 具体指标是什么]导致效果差。"
            "预算300万[发现的问题: 与50人编制矛盾]。"
        )
        clean, items = extract_and_clean(text)
        assert len(items) == 2
        assert items[0].marker_type == "doubt"
        assert items[1].marker_type == "issue"
        assert "疑点" not in clean
        assert "发现的问题" not in clean

    def test_chinese_colon(self):
        text = "测试[疑点：中文冒号]"
        clean, items = extract_and_clean(text)
        assert len(items) == 1
        assert items[0].content == "中文冒号"

    def test_position_and_surrounding(self):
        text = "前文" * 20 + "[疑点: 测试]" + "后文" * 20
        _, items = extract_and_clean(text)
        assert len(items) == 1
        assert items[0].position > 0
        assert "前文" in items[0].surrounding
        assert "后文" in items[0].surrounding

    def test_empty_output_after_clean(self):
        text = "[疑点: 空文本]"
        clean, items = extract_and_clean(text)
        assert clean == ""
        assert len(items) == 1

    def test_adjacent_markers(self):
        text = "文本[疑点: A][发现的问题: B]结尾"
        clean, items = extract_and_clean(text)
        assert len(items) == 2
        assert clean == "文本结尾"

    def test_marker_with_brackets_inside(self):
        text = "测试[疑点: 包含(括号)的内容]"
        clean, items = extract_and_clean(text)
        assert len(items) == 1
        # [^\]] 不匹配 ], 所以内容到第一个 ] 为止
        assert items[0].content == "包含(括号)的内容"

    def test_preserve_other_brackets(self):
        text = "正常引用[1]和[疑点: 问题]标记"
        clean, items = extract_and_clean(text)
        assert "[1]" in clean
        assert len(items) == 1
