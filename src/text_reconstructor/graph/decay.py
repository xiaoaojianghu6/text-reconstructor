"""DecayEngine + AdversaryScanner

DecayEngine: 基于 Ebbinghaus 对数衰减的节点权重计算
AdversaryScanner: 7 项对抗检查（嵌入 Updater 流程）
"""

from __future__ import annotations

import logging
import math
import re

from .models import SemanticGraph, EdgeType

logger = logging.getLogger(__name__)

# ------------------------------------------------------------------
# DecayEngine — Ebbinghaus 对数衰减
# ------------------------------------------------------------------

_ROLE_DECAY_RATES = {
    "nucleus": 0.3,
    "satellite": 0.6,
    "expressive": 1.0,
    "action": 0.3,
    "commitment": 0.4,
}


class DecayEngine:
    """基于 Ebbinghaus 遗忘曲线的对数衰减引擎

    不同 role 的节点衰减速率不同：
    - nucleus: 0.3 (核心信息衰减最慢)
    - satellite: 0.6 (辅助信息中等衰减)
    - expressive: 1.0 (情感表达衰减最快)
    """

    def compute_weight(
        self,
        age: int,
        initial_weight: float,
        role: str,
        thread_id: str = "main",
        anchor_type: str = "none",
    ) -> float:
        if anchor_type == "foreshadow":
            rate = 0.01
        else:
            _THREAD_RATES = {"main": 0.3, "sub": 0.6, "latent": 0.05}
            role_rate = _ROLE_DECAY_RATES.get(role, 0.5)
            thread_rate = _THREAD_RATES.get(thread_id, 0.3)
            rate = min(role_rate, thread_rate)
        if age <= 0:
            return initial_weight
        return initial_weight / (1.0 + rate * math.log(1.0 + age))

    def reactivate(self, node, current_step: int) -> None:
        node.last_referenced_at = current_step
        node.weight = min(1.0, node.weight + 0.3)


