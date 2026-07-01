"""
面试 API 路由：AI 服务对外暴露的 HTTP 接口层。

本文件定义了面试全流程的 REST 端点，分两类：
1. 同步端点（/interview/start, /interview/answer, /interview/restore 等）：
   阻塞等待 AI 链路完成后一次性返回 JSON。
2. SSE 流式端点（/interview/start/stream, /interview/answer/stream）：
   返回 text/event-stream，通过 Server-Sent Events 实时推送分析/评分进度，
   前端可展示"正在分析职位描述..."等实时状态。

SSE 格式：每条消息为 "event: <type>\ndata: <json>\n\n"，
由 _sse() 辅助函数统一格式化。

详见 AI链路学习路径.md 第七步。
"""

import json
from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import Optional, List
from app.services.interview_service import session_store

router = APIRouter()


# —— 内联 Pydantic 请求模型 ——
# 这里把请求模型定义在路由文件内而非单独 schemas 文件，
# 因为这些模型仅被本文件的端点使用，内联可减少文件跳转，便于阅读。


class StartInterviewRequest(BaseModel):
    """开始面试请求：JD + 简历"""
    jd_content: str
    resume_content: str = ""
    user_id: int = 1


class SubmitAnswerRequest(BaseModel):
    """提交答案请求：会话 ID + 候选人回答"""
    session_id: str
    answer: str


class RestoreQaItem(BaseModel):
    """恢复面试时的单条 Q&A 记录"""
    question: str = ""
    category: str = ""
    answer: str = ""
    score: int = 0
    feedback: str = ""


class RestoreSessionRequest(BaseModel):
    """
    恢复面试请求：从后端 MySQL 已存的 Q&A 历史重建 AI 会话状态。

    支持两种恢复方式：
    - 传 qas（Q&A 记录列表）：从中重建题目骨架
    - 传 questions（完整题目列表）：直接使用，保留完整元数据
    """
    jd_content: str
    resume_content: str = ""
    qas: List[RestoreQaItem] = []
    questions: List[dict] = []
    current_question_index: int = 0
    user_id: int = 1
    existing_session_id: Optional[str] = None


def _sse(event: dict) -> str:
    """
    将事件 dict 格式化为 SSE 字符串。

    SSE 协议格式：
        event: <事件类型>\n
        data: <JSON 字符串>\n
        \n
    - event 行：标识事件类型（progress / scored / complete / error）
    - data 行：JSON 序列化后的负载
    - 末尾两个 \n\n：消息分隔符，标志一条 SSE 消息结束

    处理两种事件结构：
    - 带 "data" 键的事件：data 字段作为负载
    - 不带 "data" 键的 progress 事件：把除 event 外的字段整体作为负载
    """
    event_type = event.get("event", "message")
    payload = event.get("data", event)
    if "data" in event:
        payload = event["data"]
    else:
        # progress 事件只有 step + message，整体作为 data
        payload = {k: v for k, v in event.items() if k != "event"}
    # ensure_ascii=False 保留中文，避免前端收到 \uXXXX 转义
    return f"event: {event_type}\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"


@router.post("/interview/start")
async def start_interview(request: StartInterviewRequest):
    """
    开始面试（同步）：分析 JD + 简历 -> 生成题目 -> 返回第一题。

    同步端点：阻塞等待整个 LangGraph 分析链路完成后一次性返回 JSON。
    适合分析速度快或前端无需进度展示的场景。
    """
    session = session_store.create(
        jd_content=request.jd_content,
        resume_content=request.resume_content,
        user_id=request.user_id,
    )
    try:
        # 调用 LangGraph interview_graph.invoke() 同步执行分析链路：
        # JD分析 -> 简历分析 -> 差距分析 -> 出题，阻塞等待全部完成后返回
        result = session.analyze()
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"分析失败: {str(e)}")


@router.post("/interview/start/stream")
async def start_interview_stream(request: StartInterviewRequest):
    """
    开始面试（SSE 流式）：实时推送分析进度。

    与同步端点的区别：
    - 同步：HTTP 请求阻塞，AI 完成后返回单个 JSON 响应。
    - 流式：立即返回 StreamingResponse（media_type=text/event-stream），
      生成器逐步 yield SSE 字符串，前端通过 EventSource 实时接收
      "正在分析职位描述..."等进度事件，最后收到 complete 事件。

    StreamingResponse 是 FastAPI 对 SSE 的支持：把一个生成器函数的输出
    逐块写入 HTTP 响应体，保持连接不断开直到生成器结束。
    """
    session = session_store.create(
        jd_content=request.jd_content,
        resume_content=request.resume_content,
        user_id=request.user_id,
    )

    def generate():
        """SSE 生成器：把 analyze_stream() 的事件逐条格式化为 SSE 字符串"""
        try:
            # analyze_stream() 内部调用 interview_graph.stream() 逐节点 yield 事件
            # 每完成一个图节点就推送一个 progress 事件（如"职位描述分析完成"）
            for event in session.analyze_stream():
                yield _sse(event)
        except Exception as e:
            # 异常时推送 error 事件，前端可展示错误信息
            yield _sse({"event": "error", "data": {"message": f"分析失败: {str(e)}"}})

    # StreamingResponse 把生成器的 yield 逐块写入 HTTP 响应体，保持连接不断开
    # media_type=text/event-stream 告知浏览器/前端这是 SSE 流，前端用 EventSource 接收
    return StreamingResponse(generate(), media_type="text/event-stream")


