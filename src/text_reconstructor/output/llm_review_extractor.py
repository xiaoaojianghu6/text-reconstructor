"""LLM 审查标记提取与清理

从 VPGA 输出中提取 [疑点: XXX] 和 [发现的问题: XXX] 标记，
同时从输出文本中移除这些标记，返回干净的文本。

支持两种格式:
1. 内联: [疑点: XXX] 或 [发现的问题: XXX]
2. 段标题: [发现的问题] 后续行为内容 (直到下一个 ## 或文本结束)
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# 内联格式: [疑点: XXX] 或 [发现的问题: XXX]
_INLINE_PATTERN = re.compile(r'\[(疑点|发现的问题)[:：]\s*([^\]]+)\]')
# 段标题格式: [发现的问题] 后续内容块 (非贪婪, 到下一个 ## 或文本结尾)
_SECTION_PATTERN = re.compile(r'\[发现的问题\]\s*\n(.*?)(?=\n## |\Z)', re.DOTALL)


@dataclass
class LLMReviewItem:
    marker_type: str     # "doubt" | "issue"
    content: str         # 标记内容
    position: int        # 在原文中的字符偏移
    surrounding: str     # 前后上下文


def extract_and_clean(vpga_output: str) -> tuple[str, list[LLMReviewItem]]:
    """从 VPGA 输出中提取 LLM 审查标记并清理输出文本

    Returns:
        (clean_output, items) -- 清理后的文本和提取到的审查项列表
    """
    items: list[LLMReviewItem] = []

    # 提取内联标记
    for m in _INLINE_PATTERN.finditer(vpga_output):
        items.append(LLMReviewItem(
            marker_type="doubt" if m.group(1) == "疑点" else "issue",
            content=m.group(2).strip(),
            position=m.start(),
            surrounding=vpga_output[max(0, m.start() - 50):m.end() + 50],
        ))

    # 提取段标题格式 [发现的问题] ... 内容块
    for m in _SECTION_PATTERN.finditer(vpga_output):
        block = m.group(1).strip()
        if not block:
            continue
        # 段落内可能有多条问题(按换行或编号分隔)
        for line in re.split(r'\n(?=\d+[\.\)、]|\-|\*)', block):
            line = re.sub(r'^\d+[\.\)、]\s*', '', line).strip()
            if not line:
                continue
            items.append(LLMReviewItem(
                marker_type="issue",
                content=line,
                position=m.start(),
                surrounding=vpga_output[max(0, m.start() - 50):min(len(vpga_output), m.end() + 50)],
            ))

    # 清理: 先移除内联标记, 再移除段标题块
    clean = _INLINE_PATTERN.sub('', vpga_output)
    clean = _SECTION_PATTERN.sub('', clean)
    clean = re.sub(r'\n{3,}', '\n\n', clean).strip()
    return clean, items
