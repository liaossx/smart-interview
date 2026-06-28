from langchain_openai import ChatOpenAI
from app.core.config import get_settings


def get_llm(temperature: float = 0.7):
    """获取统一的 LLM 实例（兼容 DeepSeek API）"""
    settings = get_settings()
    return ChatOpenAI(
        model=settings.deepseek_chat_model,
        temperature=temperature,
        api_key=settings.deepseek_api_key,
        base_url=settings.deepseek_base_url,
        request_timeout=60,
    )


def get_fast_llm():
    """获取快速推理的 LLM（低温度）"""
    return get_llm(temperature=0.3)


def get_creative_llm():
    """获取创意生成的 LLM（高温度）"""
    return get_llm(temperature=0.8)
