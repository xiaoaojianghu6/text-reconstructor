"""Defender — 正方辩护器

根据 Prosecution 中的 evidence_targets 依次搜索证据，
找到则返回 DefenseResult(success=True)。
支持三种搜索策略：入边搜索、域搜索、全局文本匹配搜索。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from text_reconstructor.graph.models import SemanticGraph, EdgeType
from .prosecutor import Prosecution


@dataclass
class DefenseResult:
    """一轮辩护的结果"""

    success: bool  # True = 至少找到一个有效证据
    confidence_delta: float  # 成功 +0.1，失败 -0.15
    evidence_found: list[dict] = field(default_factory=list)
    reactivated_nodes: list[int] = field(default_factory=list)
    message: str = ""


class Defender:
    """正方辩护器

    根据 Prosecution 中的 evidence_targets 依次搜索证据，
    找到则返回 DefenseResult(success=True)。
    一次搜索成功即视为辩护成功。
    """

    CONFIDENCE_SUCCESS_DELTA = 0.1
    CONFIDENCE_FAIL_DELTA = -0.15

    def respond(
        self,
        prosecution: Prosecution,
        graph: SemanticGraph,
    ) -> DefenseResult:
        """针对一次起诉进行辩护

        按 evidence_targets 顺序依次尝试各搜索方法，
        找到一个有效证据即停止。

        搜索策略顺序:
        1. incoming_support      — SUPPORT 入边
        2. incoming_evidence     — EVIDENCE 入边
        3. incoming_background   — BACKGROUND 入边
        4. incoming_cause        — CAUSE 入边
        5. incoming_condition    — CONDITION 入边
        6. co_scope_neighbors    — CO_SCOPE 邻居的支持关系
        7. same_scope            — 同 scope 节点
        8. text_match            — 文本关键词匹配
        9. future_reference      — 后续节点引用
        10. outgoing_support     — 出边 SUPPORT
        11. same_scope_support   — 同域 SUPPORT 边统计
        """
        node_id = prosecution.node_id
        if node_id < 0:
            return DefenseResult(
                success=False,
                confidence_delta=0.0,
                message="scope 级 alert 跳过辩论",
            )

        node = graph.get_node(node_id)
        if node is None:
            return DefenseResult(
                success=False,
                confidence_delta=0.0,
                message=f"节点 {node_id} 不存在",
            )

        evidence_found: list[dict] = []
        searched: list[str] = []

        for target in prosecution.evidence_targets:
            method_name = f"_search_{target}"
            method = getattr(self, method_name, None)
            if method is None:
                continue
            result = method(node_id, graph, prosecution)
            searched.append(target)
            if result:
                evidence_found.extend(result)
                break

        if evidence_found:
            reactivated = self._reactivate_evidence_nodes(evidence_found, graph)
            return DefenseResult(
                success=True,
                confidence_delta=self.CONFIDENCE_SUCCESS_DELTA,
                evidence_found=evidence_found,
                reactivated_nodes=reactivated,
                message=self._format_success(prosecution, evidence_found),
            )
        else:
            return DefenseResult(
                success=False,
                confidence_delta=self.CONFIDENCE_FAIL_DELTA,
                message=self._format_failure(prosecution, searched),
            )

    # ------------------------------------------------------------------
    # 搜索方法 (每个 evidence_target 对应一个 _search_xxx)
    # ------------------------------------------------------------------

    def _search_incoming_support(
        self, node_id: int, graph: SemanticGraph, prosecution: Prosecution
    ) -> list[dict]:
        edges = graph.get_incoming_edges(node_id, EdgeType.SUPPORT)
        return [
            {
                "type": "incoming_support",
                "source_id": e.source_id,
                "node_id": e.target_id,
                "text": self._node_text(e.source_id, graph),
                "reason": f"节点 {e.source_id} 对目标提供支持",
            }
            for e in edges
            if graph.get_node(e.source_id) is not None
        ]

    def _search_incoming_evidence(
        self, node_id: int, graph: SemanticGraph, prosecution: Prosecution
    ) -> list[dict]:
        edges = graph.get_incoming_edges(node_id, EdgeType.EVIDENCE)
        return [
            {
                "type": "incoming_evidence",
                "source_id": e.source_id,
                "node_id": e.target_id,
                "text": self._node_text(e.source_id, graph),
                "reason": f"节点 {e.source_id} 为目标提供证据",
            }
            for e in edges
        ]

    def _search_incoming_background(
        self, node_id: int, graph: SemanticGraph, prosecution: Prosecution
    ) -> list[dict]:
        edges = graph.get_incoming_edges(node_id, EdgeType.BACKGROUND)
        return [
            {
                "type": "incoming_background",
                "source_id": e.source_id,
                "node_id": e.target_id,
                "text": self._node_text(e.source_id, graph),
                "reason": f"节点 {e.source_id} 为目标提供背景",
            }
            for e in edges
        ]

    def _search_incoming_cause(
        self, node_id: int, graph: SemanticGraph, prosecution: Prosecution
    ) -> list[dict]:
        edges = graph.get_incoming_edges(node_id, EdgeType.CAUSE)
        return [
            {
                "type": "incoming_cause",
                "source_id": e.source_id,
                "node_id": e.target_id,
                "text": self._node_text(e.source_id, graph),
                "reason": f"节点 {e.source_id} 为目标提供原因",
            }
            for e in edges
        ]

    def _search_incoming_condition(
        self, node_id: int, graph: SemanticGraph, prosecution: Prosecution
    ) -> list[dict]:
        edges = graph.get_incoming_edges(node_id, EdgeType.CONDITION)
        return [
            {
                "type": "incoming_condition",
                "source_id": e.source_id,
                "node_id": e.target_id,
                "text": self._node_text(e.source_id, graph),
                "reason": f"节点 {e.source_id} 为目标提供条件",
            }
            for e in edges
        ]

    def _search_outgoing_support(
        self, node_id: int, graph: SemanticGraph, prosecution: Prosecution
    ) -> list[dict]:
        """搜索出边 SUPPORT（用于 LOGIC_CONFLICT 辩护）"""
        edges = graph.get_outgoing_edges(node_id, EdgeType.SUPPORT)
        return [
            {
                "type": "outgoing_support",
                "source_id": e.source_id,
                "node_id": e.target_id,
                "text": self._node_text(e.target_id, graph),
                "reason": f"目标对节点 {e.target_id} 提供支持，显示逻辑贡献",
            }
            for e in edges
        ]

    def _search_co_scope_neighbors(
        self, node_id: int, graph: SemanticGraph, prosecution: Prosecution
    ) -> list[dict]:
        """搜索 CO_SCOPE 邻居中能提供支持的节点"""
        edges = graph.get_outgoing_edges(node_id, EdgeType.CO_SCOPE)
        evidence = []
        for e in edges:
            neighbor_id = e.target_id
            for et in [EdgeType.SUPPORT, EdgeType.EVIDENCE, EdgeType.BACKGROUND]:
                neighbor_incoming = graph.get_incoming_edges(neighbor_id, et)
                if neighbor_incoming:
                    evidence.append(
                        {
                            "type": "co_scope_support",
                            "source_id": neighbor_id,
                            "node_id": node_id,
                            "text": self._node_text(neighbor_id, graph),
                            "reason": (
                                f"CO_SCOPE 邻居 {neighbor_id} 有 "
                                f"{et.value} 入边，可提供上下文支持"
                            ),
                        }
                    )
        return evidence

    def _search_same_scope(
        self, node_id: int, graph: SemanticGraph, prosecution: Prosecution
    ) -> list[dict]:
        """搜索同 scope 节点中的支持关系"""
        node = graph.get_node(node_id)
        if not node or not node.scope:
            return []
        same_scope = graph.find_by_scope(node.scope)
        evidence = []
        for other in same_scope:
            if other.id == node_id:
                continue
            if graph.degree(other.id) > 0:
                evidence.append(
                    {
                        "type": "same_scope_context",
                        "source_id": other.id,
                        "node_id": node_id,
                        "text": other.text,
                        "reason": f"同域节点 {other.id} 提供主题上下文",
                    }
                )
                break
        return evidence

    def _search_text_match(
        self, node_id: int, graph: SemanticGraph, prosecution: Prosecution
    ) -> list[dict]:
        """通过文本关键词匹配在全图搜索相关节点

        优先匹配 scope 相同的节点，过滤常见虚词。
        """
        node = graph.get_node(node_id)
        if not node:
            return []
        _STOP_CHARS = set("的了是在有和与也就都而把被让给向从到对于但如")
        evidence = []
        for keyword in (node.text[i : i + 4] for i in range(len(node.text) - 3) if len(node.text) >= 4):
            if all(c in _STOP_CHARS for c in keyword):
                continue
            matches = graph.find_by_text(keyword)
            same_scope = [m for m in matches if m.scope == node.scope and m.id != node_id and graph.degree(m.id) > 0]
            if same_scope:
                m = same_scope[0]
                evidence.append(
                    {
                        "type": "text_match",
                        "source_id": m.id,
                        "node_id": node_id,
                        "text": m.text,
                        "reason": f"通过关键词「{keyword}」匹配到同域节点 {m.id}",
                    }
                )
                return evidence
            for m in matches:
                if m.id != node_id and graph.degree(m.id) > 0:
                    evidence.append(
                        {
                            "type": "text_match",
                            "source_id": m.id,
                            "node_id": node_id,
                            "text": m.text,
                            "reason": f"通过关键词「{keyword}」匹配到节点 {m.id}",
                        }
                    )
                    return evidence
        return []

    def _search_future_reference(
        self, node_id: int, graph: SemanticGraph, prosecution: Prosecution
    ) -> list[dict]:
        """搜索后续节点是否引用了当前节点（COMMISSIVE 检查）"""
        node = graph.get_node(node_id)
        if not node:
            return []
        later_nodes = [
            n for n in graph.get_nodes() if n.chunk_index > node.chunk_index
        ]
        for later in later_nodes:
            if node.text in later.text or later.text in node.text:
                return [
                    {
                        "type": "future_reference",
                        "source_id": later.id,
                        "node_id": node_id,
                        "text": later.text,
                        "reason": f"后续节点 {later.id} 引用了当前承诺",
                    }
                ]
            for e in graph.get_incoming_edges(later.id):
                if e.source_id == node_id:
                    return [
                        {
                            "type": "future_reference",
                            "source_id": later.id,
                            "node_id": node_id,
                            "text": later.text,
                            "reason": f"后续节点通过 {e.edge_type.value} 边引用承诺",
                        }
                    ]
        return []

    def _search_same_scope_support(
        self, node_id: int, graph: SemanticGraph, prosecution: Prosecution
    ) -> list[dict]:
        """搜索同 scope 内的 SUPPORT 边（STRUCTURE_CHAOS 辩护）"""
        scope = prosecution.scope
        if not scope:
            return []
        same_scope = graph.find_by_scope(scope)
        support_count = 0
        for n in same_scope:
            support_count += len(graph.get_incoming_edges(n.id, EdgeType.SUPPORT))
        if support_count >= 3:
            return [
                {
                    "type": "scope_support_balance",
                    "source_id": -1,
                    "node_id": node_id,
                    "text": scope,
                    "reason": f"主题域内有 {support_count} 条 SUPPORT 边，结构基本平衡",
                }
            ]
        return []

    def _search_global_text_match(
        self, node_id: int, graph: SemanticGraph, prosecution: Prosecution
    ) -> list[dict]:
        """Round 2 全局文本匹配（不限制 scope，全图搜索）"""
        node = graph.get_node(node_id)
        if not node:
            return []
        keywords = [node.text[i : i + 4] for i in range(len(node.text) - 3)]
        for kw in set(keywords):
            if len(kw) < 2:
                continue
            matches = graph.find_by_text(kw)
            for m in matches:
                if m.id != node_id and graph.degree(m.id) > 0:
                    return [
                        {
                            "type": "global_text_match",
                            "source_id": m.id,
                            "node_id": node_id,
                            "text": m.text,
                            "reason": f"Round 2 全局搜索通过「{kw}」匹配到节点 {m.id}",
                        }
                    ]
        return []

    # ------------------------------------------------------------------
    # 辅助方法
    # ------------------------------------------------------------------

    @staticmethod
    def _node_text(node_id: int, graph: SemanticGraph) -> str:
        node = graph.get_node(node_id)
        return node.text if node else ""

    @staticmethod
    def _reactivate_evidence_nodes(
        evidence: list[dict], graph: SemanticGraph
    ) -> list[int]:
        """唤醒证据中涉及的节点"""
        reactivated = []
        for ev in evidence:
            nid = ev.get("source_id")
            if nid and nid > 0:
                node = graph.get_node(nid)
                if node:
                    node.last_referenced_at = graph.step
                    node.weight = 1.0
                    reactivated.append(nid)
        return reactivated

    @staticmethod
    def _format_success(prosecution: Prosecution, evidence: list[dict]) -> str:
        return (
            f"辩护成功: 节点[{prosecution.node_id}]「{prosecution.text[:20]}」"
            f"找到 {len(evidence)} 条证据"
        )

    @staticmethod
    def _format_failure(prosecution: Prosecution, searched: list[str]) -> str:
        return (
            f"辩护失败: 节点[{prosecution.node_id}]「{prosecution.text[:20]}」"
            f"在 {searched} 方向均未找到证据"
        )
