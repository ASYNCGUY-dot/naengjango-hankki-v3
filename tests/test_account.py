"""확장된 회원가입과 비밀번호 초기화를 검증한다 (2026-08-13).

V2의 계정은 아이디와 비밀번호뿐이었다. 비밀번호를 잊으면 복구할 방법이 없었고 가입
시점도 남지 않았다. V3는 이름·연락처·이메일·성별·연령대와 동의 기록을 함께 받고,
메일로 보낸 일회용 링크로 비밀번호를 초기화한다.

"찾기"는 없다. 비밀번호는 단방향 해시로 저장돼 서버도 알 수 없으므로 알려줄 방법이
자체가 없다.
"""

from datetime import timedelta

import pytest

from api.routers import auth as auth_router
from helpers import signup_body
from src.agents import auth_agent, mail_agent


@pytest.fixture(autouse=True)
def no_real_mail(monkeypatch):
    """테스트가 실제로 메일을 보내면 안 된다. 보낸 내용은 sent에 모아 확인한다."""
    sent: list[tuple[str, str, str]] = []

    def fake_send(to_address, subject, body):
        sent.append((to_address, subject, body))
        return True, "발송 완료"

    monkeypatch.setattr(mail_agent, "send_mail", fake_send)
    # 요청 횟수 제한은 모듈 레벨 dict라 테스트 사이에 남는다.
    auth_router._reset_requests.clear()
    return sent


def _reset_link_token(sent) -> str:
    """메일 본문에서 토큰만 뽑는다."""
    body = sent[-1][2]
    return body.split("token=")[1].split()[0]


# ---------- 가입 정보 ----------

def test_signup_stores_the_new_account_fields(client, db_conn):
    res = client.post("/auth/signup", json=signup_body("u_acct_1", name="최지수"))
    assert res.status_code == 200
    user_id = res.json()["user_id"]

    row = db_conn.execute(
        "SELECT name, phone, email, gender, age_group, created_at FROM users WHERE id = ?",
        (user_id,),
    ).fetchone()
    name, phone, email, gender, age_group, created_at = row
    assert name == "최지수"
    assert phone == "010-0000-0000"
    assert email == "u_acct_1@example.com"
    assert gender == "여성"
    assert age_group == "20대"
    # V2에는 users에만 created_at이 없어서 "가입하고 얼마 만에 썼나"를 볼 수 없었다.
    assert created_at is not None


def test_email_is_stored_lowercase_and_must_be_unique(client, db_conn):
    first = client.post("/auth/signup", json=signup_body("u_acct_a", email="Same@Example.COM"))
    assert first.status_code == 200
    stored = db_conn.execute(
        "SELECT email FROM users WHERE id = ?", (first.json()["user_id"],)
    ).fetchone()[0]
    # 대소문자만 다른 주소를 다른 사람으로 보면 초기화 대상을 특정할 수 없다.
    assert stored == "same@example.com"

    second = client.post("/auth/signup", json=signup_body("u_acct_b", email="same@example.com"))
    assert second.status_code == 409


def test_invalid_email_is_rejected(client):
    res = client.post("/auth/signup", json=signup_body("u_acct_bademail", email="골뱅이없음"))
    assert res.status_code == 422


# ---------- 동의 ----------

def test_signup_requires_both_mandatory_consents(client):
    for missing in ("terms_of_service", "privacy"):
        consents = {"terms_of_service": True, "privacy": True, "marketing": False}
        consents[missing] = False
        res = client.post(
            "/auth/signup", json=signup_body(f"u_consent_{missing}", consents=consents)
        )
        assert res.status_code == 422, f"{missing} 미동의인데 가입됐다"


def test_marketing_consent_is_optional(client):
    res = client.post(
        "/auth/signup",
        json=signup_body(
            "u_consent_nomkt",
            consents={"terms_of_service": True, "privacy": True, "marketing": False},
        ),
    )
    assert res.status_code == 200


