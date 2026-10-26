"""먹었어요 → 오늘 합계, 한국 자정, 스냅샷/소유권/재시도를 HTTP 경계에서 확인한다."""

import json
from datetime import datetime, timezone
from uuid import uuid4

import pytest

from api.auth_token import issue_token
from api.routers import meals


@pytest.fixture()
def meal_user(db_conn):
    def make_user(name="meal_user"):
        cur = db_conn.cursor()
        cur.execute(
            "INSERT INTO users (username, password_hash, gender, age_group, household_size) "
            "VALUES (?, 'test', '여성', '20대', 4)", (name,),
        )
        user_id = cur.lastrowid
        token = issue_token(cur, user_id)
        return user_id, {"Authorization": f"Bearer {token}"}
    return make_user


@pytest.fixture()
def clock(monkeypatch):
    state = [datetime(2026, 10, 23, 12, 0, tzinfo=timezone.utc)]
    monkeypatch.setattr(meals, "_now", lambda: state[0])
    return state


def _body(recipe_id=1, servings=1, request_id=None):
    return {"recipe_id": recipe_id, "servings": servings, "request_id": request_id or str(uuid4())}


def _add(client, headers, **kwargs):
    response = client.post("/meals", headers=headers, json=_body(**kwargs))
    assert response.status_code == 201, response.text
    return response.json()


def _today(client, headers):
    response = client.get("/meals/today", headers=headers)
    assert response.status_code == 200, response.text
    return response.json()


def _nutrient(body, key):
    return next(row for row in body["nutrition"]["rows"] if row["key"] == key)


@pytest.mark.parametrize("method,path,body", [
    ("get", "/meals/today", None), ("post", "/meals", _body()),
    ("put", "/meals/1", {"servings": 1}), ("delete", "/meals/1", None),
])
def test_all_meal_routes_require_login(client, method, path, body):
    kwargs = {"json": body} if body is not None else {}
    assert client.request(method, path, **kwargs).status_code == 401


def test_empty_day_has_zero_bars_and_server_korean_midnight(client, meal_user, clock):
    _, headers = meal_user()
    body = _today(client, headers)
    assert body["date"] == "2026-10-23"
    assert body["timezone"] == "Asia/Seoul"
    assert body["server_now"] == "2026-10-23T21:00:00+09:00"
    assert body["next_reset_at"] == "2026-10-24T00:00:00+09:00"
    assert body["meals"] == []
    assert body["incomplete_nutrients"] == []
    assert len(body["nutrition"]["rows"]) == 6
    assert all(row["provided"] == 0 for row in body["nutrition"]["rows"])
    assert body["nutrition"]["sodium_row"]["provided"] == 0


def test_meals_add_up_by_actual_servings_and_one_person_micro(client, db_conn, meal_user, clock):
    _, headers = meal_user()
    # 2인분 레시피의 두부 200g → 1인분 100g. household_size=4와 무관하다.
    first = _add(client, headers, servings=1.5)
    _add(client, headers, recipe_id=2, servings=0.5)
    body = _today(client, headers)
    assert len(body["meals"]) == 2
    assert _nutrient(body, "protein_g")["provided"] == 17.5  # 10*1.5 + 5*0.5
    assert _nutrient(body, "calcium_mg")["provided"] == 96  # 64*1.5, not 4 people
    assert _nutrient(body, "protein_g")["target"] == 55
    assert first["recipe_name"] == "두부조림"
    assert first["consumed_at"].endswith("+00:00")
    snapshot = json.loads(db_conn.execute("SELECT nutrition_snapshot_json FROM meal_logs WHERE id = ?", (first["id"],)).fetchone()[0])
    assert snapshot["values"]["calcium_mg"] == 64


def test_same_request_deduplicates_but_new_request_can_record_same_recipe(client, db_conn, meal_user, clock):
    _, headers = meal_user()
    body = _body(servings=0.5)
    first = client.post("/meals", headers=headers, json=body)
    second = client.post("/meals", headers=headers, json=body)
    assert first.status_code == second.status_code == 201
    assert first.json() == second.json()
    _add(client, headers, servings=0.5)
    assert db_conn.execute("SELECT COUNT(*) FROM meal_logs").fetchone()[0] == 2


@pytest.mark.parametrize("change", [{"recipe_id": 2}, {"servings": 2}])
def test_same_request_with_different_payload_is_conflict(client, meal_user, change):
    _, headers = meal_user()
    body = _body()
    assert client.post("/meals", headers=headers, json=body).status_code == 201
    assert client.post("/meals", headers=headers, json={**body, **change}).status_code == 409
    assert len(_today(client, headers)["meals"]) == 1


