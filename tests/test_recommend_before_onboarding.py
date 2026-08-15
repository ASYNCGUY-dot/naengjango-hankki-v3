"""온보딩을 마치지 않은 계정도 추천을 받을 수 있어야 한다 (2026-08-13).

V3에서 가입 항목이 늘면서 흐름이 바뀌었다. 예전에는 프로필을 만들 때 알레르기 등에
항상 값이 들어갔는데, 지금은 가입만 하고 온보딩을 안 한 상태가 정상적으로 존재한다.
그 상태에서 users.allergy는 NULL이다.

get_candidate_recipes가 profile.get("allergy", "")로 읽고 있었다. .get(키, 기본값)은
키가 없을 때만 기본값을 주므로 값이 NULL이면 None이 그대로 나오고 .split()에서 터진다.
실제 DB로 태워보다 발견했다 - 지인 5명이 전원 첫 추천에서 만났을 버그다.
"""

from helpers import signup_body


def _signup(client, username):
    res = client.post("/auth/signup", json=signup_body(username))
    assert res.status_code == 200
    data = res.json()
    return data["user_id"], {"Authorization": f"Bearer {data['token']}"}


def test_recommend_works_right_after_signup(client):
    """가입 직후(온보딩 전)에 추천을 부르면 500이 나면 안 된다."""
    user_id, headers = _signup(client, "u_reco_fresh")

    res = client.get(
        f"/recommendation/{user_id}",
        params={"ingredients": ["두부", "양파"]},
        headers=headers,
    )
    assert res.status_code == 200, res.text
    assert isinstance(res.json(), list)


def test_recommend_works_when_allergy_is_null(client, db_conn):
    """알레르기를 비워둔 계정도 마찬가지다. 컬럼이 NULL인 것과 빈 문자열인 것은 다르다."""
    user_id, headers = _signup(client, "u_reco_nullallergy")
    db_conn.execute("UPDATE users SET allergy = NULL WHERE id = ?", (user_id,))

    res = client.get(
        f"/recommendation/{user_id}", params={"ingredients": ["두부"]}, headers=headers
    )
    assert res.status_code == 200, res.text


def test_allergy_filter_still_works_when_set(client, db_conn):
    """None 처리를 넣었다고 알레르기 제외가 동작을 멈추면 안 된다.

    시드에는 알레르기 태그가 없으므로 이 테스트가 직접 붙인다 - 시드 내용이 바뀌어도
    이 검증은 그대로 성립한다.
    """
    user_id, headers = _signup(client, "u_reco_withallergy")

    before = client.get(
        f"/recommendation/{user_id}", params={"ingredients": ["두부"], "limit": 50}, headers=headers
    ).json()
    assert before, "비교할 후보가 있어야 의미가 있다"
    target_id = before[0]["id"]

    db_conn.execute(
        "INSERT INTO recipe_tags (recipe_id, tag_type, tag_value) VALUES (?, 'allergy', '대두')",
        (target_id,),
    )
    db_conn.execute("UPDATE users SET allergy = '대두' WHERE id = ?", (user_id,))

    after = client.get(
        f"/recommendation/{user_id}", params={"ingredients": ["두부"], "limit": 50}, headers=headers
    ).json()

    assert target_id not in [item["id"] for item in after], "알레르기가 걸린 레시피가 그대로 나온다"
    assert len(after) == len(before) - 1
