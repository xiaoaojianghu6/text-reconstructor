"""对抗机 — 结构化检控 + 辩护 + 置信度管理

全 Python 规则实现，零 LLM 调用。
"""

from .prosecutor import Prosecution, Prosecutor
from .defender import DefenseResult, Defender
from .alert_buffer import AlertEntry, AlertBuffer, ConfidenceManager

__all__ = [
    "Prosecution",
    "Prosecutor",
    "DefenseResult",
    "Defender",
    "AlertEntry",
    "AlertBuffer",
    "ConfidenceManager",
]
