"""관리자 엔드포인트 7개의 권한 경계를 검증한다 (V3 Phase 1, 2026-08-12).

V2에서 이 라우터는 테스트가 0개였다. 승인 권한을 다루는 자리라 여기가 뚫리면 아무나
유저 등록 레시피를 승인하거나 지울 수 있다.

권한 검사는 두 겹이다.
  1) require_self - 쿼리의 user_id가 토큰 주인 본인인가 (아니면 403)
  2) _require_admin - 그 계정이 관리자인가 (아니면 403)
promote만 예외로 관리자 판정 대신 ADMIN_SECRET 코드를 확인한다. "누가 첫 관리자가
되는가"라는 순환 문제를 피하려고 코드를 아는 사람만 스스로 승격하게 한 설계다.

이 파일의 핵심은 상태 코드만 보지 않는다는 점이다. 403이 떴어도 그 사이에 승인이나
삭제가 실제로 일어났다면 막은 게 아니므로, 거부 뒤에 DB 상태가 그대로인지 함께 본다.
"""

import pytest

from src.agents import auth_agent

ADMIN_CODE = "test-admin-code-1234"

# (HTTP 메서드, 경로) - 경로의 id는 권한 검사가 먼저 돌기 때문에 실제로 존재하지 않아도 된다.
ADMIN_GATED_ENDPOINTS = [
    ("get", "/admin/pending-recipes"),
    ("post", "/admin/recipes/1/approve"),
    ("post", "/admin/recipes/1/reject"),
    ("get", "/admin/pending-ingredients"),
    ("post", "/admin/ingredients/1/approve"),
    ("post", "/admin/ingredients/1/reject"),
]


def _signup(client, username):
    res = client.post("/auth/signup", json={"username": username, "password": "pw123456"})
    assert res.status_code == 200
    data = res.json()
    return data["user_id"], {"Authorization": f"Bearer {data['token']}"}


def _grant_admin(db_conn, user_id):
    """승격 흐름을 거치지 않고 관리자 상태만 만든다 - promote 자체는 따로 검증한다."""
    db_conn.execute("UPDATE users SET is_admin = 1 WHERE id = ?", (user_id,))


def _insert_pending_recipe(db_conn, submitted_by, menu_name="대기중인레시피"):
    cur = db_conn.execute(
        "INSERT INTO recipes (menu_name, category, calorie, source_api, submitted_by, status) "
        "VALUES (?, ?, ?, ?, ?, 'pending')",
        (menu_name, "반찬", 100, "user", submitted_by),
    )
    return cur.lastrowid


def _insert_pending_ingredient(db_conn, submitted_by, name="대기중인재료"):
    cur = db_conn.execute(
        "INSERT INTO ingredient_submissions (ingredient_name, submitted_by, calorie, status, created_at) "
        "VALUES (?, ?, ?, 'pending', '2026-08-12T00:00:00')",
        (name, submitted_by, 120),
    )
    return cur.lastrowid


def _recipe_status(db_conn, recipe_id):
    row = db_conn.execute("SELECT status FROM recipes WHERE id = ?", (recipe_id,)).fetchone()
    return row[0] if row else None


def _submission_status(db_conn, submission_id):
    row = db_conn.execute(
        "SELECT status FROM ingredient_submissions WHERE id = ?", (submission_id,)
    ).fetchone()
    return row[0] if row else None


def _is_admin(db_conn, user_id):
    return db_conn.execute("SELECT is_admin FROM users WHERE id = ?", (user_id,)).fetchone()[0]


# ---------- 1겹: 토큰 ----------

@pytest.mark.parametrize("method,path", ADMIN_GATED_ENDPOINTS)
def test_admin_endpoints_require_a_token(client, method, path):
    res = getattr(client, method)(path, params={"user_id": 1})
    assert res.status_code == 401


def test_promote_requires_a_token(client):
    res = client.post("/admin/promote", params={"user_id": 1}, json={"code": ADMIN_CODE})
    assert res.status_code == 401


