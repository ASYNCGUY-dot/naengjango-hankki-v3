"""
외부 공공 API(식약처/KAMIS) 호출 결과를 짧은 시간만 재사용하는 아주 단순한 캐시.

왜 필요한가: 이번 세션에 식약처·KAMIS 두 API가 실제로 응답 없음(ReadTimeout)을 겪었다.
503로 우아하게 처리하도록 이미 고쳐뒀지만, 그건 "에러를 안 보이게" 한 것이지 "기능이
계속 동작하게" 한 건 아니다. TTL 안에서는 같은 응답을 재사용해서 (1) 외부 API 호출
빈도 자체를 줄이고, (2) 방금 막 실패했더라도 그 직전까지 성공했던 응답이 남아있으면
그걸 그대로 돌려줘서 일시적 장애를 사용자가 못 느끼게 한다.

Render 단일 인스턴스 기준 - 프로세스 메모리에만 있어서 재배포되면 캐시가 비워진다.
로그인 실패 카운터(api/routers/auth.py)와 같은 성격의, 이 규모에서 감내할 만한 트레이드오프다.
"""

import time
from collections.abc import Callable
from typing import TypeVar

T = TypeVar("T")


class TTLCache:
    def __init__(self, ttl_seconds: float):
        self.ttl_seconds = ttl_seconds
        self._value: object = None
        self._fetched_at: float | None = None

    def get_or_fetch(self, fetch_fn: Callable[[], T]) -> T:
        """
        캐시가 TTL 안이면 그대로 재사용한다. 캐시가 없거나 지났으면 fetch_fn()을 새로
        불러온다 - 성공하면 캐시를 갱신하고, 실패하면 예외를 그대로 올리되 직전에 성공한
        캐시가 남아있으면 그걸 폴백으로 돌려준다(완전히 새 캐시라 폴백도 없으면 예외를
        그대로 던져서, 호출부의 503 처리가 그대로 동작하게 한다).
        """
        now = time.monotonic()
        if self._fetched_at is not None and (now - self._fetched_at) < self.ttl_seconds:
            return self._value  # type: ignore[return-value]

        try:
            value = fetch_fn()
        except Exception:
            if self._fetched_at is not None:
                return self._value  # type: ignore[return-value]
            raise

        self._value = value
        self._fetched_at = now
        return value

    def clear(self):
        """테스트에서 캐시 상태를 초기화할 때 쓴다 - 프로덕션 코드에서는 부르지 않는다."""
        self._value = None
        self._fetched_at = None
