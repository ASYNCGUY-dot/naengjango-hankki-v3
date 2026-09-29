"""사용 로그가 실제로 쌓이는지, 그리고 로그 때문에 요청이 망가지지 않는지 검증한다
(2026-08-18).

Phase 4에서 지인 5명의 이탈 지점을 보려면 시각이 남지 않는 행동(추천 호출·상세 열람
등)이 기록돼야 한다. 그런데 기록이 목적이 되면 안 된다 - 로그 INSERT가 실패했다고
사용자가 방금 넣은 재료가 사라지면 배보다 배꼽이 크다. 아래 두 축을 함께 본다.
"""

import logging
from datetime import datetime, timedelta, timezone

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


class _FixedClock:
    """usage_log 안의 datetime만 바꿔 끼운다.

    중복 판정이 10초 구간 단위라, 실제 시계를 쓰면 두 요청 사이에 구간 경계가 끼는 날
    테스트가 가끔 깨진다. 시각을 고정해서 그 우연을 없앤다.
    """

    moment = datetime(2026, 9, 15, 12, 0, 1, tzinfo=timezone.utc)

    @classmethod
    def now(cls, tz=None):
        return cls.moment


class TestRecipeViewDedupe:
    """같은 사람이 같은 레시피를 한순간에 여러 번 열면 한 줄만 남는다 (2026-09-15).

    운영에서 15ms·48ms 간격의 중복이 실제로 찍혔다. 원인은 못 찾았지만 동시에 처리된
    두 요청이었으므로 DB 제약으로 막는다(migration/012). 여기서는 규칙의 경계를 고정한다 -
    막아야 할 것만 막고, 세야 할 것은 그대로 세는지.
    """

    @staticmethod
    def _views(db_conn, user_id):
        return db_conn.execute(
            "SELECT COUNT(*) FROM usage_events WHERE event = 'recipe_view' AND user_id IS ?",
            (user_id,),
        ).fetchone()[0]

    def test_same_user_same_recipe_in_one_window_is_one_row(
        self, client, db_conn, monkeypatch, caplog
    ):
        monkeypatch.setattr(usage_log, "datetime", _FixedClock)
        user_id, headers = _signup(client, "dedupe_same")
        with caplog.at_level(logging.WARNING, logger="api.usage_log"):
            for _ in range(3):
                assert client.get("/recommendation/recipes/1", headers=headers).status_code == 200
        assert self._views(db_conn, user_id) == 1
        # 중복은 예상된 일이라 "기록 실패" 경고로 남기면 안 된다. 거짓 경보가 쌓이면 진짜
        # 실패가 묻힌다. ON CONFLICT DO NOTHING이 있는 이유가 이것이다 - 없어도 줄 수는
        # 같지만(예외를 삼키므로) 로그가 경고로 찬다.
        assert not [r for r in caplog.records if r.name == "api.usage_log"]

    def test_views_seconds_apart_in_one_window_are_merged(self, client, db_conn, monkeypatch):
        # 묶는 범위는 수십 ms가 아니라 구간 하나(10초)다. 새로고침 한 번 정도 간격도 묶인다.
        monkeypatch.setattr(usage_log, "datetime", _FixedClock)
        user_id, headers = _signup(client, "dedupe_seconds")
        client.get("/recommendation/recipes/1", headers=headers)
        monkeypatch.setattr(_FixedClock, "moment", _FixedClock.moment + timedelta(seconds=5))
        client.get("/recommendation/recipes/1", headers=headers)
        assert self._views(db_conn, user_id) == 1

    def test_the_request_still_succeeds_when_the_view_is_merged(self, client, monkeypatch):
        # 중복이라 기록을 건너뛰어도 사용자는 레시피를 봐야 한다.
        monkeypatch.setattr(usage_log, "datetime", _FixedClock)
        _, headers = _signup(client, "dedupe_ok")
        client.get("/recommendation/recipes/1", headers=headers)
        res = client.get("/recommendation/recipes/1", headers=headers)
        assert res.status_code == 200
        assert res.json()["ingredients"]

    def test_a_later_window_counts_again(self, client, db_conn, monkeypatch):
        # 막는 것은 "한순간"이다. 나중에 다시 연 것은 다시 연 것이다.
        monkeypatch.setattr(usage_log, "datetime", _FixedClock)
        user_id, headers = _signup(client, "dedupe_later")
        client.get("/recommendation/recipes/1", headers=headers)
        monkeypatch.setattr(
            _FixedClock,
            "moment",
            _FixedClock.moment + timedelta(seconds=usage_log.RECIPE_VIEW_DEDUPE_SECONDS),
        )
        client.get("/recommendation/recipes/1", headers=headers)
        assert self._views(db_conn, user_id) == 2

    def test_different_recipes_in_one_window_both_count(self, client, db_conn, monkeypatch):
        monkeypatch.setattr(usage_log, "datetime", _FixedClock)
        user_id, _ = _signup(client, "dedupe_two_recipes")
        cur = db_conn.cursor()
        usage_log.record(cur, usage_log.RECIPE_VIEW, user_id=user_id, recipe_id=1)
        usage_log.record(cur, usage_log.RECIPE_VIEW, user_id=user_id, recipe_id=2)
        assert self._views(db_conn, user_id) == 2

    def test_anonymous_views_are_not_merged(self, client, db_conn, monkeypatch):
        # 비로그인은 서로 다른 사람을 구분할 수 없어서 묶지 않는다. 공유 링크 유입은
        # 드문 만큼 한 줄 한 줄이 중요하다.
        monkeypatch.setattr(usage_log, "datetime", _FixedClock)
        before = self._views(db_conn, None)
        client.get("/recommendation/recipes/1")
        client.get("/recommendation/recipes/1")
        assert self._views(db_conn, None) - before == 2

    def test_the_bucket_itself_says_what_gets_merged(self):
        """묶을지 말지의 판단을 직접 고정한다.

        행 수만 보는 테스트로는 이 규칙을 못 지킨다. 인덱스가 (user_id, recipe_id,
        dedupe_bucket)이고 DB는 NULL을 서로 다른 값으로 보므로, 비로그인에 구간 번호를
        붙여도 실제로는 안 묶인다 - 그래서 "비로그인도 묶는다"로 바꿔도 겉으로는 티가
        안 났다(뮤테이션에서 실제로 살아남았다). 의도를 여기서 고정해 둔다. 나중에
        인덱스를 COALESCE(user_id, 0)으로 바꾸면 그 순간 비로그인이 묶이기 시작한다.
        """
        moment = _FixedClock.moment
        assert usage_log._dedupe_bucket(usage_log.RECIPE_VIEW, None, moment) is None
        assert usage_log._dedupe_bucket(usage_log.RECIPE_VIEW, 5, moment) is not None
        assert usage_log._dedupe_bucket(usage_log.PANTRY_ADD, 5, moment) is None

    def test_other_events_are_never_merged(self, client, db_conn, monkeypatch):
        # 재료를 같은 순간에 두 개 넣는 것은 정상이다. 중복 방지는 열람에만 건다.
        monkeypatch.setattr(usage_log, "datetime", _FixedClock)
        user_id, _ = _signup(client, "dedupe_pantry")
        cur = db_conn.cursor()
        usage_log.record(cur, usage_log.PANTRY_ADD, user_id=user_id)
        usage_log.record(cur, usage_log.PANTRY_ADD, user_id=user_id)
        count = db_conn.execute(
            "SELECT COUNT(*) FROM usage_events WHERE event = 'pantry_add' AND user_id = ?",
            (user_id,),
        ).fetchone()[0]
        assert count == 2


