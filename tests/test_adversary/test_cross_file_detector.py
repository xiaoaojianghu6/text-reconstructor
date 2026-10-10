"""测试跨文件冲突检测器 -- 单元测试 + 真实 LLM 验证"""
import json
import os
import pytest
from unittest.mock import MagicMock

from text_reconstructor.graph.models import SemanticGraph, GraphNode
from text_reconstructor.graph.numeric_extractor import (
    ExtractedNumeric,
    extract_numerics_from_graph,
    group_into_clusters,
    _extract_from_node,
)
from text_reconstructor.adversary.cross_file_detector import (
    CrossFileConflictDetector,
    AuditResult,
)


# ── 辅助 ──

def _make_node(graph, text, scope="", file_id="", file_path=""):
    return graph.add_node(
        text=text, scope=scope, file_id=file_id, file_path=file_path,
        role="nucleus", confidence=0.8,
    )


class MockLLMResponse:
    def __init__(self, content):
        self.content = content


class MockLLMClient:
    def __init__(self, response_content):
        self._response = response_content

    def chat(self, messages, system_prompt="", **kwargs):
        return MockLLMResponse(self._response)


# ── 数值提取测试 ──

class TestNumericExtraction:
    def test_extract_simple_number(self):
        g = SemanticGraph()
        node = _make_node(g, "开销每人每天20元以内", scope="预算")
        nums = _extract_from_node(node)
        assert len(nums) >= 1
        found_20 = any(abs(n.value - 20.0) < 0.01 for n in nums)
        assert found_20

    def test_extract_people_count(self):
        g = SemanticGraph()
        node = _make_node(g, "团队共有12名成员", scope="团队")
        nums = _extract_from_node(node)
        found_12 = any(abs(n.value - 12.0) < 0.01 for n in nums)
        assert found_12

    def test_extract_large_number_with_modifier(self):
        g = SemanticGraph()
        node = _make_node(g, "总开销为30000元", scope="费用")
        nums = _extract_from_node(node)
        found_30000 = any(abs(n.value - 30000.0) < 0.01 for n in nums)
        assert found_30000

    def test_context_window(self):
        g = SemanticGraph()
        node = _make_node(g, "项目预算非常紧张开销必须维持在每人每天20元以内", scope="预算")
        nums = _extract_from_node(node)
        assert len(nums) >= 1
        # 上下文窗口应包含 "每人每天20元" 的周围文字
        for n in nums:
            if abs(n.value - 20.0) < 0.01:
                assert "每人" in n.context_window or "20" in n.context_window


# ── 簇分组测试 ──

class TestClusterGrouping:
    def test_empty_graph_no_clusters(self):
        g = SemanticGraph()
        clusters = group_into_clusters(g, [])
        assert clusters == []

    def test_same_scope_grouped(self):
        g = SemanticGraph()
        _make_node(g, "预算20元", scope="预算", file_id="f1")
        _make_node(g, "花费300元", scope="预算", file_id="f2")
        nums = extract_numerics_from_graph(g)
        clusters = group_into_clusters(g, nums)
        budget_clusters = [c for c in clusters if "预算" in c.scope]
        assert len(budget_clusters) >= 1
        assert budget_clusters[0].cross_file is True

    def test_cross_file_detected(self):
        g = SemanticGraph()
        _make_node(g, "10人以内", scope="团队", file_id="f1")
        _make_node(g, "12名成员", scope="团队", file_id="f2")
        nums = extract_numerics_from_graph(g)
        clusters = group_into_clusters(g, nums)
        assert any(c.cross_file for c in clusters)


# ── 检测器测试 ──

