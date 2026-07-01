"""面试 Agent —— 预留的对话式面试 Agent（当前未启用）

本模块定义了一个完整的 ReAct 面试 Agent，设计用于"对话式面试"场景：
LLM 作为面试官，自主控制提问节奏、追问、评分，全程以对话方式推进面试。

当前架构中，面试 Q&A 循环由 InterviewSession 命令式驱动（submit_answer 方法），
而非由本 Agent 自主驱动。这种设计的原因：
- 命令式驱动（当前方案）：前端控制流程，每道题的提交、评分、追问逻辑由代码确定性控制，
  适合"结构化面试"场景（固定题目、可控评分、可追溯）
- Agent 驱动（本模块，未来方案）：LLM 自主控制流程，适合"自由对话式面试"场景
  （LLM 根据回答动态调整问题、自然追问、模拟真实面试官行为）

本 Agent 的设计特点：
1. 绑定了 evaluate_answer 工具：这是 ReAct 模式的核心——LLM 可以"调用"此工具
   来记录评分。在真正的 Agent 驱动模式下，LLM 会在每题回答后自主决定调用此工具。
2. 温度 0.6：介于分析(0.3)和创意(0.8)之间——面试官既需要稳定的专业判断，
   又需要一定的灵活性和自然对话感。
3. System Prompt 定义了面试官的行为规范和评分标准（0-10分四档）。

详见 AI链路学习路径.md 第8步（面试 Agent，预留扩展）
"""

from langchain.agents import create_agent
from langchain_core.tools import tool
from app.core.llm import get_llm


def create_interview_agent():
    """
    创建面试 Agent（带评分工具）。

    这是整个链路中唯一绑定了工具（tool）的 Agent。
    evaluate_answer 工具让 LLM 可以通过 ReAct 模式自主调用评分功能，
    而非由外部代码强制评分。当前未启用，保留供未来对话式面试模式使用。

    温度选择 0.6：
    - 低于出题(0.8)：面试官需要稳定的专业判断，不应过于发散
    - 高于分析(0.3)：对话需要一定自然感和灵活性，不能太机械
    """
    system_prompt = """你是一位专业的面试官。你的职责是：
1. 逐题提问，一次只问一道题
2. 根据候选人的回答进行追问
3. 每道题回答完毕后，给出评分和反馈
4. 所有题目完成后，总结面试

评分标准：
- 0-3分: 完全不了解
- 4-6分: 基础了解，但不够深入
- 7-8分: 掌握良好，能清晰阐述
- 9-10分: 深入理解，有独到见解

使用 evaluate_answer 工具对每道题评分。"""

    # evaluate_answer 工具：ReAct Agent 的"行动"能力
    # 在 Agent 驱动模式下，LLM 会在每题回答后自主调用此工具记录评分。
    # 当前命令式驱动模式下，评分由外部代码直接处理，不经过此工具。
    @tool
    def evaluate_answer(score: int, feedback: str) -> str:
        """对当前回答进行评分。score: 0-10, feedback: 评语"""
        return f"评分完成: {score}/10"

    return create_agent(
        model=get_llm(temperature=0.6),   # 中等温度：兼顾稳定性和对话自然感
        tools=[evaluate_answer],            # 绑定评分工具：ReAct 模式的核心能力
        name="interview_agent",
        system_prompt=system_prompt,
    )


# 单例 Agent 实例（懒加载）
_interview_agent = None


def _get_interview_agent():
    """获取面试 Agent 单例（懒加载模式）—— 当前未被调用，保留供未来使用"""
    global _interview_agent
    if _interview_agent is None:
        _interview_agent = create_interview_agent()
    return _interview_agent
