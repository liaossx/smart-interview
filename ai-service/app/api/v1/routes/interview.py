"""面试 API 路由"""

import json
from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import Optional, List
from app.services.interview_service import session_store

router = APIRouter()


class StartInterviewRequest(BaseModel):
    jd_content: str
    resume_content: str = ""
    user_id: int = 1


class SubmitAnswerRequest(BaseModel):
    session_id: str
    answer: str


class RestoreQaItem(BaseModel):
    question: str = ""
    category: str = ""
    answer: str = ""
    score: int = 0
    feedback: str = ""


class RestoreSessionRequest(BaseModel):
    jd_content: str
    resume_content: str = ""
    qas: List[RestoreQaItem] = []
    questions: List[dict] = []
    current_question_index: int = 0
    user_id: int = 1
    existing_session_id: Optional[str] = None


def _sse(event: dict) -> str:
    """将事件 dict 格式化为 SSE 字符串"""
    event_type = event.get("event", "message")
    payload = event.get("data", event)
    if "data" in event:
        payload = event["data"]
    else:
        # progress 事件只有 step + message，整体作为 data
        payload = {k: v for k, v in event.items() if k != "event"}
    return f"event: {event_type}\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"


@router.post("/interview/start")
async def start_interview(request: StartInterviewRequest):
    """开始面试：分析 JD + 简历 → 生成题目 → 返回第一题"""
    session = session_store.create(
        jd_content=request.jd_content,
        resume_content=request.resume_content,
        user_id=request.user_id,
    )
    try:
        result = session.analyze()
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"分析失败: {str(e)}")


@router.post("/interview/start/stream")
async def start_interview_stream(request: StartInterviewRequest):
    """开始面试（SSE 流式）：实时推送分析进度"""
    session = session_store.create(
        jd_content=request.jd_content,
        resume_content=request.resume_content,
        user_id=request.user_id,
    )

    def generate():
        try:
            for event in session.analyze_stream():
                yield _sse(event)
        except Exception as e:
            yield _sse({"event": "error", "data": {"message": f"分析失败: {str(e)}"}})

    return StreamingResponse(generate(), media_type="text/event-stream")


@router.post("/interview/restore")
async def restore_interview(request: RestoreSessionRequest):
    """恢复面试：从后端 MySQL 数据重建状态，继续作答"""
    session = session_store.restore(
        jd_content=request.jd_content,
        resume_content=request.resume_content,
        qas=[qa.model_dump() for qa in request.qas],
        questions=request.questions,
        current_question_index=request.current_question_index,
        user_id=request.user_id,
        existing_session_id=request.existing_session_id,
    )
    try:
        result = session.resume_analyze()
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"恢复失败: {str(e)}")


@router.post("/interview/answer")
async def submit_answer(request: SubmitAnswerRequest):
    """提交答案 → 评分 → 返回下一题"""
    session = session_store.get(request.session_id)
    if not session:
        raise HTTPException(status_code=404, detail="会话不存在")
    try:
        result = session.submit_answer(request.answer)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"评分失败: {str(e)}")


@router.post("/interview/answer/stream")
async def submit_answer_stream(request: SubmitAnswerRequest):
    """提交答案（SSE 流式）：实时推送评分进度"""
    session = session_store.get(request.session_id)
    if not session:
        raise HTTPException(status_code=404, detail="会话不存在")

    def generate():
        try:
            for event in session.submit_answer_stream(request.answer):
                yield _sse(event)
        except Exception as e:
            yield _sse({"event": "error", "data": {"message": f"评分失败: {str(e)}"}})

    return StreamingResponse(generate(), media_type="text/event-stream")


@router.get("/interview/current/{session_id}")
async def get_current_question(session_id: str):
    """获取当前题目状态（不提交答案），用于页面刷新恢复"""
    session = session_store.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="会话不存在")
    return session.get_current_question()


@router.get("/interview/result/{session_id}")
async def get_interview_result(session_id: str):
    """获取面试评估报告"""
    session = session_store.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="会话不存在")
    return session.get_result()
