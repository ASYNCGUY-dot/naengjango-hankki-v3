"""/profile/{user_id} GET·POST·PUT를 검증한다 - 로그인 후 온보딩 완료 여부 판단에 쓰이는 핵심 경로."""

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
    res = client.post("/auth/signup", json={"username": username, "password": "pw123456"})
    data = res.json()
    return data["user_id"], {"Authorization": f"Bearer {data['token']}"}


def test_get_profile_before_completion_has_profile_false(client):
    user_id, headers = _signup(client, "u_profile_1")
    res = client.get(f"/profile/{user_id}", headers=headers)
    assert res.status_code == 200
    assert res.json()["has_profile"] is False


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
