"""LLMRefiner -- 文本重构输出生成器

输入: GraphUpdater 输出的 snapshot dict
输出: LLM 生成的结构化重构文本
"""

from __future__ import annotations

import logging

from text_reconstructor.llm import LLMConfig, create_client
from text_reconstructor.processor.prefix_pruner import clean_sentence_prefix

logger = logging.getLogger(__name__)

_RELATION_LABELS = {
    "cause": "因果",
    "result": "结果",
    "evidence": "举例",
    "elaboration": "阐述",
    "background": "背景",
    "condition": "条件",
    "purpose": "目的",
    "contrast": "转折",
    "concession": "让步",
    "sequence": "时序",
    "support": "支持",
    "attack": "反驳",
}

STRUCTURING_PROMPT = """你是一个文本重构专家。请将以下标注好的散句组织为结构清晰、逻辑连贯的段落。

核心原则 -- 必须遵守：
1. 保留原文所有细节、数据、专有名词、URL -- 不允许任何信息丢失
2. 保留每个句子的主谓宾结构和实质内容，不得缩写或合并
3. 绝不能概括、总结或精简 -- 是"梳理复述"而非"概括摘要"
4. 删除无意义的填充词（啊、呢、嗯、对吧、是不是）
5. 区分口语化填充词和语言特点/文本细节 -- 前者可删，后者必留

结构和表达：
6. 按主题分组，用 ## 话题名 作为二级标题
7. 话题内用清晰的分段和分点阐述，逻辑层次鲜明
8. 添加恰当的逻辑过渡词（然而、具体而言、在此背景下、与此相反、例如）
9. 行文流畅清晰，表达得体，方便人与AI阅读

硬性约束：
10. 原文中出现的关键数据、URL、强特征比喻必须原样保留
11. 对原文中模糊、未定义的概念标注为 [疑点]
12. 发现的逻辑矛盾或遗漏单独列在 [发现的问题] 下
13. 下方列出的逻辑关系必须在输出中通过过渡词或结构安排体现"""


class LLMRefiner:

    def __init__(self, llm_client=None, config: LLMConfig | None = None):
        if llm_client is not None:
            self.client = llm_client
        else:
            self.client = create_client(
                config or LLMConfig(
                    max_tokens=4096,
                    temperature=0.15,
                    timeout=60.0,
                )
            )
        from .text_output import TextOutput
        self._fallback = TextOutput()

    def refine(self, snapshot: dict) -> str:
        nodes = snapshot.get("nodes", [])
        if not nodes:
            return ""

        prompt = self._build_prompt(snapshot)

        try:
            result = self.client.chat(
                messages=[{"role": "user", "content": prompt}],
                system_prompt=STRUCTURING_PROMPT,
            )
            output = result.content.strip()
            if output:
                return output
            logger.warning("LLM 返回空文本，回退到模板")
        except Exception as e:
            logger.warning("LLMRefiner 失败，回退到模板: %s", e)

        return self._fallback.format_simple(snapshot)

    def _build_prompt(self, snapshot: dict) -> str:
        nodes = snapshot.get("nodes", [])
        edges = snapshot.get("edges", [])

        node_map = {n["id"]: n for n in nodes}

        edge_lines = []
        for e in edges:
            et = e.get("edge_type", "")
            if et in ("co_scope",):
                continue
            label = _RELATION_LABELS.get(et, et)
            src = node_map.get(e["source_id"], {})
            tgt = node_map.get(e["target_id"], {})
            src_text = src.get("text", "")[:25]
            tgt_text = tgt.get("text", "")[:25]
            if src_text and tgt_text:
                edge_lines.append(
                    f"  - [{label}] 「{src_text}」 --> 「{tgt_text}」"
                )

        node_lines = []
        for n in nodes:
            text = clean_sentence_prefix(n.get("text", ""))
            scope = n.get("scope", "")
            role = n.get("role", "")
            rel = n.get("relation", "")
            tag = f"[{role}" + (f"/{rel}" if rel and rel != "none" else "") + "]"
            if scope:
                node_lines.append(f"  ({scope}) {tag} {text}")
            else:
                node_lines.append(f"  {tag} {text}")

        header = "标注好的句子列表：\n" + "\n".join(node_lines)

        edge_info = ""
        if edge_lines:
            shown = edge_lines[:25]
            edge_info = f"\n\n句子间关键逻辑关系（共{len(edge_lines)}条，展示前{len(shown)}条）：\n" + "\n".join(shown)

        return header + edge_info
