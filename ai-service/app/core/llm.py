"""LLM 工厂模块 —— AI 链路的底层基础设施

本模块是整个 AI 链路的 LLM 入口，所有 Agent 节点（JD 分析、简历分析、差距分析、
出题、评估）都通过这里获取 LLM 实例，而非直接实例化 ChatOpenAI。

设计要点：
1. 工厂模式（Factory Pattern）：通过 get_llm / get_fast_llm / get_creative_llm
   三个工厂函数统一管理 LLM 创建，避免在各 Agent 中重复配置 API Key、超时等参数，
   也便于未来切换模型供应商时只需改一处。
2. DeepSeek API 兼容：DeepSeek 提供 OpenAI 兼容接口，因此可以直接用 ChatOpenAI
   并指定 base_url 指向 DeepSeek 的 API 端点，无需引入额外的 SDK。
3. 温度（temperature）分层：不同任务对随机性需求不同——
   - 低温度(0.3)：分析类任务（JD 解析、简历解析、差距分析、评估）需要稳定、确定性输出
   - 高温度(0.8)：出题任务需要创意和多样性，避免每次生成雷同的题目
   - 中温度(0.7)：默认值，适合对话类场景

详见 AI链路学习路径.md 第1步（基础设施层）
"""

from langchain_openai import ChatOpenAI
from app.core.config import get_settings


def get_llm(temperature: float = 0.7):
    """
    获取统一的 LLM 实例（工厂方法）。

    所有 Agent 共用同一个底层模型（DeepSeek），通过 temperature 参数区分任务类型：
    - 分析类任务调用方传入低 temperature（0.3），确保 JSON 输出稳定可靠
    - 创意类任务调用方传入高 temperature（0.8），增加题目多样性

    DeepSeek API 兼容说明：
    DeepSeek 实现了 OpenAI 兼容协议，因此我们使用 langchain_openai 的 ChatOpenAI 类，
    仅需将 base_url 指向 DeepSeek 端点即可，模型名和 API Key 从配置读取。
    """
    settings = get_settings()
    return ChatOpenAI(
        model=settings.deepseek_chat_model,       # DeepSeek 模型名（如 deepseek-chat）
        temperature=temperature,                   # 温度参数：控制输出随机性，由调用方决定
        api_key=settings.deepseek_api_key,         # DeepSeek API Key
        base_url=settings.deepseek_base_url,       # DeepSeek 的 OpenAI 兼容端点 URL
        request_timeout=60,                        # 60秒超时，防止网络异常导致节点卡死
    )


def get_fast_llm():
    """
    获取低温度 LLM（temperature=0.3）。

    用于需要确定性输出的分析任务：JD 分析、简历分析、差距分析、评估。
    低温度减少随机性，使 LLM 更可靠地返回结构化 JSON，降低解析失败率。
    """
    return get_llm(temperature=0.3)


def get_creative_llm():
    """
    获取高温度 LLM（temperature=0.8）。

    用于需要创意和多样性的生成任务：面试出题。
    高温度让 LLM 生成更多样的题目表述和考察角度，避免每次面试题目雷同。
    """
    return get_llm(temperature=0.8)
