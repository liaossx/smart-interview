from pydantic import BaseModel, Field
from typing import Optional, List


class ChatRequest(BaseModel):
    session_id: str
    user_id: int
    message: str
    jd_id: Optional[int] = None
    resume_id: Optional[int] = None


class ChatResponse(BaseModel):
    session_id: str
    message: str
    thinking_chain: Optional[List[dict]] = None


class JDCreateRequest(BaseModel):
    content: str


class JDResponse(BaseModel):
    id: int
    user_id: int
    content: str
    analyzed_result: Optional[str] = None
    created_at: str


class SessionCreateRequest(BaseModel):
    jd_id: int
    resume_id: Optional[int] = None


class SessionResponse(BaseModel):
    id: int
    user_id: int
    jd_id: Optional[int] = None
    resume_id: Optional[int] = None
    status: str
    total_score: Optional[int] = None
    created_at: str