def test_consents_are_recorded_with_version_and_time(client, db_conn):
    """증빙이 목적이라 무엇에 언제 어느 버전으로 동의했는지가 남아야 한다."""
    res = client.post(
        "/auth/signup",
        json=signup_body(
            "u_consent_log",
            consents={"terms_of_service": True, "privacy": True, "marketing": True},
        ),
    )
    user_id = res.json()["user_id"]

    rows = db_conn.execute(
        "SELECT consent_key, version, agreed, agreed_at FROM user_consents "
        "WHERE user_id = ? ORDER BY consent_key",
        (user_id,),
    ).fetchall()

    assert {r[0] for r in rows} == set(auth_agent.ALL_CONSENTS)
    for _, version, agreed, agreed_at in rows:
        assert version == auth_agent.CONSENT_VERSION
        assert agreed
        assert agreed_at


def test_declined_marketing_is_recorded_as_false_not_omitted(client, db_conn):
    """거절도 기록이다. 행이 없으면 "안 물어봤다"와 "거절했다"를 구분할 수 없다."""
    res = client.post(
        "/auth/signup",
        json=signup_body(
            "u_consent_declined",
            consents={"terms_of_service": True, "privacy": True, "marketing": False},
        ),
    )
    agreed = db_conn.execute(
        "SELECT agreed FROM user_consents WHERE user_id = ? AND consent_key = 'marketing'",
        (res.json()["user_id"],),
    ).fetchone()[0]
    assert not agreed


# ---------- 초기화 요청 ----------

def test_reset_request_sends_a_mail_for_a_known_email(client, no_real_mail):
    client.post("/auth/signup", json=signup_body("u_reset_1"))

    res = client.post(
        "/auth/password-reset/request", json={"email": "u_reset_1@example.com"}
    )
    assert res.status_code == 200
    assert len(no_real_mail) == 1
    to_address, subject, body = no_real_mail[0]
    assert to_address == "u_reset_1@example.com"
    assert "초기화" in subject
    assert "token=" in body


def test_reset_request_does_not_reveal_whether_the_account_exists(client, no_real_mail):
    """가입 안 된 주소로 요청해도 같은 응답을 준다. 다르게 답하면 "이 주소는 가입돼
    있다/없다"를 확인하는 도구가 된다."""
    client.post("/auth/signup", json=signup_body("u_reset_2"))

    known = client.post(
        "/auth/password-reset/request", json={"email": "u_reset_2@example.com"}
    )
    unknown = client.post(
        "/auth/password-reset/request", json={"email": "아무도없음@example.com"}
    )

    assert known.status_code == unknown.status_code == 200
    assert known.json() == unknown.json()
    # 메일은 실제로 가입된 주소로만 나간다.
    assert [m[0] for m in no_real_mail] == ["u_reset_2@example.com"]


def test_mail_body_does_not_contain_the_username(client, no_real_mail):
    """메일이 잘못된 주소로 갔을 때 계정 정보까지 새어나가면 안 된다."""
    client.post("/auth/signup", json=signup_body("u_reset_secret", name="홍길동"))
    client.post("/auth/password-reset/request", json={"email": "u_reset_secret@example.com"})

    body = no_real_mail[-1][2]
    assert "u_reset_secret" not in body.replace("u_reset_secret@example.com", "")
    assert "홍길동" not in body


def test_repeated_requests_are_rate_limited(client, no_real_mail):
    """남의 주소로 반복 요청해 메일함을 채우는 것을 막는다. 이 경우에도 응답은 같다."""
    client.post("/auth/signup", json=signup_body("u_reset_flood"))
    email = "u_reset_flood@example.com"

    for _ in range(auth_router.MAX_RESET_REQUESTS + 3):
        res = client.post("/auth/password-reset/request", json={"email": email})
        assert res.status_code == 200

    assert len(no_real_mail) == auth_router.MAX_RESET_REQUESTS


# ---------- 초기화 확인 ----------

