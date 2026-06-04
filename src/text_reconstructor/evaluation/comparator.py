"""Evaluator -- 基线 vs 管线对比评估"""

from __future__ import annotations

import json
import logging
from typing import Any, Optional

from text_reconstructor.llm import LLMConfig, create_client
from .prompts import BASELINE_PROMPT, SCORING_PROMPT

logger = logging.getLogger(__name__)


class Evaluator:
    """对比评估器

    对比直接 LLM 梳理 vs 完整管线处理的输出质量。
    """

    def __init__(self, cloud_config: Optional[LLMConfig] = None):
        config = cloud_config or LLMConfig(
            backend="nvidia",
            model="deepseek-ai/deepseek-v4-flash",
            base_url="https://integrate.api.nvidia.com/v1",
            api_key="",
            max_tokens=4096,
            temperature=0.3,
            timeout=120.0,
        )
        self.client = create_client(config)

    def baseline_output(self, text: str) -> str:
        prompt = BASELINE_PROMPT.format(text=text)
        result = self.client.chat(
            messages=[{"role": "user", "content": prompt}],
            system_prompt="你是一个文本梳理专家。",
        )
        return result.content.strip()

    def pipeline_output(self, text: str) -> str:
        from text_reconstructor.processor.chunker import SentenceSplitter
        from text_reconstructor.processor.tagger import Tagger
        from text_reconstructor.graph.updater import GraphUpdater
        from text_reconstructor.output.llm_refiner import LLMRefiner

        tagger_config = LLMConfig(
            backend=self.client.config.backend,
            model=self.client.config.model,
            base_url=self.client.config.base_url,
            api_key=self.client.config.api_key,
            max_tokens=512,
            temperature=0.1,
            timeout=self.client.config.timeout,
        )
        tagger = Tagger(config=tagger_config, override_with_rules=True)
        updater = GraphUpdater(run_adversary=True)

        splitter = SentenceSplitter()
        sentences = splitter.split(text)
        chunks = tagger.batch_tag(sentences)
        snapshot = updater.process(chunks)

        refiner_config = LLMConfig(
            backend=self.client.config.backend,
            model=self.client.config.model,
            base_url=self.client.config.base_url,
            api_key=self.client.config.api_key,
            max_tokens=4096,
            temperature=0.15,
            timeout=120.0,
        )
        refiner = LLMRefiner(config=refiner_config)
        return refiner.refine(snapshot)

    def compute_fcr_scores(
        self,
        original: str,
        baseline: str,
        pipeline_result: str,
    ) -> dict:
        """用 FCR 客观指标补充 LLM 主观评分"""
        from text_reconstructor.output.detail_anchor import extract_from_sentences
        from text_reconstructor.output.fcr import compute_fcr
        from text_reconstructor.processor.chunker import SentenceSplitter

        splitter = SentenceSplitter()
        sentences = splitter.split(original)
        anchors = extract_from_sentences(sentences)

        if not anchors:
            return {"baseline_fcr": 1.0, "pipeline_fcr": 1.0, "anchor_count": 0}

        baseline_fcr = compute_fcr(sentences, baseline, anchors)
        pipeline_fcr = compute_fcr(sentences, pipeline_result, anchors)

        return {
            "baseline_fcr": baseline_fcr["fcr"],
            "pipeline_fcr": pipeline_fcr["fcr"],
            "baseline_missing": baseline_fcr["missing"],
            "pipeline_missing": pipeline_fcr["missing"],
            "anchor_count": len(anchors),
        }

    def score_outputs(self, original: str, baseline: str, pipeline_result: str) -> dict:
        prompt = SCORING_PROMPT.format(
            original=original,
            baseline=baseline,
            pipeline_result=pipeline_result,
        )
        result = self.client.chat(
            messages=[{"role": "user", "content": prompt}],
            system_prompt="你是一个文本质量评估专家。请客观评分。",
        )
        # 尝试直接解析 JSON，如果失败则尝试从 markdown 代码块提取
        raw = result.content.strip()
        try:
            scores = json.loads(raw)
            return scores
        except json.JSONDecodeError:
            pass

        # 回退：从 ```json ``` 代码块提取
        import re
        m = re.search(r"```(?:json)?\s*\n?(.*?)\n?```", raw, re.DOTALL)
        if m:
            try:
                scores = json.loads(m.group(1).strip())
                return scores
            except json.JSONDecodeError:
                pass

        logger.warning("评分 JSON 解析失败，返回原始文本")
        return {"raw_response": raw, "parse_error": True}
