"""评估 Agent：面试结束后生成综合评估报告"""

from langgraph.prebuilt import create_react_agent
from langchain_core.messages import HumanMessage
from app.core.llm import get_fast_llm
from app.agents.state import InterviewState
import json


SYSTEM_PROMPT = """你是一位面试评估专家。根据面试全过程和各维度评分数据，生成综合评估报告。

以 JSON 格式返回：
{
  "overall_score": 75,
  "dimensions": [
    {
      "name": "技术基础",
      "score": 85,
      "comment": "评语",
      "suggestions": ["建议1", "建议2"]
    },
    {
      "name": "项目经验",
      "score": 70,
      "comment": "评语",
      "suggestions": ["建议1"]
    },
    {
      "name": "场景设计",
      "score": 78,
      "comment": "评语",
      "suggestions": ["建议1"]
    },
    {
      "name": "软技能",
      "score": 65,
      "comment": "评语",
      "suggestions": ["建议1", "建议2"]
    }
  ],
  "strengths": ["优势1", "优势2"],
  "weaknesses": ["不足1", "不足2"],
  "improvement_suggestions": ["改进建议1", "改进建议2"],
  "recommended_learning": [
    {"resource": "学习资源", "reason": "推荐原因"}
  ]
}

注意：dimensions 中的 score 直接使用输入数据中各题维度的聚合均分（已提供在 aggregated_dimensions 中），不要改动分数。
comment 和 suggestions 需要你根据各维度表现撰写。
overall_score 取四个维度分的均值。
只返回 JSON。"""


def create_evaluator():
    return create_react_agent(
        model=get_fast_llm(),
        tools=[],
        name="evaluator",
        prompt=SYSTEM_PROMPT,
    )


_evaluator_agent = None


def _get_evaluator():
    global _evaluator_agent
    if _evaluator_agent is None:
        _evaluator_agent = create_evaluator()
    return _evaluator_agent


def evaluator_node(state: InterviewState) -> InterviewState:
    """评估节点"""
    aggregated = state.get("aggregated_dimensions", [])
    answers = state.get("answers", [])

    input_data = {
        "aggregated_dimensions": aggregated,
        "answers": [
            {
                "question": a.get("question", ""),
                "category": a.get("category", ""),
                "score": a.get("score", 0),
                "dimensions": a.get("dimensions", {}),
                "feedback": a.get("feedback", ""),
            }
            for a in answers
        ],
        "jd_analysis": state.get("jd_analysis", {}),
        "gap_analysis": state.get("gap_analysis", {}),
    }

    stats_context = state.get("stats_context", "")
    prompt_content = json.dumps(input_data, ensure_ascii=False, indent=2)
    if stats_context:
        prompt_content = stats_context + "\n\n" + prompt_content

    agent = _get_evaluator()
    result = agent.invoke({
        "messages": [HumanMessage(content=prompt_content)]
    })

    try:
        evaluation = json.loads(result["messages"][-1].content)
    except (json.JSONDecodeError, KeyError):
        evaluation = {"overall_score": 0, "dimensions": [], "improvement_suggestions": []}

    return {**state, "evaluation": evaluation, "phase": "done"}
