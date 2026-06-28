"""差距分析 Agent：对比 JD 要求和简历，确定出题策略"""

from langgraph.prebuilt import create_react_agent
from langchain_core.messages import HumanMessage
from app.core.llm import get_fast_llm
from app.agents.state import InterviewState
import json


SYSTEM_PROMPT = """你是一位面试策略专家。对比 JD 岗位要求和候选人的简历，分析差距并制定面试出题策略。

以 JSON 格式返回：
{
  "matching_skills": ["JD和简历都有的技能"],
  "jd_only_skills": ["JD要求但简历没写的技能"],
  "resume_only_skills": ["简历有但JD没要求的技能"],
  "interview_focus": [
    {"area": "考察方向", "reason": "为什么考察", "depth": "深入/一般/了解"}
  ],
  "question_strategy": "总体出题策略说明",
  "difficulty": "easy/medium/hard"
}

只返回 JSON。"""


def create_gap_analyzer():
    return create_react_agent(
        model=get_fast_llm(),
        tools=[],
        name="gap_analyzer",
        prompt=SYSTEM_PROMPT,
    )


_gap_agent = None


def _get_gap_agent():
    global _gap_agent
    if _gap_agent is None:
        _gap_agent = create_gap_analyzer()
    return _gap_agent


def gap_analyzer_node(state: InterviewState) -> InterviewState:
    """差距分析节点"""
    input_text = f"""
JD 分析结果:
{json.dumps(state.get("jd_analysis", {}), ensure_ascii=False, indent=2)}

简历分析结果:
{json.dumps(state.get("resume_analysis", {}), ensure_ascii=False, indent=2)}
"""
    agent = _get_gap_agent()
    result = agent.invoke({
        "messages": [HumanMessage(content=input_text)]
    })

    try:
        analysis = json.loads(result["messages"][-1].content)
    except (json.JSONDecodeError, KeyError):
        analysis = {"matching_skills": [], "interview_focus": [], "difficulty": "medium"}

    return {**state, "gap_analysis": analysis, "phase": "gap_analyzed"}
