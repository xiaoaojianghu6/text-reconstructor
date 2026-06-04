"""Suggestions 单元测试 — 展示所有 alert，不做过滤"""

import pytest
from text_reconstructor.output.suggestions import Suggestions


def _alert(
    type_="LOW_CONFIDENCE",
    severity="medium",
    text="测试节点",
    scope="",
    detail="",
    node_id=1,
    round=2,
    count=1,
):
    return {
        "type": type_,
        "node_id": node_id,
        "text": text,
        "scope": scope,
        "detail": detail,
        "severity": severity,
        "round": round,
        "count": count,
    }


class TestSuggestions:
    def setup_method(self):
        self.s = Suggestions()

    def test_empty_alerts(self):
        assert self.s.format([]) == []

    def test_all_alerts_shown(self):
        """所有 alert 都应展示，不做过滤"""
        alerts = [
            _alert(type_="LOW_CONFIDENCE", text="A"),
            _alert(type_="ISOLATED_NODE", text="B"),
            _alert(type_="LOGIC_CONFLICT", text="C"),
            _alert(type_="DANGLING_DIRECTIVE", text="D"),
        ]
        out = self.s.format(alerts)
        assert len(out) == 4

    def test_single_alert(self):
        alerts = [_alert(type_="LOW_CONFIDENCE", severity="high")]
        out = self.s.format(alerts)
        assert len(out) == 1
        assert "高优先级" in out[0]

    def test_format_contains_index(self):
        alerts = [
            _alert(type_="LOW_CONFIDENCE"),
            _alert(type_="LOGIC_CONFLICT"),
        ]
        out = self.s.format(alerts)
        assert "[建议 1/2]" in out[0]
        assert "[建议 2/2]" in out[1]

    def test_severity_labels(self):
        """不同 severity 显示对应中文标签"""
        alerts = [
            _alert(type_="A", severity="high"),
            _alert(type_="B", severity="medium"),
            _alert(type_="C", severity="low"),
        ]
        out = self.s.format(alerts)
        assert "高优先级" in out[0]
        assert "中优先级" in out[1]
        assert "低优先级" in out[2]

    def test_unknown_alert_type(self):
        """未知类型应有合理输出"""
        alerts = [_alert(type_="UNKNOWN_TYPE")]
        out = self.s.format(alerts)
        assert "未知告警类型" in out[0]
