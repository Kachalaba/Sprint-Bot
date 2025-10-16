import math

from aiohttp import ClientTimeout

from bot import _resolve_timeout_seconds


def test_resolve_timeout_from_client_timeout_total():
    timeout = ClientTimeout(total=42.5)
    assert math.isclose(_resolve_timeout_seconds(timeout), 42.5)


def test_resolve_timeout_prefers_positive_values():
    timeout = ClientTimeout(total=None, sock_read=15)
    assert math.isclose(_resolve_timeout_seconds(timeout), 15.0)


def test_resolve_timeout_from_numeric_values():
    assert _resolve_timeout_seconds(10) == 10.0
    assert _resolve_timeout_seconds(3.5) == 3.5


def test_resolve_timeout_filters_non_positive():
    assert _resolve_timeout_seconds(0) is None
    timeout = ClientTimeout(total=-1)
    assert _resolve_timeout_seconds(timeout) is None
