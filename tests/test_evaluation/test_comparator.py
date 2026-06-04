"""评估模块单元测试"""

import unittest
from unittest.mock import MagicMock, patch

from text_reconstructor.evaluation.comparator import Evaluator
from text_reconstructor.evaluation.report import ReportGenerator, load_test_texts


class TestEvaluator(unittest.TestCase):
    @patch("text_reconstructor.evaluation.comparator.create_client")
    def test_baseline_output(self, mock_factory):
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.content = "基线梳理结果"
        mock_client.chat.return_value = mock_response
        mock_factory.return_value = mock_client

        evaluator = Evaluator()
        result = evaluator.baseline_output("测试文本")
        self.assertEqual(result, "基线梳理结果")
        mock_client.chat.assert_called_once()

    @patch("text_reconstructor.evaluation.comparator.create_client")
    def test_score_outputs(self, mock_factory):
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.content = '{"baseline": {"detail_preservation": 7}, "pipeline": {"detail_preservation": 8}, "summary": "test"}'
        mock_client.chat.return_value = mock_response
        mock_factory.return_value = mock_client

        evaluator = Evaluator()
        scores = evaluator.score_outputs("原文", "基线", "管线")
        self.assertEqual(scores["baseline"]["detail_preservation"], 7)
        self.assertEqual(scores["pipeline"]["detail_preservation"], 8)


class TestReportGenerator(unittest.TestCase):
    def test_format_section(self):
        evaluator = MagicMock()
        generator = ReportGenerator(evaluator)
        report = generator._format_section(
            1, "测试1", "原始文本",
            "基线输出", "管线输出",
            {
                "baseline": {"detail_preservation": 7, "doubt_identification": 5, "fuzzy_concept_handling": 6, "structure_clarity": 7},
                "pipeline": {"detail_preservation": 8, "doubt_identification": 7, "fuzzy_concept_handling": 7, "structure_clarity": 8},
                "summary": "系统输出更优",
            },
        )
        self.assertIn("测试文本 1", report)
        self.assertIn("细节保留", report)
        self.assertIn("系统优", report)
        self.assertIn("系统输出更优", report)

    def test_load_test_texts(self):
        texts = load_test_texts()
        self.assertIsInstance(texts, list)
        if texts:
            self.assertIn("text", texts[0])
            self.assertIn("label", texts[0])


if __name__ == "__main__":
    unittest.main()
