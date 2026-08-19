"""
/my-recipes와 "추천 N회 이상이면 다른 사람에게도 보인다" 규칙을 검증한다.

이 기능은 V2에서 가져온 뒤 V3에서 한 번도 테스트된 적이 없었다(2026-08-19에 확인).
화면을 붙이기 전에 먼저 덮는다 - 특히 등록한 레시피가 알레르기 태그를 제대로 받는지는
이 앱에서 가장 위험한 실패 지점이라 반드시 고정해야 한다.
"""

import pytest
from helpers import signup_body

from src.agents import recommendation_agent


def _signup(client, username: str) -> tuple[int, dict]:
    res = client.post("/auth/signup", json=signup_body(username))
    data = res.json()
    return data["user_id"], {"Authorization": f"Bearer {data['token']}"}


def _submit(client, user_id, headers, **overrides):
    body = {
        "menu_name": "테스트김치찌개",
        "category": "국&찌개",
        "calorie": 250.0,
        "ingredients_text": "돼지고기 100g\n김치 200g\n두부 100g",
        "steps_text": "재료를 썬다\n끓인다",
    }
    body.update(overrides)
    return client.post("/my-recipes", params={"user_id": user_id}, json=body, headers=headers)


def test_submitting_a_new_name_is_published_immediately(client):
    user_id, headers = _signup(client, "u_recipe_1")

    res = _submit(client, user_id, headers)

    assert res.status_code == 200
    assert res.json()["status"] == "approved"


def test_submitting_a_duplicate_name_waits_for_an_admin(client):
    # 같은 이름이 이미 있으면 조용히 덮어쓰거나 나란히 공개하지 않고 승인 대기로 둔다.
    # 공공데이터 레시피와 이름이 겹치는 글이 검증 없이 섞이면 어느 쪽을 보는지 알 수 없다.
    user_id, headers = _signup(client, "u_recipe_2")

    res = _submit(client, user_id, headers, menu_name="두부조림")

    assert res.json()["status"] == "pending"


def test_my_recipes_lists_what_i_submitted_with_its_status(client):
    user_id, headers = _signup(client, "u_recipe_3")
    _submit(client, user_id, headers, menu_name="내가만든볶음밥")

    res = client.get("/my-recipes", params={"user_id": user_id}, headers=headers)

    assert res.status_code == 200
    items = res.json()
    assert [i["menu_name"] for i in items] == ["내가만든볶음밥"]
    # 등록 직후에는 추천이 0이다. 이 값이 승격 여부를 정하므로 화면에 그대로 보여준다.
    assert items[0] == {
        "id": items[0]["id"], "menu_name": "내가만든볶음밥", "category": "국&찌개",
        "calorie": 250.0, "status": "approved", "like_count": 0,
    }


def test_i_cannot_read_or_delete_someone_elses_recipe(client):
    owner_id, owner_headers = _signup(client, "u_recipe_4")
    submitted = _submit(client, owner_id, owner_headers, menu_name="남의레시피").json()
    other_id, other_headers = _signup(client, "u_recipe_5")

    recipe_id = submitted["recipe_id"]
    detail = client.get(
        f"/my-recipes/{recipe_id}", params={"user_id": other_id}, headers=other_headers
    )
    deleted = client.delete(
        f"/my-recipes/{recipe_id}", params={"user_id": other_id}, headers=other_headers
    )

    assert detail.status_code == 404
    assert deleted.status_code == 404
    # 남의 요청이 실패했다고 원본까지 사라지면 안 된다.
    still_there = client.get(
        f"/my-recipes/{recipe_id}", params={"user_id": owner_id}, headers=owner_headers
    )
    assert still_there.status_code == 200


def test_editing_keeps_the_recipe_id_so_recommendations_survive(client):
    # 지우고 다시 넣으면 쌓인 추천이 0으로 돌아가 승격이 풀린다.
    user_id, headers = _signup(client, "u_recipe_6")
    recipe_id = _submit(client, user_id, headers, menu_name="수정전이름").json()["recipe_id"]

    res = client.put(
        f"/my-recipes/{recipe_id}",
        params={"user_id": user_id},
        json={
            "menu_name": "수정후이름", "category": "반찬", "calorie": 300.0,
            "ingredients_text": "감자 200g", "steps_text": "굽는다",
        },
        headers=headers,
    )

    assert res.status_code == 200
    assert res.json()["recipe_id"] == recipe_id
    detail = client.get(f"/my-recipes/{recipe_id}", params={"user_id": user_id}, headers=headers)
    assert detail.json()["menu_name"] == "수정후이름"


