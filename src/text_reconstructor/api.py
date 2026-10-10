"""FastAPI 本地服务 -- Tauri 前端后端接口

提供 /api/process (快速VPGA输出) 和 /api/audit (异步管线审查) 两个端点。
"""

from __future__ import annotations

import asyncio
import json
import logging
import threading
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from text_reconstructor.llm import LLMConfig
from text_reconstructor.output.interactive_questions import InteractiveItem
from text_reconstructor.output.llm_review_extractor import extract_and_clean
from text_reconstructor.output.vpga_refiner import VPGARefiner
from text_reconstructor.output.refinement_refiner import Answer, RefinementRefiner

logger = logging.getLogger(__name__)

_graph_lock = threading.Lock()

_DEFAULT_CONFIG = lambda: LLMConfig(
    backend="nvidia",
    model="deepseek-ai/deepseek-v4-flash",
    base_url="https://integrate.api.nvidia.com/v1",
    max_tokens=8192,
    temperature=0.15,
    timeout=90.0,  # NVIDIA 响应慢，给足单次调用时间
)

_TAGGER_CONFIG = lambda: LLMConfig(
    backend="nvidia",
    model="deepseek-ai/deepseek-v4-flash",
    base_url="https://integrate.api.nvidia.com/v1",
    max_tokens=512,
    temperature=0.1,
    timeout=60.0,
)


# -- Request/Response Models --

class ProcessRequest(BaseModel):
    text: str
    mode: str = "developer"
    folder_path: str = ""
    file_id: str = ""
    file_path: str = ""
    previous_output: str = ""


class AuditRequest(BaseModel):
    text: str
    output: str  # VPGA 输出，管线审查用
    folder_path: str = ""
    file_id: str = ""
    file_path: str = ""


class RefineRequest(BaseModel):
    previous_output: str
    answers: list[dict] = []
    user_note: str = ""


class SaveStateRequest(BaseModel):
    folder_path: str
    file_path: str
    output: str = ""
    questions: list[dict] = []


class LoadStateRequest(BaseModel):
    folder_path: str


class QuestionResponse(BaseModel):
    category: str
    needs_input: bool
    question: str
    source_text: str
    alert_type: str
    severity: str
    score: float


class ProcessResponse(BaseModel):
    output: str
    questions: list[QuestionResponse]


class AuditResponse(BaseModel):
    questions: list[QuestionResponse]


class RefineResponse(BaseModel):
    output: str
    questions: list[QuestionResponse]


# -- App --

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Text Reconstructor API 启动")
    yield
    logger.info("Text Reconstructor API 关闭")


