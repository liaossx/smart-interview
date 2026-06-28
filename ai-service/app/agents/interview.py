"""面试 Agent：ReAct 模式的面试官 Agent（预留，当前由 InterviewSession 命令式驱动）

Q&A 循环、追问、评分、自适应难度均由 InterviewSession.submit_answer() 处理。
此 Agent 保留供未来对话式面试模式使用。
"""

from langgraph.prebuilt import create_react_agent
from langchain_core.tools import tool
from app.core.llm import get_llm


def create_interview_agent():
    """创建面试 Agent（带评分工具）"""
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

    @tool
    def evaluate_answer(score: int, feedback: str) -> str:
        """对当前回答进行评分。score: 0-10, feedback: 评语"""
        return f"评分完成: {score}/10"

    return create_react_agent(
        model=get_llm(temperature=0.6),
        tools=[evaluate_answer],
        name="interview_agent",
        prompt=system_prompt,
    )


_interview_agent = None


def _get_interview_agent():
    global _interview_agent
    if _interview_agent is None:
        _interview_agent = create_interview_agent()
    return _interview_agent
