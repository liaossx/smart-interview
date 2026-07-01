"""LangGraph 主图编排 —— AI 链路的分析管线工作流

本文件构建了面试前置分析管线的工作流图，拓扑结构如下：

    START ──┬──> jd_analyzer ───┐
            │                    ├──> gap_analyzer ──> question_generator ──> END
            └──> resume_analyzer┘

图执行流程（详细说明）：
1. 并行分析阶段：JD 分析和简历分析从 START 同时启动，并行执行。
   两个节点互不依赖（JD 分析只需 jd_content，简历分析只需 resume_content），
   并行可以将总耗时从串行的 2 倍降为约 1 倍。LangGraph 的 add_messages reducer
   确保 messages 字段在并行写入时不会丢失数据。
2. 汇聚阶段：gap_analyzer 等待 JD 分析和简历分析都完成后才执行——它需要两者的
   结果作为输入来对比差距。LangGraph 自动处理这个 fan-in 等待。
3. 出题阶段：question_generator 接收差距分析结果，生成面试题目列表。

为什么 Q&A 循环和评估不放在此图中？
- Q&A 循环需要用户交互（候选人逐题回答），是"人在环中"（Human-in-the-loop）的流程，
  不适合用 LangGraph 的自动执行图来驱动。实际由 InterviewSession.submit_answer()
  命令式控制：提交答案 → 评分 → 判断是否追问 → 推进到下一题。
- 评估在所有题目答完后由 InterviewSession._run_evaluation() 直接调用 evaluator_node()，
  无需经过图的编排。
- 这种"图管分析、命令管交互"的混合架构，兼顾了分析管线的自动化和面试交互的灵活性。

详见 AI链路学习路径.md 第3步（工作流编排）
"""

from langgraph.graph import StateGraph, START, END
from app.agents.state import InterviewState
from app.agents.jd_analyzer import jd_analyzer_node
from app.agents.resume_analyzer import resume_analyzer_node
from app.agents.gap_analyzer import gap_analyzer_node
from app.agents.question_generator import question_generator_node


def build_interview_graph():
    """
    构建分析管线工作流图。

    使用 LangGraph 的 StateGraph API：
    - StateGraph(InterviewState)：以 InterviewState 为状态容器
    - add_node：注册节点函数（每个节点接收 state、返回更新后的 state）
    - add_edge：定义节点间的执行顺序（边 = 数据依赖）
    - compile()：编译为可执行图实例，调用 .invoke(state) 触发执行

    返回编译后的图实例，外部通过 interview_graph.invoke(initial_state) 调用。
    """
    builder = StateGraph(InterviewState)

    # 注册四个分析节点，每个节点对应一个 ReAct Agent
    builder.add_node("jd_analyzer", jd_analyzer_node)           # JD 分析：解析岗位描述
    builder.add_node("resume_analyzer", resume_analyzer_node)   # 简历分析：解析候选人简历
    builder.add_node("gap_analyzer", gap_analyzer_node)         # 差距分析：对比 JD 与简历
    builder.add_node("question_generator", question_generator_node)  # 出题：生成面试题目

    # ---- 定义图的拓扑（边的连接关系）----
    # START 同时连接两个分析节点 → 并行执行（fan-out）
    builder.add_edge(START, "jd_analyzer")
    builder.add_edge(START, "resume_analyzer")
    # 两个分析节点都指向 gap_analyzer → gap_analyzer 等待两者都完成后才执行（fan-in）
    builder.add_edge("jd_analyzer", "gap_analyzer")
    builder.add_edge("resume_analyzer", "gap_analyzer")
    # 差距分析 → 出题（串行依赖：出题需要差距分析结果）
    builder.add_edge("gap_analyzer", "question_generator")
    # 出题完成 → 结束
    builder.add_edge("question_generator", END)

    # 编译图：LangGraph 会验证拓扑合法性（如无悬空节点），并生成可执行实例
    return builder.compile()


# 全局单例：模块加载时即编译图，避免每次面试都重新构建
interview_graph = build_interview_graph()
