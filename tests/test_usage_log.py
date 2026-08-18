"""사용 로그가 실제로 쌓이는지, 그리고 로그 때문에 요청이 망가지지 않는지 검증한다
(2026-08-18).

Phase 4에서 지인 5명의 이탈 지점을 보려면 시각이 남지 않는 행동(추천 호출·상세 열람
등)이 기록돼야 한다. 그런데 기록이 목적이 되면 안 된다 - 로그 INSERT가 실패했다고
사용자가 방금 넣은 재료가 사라지면 배보다 배꼽이 크다. 아래 두 축을 함께 본다.
"""

from helpers import signup_body

from api import usage_log


def _signup(client, username):
    res = client.post("/auth/signup", json=signup_body(username))
    assert res.status_code == 200
    data = res.json()
    return data["user_id"], {"Authorization": f"Bearer {data['token']}"}


def _events(db_conn, user_id=None):
    if user_id is None:
        rows = db_conn.execute(
            "SELECT event, user_id, recipe_id FROM usage_events ORDER BY id"
        ).fetchall()
    else:
        rows = db_conn.execute(
            "SELECT event, user_id, recipe_id FROM usage_events WHERE user_id = ? ORDER BY id",
            (user_id,),
        ).fetchall()
    return [tuple(row) for row in rows]


def _profile_body(**overrides):
    body = {
        "gender": "여성",
        "age_group": "20대",
        "allergy": "",
        "health_goal": "체중감량",
        "purpose": "자취생 식단관리",
        "cooking_level": "초급",
        "supplements": "없음",
        "household_size": 1,
        "novelty_pref": "새로운 메뉴 선호",
        "cooking_tools": "가스레인지",
        "medical_conditions": "",
    }
    body.update(overrides)
    return body


class TestFunnelIsRecorded:
    """Phase 4가 실제로 읽어야 하는 단계들이 남는가."""

    def test_login_is_recorded(self, client, db_conn):
        # 재방문 시점이 없으면 "며칠째까지 돌아왔나"를 볼 수 없다.
        _signup(client, "log_login")
        res = client.post(
            "/auth/login", json={"username": "log_login", "password": "pw123456"}
        )
        assert res.status_code == 200
        user_id = res.json()["user_id"]
        assert (usage_log.LOGIN, user_id, None) in _events(db_conn, user_id)

    def test_first_onboarding_is_recorded_but_edits_are_not(self, client, db_conn):
        # 고칠 때마다 남기면 "언제 마쳤나"가 마지막 수정 시각으로 흐려진다.
        user_id, headers = _signup(client, "log_onboard")
        assert client.put(
            f"/profile/{user_id}", json=_profile_body(), headers=headers
        ).status_code == 200
        assert client.put(
            f"/profile/{user_id}", json=_profile_body(health_goal="근육증가"), headers=headers
        ).status_code == 200

        done = [e for e in _events(db_conn, user_id) if e[0] == usage_log.ONBOARDING_DONE]
        assert len(done) == 1

    def test_pantry_add_is_recorded(self, client, db_conn):
        # ingredients 테이블에는 시각 컬럼이 없어서 여기서만 알 수 있다.
        user_id, headers = _signup(client, "log_pantry")
        assert client.post(
            f"/pantry/{user_id}", json={"name": "두부"}, headers=headers
        ).status_code == 200
        assert (usage_log.PANTRY_ADD, user_id, None) in _events(db_conn, user_id)

    def test_recommend_is_recorded(self, client, db_conn):
        user_id, headers = _signup(client, "log_recommend")
        res = client.get(
            f"/recommendation/{user_id}", params={"ingredients": ["두부"]}, headers=headers
        )
        assert res.status_code == 200, res.text
        assert (usage_log.RECOMMEND, user_id, None) in _events(db_conn, user_id)

    def test_recipe_view_records_which_recipe(self, client, db_conn):
        # 어떤 레시피가 실제로 열렸는지가 다음 판단의 근거다.
        user_id, headers = _signup(client, "log_view")
        assert client.get("/recommendation/recipes/1", headers=headers).status_code == 200
        assert (usage_log.RECIPE_VIEW, user_id, 1) in _events(db_conn, user_id)

    def test_recipe_view_without_login_is_recorded_anonymously(self, client, db_conn):
        # 레시피 상세는 링크 공유가 되므로 비로그인도 본다. 그 열람도 세야 한다.
        assert client.get("/recommendation/recipes/1").status_code == 200
        assert (usage_log.RECIPE_VIEW, None, 1) in _events(db_conn)

    def test_a_broken_token_does_not_block_a_public_view(self, client, db_conn):
        # 만료·위조 토큰을 들고 와도 공개 조회는 막지 않는다. 그냥 익명으로 센다.
        res = client.get(
            "/recommendation/recipes/1", headers={"Authorization": "Bearer not-a-real-token"}
        )
        assert res.status_code == 200
        assert (usage_log.RECIPE_VIEW, None, 1) in _events(db_conn)


class TestLoggingNeverBreaksTheRequest:
    """로그가 실패해도 사용자가 손해를 보면 안 된다.

    실패를 흉내내지 않고 진짜로 만든다 - 테이블을 지워두면 INSERT가 실제로 터진다.
    conftest가 테스트 하나를 트랜잭션 하나로 묶어 롤백하므로 다음 테스트에는 남지 않는다.

    다만 sqlite는 문 하나가 실패해도 트랜잭션을 중단시키지 않는다. 세이브포인트가
    정말로 필요한 이유(Postgres는 중단시킨다)는 여기서 증명되지 않으므로,
    tests/test_postgres_adapter.py에 운영과 같은 드라이버로 도는 테스트를 따로 뒀다.
    """

    def test_pantry_add_survives_a_failing_log(self, client, db_conn):
        user_id, headers = _signup(client, "log_fails")
        db_conn.execute("DROP TABLE usage_events")

        res = client.post(f"/pantry/{user_id}", json={"name": "두부"}, headers=headers)

        assert res.status_code == 200
        listed = client.get(f"/pantry/{user_id}", headers=headers)
        assert [item["name"] for item in listed.json()] == ["두부"]

    def test_recommend_survives_a_failing_log(self, client, db_conn):
        user_id, headers = _signup(client, "log_fails_rec")
        db_conn.execute("DROP TABLE usage_events")

        res = client.get(
            f"/recommendation/{user_id}", params={"ingredients": ["두부"]}, headers=headers
        )

        assert res.status_code == 200, res.text
        assert res.json() != []

    def test_recipe_view_survives_a_failing_log(self, client, db_conn):
        db_conn.execute("DROP TABLE usage_events")

        res = client.get("/recommendation/recipes/1")

        assert res.status_code == 200
        assert res.json()["id"] == 1
