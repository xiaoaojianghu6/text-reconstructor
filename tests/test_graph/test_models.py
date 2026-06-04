"""SemanticGraph 数据结构单元测试"""

import pytest
from text_reconstructor.graph.models import EdgeType, SemanticGraph, GraphNode, GraphEdge


class TestEdgeType:
    """EdgeType 枚举测试"""

    def test_from_relation(self):
        """relation 字段映射到 EdgeType"""
        assert EdgeType.from_relation("cause") == EdgeType.CAUSE
        assert EdgeType.from_relation("contrast") == EdgeType.CONTRAST
        assert EdgeType.from_relation("sequence") == EdgeType.SEQUENCE
        assert EdgeType.from_relation("none") is None

    def test_from_argument_relation(self):
        """argument_relation 字段映射"""
        assert EdgeType.from_argument_relation("support") == EdgeType.SUPPORT
        assert EdgeType.from_argument_relation("attack") == EdgeType.ATTACK
        assert EdgeType.from_argument_relation("none") is None

    def test_enum_values(self):
        """17 种枚举值（含新增 restatement）"""
        values = {e.value for e in EdgeType}
        expected = {
            "cause", "result", "evidence", "elaboration",
            "background", "sequence", "condition", "purpose",
            "contrast", "concession", "summary", "attribution",
            "evaluation", "restatement", "attack", "support", "co_scope",
            "thread_bridge", "reveal",
        }
        assert values == expected


