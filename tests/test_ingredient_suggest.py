"""냉장고 입력창의 자동완성을 검증한다 (2026-08-18).

왜 만들었나
재료를 손으로 치게 두면 "돼지 고기"처럼 어느 레시피 태그와도 안 맞는 값이 들어간다.
그러면 추천이 나빠지는데, 지인 테스트에서 "추천이 별로다"라는 말이 나와도 **알고리즘
문제인지 입력 문제인지 갈라낼 수 없다.** Phase 4가 알아내려는 것이 바로 그것이라
측정 도구가 오염된 채로 시작하는 셈이 된다.

그래서 제안 목록을 영양 카탈로그(30만 건)가 아니라 **레시피 태그**에서 뽑는다.
추천이 실제로 비교하는 대상이 그것이므로, 여기서 고른 이름은 반드시 어딘가에 매칭된다.
"""


def _suggest(client, keyword, **params):
    res = client.get("/pantry/suggest", params={"keyword": keyword, **params})
    assert res.status_code == 200, res.text
    return res.json()


def test_no_login_required(client):
    # 재료 이름은 개인 정보가 아니다. 로그인 전 데모에서도 쓸 수 있어야 한다.
    assert client.get("/pantry/suggest", params={"keyword": "두부"}).status_code == 200


def test_empty_keyword_returns_nothing(client):
    # 빈 검색어로 1,762종을 다 내려보내면 첫 타자가 치기도 전에 목록이 열린다.
    assert _suggest(client, "") == []


def test_suggests_names_the_recommender_actually_matches(client, db_conn):
    """이게 이 기능의 존재 이유다. 고른 이름이 추천에서 매칭돼야 한다."""
    db_conn.execute(
        "INSERT INTO recipe_tags (recipe_id, tag_type, tag_value) VALUES (1, 'ingredient', '두부')"
    )
    names = [item["name"] for item in _suggest(client, "두부")]
    assert "두부" in names


def test_more_used_ingredients_come_first(client, db_conn):
    # "두"를 치면 118개 레시피에 쓰인 "두부"가 먼저 나와야지, 하나에만 쓰인 "두부면"이
    # 먼저 나오면 안 된다.
    db_conn.execute(
        "INSERT INTO recipes (id, menu_name, category, calorie, status) "
        "VALUES (9950, '두번째', '반찬', 100, 'approved')"
    )
    for recipe_id in (1, 9950):
        db_conn.execute(
            "INSERT INTO recipe_tags (recipe_id, tag_type, tag_value) VALUES (?, 'ingredient', '흔한재료')",
            (recipe_id,),
        )
    db_conn.execute(
        "INSERT INTO recipe_tags (recipe_id, tag_type, tag_value) VALUES (1, 'ingredient', '흔한재료가공')"
    )

    names = [item["name"] for item in _suggest(client, "흔한재료")]
    assert names.index("흔한재료") < names.index("흔한재료가공")


def test_reports_how_many_recipes_use_it(client, db_conn):
    # 어느 표기를 골라야 추천이 잘 되는지 사용자가 알 수 있어야 한다.
    db_conn.execute(
        "INSERT INTO recipe_tags (recipe_id, tag_type, tag_value) VALUES (1, 'ingredient', '개수확인재료')"
    )
    items = _suggest(client, "개수확인재료")
    assert items[0]["recipe_count"] == 1


def test_noise_markers_are_not_suggested(client, db_conn):
    """원본에 "• [추가 재료] 쌈두부"처럼 표기가 섞인 태그가 있다.

    그대로 제안하면 사용자가 그 이름을 저장하게 되고, 그건 어느 레시피와도 안 맞는다.
    """
    db_conn.execute(
        "INSERT INTO recipe_tags (recipe_id, tag_type, tag_value) "
        "VALUES (1, 'ingredient', '• [추가 재료] 잡음재료')"
    )
    assert _suggest(client, "잡음재료") == []


def test_section_titles_are_not_suggested(client, db_conn):
    # "주재료"는 재료가 아니라 구획 제목이다. 냉장고에 넣을 것이 아니다.
    db_conn.execute(
        "INSERT INTO recipe_tags (recipe_id, tag_type, tag_value) VALUES (1, 'ingredient', '주재료')"
    )
    assert "주재료" not in [item["name"] for item in _suggest(client, "주재료")]


def test_limit_is_respected(client):
    assert len(_suggest(client, "", limit=3)) <= 3
