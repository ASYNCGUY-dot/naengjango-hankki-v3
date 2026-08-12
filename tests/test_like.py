"""
/recommendation/recipes/{id}/like, /like/toggle, /popular를 검증한다.

seed.sql의 승인된 레시피 3개(1: 두부조림, 2: 재료수량정보없는레시피, 3: 파프리카볶음)를 쓴다.
"""


def _signup(client, username: str) -> tuple[int, dict]:
    res = client.post("/auth/signup", json={"username": username, "password": "pw123456"})
    data = res.json()
    return data["user_id"], {"Authorization": f"Bearer {data['token']}"}


def test_toggle_like_then_status_reflects_it(client):
    user_id, headers = _signup(client, "u_like_1")

    res = client.get(f"/recommendation/recipes/1/like", params={"user_id": user_id}, headers=headers)
    assert res.status_code == 200
    assert res.json() == {"liked": False, "like_count": 0}

    res = client.post(f"/recommendation/recipes/1/like/toggle", params={"user_id": user_id}, headers=headers)
    assert res.status_code == 200
    assert res.json() == {"liked": True, "like_count": 1}

    res = client.get(f"/recommendation/recipes/1/like", params={"user_id": user_id}, headers=headers)
    assert res.json() == {"liked": True, "like_count": 1}

    # 다시 누르면 취소된다
    res = client.post(f"/recommendation/recipes/1/like/toggle", params={"user_id": user_id}, headers=headers)
    assert res.json() == {"liked": False, "like_count": 0}


def test_get_popular_recipes_orders_by_like_count_desc(client):
    # 레시피 3(파프리카볶음)에 좋아요 2개, 레시피 1(두부조림)에 1개, 레시피 2는 0개(좋아요 없음).
    u1, h1 = _signup(client, "u_like_2")
    u2, h2 = _signup(client, "u_like_3")

    client.post("/recommendation/recipes/3/like/toggle", params={"user_id": u1}, headers=h1)
    client.post("/recommendation/recipes/3/like/toggle", params={"user_id": u2}, headers=h2)
    client.post("/recommendation/recipes/1/like/toggle", params={"user_id": u1}, headers=h1)

    res = client.get("/recommendation/recipes/popular")
    assert res.status_code == 200
    items = res.json()

    # 좋아요가 하나도 없는 레시피 2는 목록에 안 나온다 (INNER JOIN)
    ids = [i["id"] for i in items]
    assert 2 not in ids

    by_id = {i["id"]: i for i in items}
    assert by_id[3]["like_count"] == 2
    assert by_id[1]["like_count"] == 1
    # 좋아요 개수 내림차순
    assert ids.index(3) < ids.index(1)