def test_a_submitted_recipe_gets_allergy_tags_from_its_ingredient_text(client, db_conn):
    # 알레르기 태그가 안 붙으면 그 레시피만 필터를 그냥 통과한다. 사용자는 걸렀다고 믿는데
    # 실제로는 안 걸리는, 이 앱에서 가장 위험한 상태다.
    user_id, headers = _signup(client, "u_recipe_7")

    recipe_id = _submit(
        client, user_id, headers,
        menu_name="계란말이테스트", ingredients_text="계란 3개\n우유 50ml\n소금 약간",
    ).json()["recipe_id"]

    cur = db_conn.cursor()
    cur.execute(
        "SELECT tag_value FROM recipe_tags WHERE recipe_id = ? AND tag_type = 'allergy'",
        (recipe_id,),
    )
    # 붙는 값은 사용자가 쓴 표기 그대로다("계란"). 공공데이터도 표기가 갈려 있어서,
    # 거르는 쪽이 동의어를 묶는다 - 아래 테스트가 그 연결을 확인한다.
    assert {row[0] for row in cur.fetchall()} == {"계란", "우유"}


def test_a_submitted_recipe_is_excluded_by_the_allergy_filter(client, db_conn):
    """등록 레시피가 필터를 그냥 통과하면, 유저 레시피 기능이 안전장치에 구멍을 낸다."""
    author_id, author_headers = _signup(client, "u_recipe_allergy_author")
    recipe_id = _submit(
        client, author_id, author_headers,
        menu_name="두부계란찜", ingredients_text="두부 200g\n계란 2개",
    ).json()["recipe_id"]

    # 다른 사람에게 보이게 하려면 먼저 기준만큼 추천을 쌓아야 한다.
    for i in range(recommendation_agent.USER_RECIPE_MIN_LIKES):
        voter_id, voter_headers = _signup(client, f"u_recipe_allergy_voter_{i}")
        client.post(
            f"/recommendation/recipes/{recipe_id}/like/toggle",
            params={"user_id": voter_id}, headers=voter_headers,
        )

    def recommended_ids(username, allergy=None):
        user_id, headers = _signup(client, username)
        if allergy:
            db_conn.execute("UPDATE users SET allergy = ? WHERE id = ?", (allergy, user_id))
        res = client.get(
            f"/recommendation/{user_id}", params={"ingredients": ["두부"]}, headers=headers
        )
        return {item["id"] for item in res.json()}

    assert recipe_id in recommended_ids("u_recipe_allergy_none")
    # 프로필에는 "달걀"이라고 저장돼 있고 레시피 태그는 "계란"이다. 동의어를 안 묶으면
    # 이 사람은 계란이 든 메뉴를 추천받는다.
    assert recipe_id not in recommended_ids("u_recipe_allergy_egg", allergy="달걀")


def test_a_user_recipe_stays_hidden_until_enough_people_recommend_it(client, db_conn):
    """승격 기준이 이 규칙의 전부다. 숫자를 바꿔도 동작이 따라오는지 함께 확인한다."""
    author_id, author_headers = _signup(client, "u_recipe_8")
    # 메뉴명에 "두부"를 넣어 추천 자격(core_ingredients) 판단을 시드 레시피와 같게 만든다.
    recipe_id = _submit(
        client, author_id, author_headers,
        menu_name="두부스테이크", ingredients_text="두부 300g",
    ).json()["recipe_id"]

    def recommended_ids(user_id, headers):
        res = client.get(
            f"/recommendation/{user_id}", params={"ingredients": ["두부"]}, headers=headers
        )
        assert res.status_code == 200
        return {item["id"] for item in res.json()}

    viewer_id, viewer_headers = _signup(client, "u_recipe_9")
    assert recipe_id not in recommended_ids(viewer_id, viewer_headers)

    # 기준보다 하나 모자란 만큼 추천을 쌓아도 아직 안 보인다.
    voters = [
        _signup(client, f"u_recipe_voter_{i}")
        for i in range(recommendation_agent.USER_RECIPE_MIN_LIKES)
    ]
    for voter_id, voter_headers in voters[:-1]:
        client.post(
            f"/recommendation/recipes/{recipe_id}/like/toggle",
            params={"user_id": voter_id}, headers=voter_headers,
        )
    assert recipe_id not in recommended_ids(viewer_id, viewer_headers)

    last_id, last_headers = voters[-1]
    client.post(
        f"/recommendation/recipes/{recipe_id}/like/toggle",
        params={"user_id": last_id}, headers=last_headers,
    )
    assert recipe_id in recommended_ids(viewer_id, viewer_headers)


@pytest.mark.parametrize("method,path", [("get", ""), ("post", ""), ("get", "/1"), ("delete", "/1")])
def test_my_recipes_requires_a_token(client, method, path):
    res = client.request(method, f"/my-recipes{path}", params={"user_id": 1}, json={})
    assert res.status_code == 401
