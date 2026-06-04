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
        llm_config: Any | None = None,
    ):
        self.graph = SemanticGraph()
        self._decay_rate = decay_rate
        self._co_scope_distance = co_scope_distance
        self._run_adversary = run_adversary
        self._decay_engine = DecayEngine()
        self._active_buffer = None
        self._semantic_router = None
        try:
            from ..processor.buffer import ActiveBuffer
            self._active_buffer = ActiveBuffer(max_size=20, eviction_threshold=0.4)
        except ImportError:
            pass
        if llm_config is not None:
            try:
                from ..llm import create_client
                from ..adversary.semantic_router import SemanticAdversaryRouter
                client = create_client(llm_config)
                self._semantic_router = SemanticAdversaryRouter(llm_client=client)
            except Exception as e:
                logger.warning("SemanticAdversaryRouter 初始化失败: %s", e)

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

        snapshot = self.graph.to_snapshot(alerts=alerts)
        if self._active_buffer is not None:
            snapshot["active_summary"] = self._active_buffer.get_active_summary()
        return snapshot

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

        # Step 6: 双轨混合对抗 -- LLM 语义审计补充
        semantic_alerts = []
        if self._semantic_router is not None:
            try:
                semantic_alerts = self._semantic_router.run(self.graph)
            except Exception as e:
                logger.warning("双轨混合对抗 LLM 审计失败: %s", e)

        # Step 7: 返回最终 alerts
        return conf_manager.get_alerts() + semantic_alerts

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
            thread_id=chunk.get("thread_id", "main"),
            anchor_type=chunk.get("anchor_type", "none"),
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

        # Step E2: 多线叙事建边
        if node.thread_id != "main" or node.anchor_type == "reveal":
            self._add_multithread_edges(node)

        # Step F: 应用衰减
        self._apply_decay_to_all()

        # Step G: 代词图谱回溯消解
        if chunk.get("_pronoun_needs_resolution"):
            self._resolve_pronoun_via_graph(node)

        # Step H: 更新 ActiveBuffer
        if self._active_buffer is not None:
            self._active_buffer.add_node(node)
            self._active_buffer.tick(tokens=len(text))

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
        """对所有节点应用 Ebbinghaus 衰减（含时空胶囊）"""
        for node in self.graph.get_nodes():
            age = self.graph.step - node.last_referenced_at
            node.weight = self._decay_engine.compute_weight(
                age, 1.0, node.role,
                thread_id=getattr(node, "thread_id", "main"),
                anchor_type=getattr(node, "anchor_type", "none"),
            )

    def _resolve_pronoun_via_graph(self, node: GraphNode) -> None:
        """代词图谱回溯消解

        沿 CO_SCOPE 边和时间轴反向寻找最近的 nucleus，隐式绑定 scope。
        只有反向搜索5个节点都找不到时才保留 REFERENCE_MISSING 状态。
        """
        # 策略1: 沿 CO_SCOPE 边反向寻找
        for edge in self.graph.get_incoming_edges(node.id, EdgeType.CO_SCOPE):
            source = self.graph.get_node(edge.source_id)
            if source and source.role == "nucleus" and source.scope and source.scope != "REFERENCE_MISSING":
                node.scope = source.scope
                self._decay_engine.reactivate(source, self.graph.step)
                return

        # 策略2: 时间轴反向，最多5步
        candidates = [
            n for n in self.graph.get_nodes()
            if n.id != node.id
            and n.chunk_index < node.chunk_index
            and n.role == "nucleus"
            and n.scope
            and n.scope != "REFERENCE_MISSING"
        ]
        candidates.sort(key=lambda n: n.chunk_index, reverse=True)
        for c in candidates[:5]:
            node.scope = c.scope
            self.graph.add_edge(node.id, c.id, EdgeType.BACKGROUND)
            self._decay_engine.reactivate(c, self.graph.step)
            return

    def _add_multithread_edges(self, node: GraphNode) -> None:
        """多线叙事建边: THREAD_BRIDGE 和 REVEAL"""
        # THREAD_BRIDGE: 副线节点 dependency 指向主线节点时
        if node.thread_id != "main" and node.scope:
            main_nodes = [
                n for n in self.graph.get_nodes()
                if n.id != node.id
                and getattr(n, "thread_id", "main") == "main"
                and n.scope == node.scope
                and n.chunk_index < node.chunk_index
            ]
            if main_nodes:
                target = max(main_nodes, key=lambda n: n.chunk_index)
                self.graph.add_edge(node.id, target.id, EdgeType.THREAD_BRIDGE)
                self._decay_engine.reactivate(target, self.graph.step)

        # REVEAL: 照应节点与伏笔节点实体重合时
        if node.anchor_type == "reveal":
            foreshadows = [
                n for n in self.graph.get_nodes()
                if n.id != node.id
                and getattr(n, "anchor_type", "none") == "foreshadow"
                and n.chunk_index < node.chunk_index
            ]
            for f in foreshadows:
                if self._text_overlap(node.text, f.text):
                    self.graph.add_edge(node.id, f.id, EdgeType.REVEAL)
                    self._decay_engine.reactivate(f, self.graph.step)
                    node.weight = 1.0

    @staticmethod
    def _text_overlap(text_a: str, text_b: str) -> bool:
        """检查两段文本是否有实质性重合（>=2字相同子串）"""
        for i in range(len(text_a) - 1):
            bigram = text_a[i:i+2]
            if bigram in text_b:
                return True
        return False
