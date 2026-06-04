"""DetailAnchor 单元测试"""

from text_reconstructor.output.detail_anchor import (
    extract_anchors,
    extract_from_sentences,
)


class TestExtractAnchors:
    def test_url_extraction(self):
        text = "参考 https://example.com/docs 了解更多"
        anchors = extract_anchors(text)
        assert any(a.anchor_type == "url" and "example.com" in a.text for a in anchors)

    def test_number_extraction(self):
        text = "预算大约300万元"
        anchors = extract_anchors(text)
        assert any("300" in a.text for a in anchors)

    def test_percentage_extraction(self):
        text = "增长了15%"
        anchors = extract_anchors(text)
        assert any("15%" in a.text for a in anchors)

    def test_range_extraction(self):
        text = "价格在1500到1800元之间"
        anchors = extract_anchors(text)
        assert any("1500" in a.text for a in anchors)

    def test_metaphor_extraction(self):
        text = "这个效果像手风琴一样展开"
        anchors = extract_anchors(text)
        assert any(a.anchor_type == "metaphor" for a in anchors)

    def test_no_anchors(self):
        text = "今天天气不错"
        anchors = extract_anchors(text)
        assert len(anchors) == 0

    def test_multiple_anchors(self):
        text = "访问 https://example.com 获取300万用户数据，像抽纸一样简单"
        anchors = extract_anchors(text)
        types = {a.anchor_type for a in anchors}
        assert "url" in types
        assert "number" in types
        assert "metaphor" in types


class TestExtractFromSentences:
    def test_multiple_sentences(self):
        sentences = [
            "预算300万",
            "访问 https://example.com",
            "普通句子",
        ]
        anchors = extract_from_sentences(sentences)
        assert len(anchors) >= 2
        assert all(a.source_index >= 0 for a in anchors)