class TestOnboardingView:
    """식단 정보 화면 진입 (2026-09-15).

    가입만 하고 멈춘 사람이 "들어갔다가 나갔는지"와 "아예 안 들어갔는지"가 로그에서 같은
    모양이었다. 진입을 따로 남겨야 둘을 가를 수 있다.
    """

    def test_entering_the_screen_is_recorded(self, client, db_conn):
        user_id, headers = _signup(client, "log_onb_view")
        res = client.post(f"/profile/{user_id}/onboarding-view", headers=headers)
        assert res.status_code == 204
        assert (usage_log.ONBOARDING_VIEW, user_id, None) in _events(db_conn, user_id)

    def test_cannot_record_for_someone_else(self, client, db_conn):
        victim_id, _ = _signup(client, "log_onb_victim")
        _, attacker_headers = _signup(client, "log_onb_attacker")
        res = client.post(f"/profile/{victim_id}/onboarding-view", headers=attacker_headers)
        assert res.status_code == 403
        assert (usage_log.ONBOARDING_VIEW, victim_id, None) not in _events(db_conn, victim_id)

    def test_requires_login(self, client):
        user_id, _ = _signup(client, "log_onb_anon")
        assert client.post(f"/profile/{user_id}/onboarding-view").status_code == 401

    def test_reading_the_profile_does_not_count_as_entering(self, client, db_conn):
        # 마이 화면도 GET /profile을 부른다. 거기에 기록을 얹었다면 마이 탭을 열 때마다
        # "식단 정보 화면에 들어왔다"가 찍혀 신호가 쓸모없어진다.
        user_id, headers = _signup(client, "log_onb_get")
        assert client.get(f"/profile/{user_id}", headers=headers).status_code == 200
        assert all(event != usage_log.ONBOARDING_VIEW for event, _, _ in _events(db_conn, user_id))