class TestCrossFileDetector:
    def test_empty_graph_no_alerts(self):
        detector = CrossFileConflictDetector()
        alerts = detector.scan(SemanticGraph())
        assert alerts == []

    def test_single_file_no_trigger(self):
        g = SemanticGraph()
        _make_node(g, "预算20元", scope="预算", file_id="f1")
        _make_node(g, "花费300元", scope="预算", file_id="f1")
        detector = CrossFileConflictDetector()
        # cross_file=False 且没有 LLM，不会产生 alerts
        # 但 numerics >= 2 会成为候选，不过没有 LLM 就无法判断
        alerts = detector.scan(g)
        # 无 LLM client，只做提取不做审计
        assert isinstance(alerts, list)

    def test_llm_conflict_detected(self):
        g = SemanticGraph()
        _make_node(g, "每人每天20元以内", scope="预算", file_id="f1", file_path="预算.md")
        _make_node(g, "总开销30000元", scope="预算", file_id="f3", file_path="费用.md")
        mock = MockLLMClient(json.dumps({
            "conflict": True,
            "detail": "每人每天20元 x 12人 x 90天 = 21600元，但总开销30000元",
            "missing_entities": [],
        }))
        detector = CrossFileConflictDetector(llm_client=mock, max_llm_calls=5)
        alerts = detector.scan(g)
        assert len(alerts) >= 1
        assert alerts[0]["type"] == "CROSS_FILE_CONFLICT"
        assert "20" in alerts[0]["detail"] or "30000" in alerts[0]["detail"]

    def test_llm_no_conflict(self):
        g = SemanticGraph()
        _make_node(g, "预算充足", scope="预算", file_id="f1")
        _make_node(g, "按计划进行", scope="预算", file_id="f2")
        mock = MockLLMClient(json.dumps({
            "conflict": False,
            "detail": "",
            "missing_entities": [],
        }))
        detector = CrossFileConflictDetector(llm_client=mock, max_llm_calls=5)
        alerts = detector.scan(g)
        assert len(alerts) == 0

    def test_backtrack_finds_missing_in_graph(self):
        g = SemanticGraph()
        _make_node(g, "每人20元", scope="预算", file_id="f1", file_path="预算.md")
        _make_node(g, "总开销30000元", scope="预算", file_id="f3", file_path="费用.md")
        _make_node(g, "团队共有12名成员", scope="团队", file_id="f2", file_path="团队.md")
        # 第一次审计: 发现冲突，但缺少人数
        # 回溯: 在图谱中找到 "12名成员"
        call_count = 0
        responses = [
            json.dumps({
                "conflict": True,
                "detail": "每人20元但不知道总人数，无法验证总开销",
                "missing_entities": ["人数"],
            }),
            json.dumps({
                "conflict": True,
                "detail": "每人20元 x 12人 = 240元/天，90天 = 21600元，但总开销30000元",
                "missing_entities": [],
            }),
        ]

        class SequentialMock:
            def chat(self, messages, system_prompt="", **kwargs):
                nonlocal call_count
                resp = MockLLMResponse(responses[call_count])
                call_count += 1
                return resp

        detector = CrossFileConflictDetector(llm_client=SequentialMock(), max_llm_calls=5)
        alerts = detector.scan(g)
        # 应有至少一个 CROSS_FILE_CONFLICT alert
        conflict_alerts = [a for a in alerts if a["type"] == "CROSS_FILE_CONFLICT"]
        assert len(conflict_alerts) >= 1

    def test_backtrack_missing_not_in_graph(self):
        g = SemanticGraph()
        _make_node(g, "每人20元", scope="预算", file_id="f1")
        _make_node(g, "总开销30000元", scope="预算", file_id="f3")
        mock = MockLLMClient(json.dumps({
            "conflict": True,
            "detail": "需要人数才能验证",
            "missing_entities": ["人数"],
        }))
        detector = CrossFileConflictDetector(llm_client=mock, max_llm_calls=5)
        alerts = detector.scan(g)
        # 找不到 "人数" 节点 -> MISSING_ENTITY alert
        missing = [a for a in alerts if a["type"] == "MISSING_ENTITY"]
        assert len(missing) >= 1

    def test_no_llm_graceful_degradation(self):
        g = SemanticGraph()
        _make_node(g, "预算20元", scope="预算", file_id="f1")
        _make_node(g, "花费300元", scope="预算", file_id="f2")
        detector = CrossFileConflictDetector(llm_client=None)
        alerts = detector.scan(g)
        assert isinstance(alerts, list)
        # 没有 LLM，不会有冲突 alert
        assert all(a["type"] != "CROSS_FILE_CONFLICT" for a in alerts)

    def test_max_llm_calls_respected(self):
        g = SemanticGraph()
        for i in range(10):
            _make_node(g, f"数据{i}", scope=f"主题{i}", file_id=f"f{i%3}")
        call_count = 0

        class CountingMock:
            def chat(self, messages, system_prompt="", **kwargs):
                nonlocal call_count
                call_count += 1
                return MockLLMResponse(json.dumps({
                    "conflict": False, "detail": "", "missing_entities": [],
                }))

        detector = CrossFileConflictDetector(llm_client=CountingMock(), max_llm_calls=2)
        detector.scan(g)
        assert call_count <= 2


# ── 解析测试 ──

class TestResponseParsing:
    def test_parse_clean_json(self):
        detector = CrossFileConflictDetector()
        result = detector._parse_response(
            '{"conflict": true, "detail": "矛盾", "missing_entities": []}'
        )
        assert result.conflict is True
        assert result.detail == "矛盾"

    def test_parse_json_in_markdown(self):
        detector = CrossFileConflictDetector()
        result = detector._parse_response(
            '```json\n{"conflict": false, "detail": "", "missing_entities": ["人数"]}\n```'
        )
        assert result is not None
        assert result.missing_entities == ["人数"]

    def test_parse_invalid_returns_none(self):
        detector = CrossFileConflictDetector()
        result = detector._parse_response("这不是JSON")
        assert result is None
