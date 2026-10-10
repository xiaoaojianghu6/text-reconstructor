"""RefinementRefiner -- 增量微调引擎

基于上一版 VPGA 输出，结合用户对问题的回答和自由补充，
做增量修改而非完全重写。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from text_reconstructor.llm import LLMConfig, create_client

logger = logging.getLogger(__name__)

_REFINE_PROMPT = """你是一个顶级文本编辑，任务是增量微调已有的重构文本。

【规则】
1. 基于上一版输出修改，不是重写。只改需要改的地方。
2. 保持整体结构和风格不变。
3. 如果用户回答了某个问题，把补充说明融入对应位置。
4. 如果用户有额外指令（如"精简第三段"），执行该指令。
5. 保留所有未解决的 [疑点: XXX] 标注。如果用户已解释了某个疑点，移除对应的 [疑点] 标记并将解释融入正文。
6. 保留 [发现的问题] 部分。
7. 不输出"好的"等AI废话，直接输出修改后的完整文本。"""


@dataclass
class Answer:
    question_index: int
    user_input: str


class RefinementRefiner:
    """增量微调引擎

    输入: 上一版输出 + 用户回答 + 自由补充
    输出: 微调后的完整文本
    """

    def __init__(self, llm_client=None, config: LLMConfig | None = None):
        if llm_client is not None:
            self.client = llm_client
        else:
            self.client = create_client(
                config or LLMConfig(
                    max_tokens=8192,
                    temperature=0.15,
                    timeout=300.0,
                )
            )

    def refine(
        self,
        previous_output: str,
        answers: list[Answer] | None = None,
        user_note: str = "",
    ) -> str:
        """增量微调上一版输出

        Args:
            previous_output: 上一版 VPGA 输出
            answers: 用户对提问的回答列表
            user_note: 用户自由补充的额外指令
        """
        if not previous_output or not previous_output.strip():
            return ""

        parts = [f"【上一版输出】\n{previous_output}\n"]

        if answers:
            parts.append("【用户回答的问题】")
            for a in answers:
                parts.append(f"问题 {a.question_index}: {a.user_input}")
            parts.append("")

        if user_note:
            parts.append(f"【用户额外指令】\n{user_note}\n")

        if not answers and not user_note:
            return previous_output

        prompt = "\n".join(parts)

        try:
            result = self.client.chat(
                messages=[{"role": "user", "content": prompt}],
                system_prompt=_REFINE_PROMPT,
            )
            output = result.content.strip()
            if output:
                return output
            logger.warning("RefinementRefiner: LLM 返回空文本")
        except Exception as e:
            logger.warning("RefinementRefiner 失败: %s", e)

        return previous_output
