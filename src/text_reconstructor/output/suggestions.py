"""Suggestions — 非强制交互提示输出

将 AlertBuffer 的 alert 列表格式化为人类可读的中文建议。
"""

from __future__ import annotations


_ALERT_TEMPLATES: dict[str, str] = {
    "LOW_CONFIDENCE": "节点「{text}」可能存在模糊概念，建议补充支持性内容",
    "ISOLATED_NODE": "节点「{text}」缺少关联关系，建议补充上下文连接",
    "LOGIC_CONFLICT": "节点「{text}」存在逻辑矛盾，建议检查论证一致性",
    "DANGLING_DIRECTIVE": "指令节点「{text}」缺乏前提条件，建议说明为什么需要这样做",
    "STRUCTURE_CHAOS": "主题域「{scope}」存在结构混乱，建议梳理逻辑结构",
}

_SEVERITY_LABELS = {
    "high": "高优先级",
    "medium": "中优先级",
    "low": "低优先级",
}

_ALLOWED_ALERT_TYPES = {"DANGLING_DIRECTIVE", "LOGIC_CONFLICT"}


class Suggestions:
    """非强制交互提示输出

    输入: AlertBuffer.get_all() 返回的 alert 列表
    输出: 可读的中文建议列表
    """

    def format(self, alerts: list[dict]) -> list[str]:
        """alert 列表 → 可读建议列表

        只输出高危逻辑中断：DANGLING_DIRECTIVE 和 LOGIC_CONFLICT 且 severity >= medium
        """
        if not alerts:
            return []

        filtered = [
            a for a in alerts
            if a.get("type") in _ALLOWED_ALERT_TYPES
            and a.get("severity") in ("high", "medium")
        ]
        if not filtered:
            return []

        total = len(filtered)
        results: list[str] = []
        for i, alert in enumerate(filtered, 1):
            results.append(self._format_one(alert, i, total))
        return results

    def _format_one(self, alert: dict, idx: int, total: int) -> str:
        """单条 alert → 格式化建议"""
        alert_type = alert.get("type", "")
        severity = alert.get("severity", "medium")
        text = alert.get("text", "")
        scope = alert.get("scope", "")
        detail_text = alert.get("detail", "")

        label = _SEVERITY_LABELS.get(severity, "中优先级")

        if alert_type in _ALERT_TEMPLATES:
            detail = _ALERT_TEMPLATES[alert_type].format(text=text, scope=scope)
        elif detail_text:
            detail = detail_text
        else:
            detail = f"节点「{text}」存在需要关注的问题"

        return f"[建议 {idx}/{total}] {label}: {detail}"
