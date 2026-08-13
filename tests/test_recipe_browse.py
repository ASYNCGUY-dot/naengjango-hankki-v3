"""홈 화면(레시피 둘러보기)이 쓰는 목록 API를 검증한다 (2026-08-13).

시안의 카드는 사진 중심인데 목록 API가 image_url을 주지 않고 있었다. 그대로 두면 화면이
레시피마다 상세를 한 번씩 더 불러야 하고, 카드 20개면 요청 20번이다 - 콜드스타트가 있는
무료 서버에서는 감당이 안 된다.

분류 필터와 페이지 넘기기도 에이전트에는 있는데 라우터가 열어주지 않아 쓸 수 없었다.
"""


def test_search_returns_image_url(client):
    res = client.get("/recommendation/recipes/search", params={"keyword": "두부"})
    assert res.status_code == 200
    items = res.json()
    assert items, "시드에 두부조림이 있어야 한다"
    # 키가 있어야 화면이 사진을 그릴 수 있다. 값이 비어 있는 레시피도 있으므로
    # 존재만 확인한다(1,148개 중 2개는 실제로 비어 있다).
    assert "image_url" in items[0]


def test_search_filters_by_category(client):
    everything = client.get("/recommendation/recipes/search", params={"limit": 100}).json()
    categories = {item["category"] for item in everything if item["category"]}
    assert categories, "시드에 분류가 있어야 한다"

    target = sorted(categories)[0]
    filtered = client.get(
        "/recommendation/recipes/search", params={"category": target, "limit": 100}
    ).json()

    assert filtered, f"{target} 분류에 결과가 있어야 한다"
    assert all(item["category"] == target for item in filtered)
    assert len(filtered) <= len(everything)


def test_category_all_is_not_a_filter(client):
    """화면의 "전체" 칩은 필터를 걸지 않는 상태다. 그 문자열이 분류로 새어 들어가면
    결과가 0개가 된다."""
    everything = client.get("/recommendation/recipes/search", params={"limit": 100}).json()
    with_all = client.get(
        "/recommendation/recipes/search", params={"category": "전체", "limit": 100}
    ).json()
    assert len(with_all) == len(everything)


def test_offset_moves_the_window(client):
    first_page = client.get("/recommendation/recipes/search", params={"limit": 1}).json()
    second_page = client.get(
        "/recommendation/recipes/search", params={"limit": 1, "offset": 1}
    ).json()

    assert len(first_page) == 1
    if second_page:  # 시드 레시피가 2개 이상일 때만 의미가 있다
        assert first_page[0]["id"] != second_page[0]["id"]


def test_categories_endpoint_lists_counts(client):
    res = client.get("/recommendation/recipes/categories")
    assert res.status_code == 200
    items = res.json()
    assert items, "분류 목록이 비면 화면이 칩을 그릴 수 없다"
    for item in items:
        assert item["category"]
        assert item["count"] >= 1
    # 많이 쓰이는 순이라 화면이 그대로 나열하면 된다.
    counts = [item["count"] for item in items]
    assert counts == sorted(counts, reverse=True)


def test_categories_path_is_not_swallowed_by_recipe_id(client):
    """8.2 함정: "/recipes/{recipe_id}"가 먼저 등록되면 "categories"가 그 자리에
    매칭되다 int 변환에 실패해 422가 난다. 실제로 겪었던 문제라 못박아 둔다."""
    res = client.get("/recommendation/recipes/categories")
    assert res.status_code != 422
