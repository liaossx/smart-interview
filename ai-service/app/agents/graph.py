"""LangGraph 主图编排：分析管线（JD分析 → 简历分析 → 差距分析 → 出题）

面试 Q&A 循环和评估不在此图中执行：
- Q&A 由 InterviewSession.submit_answer() 命令式驱动（支持追问、自适应难度）
- 评估由 InterviewSession._run_evaluation() 直接调用 evaluator_node()
"""

from langgraph.graph import StateGraph, START, END
from app.agents.state import InterviewState
from app.agents.jd_analyzer import jd_analyzer_node
from app.agents.resume_analyzer import resume_analyzer_node
from app.agents.gap_analyzer import gap_analyzer_node
from app.agents.question_generator import question_generator_node


def build_interview_graph():
    """构建分析管线工作流图"""
    builder = StateGraph(InterviewState)

    # 分析节点
    builder.add_node("jd_analyzer", jd_analyzer_node)
    builder.add_node("resume_analyzer", resume_analyzer_node)
    builder.add_node("gap_analyzer", gap_analyzer_node)
    builder.add_node("question_generator", question_generator_node)

    # JD 分析和简历分析并行执行，完成后汇入差距分析
    builder.add_edge(START, "jd_analyzer")
    builder.add_edge(START, "resume_analyzer")
    builder.add_edge("jd_analyzer", "gap_analyzer")
    builder.add_edge("resume_analyzer", "gap_analyzer")
    builder.add_edge("gap_analyzer", "question_generator")
    builder.add_edge("question_generator", END)

    return builder.compile()


# 全局实例
interview_graph = build_interview_graph()
