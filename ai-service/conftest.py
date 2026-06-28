"""pytest 全局配置：环境变量、路径、公共 fixtures"""

import os
import sys

# 确保项目根目录在 PYTHONPATH 中
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# 设置测试用环境变量（在模块导入前生效，避免 get_settings() 读取到空值）
os.environ.setdefault("DEEPSEEK_API_KEY", "test-key-not-real")
os.environ.setdefault("DEEPSEEK_BASE_URL", "http://localhost:9999")
os.environ.setdefault("DEEPSEEK_CHAT_MODEL", "test-model")
os.environ.setdefault("DATABASE_URL", "sqlite:///test.db")
os.environ.setdefault("BACKEND_URL", "http://localhost:8080")
os.environ.setdefault("JWT_SECRET", "test-jwt-secret")
os.environ.setdefault("INTERNAL_API_KEY", "test-internal-key")
os.environ.setdefault("CORS_ORIGINS", "http://localhost:3000")

import pytest
from unittest.mock import Mock


@pytest.fixture
def mock_llm():
    """返回一个 Mock LLM，其 invoke() 返回 AIMessage"""
    from langchain_core.messages import AIMessage

    def _make(content='{"score": 8, "dimensions": {"技术基础": 8, "项目经验": 7, "场景设计": 9, "软技能": 8}, "feedback": "回答良好", "follow_up": "", "confidence": 9}'):
        llm = Mock()
        llm.invoke.return_value = AIMessage(content=content)
        return llm
    return _make


@pytest.fixture
def minimal_state():
    """返回最小可用的 InterviewState 字典"""
    return {
        "messages": [],
        "user_id": 1,
        "session_id": "test-session",
        "jd_content": "测试JD内容",
        "resume_content": "测试简历内容",
        "jd_analysis": {},
        "resume_analysis": {},
        "gap_analysis": {},
        "questions": [],
        "current_question_index": 0,
        "answers": [],
        "evaluation": {},
        "stats_context": "",
        "pending_follow_up": None,
        "difficulty_stats": {"easy": [], "medium": [], "hard": []},
        "supplemental_questions": [],
        "iteration_count": 0,
        "phase": "init",
    }


@pytest.fixture
def sample_question():
    """返回一个测试用题目"""
    return {
        "id": 1,
        "category": "技术基础",
        "question": "请解释 HashMap 的原理",
        "purpose": "考察数据结构基础",
        "difficulty": "medium",
        "expected_answer_points": ["数组+链表", "扩容机制", "哈希冲突"],
        "reference_answer": "",
    }
