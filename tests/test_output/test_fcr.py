"""FCR 事实覆盖率单元测试"""

from text_reconstructor.output.fcr import compute_fcr
from text_reconstructor.output.detail_anchor import DetailAnchor


class TestFCR:
    def test_full_coverage(self):
        anchors = [
            DetailAnchor("300万", "number", 0),
            DetailAnchor("https://example.com", "url", 1),
        ]
        result = compute_fcr([], "预算300万，访问https://example.com", anchors)
        assert result["fcr"] == 1.0
        assert result["missing"] == []

    def test_partial_coverage(self):
        anchors = [
            DetailAnchor("300万", "number", 0),
            DetailAnchor("500万", "number", 1),
        ]
        result = compute_fcr([], "预算300万左右", anchors)
        assert result["fcr"] == 0.5
        assert "500万" in result["missing"]

    def test_no_anchors(self):
        result = compute_fcr(["普通句子"], "重构输出")
        assert result["fcr"] == 1.0
        assert result["total"] == 0

    def test_zero_coverage(self):
        anchors = [DetailAnchor("https://lost.com", "url", 0)]
        result = compute_fcr([], "完全没有相关内容", anchors)
        assert result["fcr"] == 0.0
        assert len(result["missing"]) == 1
