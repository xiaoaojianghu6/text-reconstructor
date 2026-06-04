"""FCR - 事实覆盖率 (Factual Coverage Ratio)

客观验证重构输出是否保留了原文的关键实体。
替代/补充 LLM 主观评分，防止 LLM 擅自压缩或遗漏细节。
"""

from __future__ import annotations

from .detail_anchor import DetailAnchor, extract_from_sentences


def compute_fcr(
    original_sentences: list[str],
    reconstructed_text: str,
    anchors: list[DetailAnchor] | None = None,
) -> dict:
    """计算事实覆盖率 FCR

    Returns:
        {
            "fcr": float,           # 0.0 - 1.0
            "total": int,           # 总锚点数
            "preserved": int,       # 保留锚点数
            "missing": list[str],   # 丢失的锚点文本
        }
    """
    if anchors is None:
        anchors = extract_from_sentences(original_sentences)

    if not anchors:
        return {"fcr": 1.0, "total": 0, "preserved": 0, "missing": []}

    missing: list[str] = []
    for a in anchors:
        if a.text not in reconstructed_text:
            missing.append(a.text)

    preserved = len(anchors) - len(missing)
    fcr = preserved / len(anchors)

    return {
        "fcr": fcr,
        "total": len(anchors),
        "preserved": preserved,
        "missing": missing,
    }
