"""简历分析 Agent —— AI 链路分析管线的第二个节点（与 JD 分析并行执行）

本模块负责解析用户提交的简历内容，提取技能、项目经验、教育背景、优劣势等结构化信息。
分析结果供后续的差距分析节点（gap_analyzer）与 JD 分析结果对比使用。

与 jd_analyzer.py 的架构完全一致：
- 使用 create_agent 创建 ReAct Agent（tools=[]，无外部工具）
- 使用 get_fast_llm()（低温度 0.3）确保 JSON 输出稳定
- 单例懒加载模式（_resume_agent）
- JSON 解析容错降级

关键差异：
- Prompt 关注点不同：JD 分析侧重"岗位要求"，简历分析侧重"候选人能力"
- 空简历处理：如果用户未提供简历（resume_content 为空），直接返回空结果而非调用 LLM，
  避免浪费 API 调用。此时差距分析会基于"JD 要求 vs 空简历"进行，全部技能都归为 jd_only。

详见 AI链路学习路径.md 第4步（简历分析节点，与 JD 分析并行）
"""

from langchain.agents import create_agent
from langchain_core.messages import HumanMessage
from app.core.llm import get_fast_llm
from app.agents.state import InterviewState
import json


# ---- System Prompt 设计 ----
# 输出 JSON schema 包含 skills/projects/education/strengths/weaknesses 等字段：
# - projects 中的 highlights 字段：提取项目亮点，供出题节点做"项目深挖"题目
# - strengths/weaknesses：供差距分析节点判断候选人长短板，制定出题策略
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
    """
    创建简历分析 ReAct Agent。

    与 JD 分析一样使用 get_fast_llm()（低温度），因为简历解析需要
    精确提取结构化信息，不需要创意和随机性。
    """
    return create_agent(
        model=get_fast_llm(),
        tools=[],
        name="resume_analyzer",
        system_prompt=SYSTEM_PROMPT,
    )


# 单例 Agent 实例（懒加载），与 jd_analyzer 模式相同
_resume_agent = None


def _get_resume_agent():
    """获取简历分析 Agent 单例（懒加载模式）"""
    global _resume_agent
    if _resume_agent is None:
        _resume_agent = create_resume_analyzer()
    return _resume_agent


def resume_analyzer_node(state: InterviewState) -> InterviewState:
    """
    简历分析节点函数 —— LangGraph 图节点入口。

    与 jd_analyzer_node 结构一致，但多了一个空简历的前置检查：
    如果 state["resume_content"] 为空（用户未上传简历），直接返回空分析结果，
    跳过 LLM 调用。此时差距分析会将所有 JD 要求技能归为"jd_only_skills"。
    """
    # 前置检查：用户可能只提交 JD 而不提交简历，此时无需调用 LLM
    if not state.get("resume_content"):
        return {"resume_analysis": {"skills": [], "projects": []}}

    agent = _get_resume_agent()
    # 将简历原文作为用户消息发送给 Agent
    result = agent.invoke({
        "messages": [HumanMessage(content=state["resume_content"])]
    })

    try:
        # 从 Agent 最后一条消息中提取 JSON 结果
        analysis = json.loads(result["messages"][-1].content)
    except (json.JSONDecodeError, KeyError):
        # 降级处理：解析失败时返回空结果 + 错误信息
        analysis = {"skills": [], "projects": [], "error": str(result)}

    return {"resume_analysis": analysis}
