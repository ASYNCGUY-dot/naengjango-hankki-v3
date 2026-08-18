"""건강 정보(알레르기·병력) 수집에 대한 별도 동의를 검증한다 (2026-08-18).

왜 따로 받는가
가입 화면의 포괄 동의로 덮지 않는다. 알레르기와 병력은 건강에 관한 정보라 나머지
항목과 취급이 다르고, 무엇에 동의하는지 눈앞에 있을 때 묻는 것이 맞다. 그래서 그 값을
실제로 입력하는 온보딩 시점에 받는다.

건강 정보를 넣지 않는 사람에게는 묻지 않는다. 수집하지 않는 것에 동의를 요구하면
동의가 형식이 된다.
"""

from helpers import signup_body

from src.agents import auth_agent


def _signup(client, username):
    res = client.post("/auth/signup", json=signup_body(username))
    assert res.status_code == 200
    data = res.json()
    return data["user_id"], {"Authorization": f"Bearer {data['token']}"}


def _profile(**overrides):
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


def _consent_rows(db_conn, user_id):
    return db_conn.execute(
        "SELECT consent_key, agreed FROM user_consents WHERE user_id = ? AND consent_key = ? "
        "ORDER BY id",
        (user_id, auth_agent.HEALTH_CONSENT),
    ).fetchall()


class TestConsentGatesSensitiveData:
    def test_allergy_without_consent_is_rejected(self, client, db_conn):
        # 조용히 비워서 저장하면 사용자는 알레르기를 넣었다고 믿는데 필터는 아무것도
        # 안 거른다. 이 프로젝트에서 가장 위험한 상태라 저장을 거절한다.
        user_id, headers = _signup(client, "hc_no_consent")

        res = client.put(f"/profile/{user_id}", json=_profile(allergy="달걀"), headers=headers)

        assert res.status_code == 422
        assert "동의" in res.json()["detail"]
        stored = db_conn.execute("SELECT allergy FROM users WHERE id = ?", (user_id,)).fetchone()
        assert not stored[0]

    def test_medical_conditions_without_consent_is_rejected(self, client):
        user_id, headers = _signup(client, "hc_no_consent2")

        res = client.put(
            f"/profile/{user_id}", json=_profile(medical_conditions="고혈압"), headers=headers
        )

        assert res.status_code == 422

    def test_allergy_with_consent_is_saved(self, client, db_conn):
        user_id, headers = _signup(client, "hc_yes")

        res = client.put(
            f"/profile/{user_id}",
            json=_profile(allergy="달걀", health_data_consent=True),
            headers=headers,
        )

        assert res.status_code == 200
        stored = db_conn.execute("SELECT allergy FROM users WHERE id = ?", (user_id,)).fetchone()
        assert stored[0] == "달걀"

    def test_no_health_data_needs_no_consent(self, client):
        # 수집하지 않는 것에 동의를 요구하면 동의가 형식이 된다.
        user_id, headers = _signup(client, "hc_none")

        res = client.put(f"/profile/{user_id}", json=_profile(), headers=headers)

        assert res.status_code == 200

    def test_whitespace_only_is_not_health_data(self, client):
        # 공백만 넣은 것을 "건강 정보를 입력했다"로 보면 저장이 막힌다.
        user_id, headers = _signup(client, "hc_blank")

        res = client.put(
            f"/profile/{user_id}", json=_profile(allergy="   ", medical_conditions=" "),
            headers=headers,
        )

        assert res.status_code == 200


class TestConsentIsRecorded:
    def test_agreement_is_recorded_as_history(self, client, db_conn):
        user_id, headers = _signup(client, "hc_record")

        client.put(
            f"/profile/{user_id}",
            json=_profile(allergy="달걀", health_data_consent=True),
            headers=headers,
        )

        rows = _consent_rows(db_conn, user_id)
        assert len(rows) == 1
        assert rows[0][1] in (1, True)

    def test_refusal_is_recorded_too(self, client, db_conn):
        # 행이 없으면 "안 물어봤다"와 "거절했다"를 구분할 수 없다.
        user_id, headers = _signup(client, "hc_refuse")

        res = client.put(f"/profile/{user_id}", json=_profile(), headers=headers)

        assert res.status_code == 200
        rows = _consent_rows(db_conn, user_id)
        assert len(rows) == 1
        assert rows[0][1] in (0, False)

    def test_withdrawal_is_appended_not_overwritten(self, client, db_conn):
        # 증빙이 목적이므로 덮어쓰지 않는다. 철회하면 행이 하나 더 쌓인다.
        user_id, headers = _signup(client, "hc_withdraw")

        client.put(
            f"/profile/{user_id}",
            json=_profile(allergy="달걀", health_data_consent=True),
            headers=headers,
        )
        client.put(f"/profile/{user_id}", json=_profile(), headers=headers)

        rows = _consent_rows(db_conn, user_id)
        assert len(rows) == 2
        assert rows[0][1] in (1, True)
        assert rows[1][1] in (0, False)

    def test_profile_reports_the_latest_consent_state(self, client):
        # 이미 동의한 사람에게 빈 체크박스를 보여주면 "동의한 적 없다"는 인상을 준다.
        user_id, headers = _signup(client, "hc_state")

        assert client.get(f"/profile/{user_id}", headers=headers).json()[
            "health_data_consent"
        ] is False

        client.put(
            f"/profile/{user_id}",
            json=_profile(allergy="달걀", health_data_consent=True),
            headers=headers,
        )

        assert client.get(f"/profile/{user_id}", headers=headers).json()[
            "health_data_consent"
        ] is True