app = FastAPI(title="Text Reconstructor API", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.post("/api/process", response_model=ProcessResponse)
async def process(req: ProcessRequest):
    """快速 VPGA 输出 (1 次 LLM 调用, 10-30s)"""
    config = _DEFAULT_CONFIG()
    # 重新处理: 有 previous_output 说明用户点了重试，提高温度产生差异化输出
    if req.previous_output:
        config.temperature = 0.6
    vpga = VPGARefiner(config=config, mode=req.mode)
    raw_output = None
    last_error = None
    _VPGA_DEADLINE = 75.0  # 单次调用总超时 (LLM timeout=90s, max_retries=1)
    for attempt in range(3):
        try:
            task = asyncio.to_thread(vpga.refine, req.text, req.previous_output)
            raw_output = await asyncio.wait_for(task, timeout=_VPGA_DEADLINE)
            break
        except asyncio.TimeoutError:
            last_error = Exception(f"VPGA 超时({_VPGA_DEADLINE}s)")
            if attempt < 2:
                logger.warning("VPGA 第%d次超时(%ss), 重试...", attempt + 1, _VPGA_DEADLINE)
                await asyncio.sleep(2.0 * (attempt + 1))
        except Exception as e:
            last_error = e
            if attempt < 2:
                logger.warning("VPGA 第%d次失败: %s, 重试...", attempt + 1, e)
                await asyncio.sleep(2.0 * (attempt + 1))
    if raw_output is None:
        logger.error("VPGA 处理失败(重试3次): %s", last_error)
        raise _llm_error(str(last_error))

    clean_output, llm_reviews = extract_and_clean(raw_output)

    # 只提取 LLM 审查标记作为快速提问，不等管线审查
    from text_reconstructor.output.interactive_questions import InteractiveQuestions
    iq = InteractiveQuestions(threshold=0.6)
    questions = iq.format(alerts=[], llm_reviews=llm_reviews)

    # 自动保存输出状态（不依赖前端单独调用 save-state）
    _auto_save_state(req.folder_path, req.file_path, clean_output, questions)

    return ProcessResponse(
        output=clean_output,
        questions=[_item_to_response(q) for q in questions],
    )


@app.post("/api/audit", response_model=AuditResponse)
async def audit(req: AuditRequest):
    """管线审查 (Tagger + Graph + 对抗机, 异步调用)"""
    import time as _time
    t0 = _time.monotonic()

    persist_path = ""
    if req.folder_path:
        from pathlib import Path
        graph_dir = Path(req.folder_path) / ".text-reconstructor"
        graph_dir.mkdir(parents=True, exist_ok=True)
        persist_path = str(graph_dir / "graph.json")

    # 管线审查用原文
    _, llm_reviews = extract_and_clean(req.output)
    questions = await asyncio.to_thread(
        _run_audit_track, req.text, llm_reviews,
        persist_path=persist_path,
        file_id=req.file_id,
        file_path=req.file_path,
    )

    logger.info("管线审查完成: %.1fs, %d 个提问", _time.monotonic() - t0, len(questions))

    # 合并审查问题到已有状态文件
    if req.folder_path and req.file_path:
        _merge_audit_questions(req.folder_path, req.file_path, questions)

    return AuditResponse(
        questions=[_item_to_response(q) for q in questions],
    )


@app.post("/api/refine", response_model=RefineResponse)
async def refine(req: RefineRequest):
    """增量微调"""
    answers = [Answer(**a) for a in req.answers]
    config = _DEFAULT_CONFIG()
    refiner = RefinementRefiner(config=config)
    try:
        raw_output = await asyncio.to_thread(refiner.refine, req.previous_output, answers, req.user_note)
    except Exception as e:
        logger.error("微调失败: %s", e)
        raise _llm_error(str(e))

    clean_output, llm_reviews = extract_and_clean(raw_output)

    from text_reconstructor.output.interactive_questions import InteractiveQuestions
    iq = InteractiveQuestions(threshold=0.6)
    questions = iq.format(alerts=[], llm_reviews=llm_reviews)

    return RefineResponse(
        output=clean_output,
        questions=[_item_to_response(q) for q in questions],
    )


def _run_audit_track(
    text: str,
    llm_reviews: list,
    persist_path: str = "",
    file_id: str = "",
    file_path: str = "",
) -> list[InteractiveItem]:
    """管线审查: Tagger -> Graph -> 对抗机 -> 提问 (加锁防图谱竞态)

    目标总耗时: 30s(Tagger) + 30s(对抗机) = ~60s
    """
    with _graph_lock:
        return _run_audit_track_inner(
            text, llm_reviews,
            persist_path=persist_path,
            file_id=file_id,
            file_path=file_path,
        )


def _run_audit_track_inner(
    text: str,
    llm_reviews: list,
    persist_path: str = "",
    file_id: str = "",
    file_path: str = "",
) -> list[InteractiveItem]:
    """管线审查内部实现"""
    import time as _time
    t0 = _time.monotonic()
    try:
        from text_reconstructor.processor.chunker import SentenceSplitter
        from text_reconstructor.processor.tagger import Tagger
        from text_reconstructor.graph.updater import GraphUpdater
        from text_reconstructor.output.interactive_questions import InteractiveQuestions

        tagger_config = _TAGGER_CONFIG()
        splitter = SentenceSplitter()
        sentences = splitter.split(text)
        if not sentences:
            return []

        tagger = Tagger(config=tagger_config)
        chunks = tagger.batch_tag(sentences)
        logger.info("管线: Tagger完成 %.1fs", _time.monotonic() - t0)

        persist = persist_path or None
        updater = GraphUpdater(
            run_adversary=True,
            llm_config=tagger_config,
            persist_path=persist,
            file_id=file_id,
            file_path=file_path,
        )
        snapshot = updater.process(chunks)
        alerts = snapshot.get("alerts", [])
        logger.info("管线: 对抗机完成 %.1fs, %d alerts", _time.monotonic() - t0, len(alerts))

        iq = InteractiveQuestions(threshold=0.6)
        return iq.format(alerts=alerts, llm_reviews=llm_reviews)
    except Exception as e:
        logger.warning("管线审查失败: %s", e)
        return []


def _llm_error(detail: str) -> HTTPException:
    return HTTPException(status_code=503, detail=detail)


def _auto_save_state(folder_path: str, file_path: str, output: str, questions: list):
    """自动保存处理状态到 .text-reconstructor/ 目录"""
    if not folder_path or not file_path:
        return
    try:
        from pathlib import Path
        graph_dir = Path(folder_path) / ".text-reconstructor"
        graph_dir.mkdir(parents=True, exist_ok=True)
        file_name = Path(file_path).name
        state_path = graph_dir / f"{file_name}.state.json"
        state_path.write_text(
            json.dumps({
                "output": output,
                "questions": [_question_to_dict(q) for q in (questions or [])],
            }, ensure_ascii=False),
            encoding="utf-8",
        )
        logger.info("自动保存状态: %s (%d 字, %d 提问)", state_path, len(output or ""), len(questions or []))
    except Exception as e:
        logger.warning("自动保存状态失败: %s", e)


def _merge_audit_questions(folder_path: str, file_path: str, new_questions: list):
    """将管线审查问题合并到已有状态文件"""
    if not folder_path or not file_path:
        return
    try:
        from pathlib import Path
        graph_dir = Path(folder_path) / ".text-reconstructor"
        file_name = Path(file_path).name
        state_path = graph_dir / f"{file_name}.state.json"
        existing_data = {"output": "", "questions": []}
        if state_path.exists():
            try:
                existing_data = json.loads(state_path.read_text(encoding="utf-8"))
            except Exception:
                pass
        existing_qs = existing_data.get("questions", [])
        existing_texts = {q.get("question", "") for q in existing_qs}
        merged_qs = existing_qs + [
            _question_to_dict(q) for q in new_questions
            if (q.question if hasattr(q, 'question') else q.get("question", "")) not in existing_texts
        ]
        state_path.write_text(
            json.dumps({"output": existing_data.get("output", ""), "questions": merged_qs}, ensure_ascii=False),
            encoding="utf-8",
        )
        logger.info("合并审查问题: %s (%d -> %d 提问)", state_path, len(existing_qs), len(merged_qs))
    except Exception as e:
        logger.warning("合并审查问题失败: %s", e)


def _question_to_dict(q) -> dict:
    if hasattr(q, 'category'):
        return {"category": q.category, "needs_input": q.needs_input, "question": q.question,
                "source_text": q.source_text, "alert_type": q.alert_type, "severity": q.severity, "score": q.score}
    return {"category": q.get("category", ""), "needs_input": q.get("needs_input", False),
            "question": q.get("question", ""), "source_text": q.get("source_text", ""),
            "alert_type": q.get("alert_type", ""), "severity": q.get("severity", ""),
            "score": q.get("score", 0.0)}


def _item_to_response(item: InteractiveItem) -> QuestionResponse:
    return QuestionResponse(
        category=item.category,
        needs_input=item.needs_input,
        question=item.question,
        source_text=item.source_text,
        alert_type=item.alert_type,
        severity=item.severity,
        score=item.score,
    )


@app.post("/api/save-state")
async def save_state(req: SaveStateRequest):
    """保存文件处理状态到 .text-reconstructor/ 目录"""
    if not req.folder_path or not req.file_path:
        return {"ok": False}
    try:
        from pathlib import Path
        graph_dir = Path(req.folder_path) / ".text-reconstructor"
        graph_dir.mkdir(parents=True, exist_ok=True)
        file_name = Path(req.file_path).name
        state_path = graph_dir / f"{file_name}.state.json"
        state_path.write_text(
            json.dumps({"output": req.output, "questions": req.questions}, ensure_ascii=False),
            encoding="utf-8",
        )
        logger.info("保存状态: %s", state_path)
        return {"ok": True}
    except Exception as e:
        logger.error("保存状态失败: %s", e)
        return {"ok": False, "error": str(e)}


@app.post("/api/load-states")
async def load_states(req: LoadStateRequest):
    """加载文件夹下所有 .state.json"""
    if not req.folder_path:
        return {"states": {}}
    try:
        from pathlib import Path
        graph_dir = Path(req.folder_path) / ".text-reconstructor"
        states = {}
        if graph_dir.exists():
            for f in graph_dir.glob("*.state.json"):
                try:
                    data = json.loads(f.read_text(encoding="utf-8"))
                    original_name = f.name.replace(".state.json", "")
                    states[f"{req.folder_path}/{original_name}"] = {
                        "output": data.get("output", ""),
                        "questions": data.get("questions", []),
                    }
                except Exception:
                    pass
        return {"states": states}
    except Exception as e:
        logger.error("加载状态失败: %s", e)
        return {"states": {}}


def start_server(port: int = 18231):
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=port, log_level="info")
