"""Agent 懒加载单例测试：验证 6 个 Agent 的缓存行为"""

import pytest
from unittest.mock import patch, MagicMock


def test_jd_agent_singleton():
    """JD Agent 首次创建后复用"""
    import app.agents.jd_analyzer as mod
    mod._jd_agent = None

    with patch("app.agents.jd_analyzer.create_jd_analyzer") as mock_create:
        mock_create.return_value = MagicMock(name="jd_agent_instance")
        agent1 = mod._get_jd_agent()
        agent2 = mod._get_jd_agent()

    assert agent1 is agent2
    assert mock_create.call_count == 1
    mod._jd_agent = None


def test_resume_agent_singleton():
    """Resume Agent 首次创建后复用"""
    import app.agents.resume_analyzer as mod
    mod._resume_agent = None

    with patch("app.agents.resume_analyzer.create_resume_analyzer") as mock_create:
        mock_create.return_value = MagicMock(name="resume_agent_instance")
        agent1 = mod._get_resume_agent()
        agent2 = mod._get_resume_agent()

    assert agent1 is agent2
    assert mock_create.call_count == 1
    mod._resume_agent = None


def test_all_agents_independent_cache():
    """6 个 Agent 各有独立缓存，互不影响"""
    modules_and_factories = [
        ("app.agents.jd_analyzer", "_jd_agent", "_get_jd_agent", "create_jd_analyzer"),
        ("app.agents.resume_analyzer", "_resume_agent", "_get_resume_agent", "create_resume_analyzer"),
        ("app.agents.gap_analyzer", "_gap_agent", "_get_gap_agent", "create_gap_analyzer"),
        ("app.agents.question_generator", "_question_agent", "_get_question_generator", "create_question_generator"),
        ("app.agents.evaluator", "_evaluator_agent", "_get_evaluator", "create_evaluator"),
        ("app.agents.interview", "_interview_agent", "_get_interview_agent", "create_interview_agent"),
    ]

    created_agents = []
    for mod_path, attr_name, getter_name, factory_name in modules_and_factories:
        mod = __import__(mod_path, fromlist=[getter_name, factory_name, attr_name])
        setattr(mod, attr_name, None)

        with patch(f"{mod_path}.{factory_name}") as mock_create:
            mock_create.return_value = MagicMock(name=f"{mod_path}_instance")
            getter = getattr(mod, getter_name)
            agent = getter()
            created_agents.append(agent)
            assert mock_create.call_count == 1

    # 验证 6 个 agent 实例互不相同
    for i in range(len(created_agents)):
        for j in range(i + 1, len(created_agents)):
            assert created_agents[i] is not created_agents[j], f"Agent {i} and {j} should be different instances"

    # 清理
    for mod_path, attr_name, _, _ in modules_and_factories:
        mod = __import__(mod_path, fromlist=[attr_name])
        setattr(mod, attr_name, None)


def test_interview_agent_creates_once():
    """Interview Agent 首次创建后复用，tool 绑定在创建时完成"""
    import app.agents.interview as mod
    mod._interview_agent = None

    with patch("app.agents.interview.create_interview_agent") as mock_create:
        mock_agent = MagicMock(name="interview_agent_instance")
        mock_create.return_value = mock_agent
        agent1 = mod._get_interview_agent()
        agent2 = mod._get_interview_agent()

    assert agent1 is agent2
    assert mock_create.call_count == 1
    mod._interview_agent = None
