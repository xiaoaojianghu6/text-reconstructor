"""Suggestions 单元测试 - 只输出高危逻辑中断"""

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

    def test_only_high_severity_shown(self):
        """只输出 DANGLING_DIRECTIVE 和 LOGIC_CONFLICT"""
        alerts = [
            _alert(type_="LOW_CONFIDENCE", text="A"),
            _alert(type_="ISOLATED_NODE", text="B"),
            _alert(type_="LOGIC_CONFLICT", text="C", severity="high"),
            _alert(type_="DANGLING_DIRECTIVE", text="D", severity="medium"),
        ]
        out = self.s.format(alerts)
        assert len(out) == 2

    def test_low_severity_filtered(self):
        """low severity 的高危类型也被过滤"""
        alerts = [
            _alert(type_="LOGIC_CONFLICT", severity="low"),
            _alert(type_="DANGLING_DIRECTIVE", severity="low"),
        ]
        out = self.s.format(alerts)
        assert len(out) == 0

    def test_non_critical_types_filtered(self):
        """非高危类型全部被过滤"""
        alerts = [
            _alert(type_="LOW_CONFIDENCE", severity="high"),
            _alert(type_="ISOLATED_NODE", severity="high"),
            _alert(type_="STRUCTURE_CHAOS", severity="high"),
            _alert(type_="UNRESOLVED_PRONOUN", severity="high"),
        ]
        out = self.s.format(alerts)
        assert len(out) == 0

    def test_format_contains_index(self):
        alerts = [
            _alert(type_="LOGIC_CONFLICT", severity="medium"),
            _alert(type_="DANGLING_DIRECTIVE", severity="medium"),
        ]
        out = self.s.format(alerts)
        assert "[建议 1/2]" in out[0]
        assert "[建议 2/2]" in out[1]

    def test_severity_labels(self):
        alerts = [
            _alert(type_="LOGIC_CONFLICT", severity="high"),
            _alert(type_="DANGLING_DIRECTIVE", severity="medium"),
        ]
        out = self.s.format(alerts)
        assert "高优先级" in out[0]
        assert "中优先级" in out[1]

    def test_semantic_conflict_shown(self):
        """SEMANTIC_CONFLICT 通过过滤"""
        alerts = [_alert(type_="SEMANTIC_CONFLICT", severity="high", detail="数值矛盾")]
        out = self.s.format(alerts)
        assert len(out) == 1

    def test_entity_hedge_shown(self):
        """ENTITY_HEDGE 通过过滤"""
        alerts = [_alert(type_="ENTITY_HEDGE", severity="medium", detail="跨距离对冲")]
        out = self.s.format(alerts)
        assert len(out) == 1

    def test_entity_hedge_low_filtered(self):
        """ENTITY_HEDGE + severity=low 被过滤"""
        alerts = [_alert(type_="ENTITY_HEDGE", severity="low")]
        out = self.s.format(alerts)
        assert len(out) == 0
