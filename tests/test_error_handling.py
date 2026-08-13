"""처리되지 않은 서버 오류가 브라우저에 제대로 도착하는지 검증한다 (2026-08-13).

왜 필요한가
가입이 500으로 실패했는데 브라우저 콘솔에는 CORS 차단으로 찍혔다. Starlette의 기본
오류 처리기가 CORS 미들웨어 바깥에서 응답을 만들어 500 응답에 CORS 헤더가 붙지 않았기
때문이다. 화면에는 "연결에 실패했습니다"만 떠서, 실제 원인(DB 컬럼 누락)을 찾는 데
한참 걸렸다.

지인 테스트에서 서버 오류가 나면 사용자도 개발자도 원인을 못 보게 되므로, 500이
CORS 헤더를 달고 나가는지 못박아 둔다.
"""

import pytest

from src.agents import recommendation_agent

DEV_ORIGIN = "http://localhost:5173"


@pytest.fixture()
def exploding_endpoint(monkeypatch):
    """조회 도중 예외가 나는 상황을 만든다."""

    def boom(*args, **kwargs):
        raise RuntimeError("일부러 낸 오류")

    monkeypatch.setattr(recommendation_agent, "get_recipe_by_id", boom)


def test_unhandled_error_returns_500_json(client, exploding_endpoint):
    res = client.get("/recommendation/recipes/1")
    assert res.status_code == 500
    assert "detail" in res.json()


def test_error_response_carries_cors_header(client, exploding_endpoint):
    """이게 없으면 브라우저가 500을 CORS 차단으로 보고해서 진짜 원인이 가려진다."""
    res = client.get("/recommendation/recipes/1", headers={"Origin": DEV_ORIGIN})
    assert res.status_code == 500
    assert res.headers.get("access-control-allow-origin") == DEV_ORIGIN


def test_error_response_does_not_leak_internals(client, exploding_endpoint):
    """예외 문구나 스택을 응답에 담지 않는다 - 내부 구조가 사용자에게 갈 이유가 없다."""
    res = client.get("/recommendation/recipes/1")
    body = res.text
    assert "일부러 낸 오류" not in body
    assert "Traceback" not in body
    assert "recommendation_agent" not in body


def test_normal_responses_are_unaffected(client):
    """오류 처리를 붙였다고 정상 응답이 달라지면 안 된다."""
    res = client.get("/recommendation/recipes/1", headers={"Origin": DEV_ORIGIN})
    assert res.status_code == 200
    assert res.headers.get("access-control-allow-origin") == DEV_ORIGIN


def test_http_exceptions_keep_their_own_status(client):
    """의도적으로 던진 404는 500으로 바뀌면 안 된다."""
    res = client.get("/recommendation/recipes/999999", headers={"Origin": DEV_ORIGIN})
    assert res.status_code == 404
    assert res.headers.get("access-control-allow-origin") == DEV_ORIGIN
