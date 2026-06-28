from typing import TypedDict, Annotated, List, Dict, Any
from langgraph.graph.message import add_messages
from langchain_core.messages import BaseMessage


class InterviewState(TypedDict):
    """面试 Agent 的全局状态"""
    messages: Annotated[List[BaseMessage], add_messages]

    # 用户信息
    user_id: int
    session_id: str

    # 输入内容
    jd_content: str
    resume_content: str

    # 分析结果
    jd_analysis: Dict[str, Any]
    resume_analysis: Dict[str, Any]
    gap_analysis: Dict[str, Any]

    # 面试流程
    questions: List[Dict[str, Any]]
    current_question_index: int
    answers: List[Dict[str, Any]]

    # 评估
    evaluation: Dict[str, Any]
    stats_context: str  # 历史统计数据上下文

    # 追问
    pending_follow_up: dict  # {question, original_answer, score_so_far}

    # 自适应难度
    difficulty_stats: Dict[str, List[int]]  # {"easy": [7], "medium": [5, 6], "hard": []}
    supplemental_questions: List[Dict[str, Any]]

    # 控制
    iteration_count: int
    phase: str  # init, interviewing, evaluating, done
