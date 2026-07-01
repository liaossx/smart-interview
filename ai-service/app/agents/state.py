"""LangGraph 全局状态定义 —— AI 链路各节点共享的数据容器

本文件定义了 InterviewState，它是整个 AI 面试链路中所有节点（Agent）之间传递和共享
数据的"中央总线"。LangGraph 的工作流图在执行时，每个节点接收 state、处理后返回更新后的
state，从而实现节点间的数据流转。

核心技术点：
1. TypedDict：Python 的类型工具，允许定义一个字典的键和值类型。LangGraph 用它来声明
   图的状态结构，既保证类型提示友好，又不需要定义完整的数据类（dataclass）。
2. Annotated + add_messages：messages 字段使用 Annotated[List[BaseMessage], add_messages]
   声明。add_messages 是 LangGraph 的 reducer 函数——当多个节点并行写入 messages 时，
   它不是简单覆盖（replace），而是将新消息追加（append）到列表中。这对于并行执行的两个
   分析节点（JD 分析 + 简历分析）同时写入 state 尤为重要，防止数据丢失。
3. 其他字段无 reducer：默认行为是"后写覆盖前写"（replace），因此这些字段由各自负责的
   节点写入，不会产生并行冲突。

详见 AI链路学习路径.md 第2步（状态定义）
"""

from typing import TypedDict, Annotated, List, Dict, Any
from langgraph.graph.message import add_messages
from langchain_core.messages import BaseMessage


class InterviewState(TypedDict):
    """
    面试 Agent 的全局状态。

    该状态贯穿整个面试生命周期：初始化 → 分析（JD/简历/差距）→ 出题 → 面试Q&A → 评估。
    每个图节点只修改自己负责的字段，通过 **state 扩展返回更新。
    """
    # ---- 消息历史 ----
    # messages 使用 add_messages reducer：多节点并行写入时自动追加而非覆盖。
    # 用于 ReAct Agent 内部的消息传递，以及未来对话式面试模式的消息记录。
    messages: Annotated[List[BaseMessage], add_messages]

    # ---- 用户与会话标识 ----
    user_id: int            # 用户 ID，用于关联用户和查询历史统计
    session_id: str         # 面试会话 ID，贯穿单次面试的全生命周期

    # ---- 原始输入 ----
    jd_content: str         # 用户输入的岗位描述（JD）原文，由前端提交
    resume_content: str     # 用户输入的简历原文，由前端提交（可能为空）

    # ---- 分析结果（由分析管线各节点填充）----
    jd_analysis: Dict[str, Any]        # JD 分析结果：技术栈、职责、级别、公司规模等
    resume_analysis: Dict[str, Any]    # 简历分析结果：技能、项目、教育、优劣势
    gap_analysis: Dict[str, Any]       # 差距分析结果：匹配/缺失技能、出题方向、难度建议

    # ---- 面试题目与答题流程 ----
    questions: List[Dict[str, Any]]     # 生成的面试题目列表，每题含 category/difficulty/参考答案等
    current_question_index: int         # 当前提问进度索引，由 InterviewSession 命令式推进
    answers: List[Dict[str, Any]]       # 候选人逐题回答及评分记录

    # ---- 评估 ----
    evaluation: Dict[str, Any]   # 最终评估报告：总分、各维度评分、改进建议等
    stats_context: str           # 历史面试统计数据上下文（注入给评估 Agent 做横向对比参考）

    # ---- 追问机制 ----
    # 当候选人回答不够深入时触发追问。存储当前追问上下文：
    # {question: 追问题目, original_answer: 原始回答, score_so_far: 当前累计得分}
    pending_follow_up: dict

    # ---- 自适应难度 ----
    # 按难度级别记录已答题的得分列表，用于动态调整后续题目难度：
    # 如 {"easy": [7], "medium": [5, 6], "hard": []} 表示 easy 答了1题得7分，medium答了2题
    difficulty_stats: Dict[str, List[int]]
    supplemental_questions: List[Dict[str, Any]]  # 自适应生成的补充题目

    # ---- 流程控制 ----
    iteration_count: int   # 迭代计数器，防止面试无限循环
    phase: str             # 当前阶段标识：init → jd_analyzed → resume_analyzed →
                           # gap_analyzed → questions_ready → interviewing → evaluating → done
