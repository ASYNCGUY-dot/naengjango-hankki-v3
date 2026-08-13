"""브라우저가 이 API를 직접 부를 수 있는지 검증한다 (V3 Phase 3, 2026-08-13).

V2에는 CORS 설정이 없었는데도 동작했다. Reflex 프론트가 서버 쪽 Python에서 API를
불러서 브라우저의 교차 출처 검사를 거치지 않았기 때문이다. V3는 브라우저가 직접 부르는
SPA라, 이 설정이 빠지면 모든 요청이 preflight에서 막힌다. 실제로 로그인 화면을 붙이고
실제 API에 태워보다가 발견했다.

단위 테스트로는 안 잡히는 종류의 문제라, 여기서 preflight 응답 자체를 확인한다.
"""

from api.main import ALLOWED_ORIGINS

DEV_ORIGIN = "http://localhost:5173"


def _preflight(client, origin: str, method: str = "POST", path: str = "/auth/login"):
    return client.options(
        path,
        headers={
            "Origin": origin,
            "Access-Control-Request-Method": method,
            "Access-Control-Request-Headers": "content-type",
        },
    )


def test_dev_origin_is_allowed_by_default(client):
    """로컬 개발 주소는 환경변수 없이도 통해야 한다 - 안 그러면 개발을 시작할 수 없다."""
    assert DEV_ORIGIN in ALLOWED_ORIGINS

    res = _preflight(client, DEV_ORIGIN)
    assert res.status_code == 200
    assert res.headers["access-control-allow-origin"] == DEV_ORIGIN


def test_preflight_allows_authorization_header(client):
    """토큰을 Authorization 헤더로 보내므로, 이 헤더가 허용 목록에 없으면 인증된 요청이
    전부 막힌다."""
    res = client.options(
        "/profile/1",
        headers={
            "Origin": DEV_ORIGIN,
            "Access-Control-Request-Method": "GET",
            "Access-Control-Request-Headers": "authorization",
        },
    )
    assert res.status_code == 200
    allowed = res.headers["access-control-allow-headers"].lower()
    assert "authorization" in allowed


def test_unknown_origin_is_not_granted(client):
    """'*'로 열지 않았는지 확인한다. 인증 토큰을 다루는 API라 아무 페이지나
    사용자의 브라우저를 통해 호출하게 둘 이유가 없다."""
    res = _preflight(client, "https://evil.example.com")
    assert res.headers.get("access-control-allow-origin") != "https://evil.example.com"
    assert res.headers.get("access-control-allow-origin") != "*"


def test_actual_request_carries_the_origin_header(client):
    """preflight만 통과하고 본 요청에 헤더가 없으면 브라우저가 응답을 버린다."""
    res = client.get("/health", headers={"Origin": DEV_ORIGIN})
    assert res.status_code == 200
    assert res.headers["access-control-allow-origin"] == DEV_ORIGIN
