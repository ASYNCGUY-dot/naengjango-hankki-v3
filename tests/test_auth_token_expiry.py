"""토큰 만료·슬라이딩 갱신(api/auth_token.py, V3 Phase 1 2026-08-12)을 검증한다.

V2에는 만료가 없어서 한 번 발급된 토큰이 영구히 유효했다. 여기서 검증하는 계약은 네 가지다.
  - 만료된 토큰은 401이고, 그 행은 DB에서 치워진다
  - expires_at을 해석할 수 없으면(형식 깨짐) 통과시키지 않는다
  - 만료가 가까우면 자동으로 연장된다(쓰는 동안은 로그아웃되지 않는다)
  - 아직 멀었으면 연장하지 않는다(요청마다 UPDATE하지 않는다)

시각 조작은 client와 같은 커넥션(db_conn)으로 expires_at을 직접 바꿔서 한다 -
실제로 30일을 기다리지 않고 만료 상황을 만들기 위함이다.
"""

from datetime import timedelta

from api.auth_token import TOKEN_SLIDE_THRESHOLD, TOKEN_TTL, _hash_token, _now


def _signup(client, username):
    res = client.post("/auth/signup", json={"username": username, "password": "pw123456"})
    assert res.status_code == 200
    return res.json()


def _read_expires_at(db_conn, token):
    cur = db_conn.execute(
        "SELECT expires_at FROM auth_tokens WHERE token_hash = ?", (_hash_token(token),)
    )
    row = cur.fetchone()
    return row[0] if row else None


def _set_expires_at(db_conn, token, value):
    db_conn.execute(
        "UPDATE auth_tokens SET expires_at = ? WHERE token_hash = ?",
        (value, _hash_token(token)),
    )


def test_fresh_token_has_expiry_about_ttl_away(client, db_conn):
    data = _signup(client, "u_exp_fresh")
    expires_at = _read_expires_at(db_conn, data["token"])
    assert expires_at is not None, "발급 시점에 expires_at이 반드시 있어야 한다"

    from datetime import datetime

    remaining = datetime.fromisoformat(expires_at) - _now()
    # 발급과 검증 사이의 실행 시간만큼 짧아지므로 여유를 둔다.
    assert TOKEN_TTL - timedelta(minutes=1) < remaining <= TOKEN_TTL


def test_expired_token_returns_401_and_row_is_removed(client, db_conn):
    data = _signup(client, "u_exp_expired")
    headers = {"Authorization": f"Bearer {data['token']}"}
    assert client.get(f"/profile/{data['user_id']}", headers=headers).status_code == 200

    _set_expires_at(db_conn, data["token"], (_now() - timedelta(seconds=1)).isoformat())

    res = client.get(f"/profile/{data['user_id']}", headers=headers)
    assert res.status_code == 401
    # 만료된 행을 남겨두면 계속 조회 대상이 되므로 그 자리에서 치워야 한다.
    assert _read_expires_at(db_conn, data["token"]) is None


def test_token_with_unparseable_expires_at_is_rejected(client, db_conn):
    """만료 시각을 해석할 수 없으면 "만료된 것으로 취급"한다 - 판단 못 하는 토큰을
    통과시키면 만료를 도입한 의미가 없다."""
    data = _signup(client, "u_exp_broken")
    _set_expires_at(db_conn, data["token"], "형식이-깨진-값")

    res = client.get(
        f"/profile/{data['user_id']}",
        headers={"Authorization": f"Bearer {data['token']}"},
    )
    assert res.status_code == 401


def test_token_near_expiry_is_extended(client, db_conn):
    """쓰고 있는 동안에는 로그아웃되지 않아야 한다."""
    data = _signup(client, "u_exp_slide")
    near = _now() + TOKEN_SLIDE_THRESHOLD - timedelta(hours=1)
    _set_expires_at(db_conn, data["token"], near.isoformat())

    res = client.get(
        f"/profile/{data['user_id']}",
        headers={"Authorization": f"Bearer {data['token']}"},
    )
    assert res.status_code == 200

    from datetime import datetime

    extended = datetime.fromisoformat(_read_expires_at(db_conn, data["token"]))
    assert extended > near, "만료가 가까우면 연장돼야 한다"
    assert extended - _now() > TOKEN_TTL - timedelta(minutes=1)


def test_token_far_from_expiry_is_not_rewritten(client, db_conn):
    """요청마다 UPDATE를 쓰면 무료 티어에서 낭비가 크다 - 문턱을 넘기 전에는 건드리지 않는다."""
    data = _signup(client, "u_exp_noslide")
    before = _read_expires_at(db_conn, data["token"])

    res = client.get(
        f"/profile/{data['user_id']}",
        headers={"Authorization": f"Bearer {data['token']}"},
    )
    assert res.status_code == 200
    assert _read_expires_at(db_conn, data["token"]) == before
