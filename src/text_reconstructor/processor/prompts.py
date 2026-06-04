"""Tagger Prompt 模板

所有 Prompt 模板集中在此，便于调优和版本管理。
分离后 Tagger 逻辑代码不变，只需修改此文件即可调 Prompt。
"""

from __future__ import annotations

# [Mini-Batch 预备代码] 以下 SYSTEM_PROMPT + BROAD_TAGGING_TEMPLATE + format_active_summary + build_broad_prompt
# 将在阶段5 Mini-Batch 流式标注时启用，当前 batch 模式不使用
SYSTEM_PROMPT = """You are a Chinese text annotation assistant. Given a sentence with context, output JSON with:

- role: "nucleus" (core info, sentence breaks without it) or "satellite" (supporting info)
- intent: "assertive" (statement/fact), "directive" (request/command), "commissive" (promise/plan), "expressive" (emotion/evaluation), or "declaration" (declare/name)
- relation: "cause", "result", "evidence", "elaboration", "background", "condition", "purpose", "summary", "contrast", "concession", "sequence", "attribution", "evaluation", "restatement", or "none"
- argument_role: "premise", "claim", or "none"
- argument_relation: "support", "attack", or "none"
- scope: topic domain of the sentence (short phrase, e.g. "pricing strategy")
- dependency: what previous content this sentence depends on (empty string if none)
- cue_phrase: the keyword that triggered your judgment (empty string if none)

Output ONLY the JSON object. No other text."""


BROAD_TAGGING_TEMPLATE = """## 上下文

前文 1: {context0}
前文 2: {context1}

当前活跃主题:
{active_summary}

## 当前句

{target}

## 任务

分析当前句并输出以下字段的 JSON：

### 字段说明

1. "role": "nucleus" 或 "satellite"
   - nucleus = 核心信息，去掉它句子不成立
   - satellite = 辅助信息，去掉后核心信息仍完整

2. "intent": 以下之一
   - "assertive" = 陈述事实、观点、判断
   - "directive" = 请求、命令、建议
   - "commissive" = 承诺、保证、计划
   - "expressive" = 表达情感、评价
   - "declaration" = 宣告、声明、命名

3. "relation": 当前句与前文的逻辑关系
   - "cause" = 原因(因为/由于)
   - "result" = 结果(所以/因此)
   - "evidence" = 举例(例如/比如)
   - "elaboration" = 进一步说明(也就是说/具体来说)
   - "background" = 背景信息
   - "condition" = 条件(如果/除非)
   - "purpose" = 目的(为了/以便)
   - "summary" = 总结(总之/总的来说)
   - "contrast" = 转折(但是/然而)
   - "concession" = 让步(虽然/尽管)
   - "sequence" = 时间顺序(然后/接着)
   - "attribution" = 引用他人观点
   - "evaluation" = 评价/判断
   - "restatement" = 换种说法重申
   - "none" = 无明显关系

4. "argument_role": "premise", "claim", 或 "none"
   - premise = 论据/理由 (为某个观点提供支持)
   - claim = 结论/主张 (被支持的论点)
   - none = 不涉及论证

5. "argument_relation": "support", "attack", 或 "none"
   - support = 支持前文某观点
   - attack = 反驳/质疑前文某观点
   - none = 无明显论证关系

6. "scope": 当前句所属的主题域（短语，如"定价策略"）

7. "dependency": 当前句依赖/引用的前文内容（如果没有则为空字符串）

8. "cue_phrase": 触发上述判断的关键词（如"因为""但是"等，没有则为空）

## 约束

- 如果当前句包含代词(他/她/它/他们/这/那/这个/那个/这里/那里)，必须在 scope 或 dependency 中写出真实指代对象
- 禁止在 scope 和 dependency 中使用代词
- 输出合法的 JSON 对象"""


def format_active_summary(active_nodes: list[dict]) -> str:
    """格式化 Active Buffer 的活跃节点摘要"""
    if not active_nodes:
        return "(无)"
    parts = []
    for node in active_nodes:
        scope = f"({node['scope']})" if node.get("scope") else ""
        parts.append(f"- {node['text']} [role={node['role']}, relation={node['relation']}]{scope}")
    return "\n".join(parts)


