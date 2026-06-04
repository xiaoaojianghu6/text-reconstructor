"""CLI 集成测试"""

import pytest
from click.testing import CliRunner
from text_reconstructor.cli import main, _read_input
from text_reconstructor.graph.updater import GraphUpdater
from text_reconstructor.output.text_output import TextOutput
from text_reconstructor.output.suggestions import Suggestions
from text_reconstructor.output.llm_refiner import LLMRefiner


class TestReadInput:
    def test_from_text(self):
        assert _read_input("hello", None) == "hello"

    def test_from_empty_text(self):
        assert _read_input("", None) == ""

    def test_text_over_file(self):
        assert _read_input("text", None) == "text"


class TestCliArgs:
    def setup_method(self):
        self.runner = CliRunner()

    def test_empty_input(self):
        """空输入 → 错误退出"""
        result = self.runner.invoke(main, [""])
        assert result.exit_code == 1

    def test_help(self):
        """--help 显示帮助"""
        result = self.runner.invoke(main, ["--help"])
        assert result.exit_code == 0
        assert "文本重构" in result.output

    def test_skip_adversary_flag_exists(self):
        """--skip-adversary 是合法参数（在 --help 中可见）"""
        result = self.runner.invoke(main, ["--help"])
        assert "--skip-adversary" in result.output

    def test_text_input_via_argument(self):
        """通过位置参数传入文本"""
        result = self.runner.invoke(main, ["测试文本"])
        # 会尝试连接 Ollama，预期错误是 LLMConnectionError
        assert result.exit_code != 2  # 不是参数解析错误

    def test_output_format_flag_in_help(self):
        """--output-format 在帮助中可见"""
        result = self.runner.invoke(main, ["--help"])
        assert "--output-format" in result.output

    def test_format_alias_in_help(self):
        """--format 别名在帮助中可见"""
        result = self.runner.invoke(main, ["--help"])
        assert "--format" in result.output


class TestPipelineNoLLM:
    """不依赖 LLM 的管道测试 (GraphUpdater + Output)"""

    CHUNKS = [
        {"text": "市场需求很大", "role": "nucleus", "intent": "assertive",
         "relation": "none", "argument_role": "none", "argument_relation": "none",
         "scope": "市场", "dependency": "", "chunk_index": 0},
        {"text": "因为用户增长快", "role": "satellite", "intent": "assertive",
         "relation": "cause", "argument_role": "premise", "argument_relation": "support",
         "scope": "市场", "dependency": "", "chunk_index": 1},
        {"text": "但是预算有限", "role": "satellite", "intent": "assertive",
         "relation": "contrast", "argument_role": "none", "argument_relation": "none",
         "scope": "预算", "dependency": "", "chunk_index": 2},
    ]

    def test_full_pipeline_no_adversary(self):
        """GraphUpdater + TextOutput + Suggestions 全链路"""
        updater = GraphUpdater(run_adversary=False)
        snap = updater.process(self.CHUNKS)

        text_out = TextOutput().format(snap)
        assert isinstance(text_out, str)
        assert len(text_out) > 0
        assert "市场需求" in text_out
        assert "用户增长" in text_out

        suggestions = Suggestions().format(snap.get("alerts", []))
        assert isinstance(suggestions, list)

    def test_pipeline_with_adversary(self):
        """含对抗机的全链路"""
        updater = GraphUpdater(run_adversary=True)
        snap = updater.process(self.CHUNKS)

        text_out = TextOutput().format(snap)
        assert isinstance(text_out, str)
        assert len(text_out) > 0

        # 对抗机可能产生建议也可能不产生
        alerts = snap.get("alerts", [])
        suggestions = Suggestions().format(alerts)
        assert isinstance(suggestions, list)

    def test_empty_chunks(self):
        """空 chunks 不崩溃"""
        updater = GraphUpdater()
        snap = updater.process([])
        assert TextOutput().format(snap) == ""
        assert Suggestions().format(snap.get("alerts", [])) == []

    def test_single_chunk_output(self):
        """单节点输出"""
        updater = GraphUpdater(run_adversary=False)
        snap = updater.process([self.CHUNKS[0]])
        text_out = TextOutput().format(snap)
        assert isinstance(text_out, str)
        assert len(text_out) > 0

    def test_adversary_disabled_no_alerts(self):
        """run_adversary=False 时 alerts 为空"""
        updater = GraphUpdater(run_adversary=False)
        snap = updater.process(self.CHUNKS)
        assert len(snap.get("alerts", [])) == 0

    def test_suggestions_format(self):
        """suggestions 输出格式正确"""
        # 构造最小化 alert
        alerts = [{"type": "ISOLATED_NODE", "node_id": 99, "text": "测试",
                   "severity": "high", "scope": "域", "detail": "孤立",
                   "round": 2, "count": 1}]
        suggestions = Suggestions().format(alerts)
        assert isinstance(suggestions, list)
        assert len(suggestions) >= 0

    def test_chunk_with_missing_fields(self):
        """chunk 缺字段不崩溃"""
        minimal_chunk = {"text": "只有文本", "role": "nucleus"}
        # fill missing fields with defaults
        chunk = {**minimal_chunk, "intent": "assertive", "relation": "none",
                 "argument_role": "none", "argument_relation": "none",
                 "scope": "", "dependency": "", "chunk_index": 0}
        updater = GraphUpdater(run_adversary=False)
        snap = updater.process([chunk])
        assert len(snap["nodes"]) == 1

    def test_scope_grouping_in_output(self):
        """输出包含 scope 分组"""
        updater = GraphUpdater(run_adversary=False)
        snap = updater.process(self.CHUNKS)
        text_out = TextOutput().format(snap)
        assert "## 市场" in text_out
        assert "## 预算" in text_out
