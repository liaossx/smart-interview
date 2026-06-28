"""简历分析 Agent：解析简历，提取技能、项目经验、教育背景"""

from langgraph.prebuilt import create_react_agent
from langchain_core.messages import HumanMessage
from app.core.llm import get_fast_llm
from app.agents.state import InterviewState
import json


SYSTEM_PROMPT = """你是一位资深的简历分析专家。分析用户提供的简历内容，提取以下信息并以 JSON 格式返回：

{
  "skills": ["技能1", "技能2", ...],
  "projects": [
    {
      "name": "项目名",
      "tech_stack": ["技术1", ...],
      "description": "简要描述",
      "highlights": ["亮点1", ...]
    }
  ],
  "education": {
    "school": "学校名",
    "major": "专业",
    "degree": "学历"
  },
  "work_experience": "工作经历描述",
  "strengths": ["优势1", "优势2", ...],
  "weaknesses": ["不足1", "不足2", ...]
}

只返回 JSON，不要其他内容。"""


def create_resume_analyzer():
    return create_react_agent(
        model=get_fast_llm(),
        tools=[],
        name="resume_analyzer",
        prompt=SYSTEM_PROMPT,
    )


_resume_agent = None


def _get_resume_agent():
    global _resume_agent
    if _resume_agent is None:
        _resume_agent = create_resume_analyzer()
    return _resume_agent


def resume_analyzer_node(state: InterviewState) -> InterviewState:
    """简历分析节点"""
    if not state.get("resume_content"):
        return {**state, "resume_analysis": {"skills": [], "projects": []},
                "phase": "resume_analyzed"}

    agent = _get_resume_agent()
    result = agent.invoke({
        "messages": [HumanMessage(content=state["resume_content"])]
    })

    try:
        analysis = json.loads(result["messages"][-1].content)
    except (json.JSONDecodeError, KeyError):
        analysis = {"skills": [], "projects": [], "error": str(result)}

    return {**state, "resume_analysis": analysis, "phase": "resume_analyzed"}
