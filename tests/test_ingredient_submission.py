"""
/ingredient-submissions를 검증한다.

식품영양성분 DB(30만 건)에 없는 재료를 사용자가 직접 채워 넣는 기능이다. 이것도 V2에서
가져온 뒤 V3에서 테스트가 없었다(2026-08-19에 확인).
"""

import pytest
from helpers import signup_body


def _signup(client, username: str) -> tuple[int, dict]:
    res = client.post("/auth/signup", json=signup_body(username))
    data = res.json()
    return data["user_id"], {"Authorization": f"Bearer {data['token']}"}


def _submit(client, user_id, headers, **overrides):
    body = {
        "ingredient_name": "직접만든고추장",
        "calorie": 180.0, "carbs_g": 40.0, "protein_g": 5.0,
        "fat_g": 1.0, "sodium_mg": 2000.0, "price_per_100g": 900.0,
    }
    body.update(overrides)
    return client.post(
        "/ingredient-submissions", params={"user_id": user_id}, json=body, headers=headers
    )


def test_a_new_ingredient_is_accepted_immediately(client):
    user_id, headers = _signup(client, "u_sub_1")

    res = _submit(client, user_id, headers)

    assert res.status_code == 200
    assert res.json()["status"] == "approved"


def test_an_ingredient_the_official_db_already_has_waits_for_an_admin(client):
    # seed의 ingredient_catalog에 "두부"가 있다. 공식 값이 있는데 사용자가 적은 값으로
    # 덮으면 다른 사람의 영양 계산까지 바뀐다.
    user_id, headers = _signup(client, "u_sub_2")

    res = _submit(client, user_id, headers, ingredient_name="두부")

    assert res.json()["status"] == "pending"


def test_a_name_someone_else_already_registered_waits_too(client):
    first_id, first_headers = _signup(client, "u_sub_3")
    _submit(client, first_id, first_headers, ingredient_name="할머니된장")
    second_id, second_headers = _signup(client, "u_sub_4")

    res = _submit(client, second_id, second_headers, ingredient_name="할머니된장")

    assert res.json()["status"] == "pending"


def test_my_submissions_lists_only_mine(client):
    mine_id, mine_headers = _signup(client, "u_sub_5")
    other_id, other_headers = _signup(client, "u_sub_6")
    _submit(client, mine_id, mine_headers, ingredient_name="내가등록한재료")
    _submit(client, other_id, other_headers, ingredient_name="남이등록한재료")

    res = client.get("/ingredient-submissions", params={"user_id": mine_id}, headers=mine_headers)

    assert res.status_code == 200
    assert [i["ingredient_name"] for i in res.json()] == ["내가등록한재료"]


def test_i_cannot_read_or_edit_someone_elses_submission(client, db_conn):
    owner_id, owner_headers = _signup(client, "u_sub_7")
    _submit(client, owner_id, owner_headers, ingredient_name="남의재료")
    cur = db_conn.cursor()
    cur.execute("SELECT id FROM ingredient_submissions WHERE ingredient_name = '남의재료'")
    submission_id = cur.fetchone()[0]

    other_id, other_headers = _signup(client, "u_sub_8")
    detail = client.get(
        f"/ingredient-submissions/{submission_id}",
        params={"user_id": other_id}, headers=other_headers,
    )
    edited = client.put(
        f"/ingredient-submissions/{submission_id}",
        params={"user_id": other_id},
        json={"ingredient_name": "가로챈이름", "calorie": 1.0},
        headers=other_headers,
    )

    assert detail.status_code == 404
    assert edited.status_code == 404
    cur.execute("SELECT ingredient_name FROM ingredient_submissions WHERE id = ?", (submission_id,))
    assert cur.fetchone()[0] == "남의재료"


def test_editing_my_submission_sends_it_back_for_review(client, db_conn):
    # 승인된 뒤에 내용을 바꾸면 검토를 다시 받아야 한다. 안 그러면 승인 딱지만 남기고
    # 값을 마음대로 바꿀 수 있다.
    user_id, headers = _signup(client, "u_sub_9")
    _submit(client, user_id, headers, ingredient_name="수제간장")
    cur = db_conn.cursor()
    cur.execute("SELECT id FROM ingredient_submissions WHERE ingredient_name = '수제간장'")
    submission_id = cur.fetchone()[0]

    res = client.put(
        f"/ingredient-submissions/{submission_id}",
        params={"user_id": user_id},
        json={"ingredient_name": "두부", "calorie": 90.0},
        headers=headers,
    )

    assert res.status_code == 200
    assert res.json()["status"] == "pending"


@pytest.mark.parametrize("method,path", [("get", ""), ("post", ""), ("get", "/1"), ("put", "/1")])
def test_ingredient_submissions_require_a_token(client, method, path):
    res = client.request(
        method, f"/ingredient-submissions{path}",
        params={"user_id": 1}, json={"ingredient_name": "x"},
    )
    assert res.status_code == 401


@pytest.mark.parametrize(
    "field,value",
    [("ingredient_name", "가" * 41), ("ingredient_name", ""), ("calorie", -1), ("carbs_g", 101)],
)
def test_submission_limits_are_enforced_by_the_server(client, field, value):
    """영양값은 100g 기준이라 상한이 명확하다 - g 단위 성분이 100을 넘을 수 없다."""
    user_id, headers = _signup(client, f"u_sub_limit_{field}_{len(str(value))}")

    res = _submit(client, user_id, headers, **{field: value})

    assert res.status_code == 422
