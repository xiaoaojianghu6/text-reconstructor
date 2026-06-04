"""GraphUpdater — 增量更新 + 建边规则 + 对抗机集成

从 ChunkDict 流增量构建语义图谱，全部基于纯 Python 规则（零 LLM）。
"""

from __future__ import annotations

import logging
from typing import Any

from .models import EdgeType, SemanticGraph, GraphNode
from .decay import DecayEngine

logger = logging.getLogger(__name__)


class GraphUpdater:
    """图谱增量更新器

    输入: list[ChunkDict]（来自 Processor）
    输出: snapshot dict（给 Output 模块，含 alerts）

    建边规则（全纯 Python 映射，无 LLM 调用）：

    规则 1 — relation 直映边
      非 "none" 的 relation 值映射为对应 EdgeType 边，
      target = 窗口中最近的 nucleus 节点或前一个节点

    规则 2 — argument_relation 直映边
      "support" → SUPPORT 边，"attack" → ATTACK 边

    规则 3 — CO_SCOPE 弱连接
      scope 相同且 chunk_index 差 < 5 的节点建 CO_SCOPE 双向边

    规则 4 — DEPENDS 依赖边
      dependency 非空时，在图中查找匹配节点建 DEPENDS 边

    对抗机集成 — process() 返回的 alerts 由 Adversary 填充
    """

    def __init__(
        self,
        decay_rate: float = 0.001,
        co_scope_distance: int = 5,
        run_adversary: bool = True,
    ):
        self.graph = SemanticGraph()
        self._decay_rate = decay_rate
        self._co_scope_distance = co_scope_distance
        self._run_adversary = run_adversary
        self._decay_engine = DecayEngine()

    # ── 公开接口 ──

    def process(
        self,
        chunks: list[dict],
        run_adversary: bool | None = None,
    ) -> dict:
        """处理 ChunkDict 列表，增量构建图谱

        Args:
            chunks: Processor 输出的 ChunkDict 列表
            run_adversary: 覆盖构造函数的 run_adversary 设置

        Returns:
            snapshot dict: {"nodes": [...], "edges": [...], "alerts": [...]}
        """
        self.graph = SemanticGraph()

        for chunk in chunks:
            self._process_one(chunk)

        # 对抗机扫描
        adversary = (
            run_adversary if run_adversary is not None
            else self._run_adversary
        )
        alerts = []
        if adversary:
            alerts = self._run_adversary_cycle()

        return self.graph.to_snapshot(alerts=alerts)

    def get_graph(self) -> SemanticGraph:
        return self.graph

    # ── 对抗机 ──

    def _run_adversary_cycle(self) -> list[dict]:
        """执行完整的对抗机正反方辩论流程

        步骤:
        1. Scanner 全图扫描
        2. Prosecutor 结构化 alert → Prosecution 列表
        3. 按 node_id 分组
        4. 每节点依次运行 ConfidenceManager.run_node_cycle()
        5. STRUCTURE_CHAOS 等 scope 级 alert 直接入 buffer
        6. 返回 AlertBuffer 中的最终 alert 列表
        """
        from .decay import AdversaryScanner
        from ..adversary.prosecutor import Prosecutor
        from ..adversary.defender import Defender
        from ..adversary.alert_buffer import ConfidenceManager

        # Step 1: 扫描
        scanner = AdversaryScanner()
        raw_alerts = scanner.scan(self.graph)

        if not raw_alerts:
            return []

        # Step 2: 结构化
        prosecutor = Prosecutor()
        defender = Defender()
        conf_manager = ConfidenceManager()

        prosecutions = prosecutor.build(raw_alerts, self.graph, round_num=1)

        # Step 3 & 4: 按 node_id 分组辩论
        node_groups: dict[int, list] = {}
        scope_alerts: list = []

        for p in prosecutions:
            if p.node_id < 0:
                scope_alerts.append(p)
            else:
                node_groups.setdefault(p.node_id, []).append(p)

        # Step 4: 逐节点辩论
        for node_id, node_prosecutions in node_groups.items():
            conf_manager.run_node_cycle(
                node_id=node_id,
                prosecutions=node_prosecutions,
                graph=self.graph,
                prosecutor=prosecutor,
                defender=defender,
            )

        # Step 5: scope 级 alert 直接入 buffer
        for p in scope_alerts:
            conf_manager.run_scope_cycle(p, self.graph)

        # Step 6: 返回最终 alerts
        return conf_manager.get_alerts()

    # ── 单 chunk 处理 ──

    def _process_one(self, chunk: dict) -> int:
        """处理单个 ChunkDict

        Returns:
            新建节点的 id
        """
        chunk_index = chunk.get("chunk_index", self.graph.step)
        text = chunk.get("text", "")

        # Step A: 创建节点
        node = self.graph.add_node(
            text=text,
            role=chunk.get("role", "satellite"),
            intent=chunk.get("intent", "assertive"),
            relation=chunk.get("relation", "none"),
            scope=chunk.get("scope", ""),
            chunk_index=chunk_index,
            confidence=chunk.get("confidence", 0.6),
            weight=1.0,
            token_count=len(text),
            created_at=self.graph.step,
            last_referenced_at=self.graph.step,
        )

        # Step B: relation 直映边
        relation = chunk.get("relation", "none")
        edge_type = EdgeType.from_relation(relation)
        if edge_type:
            target = self._find_relation_target(node, relation)
            if target is not None:
                self.graph.add_edge(node.id, target.id, edge_type)

        # Step C: argument_relation 直映边
        arg_rel = chunk.get("argument_relation", "none")
        arg_edge = EdgeType.from_argument_relation(arg_rel)
        if arg_edge:
            target = self._find_argument_target(node)
            if target is not None:
                self.graph.add_edge(node.id, target.id, arg_edge)

        # Step D: CO_SCOPE 弱连接
        scope = chunk.get("scope", "")
        if scope:
            self._add_co_scope_edges(node)

        # Step E: DEPENDS 依赖边
        dependency = chunk.get("dependency", "")
        if dependency:
            self._add_depends_edge(node, dependency)

        # Step F: 应用衰减
        self._apply_decay_to_all()

        self.graph.tick()
        return node.id

    # ── 建边规则实现 ──

    def _find_relation_target(self, node: GraphNode, relation: str) -> GraphNode | None:
        """找到 relation 边的 target 节点

        改进策略：
        - contrast/concession 优先找相同 scope 的节点
        - cause/result 允许跨 scope 但优先近距离
        - 其他关系优先选最近的 nucleus
        """
        candidates = [n for n in self.graph.get_nodes()
                      if n.id != node.id and n.chunk_index < node.chunk_index]
        if not candidates:
            return None

        if relation in ("contrast", "concession") and node.scope:
            same_scope = [n for n in candidates if n.scope == node.scope]
            if same_scope:
                nuclei = [n for n in same_scope if n.role == "nucleus"]
                if nuclei:
                    return max(nuclei, key=lambda n: n.chunk_index)
                return max(same_scope, key=lambda n: n.chunk_index)

        nuclei = [n for n in candidates if n.role == "nucleus"]
        if nuclei:
            return max(nuclei, key=lambda n: n.chunk_index)
        return max(candidates, key=lambda n: n.chunk_index)

    def _find_argument_target(self, node: GraphNode) -> GraphNode | None:
        """找到 argument 边的 target

        改进策略：
        - attack 优先在相同 scope 内查找
        - premise 优先找 argument_role=claim 的节点
        """
        candidates = [
            n for n in self.graph.get_nodes()
            if n.id != node.id and n.chunk_index < node.chunk_index
        ]
        candidates.sort(key=lambda n: n.chunk_index, reverse=True)
        if not candidates:
            return None

        if node.scope:
            same_scope = [n for n in candidates if n.scope == node.scope]
            for n in same_scope:
                if n.intent in ("assertive", "directive") and n.relation != "none":
                    return n

        for n in candidates:
            if n.intent in ("assertive", "directive") and n.relation != "none":
                return n
        return candidates[0]

    def _add_co_scope_edges(self, node: GraphNode) -> None:
        """添加同域弱连接"""
        same_scope = [
            n for n in self.graph.get_nodes()
            if n.id != node.id
            and n.scope == node.scope
            and abs(n.chunk_index - node.chunk_index) < self._co_scope_distance
        ]
        for other in same_scope:
            self.graph.add_edge(node.id, other.id, EdgeType.CO_SCOPE)
            self.graph.add_edge(other.id, node.id, EdgeType.CO_SCOPE)
            self._decay_engine.reactivate(other, self.graph.step)

    def _add_depends_edge(self, node: GraphNode, dependency: str) -> None:
        """添加依赖边"""
        matches = self.graph.find_by_text(dependency)
        if matches:
            target = min(matches, key=lambda n: abs(n.chunk_index - node.chunk_index))
            self.graph.add_edge(
                node.id, target.id, EdgeType.BACKGROUND,
            )
            self._decay_engine.reactivate(target, self.graph.step)

    def _apply_decay_to_all(self) -> None:
        """对所有节点应用 Ebbinghaus 衰减"""
        for node in self.graph.get_nodes():
            age = self.graph.step - node.last_referenced_at
            node.weight = self._decay_engine.compute_weight(
                age, 1.0, node.role
            )
