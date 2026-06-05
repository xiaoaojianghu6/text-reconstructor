"""VPGARefiner -- Verbatim-Preserving Holistic Rewrite

VPGA (Verbatim-Preserving Holistic Rewrite) 协议:
直接将原始全文交给 LLM 一次完成重构，不走 Tagger/Graph 中间层。
避免离散标签标注导致的信息瓶颈和有损压缩。
"""

from __future__ import annotations

import logging

from text_reconstructor.llm import LLMConfig, create_client

logger = logging.getLogger(__name__)

VPGA_PROMPT = """你是一个顶级主编、叙事学专家与人类思维重构军师。

【任务】
将用户口语化、混乱、多线交织的原始输入，重构为逻辑极度严密、段落呼吸感极强的结构化文本。

【核心原则 -- 违者判定任务失败】
1. 绝对不能概括！绝对不能总结！绝对不能精简！这是"逻辑梳理与保义复述"，不是"摘要提取"。
2. 100%保留原文中所有的事实细节、数据、URL、独特的个人比喻。
3. 必须保留作者独特的文风、神态与情绪。如果作者的口语中带有调侃、情绪或特定的表达习惯（例如"以防由于你实力不足而全玩完"），必须在重组后的合适位置原样保留，严禁将其规整为平庸、冰冷的学术词汇或公文套话。
4. 保留每个句子的主谓宾结构和实质内容，不得缩写或合并不同观点。
5. 区分口语化填充词(啊/呢/嗯/对吧/是不是)和语言特点/文本细节 -- 前者可删，后者必留。

【结构与去噪规则】
6. 自动识别并切除在逻辑重组后失效的线性过渡词（如句首突兀残留的"第一"、"第二点是"、"再然后"、"我发现啊"），使用自然的上下文逻辑连词（然而、具体而言、在此背景下、与此呼应的是）将段落缝合。
7. 将破碎的单句进行宏观聚类，按话题分组，使用 ## 话题名称 作为二级标题。
8. 话题内用清晰的分段和分点阐述，逻辑层次鲜明。严禁产生"一个标题下只有一两句话"的稀碎排版。
9. 如果原文中存在多线叙事（例如一边讲产品，一边讲个人经历），使用电影剪辑式的并行过渡手法缝合（例如"与此遥相呼应的是..."），保证行文的线性呼吸感。
10. 行文流畅清晰，表达得体，方便人与AI阅读。

【硬性约束】
11. 原文中出现的关键数据、URL、强特征比喻必须原样保留，不得做任何同义词替换。
12. 对原文中模糊、未定义的概念，必须在正文中直接标注 [疑点: XXX]（如"有机可寻[疑点: 含义不明，可能指'有规律可循']"）。不要只在末尾列出疑点，必须在正文出现处就地标注。至少识别出所有以下类型的模糊表达：含义不明的术语、指代不清的代词、逻辑跳跃的推断、缺乏数据支撑的断言。
13. [发现的问题] 仅用于列出原文表述层面的逻辑缺陷，具体包括：(a) 前后文自相矛盾（如前面说A后面又说非A）；(b) 明显的论据遗漏（提了结论但缺乏必要前提）；(c) 未交代的指代跳跃（突然出现新概念但无上下文支撑）。严禁将以下内容列为"问题"：作者主动提出的改进建议、作者的反问/思考、作者对第三方的批评、系统对作者观点的质疑或反驳。[发现的问题] 列在文末。
14. 不要输出"好的，以下是重构结果"等AI废话，直接输出重构文本。"""


class VPGARefiner:
    """VPGA 全局语义引擎

    输入: 原始全文
    输出: LLM 一次完成的重构文本
    """

    def __init__(self, llm_client=None, config: LLMConfig | None = None):
        if llm_client is not None:
            self.client = llm_client
        else:
            self.client = create_client(
                config or LLMConfig(
                    max_tokens=8192,
                    temperature=0.15,
                    timeout=120.0,
                )
            )

    def refine(self, text: str) -> str:
        """直接处理原文，一次 LLM 调用完成重构"""
        if not text or not text.strip():
            return ""

        prompt = text

        try:
            result = self.client.chat(
                messages=[{"role": "user", "content": prompt}],
                system_prompt=VPGA_PROMPT,
            )
            output = result.content.strip()
            if output:
                return output
            logger.warning("VPGARefiner: LLM 返回空文本")
        except Exception as e:
            logger.warning("VPGARefiner 失败: %s", e)

        return text