def test_edit_changes_total_not_snapshot_or_original_request(client, db_conn, meal_user, clock):
    _, headers = meal_user()
    body = _body()
    original = client.post("/meals", headers=headers, json=body).json()
    updated = client.put(f"/meals/{original['id']}", headers=headers, json={"servings": 2.5})
    assert updated.status_code == 200
    assert updated.json()["consumed_at"] == original["consumed_at"]
    assert _nutrient(_today(client, headers), "protein_g")["provided"] == 25
    replay = client.post("/meals", headers=headers, json=body)
    assert replay.status_code == 201
    assert replay.json()["servings"] == 2.5
    assert db_conn.execute("SELECT COUNT(*) FROM meal_logs").fetchone()[0] == 1


def test_delete_removes_today_total_and_old_retry_does_not_restore_it(client, db_conn, meal_user, clock):
    _, headers = meal_user()
    body = _body()
    entry = client.post("/meals", headers=headers, json=body).json()
    deleted = client.delete(f"/meals/{entry['id']}", headers=headers)
    assert deleted.status_code == 204
    assert deleted.content == b""
    original_deleted_at = db_conn.execute("SELECT deleted_at, updated_at FROM meal_logs WHERE id = ?", (entry["id"],)).fetchone()
    clock[0] = datetime(2026, 10, 23, 13, 0, tzinfo=timezone.utc)
    assert client.delete(f"/meals/{entry['id']}", headers=headers).status_code == 204
    assert db_conn.execute("SELECT deleted_at, updated_at FROM meal_logs WHERE id = ?", (entry["id"],)).fetchone() == original_deleted_at
    assert _today(client, headers)["meals"] == []
    assert _nutrient(_today(client, headers), "protein_g")["provided"] == 0
    assert client.post("/meals", headers=headers, json=body).status_code == 409
    assert client.put(f"/meals/{entry['id']}", headers=headers, json={"servings": 2}).status_code == 404


def test_each_user_only_sees_and_changes_own_meals(client, meal_user):
    _, owner = meal_user("meal_owner")
    stranger_id, stranger = meal_user("meal_other")
    body = _body()
    owned = client.post("/meals", headers=owner, json=body).json()
    assert _today(client, stranger)["meals"] == []
    assert client.put(f"/meals/{owned['id']}", headers=stranger, json={"servings": 2}).status_code == 404
    assert client.delete(f"/meals/{owned['id']}", headers=stranger).status_code == 404
    # 같은 UUID라도 다른 사람의 기록은 서로 독립적이다.
    other = client.post("/meals", headers=stranger, json=body)
    assert other.status_code == 201
    assert other.json()["id"] != owned["id"]
    # 클라이언트 user_id 필드는 허용하지 않고 조회 쿼리도 소유권에 영향을 주지 않는다.
    assert client.post("/meals", headers=owner, json={**_body(), "user_id": stranger_id}).status_code == 422
    assert client.get(f"/meals/today?user_id={stranger_id}", headers=owner).json()["meals"][0]["id"] == owned["id"]


def test_korean_midnight_resets_totals_but_keeps_prior_day_records(client, db_conn, meal_user, clock):
    _, headers = meal_user()
    clock[0] = datetime(2026, 10, 23, 14, 59, 59, 999999, tzinfo=timezone.utc)
    previous = _add(client, headers)
    assert _today(client, headers)["date"] == "2026-10-23"
    clock[0] = datetime(2026, 10, 23, 15, 0, tzinfo=timezone.utc)
    empty = _today(client, headers)
    assert empty["date"] == "2026-10-24"
    assert empty["meals"] == []
    assert empty["next_reset_at"] == "2026-10-25T00:00:00+09:00"
    current = _add(client, headers, servings=0.5)
    assert [item["id"] for item in _today(client, headers)["meals"]] == [current["id"]]
    assert _nutrient(_today(client, headers), "protein_g")["provided"] == 5
    assert db_conn.execute("SELECT COUNT(*) FROM meal_logs WHERE deleted_at IS NULL").fetchone()[0] == 2
    # 이전 날 기록 수정/취소는 현재 날짜 합계를 바꾸지 않는다.
    assert client.put(f"/meals/{previous['id']}", headers=headers, json={"servings": 3}).status_code == 200
    assert _nutrient(_today(client, headers), "protein_g")["provided"] == 5
    assert client.delete(f"/meals/{previous['id']}", headers=headers).status_code == 204
    assert _nutrient(_today(client, headers), "protein_g")["provided"] == 5


