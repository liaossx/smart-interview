"""JD 分析 Agent：解析岗位描述，提取技术栈、职责、级别等信息"""

from langgraph.prebuilt import create_react_agent
from langchain_core.tools import tool
from langchain_core.messages import SystemMessage, HumanMessage
from app.core.llm import get_fast_llm
from app.agents.state import InterviewState
import json


SYSTEM_PROMPT = """你是一位资深的 JD 分析专家。分析用户提供的岗位描述(JD)，提取以下信息并以 JSON 格式返回：

{
  "tech_stack": ["技术1", "技术2", ...],
  "responsibilities": ["职责1", "职责2", ...],
  "required_skills": ["技能1", "技能2", ...],
  "experience_level": "校招/实习/社招",
  "key_requirements": ["要求1", "要求2", ...],
  "role_type": "后端开发/AI Agent/算法/...",
  "company_scale": "大厂/中型公司/创业公司/未知",
  "company_scale_reason": "判断依据（公司名、业务描述、薪资范围、团队规模等）",
  "summary": "简要总结"
}

company_scale 判断依据：
- 大厂：知名互联网公司（阿里、腾讯、字节、美团等）、规模描述"万人"级别、有完善技术体系要求
- 中型公司：B轮以上、几百到千人规模、描述较规范
- 创业公司：描述模糊、要求"全栈"、强调"快速迭代"、"创业精神"、薪资范围含期权

只返回 JSON，不要其他内容。"""


def create_jd_analyzer():
    return create_react_agent(
        model=get_fast_llm(),
        tools=[],
        name="jd_analyzer",
        prompt=SYSTEM_PROMPT,
    )


_jd_agent = None


def _get_jd_agent():
    global _jd_agent
    if _jd_agent is None:
        _jd_agent = create_jd_analyzer()
    return _jd_agent


def jd_analyzer_node(state: InterviewState) -> InterviewState:
    """JD 分析节点"""
    agent = _get_jd_agent()
    result = agent.invoke({
        "messages": [HumanMessage(content=state["jd_content"])]
    })

    try:
        analysis = json.loads(result["messages"][-1].content)
    except (json.JSONDecodeError, KeyError):
        analysis = {"tech_stack": [], "summary": "分析失败", "error": str(result)}

    return {**state, "jd_analysis": analysis, "phase": "jd_analyzed"}
