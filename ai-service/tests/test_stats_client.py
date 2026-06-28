"""StatsClient 测试：TTL 缓存、HTTP 错误处理、上下文构建"""

import pytest
from unittest.mock import patch, MagicMock, Mock

from app.services.stats_client import StatsClient


def make_mock_response(status_code=200, json_data=None):
    """构造 httpx mock 响应"""
    resp = Mock()
    resp.status_code = status_code
    resp.json.return_value = json_data or {}
    return resp


@patch("app.services.stats_client.httpx.Client")
def test_ttl_cache_hit(mock_client_cls):
    """TTL 缓存命中：相同 path 第二次走缓存，HTTP 只调用 1 次"""
    client = StatsClient(cache_ttl=300)
    mock_resp = make_mock_response(200, {"data": {"key": "value"}})
    mock_client_cls.return_value.__enter__.return_value.get.return_value = mock_resp

    result1 = client._fetch("/categories")
    result2 = client._fetch("/categories")

    assert result1 == {"key": "value"}
    assert result2 == {"key": "value"}
    assert mock_client_cls.return_value.__enter__.return_value.get.call_count == 1


@patch("app.services.stats_client.httpx.Client")
def test_ttl_cache_expiry(mock_client_cls):
    """TTL 过期重新请求：cache_ttl=0 时缓存立即过期，HTTP 调用 2 次"""
    client = StatsClient(cache_ttl=0)
    mock_resp = make_mock_response(200, {"data": {"key": "value"}})
    mock_client_cls.return_value.__enter__.return_value.get.return_value = mock_resp

    result1 = client._fetch("/categories")
    result2 = client._fetch("/categories")

    assert result1 == {"key": "value"}
    assert result2 == {"key": "value"}
    assert mock_client_cls.return_value.__enter__.return_value.get.call_count == 2


@patch("app.services.stats_client.httpx.Client")
def test_different_path_independent_cache(mock_client_cls):
    """不同 path 独立缓存：两个 path 各发一次 HTTP"""
    client = StatsClient(cache_ttl=300)
    mock_resp = make_mock_response(200, {"data": {"key": "value"}})
    mock_client_cls.return_value.__enter__.return_value.get.return_value = mock_resp

    client._fetch("/categories")
    client._fetch("/overview")

    assert mock_client_cls.return_value.__enter__.return_value.get.call_count == 2


@patch("app.services.stats_client.httpx.Client")
def test_http_error_returns_empty(mock_client_cls):
    """HTTP 错误返回空 dict：status_code=500"""
    client = StatsClient(cache_ttl=300)
    mock_resp = make_mock_response(500, {})
    mock_client_cls.return_value.__enter__.return_value.get.return_value = mock_resp

    result = client._fetch("/categories")

    assert result == {}


@patch("app.services.stats_client.httpx.Client")
def test_network_exception_returns_empty(mock_client_cls):
    """网络异常返回空 dict：httpx 抛出 ConnectionError"""
    client = StatsClient(cache_ttl=300)
    mock_client_cls.return_value.__enter__.return_value.get.side_effect = ConnectionError("Connection refused")

    result = client._fetch("/categories")

    assert result == {}


def test_build_scoring_context_format():
    """build_scoring_context 格式化：验证输出包含类别名、均分、区间"""
    client = StatsClient(cache_ttl=300)
    client._fetch = Mock(side_effect=lambda path: {
        "/categories": {
            "categories": [
                {"category": "技术基础", "count": 10, "avgScore": 6.5, "minScore": 3, "maxScore": 9},
                {"category": "综合", "count": 20, "avgScore": 7.0, "minScore": 2, "maxScore": 10},
            ],
            "totalQAs": 30,
        },
        "/calibrated?category=技术基础": [
            {"question": "HashMap原理", "answer": "数组+链表", "score": 7},
        ],
    }.get(path, {}))

    result = client.build_scoring_context("技术基础")

    assert "技术基础" in result
    assert "6.5" in result
    assert "10" in result  # count
    assert "[3-9]" in result  # min-max range
    assert "校准" in result or "样本" in result  # calibrated examples section


def test_build_scoring_context_empty_data():
    """build_scoring_context 空数据：_fetch 返回空，输出为空字符串"""
    client = StatsClient(cache_ttl=300)
    client._fetch = Mock(return_value={})

    result = client.build_scoring_context("技术基础")

    assert result == ""