def test_day_query_excludes_exact_next_midnight(client, db_conn, meal_user, clock):
    _, headers = meal_user()
    entry = _add(client, headers)
    db_conn.execute("UPDATE meal_logs SET consumed_at = ? WHERE id = ?", ("2026-10-23T15:00:00.000000+00:00", entry["id"]))
    assert _today(client, headers)["meals"] == []


def test_recipe_changes_do_not_rewrite_meal_snapshot_and_targets_follow_profile(client, db_conn, meal_user):
    user_id, headers = meal_user()
    _add(client, headers)
    db_conn.execute("UPDATE recipes SET menu_name = '수정한 이름', nutrients_json = ? WHERE id = 1", (json.dumps({"protein_g": 999}),))
    db_conn.execute("UPDATE ingredient_catalog SET calcium_mg = 999 WHERE name = '두부'")
    db_conn.execute("UPDATE users SET gender = '남성', medical_conditions = '고혈압' WHERE id = ?", (user_id,))
    body = _today(client, headers)
    assert body["meals"][0]["recipe_name"] == "두부조림"
    assert _nutrient(body, "protein_g")["provided"] == 10
    assert _nutrient(body, "protein_g")["target"] == 65
    assert _nutrient(body, "calcium_mg")["provided"] == 64
    assert body["nutrition"]["sodium_row"]["limit"] == 2000


def test_missing_nutrients_are_marked_incomplete_and_not_claimed_as_known_zero(client, db_conn, meal_user):
    _, headers = meal_user()
    db_conn.execute("UPDATE recipes SET nutrients_json = ? WHERE id = 2", ('{"protein_g": null, "sodium_mg": "NaN"}',))
    _add(client, headers, recipe_id=2)
    body = _today(client, headers)
    assert set(body["incomplete_nutrients"]) == set(meals.NUTRIENT_KEYS)
    assert body["nutrition"]["micro_is_partial"] is True
    snapshot = json.loads(db_conn.execute("SELECT nutrition_snapshot_json FROM meal_logs").fetchone()[0])
    assert snapshot["values"] == {}


def test_known_zero_is_not_missing_and_staples_are_partial(client, db_conn, meal_user):
    _, headers = meal_user()
    db_conn.execute("UPDATE recipes SET nutrients_json = ? WHERE id = 1", ('{"protein_g": 0, "sodium_mg": 0}',))
    db_conn.execute("DELETE FROM recipe_ingredients WHERE recipe_id = 1 AND name = '양파'")
    db_conn.execute("UPDATE ingredient_catalog SET vitamin_a_ug = 0 WHERE name = '두부'")
    _add(client, headers)
    assert _today(client, headers)["incomplete_nutrients"] == []
    db_conn.execute("INSERT INTO recipe_ingredients (recipe_id, name, amount, unit, base_servings) VALUES (1, '소금', 1, 'g', 2)")
    _add(client, headers)
    assert set(_today(client, headers)["incomplete_nutrients"]) == set(meals.MICRO_KEYS)


@pytest.mark.parametrize("value", [0, -1, 0.09, 10.01, 10**400, True, "1", "NaN", "Infinity", None])
def test_invalid_servings_are_rejected_on_create_and_update(client, meal_user, value):
    _, headers = meal_user()
    entry = _add(client, headers)
    assert client.post("/meals", headers=headers, json=_body(servings=value)).status_code == 422
    assert client.put(f"/meals/{entry['id']}", headers=headers, json={"servings": value}).status_code == 422


@pytest.mark.parametrize("value", ["NaN", "Infinity", "-Infinity"])
def test_nonstandard_nonfinite_json_is_rejected_without_serialization_error(client, meal_user, value):
    _, headers = meal_user()
    content = '{"recipe_id":1,"servings":' + value + ',"request_id":"' + str(uuid4()) + '"}'
    response = client.post("/meals", headers={**headers, "Content-Type": "application/json"}, content=content)
    assert response.status_code == 422


def test_unknown_and_other_users_pending_recipes_cannot_be_recorded(client, db_conn, meal_user):
    _, headers = meal_user()
    assert client.post("/meals", headers=headers, json=_body(recipe_id=999999)).status_code == 404
    db_conn.execute("UPDATE recipes SET status = 'pending', submitted_by = NULL WHERE id = 1")
    assert client.post("/meals", headers=headers, json=_body()).status_code == 404


def test_missing_or_invalid_request_id_cannot_create_meal(client, meal_user):
    _, headers = meal_user()
    assert client.post("/meals", headers=headers, json={"recipe_id": 1, "servings": 1}).status_code == 422
    assert client.post("/meals", headers=headers, json=_body(request_id="invalid")).status_code == 422
