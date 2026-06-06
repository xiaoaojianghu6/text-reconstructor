"""EntityHedgeScanner 单元测试"""

from text_reconstructor.adversary.entity_hedge import EntityHedgeScanner
from text_reconstructor.graph.models import SemanticGraph


def _add_node(
    graph: SemanticGraph, text: str,
    scope: str = "", chunk_index: int = 0,
    intent: str = "assertive", role: str = "nucleus",
):
    return graph.add_node(
        text=text, scope=scope, chunk_index=chunk_index,
        intent=intent, role=role,
    )


class TestEmptyAndNoEntity:
    def test_empty_graph(self):
        assert EntityHedgeScanner().scan(SemanticGraph()) == []

    def test_no_special_entities(self):
        g = SemanticGraph()
        _add_node(g, "今天天气不错", "闲聊")
        alerts = EntityHedgeScanner().scan(g)
        assert not any(a["type"] == "SEMANTIC_CONFLICT" for a in alerts)


class TestCrossDistanceHedge:
    def test_same_scope_close_no_alert(self):
        g = SemanticGraph()
        _add_node(g, "项目预算为300万元", "预算", chunk_index=0)
        _add_node(g, "预算需要审批", "预算", chunk_index=1)
        alerts = EntityHedgeScanner().scan(g)
        hedge = [a for a in alerts if "跨距离" in a.get("detail", "")]
        assert len(hedge) == 0

    def test_different_scope_far_alert(self):
        g = SemanticGraph()
        _add_node(g, "项目预算为300万元", "预算", chunk_index=0)
        _add_node(g, "预算还需要考虑税收", "税务", chunk_index=5)
        alerts = EntityHedgeScanner().scan(g)
        assert any("跨距离" in a["detail"] for a in alerts)


class TestNumericConflict:
    def test_same_value_no_conflict(self):
        g = SemanticGraph()
        _add_node(g, "预算300万元", "预算", chunk_index=0)
        _add_node(g, "总额300万元", "预算", chunk_index=1)
        alerts = [a for a in EntityHedgeScanner().scan(g) if a["type"] == "SEMANTIC_CONFLICT"]
        assert len(alerts) == 0

    def test_large_numeric_conflict(self):
        g = SemanticGraph()
        _add_node(g, "预算300万元", "项目", chunk_index=0)
        _add_node(g, "需要5000万元", "项目", chunk_index=1)
        alerts = [a for a in EntityHedgeScanner().scan(g) if a["type"] == "SEMANTIC_CONFLICT"]
        assert len(alerts) >= 1
        assert "矛盾" in alerts[0]["detail"]

    def test_no_implicit_conflict_when_reasonable(self):
        g = SemanticGraph()
        _add_node(g, "总预算300万元", "项目", chunk_index=0)
        _add_node(g, "需要雇佣50人", "项目", chunk_index=1)
        alerts = [a for a in EntityHedgeScanner().scan(g) if a["type"] == "SEMANTIC_CONFLICT"]
        constraint = [a for a in alerts if "资源约束" in a["detail"]]
        assert len(constraint) == 0

    def test_implicit_conflict_when_unreasonable(self):
        g = SemanticGraph()
        _add_node(g, "总预算10万元", "项目", chunk_index=0)
        _add_node(g, "需要雇佣50人", "项目", chunk_index=1)
        alerts = [a for a in EntityHedgeScanner().scan(g) if a["type"] == "SEMANTIC_CONFLICT"]
        constraint = [a for a in alerts if "资源约束" in a["detail"]]
        assert len(constraint) >= 1


class TestCommitmentTracking:
    def test_unfulfilled_commitment(self):
        g = SemanticGraph()
        _add_node(g, "我们计划开发新产品", "产品", chunk_index=0)
        _add_node(g, "团队已经组建完成", "团队", chunk_index=1)
        alerts = EntityHedgeScanner().scan(g)
        assert any("承诺" in a["detail"] for a in alerts)

    def test_fulfilled_commitment(self):
        g = SemanticGraph()
        _add_node(g, "我们计划开发新产品", "产品", chunk_index=0)
        _add_node(g, "新产品已经上线", "产品", chunk_index=1)
        alerts = EntityHedgeScanner().scan(g)
        commitment = [a for a in alerts if "承诺" in a["detail"]]
        assert len(commitment) == 0


class TestAlertFormat:
    def test_alert_has_required_fields(self):
        g = SemanticGraph()
        _add_node(g, "预算300万元", "项目", chunk_index=0)
        _add_node(g, "需要5000万元", "项目", chunk_index=1)
        alerts = [a for a in EntityHedgeScanner().scan(g) if a["type"] == "SEMANTIC_CONFLICT"]
        assert len(alerts) >= 1
        a = alerts[0]
        for field in ("type", "node_id", "text", "scope", "detail", "severity", "source"):
            assert field in a, f"missing field: {field}"
        assert a["source"] == "entity_hedge"

    def test_scan_is_readonly(self):
        g = SemanticGraph()
        _add_node(g, "预算300万元", "项目", chunk_index=0)
        count_before = g.node_count()
        EntityHedgeScanner().scan(g)
        assert g.node_count() == count_before