class TestSemanticGraph:
    """SemanticGraph 容器测试"""

    def setup_method(self):
        self.g = SemanticGraph()

    def test_add_node(self):
        """添加节点后自增 id"""
        n1 = self.g.add_node(text="A")
        n2 = self.g.add_node(text="B")
        assert n1.id == 1
        assert n2.id == 2
        assert self.g.node_count() == 2

    def test_add_node_with_kwargs(self):
        """添加节点时传入字段"""
        n = self.g.add_node(
            text="测试", role="nucleus", intent="assertive",
            scope="市场分析", chunk_index=0, confidence=0.8,
        )
        assert n.text == "测试"
        assert n.role == "nucleus"
        assert n.scope == "市场分析"

    def test_get_node(self):
        """按 id 获取节点"""
        n = self.g.add_node(text="A")
        assert self.g.get_node(n.id) is n
        assert self.g.get_node(999) is None

    def test_get_nodes(self):
        """获取所有节点"""
        self.g.add_node(text="A")
        self.g.add_node(text="B")
        nodes = self.g.get_nodes()
        assert len(nodes) == 2

    def test_remove_node(self):
        """删除节点及其边"""
        n1 = self.g.add_node(text="A")
        n2 = self.g.add_node(text="B")
        self.g.add_edge(n1.id, n2.id, EdgeType.CAUSE)
        assert self.g.edge_count() == 1
        assert self.g.remove_node(n1.id) is True
        assert self.g.node_count() == 1
        assert self.g.edge_count() == 0  # 相关边也删除

    def test_remove_nonexistent(self):
        """删除不存在的节点返回 False"""
        assert self.g.remove_node(999) is False

    def test_add_edge(self):
        """添加边"""
        n1 = self.g.add_node(text="A")
        n2 = self.g.add_node(text="B")
        e = self.g.add_edge(n1.id, n2.id, EdgeType.CAUSE)
        assert e is not None
        assert e.source_id == n1.id
        assert e.target_id == n2.id
        assert e.edge_type == EdgeType.CAUSE
        assert self.g.edge_count() == 1

    def test_add_edge_dedup(self):
        """相同 (source, target, type) 不重复添加"""
        n1 = self.g.add_node(text="A")
        n2 = self.g.add_node(text="B")
        self.g.add_edge(n1.id, n2.id, EdgeType.CAUSE)
        e2 = self.g.add_edge(n1.id, n2.id, EdgeType.CAUSE)
        assert e2 is None
        assert self.g.edge_count() == 1

    def test_add_edge_nonexistent_nodes(self):
        """不存在的节点建边失败"""
        assert self.g.add_edge(1, 2, EdgeType.CAUSE) is None

    def test_get_outgoing_edges(self):
        """获取出边"""
        n1 = self.g.add_node(text="A")
        n2 = self.g.add_node(text="B")
        n3 = self.g.add_node(text="C")
        self.g.add_edge(n1.id, n2.id, EdgeType.CAUSE)
        self.g.add_edge(n1.id, n3.id, EdgeType.CONTRAST)
        edges = self.g.get_outgoing_edges(n1.id)
        assert len(edges) == 2
        cause_edges = self.g.get_outgoing_edges(n1.id, EdgeType.CAUSE)
        assert len(cause_edges) == 1

    def test_get_incoming_edges(self):
        """获取入边"""
        n1 = self.g.add_node(text="A")
        n2 = self.g.add_node(text="B")
        self.g.add_edge(n1.id, n2.id, EdgeType.SUPPORT)
        edges = self.g.get_incoming_edges(n2.id)
        assert len(edges) == 1
        support_edges = self.g.get_incoming_edges(n2.id, EdgeType.SUPPORT)
        assert len(support_edges) == 1

    def test_degree(self):
        """节点度数"""
        n1 = self.g.add_node(text="A")
        n2 = self.g.add_node(text="B")
        self.g.add_edge(n1.id, n2.id, EdgeType.CAUSE)
        assert self.g.degree(n1.id) == 1  # 出边
        assert self.g.degree(n2.id) == 1  # 入边

    def test_degree_zero(self):
        """孤立节点度数为 0"""
        n = self.g.add_node(text="A")
        assert self.g.degree(n.id) == 0

    def test_find_by_scope(self):
        """按主题域搜索"""
        self.g.add_node(text="A", scope="定价")
        self.g.add_node(text="B", scope="定价")
        self.g.add_node(text="C", scope="市场")
        assert len(self.g.find_by_scope("定价")) == 2
        assert len(self.g.find_by_scope("市场")) == 1
        assert self.g.find_by_scope("") == []

    def test_find_by_text(self):
        """按文本子串搜索"""
        self.g.add_node(text="我们产品在年轻人中很受欢迎")
        self.g.add_node(text="我们需要做市场调研")
        assert len(self.g.find_by_text("产品")) == 1
        assert len(self.g.find_by_text("我们")) == 2
        assert self.g.find_by_text("") == []

    def test_get_isolated_nodes(self):
        """孤立节点检测"""
        n1 = self.g.add_node(text="A")
        n2 = self.g.add_node(text="B")
        self.g.add_edge(n1.id, n2.id, EdgeType.CAUSE)
        n3 = self.g.add_node(text="C")  # 孤立
        isolated = self.g.get_isolated_nodes()
        assert len(isolated) == 1
        assert isolated[0].id == n3.id

    def test_to_snapshot(self):
        """快照导出"""
        n1 = self.g.add_node(text="A", role="nucleus", chunk_index=0)
        n2 = self.g.add_node(text="B", role="satellite", chunk_index=1)
        self.g.add_edge(n1.id, n2.id, EdgeType.EVIDENCE)
        snap = self.g.to_snapshot()
        assert len(snap["nodes"]) == 2
        assert len(snap["edges"]) == 1
        assert snap["alerts"] == []
        assert snap["nodes"][0]["text"] == "A"
        assert snap["edges"][0]["edge_type"] == "evidence"

    def test_to_snapshot_with_alerts(self):
        """带 alerts 的快照"""
        self.g.add_node(text="A")
        snap = self.g.to_snapshot(alerts=[{"type": "test"}])
        assert len(snap["alerts"]) == 1

    def test_tick(self):
        """全局步进"""
        self.g.tick()
        assert self.g.step == 1

    def test_clear(self):
        """清空"""
        self.g.add_node(text="A")
        self.g.add_node(text="B")
        self.g.add_edge(1, 2, EdgeType.CAUSE)
        self.g.clear()
        assert self.g.node_count() == 0
        assert self.g.edge_count() == 0

    def test_empty_graph_snapshot(self):
        """空图快照"""
        snap = self.g.to_snapshot()
        assert snap == {"nodes": [], "edges": [], "alerts": []}

    def test_multiple_edges_between_nodes(self):
        """两节点之间可以有不同类型的边"""
        n1 = self.g.add_node(text="A")
        n2 = self.g.add_node(text="B")
        self.g.add_edge(n1.id, n2.id, EdgeType.CAUSE)
        self.g.add_edge(n1.id, n2.id, EdgeType.CONTRAST)
        assert self.g.edge_count() == 2

    def test_node_defaults(self):
        """节点默认字段"""
        n = self.g.add_node(text="测试")
        assert n.role == "satellite"
        assert n.intent == "assertive"
        assert n.confidence == 0.6
        assert n.weight == 1.0
