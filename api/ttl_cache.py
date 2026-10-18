"""
외부 공공 API(식약처/KAMIS) 호출 결과를 짧은 시간만 재사용하는 아주 단순한 캐시.

왜 필요한가: 이번 세션에 식약처·KAMIS 두 API가 실제로 응답 없음(ReadTimeout)을 겪었다.
503로 우아하게 처리하도록 이미 고쳐뒀지만, 그건 "에러를 안 보이게" 한 것이지 "기능이
계속 동작하게" 한 건 아니다. TTL 안에서는 같은 응답을 재사용해서 (1) 외부 API 호출
빈도 자체를 줄이고, (2) 방금 막 실패했더라도 그 직전까지 성공했던 응답이 남아있으면
그걸 그대로 돌려줘서 일시적 장애를 사용자가 못 느끼게 한다.

Render 단일 인스턴스 기준 - 프로세스 메모리에만 있어서 재배포되면 캐시가 비워진다.
로그인 실패 카운터(api/routers/auth.py)와 같은 성격의, 이 규모에서 감내할 만한 트레이드오프다.

2026-10-18 추가: "재사용하는 시간(ttl_seconds)"과 "장애 때 이전 값을 허용하는 최대 기간
(max_stale_seconds)"을 나눴다. 전에는 갱신이 계속 실패하면 며칠 전 결과도 기간 제한 없이
돌려줬다. 상한은 쓰는 쪽이 정한다 - 기본값(None)은 예전처럼 제한이 없어서, 상한을 주지 않은
식약처 회수 정보(api/routers/safety.py)의 동작은 그대로다.
"""

import time
from collections.abc import Callable
from typing import TypeVar

T = TypeVar("T")


class TTLCache:
    def __init__(
        self,
        ttl_seconds: float,
        max_stale_seconds: float | None = None,
        clock: Callable[[], float] = time.monotonic,
    ):
        self.ttl_seconds = ttl_seconds
        # 갱신이 실패했을 때 이전 값을 돌려줄 수 있는 최대 기간(받은 시각부터). None이면 제한 없음.
        self.max_stale_seconds = max_stale_seconds
        # 테스트가 실제로 기다리지 않고 시간을 옮길 수 있게 시계를 바꿔 끼운다.
        self._clock = clock
        self._value: object = None
        self._fetched_at: float | None = None

    def get_or_fetch(self, fetch_fn: Callable[[], T]) -> T:
        """
        캐시가 TTL 안이면 그대로 재사용한다. 캐시가 없거나 지났으면 fetch_fn()을 새로
        불러온다 - 성공하면 캐시를 갱신하고, 실패하면 예외를 그대로 올리되 직전에 성공한
        캐시가 남아있으면 그걸 폴백으로 돌려준다(완전히 새 캐시라 폴백도 없으면 예외를
        그대로 던져서, 호출부의 503 처리가 그대로 동작하게 한다).
        """
        value, _stale = self.get_or_fetch_with_status(fetch_fn)
        return value

    def get_or_fetch_with_status(self, fetch_fn: Callable[[], T]) -> tuple[T, bool]:
        """get_or_fetch와 같고, 돌려준 값이 **갱신에 실패해서 쓴 이전 값인지**를 함께 준다.

        화면이 "이번에는 새로 못 받아 이전에 받은 시세"라고 밝히려면 이것을 알아야 한다.
        여러 요청이 동시에 오므로(FastAPI는 동기 엔드포인트를 스레드에서 돌린다) 상태를
        인스턴스에 남기지 않고 값과 함께 돌려준다.
        """
        now = self._clock()
        if self._fetched_at is not None and (now - self._fetched_at) < self.ttl_seconds:
            return self._value, False  # type: ignore[return-value]

        try:
            value = fetch_fn()
        except Exception:
            if self._fetched_at is not None and self._within_stale_limit(now):
                return self._value, True  # type: ignore[return-value]
            raise

        self._value = value
        self._fetched_at = now
        return value, False

    def _within_stale_limit(self, now: float) -> bool:
        if self.max_stale_seconds is None:
            return True
        # 정확히 상한에 닿은 값은 쓰지 않는다("24시간까지" = 24시간 미만).
        return (now - self._fetched_at) < self.max_stale_seconds  # type: ignore[operator]

    def clear(self):
        """테스트에서 캐시 상태를 초기화할 때 쓴다 - 프로덕션 코드에서는 부르지 않는다."""
        self._value = None
        self._fetched_at = None
