"""LLMRefiner 单元测试"""

from unittest.mock import MagicMock

import pytest
from text_reconstructor.output.llm_refiner import LLMRefiner


def _node(
    id_,
    text,
    role="nucleus",
    intent="assertive",
    relation="none",
    scope="",
    chunk_index=0,
    confidence=0.6,
    **kw,
):
    return {
        "id": id_,
        "text": text,
        "role": role,
        "intent": intent,
        "relation": relation,
        "scope": scope,
        "chunk_index": chunk_index,
        "confidence": confidence,
        "weight": 1.0,
        **kw,
    }


def _edge(source_id, target_id, edge_type, **kw):
    return {
        "source_id": source_id,
        "target_id": target_id,
        "edge_type": edge_type,
        "confidence": 1.0,
        **kw,
    }


class TestLLMRefinerNormal:
    """LLMRefiner 正常输出测试"""

    def test_normal_output(self):
        """多句时 mock LLM 返回清理文本 → 输出即该文本"""
        mock_chat = MagicMock()
        mock_chat.content = "清理后的文本内容。"
        mock_client = MagicMock()
        mock_client.chat.return_value = mock_chat

        refiner = LLMRefiner(llm_client=mock_client)
        snap = {
            "nodes": [
                _node(1, "第一句", scope="测试", chunk_index=0),
                _node(2, "第二句", scope="测试", chunk_index=1),
            ],
            "edges": [],
            "alerts": [],
        }
        result = refiner.refine(snap)
        assert result == "清理后的文本内容。"
        # 验证 LLM 被调用了一次
        assert mock_client.chat.call_count == 1

    def test_multi_sentence(self):
        """多句 → LLM 被调用并输出结果"""
        mock_chat = MagicMock()
        mock_chat.content = "结果段落。"
        mock_client = MagicMock()
        mock_client.chat.return_value = mock_chat

        refiner = LLMRefiner(llm_client=mock_client)
        snap = {
            "nodes": [
                _node(1, "第一句。", scope="域A", chunk_index=0),
                _node(2, "第二句。", scope="域A", chunk_index=1),
                _node(3, "第三句。", scope="域B", chunk_index=2),
            ],
            "edges": [_edge(1, 2, "cause")],
            "alerts": [],
        }
        result = refiner.refine(snap)
        assert result == "结果段落。"


class TestLLMRefinerFallback:
    """LLM 失败时的回退测试"""

    def test_llm_exception(self):
        """LLM 抛出异常 → 回退到 format_simple"""
        mock_client = MagicMock()
        mock_client.chat.side_effect = Exception("LLM 挂了")

        refiner = LLMRefiner(llm_client=mock_client)
        snap = {
            "nodes": [
                _node(1, "测试文本。", scope="测试", chunk_index=0),
            ],
            "edges": [],
            "alerts": [],
        }
        result = refiner.refine(snap)
        # fallback 应输出原句
        assert "测试文本。" in result
        # fallback 应有 scope 标题
        assert "## 测试" in result

    def test_llm_empty_return(self):
        """LLM 返回空字符串 → 回退到 format_simple"""
        mock_chat = MagicMock()
        mock_chat.content = ""
        mock_client = MagicMock()
        mock_client.chat.return_value = mock_chat

        refiner = LLMRefiner(llm_client=mock_client)
        snap = {
            "nodes": [
                _node(1, "测试文本。", scope="测试", chunk_index=0),
            ],
            "edges": [],
            "alerts": [],
        }
        result = refiner.refine(snap)
        assert "测试文本。" in result


class TestLLMRefinerEdgeCases:
    """边界情况"""

    def test_empty_snapshot(self):
        """空 snapshot → 空字符串"""
        refiner = LLMRefiner()
        assert refiner.refine({"nodes": [], "edges": [], "alerts": []}) == ""

    def test_no_nodes_key(self):
        """snapshot 无 nodes 键 → 空字符串"""
        refiner = LLMRefiner()
        assert refiner.refine({}) == ""

    def test_single_sentence_uses_llm(self):
        """单句 → 用极简 prompt 调用 LLM，不包含标注标签"""
        mock_chat = MagicMock()
        mock_chat.content = "这个方案可行。"
        mock_client = MagicMock()
        mock_client.chat.return_value = mock_chat

        refiner = LLMRefiner(llm_client=mock_client)
        snap = {
            "nodes": [_node(1, "我觉得啊, 这个方案可行。")],
            "edges": [],
            "alerts": [],
        }
        result = refiner.refine(snap)
        assert result == "这个方案可行。"
        # LLM 被调用
        assert mock_client.chat.call_count == 1
        # 验证 prompt 不含标签（极简模式）
        prompt = mock_client.chat.call_args[1]["messages"][0]["content"]
        assert "[话题:" not in prompt
        assert "这个方案可行" in prompt


class TestLLMRefinerPrompt:
    """Prompt 构建验证"""

    def test_scope_in_prompt(self):
        """prompt 中包含 scope 分组信息（括号格式）"""
        mock_chat = MagicMock()
        mock_client = MagicMock()
        mock_client.chat.return_value = mock_chat

        refiner = LLMRefiner(llm_client=mock_client)
        snap = {
            "nodes": [
                _node(1, "市场句。", scope="市场", chunk_index=0),
                _node(2, "产品句。", scope="产品", chunk_index=1),
            ],
            "edges": [],
            "alerts": [],
        }
        refiner.refine(snap)
        prompt = mock_client.chat.call_args[1]["messages"][0]["content"]
        assert "市场" in prompt
        assert "产品" in prompt
        assert "(市场)" in prompt

    def test_instructions_in_prompt(self):
        """prompt 中包含句子标注信息"""
        mock_chat = MagicMock()
        mock_client = MagicMock()
        mock_client.chat.return_value = mock_chat

        refiner = LLMRefiner(llm_client=mock_client)
        snap = {
            "nodes": [
                _node(1, "第一句。", chunk_index=0),
                _node(2, "第二句。", chunk_index=1),
            ],
            "edges": [],
            "alerts": [],
        }
        refiner.refine(snap)
        prompt = mock_client.chat.call_args[1]["messages"][0]["content"]
        assert "第一句。" in prompt
        assert "第二句。" in prompt

    def test_labels_in_prompt(self):
        """多句场景下标注包含角色和关系信息"""
        mock_chat = MagicMock()
        mock_client = MagicMock()
        mock_client.chat.return_value = mock_chat

        refiner = LLMRefiner(llm_client=mock_client)
        snap = {
            "nodes": [
                _node(1, "原因句。", role="nucleus", relation="cause", chunk_index=0),
                _node(2, "结果句。", role="satellite", relation="result", chunk_index=1),
            ],
            "edges": [],
            "alerts": [],
        }
        refiner.refine(snap)
        prompt = mock_client.chat.call_args[1]["messages"][0]["content"]
        assert "nucleus" in prompt  # English role tag
        assert "cause" in prompt  # English relation tag


class TestLLMRefinerIntegration:
    """与 TextOutput fallback 的集成测试"""

    def test_format_simple_output(self):
        """format_simple 按 scope 分组输出原句"""
        refiner = LLMRefiner(llm_client=MagicMock())
        snap = {
            "nodes": [
                _node(1, "市场句。", scope="市场", chunk_index=0),
                _node(2, "预算句。", scope="预算", chunk_index=1),
            ],
            "edges": [],
            "alerts": [],
        }
        result = refiner._fallback.format_simple(snap)
        assert "## 市场" in result
        assert "## 预算" in result
        assert "市场句。" in result
        assert "预算句。" in result
        # 无前缀标记
        assert "+ " not in result
        assert "- " not in result