class AdversaryScanner:
    """对抗机基础扫描

    5 项检测规则（全 Python 规则，零 LLM）:

    ① LOW_CONFIDENCE — 置信度 < 0.5
    ② ISOLATED_NODE — degree=0 的孤立节点
    ③ LOGIC_CONFLICT — ATTACK 入边 > SUPPORT 入边
    ④ DANGLING_DIRECTIVE — directive 无 CAUSE 入边
    ⑤ STRUCTURE_CHAOS — 同 scope 内密集 ATTACK+CONTRAST
    """

    CONFIDENCE_THRESHOLD = 0.5

    def scan(self, graph: SemanticGraph) -> list[dict]:
        """执行全图扫描，返回 alert 列表"""
        alerts: list[dict] = []

        for node in graph.get_nodes():
            # ① 低置信度
            if node.confidence < self.CONFIDENCE_THRESHOLD:
                alerts.append(self._make_alert(
                    node, "LOW_CONFIDENCE",
                    f"置信度 {node.confidence:.2f} 低于阈值 {self.CONFIDENCE_THRESHOLD}",
                ))

            # ② 孤立节点
            if graph.degree(node.id) == 0:
                alerts.append(self._make_alert(
                    node, "ISOLATED_NODE",
                    "孤立节点，无任何关联边，可能是遗漏信息",
                ))

            # ③ 逻辑冲突
            attacks = len(graph.get_incoming_edges(node.id, EdgeType.ATTACK))
            supports = len(graph.get_incoming_edges(node.id, EdgeType.SUPPORT))
            if attacks > supports:
                alerts.append(self._make_alert(
                    node, "LOGIC_CONFLICT",
                    f"ATTACK 入边({attacks}) > SUPPORT 入边({supports})，可能存在逻辑矛盾",
                ))

            # ④ 悬空指令
            if node.intent == "directive":
                incoming_causes = len(graph.get_incoming_edges(node.id, EdgeType.CAUSE))
                if incoming_causes == 0:
                    alerts.append(self._make_alert(
                        node, "DANGLING_DIRECTIVE",
                        "指令节点缺少前置原因（无 CAUSE 入边）",
                    ))

        # ⑤ 同 scope 结构混乱检测
        alert5 = self._scan_structure_chaos(graph)
        if alert5:
            alerts.extend(alert5)

        # ⑥ 未消解代词
        alert6 = self._scan_unresolved_pronouns(graph)
        if alert6:
            alerts.extend(alert6)

        # ⑦ 论证缺口
        alert7 = self._scan_argument_gaps(graph)
        if alert7:
            alerts.extend(alert7)

        # 去重
        return self._deduplicate(alerts)

    @staticmethod
    def _deduplicate(alerts: list[dict]) -> list[dict]:
        """相同 (type, text) 或 (type, scope) 的 alert 合并计数

        STRUCTURE_CHAOS 没有 text 字段，改用 scope 做去重 key。
        """
        seen: dict[tuple[str, str], dict] = {}
        result = []
        for a in alerts:
            text = a.get("text") if a.get("text") else a.get("scope", "")
            key = (a["type"], text)
            if key in seen:
                seen[key]["count"] = seen[key].get("count", 1) + 1
            else:
                a["count"] = 1
                seen[key] = a
                result.append(a)
        return result

    def _scan_structure_chaos(self, graph: SemanticGraph) -> list[dict]:
        """同 scope 内密集 ATTACK+CONTRAST 检测"""
        alerts = []
        scopes: dict[str, list] = {}
        for node in graph.get_nodes():
            if node.scope:
                scopes.setdefault(node.scope, []).append(node)

        for scope, nodes in scopes.items():
            attack_count = 0
            contrast_count = 0
            for n in nodes:
                attack_count += len(graph.get_incoming_edges(n.id, EdgeType.ATTACK))
                contrast_count += len(graph.get_incoming_edges(n.id, EdgeType.CONTRAST))
            total = attack_count + contrast_count
            if total >= 3 and len(nodes) >= 2:
                alerts.append({
                    "type": "STRUCTURE_CHAOS",
                    "scope": scope,
                    "detail": (
                        f"主题域「{scope}」内存在 {attack_count} 条反驳边 + "
                        f"{contrast_count} 条对比边（共 {total} 条），"
                        f"涉及 {len(nodes)} 个节点，结构可能混乱"
                    ),
                    "severity": "medium" if total < 5 else "high",
                })
        return alerts

    def _scan_unresolved_pronouns(self, graph: SemanticGraph) -> list[dict]:
        """检测全文处理完后仍有未消解代词的节点"""
        pronoun_re = re.compile(r"(他|她|它|他们|她们|它们|这|那|这个|那个|这里|那里)")
        alerts = []
        for node in graph.get_nodes():
            if pronoun_re.search(node.text):
                has_resolved = False
                for edge in graph.get_incoming_edges(node.id):
                    if edge.edge_type == EdgeType.BACKGROUND:
                        has_resolved = True
                        break
                if not has_resolved:
                    alerts.append(self._make_alert(
                        node, "UNRESOLVED_PRONOUN",
                        f"句子包含代词但未消解指代对象: {node.text[:50]}",
                    ))
        return alerts

    def _scan_argument_gaps(self, graph: SemanticGraph) -> list[dict]:
        """检测同 scope 内有 claim 但无 premise 支持的节点"""
        alerts = []
        for node in graph.get_nodes():
            if not node.scope:
                continue
            incoming = graph.get_incoming_edges(
                node.id, edge_type=EdgeType.SUPPORT
            ) + graph.get_incoming_edges(node.id, edge_type=EdgeType.EVIDENCE)
            if not incoming and node.intent == "assertive" and node.role == "nucleus":
                alerts.append(self._make_alert(
                    node, "ARGUMENT_GAP",
                    f"主题域「{node.scope}」内的核心主张缺少论据支持",
                ))
        return alerts

    # ── 辅助 ──

    def _make_alert(self, node, alert_type: str, detail: str) -> dict:
        return {
            "type": alert_type,
            "node_id": node.id,
            "text": node.text,
            "scope": node.scope,
            "detail": detail,
            "severity": "low" if alert_type in ("ISOLATED_NODE",) else "medium",
        }
