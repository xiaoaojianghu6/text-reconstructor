"""ActiveBuffer -- 跨距离上下文对齐

基于 DecayEngine 的节点激活/衰减池管理。
替代之前的空壳占位符。
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from ..graph.decay import DecayEngine

logger = logging.getLogger(__name__)


class ActiveBuffer:
    """活跃节点缓冲池

    管理当前处于激活状态的图谱节点，
    提供 Top-K 选择和衰减池打捞能力。

    Args:
        max_size: 最大激活节点数
        eviction_threshold: 驱逐权重阈值
    """

    def __init__(self, max_size: int = 20, eviction_threshold: float = 0.4):
        self.nodes: list[Any] = []
        self.decay_pool: dict[int, Any] = {}
        self.max_size = max_size
        self.eviction_threshold = eviction_threshold
        self.step_counter: int = 0
        self._decay_engine = DecayEngine()

    def add_node(self, node: Any) -> None:
        self.nodes.append(node)
        if len(self.nodes) > self.max_size:
            self._evict()

    def tick(self, tokens: int = 1) -> None:
        self.step_counter += tokens
        self._apply_decay()

    def get_top_k(self, k: int = 3) -> list[Any]:
        sorted_nodes = sorted(
            self.nodes,
            key=lambda n: getattr(n, "weight", 1.0),
            reverse=True,
        )
        return sorted_nodes[:k]

    def reference(self, node_id: int) -> None:
        for node in self.nodes:
            if getattr(node, "id", None) == node_id:
                self._decay_engine.reactivate(node, self.step_counter)
                return
        if node_id in self.decay_pool:
            node = self.decay_pool.pop(node_id)
            self._decay_engine.reactivate(node, self.step_counter)
            self.nodes.append(node)

    def scavenge(self, query: str) -> Optional[Any]:
        for node_id, node in list(self.decay_pool.items()):
            text = getattr(node, "text", "")
            if query in text or text in query:
                self.decay_pool.pop(node_id)
                self._decay_engine.reactivate(node, self.step_counter)
                self.nodes.append(node)
                return node
        return None

    def get_active_summary(self) -> list[dict]:
        top = self.get_top_k(3)
        return [
            {
                "text": getattr(n, "text", ""),
                "role": getattr(n, "role", ""),
                "relation": getattr(n, "relation", ""),
                "scope": getattr(n, "scope", ""),
            }
            for n in top
        ]

    def _apply_decay(self) -> None:
        to_evict = []
        for node in self.nodes:
            age = self.step_counter - getattr(node, "last_referenced_at", 0)
            role = getattr(node, "role", "satellite")
            weight = self._decay_engine.compute_weight(age, 1.0, role)
            node.weight = weight
            if weight < self.eviction_threshold:
                to_evict.append(node)

        for node in to_evict:
            self.nodes.remove(node)
            self.decay_pool[getattr(node, "id", id(node))] = node

    def _evict(self) -> None:
        if not self.nodes:
            return
        lowest = min(self.nodes, key=lambda n: getattr(n, "weight", 1.0))
        self.nodes.remove(lowest)
        self.decay_pool[getattr(lowest, "id", id(lowest))] = lowest
