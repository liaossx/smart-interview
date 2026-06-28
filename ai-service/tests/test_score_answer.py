"""评分引擎 _score_answer 测试：重试、JSON 解析、分数钳制、兜底"""

import json
import pytest
from unittest.mock import patch, MagicMock
from langchain_core.messages import AIMessage

from app.services.interview_service import InterviewSession


def make_session(state):
    """创建 InterviewSession 实例用于测试 _score_answer"""
    return InterviewSession("test-session", state, {}, None)


def make_llm_response(content):
    """构造 LLM 返回的 AIMessage"""
    return AIMessage(content=content)


@patch("app.services.interview_service.time.sleep")
@patch("app.services.stats_client.stats_client.build_scoring_context")
@patch("app.core.llm.get_fast_llm")
def test_score_answer_normal(mock_get_llm, mock_build_ctx, mock_sleep, minimal_state, sample_question):
    """正常评分：LLM 返回合法 JSON，验证字段正确提取"""
    mock_llm = MagicMock()
    mock_llm.invoke.return_value = make_llm_response(
        '{"score": 8, "dimensions": {"技术基础": 8, "项目经验": 7, "场景设计": 9, "软技能": 8}, '
        '"feedback": "回答良好", "follow_up": "", "confidence": 9}'
    )
    mock_get_llm.return_value = mock_llm
    mock_build_ctx.return_value = ""

    session = make_session(minimal_state)
    result = session._score_answer(sample_question, "测试回答")

    assert result["score"] == 8
    assert result["dimensions"]["技术基础"] == 8
    assert result["dimensions"]["项目经验"] == 7
    assert result["dimensions"]["场景设计"] == 9
    assert result["dimensions"]["软技能"] == 8
    assert result["confidence"] == 9
    assert result["feedback"] == "回答良好"
    mock_sleep.assert_not_called()


@patch("app.services.interview_service.time.sleep")
@patch("app.services.stats_client.stats_client.build_scoring_context")
@patch("app.core.llm.get_fast_llm")
def test_score_answer_markdown_fences(mock_get_llm, mock_build_ctx, mock_sleep, minimal_state, sample_question):
    """markdown 代码围栏清理：LLM 返回 ```json\n{...}\n```，验证围栏被剥离"""
    mock_llm = MagicMock()
    mock_llm.invoke.return_value = make_llm_response(
        '```json\n{"score": 7, "dimensions": {"技术基础": 7, "项目经验": 7, "场景设计": 7, "软技能": 7}, '
        '"feedback": "还行", "follow_up": "", "confidence": 8}\n```'
    )
    mock_get_llm.return_value = mock_llm
    mock_build_ctx.return_value = ""

    session = make_session(minimal_state)
    result = session._score_answer(sample_question, "测试回答")

    assert result["score"] == 7
    assert result["confidence"] == 8


@patch("app.services.interview_service.time.sleep")
@patch("app.services.stats_client.stats_client.build_scoring_context")
@patch("app.core.llm.get_fast_llm")
def test_score_answer_score_clamp_high(mock_get_llm, mock_build_ctx, mock_sleep, minimal_state, sample_question):
    """score 越界钳制：score=15 被钳制到 10"""
    mock_llm = MagicMock()
    mock_llm.invoke.return_value = make_llm_response(
        '{"score": 15, "dimensions": {"技术基础": 5, "项目经验": 5, "场景设计": 5, "软技能": 5}, '
        '"feedback": "test", "follow_up": "", "confidence": 5}'
    )
    mock_get_llm.return_value = mock_llm
    mock_build_ctx.return_value = ""

    session = make_session(minimal_state)
    result = session._score_answer(sample_question, "测试回答")

    assert result["score"] == 10


@patch("app.services.interview_service.time.sleep")
@patch("app.services.stats_client.stats_client.build_scoring_context")
@patch("app.core.llm.get_fast_llm")
def test_score_answer_score_clamp_low(mock_get_llm, mock_build_ctx, mock_sleep, minimal_state, sample_question):
    """score 越界钳制：score=-3 被钳制到 0"""
    mock_llm = MagicMock()
    mock_llm.invoke.return_value = make_llm_response(
        '{"score": -3, "dimensions": {"技术基础": 5, "项目经验": 5, "场景设计": 5, "软技能": 5}, '
        '"feedback": "test", "follow_up": "", "confidence": 5}'
    )
    mock_get_llm.return_value = mock_llm
    mock_build_ctx.return_value = ""

    session = make_session(minimal_state)
    result = session._score_answer(sample_question, "测试回答")

    assert result["score"] == 0


