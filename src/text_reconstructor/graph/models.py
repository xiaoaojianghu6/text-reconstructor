"""增量语义图谱 — 数据结构

EdgeType 枚举 (16种)、GraphNode/GraphEdge/SemanticGraph 容器。
后端基于 networkx.DiGraph。
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any

import networkx as nx


# ------------------------------------------------------------------
# EdgeType 枚举
# ------------------------------------------------------------------

class EdgeType(str, Enum):
    """边类型 — 涵盖 RST 修辞关系 + 论证关系 + 弱连接"""

    # ── RST 修辞关系 ──
    CAUSE = "cause"
    RESULT = "result"
    EVIDENCE = "evidence"
    ELABORATION = "elaboration"
    BACKGROUND = "background"
    SEQUENCE = "sequence"
    CONDITION = "condition"
    PURPOSE = "purpose"
    CONTRAST = "contrast"
    CONCESSION = "concession"
    SUMMARY = "summary"
    ATTRIBUTION = "attribution"
    EVALUATION = "evaluation"

    # ── 论证框架 ──
    ATTACK = "attack"
    SUPPORT = "support"

    # ── RST 重述 ──
    RESTATEMENT = "restatement"

    # ── 弱连接 ──
    CO_SCOPE = "co_scope"

    @classmethod
    def from_relation(cls, relation: str) -> EdgeType | None:
        """从 Chunk relation 字段映射到 EdgeType"""
        mapping = {
            "cause": cls.CAUSE,
            "result": cls.RESULT,
            "evidence": cls.EVIDENCE,
            "elaboration": cls.ELABORATION,
            "background": cls.BACKGROUND,
            "sequence": cls.SEQUENCE,
            "condition": cls.CONDITION,
            "purpose": cls.PURPOSE,
            "contrast": cls.CONTRAST,
            "concession": cls.CONCESSION,
            "summary": cls.SUMMARY,
            "attribution": cls.ATTRIBUTION,
            "evaluation": cls.EVALUATION,
            "restatement": cls.RESTATEMENT,
        }
        return mapping.get(relation)

    @classmethod
    def from_argument_relation(cls, argument_relation: str) -> EdgeType | None:
        """从 Chunk argument_relation 映射到 EdgeType"""
        mapping = {
            "support": cls.SUPPORT,
            "attack": cls.ATTACK,
        }
        return mapping.get(argument_relation)


# ------------------------------------------------------------------
# 节点和边
# ------------------------------------------------------------------

@dataclass
class GraphNode:
    id: int
    text: str
    role: str = "satellite"
    intent: str = "assertive"
    relation: str = "none"
    scope: str = ""
    chunk_index: int = 0
    confidence: float = 0.6
    weight: float = 1.0
    token_count: int = 0
    created_at: int = 0
    last_referenced_at: int = 0


@dataclass
class GraphEdge:
    source_id: int
    target_id: int
    edge_type: EdgeType
    confidence: float = 1.0


# ------------------------------------------------------------------
# SemanticGraph 容器 (networkx 后端)
# ------------------------------------------------------------------

class SemanticGraph:
    """有向语义图谱

    使用 networkx.DiGraph 作为后端存储，提供节点/边增删查和快照导出。
    GraphNode 实例作为节点属性存储，GraphEdge 实例作为边属性存储。
    节点使用自增 ID，无冲突设计。
    """

    def __init__(self) -> None:
        self._graph: nx.MultiDiGraph = nx.MultiDiGraph()
        self._next_id: int = 1
        self.step: int = 0        # 全局步进（公开，供 DecayEngine 等访问）

    # ── 节点操作 ──

    def add_node(self, **kwargs: Any) -> GraphNode:
        """添加节点，自动分配 id"""
        node_id = self._next_id
        self._next_id += 1
        node = GraphNode(id=node_id, **kwargs)
        self._graph.add_node(node_id, data=node)
        return node

    def get_node(self, node_id: int) -> GraphNode | None:
        if node_id not in self._graph:
            return None
        return self._graph.nodes[node_id].get("data")

    def get_nodes(self) -> list[GraphNode]:
        return [d.get("data") for _, d in self._graph.nodes(data=True)]

    def node_count(self) -> int:
        return self._graph.number_of_nodes()

    def remove_node(self, node_id: int) -> bool:
        """删除节点及其相关边"""
        if node_id not in self._graph:
            return False
        self._graph.remove_node(node_id)
        return True

    # ── 边操作 ──

    def add_edge(
        self,
        source_id: int,
        target_id: int,
        edge_type: EdgeType,
        confidence: float = 1.0,
    ) -> GraphEdge | None:
        """添加边（自动去重：同 source + target + type 不重复添加）"""
        if source_id not in self._graph or target_id not in self._graph:
            return None
        for _, _, d in self._graph.out_edges(source_id, data=True):
            if d.get("edge_type") == edge_type:
                return None
        edge = GraphEdge(
            source_id=source_id,
            target_id=target_id,
            edge_type=edge_type,
            confidence=confidence,
        )
        self._graph.add_edge(
            source_id, target_id,
            data=edge, edge_type=edge_type, confidence=confidence,
        )
        return edge

    def get_edges(self) -> list[GraphEdge]:
        return [d.get("data") for _, _, d in self._graph.edges(data=True)]

    def get_outgoing_edges(
        self, node_id: int, edge_type: EdgeType | None = None
    ) -> list[GraphEdge]:
        result = []
        for _, _, d in self._graph.out_edges(node_id, data=True):
            if edge_type is None or d.get("edge_type") == edge_type:
                edge = d.get("data")
                if edge:
                    result.append(edge)
        return result

    def get_incoming_edges(
        self, node_id: int, edge_type: EdgeType | None = None
    ) -> list[GraphEdge]:
        result = []
        for _, _, d in self._graph.in_edges(node_id, data=True):
            if edge_type is None or d.get("edge_type") == edge_type:
                edge = d.get("data")
                if edge:
                    result.append(edge)
        return result

    def edge_count(self) -> int:
        return self._graph.number_of_edges()

    # ── 查询 ──

    def degree(self, node_id: int) -> int:
        """节点总度数（入度 + 出度）"""
        return self._graph.degree(node_id)

    def find_by_scope(self, scope: str) -> list[GraphNode]:
        """按主题域搜索"""
        if not scope:
            return []
        return [
            d["data"] for _, d in self._graph.nodes(data=True)
            if d.get("data") and d["data"].scope == scope
        ]

    def find_by_text(self, text: str) -> list[GraphNode]:
        """按文本子串匹配（用于 dependency 解析）"""
        if not text:
            return []
        return [
            d["data"] for _, d in self._graph.nodes(data=True)
            if d.get("data") and text in d["data"].text
        ]

    def get_isolated_nodes(self) -> list[GraphNode]:
        """degree=0 的孤立节点"""
        return [
            d["data"] for n, d in self._graph.nodes(data=True)
            if d.get("data") and self._graph.degree(n) == 0
        ]

    # ── 快照导出 ──

    def to_snapshot(self, alerts: list | None = None) -> dict:
        """输出 Graph snapshot"""
        nodes = sorted(self.get_nodes(), key=lambda x: x.id)
        return {
            "nodes": [
                {
                    "id": n.id,
                    "text": n.text,
                    "role": n.role,
                    "intent": n.intent,
                    "relation": n.relation,
                    "scope": n.scope,
                    "chunk_index": n.chunk_index,
                    "confidence": n.confidence,
                    "weight": n.weight,
                }
                for n in nodes
            ],
            "edges": [
                {
                    "source_id": e.source_id,
                    "target_id": e.target_id,
                    "edge_type": e.edge_type.value,
                    "confidence": e.confidence,
                }
                for e in self.get_edges()
            ],
            "alerts": alerts or [],
        }

    # ── 生命周期 ──

    def tick(self) -> None:
        """全局步进"""
        self.step += 1

    def clear(self) -> None:
        """清空图谱"""
        self._graph.clear()
        self._next_id = 1
        self.step = 0
