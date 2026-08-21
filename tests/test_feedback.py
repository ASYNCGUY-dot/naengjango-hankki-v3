"""
/feedback을 검증한다 (2026-08-22).

가장 중요한 것은 **읽는 범위**다. 쓴 사람은 자기 글만, 관리자는 전부 본다.
사용자 테스트에서 남의 의견이 보이면 그쪽으로 끌려가서, 두 번째 사람부터는 자기
생각이 아니라 "나도 그랬어"를 쓰게 된다. 이게 새면 Phase 4의 답이 오염된다.
"""

import pytest
from helpers import signup_body


def _signup(client, username: str) -> tuple[int, dict]:
    res = client.post("/auth/signup", json=signup_body(username))
    data = res.json()
    return data["user_id"], {"Authorization": f"Bearer {data['token']}"}


def _write(client, user_id, headers, body="재료 넣는 게 좀 귀찮았어요."):
    return client.post("/feedback", params={"user_id": user_id}, json={"body": body}, headers=headers)


def _make_admin(db_conn, user_id: int) -> None:
    db_conn.execute("UPDATE users SET is_admin = 1 WHERE id = ?", (user_id,))


def test_writing_returns_the_saved_item(client):
    user_id, headers = _signup(client, "u_fb_1")

    res = _write(client, user_id, headers)

    assert res.status_code == 200
    item = res.json()
    assert item["body"] == "재료 넣는 게 좀 귀찮았어요."
    # 본인 조회에서는 이름을 돌려주지 않는다 - 자기 글인 게 이미 자명하다.
    assert item["username"] is None


def test_i_see_only_my_own(client):
    """이게 이 기능의 핵심 규칙이다."""
    mine_id, mine_headers = _signup(client, "u_fb_2")
    other_id, other_headers = _signup(client, "u_fb_3")
    _write(client, mine_id, mine_headers, "내가 쓴 글")
    _write(client, other_id, other_headers, "남이 쓴 글")

    res = client.get("/feedback", params={"user_id": mine_id}, headers=mine_headers)

    assert res.status_code == 200
    assert [f["body"] for f in res.json()] == ["내가 쓴 글"]


def test_my_list_is_newest_first(client):
    user_id, headers = _signup(client, "u_fb_4")
    _write(client, user_id, headers, "먼저 쓴 글")
    _write(client, user_id, headers, "나중에 쓴 글")

    bodies = [f["body"] for f in client.get(
        "/feedback", params={"user_id": user_id}, headers=headers).json()]

    assert bodies == ["나중에 쓴 글", "먼저 쓴 글"]


def test_admin_sees_everyone_with_names(client, db_conn):
    # 누가 썼는지가 있어야 그 사람의 usage_events와 맞춰 볼 수 있다.
    a_id, a_headers = _signup(client, "u_fb_5")
    b_id, b_headers = _signup(client, "u_fb_6")
    _write(client, a_id, a_headers, "A의 의견")
    _write(client, b_id, b_headers, "B의 의견")
    admin_id, admin_headers = _signup(client, "u_fb_admin")
    _make_admin(db_conn, admin_id)

    res = client.get("/feedback/all", params={"user_id": admin_id}, headers=admin_headers)

    assert res.status_code == 200
    got = {(f["username"], f["body"]) for f in res.json()}
    assert ("u_fb_5", "A의 의견") in got
    assert ("u_fb_6", "B의 의견") in got


def test_a_normal_account_cannot_read_everyone(client):
    """여기가 새면 지인끼리 서로의 의견을 보게 된다."""
    author_id, author_headers = _signup(client, "u_fb_7")
    _write(client, author_id, author_headers, "남에게 보이면 안 되는 글")
    reader_id, reader_headers = _signup(client, "u_fb_8")

    res = client.get("/feedback/all", params={"user_id": reader_id}, headers=reader_headers)

    assert res.status_code == 403


def test_i_cannot_read_someone_elses_list(client):
    owner_id, _ = _signup(client, "u_fb_9")
    other_id, other_headers = _signup(client, "u_fb_10")

    res = client.get("/feedback", params={"user_id": owner_id}, headers=other_headers)

    assert res.status_code == 403


def test_i_can_delete_my_own_but_not_someone_elses(client):
    owner_id, owner_headers = _signup(client, "u_fb_11")
    feedback_id = _write(client, owner_id, owner_headers, "지울 글").json()["id"]
    other_id, other_headers = _signup(client, "u_fb_12")

    stolen = client.delete(
        f"/feedback/{feedback_id}", params={"user_id": other_id}, headers=other_headers
    )
    assert stolen.status_code == 404

    mine = client.delete(
        f"/feedback/{feedback_id}", params={"user_id": owner_id}, headers=owner_headers
    )
    assert mine.status_code == 200
    assert client.get("/feedback", params={"user_id": owner_id}, headers=owner_headers).json() == []


def test_an_admin_cannot_delete_someone_elses(client, db_conn):
    """관리자 화면은 읽으려고 있는 것이지 치우려고 있는 것이 아니다."""
    author_id, author_headers = _signup(client, "u_fb_13")
    feedback_id = _write(client, author_id, author_headers, "관리자도 못 지우는 글").json()["id"]
    admin_id, admin_headers = _signup(client, "u_fb_admin2")
    _make_admin(db_conn, admin_id)

    res = client.delete(
        f"/feedback/{feedback_id}", params={"user_id": admin_id}, headers=admin_headers
    )

    assert res.status_code == 404


@pytest.mark.parametrize("body", ["", "가" * 2001])
def test_body_limits_are_enforced_by_the_server(client, body):
    user_id, headers = _signup(client, f"u_fb_limit_{len(body)}")

    assert _write(client, user_id, headers, body).status_code == 422


@pytest.mark.parametrize("method,path", [("get", ""), ("get", "/all"), ("post", ""), ("delete", "/1")])
def test_feedback_requires_a_token(client, method, path):
    res = client.request(method, f"/feedback{path}", params={"user_id": 1}, json={"body": "x"})
    assert res.status_code == 401


def test_writing_is_logged(client, db_conn):
    """"어디까지 갔나"를 한 쿼리로 보려면 다른 단계와 같은 표에 있어야 한다."""
    user_id, headers = _signup(client, "u_fb_14")

    _write(client, user_id, headers)

    events = db_conn.execute(
        "SELECT event FROM usage_events WHERE user_id = ?", (user_id,)
    ).fetchall()
    assert ("feedback_post",) in events
