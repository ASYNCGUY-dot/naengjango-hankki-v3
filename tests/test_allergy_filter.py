"""알레르기 제외가 실제로 걸러내는지 검증한다 (2026-08-13).

운영 데이터를 보다 두 가지를 발견했다.

1) recipe_tags에 같은 것을 가리키는 태그가 둘씩 있다. 원본 공공데이터의 표기가 통일돼
   있지 않아서다 - "달걀" 200개 / "계란" 27개, "소고기" 71개 / "쇠고기" 47개. 제외는
   정확 일치로 비교하므로, "달걀"만 저장된 사용자에게 "계란" 태그가 붙은 27개가 그대로
   추천됐다. 알레르기가 있는 사람에게는 위험한 누락이다.

2) 기존 users.allergy가 자유 입력이라 "콩"(태그는 "대두"), "@$#$" 같은 값이 들어 있다.
   고르긴 골랐는데 아무것도 안 걸러지고, 본인은 걸러졌다고 믿는 상태가 된다.
   그래서 온보딩은 실제 태그에서 만든 목록으로만 고르게 한다.
"""

from helpers import signup_body
from src.agents.recommendation_agent import expand_allergies


def _signup(client, username):
    res = client.post("/auth/signup", json=signup_body(username))
    assert res.status_code == 200
    data = res.json()
    return data["user_id"], {"Authorization": f"Bearer {data['token']}"}


def _tag(db_conn, recipe_id, value):
    db_conn.execute(
        "INSERT INTO recipe_tags (recipe_id, tag_type, tag_value) VALUES (?, 'allergy', ?)",
        (recipe_id, value),
    )


def _recommend_ids(client, user_id, headers):
    res = client.get(
        f"/recommendation/{user_id}",
        params={"ingredients": ["두부"], "limit": 50},
        headers=headers,
    )
    assert res.status_code == 200, res.text
    return [item["id"] for item in res.json()]


class TestExpandAllergies:
    def test_empty_input_is_empty_set(self):
        # 가입만 하고 온보딩을 안 한 상태가 정상적으로 존재한다.
        assert expand_allergies(None) == set()
        assert expand_allergies("") == set()
        assert expand_allergies(" , ") == set()

    def test_synonyms_are_added(self):
        assert expand_allergies("달걀") == {"달걀", "계란"}
        assert expand_allergies("계란") == {"달걀", "계란"}
        assert expand_allergies("소고기") == {"소고기", "쇠고기"}

    def test_unrelated_values_pass_through(self):
        assert expand_allergies("땅콩,새우") == {"땅콩", "새우"}

    def test_whitespace_is_trimmed(self):
        assert expand_allergies(" 땅콩 , 새우 ") == {"땅콩", "새우"}


def test_synonym_tag_is_also_excluded(client, db_conn):
    """"달걀"을 고른 사용자에게 "계란" 태그가 붙은 레시피가 나오면 안 된다."""
    user_id, headers = _signup(client, "u_allergy_syn")
    before = _recommend_ids(client, user_id, headers)
    assert len(before) >= 2, "구분할 후보가 둘 이상 있어야 한다"

    _tag(db_conn, before[0], "달걀")
    _tag(db_conn, before[1], "계란")
    db_conn.execute("UPDATE users SET allergy = '달걀' WHERE id = ?", (user_id,))

    after = _recommend_ids(client, user_id, headers)
    assert before[0] not in after, "직접 고른 표기가 안 걸러졌다"
    assert before[1] not in after, "동의어 표기가 안 걸러졌다 - 이게 위험한 누락이다"


def test_allergy_options_come_from_real_tags(client, db_conn):
    """화면이 목록을 지어내면 태그에 없는 값을 고르게 되고, 필터는 아무것도 안 거른다."""
    db_conn.execute(
        "INSERT INTO recipe_tags (recipe_id, tag_type, tag_value) VALUES (1, 'allergy', '땅콩')"
    )
    res = client.get("/profile/allergy-options")
    assert res.status_code == 200

    options = res.json()
    assert options, "태그가 있으면 목록이 비면 안 된다"
    assert all(option["recipe_count"] >= 1 for option in options)
    assert "땅콩" in [option["value"] for option in options]


def test_allergy_options_merge_synonyms(client, db_conn):
    """달걀과 계란을 따로 보여주면 사용자가 둘 다 골라야 안전해진다 - 그건 설계 실패다."""
    db_conn.execute(
        "INSERT INTO recipe_tags (recipe_id, tag_type, tag_value) VALUES (1, 'allergy', '달걀')"
    )
    db_conn.execute(
        "INSERT INTO recipe_tags (recipe_id, tag_type, tag_value) VALUES (2, 'allergy', '계란')"
    )

    options = client.get("/profile/allergy-options").json()
    labels = [option["label"] for option in options]
    assert labels.count("달걀") + labels.count("계란") == 1, "동의어가 따로 노출됐다"

    merged = next(o for o in options if o["label"] in ("달걀", "계란"))
    assert merged["recipe_count"] == 2, "묶은 개수가 합산되지 않았다"


def test_allergy_options_path_is_not_swallowed_by_user_id(client):
    """8.2 함정: "/{user_id}"가 먼저 등록되면 "allergy-options"가 int 변환에 실패해 422."""
    assert client.get("/profile/allergy-options").status_code != 422