def test_reset_changes_the_password(client, no_real_mail):
    client.post("/auth/signup", json=signup_body("u_reset_ok", password="oldpw12345"))
    client.post("/auth/password-reset/request", json={"email": "u_reset_ok@example.com"})
    token = _reset_link_token(no_real_mail)

    res = client.post(
        "/auth/password-reset/confirm", json={"token": token, "new_password": "newpw12345"}
    )
    assert res.status_code == 200

    assert (
        client.post(
            "/auth/login", json={"username": "u_reset_ok", "password": "newpw12345"}
        ).status_code
        == 200
    )
    assert (
        client.post(
            "/auth/login", json={"username": "u_reset_ok", "password": "oldpw12345"}
        ).status_code
        == 401
    )


def test_reset_revokes_existing_sessions(client, no_real_mail):
    """비밀번호를 바꿨는데 남이 로그인해 있던 세션이 살아 있으면 바꾼 의미가 없다."""
    signup = client.post("/auth/signup", json=signup_body("u_reset_sessions")).json()
    headers = {"Authorization": f"Bearer {signup['token']}"}
    assert client.get(f"/profile/{signup['user_id']}", headers=headers).status_code == 200

    client.post("/auth/password-reset/request", json={"email": "u_reset_sessions@example.com"})
    client.post(
        "/auth/password-reset/confirm",
        json={"token": _reset_link_token(no_real_mail), "new_password": "newpw12345"},
    )

    assert client.get(f"/profile/{signup['user_id']}", headers=headers).status_code == 401


def test_token_cannot_be_used_twice(client, no_real_mail):
    client.post("/auth/signup", json=signup_body("u_reset_twice"))
    client.post("/auth/password-reset/request", json={"email": "u_reset_twice@example.com"})
    token = _reset_link_token(no_real_mail)

    first = client.post(
        "/auth/password-reset/confirm", json={"token": token, "new_password": "newpw12345"}
    )
    assert first.status_code == 200

    second = client.post(
        "/auth/password-reset/confirm", json={"token": token, "new_password": "otherpw1234"}
    )
    assert second.status_code == 400
    # 만료와 구분해서 안내한다.
    assert "이미 사용" in second.json()["detail"]


def test_new_request_invalidates_the_previous_link(client, no_real_mail):
    """여러 링크가 동시에 살아 있으면 오래된 메일로도 비밀번호가 바뀐다."""
    client.post("/auth/signup", json=signup_body("u_reset_two_links"))
    email = "u_reset_two_links@example.com"

    client.post("/auth/password-reset/request", json={"email": email})
    old_token = _reset_link_token(no_real_mail)
    client.post("/auth/password-reset/request", json={"email": email})
    new_token = _reset_link_token(no_real_mail)
    assert old_token != new_token

    stale = client.post(
        "/auth/password-reset/confirm", json={"token": old_token, "new_password": "newpw12345"}
    )
    assert stale.status_code == 400

    fresh = client.post(
        "/auth/password-reset/confirm", json={"token": new_token, "new_password": "newpw12345"}
    )
    assert fresh.status_code == 200


def test_expired_token_is_rejected(client, db_conn, no_real_mail):
    client.post("/auth/signup", json=signup_body("u_reset_expired"))
    client.post("/auth/password-reset/request", json={"email": "u_reset_expired@example.com"})
    token = _reset_link_token(no_real_mail)

    past = (auth_agent._now() - timedelta(seconds=1)).isoformat()
    db_conn.execute(
        "UPDATE password_reset_tokens SET expires_at = ? WHERE token_hash = ?",
        (past, auth_agent._hash_token(token)),
    )

    res = client.post(
        "/auth/password-reset/confirm", json={"token": token, "new_password": "newpw12345"}
    )
    assert res.status_code == 400
    assert "만료" in res.json()["detail"]


def test_unknown_token_is_rejected(client):
    res = client.post(
        "/auth/password-reset/confirm",
        json={"token": "이런토큰은없다", "new_password": "newpw12345"},
    )
    assert res.status_code == 400


def test_short_new_password_is_rejected(client, no_real_mail):
    client.post("/auth/signup", json=signup_body("u_reset_shortpw"))
    client.post("/auth/password-reset/request", json={"email": "u_reset_shortpw@example.com"})
    token = _reset_link_token(no_real_mail)

    res = client.post(
        "/auth/password-reset/confirm", json={"token": token, "new_password": "short"}
    )
    assert res.status_code == 422
