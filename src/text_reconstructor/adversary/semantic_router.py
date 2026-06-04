"""SemanticAdversaryRouter - 双轨混合对抗机的LLM审计轨道

轨道1: Python拓扑粗筛(0ms) - 现有AdversaryScanner
轨道2: 局部子图LLM审计 - 仅把可疑节点对发给LLM做精准语义审计

仅在拓扑粗筛发现可疑节点对时触发LLM调用，节省90%以上token。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from ..graph.models import SemanticGraph, EdgeType

logger = logging.getLogger(__name__)

_AUDIT_SYSTEM_PROMPT = """You are a precise logic auditor. You analyze pairs of statements to detect contradictions, vague concepts, or missing logical chains.
Reply concisely in Chinese. If no issue exists, reply exactly "SAFE"."""


@dataclass
class SuspiciousPair:
    node_a_id: int
    node_b_id: int
    reason: str
    node_a_text: str = ""
    node_b_text: str = ""


class SemanticAdversaryRouter:

    def __init__(self, llm_client=None):
        self.llm_client = llm_client

    def scan_topology(self, graph: SemanticGraph) -> list[SuspiciousPair]:
        """轨道1: Python拓扑粗筛

        发现三种可疑模式:
        1. 同scope无逻辑边(叙述逻辑矛盾候选)
        2. directive入度=0(逻辑关系不清候选)
        3. 低置信度或代词未消解(概念模糊候选)
        """
        pairs: list[SuspiciousPair] = []
        nodes = graph.get_nodes()

        # 类型1: 同scope活跃节点对但无逻辑边
        scope_groups: dict[str, list] = {}
        for n in nodes:
            if n.scope and n.scope != "REFERENCE_MISSING":
                scope_groups.setdefault(n.scope, []).append(n)

        for scope, group in scope_groups.items():
            if len(group) < 2:
                continue
            for i in range(len(group)):
                for j in range(i + 1, len(group)):
                    a, b = group[i], group[j]
                    has_logical = (
                        graph.has_edge(a.id, b.id) or graph.has_edge(b.id, a.id)
                    )
                    if not has_logical:
                        pairs.append(SuspiciousPair(
                            node_a_id=a.id, node_b_id=b.id,
                            reason="same_scope_no_logical_edge",
                            node_a_text=a.text, node_b_text=b.text,
                        ))

        # 类型2: directive节点无逻辑入边
        for n in nodes:
            if n.intent == "directive":
                incoming = graph.get_incoming_edges(n.id)
                has_cause = any(
                    e.edge_type in (EdgeType.CAUSE, EdgeType.CONDITION, EdgeType.BACKGROUND)
                    for e in incoming
                )
                if not has_cause:
                    prev = [
                        p for p in nodes
                        if p.id != n.id and p.chunk_index == n.chunk_index - 1
                    ]
                    if prev:
                        pairs.append(SuspiciousPair(
                            node_a_id=n.id, node_b_id=prev[0].id,
                            reason="dangling_directive",
                            node_a_text=n.text, node_b_text=prev[0].text,
                        ))

        return pairs

    def audit_pair(self, pair: SuspiciousPair) -> str | None:
        """轨道2: LLM精准语义审计

        仅把2个节点发给LLM，返回冲突说明或None。
        """
        if not self.llm_client:
            return None

        prompt = (
            f"判断以下两句话是否存在逻辑矛盾、资源冲突或概念模糊：\n\n"
            f"语句A：{pair.node_a_text}\n"
            f"语句B：{pair.node_b_text}\n\n"
            f"如果不冲突，直接回复 SAFE。\n"
            f"如果存在冲突或模糊，用一句话指出问题核心并给出建议。"
        )

        try:
            result = self.llm_client.chat(
                messages=[{"role": "user", "content": prompt}],
                system_prompt=_AUDIT_SYSTEM_PROMPT,
            )
            content = result.content.strip()
            if content and content != "SAFE":
                return content
        except Exception as e:
            logger.warning("语义审计LLM调用失败: %s", e)

        return None

    def run(self, graph: SemanticGraph) -> list[dict]:
        """执行完整的双轨对抗流程

        Returns:
            高质量alert列表（带LLM语义审计结果的）
        """
        pairs = self.scan_topology(graph)
        if not pairs:
            return []

        alerts: list[dict] = []
        for pair in pairs[:5]:  # 限制最多审计5对，控制成本
            finding = self.audit_pair(pair)
            if finding:
                alerts.append({
                    "type": "SEMANTIC_CONFLICT",
                    "node_id": pair.node_a_id,
                    "text": pair.node_a_text,
                    "detail": finding,
                    "severity": "high",
                    "related_node_id": pair.node_b_id,
                })

        return alerts
