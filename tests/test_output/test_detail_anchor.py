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
        """无特殊实体时，extract_from_sentences 只产出频次 >= 2 的 named_entity"""
        sentences = ["今天天气不错"]
        anchors = extract_from_sentences(sentences)
        # "今天天气不错" 只出现1次，named_entity 被频次过滤掉
        assert all(a.anchor_type != "url" for a in anchors)
        assert all(a.anchor_type != "number" for a in anchors)
        assert all(a.anchor_type != "metaphor" for a in anchors)

    def test_no_anchors_raw(self):
        """extract_anchors 可能产出低置信度 named_entity 候选"""
        text = "今天天气不错"
        anchors = extract_anchors(text)
        # 只有 named_entity 候选(低置信度)，无 url/number/metaphor
        assert not any(a.anchor_type == "url" for a in anchors)
        assert not any(a.anchor_type == "number" for a in anchors)
        assert not any(a.anchor_type == "metaphor" for a in anchors)

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

    def test_named_entity_frequency_filter(self):
        """named_entity 出现 >= 2 次才保留"""
        sentences = [
            "张三去了北京",
            "张三回来了",
        ]
        anchors = extract_from_sentences(sentences)
        ne = [a for a in anchors if a.anchor_type == "named_entity"]
        assert any(a.text == "张三" for a in ne)

    def test_named_entity_low_freq_filtered(self):
        """named_entity 只出现1次被过滤"""
        sentences = ["张三去了北京"]
        anchors = extract_from_sentences(sentences)
        ne = [a for a in anchors if a.anchor_type == "named_entity"]
        assert not any(a.text == "张三" for a in ne)


class TestCommitmentVerb:
    def test_commitment_extraction(self):
        anchors = extract_anchors("我们计划开发新产品")
        cv = [a for a in anchors if a.anchor_type == "commitment_verb"]
        assert len(cv) >= 1
        assert "计划" in cv[0].text

    def test_commitment_multiple(self):
        anchors = extract_anchors("打算明天去，准备下周回")
        cv = [a for a in anchors if a.anchor_type == "commitment_verb"]
        assert len(cv) >= 2

    def test_commitment_no_match(self):
        anchors = extract_anchors("今天天气不错")
        assert not any(a.anchor_type == "commitment_verb" for a in anchors)


class TestQuantityConstraint:
    def test_quantity_with_context(self):
        anchors = extract_anchors("项目总预算为300万元")
        qc = [a for a in anchors if a.anchor_type == "quantity_constraint"]
        assert len(qc) >= 1
        assert "300" in qc[0].text

    def test_quantity_percentage(self):
        anchors = extract_anchors("增长15%")
        qc = [a for a in anchors if a.anchor_type == "quantity_constraint"]
        assert len(qc) >= 1

    def test_quantity_with_unit(self):
        anchors = extract_anchors("需要雇佣50人")
        qc = [a for a in anchors if a.anchor_type == "quantity_constraint"]
        assert len(qc) >= 1
        assert "50人" in qc[0].text


class TestBackwardCompat:
    def test_old_types_still_work(self):
        text = "预算300万，参考 https://x.com"
        anchors = extract_anchors(text)
        types = {a.anchor_type for a in anchors}
        assert "url" in types
        assert "number" in types

    def test_detail_anchor_new_fields_default(self):
        from text_reconstructor.output.detail_anchor import DetailAnchor
        a = DetailAnchor("test", "url")
        assert a.context == ""
        assert a.confidence == 1.0
        assert a.source_index == -1
