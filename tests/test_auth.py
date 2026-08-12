"""
/auth/signup, /auth/login, 그리고 오늘 추가한 로그인 시도 횟수 제한(api/routers/auth.py)을 검증한다.

주의: _failed_login_attempts는 auth.py 모듈 레벨의 인메모리 dict라서 테스트 프로세스
전체에서 공유된다(DB 롤백과 무관). 그래서 각 테스트는 매번 새 아이디를 써서 서로의
실패 카운트에 영향을 주지 않게 한다.
"""

from api.routers import auth as auth_router


def test_signup_then_login_succeeds(client):
    signup_res = client.post("/auth/signup", json={"username": "u_auth_1", "password": "pw123456"})
    assert signup_res.status_code == 200
    user_id = signup_res.json()["user_id"]
    assert signup_res.json()["token"]  # 가입 즉시 토큰이 발급돼야 한다 (#63)

    login_res = client.post("/auth/login", json={"username": "u_auth_1", "password": "pw123456"})
    assert login_res.status_code == 200
    assert login_res.json()["user_id"] == user_id
    assert login_res.json()["token"]


def test_token_authorizes_own_data_and_rejects_others(client):
    """토큰 인가(#63)의 핵심 계약: 토큰 없으면 401, 남의 user_id면 403, 본인이면 200."""
    a = client.post("/auth/signup", json={"username": "u_authz_a", "password": "pw123456"}).json()
    b = client.post("/auth/signup", json={"username": "u_authz_b", "password": "pw123456"}).json()
    headers_a = {"Authorization": f"Bearer {a['token']}"}

    no_token = client.get(f"/profile/{a['user_id']}")
    assert no_token.status_code == 401

    bad_token = client.get(f"/profile/{a['user_id']}", headers={"Authorization": "Bearer not-a-real-token"})
    assert bad_token.status_code == 401

    other_user = client.get(f"/profile/{b['user_id']}", headers=headers_a)
    assert other_user.status_code == 403

    own = client.get(f"/profile/{a['user_id']}", headers=headers_a)
    assert own.status_code == 200


def test_logout_revokes_token(client):
    data = client.post("/auth/signup", json={"username": "u_logout_1", "password": "pw123456"}).json()
    headers = {"Authorization": f"Bearer {data['token']}"}

    assert client.get(f"/profile/{data['user_id']}", headers=headers).status_code == 200

    logout_res = client.post("/auth/logout", headers=headers)
    assert logout_res.status_code == 200

    # 폐기된 토큰으로는 더 이상 접근할 수 없어야 한다
    assert client.get(f"/profile/{data['user_id']}", headers=headers).status_code == 401


def test_duplicate_signup_returns_409(client):
    client.post("/auth/signup", json={"username": "u_auth_2", "password": "pw123456"})
    res = client.post("/auth/signup", json={"username": "u_auth_2", "password": "differentpw123"})
    assert res.status_code == 409


def test_signup_with_short_password_returns_422(client):
    res = client.post("/auth/signup", json={"username": "u_auth_shortpw", "password": "abc123"})
    assert res.status_code == 422

    # 짧은 비밀번호로 거부된 아이디는 실제로 생성되지 않아야 한다 - 이후 정상 비밀번호로 가입 가능
    retry_res = client.post("/auth/signup", json={"username": "u_auth_shortpw", "password": "abc123456"})
    assert retry_res.status_code == 200


def test_wrong_password_returns_401(client):
    client.post("/auth/signup", json={"username": "u_auth_3", "password": "correct123"})
    res = client.post("/auth/login", json={"username": "u_auth_3", "password": "wrong"})
    assert res.status_code == 401


def test_login_nonexistent_user_returns_401(client):
    res = client.post("/auth/login", json={"username": "u_auth_never_existed", "password": "x"})
    assert res.status_code == 401


def test_login_lockout_after_max_failed_attempts(client):
    username = "u_auth_lockout_1"
    client.post("/auth/signup", json={"username": username, "password": "correct123"})

    for _ in range(auth_router.MAX_LOGIN_ATTEMPTS):
        res = client.post("/auth/login", json={"username": username, "password": "wrong"})
        assert res.status_code == 401

    locked_res = client.post("/auth/login", json={"username": username, "password": "wrong"})
    assert locked_res.status_code == 429

    # 잠긴 상태에서는 올바른 비밀번호로도 막혀야 한다
    locked_with_correct = client.post("/auth/login", json={"username": username, "password": "correct123"})
    assert locked_with_correct.status_code == 429

    auth_router._clear_failed_logins(username)


def test_successful_login_resets_failed_attempt_counter(client):
    username = "u_auth_reset_1"
    client.post("/auth/signup", json={"username": username, "password": "correct123"})

    client.post("/auth/login", json={"username": username, "password": "wrong"})
    client.post("/auth/login", json={"username": username, "password": "wrong"})
    ok_res = client.post("/auth/login", json={"username": username, "password": "correct123"})
    assert ok_res.status_code == 200

    for _ in range(auth_router.MAX_LOGIN_ATTEMPTS - 1):
        res = client.post("/auth/login", json={"username": username, "password": "wrong"})
        assert res.status_code == 401  # 리셋됐으므로 아직 잠기면 안 된다

    auth_router._clear_failed_logins(username)
