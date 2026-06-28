"""出题 Agent：根据差距分析生成面试题目"""

from langgraph.prebuilt import create_react_agent
from langchain_core.messages import HumanMessage
from app.core.llm import get_creative_llm
from app.agents.state import InterviewState
import json


SYSTEM_PROMPT = """你是一位面试出题专家。根据 JD 要求、候选人简历和差距分析，生成 8-12 道面试题。

公司规模决定了出题风格，必须严格遵守以下规则：

【大厂出题风格】
- 重底层原理：HashMap 原理、JVM 内存模型、线程池参数、MySQL 索引结构
- 重系统设计：让你设计一个 XX 系统，考察架构能力
- 重算法思维：时间/空间复杂度分析、缓存策略、并发设计
- 题目深度：hard 占 40%，medium 占 50%，easy 占 10%
- 场景题举例："亿级流量下如何设计一个缓存策略"

【中型公司出题风格】
- 重框架实战：Spring Boot 自动配置原理、MyBatis 缓存、Redis 实际使用
- 重业务理解：结合业务场景的技术方案设计
- 重问题排查：线上问题排查思路、性能调优
- 题目深度：hard 占 20%，medium 占 60%，easy 占 20%
- 场景题举例："你们项目中的缓存是怎么用的？遇到了什么问题？"

【创业公司出题风格】
- 重全栈能力：CRUD 之外的思考、技术选型能力
- 重解决问题：遇到困难怎么解决、快速学习能力
- 重实战经验：能不能直接上手干活
- 题目深度：hard 占 10%，medium 占 50%，easy 占 40%
- 场景题举例："如果让你从零搭建一个项目后端，你会怎么选型？"

以 JSON 格式返回题目列表：
{
  "questions": [
    {
      "id": 1,
      "category": "技术基础/项目经验/场景设计/软技能",
      "question": "题目内容",
      "purpose": "考察什么能力",
      "difficulty": "easy/medium/hard",
      "expected_answer_points": ["要点1", "要点2"],
      "reference_answer": "仅当 category 为「技术基础」时填写，是一段 200-500 字的完整参考答案，直接可以当作面试标准答案来学习。其他 category 填空字符串即可。"
    }
  ]
}

reference_answer 撰写要求：
- 仅技术基础（八股文）题需要写完整答案，作为面试标准答案供候选人学习
- 用清晰的分点或段落阐述核心概念、原理、关键步骤
- 覆盖 expected_answer_points 中的所有要点并展开
- 200-500 字，语言专业但不晦涩

题目分配建议：
- 40% 技术基础题（根据 JD 技术栈）
- 30% 项目深挖题（根据简历项目）
- 20% 场景设计题（结合 JD 业务场景）
- 10% 软技能题

只返回 JSON。"""


def create_question_generator():
    return create_react_agent(
        model=get_creative_llm(),
        tools=[],
        name="question_generator",
        prompt=SYSTEM_PROMPT,
    )


_question_agent = None


def _get_question_generator():
    global _question_agent
    if _question_agent is None:
        _question_agent = create_question_generator()
    return _question_agent


def question_generator_node(state: InterviewState) -> InterviewState:
    """出题节点"""
    input_text = f"""
JD 分析: {json.dumps(state.get("jd_analysis", {}), ensure_ascii=False, indent=2)}

简历分析: {json.dumps(state.get("resume_analysis", {}), ensure_ascii=False, indent=2)}

差距分析: {json.dumps(state.get("gap_analysis", {}), ensure_ascii=False, indent=2)}
"""
    agent = _get_question_generator()
    result = agent.invoke({
        "messages": [HumanMessage(content=input_text)]
    })

    try:
        data = json.loads(result["messages"][-1].content)
        questions = data.get("questions", [])
    except (json.JSONDecodeError, KeyError):
        questions = []

    return {
        **state,
        "questions": questions,
        "current_question_index": 0,
        "phase": "questions_ready",
    }
