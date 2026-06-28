"""统计数据客户端：从后端拉取面试历史统计数据，注入 AI prompt"""

import logging
import time
import httpx
from typing import Optional
from app.core.config import get_settings

logger = logging.getLogger(__name__)


class StatsClient:
    """拉取后端聚合统计，格式化后供 AI prompt 使用"""

    def __init__(self, base_url: str = None, timeout: float = 5.0, cache_ttl: int = 300):
        settings = get_settings()
        self.base_url = base_url or f"{settings.backend_url}/api/v1/stats"
        self.timeout = timeout
        self.internal_key = settings.internal_api_key
        self._cache = {}
        self._cache_ttl = cache_ttl

    def _fetch(self, path: str) -> dict:
        # 查缓存
        cached = self._cache.get(path)
        if cached:
            ts, data = cached
            if time.time() - ts < self._cache_ttl:
                return data

        url = f"{self.base_url}{path}"
        headers = {}
        if self.internal_key:
            headers["X-Internal-Key"] = self.internal_key
        try:
            with httpx.Client() as client:
                resp = client.get(url, timeout=self.timeout, headers=headers)
                if resp.status_code == 200:
                    data = resp.json()
                    result = data.get("data", data)
                    self._cache[path] = (time.time(), result)
                    return result
                logger.warning(f"Stats API {url} 返回 {resp.status_code}")
                return {}
        except Exception as e:
            logger.warning(f"Stats API {url} 不可达: {e}")
            return {}

    def get_category_stats(self) -> dict:
        return self._fetch("/categories")

    def get_overall_stats(self) -> dict:
        return self._fetch("/overview")

    def get_full_stats(self) -> dict:
        return self._fetch("/full")

    def get_calibrated_examples(self, category: str = None) -> list:
        path = "/calibrated"
        if category:
            path += f"?category={category}"
        return self._fetch(path) or []

    def build_scoring_context(self, category: str) -> str:
        """为单题评分构建历史数据上下文 + 校准样本"""
        stats = self.get_category_stats()
        examples = self.get_calibrated_examples(category) if category else []

        lines = []
        if not stats and not examples:
            return ""

        lines.append("【历史参考数据 — 仅作评分参照】")

        if stats:
            categories = stats.get("categories", [])
            lines.append(f"系统至今共评阅 {stats.get('totalQAs', 0)} 道答题。")

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

            overall = next((c for c in categories if c.get("category") == "综合"), None)
            if overall and overall.get("count", 0) > 0:
                lines.append(
                    f"综合均分 {overall['avgScore']}，"
                    f"区间 [{overall.get('minScore', '?')}-{overall.get('maxScore', '?')}]。"
                )

        # 校准样本：few-shot
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
        """为综合评估构建全局历史数据上下文"""
        overview = self.get_overall_stats()
        cats = self.get_category_stats()

        if not overview and not cats:
            return ""

        lines = ["【系统历史面试数据 — 仅作评估参照】"]

        if overview:
            lines.append(
                f"已完成 {overview.get('completedSessions', 0)} 场面试 / "
                f"共 {overview.get('totalSessions', 0)} 场，"
                f"用户均分 {overview.get('avgTotalScore', 'N/A')}，"
                f"完成率 {overview.get('completionRate', 'N/A')}%。"
            )

        if cats:
            for c in cats.get("categories", [])[:5]:
                if c.get("category") != "综合" and c.get("count", 0) > 0:
                    lines.append(
                        f"  - {c['category']}: {c['count']} 题, "
                        f"均分 {c['avgScore']} [{c.get('minScore', '?')}-{c.get('maxScore', '?')}]"
                    )

        return "\n".join(lines)


stats_client = StatsClient()
