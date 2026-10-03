"""재료 행이 재료인지 구획 제목인지 가리는 규칙을 검증한다 (2026-08-18).

왜 만들었나
화면이 "수량이 없으면 구획 제목"으로 판단하고 있었다. 운영 데이터를 세어보니 수량 없는
행 649개 중 진짜 구획 제목은 **4개**뿐이었다. 나머지는 "소금적당량"·"후추 적당량"처럼
수량이 글자로 적힌 진짜 재료다.

결과가 나빴다. 309개 레시피(전체의 27%)에서 재료가 제목으로 잘못 그려지고, 그 행이
목록 맨 끝에 있으면 뒤따르는 항목이 없어서 **화면에서 통째로 사라졌다.** 실제로
"감자를 곁들인 야채스튜"(id 791)는 DB에 재료가 15개인데 화면에는 13개만 나왔다 -
소금과 후추가 없어진 것이다. 요리 앱에서 그건 그냥 틀린 것이다.
"""

import pytest

from src.agents.portion_agent import classify_ingredient_row, display_name


class TestDisplayName:
    """원본 재료 텍스트를 나눌 때 남은 찌꺼기를 화면에 내보내기 전에 정리한다 (2026-10-02).

    운영 레시피 131개의 242행이 "재료 닭가슴살"·"[주재료]닭다리살"처럼 분류어가 앞에 붙은 채
    상세 화면과 재료비 카드에 그대로 나왔다.
    """

    @pytest.mark.parametrize("raw, shown", [
        ("재료 닭가슴살", "닭가슴살"),
        ("육수 다시마", "다시마"),
        ("양념 다진 마늘", "다진 마늘"),
        ("[주재료]닭다리살", "닭다리살"),
        ("(속재료) 단호박", "단호박"),
        ("스파게티면(건면)(5g)<br>", "스파게티면(건면)(5g)"),
        ("<br>[양념] 식용유", "식용유"),
    ])
    def test_leftover_labels_are_removed(self, raw, shown):
        assert display_name(raw) == shown

    @pytest.mark.parametrize("name", ["재료", "주재료", "장식", "소금적당량", "양파", "닭고기(가슴살"])
    def test_names_without_leftovers_are_unchanged(self, name):
        """구획 제목 자체("재료")는 뒤에 이름이 없으니 그대로다. 그래야 제목으로 계속 분류된다."""
        assert display_name(name) == name


class TestClassification:
    def test_real_section_titles(self):
        for name in ("주재료", "부재료", "양념장", "장식"):
            assert classify_ingredient_row(name, None) == "section"

    def test_textual_amounts_are_ingredients(self):
        """이게 사라지던 것들이다. 수량이 글자로 적혀 있을 뿐 진짜 재료다."""
        for name in ("소금적당량", "후추 적당량", "후춧가루(약간)", "파슬리가루(약간)"):
            assert classify_ingredient_row(name, None) == "ingredient", name

    def test_split_fragments_are_kept_as_ingredients(self):
        """원본 CSV가 쉼표에서 잘려 생긴 조각이다.

        "닭고기(가슴살, 120g)"이 두 행으로 쪼개졌다. 보기 좋진 않지만 제목으로 그리거나
        지우는 것보다는 재료로 남기는 편이 정보를 덜 잃는다.
        """
        for name in ("닭고기(가슴살", "120g)", "양파(½개)"):
            assert classify_ingredient_row(name, None) == "ingredient", name

    def test_metadata_rows_are_noise(self):
        # "1인분 기준<br>"은 재료가 아니라 원본의 안내 문구다.
        for name in ("1인분 기준<br>", "2인분 기준<br>", "", "   "):
            assert classify_ingredient_row(name, None) == "noise", repr(name)

    def test_servings_note_without_spaces_or_br_is_still_noise(self):
        """"<br>"을 떼고 나면 "1인분기준"(띄어쓰기 없음)이 안내 문구 판정을 빠져나갔다."""
        for name in ("1인분기준", "1인분 기준", "2인분 기준", "1인분기준<br>"):
            assert classify_ingredient_row(name, None) == "noise", name

    def test_a_section_word_with_an_amount_is_an_ingredient(self):
        # "재료"라는 이름에 수량이 붙어 있으면 그건 제목이 아니다.
        assert classify_ingredient_row("재료", 100.0) == "ingredient"


