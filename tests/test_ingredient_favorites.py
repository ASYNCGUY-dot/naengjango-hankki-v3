"""
/ingredients/search, /ingredients/{user_id}/{food_code}/toggle, /ingredients/{user_id}/favorites를
검증한다 - 오늘 프론트엔드를 새로 연결한 재료 즐겨찾기 기능.
"""


def _signup(client, username: str) -> tuple[int, dict]:
    res = client.post("/auth/signup", json={"username": username, "password": "pw123456"})
    data = res.json()
    return data["user_id"], {"Authorization": f"Bearer {data['token']}"}


def _first_food_code(client) -> str:
    res = client.get("/ingredients/search", params={"keyword": "두부", "limit": 1})
    assert res.status_code == 200
    items = res.json()["items"]
    assert len(items) > 0, "테스트 DB의 ingredient_catalog에 '두부' 검색 결과가 없습니다."
    return items[0]["food_code"]


def test_search_ingredients_returns_results(client):
    # 검색은 특정 유저의 데이터가 아니므로 토큰 없이 공개다
    res = client.get("/ingredients/search", params={"keyword": "두부", "limit": 5})
    assert res.status_code == 200
    body = res.json()
    assert body["total"] > 0
    assert len(body["items"]) > 0
    assert "food_code" in body["items"][0]


def test_search_ingredients_prefers_raw_over_variants_even_when_uncurated(client):
    # "고사리"는 COMMON_INGREDIENT_NAMES 큐레이션 목록에 없다(2026-07-21, "3번 설정을
    # 모든 재료에 적용해줘") - 가나다순이면 "고사리_데친것"이 "고사리_생것"보다 먼저 나오지만
    # (ㄷ<ㅅ), 변형 우선순위 정렬이 일반화됐다면 "_생것"이 먼저 나와야 한다.
    res = client.get("/ingredients/search", params={"keyword": "고사리", "limit": 10})
    assert res.status_code == 200
    names = [i["name"] for i in res.json()["items"]]
    assert names.index("고사리_생것") < names.index("고사리_데친것")
    assert names.index("고사리_생것") < names.index("고사리_말린것")


def test_favorites_list_empty_before_any_toggle(client):
    user_id, headers = _signup(client, "u_favfood_1")
    res = client.get(f"/ingredients/{user_id}/favorites", headers=headers)
    assert res.status_code == 200
    assert res.json() == []


def test_toggle_favorite_adds_then_removes(client):
    user_id, headers = _signup(client, "u_favfood_2")
    food_code = _first_food_code(client)

    add_res = client.post(f"/ingredients/{user_id}/{food_code}/toggle", headers=headers)
    assert add_res.status_code == 200
    assert add_res.json()["favorited"] is True

    list_res = client.get(f"/ingredients/{user_id}/favorites", headers=headers)
    codes = [item["food_code"] for item in list_res.json()]
    assert food_code in codes

    remove_res = client.post(f"/ingredients/{user_id}/{food_code}/toggle", headers=headers)
    assert remove_res.status_code == 200
    assert remove_res.json()["favorited"] is False

    list_res_after = client.get(f"/ingredients/{user_id}/favorites", headers=headers)
    codes_after = [item["food_code"] for item in list_res_after.json()]
    assert food_code not in codes_after
