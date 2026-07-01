"""出题 Agent —— AI 链路分析管线的最后一个节点

本模块根据 JD 分析、简历分析和差距分析的结果，生成 8-12 道面试题目。
它是分析管线的终点（question_generator → END），生成的题目将驱动后续的 Q&A 交互。

核心设计要点：
1. 题目分类分配策略（40/30/20/10）：
   - 40% 技术基础题（八股文）：根据 JD 技术栈出题，如"HashMap 原理""MySQL 索引"
   - 30% 项目深挖题：根据简历项目出题，考察候选人真实经历和深度理解
   - 20% 场景设计题：结合 JD 业务场景，考察架构思维和方案设计能力
   - 10% 软技能题：考察沟通、团队协作、学习能力等非技术维度
   这个比例确保面试既考察基础功底，又考察实战能力和综合素质。

2. 公司规模难度调整：
   - 大厂：hard 40% / medium 50% / easy 10% → 重底层原理、系统设计、算法思维
   - 中型公司：hard 20% / medium 60% / easy 20% → 重框架实战、业务理解、问题排查
   - 创业公司：hard 10% / medium 50% / easy 40% → 重全栈能力、解决问题、实战经验
   公司规模来自 jd_analysis 中的 company_scale 字段，由 JD 分析节点判断。

3. 使用 get_creative_llm()（高温度 0.8）：
   出题是创意生成任务，高温度增加题目表述和考察角度的多样性，
   避免同一岗位每次面试都出相同的题目。

4. reference_answer 设计（四类区别对待）：
   - 技术基础（八股文）：完整 200-500 字参考答案，作为面试标准答案供候选人学习
   - 项目深挖：留空字符串，候选人的项目经历各不相同，无标准答案
   - 场景设计：留空字符串，设计方案因人而异，考察的是思路而非固定答案
   - 软技能：给出示例性参考答案，让候选人了解什么样的回答是高质量的

5. expected_answer_points 设计（四类区别对待）：
   - 技术基础：覆盖参考答案的核心知识点，要点 = 答案的知识骨架
   - 项目深挖：基于简历分析中该候选人的具体项目信息（tech_stack、highlights、项目角色）
     来定制要点，每个要点必须引用具体的项目名、技术栈或业务场景，引导候选人展开真实项目细节。
     禁止使用泛化表述如"项目背景清晰""明确个人职责"，务必具体到项目细节
   - 场景设计：列出关键的架构决策点和设计权衡（选型理由、数据一致性方案、高并发策略等）
   - 软技能：列出高质量回答应覆盖的维度，引导候选人用 STAR 原则结构化表达

详见 AI链路学习路径.md 第6步（出题节点）
"""

from langchain.agents import create_agent
from langchain_core.messages import HumanMessage
from app.core.llm import get_creative_llm
from app.agents.state import InterviewState
import json


# ---- System Prompt 设计 ----
# 这是整个 AI 链路中最复杂的 Prompt，包含四部分关键指令：
# 1. 公司规模出题风格规则：定义大厂/中型/创业公司各自的出题侧重点和难度比例
# 2. JSON 输出 schema：定义题目结构，含 category/question/difficulty/参考答案等
# 3. reference_answer 和 expected_answer_points 的按类别差异化规则
# 4. 题目分配建议：40%技术基础 + 30%项目深挖 + 20%场景设计 + 10%软技能
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
      "expected_answer_points": ["见下方规则"],
      "reference_answer": "见下方规则"
    }
  ]
}

==== reference_answer 规则（按 category 区分）====

【技术基础】必须填写完整的参考答案，200-500 字，作为面试标准答案供候选人学习：
- 用清晰的分点或段落阐述核心概念、原理、关键步骤
- 覆盖 expected_answer_points 中的所有要点并展开
- 语言专业但不晦涩，让候选人读完能真正理解这个知识点

【项目经验】必须留空字符串 "" —— 候选人的项目经历各不相同，无标准答案

【场景设计】必须留空字符串 "" —— 设计方案因人而异，没有唯一正确答案

【软技能】填写一段示例性参考答案（100-200 字），展示高质量回答的结构和深度：
- 用 STAR 原则（情境-任务-行动-结果）组织
- 让候选人明白这类开放题应该如何回答

==== expected_answer_points 规则（按 category 区分）====

【技术基础】要点 = 参考答案的知识骨架，列出 3-5 个必须覆盖的核心知识点

【项目经验】要点必须来自简历分析中该候选人的具体项目信息：
- 每个要点必须引用简历分析里的具体项目名、技术栈或项目亮点（highlights）
- 引导候选人展开真实项目细节，例如：
  - "订单系统从单体拆分微服务时，如何保证数据一致性"（引用简历中的项目名和 tech_stack）
  - "项目中 Redis 缓存与 DB 的读写一致性方案"（引用简历中具体使用的技术）
- 严禁使用泛化表述如"项目背景和业务目标清晰"、"明确个人职责"等

【场景设计】列出 3-5 个关键的架构决策点和设计权衡：
- 如"选型理由及替代方案对比"、"数据一致性保证"、"高并发下的性能优化策略"
- 考察候选人做 trade-off 的能力

【软技能】列出高质量回答应覆盖的维度：
- 如"使用了 STAR 原则"、"有具体案例和数据支撑"、"展示了自我反思"

==== 题目分配 ====
- 40% 技术基础题（根据 JD 技术栈）
- 30% 项目深挖题（根据简历项目）
- 20% 场景设计题（结合 JD 业务场景）
- 10% 软技能题

只返回 JSON。"""


def create_question_generator():
    """
    创建出题 ReAct Agent。

    使用 get_creative_llm()（高温度 0.8）：出题是创意生成任务，
    高温度让 LLM 生成更多样的题目表述和考察角度。
    这是整个链路中唯一使用高温度的节点，其他分析节点都用低温度。
    """
    return create_agent(
        model=get_creative_llm(),
        tools=[],
        name="question_generator",
        system_prompt=SYSTEM_PROMPT,
    )


# 单例 Agent 实例（懒加载）
_question_agent = None


def _get_question_generator():
    """获取出题 Agent 单例（懒加载模式）"""
    global _question_agent
    if _question_agent is None:
        _question_agent = create_question_generator()
    return _question_agent


def question_generator_node(state: InterviewState) -> InterviewState:
    """
    出题节点函数 —— LangGraph 图节点入口，分析管线的终点。

    接收前序三个节点的全部分析结果（JD 分析 + 简历分析 + 差距分析），
    拼接为输入文本发送给出题 Agent，生成 8-12 道面试题目。

    输出写入 state：
    - questions：题目列表，每题含 category/difficulty/reference_answer 等
    - current_question_index：初始化为 0，后续由 InterviewSession 逐题推进
    - phase：标记为 "questions_ready"，表示分析管线完成，可以开始面试
    """
    # 将三个分析结果拼接为 LLM 输入：JD 分析提供技术栈和公司规模，
    # 简历分析提供项目经历（用于项目深挖题），差距分析提供出题方向和难度建议
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
        # 解析 JSON：题目列表在 data["questions"] 中
        data = json.loads(result["messages"][-1].content)
        questions = data.get("questions", [])
    except (json.JSONDecodeError, KeyError):
        # 降级处理：解析失败时返回空题目列表
        # InterviewSession 会检测到空列表并做相应处理（如提示用户重新生成）
        questions = []

    return {
        **state,
        "questions": questions,              # 生成的面试题目列表
        "current_question_index": 0,         # 面试从第一题开始
        "phase": "questions_ready",          # 分析管线完成，进入面试阶段
    }
