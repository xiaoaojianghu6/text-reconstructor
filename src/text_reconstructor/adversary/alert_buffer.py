"""AlertBuffer — 优先级 Alert 队列 + ConfidenceManager 置信度管理

AlertBuffer:
  - 去重键: (alert_type, node_id)
  - 优先级排序: severity(high>medium>low) → round → count

ConfidenceManager:
  - 辩论循环编排器（最多 2 轮）
  - SAFETY_LINE=0.7（辩护后 >= 0.7 安全）
  - ALERT_THRESHOLD=0.5（2 轮后 < 0.5 入 AlertBuffer）

"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from text_reconstructor.graph.models import SemanticGraph
from .prosecutor import Prosecutor, Prosecution


@dataclass
class AlertEntry:
    """AlertBuffer 中的单条 alert"""

    alert_type: str
    node_id: int = -1
    text: str = ""
    scope: str = ""
    detail: str = ""
    severity: str = "medium"
    round: int = 1
    count: int = 1


class AlertBuffer:
    """优先级 Alert 队列

    关键设计：
    - 去重键: (alert_type, node_id) — 相同类型+节点只保留一条
    - 优先级排序: severity(high>medium>low) → round(越大越优先) → count(越多越优先)
    - 2-round 上限: 外部确保 round <= 2，buffer 只做记录
    - 永久存储: 所有 push 进来的 alert 都会保留到 get_all()
    """

    def __init__(self):
        self._alerts: dict[tuple[str, int], AlertEntry] = {}

    def push(
        self,
        alert_type: str,
        node_id: int = -1,
        text: str = "",
        scope: str = "",
        detail: str = "",
        severity: str = "medium",
        round: int = 1,
    ) -> None:
        """推入或更新 alert

        去重规则: (alert_type, node_id) 相同则合并——更新 count, round。
        如果新 severity 更高，升级；否则保留原 severity。
        """
        key = (alert_type, node_id)
        if key in self._alerts:
            existing = self._alerts[key]
            existing.count += 1
            existing.round = max(existing.round, round)
            if self._severity_rank(severity) > self._severity_rank(existing.severity):
                existing.severity = severity
            existing.detail = detail
        else:
            self._alerts[key] = AlertEntry(
                alert_type=alert_type,
                node_id=node_id,
                text=text,
                scope=scope,
                detail=detail,
                severity=severity,
                round=round,
                count=1,
            )

    def has(self, alert_type: str, node_id: int) -> bool:
        return (alert_type, node_id) in self._alerts

    def get_all(self) -> list[dict]:
        """输出用于 snapshot 的 sorted list（高优先级在前）"""
        entries = sorted(
            self._alerts.values(),
            key=lambda e: (
                self._severity_rank(e.severity),
                e.round,
                e.count,
            ),
            reverse=True,
        )
        return [
            {
                "type": e.alert_type,
                "node_id": e.node_id,
                "text": e.text,
                "scope": e.scope,
                "detail": e.detail,
                "severity": e.severity,
                "round": e.round,
                "count": e.count,
            }
            for e in entries
        ]

    def clear(self) -> None:
        self._alerts.clear()

    def size(self) -> int:
        return len(self._alerts)

    @staticmethod
    def _severity_rank(severity: str) -> int:
        return {"high": 3, "medium": 2, "low": 1}.get(severity, 0)


class ConfidenceManager:
    """置信度管理与辩论循环编排器

    核心常量:
    - SAFETY_LINE = 0.7         (防御后 >= 0.7 则安全)
    - ALERT_THRESHOLD = 0.5     (2 轮后 < 0.5 推入 AlertBuffer)
    - MAX_ROUNDS = 2            (硬性上限)
    """

    SAFETY_LINE = 0.7
    ALERT_THRESHOLD = 0.5
    MAX_ROUNDS = 2

    def __init__(self, alert_buffer: AlertBuffer | None = None):
        self.alert_buffer = alert_buffer or AlertBuffer()

    def run_node_cycle(
        self,
        node_id: int,
        prosecutions: list[Prosecution],
        graph: SemanticGraph,
        prosecutor: Prosecutor,
        defender: Defender,
    ) -> None:
        """对单个节点执行完整的辩论循环

        使用 round 计数器驱动，确保 2 轮硬性终止。
        """
        node = graph.get_node(node_id)
        if node is None:
            return

        if node.confidence >= self.SAFETY_LINE:
            return

        for current_round in range(1, self.MAX_ROUNDS + 1):
            updated_prosecutions = prosecutor.build(
                [self._prosecution_to_alert(p) for p in prosecutions],
                graph,
                round_num=current_round,
            )

            total_delta = 0.0
            for prosecution in updated_prosecutions:
                if prosecution.node_id < 0:
                    continue
                result = defender.respond(prosecution, graph)
                total_delta += result.confidence_delta

            if total_delta != 0.0:
                node.confidence = max(0.0, min(1.0, node.confidence + total_delta))

            if node.confidence >= self.SAFETY_LINE:
                return

        # 辩论结束后评估
        if node.confidence < self.ALERT_THRESHOLD:
            severity = "high"
        else:
            severity = "medium"
        for prosecution in prosecutions:
            if prosecution.node_id >= 0:
                self.alert_buffer.push(
                    alert_type=prosecution.alert_type,
                    node_id=node_id,
                    text=prosecution.text,
                    scope=prosecution.scope,
                    detail=prosecution.detail,
                    severity=severity,
                    round=self.MAX_ROUNDS,
                )

    def run_scope_cycle(self, prosecution: Prosecution, graph: SemanticGraph) -> None:
        """处理 scope 级 alert（STRUCTURE_CHAOS 等）

        scope 级 alert 不经过辩论，直接推入 AlertBuffer。
        """
        self.alert_buffer.push(
            alert_type=prosecution.alert_type,
            node_id=-1,
            text=prosecution.text,
            scope=prosecution.scope,
            detail=prosecution.detail,
            severity=prosecution.severity,
            round=1,
        )

    def get_alerts(self) -> list[dict]:
        return self.alert_buffer.get_all()

    @staticmethod
    def _prosecution_to_alert(p: Prosecution) -> dict:
        return {
            "type": p.alert_type,
            "node_id": p.node_id,
            "text": p.text,
            "scope": p.scope,
            "detail": p.detail,
            "severity": p.severity,
        }
