"""사용 로그 기록 (2026-08-18).

Phase 4에서 지인 5명에게 일주일 써보게 할 때 "어느 단계에서 멈추는가"를 보기 위한
것이다. 상태만 봐서는 첫날 재료를 넣고 안 돌아온 사람과 엿새째까지 쓰다 멈춘 사람이
구분되지 않는다. 그래서 시각이 남지 않는 행동만 골라 이벤트로 쌓는다.
어떤 이벤트를 남기고 무엇을 남기지 않는지는 migration/007_usage_events.sql에 적어뒀다.

이 파일이 지키는 규칙은 하나다. **로그 때문에 요청이 실패하면 안 된다.**
로그는 부수적인 기록이고, 그것 때문에 사용자가 추천을 못 받거나 재료가 저장되지
않으면 배보다 배꼽이 크다.

그래서 그냥 try/except로 감싸면 되는 게 아니다. Postgres는 트랜잭션 안에서 문 하나가
실패하면 트랜잭션 전체를 중단 상태로 만든다. 예외를 삼켜도 그 뒤의 COMMIT이 사실상
ROLLBACK으로 처리되므로, **사용자가 방금 넣은 재료가 조용히 사라진다.** 로그 INSERT를
SAVEPOINT로 감싸는 이유가 이것이다 - 실패해도 되돌리는 범위가 로그 한 줄로 한정된다.
"""

import logging
from datetime import datetime, timezone

_logger = logging.getLogger("api.usage_log")

# 이벤트 이름을 여기 모아둔다. 라우터가 문자열을 직접 쓰면 오타가 나도 아무도 모르고,
# 나중에 집계 쿼리에서 한 종류가 통째로 비어 보인다.
LOGIN = "login"
ONBOARDING_DONE = "onboarding_done"
PANTRY_ADD = "pantry_add"
RECOMMEND = "recommend"
RECIPE_VIEW = "recipe_view"
# 자랑 글 작성. 글 자체가 brags에 created_at과 함께 남지만, 이건 "만들어봤다"는
# 이 앱의 최종 목표에 닿은 유일한 신호라 이탈 지점 분석에서 따로 세고 싶다.
BRAG_POST = "brag_post"


def record(cur, event: str, user_id: int | None = None, recipe_id: int | None = None) -> None:
    """이벤트 한 줄을 남긴다. 실패해도 호출부에 예외를 올리지 않는다."""
    try:
        cur.execute("SAVEPOINT usage_log")
    except Exception:
        # 세이브포인트조차 못 잡는 상황이면 트랜잭션이 이미 정상이 아니다.
        # 여기서 더 건드리면 상태만 나빠지므로 로그를 포기한다.
        _logger.warning("usage_log: SAVEPOINT 실패, 기록을 건너뛴다", exc_info=True)
        return

    try:
        cur.execute(
            "INSERT INTO usage_events (user_id, event, recipe_id, created_at) "
            "VALUES (?, ?, ?, ?)",
            (user_id, event, recipe_id, datetime.now(timezone.utc).isoformat()),
        )
        cur.execute("RELEASE SAVEPOINT usage_log")
    except Exception:
        _logger.warning("usage_log: %s 기록 실패", event, exc_info=True)
        try:
            cur.execute("ROLLBACK TO SAVEPOINT usage_log")
            cur.execute("RELEASE SAVEPOINT usage_log")
        except Exception:
            _logger.warning("usage_log: 세이브포인트 복구 실패", exc_info=True)
