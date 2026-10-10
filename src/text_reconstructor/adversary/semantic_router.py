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
Reply concisely in Chinese. For each pair, reply "对N: SAFE" if no issue, or "对N: <一句话问题描述>" if there is an issue."""


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
        """
        pairs: list[SuspiciousPair] = []
        nodes = graph.get_nodes()
        seen: set[tuple[int, int]] = set()

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
                    key = (min(a.id, b.id), max(a.id, b.id))
                    if key in seen:
                        continue
                    seen.add(key)
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

    def _batch_audit_pairs(self, pairs: list[SuspiciousPair]) -> dict[int, str]:
        """一次 LLM 调用审计所有 pairs，返回 {索引: 冲突说明}"""
        if not self.llm_client or not pairs:
            return {}

        parts = []
        for i, pair in enumerate(pairs, 1):
            parts.append(f"对{i}:\n语句A：{pair.node_a_text}\n语句B：{pair.node_b_text}")
        prompt = "请逐对判断以下语句对是否存在逻辑矛盾、资源冲突或概念模糊：\n\n" + "\n\n".join(parts)
        prompt += "\n\n对每对回复:\n对N: SAFE\n或\n对N: <冲突说明>"

        try:
            result = self.llm_client.chat(
                messages=[{"role": "user", "content": prompt}],
                system_prompt=_AUDIT_SYSTEM_PROMPT,
                max_retries=1,
            )
            content = result.content.strip()
        except Exception as e:
            logger.warning("批量语义审计LLM调用失败: %s", e)
            return {}

        findings: dict[int, str] = {}
        import re
        for m in re.finditer(r'对(\d+)[:：]\s*(.+)', content):
            idx = int(m.group(1)) - 1
            text = m.group(2).strip()
            if text and text.upper() != "SAFE":
                findings[idx] = text
        return findings

    def run(self, graph: SemanticGraph) -> list[dict]:
        """执行完整的双轨对抗流程 (批量审计版)"""
        pairs = self.scan_topology(graph)
        if not pairs:
            return []

        # 最多审计5对（控制prompt长度），一次LLM调用全审
        candidates = pairs[:5]
        findings = self._batch_audit_pairs(candidates)

        alerts: list[dict] = []
        for i, pair in enumerate(candidates):
            finding = findings.get(i)
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
