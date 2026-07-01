"""
统计数据客户端：从后端拉取面试历史统计数据，注入 AI prompt。

本文件是 AI 评分链路的"数据校准层"，职责：
1. 通过 HTTP 调用后端 stats API，获取历史面试的聚合统计（各类别均分/区间/完成率等）。
2. 5 分钟 TTL 内存缓存，减少对后端的重复请求。
3. build_scoring_context()：把单题类别的历史数据 + 人工校准样本格式化为 prompt 文本，
   注入 _score_answer() 的评分 prompt，使 LLM 评分有横向参照。
4. build_evaluation_context()：把全局历史数据格式化为 prompt 文本，
   注入 _run_evaluation() 的评估 prompt，使综合评估有系统级参照。
5. 使用 X-Internal-Key 头做服务间鉴权，区分内部调用与外部请求。

详见 AI链路学习路径.md 第六步。
"""

import logging
import time
import httpx
from typing import Optional
from app.core.config import get_settings

logger = logging.getLogger(__name__)


class StatsClient:
    """
    拉取后端聚合统计，格式化后供 AI prompt 使用。

    缓存策略：每次 _fetch() 先查内存缓存，未过期（< TTL）直接返回，
    过期或未命中才发 HTTP 请求，请求成功后写回缓存。
    """

    def __init__(self, base_url: str = None, timeout: float = 5.0, cache_ttl: int = 300):
        # 从全局配置加载后端 URL 和内部鉴权密钥
        settings = get_settings()
        self.base_url = base_url or f"{settings.backend_url}/api/v1/stats"  # 后端 stats API 基址
        self.timeout = timeout            # HTTP 超时 5s，避免后端慢拖垮 AI 链路
        self.internal_key = settings.internal_api_key  # 服务间鉴权密钥
        self._cache = {}                 # 内存缓存：path -> (timestamp, data)
        self._cache_ttl = cache_ttl      # 缓存有效期 300s（5 分钟）

    def _fetch(self, path: str) -> dict:
        """
        带缓存的 HTTP GET 请求。

        缓存逻辑：
        1. 先查 _cache[path]，若 (当前时间 - 时间戳) < TTL 直接返回缓存数据。
        2. 缓存未命中或过期，发 HTTP 请求，成功后写回缓存。
        3. 请求失败（超时/非200/异常）返回空 dict，不写缓存，不影响 AI 主流程。

        鉴权：请求头带 X-Internal-Key，后端据此识别为内部服务调用，跳过用户鉴权。
        """
        # 查缓存
        cached = self._cache.get(path)
        if cached:
            ts, data = cached
            if time.time() - ts < self._cache_ttl:
                return data  # 缓存命中，直接返回

        # 缓存未命中或已过期，发起 HTTP 请求到后端
        url = f"{self.base_url}{path}"
        # X-Internal-Key：服务间鉴权头，后端识别为 AI 服务内部调用，无需用户 token
        headers = {}
        if self.internal_key:
            headers["X-Internal-Key"] = self.internal_key
        try:
            # httpx 同步客户端，timeout=5s 防止后端慢响应拖垮 AI 评分链路
            with httpx.Client() as client:
                resp = client.get(url, timeout=self.timeout, headers=headers)
                if resp.status_code == 200:
                    data = resp.json()
                    # 后端统一响应格式 {code, data, ...}，取 data 字段；无则用整个 body
                    result = data.get("data", data)
                    self._cache[path] = (time.time(), result)  # 写回缓存
                    return result
                logger.warning(f"Stats API {url} 返回 {resp.status_code}")
                return {}
        except Exception as e:
            # 后端不可达时返回空 dict，AI 链路降级运行（无统计参照也能评分）
            logger.warning(f"Stats API {url} 不可达: {e}")
            return {}

    def get_category_stats(self) -> dict:
        """获取各题类别的历史统计（题数/均分/区间），走 5 分钟缓存"""
        return self._fetch("/categories")

    def get_overall_stats(self) -> dict:
        """获取全局面试概览（完成场数/均分/完成率），走 5 分钟缓存"""
        return self._fetch("/overview")

    def get_full_stats(self) -> dict:
        """获取完整统计数据（类别 + 概览 + 校准样本），走 5 分钟缓存"""
        return self._fetch("/full")

    def get_calibrated_examples(self, category: str = None) -> list:
        """获取人工校准样本（few-shot 参考题），可选按类别过滤"""
        path = "/calibrated"
        if category:
            path += f"?category={category}"
        return self._fetch(path) or []

    def build_scoring_context(self, category: str) -> str:
        """
        为单题评分构建历史数据上下文 + 校准样本，格式化为 prompt 文本。

        输出文本会被原样拼入 _score_answer() 的评分 prompt，包含两部分：
        1. 【历史参考数据】：该类别的题数、均分、区间 + 综合均分，
           让 LLM 评分时知道"同类回答通常得多少分"，避免评分尺度漂移。
        2. 【人工校准参考样本】：few-shot 示例（题目+回答+校准分），
           让 LLM 参照人工标注的标准来评分。

        若后端不可达或无数据，返回空字符串，AI 链路正常降级运行。
        """
        # 获取该类别的历史统计（题数/均分/区间），走 5 分钟缓存
        stats = self.get_category_stats()
        # 获取人工校准样本（few-shot 参考题），按类别过滤，走 5 分钟缓存
        examples = self.get_calibrated_examples(category) if category else []

        lines = []  # 逐行拼接 prompt 文本
        # 无任何历史数据时返回空字符串，不污染 prompt
        if not stats and not examples:
            return ""

        lines.append("【历史参考数据 — 仅作评分参照】")

        if stats:
            categories = stats.get("categories", [])  # 各类别的统计列表
            lines.append(f"系统至今共评阅 {stats.get('totalQAs', 0)} 道答题。")

            # 找到当前类别的统计，展示题数/均分/区间
            target = None
            for c in categories:
                if c.get("category") == category:
                    target = c
                    break

            if target and target.get("count", 0) > 0:
                lines.append(
                    f"「{category}」类别历史 {target['count']} 题，"
                    f"平均 {target['avgScore']} 分，"
                    f"区间 [{target.get('minScore', '?')}-{target.get('maxScore', '?')}]。"
                )

            # 综合类别（跨类别均分），给 LLM 一个全局参照基准
            overall = next((c for c in categories if c.get("category") == "综合"), None)
            if overall and overall.get("count", 0) > 0:
                lines.append(
                    f"综合均分 {overall['avgScore']}，"
                    f"区间 [{overall.get('minScore', '?')}-{overall.get('maxScore', '?')}]。"
                )

        # 校准样本：few-shot 方式让 LLM 参照人工标注标准评分
        # 最多取 3 个样本，避免 prompt 过长
        if examples:
            lines.append("")
            lines.append("【人工校准参考样本 — 请参照此标准评分】")
            for i, ex in enumerate(examples[:3]):
                lines.append(
                    f"样本{i+1}: Q: {ex.get('question', '')[:100]}..."
                    f" A: {ex.get('answer', '')[:80]}..."
                    f" → 校准分: {ex.get('score')}/10"
                )

        return "\n".join(lines)

    def build_evaluation_context(self) -> str:
        """
        为综合评估构建全局历史数据上下文。

        与 build_scoring_context() 的区别：
        - build_scoring_context 面向单题评分，聚焦某一类别的历史分布。
        - build_evaluation_context 面向整场面试的综合评估，提供系统级数据：
          完成场数、用户均分、完成率、各主要类别的分布概览。

        输出文本注入 _run_evaluation() 的评估 prompt，让评估节点知道
        "候选人在系统中处于什么水平"。
        """
        # 获取全局面试概览（完成场数/均分/完成率），走 5 分钟缓存
        overview = self.get_overall_stats()
        # 获取各类别统计（题数/均分/区间），走 5 分钟缓存
        cats = self.get_category_stats()

        # 无数据时返回空字符串，不污染评估 prompt
        if not overview and not cats:
            return ""

        lines = ["【系统历史面试数据 — 仅作评估参照】"]

        if overview:
            # 拼接全局概览：让评估节点知道候选人在系统中的相对水平
            lines.append(
                f"已完成 {overview.get('completedSessions', 0)} 场面试 / "
                f"共 {overview.get('totalSessions', 0)} 场，"
                f"用户均分 {overview.get('avgTotalScore', 'N/A')}，"
                f"完成率 {overview.get('completionRate', 'N/A')}%。"
            )

        if cats:
            # 展示前 5 个类别的分布（排除"综合"），让评估节点了解各维度系统水平
            # 截取前 5 个避免 prompt 过长；排除"综合"因为它是跨类别汇总非独立维度
            for c in cats.get("categories", [])[:5]:
                if c.get("category") != "综合" and c.get("count", 0) > 0:
                    lines.append(
                        f"  - {c['category']}: {c['count']} 题, "
                        f"均分 {c['avgScore']} [{c.get('minScore', '?')}-{c.get('maxScore', '?')}]"
                    )

        return "\n".join(lines)


# 模块级单例：全局共享同一个 StatsClient 实例（含共享缓存）
stats_client = StatsClient()
