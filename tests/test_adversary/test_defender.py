"""Defender 单元测试

每个测试构建特定图结构，验证各种搜索方法的正确性。
"""

import pytest
from text_reconstructor.graph.models import SemanticGraph, EdgeType
from text_reconstructor.adversary.defender import DefenseResult, Defender
from text_reconstructor.adversary.prosecutor import Prosecution


def _simple_prosecution(
    alert_type="LOW_CONFIDENCE",
    node_id=1,
    text="测试",
    scope="test",
    evidence_targets=None,
):
    return Prosecution(
        alert_type=alert_type,
        node_id=node_id,
        text=text,
        scope=scope,
        detail="",
        severity="medium",
        round=1,
        required_evidence="证据",
        evidence_targets=evidence_targets or ["incoming_support"],
        intent="assertive",
    )


class TestDefenderRespond:
    """Defender.respond() 基础响应"""

    def setup_method(self):
        self.defender = Defender()

    def test_respond_support_found(self):
        """SUPPORT 入边存在 → success=True, delta=+0.1"""
        g = SemanticGraph()
        n1 = g.add_node(text="支持者", chunk_index=0)
        n2 = g.add_node(text="目标", chunk_index=1)
        g.add_edge(n1.id, n2.id, EdgeType.SUPPORT)
        p = _simple_prosecution(node_id=n2.id, evidence_targets=["incoming_support"])
        result = self.defender.respond(p, g)
        assert result.success is True
        assert result.confidence_delta == 0.1

    def test_respond_no_support(self):
        """无支持证据 → success=False, delta=-0.15"""
        g = SemanticGraph()
        n1 = g.add_node(text="孤立", chunk_index=0)
        p = _simple_prosecution(node_id=n1.id, evidence_targets=["incoming_support"])
        result = self.defender.respond(p, g)
        assert result.success is False
        assert result.confidence_delta == -0.15

    def test_respond_evidence_found(self):
        """EVIDENCE 入边存在 → success=True"""
        g = SemanticGraph()
        n1 = g.add_node(text="证据源", chunk_index=0)
        n2 = g.add_node(text="目标", chunk_index=1)
        g.add_edge(n1.id, n2.id, EdgeType.EVIDENCE)
        p = _simple_prosecution(node_id=n2.id, evidence_targets=["incoming_evidence"])
        result = self.defender.respond(p, g)
        assert result.success is True

    def test_respond_background_found(self):
        """BACKGROUND 入边存在 → success=True"""
        g = SemanticGraph()
        n1 = g.add_node(text="背景", chunk_index=0)
        n2 = g.add_node(text="目标", chunk_index=1)
        g.add_edge(n1.id, n2.id, EdgeType.BACKGROUND)
        p = _simple_prosecution(node_id=n2.id, evidence_targets=["incoming_background"])
        result = self.defender.respond(p, g)
        assert result.success is True

    def test_respond_cause_found(self):
        """CAUSE 入边存在 → success=True"""
        g = SemanticGraph()
        n1 = g.add_node(text="原因", chunk_index=0)
        n2 = g.add_node(text="结果", chunk_index=1)
        g.add_edge(n1.id, n2.id, EdgeType.CAUSE)
        p = _simple_prosecution(node_id=n2.id, evidence_targets=["incoming_cause"])
        result = self.defender.respond(p, g)
        assert result.success is True

    def test_respond_co_scope_support(self):
        """CO_SCOPE 邻居有支持 → success=True"""
        g = SemanticGraph()
        n1 = g.add_node(text="邻居", scope="域", chunk_index=0)
        n2 = g.add_node(text="目标", scope="域", chunk_index=1)
        n3 = g.add_node(text="支持者", chunk_index=2)
        g.add_edge(n1.id, n2.id, EdgeType.CO_SCOPE)
        g.add_edge(n2.id, n1.id, EdgeType.CO_SCOPE)  # 双向
        g.add_edge(n3.id, n1.id, EdgeType.SUPPORT)  # 邻居被支持
        p = _simple_prosecution(node_id=n2.id, evidence_targets=["co_scope_neighbors"])
        result = self.defender.respond(p, g)
        assert result.success is True

    def test_respond_same_scope_context(self):
        """同 scope 非孤立节点 → success=True"""
        g = SemanticGraph()
        n1 = g.add_node(text="上下文", scope="产品", chunk_index=0)
        n2 = g.add_node(text="目标", scope="产品", chunk_index=1)
        g.add_edge(n1.id, n2.id, EdgeType.CAUSE)  # 使 n1 非孤立
        p = _simple_prosecution(node_id=n2.id, evidence_targets=["same_scope"])
        result = self.defender.respond(p, g)
        assert result.success is True

    def test_respond_text_match(self):
        """文本关键词匹配 → success=True"""
        g = SemanticGraph()
        # 确保有共有的 4 字词 — "分析报告" 出现在两段文本中
        n1 = g.add_node(text="分析报告精炼总结", scope="A", chunk_index=0)
        n2 = g.add_node(text="我们做了分析报告并总结", scope="B", chunk_index=1)
        g.add_edge(n1.id, n2.id, EdgeType.CAUSE)  # 使两者非孤立
        p = _simple_prosecution(node_id=n2.id, evidence_targets=["text_match"])
        result = self.defender.respond(p, g)
        assert result.success is True

    def test_respond_future_reference(self):
        """后续节点引用 → success=True"""
        g = SemanticGraph()
        n1 = g.add_node(text="开发新产品", scope="", chunk_index=0)
        n2 = g.add_node(text="我们正在开发新产品", scope="", chunk_index=2)
        p = _simple_prosecution(node_id=n1.id, evidence_targets=["future_reference"])
        result = self.defender.respond(p, g)
        assert result.success is True

    def test_respond_scope_level_skip(self):
        """node_id=-1 → 跳过辩论，delta=0"""
        p = _simple_prosecution(node_id=-1)
        g = SemanticGraph()
        result = self.defender.respond(p, g)
        assert result.success is False
        assert result.confidence_delta == 0.0

    def test_respond_reactivates_nodes(self):
        """成功辩护后相关节点 last_referenced_at 更新"""
        g = SemanticGraph()
        n1 = g.add_node(text="支持者", chunk_index=0, last_referenced_at=0)
        n2 = g.add_node(text="目标", chunk_index=1)
        g.step = 50
        g.add_edge(n1.id, n2.id, EdgeType.SUPPORT)
        p = _simple_prosecution(node_id=n2.id, evidence_targets=["incoming_support"])
        self.defender.respond(p, g)
        # n1 应被唤醒
        updated = g.get_node(n1.id)
        assert updated.last_referenced_at == 50
        assert updated.weight == 1.0

    def test_respond_empty_graph(self):
        """空图 → success=False"""
        g = SemanticGraph()
        p = _simple_prosecution(node_id=1)
        result = self.defender.respond(p, g)
        assert result.success is False

    def test_respond_nonexistent_node(self):
        """不存在的节点 → success=False"""
        g = SemanticGraph()
        g.add_node(text="存在的", chunk_index=0)
        p = _simple_prosecution(node_id=999)
        result = self.defender.respond(p, g)
        assert result.success is False

    def test_scope_support_balance_found(self):
        """同域 SUPPORT 边 >= 3 → success=True"""
        g = SemanticGraph()
        for i in range(5):
            g.add_node(text=f"节点{i}", scope="混乱域", chunk_index=i)
        nodes = g.get_nodes()
        # 建 3 条 SUPPORT 边
        g.add_edge(nodes[0].id, nodes[1].id, EdgeType.SUPPORT)
        g.add_edge(nodes[2].id, nodes[3].id, EdgeType.SUPPORT)
        g.add_edge(nodes[4].id, nodes[0].id, EdgeType.SUPPORT)
        p = _simple_prosecution(
            alert_type="STRUCTURE_CHAOS",
            node_id=nodes[1].id,
            scope="混乱域",
            evidence_targets=["same_scope_support"],
        )
        result = self.defender.respond(p, g)
        assert result.success is True

    def test_condition_edge_found(self):
        """CONDITION 入边存在 → success=True"""
        g = SemanticGraph()
        n1 = g.add_node(text="条件", chunk_index=0)
        n2 = g.add_node(text="结果", chunk_index=1)
        g.add_edge(n1.id, n2.id, EdgeType.CONDITION)
        p = _simple_prosecution(node_id=n2.id, evidence_targets=["incoming_condition"])
        result = self.defender.respond(p, g)
        assert result.success is True

    def test_outgoing_support_found(self):
        """出边 SUPPORT 存在 → success=True"""
        g = SemanticGraph()
        n1 = g.add_node(text="目标", chunk_index=0)
        n2 = g.add_node(text="被支持者", chunk_index=1)
        g.add_edge(n1.id, n2.id, EdgeType.SUPPORT)
        p = _simple_prosecution(node_id=n1.id, evidence_targets=["outgoing_support"])
        result = self.defender.respond(p, g)
        assert result.success is True


class TestDefenseResult:
    """DefenseResult 字段测试"""

    def test_dataclass_fields(self):
        result = DefenseResult(
            success=True,
            confidence_delta=0.1,
            evidence_found=[{"type": "test"}],
            reactivated_nodes=[1, 2],
            message="ok",
        )
        assert result.success is True
        assert result.confidence_delta == 0.1
        assert result.evidence_found == [{"type": "test"}]
        assert result.reactivated_nodes == [1, 2]
        assert result.message == "ok"

    def test_default_values(self):
        result = DefenseResult(success=False, confidence_delta=0.0)
        assert result.evidence_found == []
        assert result.reactivated_nodes == []
        assert result.message == ""
