"""EntityHedgeScanner -- 基于内容特征的第三轨道对抗扫描器

不依赖 Tagger 标注的图谱拓扑，直接从节点文本提取实体做跨节点一致性校验。
三项检测:
1. 跨距离实体对冲: 同一实体出现在物理距离远/不同scope的节点
2. 数值冲突: 同scope下数值矛盾
3. 承诺追踪: 承诺性语句后续无对应执行描述
"""

from __future__ import annotations

import logging
import re
from collections import defaultdict

from text_reconstructor.graph.models import GraphNode, SemanticGraph
from text_reconstructor.output.detail_anchor import DetailAnchor, extract_anchors

logger = logging.getLogger(__name__)

_IMPLICIT_CONSTRAINTS: dict[tuple[str, str], dict] = {
    ("人", "万"): {"unit_b": "元", "min_per_capita": 5000},
    ("人", "月"): {"unit_b": "元", "min_per_capita": 2000},
}

_VAL_RE = re.compile(r'(\d+(?:\.\d+)?)')
_UNIT_RE = re.compile(r'(\d+(?:\.\d+)?(?:万|亿)?)(元|块|美元|人|个|次|条|篇|页|小时|天|周|月|年|%)')


class EntityHedgeScanner:
    """实体对冲扫描器 -- 零 LLM 依赖，纯 Python 正则 + 规则"""

    def scan(self, graph: SemanticGraph) -> list[dict]:
        if graph.node_count() == 0:
            return []

        entity_map: dict[str, list[dict]] = defaultdict(list)
        for node in graph.get_nodes():
            anchors = self._extract_node_entities(node)
            for a in anchors:
                key = self._normalize(a.text)
                if key:
                    entity_map[key].append({
                        "node_id": node.id,
                        "anchor_type": a.anchor_type,
                        "text": a.text,
                        "context": a.context,
                        "chunk_index": node.chunk_index,
                        "scope": node.scope,
                    })

        alerts: list[dict] = []
        alerts.extend(self._detect_cross_distance(graph, entity_map))
        alerts.extend(self._detect_numeric_conflict(graph, entity_map))
        alerts.extend(self._detect_commitment_tracking(graph, entity_map))
        return alerts

    def _extract_node_entities(self, node: GraphNode) -> list[DetailAnchor]:
        return extract_anchors(node.text, node.chunk_index)

    @staticmethod
    def _normalize(text: str) -> str:
        t = text.strip()
        t = t.replace(",", "").replace("，", "")
        t = t.replace("％", "%")
        return t

    def _detect_cross_distance(
        self, graph: SemanticGraph, entity_map: dict[str, list[dict]],
    ) -> list[dict]:
        alerts: list[dict] = []
        seen_pairs: set[tuple[int, int]] = set()

        target_types = {"quantity_constraint", "number", "named_entity", "url"}
        for key, entries in entity_map.items():
            if len(entries) < 2:
                continue
            if entries[0]["anchor_type"] not in target_types:
                continue

            for i in range(len(entries)):
                for j in range(i + 1, len(entries)):
                    a, b = entries[i], entries[j]
                    pair = (min(a["node_id"], b["node_id"]), max(a["node_id"], b["node_id"]))
                    if pair in seen_pairs:
                        continue
                    seen_pairs.add(pair)

                    distance = abs(a["chunk_index"] - b["chunk_index"])
                    same_scope = (
                        a["scope"] and b["scope"] and a["scope"] == b["scope"]
                    )

                    if distance >= 3 and not same_scope:
                        severity = "high"
                    elif distance >= 5 and same_scope:
                        severity = "medium"
                    elif not same_scope and distance >= 2:
                        severity = "medium"
                    else:
                        continue

                    alerts.append({
                        "type": "ENTITY_HEDGE",
                        "node_id": a["node_id"],
                        "text": a["text"],
                        "scope": a["scope"],
                        "detail": (
                            f"实体「{key}」跨距离(距离={distance})出现在"
                            f"不同位置(节点{a['node_id']}与{b['node_id']})"
                        ),
                        "severity": severity,
                        "related_node_id": b["node_id"],
                        "source": "entity_hedge",
                    })
        return alerts

    def _detect_numeric_conflict(
        self, graph: SemanticGraph, entity_map: dict[str, list[dict]],
    ) -> list[dict]:
        alerts: list[dict] = []
        seen_pairs: set[tuple[int, int]] = set()

        scope_numerics: dict[str, list[dict]] = defaultdict(list)
        for key, entries in entity_map.items():
            if entries[0]["anchor_type"] not in ("quantity_constraint", "number"):
                continue
            for e in entries:
                scope_numerics[e["scope"] or "__global__"].append(e)

        for scope, items in scope_numerics.items():
            for i in range(len(items)):
                for j in range(i + 1, len(items)):
                    a, b = items[i], items[j]
                    if a["text"] == b["text"]:
                        continue
                    pair = (min(a["node_id"], b["node_id"]), max(a["node_id"], b["node_id"]))
                    if pair in seen_pairs:
                        continue

                    conflict = self._check_numeric_pair(a["text"], b["text"])
                    if conflict:
                        seen_pairs.add(pair)
                        alerts.append({
                            "type": "SEMANTIC_CONFLICT",
                            "node_id": a["node_id"],
                            "text": a["text"],
                            "scope": scope if scope != "__global__" else "",
                            "detail": conflict,
                            "severity": "high",
                            "related_node_id": b["node_id"],
                            "source": "entity_hedge",
                        })

        return alerts

    @staticmethod
    def _check_numeric_pair(text_a: str, text_b: str) -> str | None:
        m_a = _VAL_RE.search(text_a)
        m_b = _VAL_RE.search(text_b)
        if not m_a or not m_b:
            return None
        val_a = float(m_a.group(1))
        val_b = float(m_b.group(1))

        u_a = _UNIT_RE.search(text_a)
        u_b = _UNIT_RE.search(text_b)
        unit_a = u_a.group(2) if u_a else ""
        unit_b = u_b.group(2) if u_b else ""

        # 检测数值中是否包含"万"或"亿"量级
        wan_a = "万" in text_a
        wan_b = "万" in text_b

        # 同量词数值冲突
        if unit_a and unit_a == unit_b and wan_a == wan_b:
            ratio = max(val_a, val_b) / max(min(val_a, val_b), 0.01)
            if ratio > 2.0:
                return f"同主题下数值矛盾: 「{text_a}」vs「{text_b}」"

        # 隐含约束冲突 (如 "10万元" vs "50人")
        for (u1, u2), constraint in _IMPLICIT_CONSTRAINTS.items():
            # u1="人", u2="万": 一个是人数，一个是万元
            if unit_a == u1 and (unit_b == u2 or wan_b):
                real_b = val_b * 10000 if wan_b else val_b
                per_capita = real_b / val_a
                if per_capita < constraint["min_per_capita"]:
                    return f"资源约束冲突: 「{text_a}」与「{text_b}」不合理(人均{per_capita:.0f}元)"
            elif unit_b == u1 and (unit_a == u2 or wan_a):
                real_a = val_a * 10000 if wan_a else val_a
                per_capita = real_a / val_b
                if per_capita < constraint["min_per_capita"]:
                    return f"资源约束冲突: 「{text_a}」与「{text_b}」不合理(人均{per_capita:.0f}元)"

        return None

    def _detect_commitment_tracking(
        self, graph: SemanticGraph, entity_map: dict[str, list[dict]],
    ) -> list[dict]:
        alerts: list[dict] = []
        nodes = {n.id: n for n in graph.get_nodes()}

        for key, entries in entity_map.items():
            if entries[0]["anchor_type"] != "commitment_verb":
                continue

            for entry in entries:
                node = nodes.get(entry["node_id"])
                if not node:
                    continue

                context = entry["context"]
                if not context or len(context) < 2:
                    continue

                fulfilled = False
                for other in graph.get_nodes():
                    if other.id == node.id:
                        continue
                    if other.chunk_index <= node.chunk_index:
                        continue
                    # 检查后续节点文本是否包含 context 中的核心名词片段
                    if _context_overlap(context, other.text):
                        fulfilled = True
                        break

                if not fulfilled:
                    alerts.append({
                        "type": "ENTITY_HEDGE",
                        "node_id": node.id,
                        "text": node.text,
                        "scope": node.scope,
                        "detail": f"承诺「{key}」未被后续内容确认执行",
                        "severity": "medium",
                        "source": "entity_hedge",
                    })

        return alerts


def _context_overlap(context: str, target: str) -> bool:
    """检查 context 中是否有 2-4 字的中文子串出现在 target 中"""
    zh_chars = [c for c in context if '一' <= c <= '鿿']
    for n in range(min(4, len(zh_chars)), 1, -1):
        for i in range(len(zh_chars) - n + 1):
            seg = "".join(zh_chars[i:i + n])
            if seg in target:
                return True
    return False
