"""测试 FastAPI 后端 API"""

import pytest
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient

from text_reconstructor.api import app


@pytest.fixture
def client():
    return TestClient(app)


class TestProcessEndpoint:
    @patch("text_reconstructor.api.VPGARefiner")
    @patch("text_reconstructor.api._run_audit_track")
    def test_process_writer_mode(self, mock_audit, mock_vpga_cls, client):
        mock_refiner = MagicMock()
        mock_refiner.refine.return_value = "重构结果[疑点: 测试]"
        mock_vpga_cls.return_value = mock_refiner
        mock_audit.return_value = []

        resp = client.post("/api/process", json={
            "text": "测试文本",
            "mode": "writer",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert "output" in data
        assert "疑点" not in data["output"]
        # LLM reviews from [疑点:] marker are extracted as questions
        assert len(data["questions"]) >= 1

    @patch("text_reconstructor.api.VPGARefiner")
    @patch("text_reconstructor.api._run_audit_track")
    def test_process_developer_mode(self, mock_audit, mock_vpga_cls, client):
        mock_refiner = MagicMock()
        mock_refiner.refine.return_value = "开发者模式输出"
        mock_vpga_cls.return_value = mock_refiner
        mock_audit.return_value = []

        resp = client.post("/api/process", json={
            "text": "测试文本",
            "mode": "developer",
        })
        assert resp.status_code == 200

    @patch("text_reconstructor.api.VPGARefiner")
    @patch("text_reconstructor.api._run_audit_track")
    def test_process_extracts_reviews(self, mock_audit, mock_vpga_cls, client):
        from text_reconstructor.output.llm_review_extractor import LLMReviewItem
        from text_reconstructor.output.interactive_questions import InteractiveItem

        mock_refiner = MagicMock()
        mock_refiner.refine.return_value = "文本[疑点: 含义不明]结尾"
        mock_vpga_cls.return_value = mock_refiner

        review = LLMReviewItem(
            marker_type="doubt", content="含义不明",
            position=2, surrounding="文本[疑点: 含义不明]结尾",
        )
        mock_audit.return_value = [
            InteractiveItem(
                category="ambiguity", needs_input=True,
                question="「含义不明」-- 需要补充说明?",
                source_text="", alert_type="llm_doubt",
                severity="medium", score=0.72,
            )
        ]

        resp = client.post("/api/process", json={"text": "测试", "mode": "writer"})
        data = resp.json()
        assert len(data["questions"]) == 1
        assert data["questions"][0]["category"] == "ambiguity"


class TestRefineEndpoint:
    @patch("text_reconstructor.api.RefinementRefiner")
    @patch("text_reconstructor.api._run_audit_track")
    def test_refine_with_answers(self, mock_audit, mock_refiner_cls, client):
        mock_refiner = MagicMock()
        mock_refiner.refine.return_value = "微调后输出"
        mock_refiner_cls.return_value = mock_refiner
        mock_audit.return_value = []

        resp = client.post("/api/refine", json={
            "previous_output": "上一版输出",
            "answers": [{"question_index": 0, "user_input": "手风琴是UI组件"}],
            "user_note": "精简一下",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["output"] == "微调后输出"

    @patch("text_reconstructor.api.RefinementRefiner")
    @patch("text_reconstructor.api._run_audit_track")
    def test_refine_no_changes(self, mock_audit, mock_refiner_cls, client):
        mock_refiner = MagicMock()
        mock_refiner.refine.return_value = "上一版输出"
        mock_refiner_cls.return_value = mock_refiner
        mock_audit.return_value = []

        resp = client.post("/api/refine", json={
            "previous_output": "上一版输出",
            "answers": [],
            "user_note": "",
        })
        assert resp.status_code == 200
