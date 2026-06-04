"""Tagger - LLM 标注 + 后处理 + 指代消解

工作流:
  1. Broad Tagging → LLM 输出 JSON
  2. 信号词后处理 → regex 修正 relation
  3. JSON 校验 → 补充默认值
  4. 代词检测 → 确保 scope/dependency 非空
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Any, Optional

from text_reconstructor.llm import OllamaClient, LLMConfig, create_client
from .prompts import build_batch_prompt, build_scope_prompt, build_mini_batch_prompt

logger = logging.getLogger(__name__)

# ------------------------------------------------------------------
# 信号词规则
# ------------------------------------------------------------------

@dataclass
class SignalRule:
    pattern: re.Pattern
    relation: str
    priority: int = 5  # 优先级（越大越优先）


_SIGNAL_RULES: list[SignalRule] = [
    # 优先级的直觉：转折词(但是/然而)和因果词(因为/所以)最明确，
    # 条件词(如果/只有)可能嵌入在从句中。
    # 因果
    SignalRule(re.compile(r"(因为|所以|因此|从而|导致|由于|因而|于是)"), "cause", priority=8),
    # 转折（最高优先级 — 句子核心语气）
    SignalRule(re.compile(r"(但是|然而|不过|却|虽然|尽管|可是|但)"), "contrast", priority=10),
    # 时序
    SignalRule(re.compile(r"(然后|接着|随后|之后|此后|先)"), "sequence", priority=6),
    # 证据
    SignalRule(re.compile(r"(例如|比如|比方说|譬如|举例)"), "evidence", priority=9),
    # 总结
    SignalRule(re.compile(r"(总之|综上所述|总的来说|概括|简而言之)"), "summary", priority=9),
    # 条件（优先级较低 — 可能嵌入在从句）
    SignalRule(re.compile(r"(如果|假如|一旦|除非|只有|只要)"), "condition", priority=4),
    # 目的
    SignalRule(re.compile(r"(为了|以便|以免|以期)"), "purpose", priority=7),
    # 阐述
    SignalRule(re.compile(r"(也就是说|换句话说|具体来说|即)"), "elaboration", priority=7),
]

# ------------------------------------------------------------------
# 代词检测
# ------------------------------------------------------------------

_PRONOUN_PATTERN = re.compile(r"(他|她|它|他们|她们|它们|这|那|这个|那个|这里|那里|这些|那些)")

# 公开给 GraphUpdater._resolve_pronoun 使用
PRONOUN_PATTERN = _PRONOUN_PATTERN

# ------------------------------------------------------------------
# Intent 信号词规则
# ------------------------------------------------------------------

_INTENT_RULES: list[tuple[re.Pattern, str]] = [
    # 承诺/计划 (commissive)
    (re.compile(r"(计划|打算|准备|将要|承诺|保证|目标|愿景|争取)"), "commissive"),
    (re.compile(r"(将|会)在.*(前|内|之前)"), "commissive"),
    # 指令/建议 (directive) — 放宽句首匹配，但不匹配普通陈述中的"需要/应该"
    (re.compile(r"^(请|必须|应当|建议|推荐|务必)"), "directive"),
    (re.compile(r"(请|让|要求|命令|强烈建议)"), "directive"),
    # 表达 (expressive)
    (re.compile(r"(遗憾|高兴|担心|希望|失望|满意|庆幸|可惜)"), "expressive"),
    # 宣告 (declaration)
    (re.compile(r"(宣布|宣告|任命)"), "declaration"),
]

# 广泛但易误判的 directive 信号词 — 仅在 LLM 已标 directive 且确实匹配时才确认
_DIRECTIVE_COMMON = re.compile(r"(需要|应该|必须|得)")


def _is_strong_directive(text: str) -> bool:
    """检查是否有强 directive 信号"""
    for pattern, intent in _INTENT_RULES:
        if intent == "directive" and pattern.search(text):
            return True
    return _DIRECTIVE_COMMON.search(text) is not None


# ------------------------------------------------------------------
# Chunk 默认值
# ------------------------------------------------------------------

_DEFAULT_CHUNK: dict[str, Any] = {
    "role": "satellite",
    "intent": "assertive",
    "relation": "none",
    "argument_role": "none",
    "argument_relation": "none",
    "scope": "",
    "dependency": "",
    "cue_phrase": "",
    "thread_id": "main",
    "anchor_type": "none",
}


class Tagger:
    """结构化标签标注器

    Args:
        llm_client: OllamaClient 实例
        enable_narrow: 是否启用 Narrow 阶段（两次 LLM 调用）
    """

    def __init__(
        self,
        llm_client=None,
        config: Optional[LLMConfig] = None,
        override_with_rules: bool = True,
    ):
        if llm_client is not None:
            self.client = llm_client
        else:
            self.client = create_client(
                config or LLMConfig(max_tokens=512, temperature=0.1)
            )
        self._override_with_rules = override_with_rules

    def batch_tag(
        self,
        sentences: list[str],
        timeout: float = 180.0,
    ) -> list[dict[str, Any]]:
        """批量标注所有句子 — 一次 LLM 调用

        Args:
            sentences: 全部句子列表
            timeout: 请求超时（秒），batch 需要更长时间

        Returns:
            list[ChunkDict] — 每句对应一个 chunk
        """
        if not sentences:
            return []

        from text_reconstructor.llm import LLMConfig
        system_prompt, user_prompt = build_batch_prompt(sentences)
        num_pred = min(2000, max(300, len(sentences) * 25))

        batch_config = LLMConfig(
            model=self.client.config.model,
            base_url=self.client.config.base_url,
            timeout=timeout,
            temperature=self.client.config.temperature,
            max_tokens=num_pred,
            think=self.client.config.think,
            backend=self.client.config.backend,
            api_key=self.client.config.api_key,
        )
        batch_client = create_client(batch_config)
        try:
            raw_output = batch_client.chat(
                messages=[{"role": "user", "content": user_prompt}],
                system_prompt=system_prompt,
            )
            content = raw_output.content
        except Exception as e:
            logger.error("Batch LLM 调用失败: %s", e)
            return [self._default_chunk(s) for s in sentences]

        chunks = self._parse_batch_output(content, sentences)
        chunks = self._infer_scopes(chunks, sentences)
        return chunks

    def batch_tag_streaming(
        self,
        sentences: list[str],
        batch_size: int = 8,
        active_summary: list[dict] | None = None,
        timeout: float = 180.0,
    ) -> tuple[list[dict[str, Any]], list[dict]]:
        """Mini-Batch 流式标注 -- 8句一批，携带 ActiveBuffer 上下文

        Returns:
            (chunks, updated_active_summary) 元组
        """
        if not sentences:
            return [], active_summary or []

        from text_reconstructor.llm import LLMConfig
        all_chunks: list[dict[str, Any]] = []
        current_active = active_summary or []

        for i in range(0, len(sentences), batch_size):
            batch = sentences[i:i + batch_size]
            system_prompt, user_prompt = build_mini_batch_prompt(
                batch, current_active, offset=i
            )

            num_pred = min(2000, max(300, len(batch) * 25))
            batch_config = LLMConfig(
                model=self.client.config.model,
                base_url=self.client.config.base_url,
                timeout=timeout,
                temperature=self.client.config.temperature,
                max_tokens=num_pred,
                think=self.client.config.think,
                backend=self.client.config.backend,
                api_key=self.client.config.api_key,
            )
            batch_client = create_client(batch_config)
            try:
                raw_output = batch_client.chat(
                    messages=[{"role": "user", "content": user_prompt}],
                    system_prompt=system_prompt,
                )
                content = raw_output.content
            except Exception as e:
                logger.error("Mini-Batch LLM 调用失败 (offset=%d): %s", i, e)
                all_chunks.extend(self._default_chunk(s) for s in batch)
                continue

            chunks = self._parse_batch_output(content, batch)

            # 更新 active_summary
            current_active = self._update_active_from_chunks(chunks, current_active)
            all_chunks.extend(chunks)

        all_chunks = self._infer_scopes(all_chunks, sentences)
        return all_chunks, current_active

    @staticmethod
    def _update_active_from_chunks(
        chunks: list[dict], current: list[dict], max_items: int = 3
    ) -> list[dict]:
        """从当前 batch 中选出最好的节点作为 active_summary"""
        good = [
            {"text": c["text"], "role": c["role"], "relation": c["relation"],
             "scope": c.get("scope", "")}
            for c in chunks
            if c.get("scope") and c["scope"] not in ("", "REFERENCE_MISSING")
            and c["role"] == "nucleus"
        ]
        merged = (good + current)[:max_items]
        return merged

    def _parse_batch_output(
        self,
        raw_output: str,
        sentences: list[str],
    ) -> list[dict[str, Any]]:
        """解析 batch 输出为 ChunkDict 列表

        格式: 编号||role||intent||relation||argument_role||argument_relation||scope||dependency
        scope 和 dependency 可以包含空格或为空
        """
        FIELDS = ["role", "intent", "relation", "argument_role", "argument_relation", "scope", "dependency"]
        parsed = {}
        for line in raw_output.split("\n"):
            line = line.strip()
            parts = [p.strip() for p in line.split("||")]
            if len(parts) >= 8:
                try:
                    idx = int(parts[0])
                    parsed[idx] = dict(zip(FIELDS, parts[1:8]))
                except (ValueError, IndexError):
                    continue
            elif len(parts) == 7:
                # dependency 可能被省略（末尾无 ||）
                try:
                    idx = int(parts[0])
                    data = dict(zip(FIELDS[:6], parts[1:7]))
                    data["dependency"] = ""
                    parsed[idx] = data
                except (ValueError, IndexError):
                    continue

        chunks = []
        for i, s in enumerate(sentences):
            if i in parsed:
                chunk = parsed[i]
            else:
                chunk = {}

            if self._override_with_rules:
                chunk = apply_signal_corrections(chunk, s)
                chunk = apply_intent_corrections(chunk, s)
            chunk = validate_chunk(chunk, s)
            chunk = apply_rst_role(chunk, s)
            chunk = infer_scope(chunk, s)
            chunk = check_pronouns(chunk, s)
            chunks.append(chunk)

        return chunks

    def _infer_scopes(
        self,
        chunks: list[dict[str, Any]],
        sentences: list[str],
    ) -> list[dict[str, Any]]:
        """二次 LLM 调用: 专门推理 scope（主题域分组）

        仅在首次标注的 scope 过少（<=2 种）时触发。
        与 batch 标注分离，避免单一模型同时处理所有字段导致的 scope 不一致。
        """
        if not chunks or len(chunks) <= 1:
            return chunks

        _LOW_QUALITY_SCOPES = {"", "REFERENCE_MISSING", "none", "(无)"}
        low_quality_count = sum(
            1 for c in chunks if c.get("scope", "") in _LOW_QUALITY_SCOPES
        )
        if low_quality_count == 0:
            return chunks

        sys_prompt, user_prompt = build_scope_prompt(sentences)

        scope_config = LLMConfig(
            model=self.client.config.model,
            base_url=self.client.config.base_url,
            timeout=30.0,
            temperature=0.1,
            max_tokens=len(chunks) * 20,
            think=self.client.config.think,
            backend=self.client.config.backend,
            api_key=self.client.config.api_key,
        )
        scope_client = create_client(scope_config)
        try:
            raw = scope_client.chat(
                messages=[{"role": "user", "content": user_prompt}],
                system_prompt=sys_prompt,
            )
            parsed = {}
            for line in raw.content.strip().split("\n"):
                parts = [p.strip() for p in line.split("||")]
                if len(parts) >= 2:
                    try:
                        idx = int(parts[0])
                        scope = parts[1]
                        if scope and scope not in ("", "(无)"):
                            parsed[idx] = scope
                    except ValueError:
                        continue
            for idx, scope in parsed.items():
                if 0 <= idx < len(chunks):
                    chunks[idx]["scope"] = scope
                    chunks[idx]["_scope_inferred"] = True
        except Exception as e:
            logger.warning("Scope 推理失败，保留初始 scope: %s", e)

        return chunks

    @staticmethod
    def _default_chunk(text: str) -> dict[str, Any]:
        return validate_chunk({}, text)


# ------------------------------------------------------------------
# 信号词后处理
# ------------------------------------------------------------------

def apply_signal_corrections(chunk: dict, text: str) -> dict:
    """通过信号词修正 relation 字段

    当文本匹配多个信号词时，以优先级最高的为准。
    """
    best_match = None
    best_priority = -1
    for rule in _SIGNAL_RULES:
        if rule.pattern.search(text):
            if rule.priority > best_priority:
                best_priority = rule.priority
                best_match = rule

    if best_match is not None:
        current = chunk.get("relation", "none")
        if current in (None, "", "none") or current != best_match.relation:
            chunk["relation"] = best_match.relation
            chunk["_corrected"] = True
    return chunk


# ------------------------------------------------------------------
# RST 理论规则: nucleus/satellite 修正
# ------------------------------------------------------------------

_RST_CAUSE_PATTERN = re.compile(r"(因为|由于|原因)")
_RST_RESULT_PATTERN = re.compile(r"(所以|因此|因而|从而|于是|故)")

# 单核关系: 这些关系的 satellite 侧
_RST_SATELLITE_RELATIONS = {
    "evidence", "elaboration", "background", "condition", "purpose", "concession",
}
# 多核关系: 所有参与方都是 nucleus
_RST_NUCLEUS_RELATIONS = {"contrast", "sequence", "summary", "restatement"}


def apply_rst_role(chunk: dict, text: str) -> dict:
    """RST 理论规则修正 nucleus/satellite 分配

    RST(修辞结构理论)规定:
    - 单核关系: 辅助信息(evidence/elaboration/background/condition/purpose/concession) → satellite
    - 多核关系: 转折/时序/总结/重申 → nucleus（并列结构双方同等重要）
    - 因果关系: 原因从句("因为/由于") → satellite, 结果从句("所以/因此") → nucleus
    - 无关系: 无明显修辞功能 → satellite
    """
    current_role = chunk.get("role", "satellite")
    relation = chunk.get("relation", "none")

    # 多核关系 → nucleus
    if relation in _RST_NUCLEUS_RELATIONS:
        if current_role != "nucleus":
            chunk["role"] = "nucleus"
            chunk["_role_rst_corrected"] = True
        return chunk

    # 原因/结果区分
    if relation == "cause":
        if _RST_CAUSE_PATTERN.search(text):
            if current_role != "satellite":
                chunk["role"] = "satellite"
                chunk["_role_rst_corrected"] = True
        elif _RST_RESULT_PATTERN.search(text):
            if current_role != "nucleus":
                chunk["role"] = "nucleus"
                chunk["_role_rst_corrected"] = True
        else:
            # 无明确信号: RST 因果中因通常是卫星
            if current_role != "satellite":
                chunk["role"] = "satellite"
                chunk["_role_rst_corrected"] = True
        return chunk

    # 单核卫星关系 → satellite
    if relation in _RST_SATELLITE_RELATIONS and current_role != "satellite":
        chunk["role"] = "satellite"
        chunk["_role_rst_corrected"] = True
        return chunk

    # relation="none" 时尊重 LLM 的原始 role 判断
    # 无明确修辞关系不代表不是核心信息（如独立的结论性陈述）

    return chunk


# ------------------------------------------------------------------
# JSON 校验
# ------------------------------------------------------------------

_REQUIRED_FIELDS = ["role", "intent", "relation"]


def validate_chunk(chunk: dict, text: str) -> dict:
    """校验 Chunk JSON，补充缺失的必需字段"""
    if not isinstance(chunk, dict):
        chunk = {}

    # 保留原文
    chunk["text"] = text

    # 补充缺失字段
    for key, default in _DEFAULT_CHUNK.items():
        if key not in chunk or chunk[key] is None:
            chunk[key] = default

    # 确保必填字段在 enum 范围内
    if chunk["role"] not in ("nucleus", "satellite"):
        chunk["role"] = "satellite"

    if chunk["intent"] not in ("assertive", "directive", "commissive", "expressive", "declaration"):
        chunk["intent"] = "assertive"

    valid_relations = {
        "cause", "result", "evidence", "elaboration", "background",
        "condition", "purpose", "summary", "contrast", "concession",
        "sequence", "attribution", "evaluation", "restatement", "none",
    }
    if chunk["relation"] not in valid_relations:
        chunk["relation"] = "none"

    return chunk


# ------------------------------------------------------------------
# 代词检测
# ------------------------------------------------------------------

def check_pronouns(chunk: dict, text: str) -> dict:
    """检测原文中是否有代词，若无 scope/dependency 则标记 _pronoun_needs_resolution

    不再直接将 scope 设为 REFERENCE_MISSING，避免污染业务字段。
    代词消解将在 GraphUpdater 中通过图谱回溯完成。
    """
    if _PRONOUN_PATTERN.search(text):
        if not chunk.get("scope") and not chunk.get("dependency"):
            chunk["_pronoun_needs_resolution"] = True
    return chunk


# ------------------------------------------------------------------
# Intent 后处理修正
# ------------------------------------------------------------------

def apply_intent_corrections(chunk: dict, text: str) -> dict:
    """通过信号词修正 intent 字段

    规则:
    1. 强信号词匹配 → 覆盖为指定 intent
    2. LLM 输出 directive 但无强信号 → 回退 assertive（避免 1.5B 模型过度预测 directive）
    """
    current = chunk.get("intent", "assertive")
    matched = False
    for pattern, intent in _INTENT_RULES:
        if pattern.search(text):
            if current != intent:
                chunk["intent"] = intent
                chunk["_intent_corrected"] = True
                matched = True
                break

    if not matched and current == "directive":
        # LLM 标了 directive 但无强信号 — 降级为 assertive
        if not _is_strong_directive(text):
            chunk["intent"] = "assertive"
            chunk["_intent_corrected"] = True
    return chunk


# ------------------------------------------------------------------
# Scope 后处理（LLM 未识别时回退到关键词）
# ------------------------------------------------------------------

def infer_scope(chunk: dict, text: str) -> dict:
    """scope 字段后处理 — LLM 未识别时从 dependency 回退"""
    if chunk.get("scope"):
        return chunk
    dep = chunk.get("dependency", "")
    if dep and dep not in ("", "none"):
        if not _PRONOUN_PATTERN.search(dep):
            chunk["scope"] = dep[:8]
    return chunk
