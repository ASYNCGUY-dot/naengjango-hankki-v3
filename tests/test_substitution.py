"""
/recommendation/recipes/{id}/substitution을 검증한다.

특히 이번에 substitution_agent.py의 SUBSTITUTES 딕셔너리에 새로 추가한 항목(파프리카/피망 등,
"아쉬운 점" 리포트에서 지적했던 대체재 커버리지 부족을 보완한 것)이 실제로 라우터 응답까지
이어지는지 확인한다. seed.sql의 "파프리카볶음"(재료 태그: 파프리카 1개)을 기준으로 쓴다.
"""

RECIPE_TOFU = 1        # "두부조림" (재료: 두부, 양파)
RECIPE_PAPRIKA = 3      # "파프리카볶음" (재료: 파프리카)


def _signup(client, username: str) -> tuple[int, dict]:
    res = client.post("/auth/signup", json={"username": username, "password": "pw123456"})
    data = res.json()
    return data["user_id"], {"Authorization": f"Bearer {data['token']}"}


def _add_pantry(client, user_id: int, headers: dict, name: str):
    client.post(f"/pantry/{user_id}", json={"name": name, "expiry_date": None}, headers=headers)


def test_substitution_without_token_returns_401(client):
    res = client.get(f"/recommendation/recipes/{RECIPE_TOFU}/substitution", params={"user_id": 999999999})
    assert res.status_code == 401


def test_substitution_nonexistent_recipe_returns_404(client):
    user_id, headers = _signup(client, "u_subst_1")
    res = client.get("/recommendation/recipes/999999/substitution", params={"user_id": user_id}, headers=headers)
    assert res.status_code == 404


def test_coverage_reflects_owned_ingredients(client):
    user_id, headers = _signup(client, "u_subst_2")
    _add_pantry(client, user_id, headers, "두부")

    res = client.get(f"/recommendation/recipes/{RECIPE_TOFU}/substitution", params={"user_id": user_id}, headers=headers)
    assert res.status_code == 200
    coverage = res.json()["coverage"]
    assert coverage == {"total": 2, "matched": 1, "missing": 1, "coverage_pct": 50}


def test_missing_ingredient_suggests_new_substitution_entry(client):
    # 파프리카를 안 갖고 있으면, 새로 추가한 "파프리카 -> 피망" 항목이 후보로 나와야 한다.
    user_id, headers = _signup(client, "u_subst_3")
    res = client.get(f"/recommendation/recipes/{RECIPE_PAPRIKA}/substitution", params={"user_id": user_id}, headers=headers)
    assert res.status_code == 200
    missing = res.json()["missing_ingredients"]
    assert len(missing) == 1
    assert missing[0]["ingredient"] == "파프리카"
    assert missing[0]["type"] == "substitute"
    assert "피망" in missing[0]["suggestion"]


def test_missing_ingredient_points_to_owned_substitute(client):
    # 유저가 대체재(피망)를 이미 갖고 있으면, "이미 갖고 계신 피망으로 대체하세요" 식으로
    # 더 구체적인 안내가 나와야 한다(substitution_agent.py #80 개정 로직).
    user_id, headers = _signup(client, "u_subst_4")
    _add_pantry(client, user_id, headers, "피망")

    res = client.get(f"/recommendation/recipes/{RECIPE_PAPRIKA}/substitution", params={"user_id": user_id}, headers=headers)
    assert res.status_code == 200
    missing = res.json()["missing_ingredients"]
    assert "이미 갖고 계신 피망" in missing[0]["suggestion"]
