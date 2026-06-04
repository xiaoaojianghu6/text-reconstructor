"""Prosecutor 单元测试"""

import pytest
from text_reconstructor.graph.models import SemanticGraph, EdgeType
from text_reconstructor.adversary.prosecutor import Prosecution, Prosecutor


def _make_graph():
    """创建测试用图"""
    g = SemanticGraph()
    n1 = g.add_node(text="A", intent="assertive", scope="test", chunk_index=0,
                    confidence=0.6)
    n2 = g.add_node(text="B", intent="directive", scope="test", chunk_index=1,
                    confidence=0.3)
    n3 = g.add_node(text="C", intent="commissive", scope="other", chunk_index=2,
                    confidence=0.6)
    n4 = g.add_node(text="D", intent="expressive", scope="test", chunk_index=3,
                    confidence=0.4)
    return g, [n1, n2, n3, n4]


class TestProsecutorBuild:
    """Prosecutor.build() 基础功能"""

    def setup_method(self):
        self.prosecutor = Prosecutor()

    def test_build_empty(self):
        """空 alert 列表返回空 prosecution 列表"""
        graph = SemanticGraph()
        result = self.prosecutor.build([], graph)
        assert result == []

    def test_build_low_confidence(self):
        """LOW_CONFIDENCE → 正确设置 required_evidence"""
        graph, _ = _make_graph()
        alerts = [{"type": "LOW_CONFIDENCE", "node_id": 2, "text": "B",
                   "scope": "test", "detail": "置信度 0.30", "severity": "medium"}]
        result = self.prosecutor.build(alerts, graph)
        assert len(result) == 1
        assert result[0].alert_type == "LOW_CONFIDENCE"
        assert "SUPPORT" in result[0].required_evidence
        assert "incoming_support" in result[0].evidence_targets

    def test_build_isolated_node(self):
        """ISOLATED_NODE → evidence_targets 含 co_scope_neighbors"""
        graph, _ = _make_graph()
        alerts = [{"type": "ISOLATED_NODE", "node_id": 1, "text": "A",
                   "scope": "", "detail": "孤立节点", "severity": "low"}]
        result = self.prosecutor.build(alerts, graph)
        assert len(result) == 1
        assert "co_scope_neighbors" in result[0].evidence_targets

    def test_build_logic_conflict(self):
        """LOGIC_CONFLICT → evidence_targets 含 outgoing_support"""
        graph, _ = _make_graph()
        alerts = [{"type": "LOGIC_CONFLICT", "node_id": 1, "text": "A",
                   "scope": "test", "detail": "ATTACK>SUPPORT", "severity": "medium"}]
        result = self.prosecutor.build(alerts, graph)
        assert "outgoing_support" in result[0].evidence_targets

    def test_build_dangling_directive(self):
        """DANGLING_DIRECTIVE → evidence_targets 含 incoming_cause"""
        graph, _ = _make_graph()
        alerts = [{"type": "DANGLING_DIRECTIVE", "node_id": 2, "text": "B",
                   "scope": "", "detail": "指令缺原因", "severity": "medium"}]
        result = self.prosecutor.build(alerts, graph)
        assert "incoming_cause" in result[0].evidence_targets

    def test_build_structure_chaos(self):
        """STRUCTURE_CHAOS → node_id=-1, 标记为 scope 级"""
        alerts = [{"type": "STRUCTURE_CHAOS", "scope": "混乱域",
                   "detail": "密集 ATTACK+CONTRAST", "severity": "medium"}]
        graph = SemanticGraph()
        result = self.prosecutor.build(alerts, graph)
        assert len(result) == 1
        assert result[0].node_id == -1
        assert result[0].alert_type == "STRUCTURE_CHAOS"

    def test_build_round2_expansion(self):
        """Round 2 时 evidence_targets 扩展含 same_scope/global_text_match"""
        graph, _ = _make_graph()
        alerts = [{"type": "ISOLATED_NODE", "node_id": 1, "text": "A",
                   "scope": "", "detail": "孤立", "severity": "low"}]
        result = self.prosecutor.build(alerts, graph, round_num=2)
        targets = result[0].evidence_targets
        assert "same_scope" in targets
        assert "global_text_match" in targets
        assert result[0].is_escalated is True

    def test_build_round1_not_escalated(self):
        """Round 1 时不标记 is_escalated"""
        graph, _ = _make_graph()
        alerts = [{"type": "LOW_CONFIDENCE", "node_id": 2, "text": "B",
                   "scope": "", "detail": "低置信", "severity": "medium"}]
        result = self.prosecutor.build(alerts, graph, round_num=1)
        assert result[0].is_escalated is False


class TestProsecutorSpeechAct:
    """Speech-act 专项增强测试"""

    def setup_method(self):
        self.prosecutor = Prosecutor()

    def test_speech_act_assertive(self):
        """ASSERTIVE 节点 → incoming_evidence"""
        g = SemanticGraph()
        g.add_node(text="事实陈述", intent="assertive", chunk_index=0, confidence=0.6)
        alerts = [{"type": "LOW_CONFIDENCE", "node_id": 1, "text": "事实陈述",
                   "scope": "", "detail": "", "severity": "medium"}]
        result = self.prosecutor.build(alerts, g)
        assert "incoming_evidence" in result[0].evidence_targets

    def test_speech_act_commissive(self):
        """COMMISSIVE 节点 → future_reference"""
        g = SemanticGraph()
        g.add_node(text="我承诺", intent="commissive", chunk_index=0, confidence=0.6)
        alerts = [{"type": "LOW_CONFIDENCE", "node_id": 1, "text": "我承诺",
                   "scope": "", "detail": "", "severity": "medium"}]
        result = self.prosecutor.build(alerts, g)
        assert "future_reference" in result[0].evidence_targets

    def test_speech_act_expressive(self):
        """EXPRESSIVE 节点 → incoming_cause"""
        g = SemanticGraph()
        g.add_node(text="我很高兴", intent="expressive", chunk_index=0, confidence=0.6)
        alerts = [{"type": "LOW_CONFIDENCE", "node_id": 1, "text": "我很高兴",
                   "scope": "", "detail": "", "severity": "medium"}]
        result = self.prosecutor.build(alerts, g)
        assert "incoming_cause" in result[0].evidence_targets

    def test_speech_act_directive(self):
        """DIRECTIVE 节点 → incoming_background"""
        g = SemanticGraph()
        g.add_node(text="去执行", intent="directive", chunk_index=0, confidence=0.6)
        alerts = [{"type": "DANGLING_DIRECTIVE", "node_id": 1, "text": "去执行",
                   "scope": "", "detail": "", "severity": "medium"}]
        result = self.prosecutor.build(alerts, g)
        assert "incoming_background" in result[0].evidence_targets


class TestProsecutionDataclass:
    """Prosecution 数据类字段测试"""

    def test_fields_complete(self):
        """Prosecution 所有字段存取正确"""
        p = Prosecution(
            alert_type="LOW_CONFIDENCE",
            node_id=1,
            text="测试文本",
            scope="测试域",
            detail="详情",
            severity="high",
            round=2,
            required_evidence="need SUPPORT",
            evidence_targets=["incoming_support"],
            intent="assertive",
            is_escalated=True,
        )
        assert p.alert_type == "LOW_CONFIDENCE"
        assert p.node_id == 1
        assert p.text == "测试文本"
        assert p.scope == "测试域"
        assert p.detail == "详情"
        assert p.severity == "high"
        assert p.round == 2
        assert p.required_evidence == "need SUPPORT"
        assert p.evidence_targets == ["incoming_support"]
        assert p.intent == "assertive"
        assert p.is_escalated is True