def build_broad_prompt(
    target: str,
    context: list[str],
    active_summary: str,
) -> tuple[str, str]:
    """构建 Broad 阶段 Prompt

    Returns:
        (system_prompt, user_prompt)
    """
    context0 = context[0] if len(context) > 0 else ""
    context1 = context[1] if len(context) > 1 else ""
    user_prompt = BROAD_TAGGING_TEMPLATE.format(
        context0=context0,
        context1=context1,
        active_summary=active_summary,
        target=target,
    )
    return SYSTEM_PROMPT, user_prompt


# ------------------------------------------------------------------
# Batch 模式 — 一次调用标注所有句子
# ------------------------------------------------------------------

BATCH_SYSTEM_PROMPT = """You are a Chinese text annotation assistant. Given a list of sentences, output annotations in a structured format."""


BATCH_TAGGING_TEMPLATE = """为以下每句话标注 role/intent/relation/scope/论证角色/主张关系/依赖关系。

每行格式（严格遵循，不要额外文字）：
编号||role||intent||relation||argument_role||argument_relation||scope||dependency

role: nucleus(核心) 或 satellite(辅助)
intent: assertive(陈述) 或 directive(指令) 或 commissive(承诺) 或 expressive(情感) 或 declaration(宣告)
relation: cause(原因) 或 result(结果) 或 evidence(举例) 或 elaboration(说明) 或 background(背景) 或 condition(条件) 或 purpose(目的) 或 summary(总结) 或 contrast(转折) 或 concession(让步) 或 sequence(顺序) 或 evaluation(评价) 或 none(无)
argument_role: premise(论据) 或 claim(主张) 或 none(无)
argument_relation: support(支持) 或 attack(反驳) 或 none(无)
scope: 当前句的主题域/话题（如"定价策略"），用短语概括
dependency: 依赖的前文内容（可为空）

注意间接言语行为：
- "你能...吗？" "是不是应该..." 实际是指令(directive)，不是疑问
- "我觉得可能需要..." "建议..." 实际是指令或建议
- "我打算/准备..." 是承诺(commissive)

示例：
0||nucleus||commissive||none||none||none||定价策略||
1||satellite||assertive||cause||premise||support||市场分析||价格敏感度
2||nucleus||expressive||contrast||claim||none||产品评价||
3||satellite||directive||condition||none||none||技术方案||预算限制
4||satellite||assertive||concession||premise||support||竞争分析||对手优势
5||nucleus||assertive||result||claim||none||项目进展||阶段一完成

共 {count} 句：

{numbered_sentences}"""


def build_batch_prompt(sentences: list[str]) -> tuple[str, str]:
    """构建 Batch 标注 Prompt

    Args:
        sentences: 全部句子的列表

    Returns:
        (system_prompt, user_prompt)
    """
    numbered = "\n".join(f"{i}. {s}" for i, s in enumerate(sentences))
    user_prompt = BATCH_TAGGING_TEMPLATE.format(
        count=len(sentences),
        numbered_sentences=numbered,
    )
    return BATCH_SYSTEM_PROMPT, user_prompt


# ------------------------------------------------------------------
# Scope 推理 — 二次调用专门做主题域分组
# ------------------------------------------------------------------

SCOPE_SYSTEM_PROMPT = """Group the sentences by topic. Sentences discussing the same subject get the same topic label."""

SCOPE_TEMPLATE = """为以下每句话分配一个主题域(scope)。

规则：
1. 讨论同一主题的句子使用完全相同的 scope 名称
2. scope 用短语概括（2-5字），如"市场需求""技术方案""可行性分析"
3. 相邻句子如果讨论不同方面，分配不同的 scope
4. 每行格式：编号||scope

{numbered_sentences}"""


def build_scope_prompt(sentences: list[str]) -> tuple[str, str]:
    """构建 Scope 推理 Prompt

    Args:
        sentences: 全部句子的列表

    Returns:
        (system_prompt, user_prompt)
    """
    numbered = "\n".join(f"{i}. {s}" for i, s in enumerate(sentences))
    user_prompt = SCOPE_TEMPLATE.format(numbered_sentences=numbered)
    return SCOPE_SYSTEM_PROMPT, user_prompt
