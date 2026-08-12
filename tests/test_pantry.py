"""
/pantry/{user_id} GET·POST·PUT·DELETE를 검증한다.

냉장고 화면 개편(2026-07-19)에서 추가한 PUT(유통기한만 수정)이 핵심이고,
기존에 테스트가 없던 pantry 기본 흐름(추가→조회→삭제)도 함께 고정한다.
"""


def _signup(client, username: str) -> tuple[int, dict]:
    res = client.post("/auth/signup", json={"username": username, "password": "pw123456"})
    data = res.json()
    return data["user_id"], {"Authorization": f"Bearer {data['token']}"}


def _add(client, user_id: int, headers: dict, name: str, expiry: str | None = None) -> int:
    res = client.post(f"/pantry/{user_id}", json={"name": name, "expiry_date": expiry}, headers=headers)
    assert res.status_code == 200
    items = client.get(f"/pantry/{user_id}", headers=headers).json()
    return next(i["id"] for i in items if i["name"] == name)


def test_add_then_list_then_remove(client):
    user_id, headers = _signup(client, "u_pantry_1")
    ing_id = _add(client, user_id, headers, "두부")

    items = client.get(f"/pantry/{user_id}", headers=headers).json()
    assert [i["name"] for i in items] == ["두부"]

    res = client.delete(f"/pantry/{user_id}/{ing_id}", headers=headers)
    assert res.status_code == 200
    assert client.get(f"/pantry/{user_id}", headers=headers).json() == []


def test_duplicate_add_updates_expiry_instead_of_duplicating(client):
    # add_pantry_ingredient()는 같은 이름이 있으면 유통기한만 갱신한다(중복 방지)
    user_id, headers = _signup(client, "u_pantry_2")
    _add(client, user_id, headers, "두부")
    _add(client, user_id, headers, "두부", expiry="2026-12-31")

    items = client.get(f"/pantry/{user_id}", headers=headers).json()
    assert len(items) == 1
    assert items[0]["expiry_date"] == "2026-12-31"


def test_update_expiry_only(client):
    user_id, headers = _signup(client, "u_pantry_3")
    ing_id = _add(client, user_id, headers, "계란")

    res = client.put(
        f"/pantry/{user_id}/{ing_id}", json={"expiry_date": "2026-08-01"}, headers=headers
    )
    assert res.status_code == 200
    items = client.get(f"/pantry/{user_id}", headers=headers).json()
    assert items[0]["expiry_date"] == "2026-08-01"

    # 유통기한을 다시 비울 수도 있어야 한다
    res = client.put(f"/pantry/{user_id}/{ing_id}", json={"expiry_date": None}, headers=headers)
    assert res.status_code == 200
    assert client.get(f"/pantry/{user_id}", headers=headers).json()[0]["expiry_date"] is None


def test_update_expiry_of_others_ingredient_returns_404(client):
    owner_id, owner_headers = _signup(client, "u_pantry_4")
    ing_id = _add(client, owner_id, owner_headers, "당근")

    intruder_id, intruder_headers = _signup(client, "u_pantry_5")
    # 남의 user_id 경로는 403, 본인 경로에 남의 ingredient_id를 넣으면 404
    res = client.put(
        f"/pantry/{owner_id}/{ing_id}", json={"expiry_date": "2026-08-01"}, headers=intruder_headers
    )
    assert res.status_code == 403

    res = client.put(
        f"/pantry/{intruder_id}/{ing_id}", json={"expiry_date": "2026-08-01"}, headers=intruder_headers
    )
    assert res.status_code == 404


def test_pantry_without_token_returns_401(client):
    user_id, _ = _signup(client, "u_pantry_6")
    assert client.get(f"/pantry/{user_id}").status_code == 401
