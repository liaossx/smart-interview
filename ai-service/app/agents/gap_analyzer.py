"""差距分析 Agent —— AI 链路分析管线的第三个节点（汇聚节点）

本模块是分析管线的"枢纽"节点：它等待 JD 分析和简历分析都完成后，将两者的结构化
结果进行对比，找出技能匹配/缺失情况，并制定面试出题策略。

核心职责：
1. 技能对比：将 JD 要求的技能与简历中的技能做交集/差集分析
   - matching_skills：两者都有的技能 → 候选人已具备，可深入考察
   - jd_only_skills：JD 要求但简历没有 → 候选人可能欠缺，需重点考察
   - resume_only_skills：简历有但 JD 没要求 → 了解即可，不作重点
2. 出题方向制定（interview_focus）：根据差距分析结果，为每个考察方向标注
   "深入/一般/了解"深度级别，直接指导出题节点的题目分配
3. 难度建议（difficulty）：综合 JD 级别和候选人水平，给出 easy/medium/hard 建议

输入拼接策略：
gap_analyzer 不直接处理原始 JD/简历文本，而是接收前两个节点的结构化分析结果
（jd_analysis 和 resume_analysis），将它们序列化为 JSON 文本拼接后发给 LLM。
这种"结构化输入"方式让 LLM 聚焦于对比分析，而非重新解析原文。

详见 AI链路学习路径.md 第5步（差距分析节点）
"""

from langchain.agents import create_agent
from langchain_core.messages import HumanMessage
from app.core.llm import get_fast_llm
from app.agents.state import InterviewState
import json


# ---- System Prompt 设计 ----
# 输出 JSON schema 的关键字段：
# - interview_focus：出题方向的列表，每项含 area(方向)/reason(原因)/depth(深度)
#   这是连接"分析"与"出题"的核心数据：出题节点根据此列表分配题目
# - difficulty：整体难度建议，影响出题节点中 easy/medium/hard 的比例分配
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
    """
    创建差距分析 ReAct Agent。

    使用 get_fast_llm()（低温度 0.3）：差距分析需要客观、稳定地对比技能，
    不需要创意输出。低温度确保分析结果一致性。
    """
    return create_agent(
        model=get_fast_llm(),
        tools=[],
        name="gap_analyzer",
        system_prompt=SYSTEM_PROMPT,
    )


# 单例 Agent 实例（懒加载）
_gap_agent = None


def _get_gap_agent():
    """获取差距分析 Agent 单例（懒加载模式）"""
    global _gap_agent
    if _gap_agent is None:
        _gap_agent = create_gap_analyzer()
    return _gap_agent


def gap_analyzer_node(state: InterviewState) -> InterviewState:
    """
    差距分析节点函数 —— LangGraph 图节点入口。

    此节点是图中的 fan-in 汇聚点：LangGraph 确保 jd_analyzer 和 resume_analyzer
    都完成后才执行此节点。此时 state 中已包含 jd_analysis 和 resume_analysis。

    处理流程：
    1. 从 state 取出 JD 分析和简历分析的结构化结果
    2. 将两个 JSON 结果序列化为文本，拼接成对比输入
    3. 发送给差距分析 Agent，获取技能对比和出题策略
    4. 解析 JSON 结果写入 state["gap_analysis"]
    """
    # 将前序节点的结构化分析结果拼接为 LLM 输入文本
    # 使用 json.dumps + ensure_ascii=False 保留中文可读性，indent=2 方便 LLM 理解结构
    input_text = f"""
JD 分析结果:
{json.dumps(state.get("jd_analysis", {}), ensure_ascii=False, indent=2)}

简历分析结果:
{json.dumps(state.get("resume_analysis", {}), ensure_ascii=False, indent=2)}
"""
    agent = _get_gap_agent()
    # 将拼接的对比文本发送给 Agent，System Prompt 已指导它做技能对比和策略制定
    result = agent.invoke({
        "messages": [HumanMessage(content=input_text)]
    })

    try:
        # 从 Agent 最后一条消息中提取 JSON 结果
        # 结果包含 matching_skills/jd_only_skills/interview_focus/difficulty 等
        analysis = json.loads(result["messages"][-1].content)
    except (json.JSONDecodeError, KeyError):
        # 降级处理：解析失败时返回默认中等难度，避免后续出题节点完全无策略可用
        analysis = {"matching_skills": [], "interview_focus": [], "difficulty": "medium"}

    return {**state, "gap_analysis": analysis, "phase": "gap_analyzed"}
