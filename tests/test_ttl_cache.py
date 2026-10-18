"""
api/ttl_cache.py의 재사용 시간(TTL)과 장애 때 이전 값을 허용하는 최대 기간을 검증한다 (2026-10-18).

시간은 실제로 기다리지 않고 가짜 시계로 옮긴다. 24시간짜리 상한을 진짜로 기다릴 수는 없다.
"""

import pytest

from api.routers import price as price_router
from api.routers import safety as safety_router
from api.ttl_cache import TTLCache

HOUR = 60 * 60


class FakeClock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float):
        self.now += seconds


def _failing():
    raise TimeoutError("KAMIS 응답 없음")


@pytest.fixture
def clock():
    return FakeClock()


def test_value_is_reused_within_ttl(clock):
    cache = TTLCache(ttl_seconds=600, clock=clock)
    calls = {"n": 0}

    def fetch():
        calls["n"] += 1
        return "v1"

    assert cache.get_or_fetch_with_status(fetch) == ("v1", False)
    clock.advance(599)
    assert cache.get_or_fetch_with_status(fetch) == ("v1", False)
    assert calls["n"] == 1


def test_expired_value_is_refreshed_when_the_fetch_succeeds(clock):
    cache = TTLCache(ttl_seconds=600, max_stale_seconds=24 * HOUR, clock=clock)
    cache.get_or_fetch(lambda: "v1")
    clock.advance(600)

    assert cache.get_or_fetch_with_status(lambda: "v2") == ("v2", False)


def test_previous_value_is_used_within_the_stale_limit_and_says_so(clock):
    cache = TTLCache(ttl_seconds=600, max_stale_seconds=24 * HOUR, clock=clock)
    cache.get_or_fetch(lambda: "v1")
    clock.advance(23 * HOUR)

    assert cache.get_or_fetch_with_status(_failing) == ("v1", True)


def test_previous_value_past_the_stale_limit_is_refused(clock):
    cache = TTLCache(ttl_seconds=600, max_stale_seconds=24 * HOUR, clock=clock)
    cache.get_or_fetch(lambda: "v1")
    clock.advance(25 * HOUR)

    with pytest.raises(TimeoutError):
        cache.get_or_fetch_with_status(_failing)


def test_stale_limit_boundary(clock):
    """24시간 미만은 쓰고, 정확히 24시간이 된 값은 쓰지 않는다."""
    cache = TTLCache(ttl_seconds=600, max_stale_seconds=24 * HOUR, clock=clock)
    cache.get_or_fetch(lambda: "v1")

    clock.advance(24 * HOUR - 1)
    assert cache.get_or_fetch_with_status(_failing) == ("v1", True)

    clock.advance(1)
    with pytest.raises(TimeoutError):
        cache.get_or_fetch_with_status(_failing)


def test_stale_age_counts_from_the_last_successful_fetch(clock):
    """이전 값을 돌려줘도 받은 시각은 그대로다. 실패가 이어지는 동안 상한이 계속 밀리면 안 된다."""
    cache = TTLCache(ttl_seconds=600, max_stale_seconds=24 * HOUR, clock=clock)
    cache.get_or_fetch(lambda: "v1")

    for _ in range(23):
        clock.advance(HOUR)
        assert cache.get_or_fetch_with_status(_failing) == ("v1", True)
    clock.advance(HOUR)
    with pytest.raises(TimeoutError):
        cache.get_or_fetch_with_status(_failing)


def test_first_fetch_failure_raises(clock):
    cache = TTLCache(ttl_seconds=600, max_stale_seconds=24 * HOUR, clock=clock)
    with pytest.raises(TimeoutError):
        cache.get_or_fetch_with_status(_failing)


def test_without_a_stale_limit_the_old_behavior_stays(clock):
    """상한을 주지 않으면 예전처럼 기간 제한 없이 이전 값을 돌려준다(식약처 회수 정보가 이렇다)."""
    cache = TTLCache(ttl_seconds=600, clock=clock)
    cache.get_or_fetch(lambda: "v1")
    clock.advance(30 * 24 * HOUR)

    assert cache.get_or_fetch(_failing) == "v1"


def test_only_kamis_gets_the_stale_limit():
    """공용 캐시를 고치면서 다른 기능의 장애 대응까지 바꾸지 않는다."""
    assert price_router._prices_cache.max_stale_seconds == 24 * HOUR
    assert price_router._prices_cache.ttl_seconds == 600
    assert safety_router._recalls_cache.max_stale_seconds is None
