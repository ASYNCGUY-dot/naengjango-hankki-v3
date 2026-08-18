"""홈 화면 테마 목록을 검증한다 (2026-08-18).

왜 만들었나
홈이 승인된 레시피를 가나다순으로 20개 쏟아내서 "두서 없고 어지럽다"는 피드백을 받았다.
"가지겉절이, 가지나물냉국, 가지라따뚜이…"가 줄줄이 나오는 게 큰 몫이었다.

테마는 데이터가 지탱하는 것만 쓴다. 요청에는 한식·중식·일식과 난이도도 있었지만
recipes에 그런 컬럼이 없다. 난이도는 재료 개수로 대신한다.
"""

from src.agents import recommendation_agent


def _themes(client, **params):
    res = client.get("/recommendation/recipes/themes", params=params)
    assert res.status_code == 200, res.text
    return {theme["key"]: theme for theme in res.json()}


class TestThemeContents:
    def test_light_theme_only_has_light_recipes(self, client):
        for recipe in _themes(client)["light"]["recipes"]:
            assert recipe["calorie"] <= recommendation_agent.LIGHT_CALORIE_MAX

    def test_hearty_theme_only_has_hearty_recipes(self, client, db_conn):
        # 시드에는 고칼로리 레시피가 없다. 없으면 테마가 빠지는 게 맞는 동작이라
        # (아래 test_theme_is_dropped_when_empty), 여기서는 직접 넣고 본다.
        db_conn.execute(
            "INSERT INTO recipes (id, menu_name, category, calorie, status) "
            "VALUES (9903, '기름진덮밥', '밥', 700, 'approved')"
        )
        recipes = _themes(client)["hearty"]["recipes"]
        assert 9903 in [r["id"] for r in recipes]
        for recipe in recipes:
            assert recipe["calorie"] >= recommendation_agent.HEARTY_CALORIE_MIN

    def test_theme_is_dropped_when_empty(self, client):
        # 시드에 400kcal 이상이 하나도 없다. 빈 줄을 보여주느니 줄을 뺀다.
        assert "hearty" not in _themes(client)

    def test_simple_theme_recipes_really_have_few_ingredients(self, client, db_conn):
        # 난이도 컬럼이 없어 재료 개수로 대신한다. 그 대용이 실제로 맞아야 의미가 있다.
        for recipe in _themes(client)["simple"]["recipes"]:
            count = db_conn.execute(
                "SELECT COUNT(*) FROM recipe_ingredients WHERE recipe_id = ?", (recipe["id"],)
            ).fetchone()[0]
            assert count <= recommendation_agent.SIMPLE_INGREDIENT_MAX

    def test_cards_carry_their_photo(self, client):
        # 목록이 사진을 안 주면 화면이 레시피마다 상세를 한 번씩 더 불러야 한다.
        for theme in _themes(client).values():
            for recipe in theme["recipes"]:
                assert "image_url" in recipe

    def test_승인되지_않은_레시피는_섞이지_않는다(self, client, db_conn):
        db_conn.execute(
            "INSERT INTO recipes (id, menu_name, category, calorie, status) "
            "VALUES (9901, '심사중저칼로리', '반찬', 50, 'pending')"
        )
        ids = [r["id"] for t in _themes(client).values() for r in t["recipes"]]
        assert 9901 not in ids


class TestSeasonal:
    def test_month_decides_the_seasonal_theme(self, client, db_conn):
        # 달마다 바뀌는 것이 이 테마의 존재 이유다. 고정이면 그냥 또 하나의 목록이다.
        db_conn.execute(
            "INSERT INTO recipes (id, menu_name, category, calorie, status) "
            "VALUES (9902, '연근조림', '반찬', 100, 'approved')"
        )
        db_conn.execute(
            "INSERT INTO recipe_ingredients (recipe_id, name, amount, unit) "
            "VALUES (9902, '연근', 100, 'g')"
        )

        december = _themes(client, month=12)
        assert "12월 제철" == december["seasonal"]["title"]
        assert 9902 in [r["id"] for r in december["seasonal"]["recipes"]]

        # 3월 제철은 대파다. 연근 레시피가 거기 끼면 안 된다.
        march = _themes(client, month=3)
        assert 9902 not in [r["id"] for r in march.get("seasonal", {"recipes": []})["recipes"]]

    def test_seasonal_theme_is_dropped_when_nothing_matches(self, client):
        # 걸리는 레시피가 없으면 빈 줄을 보여주느니 줄 자체를 뺀다.
        themes = _themes(client, month=2)  # 2월은 한라봉 - 시드에 없다
        assert "seasonal" not in themes


class TestKoreanParticle:
    """조사가 틀리면 한국어 사용자가 바로 알아챈다. "참나물가 제철이에요"가 실제로 나왔다."""

    def test_batchim_decides_the_particle(self):
        assert recommendation_agent._subject_particle("참나물") == "이"  # ㄹ 받침
        assert recommendation_agent._subject_particle("블루베리") == "가"  # 받침 없음
        assert recommendation_agent._subject_particle("단감") == "이"
        assert recommendation_agent._subject_particle("대파") == "가"

    def test_seasonal_subtitle_uses_the_right_particle(self, client, db_conn):
        # 8월은 블루베리, 참나물이다. 마지막 낱말이 조사를 정한다.
        db_conn.execute(
            "INSERT INTO recipes (id, menu_name, category, calorie, status) "
            "VALUES (9904, '참나물무침', '반찬', 60, 'approved')"
        )
        db_conn.execute(
            "INSERT INTO recipe_ingredients (recipe_id, name, amount, unit) "
            "VALUES (9904, '참나물', 100, 'g')"
        )
        subtitle = _themes(client, month=8)["seasonal"]["subtitle"]
        assert subtitle.endswith("참나물이 제철이에요"), subtitle


class TestThemeShape:
    def test_every_theme_reports_how_many_there_are(self, client):
        # 열 개만 보여주고 끝이면 그게 전부인지 일부인지 알 수 없다.
        for theme in _themes(client).values():
            assert theme["total"] >= len(theme["recipes"])
            assert theme["title"]

    def test_limit_caps_each_row(self, client):
        for theme in _themes(client, limit=2).values():
            assert len(theme["recipes"]) <= 2

    def test_themes_are_not_sorted_by_name(self, client, db_conn):
        """가나다순이면 애초 문제였던 뭉침이 테마 안에서 되풀이된다."""
        for i in range(8):
            db_conn.execute(
                "INSERT INTO recipes (id, menu_name, category, calorie, status) "
                "VALUES (?, ?, '반찬', 50, 'approved')",
                (9910 + i, f"가나다{i}"),
            )
        names = [r["menu_name"] for r in _themes(client)["light"]["recipes"]]
        assert names != sorted(names)
