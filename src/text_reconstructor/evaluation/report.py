"""ReportGenerator -- 评估报告生成"""

from __future__ import annotations

import logging
import os
import time
from typing import Any

from .comparator import Evaluator

logger = logging.getLogger(__name__)

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)
))))


def load_test_texts() -> list[dict[str, str]]:
    """从 测试文本.md 加载测试文本"""
    path = os.path.join(_PROJECT_ROOT, "测试文本.md")
    if not os.path.exists(path):
        return []

    with open(path, "r", encoding="utf-8") as f:
        content = f.read()

    texts = []
    parts = content.split("### 测试文本")
    for part in parts[1:]:
        lines = part.strip().split("\n", 1)
        label = lines[0].strip().rstrip("：:")
        text_body = lines[1].strip() if len(lines) > 1 else ""
        text_body = text_body.strip('"').strip('"').strip('"')
        if text_body:
            texts.append({"label": label, "text": text_body})

    return texts


class ReportGenerator:
    """评估报告生成器"""

    def __init__(self, evaluator: Evaluator):
        self.evaluator = evaluator

    def generate(self, test_texts: list[dict[str, str]] | None = None) -> str:
        if test_texts is None:
            test_texts = load_test_texts()

        sections = []
        for i, item in enumerate(test_texts, 1):
            if i > 1:
                time.sleep(3)

            label = item.get("label", str(i))
            text = item["text"]

            logger.info("评估测试文本 %s: %s", i, label)

            baseline = self.evaluator.baseline_output(text)
            pipeline_result = self.evaluator.pipeline_output(text)
            scores = self.evaluator.score_outputs(text, baseline, pipeline_result)

            section = self._format_section(i, label, text, baseline, pipeline_result, scores)
            sections.append(section)

        report = "# 评估报告\n\n" + "\n\n---\n\n".join(sections)
        return report

    def save(self, report: str, path: str | None = None) -> str:
        if path is None:
            path = os.path.join(_PROJECT_ROOT, "评估报告.md")
        with open(path, "w", encoding="utf-8") as f:
            f.write(report)
        return path

    def _format_section(
        self, idx: int, label: str, original: str,
        baseline: str, pipeline_result: str, scores: dict,
    ) -> str:
        lines = [
            f"## 测试文本 {idx}: {label}",
            "",
            "### 原文",
            "",
            f"> {original[:200]}{'...' if len(original) > 200 else ''}",
            "",
            "### 基线输出（直接 LLM 梳理）",
            "",
            baseline,
            "",
            "### 系统输出（管线处理）",
            "",
            pipeline_result,
        ]

        if scores.get("parse_error"):
            lines.extend(["", "### 评分", "", "（评分解析失败）", scores.get("raw_response", "")])
        else:
            lines.extend(["", "### 评分对比", ""])
            lines.append("| 维度 | 基线 | 系统 | 说明 |")
            lines.append("|------|------|------|------|")

            dim_labels = {
                "detail_preservation": "细节保留",
                "doubt_identification": "疑点识别",
                "fuzzy_concept_handling": "模糊处理",
                "structure_clarity": "结构清晰",
            }

            b_scores = scores.get("baseline", {})
            p_scores = scores.get("pipeline", {})

            for dim_key, dim_label in dim_labels.items():
                b_val = b_scores.get(dim_key, "-")
                p_val = p_scores.get(dim_key, "-")
                winner = ""
                if isinstance(b_val, (int, float)) and isinstance(p_val, (int, float)):
                    if p_val > b_val:
                        winner = "系统优"
                    elif b_val > p_val:
                        winner = "基线优"
                    else:
                        winner = "持平"
                lines.append(f"| {dim_label} | {b_val} | {p_val} | {winner} |")

            summary = scores.get("summary", "")
            if summary:
                lines.extend(["", f"**总评**: {summary}"])

        return "\n".join(lines)
