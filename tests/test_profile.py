"""/profile/{user_id} GET·PUT를 검증한다 - 로그인 후 온보딩 완료 여부 판단에 쓰이는 핵심 경로.


POST ""는 V3 Phase 1(2026-08-12)에서 없앴다. 인증 없이 users 행을 새로 만들던
엔드포인트였고, 운영 DB의 빈 계정 34개가 전부 이 경로로 생겼다.
"""

from helpers import signup_body

PROFILE_PAYLOAD = {
    "gender": "여성",
    "age_group": "30대",
    "allergy": "",
    "health_goal": "체중감량",
    "purpose": "자취생 식단관리",
    "cooking_level": "초급",
    "supplements": "없음",
    "household_size": 1,
    "novelty_pref": "새로운 메뉴 선호",
    "cooking_tools": "가스레인지,전자레인지",
    "medical_conditions": "",
}


def _signup(client, username: str) -> tuple[int, dict]:
    """(user_id, 인증 헤더)를 돌려준다 - 토큰 인가(#63) 이후 모든 유저 스코프 요청에 헤더가 필요하다."""
    res = client.post("/auth/signup", json=signup_body(username))
    data = res.json()
    return data["user_id"], {"Authorization": f"Bearer {data['token']}"}


def test_get_profile_before_completion_has_profile_false(client):
    """가입만 하고 온보딩을 안 했으면 has_profile은 False여야 한다.

    가입 단계에서 성별·연령대를 받게 되면서(2026-08-13) 이 판단 기준이 한 번 어긋났다.
    gender로 판단하던 시절에는 가입 직후부터 True가 됐다. 지금은 온보딩에서만 채워지는
    health_goal을 본다.
    """
    user_id, headers = _signup(client, "u_profile_1")
    res = client.get(f"/profile/{user_id}", headers=headers)
    assert res.status_code == 200
    assert res.json()["has_profile"] is False

    # 가입에서 받은 항목은 이미 채워져 있어야 한다 - 온보딩 완료와는 별개다.
    assert res.json()["gender"] == "여성"
    assert res.json()["age_group"] == "20대"


def test_get_profile_without_token_returns_401(client):
    # 토큰 인가(#63) 이후, user_id만 알아서는 남의 프로필을 볼 수 없다 -
    # require_self가 404 확인보다 먼저 돌기 때문에 "존재하지 않는 user_id"도 401/403이 먼저다.
    user_id, _ = _signup(client, "u_profile_noauth")
    res = client.get(f"/profile/{user_id}")
    assert res.status_code == 401


def test_put_then_get_profile_reflects_saved_data(client):
    user_id, headers = _signup(client, "u_profile_2")

    put_res = client.put(f"/profile/{user_id}", json=PROFILE_PAYLOAD, headers=headers)
    assert put_res.status_code == 200
    assert put_res.json() == {"user_id": user_id, "updated": True}

    get_res = client.get(f"/profile/{user_id}", headers=headers)
    assert get_res.status_code == 200
    body = get_res.json()
    assert body["has_profile"] is True
    assert body["gender"] == "여성"
    assert body["health_goal"] == "체중감량"
    assert body["household_size"] == 1


def test_put_profile_missing_required_field_returns_422(client):
    # validate_profile()은 키의 "존재"만 보고(빈 문자열도 존재로 침) - 실제로 422가
    # 나는 건 ProfileRequest(Pydantic)가 이 필드에 기본값이 없어서 요청 자체를 거부하기
    # 때문이다. 그래서 값을 비우는 게 아니라 키 자체를 빼야 한다.
    user_id, headers = _signup(client, "u_profile_3")
    incomplete = {k: v for k, v in PROFILE_PAYLOAD.items() if k != "health_goal"}
    res = client.put(f"/profile/{user_id}", json=incomplete, headers=headers)
    assert res.status_code == 422


def test_put_other_users_profile_returns_403(client):
    _, headers = _signup(client, "u_profile_4")
    res = client.put("/profile/999999999", json=PROFILE_PAYLOAD, headers=headers)
    assert res.status_code == 403


def test_anonymous_profile_creation_is_gone(client, db_conn):
    """인증 없이 계정을 만들 수 있던 경로가 실제로 닫혔는지 확인한다 (V3 Phase 1).

    이 엔드포인트를 지운 것이 users.username NOT NULL의 전제다 - 열려 있으면
    username 없는 행이 계속 생겨서 제약을 걸 수 없다.
    """
    before = db_conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]

    res = client.post("/profile", json=PROFILE_PAYLOAD)
    assert res.status_code != 200

    after = db_conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
    assert after == before, "인증 없는 요청으로 계정이 생기면 안 된다"


def test_profile_says_whether_i_am_an_admin(client, db_conn):
    """마이 화면이 승인 대기 목록 링크를 보여줄지 정하는 데 쓴다.

    화면에서 감추는 것은 편의일 뿐이라, 일반 사용자에게 False가 가는 것 자체보다
    /admin 엔드포인트가 다시 막는 것이 실제 방어선이다(test_admin.py).
    """
    user_id, headers = _signup(client, "u_profile_admin")

    assert client.get(f"/profile/{user_id}", headers=headers).json()["is_admin"] is False

    db_conn.execute("UPDATE users SET is_admin = 1 WHERE id = ?", (user_id,))
    assert client.get(f"/profile/{user_id}", headers=headers).json()["is_admin"] is True