class TestDetailResponse:
    def test_every_row_says_what_it_is(self, client):
        rows = client.get("/recommendation/recipes/1").json()["ingredients"]
        assert rows
        for row in rows:
            assert row["kind"] in ("ingredient", "section")

    def test_noise_rows_never_reach_the_screen(self, client, db_conn):
        db_conn.execute(
            "INSERT INTO recipe_ingredients (recipe_id, name, amount, unit, base_servings) "
            "VALUES (1, '1인분 기준<br>', NULL, NULL, 1)"
        )
        names = [r["name"] for r in client.get("/recommendation/recipes/1").json()["ingredients"]]
        assert "1인분 기준<br>" not in names

    def test_a_real_ingredient_ending_in_br_is_shown(self, client, db_conn):
        """"<br>"이 붙었다는 이유로 진짜 재료를 숨기고 있었다. 운영 레시피 21행(달걀지단·숙주·
        차돌박이·토마토 등)이 상세 화면에서 사라져 있었다."""
        db_conn.execute(
            "INSERT INTO recipe_ingredients (recipe_id, name, amount, unit, base_servings) "
            "VALUES (1, '숙주(30g)<br>', NULL, NULL, 1), (1, '1인분기준<br>', NULL, NULL, 1)"
        )
        names = [r["name"] for r in client.get("/recommendation/recipes/1").json()["ingredients"]]
        assert "숙주(30g)" in names
        assert not any("기준" in n for n in names)

    def test_leftover_labels_never_reach_the_screen(self, client, db_conn):
        db_conn.execute(
            "INSERT INTO recipe_ingredients (recipe_id, name, amount, unit, base_servings) "
            "VALUES (1, '재료 닭가슴살', 60, 'g', 1)"
        )
        names = [r["name"] for r in client.get("/recommendation/recipes/1").json()["ingredients"]]
        assert "닭가슴살" in names
        assert "재료 닭가슴살" not in names

    def test_an_ingredient_without_an_amount_still_shows_up(self, client, db_conn):
        """이 테스트가 이 파일의 핵심이다. 소금이 사라지던 버그를 고정한다."""
        db_conn.execute(
            "INSERT INTO recipe_ingredients (recipe_id, name, amount, unit, base_servings) "
            "VALUES (1, '소금적당량', NULL, NULL, 1)"
        )
        rows = client.get("/recommendation/recipes/1").json()["ingredients"]
        salt = [r for r in rows if r["name"] == "소금적당량"]
        assert len(salt) == 1
        assert salt[0]["kind"] == "ingredient"


class TestMissingIngredients:
    def test_section_titles_are_not_reported_as_missing(self, client, db_conn):
        """화면이 "주재료가 부족합니다"라고 말하던 것을 막는다."""
        res = client.post(
            "/auth/signup",
            json={
                "username": "sub_section", "password": "pw123456", "name": "테스트",
                "phone": "010-0000-0000", "email": "sub_section@example.com",
                "gender": "여성", "age_group": "20대",
                "consents": {"terms_of_service": True, "privacy": True, "marketing": False},
            },
        )
        assert res.status_code == 200
        data = res.json()
        headers = {"Authorization": f"Bearer {data['token']}"}

        db_conn.execute(
            "INSERT INTO recipe_tags (recipe_id, tag_type, tag_value) VALUES (1, 'ingredient', '주재료')"
        )
        body = client.get(
            "/recommendation/recipes/1/substitution",
            params={"user_id": data["user_id"]},
            headers=headers,
        ).json()
        assert "주재료" not in [m["ingredient"] for m in body["missing_ingredients"]]

    def test_coverage_and_the_missing_list_agree(self, client, db_conn):
        """한쪽만 구획 제목을 빼면 "7개 부족"인데 목록은 5개인 상태가 된다.

        substitution_agent의 docstring이 약속하는 불변조건이고, 2026-08-18에 실제로 깨졌다.
        """
        res = client.post(
            "/auth/signup",
            json={
                "username": "cov_agree", "password": "pw123456", "name": "테스트",
                "phone": "010-0000-0000", "email": "cov_agree@example.com",
                "gender": "여성", "age_group": "20대",
                "consents": {"terms_of_service": True, "privacy": True, "marketing": False},
            },
        )
        data = res.json()
        headers = {"Authorization": f"Bearer {data['token']}"}
        db_conn.execute(
            "INSERT INTO recipe_tags (recipe_id, tag_type, tag_value) VALUES (1, 'ingredient', '장식')"
        )

        body = client.get(
            "/recommendation/recipes/1/substitution",
            params={"user_id": data["user_id"]},
            headers=headers,
        ).json()
        assert body["coverage"]["missing"] == len(body["missing_ingredients"])

    def test_the_card_and_the_detail_report_the_same_number(self, client, db_conn):
        """추천 카드가 "7개 부족"이라 하고 상세가 "5개"라고 하면 둘 다 못 믿게 된다.

        정렬용 missing_count는 조미료를 빼고 세는데, 그 숫자를 화면에 쓰면 소금이 없는데도
        "다 있다"가 된다. 그래서 화면에는 missing_for_display를 내보낸다.
        """
        res = client.post(
            "/auth/signup",
            json={
                "username": "same_num", "password": "pw123456", "name": "테스트",
                "phone": "010-0000-0000", "email": "same_num@example.com",
                "gender": "여성", "age_group": "20대",
                "consents": {"terms_of_service": True, "privacy": True, "marketing": False},
            },
        )
        data = res.json()
        user_id = data["user_id"]
        headers = {"Authorization": f"Bearer {data['token']}"}
        client.post(f"/pantry/{user_id}", json={"name": "두부"}, headers=headers)

        card = client.get(
            f"/recommendation/{user_id}", params={"ingredients": ["두부"]}, headers=headers
        ).json()
        assert card, "추천 결과가 있어야 비교할 수 있다"
        first = card[0]

        detail = client.get(
            f"/recommendation/recipes/{first['id']}/substitution",
            params={"user_id": user_id},
            headers=headers,
        ).json()
        assert first["missing_count"] == detail["coverage"]["missing"]
