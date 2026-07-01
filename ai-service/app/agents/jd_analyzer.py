"""JD 分析 Agent —— AI 链路分析管线的第一个节点

本模块负责解析用户提交的岗位描述（Job Description），提取技术栈、职责、经验级别、
公司规模等结构化信息，供后续的差距分析和出题节点使用。

核心技术点：
1. ReAct Agent 模式：使用 langchain.agents 的 create_agent 创建 Agent。ReAct
   （Reasoning + Acting）是一种让 LLM "思考-行动"循环的框架。虽然此 Agent 没有绑定
   外部工具（tools=[]），但 create_agent 仍提供了统一的 Agent 接口和消息处理
   机制，便于未来扩展（如添加搜索工具查证公司信息）。
2. Prompt 设计：System Prompt 明确要求 LLM 以 JSON 格式返回，并给出了完整的 JSON
   schema 示例。这是"提示工程"的关键——通过在 prompt 中定义输出结构，让 LLM 的
   输出可直接被 json.loads 解析，无需额外的输出解析器。
3. JSON 输出解析：LLM 返回的消息存在 result["messages"][-1].content 中（即最后一条
   AI 消息）。代码尝试 json.loads 解析，失败时返回降级结果（空列表 + error 字段），
   确保即使 LLM 输出格式异常，管线也不会中断。
4. 单例懒加载：_jd_agent 全局变量在首次调用时才创建 Agent 实例，避免模块加载时
   即初始化所有 Agent（减少启动时间和内存占用）。

详见 AI链路学习路径.md 第4步（JD 分析节点）
"""

from langchain.agents import create_agent
from langchain_core.tools import tool
from langchain_core.messages import SystemMessage, HumanMessage
from app.core.llm import get_fast_llm
from app.agents.state import InterviewState
import json


# ---- System Prompt 设计 ----
# 关键设计原则：
# 1. 角色设定："资深的 JD 分析专家" → 引导 LLM 以专业视角分析
# 2. 输出格式约束：给出完整的 JSON schema 示例，LLM 会模仿该格式输出
# 3. company_scale 判断规则：明确列出大厂/中型/创业公司的判断依据，
#    因为公司规模直接影响后续出题的难度分配（见 question_generator.py）
# 4. 末尾强约束："只返回 JSON，不要其他内容" → 避免 LLM 输出多余文本导致解析失败
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
    """
    创建 JD 分析 ReAct Agent。

    使用 get_fast_llm()（低温度 0.3）：分析任务需要稳定输出，低温度让 LLM
    更可靠地返回符合 JSON schema 的结构化结果。
    tools=[]：当前不绑定外部工具，纯靠 LLM 自身能力解析 JD 文本。
    """
    return create_agent(
        model=get_fast_llm(),
        tools=[],
        name="jd_analyzer",
        system_prompt=SYSTEM_PROMPT,
    )


# 单例 Agent 实例（懒加载）：首次调用 _get_jd_agent() 时才创建，
# 后续复用同一实例，避免重复创建 Agent 对象
_jd_agent = None


def _get_jd_agent():
    """获取 JD 分析 Agent 单例（懒加载模式）"""
    global _jd_agent
    if _jd_agent is None:
        _jd_agent = create_jd_analyzer()
    return _jd_agent


def jd_analyzer_node(state: InterviewState) -> InterviewState:
    """
    JD 分析节点函数 —— LangGraph 图节点入口。

    LangGraph 节点函数的约定：接收当前 state，返回更新后的 state。
    本节点的职责：
    1. 从 state["jd_content"] 取出 JD 原文
    2. 将 JD 原文作为 HumanMessage 发送给 ReAct Agent
    3. 从 Agent 返回的最后一条消息中提取 JSON
    4. 将解析结果写入 state["jd_analysis"]，并更新 phase 标记

    JSON 解析容错：若 LLM 输出不符合 JSON 格式（偶尔发生），返回降级结果，
    包含空列表和 error 信息，确保管线不会因解析失败而中断。
    """
    agent = _get_jd_agent()
    # 将 JD 原文作为用户消息发送给 Agent，System Prompt 已在 Agent 创建时注入
    result = agent.invoke({
        "messages": [HumanMessage(content=state["jd_content"])]
    })

    try:
        # result["messages"][-1] 是 Agent 的最后一条回复（AI 消息）
        # .content 是消息的文本内容，期望是合法的 JSON 字符串
        analysis = json.loads(result["messages"][-1].content)
    except (json.JSONDecodeError, KeyError):
        # 降级处理：LLM 输出格式异常时，返回空结果 + 错误信息
        # 后续节点会检测到 tech_stack 为空并做相应处理
        analysis = {"tech_stack": [], "summary": "分析失败", "error": str(result)}

    # 返回更新后的 state：用 **state 展开保留所有原有字段，仅覆盖 jd_analysis 和 phase
    return {"jd_analysis": analysis}
