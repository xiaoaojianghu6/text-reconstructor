"""Prosecutor — 结构化检控器

将 AdversaryScanner 产出的原始 alert dict 转化为 Prosecution 对象，
每个 Prosecution 包含具体指控和"需要什么证据才能解决"的规格说明。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from text_reconstructor.graph.models import SemanticGraph, GraphNode


@dataclass
class Prosecution:
    """一次具体的"起诉"——从 alert 转化而来

    核心思想：每个 alert 类型对应一种"证据不足"模式，
    Prosecution 将描述"需要什么证据才能让这个节点可信"。
    """

    alert_type: str  # 原始 alert 类型，如 "LOW_CONFIDENCE"
    node_id: int  # 被指控的节点
    text: str  # 节点文本
    scope: str  # 主题域
    detail: str  # 原始 detail 描述
    severity: str  # "high" / "medium" / "low"
    round: int  # 当前轮次 (1 或 2)

    # 检控的核心规格
    required_evidence: str  # 需要什么类型的证据描述
    evidence_targets: list[str] = field(default_factory=list)  # 搜索方向列表
    intent: str | None = None  # 节点 intent，用于 speech-act 专项检查
    is_escalated: bool = False  # Round 2 时 True，搜索范围扩大


class Prosecutor:
    """结构化检控器

    接收 Scanner 原始 alert 列表，产出结构化 Prosecution 列表。
    每类 alert 有对应的转换规则。
    """

    # 各 alert 类型到 requirement 的映射表
    _REQUIREMENT_MAP: dict[str, dict] = {
        "LOW_CONFIDENCE": {
            "required_evidence": "incoming SUPPORT, EVIDENCE, or BACKGROUND edges",
            "evidence_targets": [
                "incoming_support",
                "incoming_evidence",
                "incoming_background",
            ],
            "detail_template": "节点置信度 {conf:.2f} 低于阈值，需要支持性证据提升",
        },
        "ISOLATED_NODE": {
            "required_evidence": "any relational connection (CAUSE, BACKGROUND, CO_SCOPE)",
            "evidence_targets": ["co_scope_neighbors", "text_match", "same_scope"],
            "detail_template": "孤立节点需要关联关系（同域/文本匹配/背景引用）",
        },
        "LOGIC_CONFLICT": {
            "required_evidence": "additional SUPPORT edges or mitigating context",
            "evidence_targets": ["outgoing_support", "same_scope", "incoming_background"],
            "detail_template": (
                "ATTACK({attacks}) > SUPPORT({supports})，"
                "需要辩护性证据抵消攻击"
            ),
        },
        "DANGLING_DIRECTIVE": {
            "required_evidence": "CAUSE, BACKGROUND, or CONDITION incoming edges",
            "evidence_targets": [
                "incoming_cause",
                "incoming_background",
                "incoming_condition",
                "same_scope",
            ],
            "detail_template": "指令节点缺少前置原因/背景上下文",
        },
        "STRUCTURE_CHAOS": {
            "required_evidence": "balanced SUPPORT edges or scope restructuring",
            "evidence_targets": ["same_scope_support"],
            "detail_template": (
                "主题域内 ATTACK+CONTRAST({total}) 密集，"
                "需要结构性支持证据"
            ),
        },
    }

    def build(
        self,
        alerts: list[dict],
        graph: SemanticGraph,
        round_num: int = 1,
    ) -> list[Prosecution]:
        """将 alert dict 列表转化为 Prosecution 列表

        STRUCTURE_CHAOS 类型（scope 级，非节点级）特殊处理：
        创建 node_id=-1 的 Prosecution，跳过辩论直接入 AlertBuffer。
        """
        prosecutions: list[Prosecution] = []
        for alert in alerts:
            if alert["type"] == "STRUCTURE_CHAOS":
                p = self._build_scope_alert(alert, round_num)
            else:
                p = self._build_node_alert(alert, graph, round_num)
            prosecutions.append(p)
        return prosecutions

    def _build_node_alert(
        self,
        alert: dict,
        graph: SemanticGraph,
        round_num: int,
    ) -> Prosecution:
        """构建节点级起诉"""
        rule = self._REQUIREMENT_MAP.get(alert["type"], {})
        node = graph.get_node(alert["node_id"])
        intent = node.intent if node else None

        # Round 2 扩展搜索范围
        targets = list(rule.get("evidence_targets", []))
        if round_num >= 2:
            extras = ["same_scope", "global_text_match"]
            for e in extras:
                if e not in targets:
                    targets.append(e)

        prosecution = Prosecution(
            alert_type=alert["type"],
            node_id=alert["node_id"],
            text=alert.get("text", ""),
            scope=alert.get("scope", ""),
            detail=alert.get("detail", ""),
            severity=alert.get("severity", "medium"),
            round=round_num,
            required_evidence=rule.get("required_evidence", ""),
            evidence_targets=targets,
            intent=intent,
            is_escalated=(round_num >= 2),
        )

        # Speech-act 专项增强
        if node:
            self._inject_speech_act_requirements(prosecution, node)

        return prosecution

    def _build_scope_alert(
        self,
        alert: dict,
        round_num: int,
    ) -> Prosecution:
        """构建 scope 级别起诉（STRUCTURE_CHAOS 专用）"""
        rule = self._REQUIREMENT_MAP.get(alert["type"], {})
        return Prosecution(
            alert_type=alert["type"],
            node_id=-1,
            text=alert.get("detail", ""),
            scope=alert.get("scope", ""),
            detail=alert.get("detail", ""),
            severity=alert.get("severity", "medium"),
            round=round_num,
            required_evidence=rule.get("required_evidence", ""),
            evidence_targets=rule.get("evidence_targets", []),
            intent=None,
            is_escalated=(round_num >= 2),
        )

    def _inject_speech_act_requirements(
        self,
        prosecution: Prosecution,
        node: GraphNode,
    ) -> None:
        """按照言语行为类型注入额外的证据要求"""
        if node.intent == "assertive":
            if "incoming_evidence" not in prosecution.evidence_targets:
                prosecution.evidence_targets.append("incoming_evidence")

        elif node.intent == "directive":
            if "incoming_background" not in prosecution.evidence_targets:
                prosecution.evidence_targets.append("incoming_background")

        elif node.intent == "commissive":
            if "future_reference" not in prosecution.evidence_targets:
                prosecution.evidence_targets.append("future_reference")
            prosecution.required_evidence += "; 检查承诺后续是否被提及"

        elif node.intent == "expressive":
            if "incoming_cause" not in prosecution.evidence_targets:
                prosecution.evidence_targets.append("incoming_cause")
            if "same_scope" not in prosecution.evidence_targets:
                prosecution.evidence_targets.append("same_scope")
            prosecution.required_evidence += "; 需要情感表达的触发原因"
