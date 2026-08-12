"""
Pantry Agent [확장] - "내 냉장고" (로그인 유저의 보유 재료 등록)
- 역할: 매번 재료를 텍스트로 입력하지 않아도 되도록, 로그인한 유저가 자주 쓰는 재료를
        유통기한과 함께 미리 등록해두고 재사용할 수 있게 한다.
- 기존 스키마에 이미 있던 ingredients 테이블(id, user_id, name, source_type, expiry_date)을 그대로 쓴다.
- 유통기한이 있으면 Safety Agent의 임박 안내와도 자연스럽게 연결된다 (지침 8번: 유통기한 확인).
"""

import sqlite3

DB_PATH = "data/app.db"


def add_pantry_ingredient(cur, user_id: int, name: str, expiry_date: str | None = None):
    """같은 이름이 이미 있으면 유통기한만 갱신하고, 없으면 새로 추가한다 (중복 방지)."""
    cur.execute(
        "SELECT id FROM ingredients WHERE user_id = ? AND name = ?",
        (user_id, name)
    )
    existing = cur.fetchone()
    if existing:
        cur.execute(
            "UPDATE ingredients SET expiry_date = ? WHERE id = ?",
            (expiry_date, existing[0])
        )
    else:
        cur.execute(
            "INSERT INTO ingredients (user_id, name, source_type, expiry_date) VALUES (?, ?, ?, ?)",
            (user_id, name, "사용자입력", expiry_date)
        )


def remove_pantry_ingredient(cur, ingredient_id: int, user_id: int):
    """user_id까지 같이 확인해서, 다른 사람의 재료를 실수로 지우는 일이 없게 한다."""
    cur.execute(
        "DELETE FROM ingredients WHERE id = ? AND user_id = ?",
        (ingredient_id, user_id)
    )


def update_pantry_expiry(cur, ingredient_id: int, user_id: int, expiry_date: str | None) -> bool:
    """보유 재료의 유통기한만 갱신한다 (2026-07-19 냉장고 화면 개편 - 목록에서 바로 수정).
    remove와 같은 이유로 user_id까지 확인하고, 본인 재료가 아니면 False를 돌려준다."""
    cur.execute(
        "SELECT id FROM ingredients WHERE id = ? AND user_id = ?",
        (ingredient_id, user_id)
    )
    if cur.fetchone() is None:
        return False
    cur.execute(
        "UPDATE ingredients SET expiry_date = ? WHERE id = ?",
        (expiry_date, ingredient_id)
    )
    return True


def get_pantry_ingredients(cur, user_id: int) -> list[dict]:
    """유통기한이 가까운 순으로 정렬한다 (NULL은 맨 뒤로)."""
    cur.execute("""
        SELECT id, name, expiry_date FROM ingredients
        WHERE user_id = ?
        ORDER BY (expiry_date IS NULL), expiry_date ASC
    """, (user_id,))
    rows = cur.fetchall()
    return [{"id": r[0], "name": r[1], "expiry_date": r[2]} for r in rows]


if __name__ == "__main__":
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    test_user_id = 14  # auth_agent 테스트로 만든 계정 재사용
    cur.execute("DELETE FROM ingredients WHERE user_id = ?", (test_user_id,))
    conn.commit()

    add_pantry_ingredient(cur, test_user_id, "두부", "2026-07-15")
    add_pantry_ingredient(cur, test_user_id, "양파", None)
    add_pantry_ingredient(cur, test_user_id, "계란", "2026-07-10")
    conn.commit()

    print("--- 내 냉장고 (유통기한 가까운 순) ---")
    for item in get_pantry_ingredients(cur, test_user_id):
        print(f"  [{item['id']}] {item['name']} (유통기한: {item['expiry_date'] or '미입력'})")

    # 같은 이름 다시 등록하면 갱신되는지 확인
    add_pantry_ingredient(cur, test_user_id, "두부", "2026-07-20")
    conn.commit()
    print("\n두부 유통기한 갱신 후:")
    for item in get_pantry_ingredients(cur, test_user_id):
        if item["name"] == "두부":
            print(f"  [{item['id']}] {item['name']} (유통기한: {item['expiry_date']})")

    # 삭제 테스트
    ids = [i["id"] for i in get_pantry_ingredients(cur, test_user_id) if i["name"] == "양파"]
    remove_pantry_ingredient(cur, ids[0], test_user_id)
    conn.commit()
    print("\n양파 삭제 후 남은 개수:", len(get_pantry_ingredients(cur, test_user_id)))

    conn.close()