# ---------- 2겹: require_self (남의 user_id를 쿼리에 넣기) ----------

@pytest.mark.parametrize("method,path", ADMIN_GATED_ENDPOINTS)
def test_admin_endpoints_reject_another_users_id(client, db_conn, method, path):
    """관리자 토큰을 들고 있어도, 쿼리의 user_id가 남이면 거부돼야 한다."""
    admin_id, admin_headers = _signup(client, f"u_admin_self_{method}_{abs(hash(path))}")
    _grant_admin(db_conn, admin_id)
    victim_id, _ = _signup(client, f"u_admin_victim_{method}_{abs(hash(path))}")

    res = getattr(client, method)(path, params={"user_id": victim_id}, headers=admin_headers)
    assert res.status_code == 403


# ---------- 3겹: _require_admin (일반 계정이 본인 id로 접근) ----------

@pytest.mark.parametrize("method,path", ADMIN_GATED_ENDPOINTS)
def test_admin_endpoints_reject_non_admin(client, method, path):
    user_id, headers = _signup(client, f"u_admin_plain_{method}_{abs(hash(path))}")
    res = getattr(client, method)(path, params={"user_id": user_id}, headers=headers)
    assert res.status_code == 403


# ---------- 거부가 "실제로" 막았는지 (상태 코드만으로는 부족하다) ----------

def test_non_admin_approve_does_not_change_recipe_status(client, db_conn):
    owner_id, _ = _signup(client, "u_admin_eff_owner")
    attacker_id, attacker_headers = _signup(client, "u_admin_eff_attacker")
    recipe_id = _insert_pending_recipe(db_conn, owner_id)

    res = client.post(
        f"/admin/recipes/{recipe_id}/approve",
        params={"user_id": attacker_id},
        headers=attacker_headers,
    )
    assert res.status_code == 403
    assert _recipe_status(db_conn, recipe_id) == "pending", "거부됐는데 승인이 반영되면 안 된다"


def test_non_admin_reject_does_not_delete_recipe(client, db_conn):
    """reject는 레시피를 완전히 삭제한다 - 막지 못하면 되돌릴 수 없는 피해다."""
    owner_id, _ = _signup(client, "u_admin_eff_owner2")
    attacker_id, attacker_headers = _signup(client, "u_admin_eff_attacker2")
    recipe_id = _insert_pending_recipe(db_conn, owner_id, menu_name="지워지면안되는레시피")

    res = client.post(
        f"/admin/recipes/{recipe_id}/reject",
        params={"user_id": attacker_id},
        headers=attacker_headers,
    )
    assert res.status_code == 403
    assert _recipe_status(db_conn, recipe_id) == "pending", "거부됐는데 삭제되면 안 된다"


def test_non_admin_cannot_change_ingredient_submission(client, db_conn):
    owner_id, _ = _signup(client, "u_admin_eff_owner3")
    attacker_id, attacker_headers = _signup(client, "u_admin_eff_attacker3")
    submission_id = _insert_pending_ingredient(db_conn, owner_id)

    for action in ("approve", "reject"):
        res = client.post(
            f"/admin/ingredients/{submission_id}/{action}",
            params={"user_id": attacker_id},
            headers=attacker_headers,
        )
        assert res.status_code == 403
        assert _submission_status(db_conn, submission_id) == "pending"


def test_non_admin_cannot_read_pending_queues(client, db_conn):
    """목록 조회도 막혀야 한다 - 누가 무엇을 올렸는지(username 포함) 새어나가면 안 된다."""
    owner_id, _ = _signup(client, "u_admin_leak_owner")
    _insert_pending_recipe(db_conn, owner_id, menu_name="비공개대기레시피")
    attacker_id, attacker_headers = _signup(client, "u_admin_leak_attacker")

    res = client.get("/admin/pending-recipes", params={"user_id": attacker_id}, headers=attacker_headers)
    assert res.status_code == 403
    assert "비공개대기레시피" not in res.text


