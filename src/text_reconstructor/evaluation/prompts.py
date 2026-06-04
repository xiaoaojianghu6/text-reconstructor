"""评估 Prompt 模板"""

BASELINE_PROMPT = """请梳理以下文本的结构和逻辑，保留所有细节。

要求：
1. 按话题分段输出
2. 保留原文每一个观点、细节、例子，不压缩不省略
3. 使用恰当的连接词体现逻辑关系
4. 修正口语化表达，但保持原意不变
5. 对模糊/不确定的概念标明

原文：
{text}"""

SCORING_PROMPT = """你是一个文本评估专家。请对两个"文本梳理"结果进行评分。

评分维度（每个维度 0-10 分）：
1. detail_preservation（细节保留）：是否保留了原文所有细节、观点、例子？有没有遗漏？
2. doubt_identification（疑点识别）：是否识别出模糊概念、不确定的表述、潜在问题？
3. fuzzy_concept_handling（模糊处理）：对原文中模糊/歧义的表达，处理是否合理？是过度猜测还是正确保留？
4. structure_clarity（结构清晰）：逻辑结构是否清晰？分段分点是否合理？是否方便人类和AI阅读？

原文：
{original}

--- 基线输出（直接LLM梳理）---
{baseline}

--- 系统输出（管线处理）---
{pipeline_result}

请输出纯 JSON 格式的评分结果（不要 markdown 代码块，不要 ```json 标记，只输出 JSON 对象本身）：
{{
    "baseline": {{
        "detail_preservation": X,
        "doubt_identification": X,
        "fuzzy_concept_handling": X,
        "structure_clarity": X
    }},
    "pipeline": {{
        "detail_preservation": X,
        "doubt_identification": X,
        "fuzzy_concept_handling": X,
        "structure_clarity": X
    }},
    "summary": "简要评述两个输出的主要差异"
}}"""