@router.post("/interview/restore")
async def restore_interview(request: RestoreSessionRequest):
    """
    恢复面试：从后端 MySQL 数据重建 AI 会话状态，继续作答。

    场景：用户刷新页面/断线重连时，前端把后端存的 Q&A 历史记录传过来，
    AI 服务据此重建 LangGraph state，跳过分析阶段直接进入题目就绪。
    """
    # 从后端 MySQL 数据重建 AI 会话状态：把已有的 Q&A 历史注入 LangGraph state
    # model_dump() 把 Pydantic 模型转为 dict，供 InterviewSessionStore.restore() 使用
    session = session_store.restore(
        jd_content=request.jd_content,
        resume_content=request.resume_content,
        qas=[qa.model_dump() for qa in request.qas],  # Pydantic model -> dict
        questions=request.questions,
        current_question_index=request.current_question_index,
        user_id=request.user_id,
        existing_session_id=request.existing_session_id,
    )
    try:
        # 恢复后跳过分析阶段，直接进入题目就绪状态，返回当前应作答的题目
        result = session.resume_analyze()
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"恢复失败: {str(e)}")


@router.post("/interview/answer")
async def submit_answer(request: SubmitAnswerRequest):
    """
    提交答案（同步）：评分 -> 返回下一题/追问/评估结果。

    同步端点：阻塞等待 LLM 评分完成后一次性返回 JSON。
    返回 phase 可能是 continue（下一题）、follow_up（追问）、done（完成）。
    """
    session = session_store.get(request.session_id)
    if not session:
        raise HTTPException(status_code=404, detail="会话不存在")
    try:
        # 调用评分引擎 _score_answer()：构建 prompt -> 调用 LLM -> 解析 JSON -> 校验分数
        # 根据 score 决定后续：score<7 且有 follow_up -> 返回追问；否则推进到下一题或触发评估
        result = session.submit_answer(request.answer)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"评分失败: {str(e)}")


@router.post("/interview/answer/stream")
async def submit_answer_stream(request: SubmitAnswerRequest):
    """
    提交答案（SSE 流式）：实时推送评分进度。

    与同步端点的区别：先推送 scoring progress 事件告知前端"正在评分"，
    评分完成后推送 scored（继续答题）或 complete（面试完成）事件。
    评分本身仍走同步 submit_answer()，SSE 层只包装了进度推送。
    """
    session = session_store.get(request.session_id)
    if not session:
        raise HTTPException(status_code=404, detail="会话不存在")

    def generate():
        """SSE 生成器：把 submit_answer_stream() 的事件逐条格式化"""
        try:
            # submit_answer_stream() 先推送 scoring progress 事件，再调用同步 submit_answer()
            # 评分完成后推送 scored（继续答题）或 complete（面试完成）事件
            for event in session.submit_answer_stream(request.answer):
                yield _sse(event)
        except Exception as e:
            yield _sse({"event": "error", "data": {"message": f"评分失败: {str(e)}"}})

    # 返回 SSE 流，前端通过 EventSource 实时接收评分进度
    return StreamingResponse(generate(), media_type="text/event-stream")


@router.get("/interview/current/{session_id}")
async def get_current_question(session_id: str):
    """
    获取当前题目状态（不提交答案）。

    用于页面刷新恢复：前端刷新后调此接口获取当前应该展示的题目，
    如果存在 pending_follow_up 则展示追问，否则展示当前题目。
    """
    session = session_store.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="会话不存在")
    # 返回当前题目状态：有追问则返回 follow_up，已答完则返回 done，否则返回当前题
    return session.get_current_question()


@router.get("/interview/result/{session_id}")
async def get_interview_result(session_id: str):
    """
    获取面试评估报告。

    面试完成后（phase=done）调用，返回综合评估结果：
    总分、各维度分、优势、劣势、改进建议、学习推荐、评分质量指标。
    """
    session = session_store.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="会话不存在")
    # 返回综合评估报告：总分、各维度分、优劣势、改进建议、学习推荐、评分质量指标
    return session.get_result()
