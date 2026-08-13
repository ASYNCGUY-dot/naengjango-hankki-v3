"""레시피 상세가 인가 없이도 쓸 만한지 검증한다 (2026-08-13).

재료를 주는 엔드포인트는 인가가 필요했다 - 가구원 수에 맞춰 환산하느라 프로필을 읽기
때문이다. 그러면 레시피 링크를 공유받은 사람이 재료를 못 본다. 재료 없는 레시피는
레시피가 아니고, 링크 공유가 되는 것이 React 전환의 핵심 이득이었다.

그래서 상세 응답에 환산하지 않은 원본 재료를 함께 담는다. 가구원 수 환산은 개인화라
인가가 필요한 엔드포인트에 그대로 남는다.
"""


def test_detail_includes_ingredients_without_login(client):
    res = client.get("/recommendation/recipes/1")
    assert res.status_code == 200
    body = res.json()
    assert body["menu_name"]
    assert body["ingredients"], "재료 없이는 레시피 화면이 성립하지 않는다"
    first = body["ingredients"][0]
    assert set(first) == {"name", "amount", "unit"}


def test_detail_reports_base_servings(client):
    """수량이 몇 인분 기준인지 알아야 화면이 "2인분 기준"이라고 적을 수 있다."""
    res = client.get("/recommendation/recipes/1")
    assert res.json()["base_servings"] is not None


def test_scaled_ingredients_still_require_login(client):
    """개인화된 환산은 인가가 필요한 자리에 그대로 남아야 한다."""
    res = client.get("/recommendation/recipes/1/ingredients", params={"user_id": 1})
    assert res.status_code == 401


def test_unknown_recipe_returns_404(client):
    # 잘못된 링크를 받아도 빈 화면이 아니라 "없는 레시피"라고 알 수 있어야 한다.
    res = client.get("/recommendation/recipes/999999")
    assert res.status_code == 404


def test_detail_has_no_ingredients_does_not_break(client, db_conn):
    """재료가 등록되지 않은 레시피도 상세는 열려야 한다."""
    cur = db_conn.execute(
        "INSERT INTO recipes (menu_name, category, source_api, status) "
        "VALUES ('재료없는레시피', '기타', 'test', 'approved')"
    )
    recipe_id = cur.lastrowid

    res = client.get(f"/recommendation/recipes/{recipe_id}")
    assert res.status_code == 200
    assert res.json()["ingredients"] == []
