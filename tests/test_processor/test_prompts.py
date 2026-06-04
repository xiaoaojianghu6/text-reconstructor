"""Prompt 模板单元测试"""

import pytest
from text_reconstructor.processor.prompts import (
    SYSTEM_PROMPT,
    BROAD_TAGGING_TEMPLATE,
    BATCH_SYSTEM_PROMPT,
    BATCH_TAGGING_TEMPLATE,
    build_broad_prompt,
    build_batch_prompt,
    build_scope_prompt,
    format_active_summary,
)


class TestBuildBroadPrompt:
    """build_broad_prompt 模板渲染测试"""

    def test_basic_rendering(self):
        """基本渲染包含 target 和 context"""
        sys_prompt, user_prompt = build_broad_prompt(
            target="今天天气很好。",
            context=["昨天下了雨。", "前天刮风。"],
            active_summary="- 天气 [role=nucleus]",
        )
        assert "今天天气很好。" in user_prompt
        assert "昨天下了雨。" in user_prompt
        assert "前天刮风。" in user_prompt
        assert "天气" in user_prompt
        assert sys_prompt == SYSTEM_PROMPT

    def test_partial_context(self):
        """context 不足 2 个时空字符串填充"""
        _, user_prompt = build_broad_prompt(
            target="只有一句。",
            context=["前一句。"],
            active_summary="(无)",
        )
        assert "只有一句。" in user_prompt
        assert "前一句。" in user_prompt

    def test_empty_context(self):
        """context 完全为空"""
        _, user_prompt = build_broad_prompt(
            target="第一句。",
            context=[],
            active_summary="(无)",
        )
        assert "第一句。" in user_prompt


class TestBuildBatchPrompt:
    """build_batch_prompt 模板渲染测试"""

    def test_basic_rendering(self):
        """正确渲染编号句子列表"""
        sys_prompt, user_prompt = build_batch_prompt(
            ["今天天气好。", "我们去散步了。"]
        )
        assert "0. 今天天气好。" in user_prompt
        assert "1. 我们去散步了。" in user_prompt
        assert "2" in user_prompt  # count=2
        assert sys_prompt == BATCH_SYSTEM_PROMPT

    def test_empty_list(self):
        """空句子列表"""
        _, user_prompt = build_batch_prompt([])
        assert "0" in user_prompt  # count=0

    def test_single_sentence(self):
        """单句列表"""
        _, user_prompt = build_batch_prompt(["测试。"])
        assert "0. 测试。" in user_prompt
        assert "1" in user_prompt  # count=1


class TestBuildScopePrompt:
    """build_scope_prompt 模板渲染测试"""

    def test_basic_rendering(self):
        """正确渲染句子列表"""
        sys_prompt, user_prompt = build_scope_prompt(["今天天气好。", "我们去散步了。"])
        assert "0. 今天天气好。" in user_prompt
        assert "1. 我们去散步了。" in user_prompt
        assert sys_prompt is not None

    def test_empty_list(self):
        """空列表"""
        sys_prompt, user_prompt = build_scope_prompt([])
        assert user_prompt is not None


class TestFormatActiveSummary:
    """format_active_summary 格式化测试"""

    def test_empty(self):
        """空列表返回 (无)"""
        assert format_active_summary([]) == "(无)"

    def test_single_node(self):
        """单节点格式化"""
        nodes = [{"text": "核心内容", "role": "nucleus", "relation": "cause", "scope": "主题"}]
        result = format_active_summary(nodes)
        assert "核心内容" in result
        assert "nucleus" in result
        assert "cause" in result
        assert "主题" in result

    def test_multiple_nodes(self):
        """多节点各占一行"""
        nodes = [
            {"text": "A", "role": "nucleus", "relation": "cause", "scope": "域1"},
            {"text": "B", "role": "satellite", "relation": "evidence", "scope": ""},
        ]
        result = format_active_summary(nodes)
        lines = result.split("\n")
        assert len(lines) == 2
        assert "域1" in lines[0]
        # 第二个节点 scope 为空，不显示 scope
        assert "evidence" in lines[1]