# ---------- promote (ADMIN_SECRET 경로) ----------

def test_promote_with_wrong_code_returns_401_and_grants_nothing(client, db_conn, monkeypatch):
    monkeypatch.setattr(auth_agent, "ADMIN_SECRET", ADMIN_CODE)
    user_id, headers = _signup(client, "u_promote_wrong")

    res = client.post("/admin/promote", params={"user_id": user_id},
                      json={"code": "틀린코드"}, headers=headers)
    assert res.status_code == 401
    assert not _is_admin(db_conn, user_id), "코드가 틀렸는데 권한이 올라가면 안 된다"


def test_promote_with_correct_code_grants_admin(client, db_conn, monkeypatch):
    monkeypatch.setattr(auth_agent, "ADMIN_SECRET", ADMIN_CODE)
    user_id, headers = _signup(client, "u_promote_ok")

    res = client.post("/admin/promote", params={"user_id": user_id},
                      json={"code": ADMIN_CODE}, headers=headers)
    assert res.status_code == 200
    assert res.json() == {"is_admin": True}
    assert _is_admin(db_conn, user_id)


def test_promote_cannot_target_another_user(client, db_conn, monkeypatch):
    """올바른 코드를 알아도 남을 관리자로 만들 수는 없다 - 승격은 본인에게만."""
    monkeypatch.setattr(auth_agent, "ADMIN_SECRET", ADMIN_CODE)
    _, attacker_headers = _signup(client, "u_promote_attacker")
    victim_id, _ = _signup(client, "u_promote_victim")

    res = client.post("/admin/promote", params={"user_id": victim_id},
                      json={"code": ADMIN_CODE}, headers=attacker_headers)
    assert res.status_code == 403
    assert not _is_admin(db_conn, victim_id)


def test_promote_is_blocked_when_admin_secret_is_unset(client, db_conn, monkeypatch):
    """ADMIN_SECRET이 비어 있는 환경(예: .env 없이 배포)에서 빈 코드로 승격되면 안 된다."""
    monkeypatch.setattr(auth_agent, "ADMIN_SECRET", None)
    user_id, headers = _signup(client, "u_promote_nosecret")

    res = client.post("/admin/promote", params={"user_id": user_id},
                      json={"code": ""}, headers=headers)
    assert res.status_code == 401
    assert not _is_admin(db_conn, user_id)


# ---------- 관리자 정상 경로 ----------

def test_admin_can_list_and_approve_pending_recipe(client, db_conn):
    admin_id, admin_headers = _signup(client, "u_admin_happy")
    _grant_admin(db_conn, admin_id)
    owner_id, _ = _signup(client, "u_admin_happy_owner")
    recipe_id = _insert_pending_recipe(db_conn, owner_id, menu_name="승인대상레시피")

    listed = client.get("/admin/pending-recipes", params={"user_id": admin_id}, headers=admin_headers)
    assert listed.status_code == 200
    assert any(r["id"] == recipe_id for r in listed.json())

    approved = client.post(f"/admin/recipes/{recipe_id}/approve",
                           params={"user_id": admin_id}, headers=admin_headers)
    assert approved.status_code == 200
    assert _recipe_status(db_conn, recipe_id) == "approved"


def test_admin_can_reject_pending_ingredient(client, db_conn):
    admin_id, admin_headers = _signup(client, "u_admin_happy2")
    _grant_admin(db_conn, admin_id)
    owner_id, _ = _signup(client, "u_admin_happy_owner2")
    submission_id = _insert_pending_ingredient(db_conn, owner_id)

    listed = client.get("/admin/pending-ingredients", params={"user_id": admin_id}, headers=admin_headers)
    assert listed.status_code == 200
    assert any(s["id"] == submission_id for s in listed.json())

    rejected = client.post(f"/admin/ingredients/{submission_id}/reject",
                           params={"user_id": admin_id}, headers=admin_headers)
    assert rejected.status_code == 200
    assert _submission_status(db_conn, submission_id) == "rejected"
