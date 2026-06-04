"""TextOutput 单元测试"""

import pytest
from text_reconstructor.output.text_output import TextOutput


def _node(id_, text, role="nucleus", scope="", chunk_index=0, **kw):
    return {
        "id": id_,
        "text": text,
        "role": role,
        "intent": "assertive",
        "relation": "none",
        "scope": scope,
        "chunk_index": chunk_index,
        "confidence": 0.6,
        "weight": 1.0,
        **kw,
    }


def _edge(source_id, target_id, edge_type, **kw):
    return {
        "source_id": source_id,
        "target_id": target_id,
        "edge_type": edge_type,
        "confidence": 1.0,
        **kw,
    }


class TestTextOutputEmpty:
    def setup_method(self):
        self.t = TextOutput()

    def test_empty_graph(self):
        assert self.t.format({"nodes": [], "edges": [], "alerts": []}) == ""

    def test_no_nodes_key(self):
        assert self.t.format({}) == ""


class TestTextOutputSingleNode:
    def setup_method(self):
        self.t = TextOutput()

    def test_single_node(self):
        snap = {"nodes": [_node(1, "测试文本")], "edges": [], "alerts": []}
        out = self.t.format(snap)
        assert "测试文本" in out
        assert "\t" not in out  # 无多余控制字符


class TestTextOutputTopoSort:
    def setup_method(self):
        self.t = TextOutput()

    def test_cause_chain_ordering(self):
        """cause→result 链 → cause 在前"""
        snap = {
            "nodes": [
                _node(1, "结果", chunk_index=1),
                _node(2, "原因", chunk_index=0),
            ],
            "edges": [_edge(2, 1, "cause")],
            "alerts": [],
        }
        out = self.t.format(snap)
        cause_pos = out.index("原因")
        result_pos = out.index("结果")
        assert cause_pos < result_pos

    def test_cycle_handling(self):
        """循环图 → 回退到 chunk_index"""
        snap = {
            "nodes": [
                _node(1, "B", chunk_index=1),
                _node(2, "A", chunk_index=0),
            ],
            "edges": [
                _edge(1, 2, "support"),
                _edge(2, 1, "support"),
            ],
            "alerts": [],
        }
        out = self.t.format(snap)
        assert "A" in out
        assert "B" in out

    def test_co_scope_ignored_in_sort(self):
        """CO_SCOPE 不影响拓扑排序"""
        snap = {
            "nodes": [
                _node(1, "后", chunk_index=1),
                _node(2, "前", chunk_index=0),
            ],
            "edges": [_edge(1, 2, "co_scope"), _edge(2, 1, "co_scope")],
            "alerts": [],
        }
        out = self.t.format(snap)
        assert "前" in out
        assert "后" in out


class TestTextOutputPrefix:
    def setup_method(self):
        self.t = TextOutput()

    def test_support_prefix(self):
        """SUPPORT 子节点 → + 前缀"""
        snap = {
            "nodes": [
                _node(1, "核心", chunk_index=0),
                _node(2, "支持论据", chunk_index=1),
            ],
            "edges": [_edge(1, 2, "support")],
            "alerts": [],
        }
        out = self.t.format(snap)
        assert "+" in out
        assert "核心" in out
        assert "支持论据" in out

    def test_attack_prefix(self):
        """ATTACK 子节点 → - 前缀"""
        snap = {
            "nodes": [
                _node(1, "论点", chunk_index=0),
                _node(2, "反驳", chunk_index=1),
            ],
            "edges": [_edge(1, 2, "attack")],
            "alerts": [],
        }
        out = self.t.format(snap)
        assert "-" in out
        assert "反驳" in out

    def test_progressive_arrow(self):
        """CAUSE→RESULT → → 前缀"""
        snap = {
            "nodes": [
                _node(1, "原因", chunk_index=0),
                _node(2, "结果", chunk_index=1),
            ],
            "edges": [_edge(1, 2, "cause")],
            "alerts": [],
        }
        out = self.t.format(snap)
        assert "→" in out
        assert "结果" in out

    def test_root_node_no_prefix(self):
        """根节点无前缀"""
        snap = {
            "nodes": [
                _node(1, "核心论点", chunk_index=0),
            ],
            "edges": [],
            "alerts": [],
        }
        out = self.t.format(snap)
        assert not out.startswith("+")
        assert not out.startswith("-")
        assert not out.startswith("→")


class TestTextOutputScope:
    def setup_method(self):
        self.t = TextOutput()

    def test_scope_grouping(self):
        """不同 scope 分组输出"""
        snap = {
            "nodes": [
                _node(1, "市场分析", scope="市场", chunk_index=0),
                _node(2, "产品设计", scope="产品", chunk_index=1),
            ],
            "edges": [],
            "alerts": [],
        }
        out = self.t.format(snap)
        assert "## 市场" in out
        assert "## 产品" in out

    def test_empty_scope_grouped(self):
        """scope="" 归入 其他"""
        snap = {
            "nodes": [
                _node(1, "无域内容", scope="", chunk_index=0),
            ],
            "edges": [],
            "alerts": [],
        }
        out = self.t.format(snap)
        assert "其他" in out


class TestTextOutputNested:
    def setup_method(self):
        self.t = TextOutput()

    def test_indentation_depth(self):
        """多层嵌套 → 正确递进缩进"""
        snap = {
            "nodes": [
                _node(1, "根", chunk_index=0),
                _node(2, "子", chunk_index=1),
                _node(3, "孙", chunk_index=2),
            ],
            "edges": [
                _edge(1, 2, "support"),
                _edge(2, 3, "support"),
            ],
            "alerts": [],
        }
        out = self.t.format(snap)
        lines = [l for l in out.split("\n") if l.strip()]
        # "根" 无缩进， "子" 缩进 2， "孙" 缩进 4
        root_line = [l for l in lines if "根" in l][0]
        child_line = [l for l in lines if "子" in l][0]
        grand_line = [l for l in lines if "孙" in l][0]
        assert not root_line.startswith(" ")  # 无缩进
        assert child_line.startswith("  ")      # 缩进 2
        assert grand_line.startswith("    ")    # 缩进 4

    def test_mixed_relations(self):
        """混合关系正确标记"""
        snap = {
            "nodes": [
                _node(1, "主论点", chunk_index=0),
                _node(2, "支持", chunk_index=1),
                _node(3, "反驳", chunk_index=2),
            ],
            "edges": [
                _edge(1, 2, "support"),
                _edge(1, 3, "attack"),
            ],
            "alerts": [],
        }
        out = self.t.format(snap)
        support_line = [l for l in out.split("\n") if "支持" in l][0]
        attack_line = [l for l in out.split("\n") if "反驳" in l][0]
        assert "+" in support_line
        assert "-" in attack_line

    def test_large_graph_all_nodes_output(self):
        """多节点图 → 所有节点都被输出"""
        nodes = [_node(i, f"节点{i}", chunk_index=i) for i in range(10)]
        edges = []
        for i in range(9):
            edges.append(_edge(i, i + 1, "support"))
        snap = {"nodes": nodes, "edges": edges, "alerts": []}
        out = self.t.format(snap)
        for i in range(10):
            assert f"节点{i}" in out