@patch("app.services.interview_service.time.sleep")
@patch("app.services.stats_client.stats_client.build_scoring_context")
@patch("app.core.llm.get_fast_llm")
def test_score_answer_missing_dimensions(mock_get_llm, mock_build_ctx, mock_sleep, minimal_state, sample_question):
    """dimensions 缺失字段补 0：LLM 只返回 2 个维度，另外 2 个应为 0"""
    mock_llm = MagicMock()
    mock_llm.invoke.return_value = make_llm_response(
        '{"score": 6, "dimensions": {"技术基础": 6, "项目经验": 5}, '
        '"feedback": "test", "follow_up": "", "confidence": 7}'
    )
    mock_get_llm.return_value = mock_llm
    mock_build_ctx.return_value = ""

    session = make_session(minimal_state)
    result = session._score_answer(sample_question, "测试回答")

    assert result["dimensions"]["技术基础"] == 6
    assert result["dimensions"]["项目经验"] == 5
    assert result["dimensions"]["场景设计"] == 0
    assert result["dimensions"]["软技能"] == 0


@patch("app.services.interview_service.time.sleep")
@patch("app.services.stats_client.stats_client.build_scoring_context")
@patch("app.core.llm.get_fast_llm")
def test_score_answer_retry_success(mock_get_llm, mock_build_ctx, mock_sleep, minimal_state, sample_question):
    """JSON 解析失败重试：前两次非法 JSON，第三次合法，验证最终成功"""
    mock_llm = MagicMock()
    mock_llm.invoke.side_effect = [
        make_llm_response("not json at all"),
        make_llm_response("{invalid}"),
        make_llm_response(
            '{"score": 7, "dimensions": {"技术基础": 7, "项目经验": 7, "场景设计": 7, "软技能": 7}, '
            '"feedback": "ok", "follow_up": "", "confidence": 8}'
        ),
    ]
    mock_get_llm.return_value = mock_llm
    mock_build_ctx.return_value = ""

    session = make_session(minimal_state)
    result = session._score_answer(sample_question, "测试回答")

    assert result["score"] == 7
    assert mock_llm.invoke.call_count == 3
    assert mock_sleep.call_count == 2


@patch("app.services.interview_service.time.sleep")
@patch("app.services.stats_client.stats_client.build_scoring_context")
@patch("app.core.llm.get_fast_llm")
def test_score_answer_all_fail_fallback(mock_get_llm, mock_build_ctx, mock_sleep, minimal_state, sample_question):
    """三次全失败兜底：LLM 三次返回非法 JSON，验证返回兜底 score=5, confidence=1"""
    mock_llm = MagicMock()
    mock_llm.invoke.return_value = make_llm_response("not json")
    mock_get_llm.return_value = mock_llm
    mock_build_ctx.return_value = ""

    session = make_session(minimal_state)
    result = session._score_answer(sample_question, "测试回答")

    assert result["score"] == 5
    assert result["confidence"] == 1
    assert result["dimensions"]["技术基础"] == 5
    assert result["dimensions"]["项目经验"] == 5
    assert result["dimensions"]["场景设计"] == 5
    assert result["dimensions"]["软技能"] == 5
    assert mock_llm.invoke.call_count == 3
    assert mock_sleep.call_count == 2


@patch("app.services.interview_service.time.sleep")
@patch("app.services.stats_client.stats_client.build_scoring_context")
@patch("app.core.llm.get_fast_llm")
def test_score_answer_non_retryable_error(mock_get_llm, mock_build_ctx, mock_sleep, minimal_state, sample_question):
    """不可重试错误直接跳出：LLM 抛出 AuthenticationError，验证不重试直接走兜底"""
    mock_llm = MagicMock()
    mock_llm.invoke.side_effect = Exception("Permission denied")
    mock_get_llm.return_value = mock_llm
    mock_build_ctx.return_value = ""

    session = make_session(minimal_state)
    result = session._score_answer(sample_question, "测试回答")

    assert result["score"] == 5
    assert result["confidence"] == 1
    assert mock_llm.invoke.call_count == 1
    mock_sleep.assert_not_called()


@patch("app.services.interview_service.time.sleep")
@patch("app.services.stats_client.stats_client.build_scoring_context")
@patch("app.core.llm.get_fast_llm")
def test_score_answer_stats_context_injected(mock_get_llm, mock_build_ctx, mock_sleep, minimal_state, sample_question):
    """stats_context 注入：验证 build_scoring_context 的返回值出现在 LLM prompt 中"""
    mock_llm = MagicMock()
    mock_llm.invoke.return_value = make_llm_response(
        '{"score": 8, "dimensions": {"技术基础": 8, "项目经验": 8, "场景设计": 8, "软技能": 8}, '
        '"feedback": "good", "follow_up": "", "confidence": 9}'
    )
    mock_get_llm.return_value = mock_llm
    mock_build_ctx.return_value = "【历史参考数据】技术基础类别历史 10 题，平均 6.5 分"

    session = make_session(minimal_state)
    result = session._score_answer(sample_question, "测试回答")

    # 验证 build_scoring_context 被调用，传入了 category
    mock_build_ctx.assert_called_once_with("技术基础")
    # 验证 LLM invoke 被调用，且 prompt 中包含 stats_context
    invoke_args = mock_llm.invoke.call_args
    prompt_content = invoke_args[0][0][0].content  # 第一参数是列表，第一个元素是 HumanMessage
    assert "历史参考数据" in prompt_content
    assert "6.5" in prompt_content
