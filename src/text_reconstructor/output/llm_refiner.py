"""LLMRefiner — 文本重构输出生成器

输入: GraphUpdater 输出的 snapshot dict
输出: LLM 生成的清理后纯文本
"""

from __future__ import annotations

import logging

from text_reconstructor.llm import LLMConfig, create_client

logger = logging.getLogger(__name__)

STRUCTURING_PROMPT = """你是一个文本重构专家。请将以下散句组织为结构清晰、逻辑连贯的段落。

必须遵守的规则：
1. 保留原文所有细节、数据、专有名词、URL — 不允许任何信息丢失
2. 保留每个句子的主谓宾结构，不得缩写或合并句子
3. 不得概括或总结，保留原文的实质内容
4. 删除无意义的填充词（啊、呢、嗯、对吧、是不是）

允许的操作：
5. 添加逻辑过渡词（如：然而、具体而言、在此背景下、与此相反、例如）
6. 添加 ## 二级标题按话题分组
7. 添加段落换行和空行
8. 必要时调整句子顺序（但必须保留所有句子）

输出格式：
- 每个话题用 ## 话题名 作为二级标题
- 话题内每个句子用 "数字. " 编号列出（如 "1. ..."、"2. ..."）
- 保持每个句子的原始主谓宾结构
- 不要添加原文没有的信息
- 对原文中模糊、未定义的概念标注为 [疑点]
- 发现的逻辑矛盾或遗漏单独列在 [发现的问题] 下"""


class LLMRefiner:
    """文本重构输出生成器"""

    def __init__(self, llm_client=None, config: LLMConfig | None = None):
        if llm_client is not None:
            self.client = llm_client
        else:
            self.client = create_client(
                config or LLMConfig(
                    max_tokens=4096,
                    temperature=0.3,
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
        sections = []
        for n in snapshot.get("nodes", []):
            text = n.get("text", "")
            role = n.get("role", "")
            rel = n.get("relation", "")
            scope = n.get("scope", "")
            tag_parts = [p for p in [role, rel] if p]
            tag = f"[{'/'.join(tag_parts)}]" if tag_parts else ""
            prefix = f"{tag} " if tag else ""
            if scope:
                sections.append(f"  ({scope}) {prefix}{text}")
            else:
                sections.append(f"  {prefix}{text}")
        return "\n".join(sections)
