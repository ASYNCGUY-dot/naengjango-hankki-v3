"""
Favorite Agent - 레시피 즐겨찾기
- 로그인한 사용자가 레시피를 즐겨찾기에 추가/삭제할 수 있다.
- DB upsert 문법 대신, 있는지 먼저 확인하고 없을 때만 넣는 방식을 쓴다 (지침: 초보자가 읽기 쉽게).
"""

import sqlite3
from datetime import datetime

DB_PATH = "data/app.db"


def is_favorited(cur, user_id: int, recipe_id: int) -> bool:
    cur.execute(
        "SELECT id FROM favorites WHERE user_id = ? AND recipe_id = ?",
        (user_id, recipe_id)
    )
    return cur.fetchone() is not None


def add_favorite(cur, user_id: int, recipe_id: int):
    """이미 즐겨찾기 되어 있으면 아무것도 하지 않는다 (중복 저장 방지)."""
    if is_favorited(cur, user_id, recipe_id):
        return
    cur.execute(
        "INSERT INTO favorites (user_id, recipe_id, created_at) VALUES (?, ?, ?)",
        (user_id, recipe_id, datetime.now().isoformat())
    )


def remove_favorite(cur, user_id: int, recipe_id: int):
    cur.execute(
        "DELETE FROM favorites WHERE user_id = ? AND recipe_id = ?",
        (user_id, recipe_id)
    )


def toggle_favorite(cur, user_id: int, recipe_id: int) -> bool:
    """지금 상태의 반대로 바꾸고, 바뀐 뒤의 상태(True=즐겨찾기됨)를 반환한다."""
    if is_favorited(cur, user_id, recipe_id):
        remove_favorite(cur, user_id, recipe_id)
        return False
    add_favorite(cur, user_id, recipe_id)
    return True


def get_favorite_recipes(cur, user_id: int) -> list[dict]:
    """이 사용자가 즐겨찾기한 레시피들을 최신순으로 가져온다."""
    cur.execute("""
        SELECT r.id, r.menu_name, r.category, r.calorie, f.created_at
        FROM favorites f
        JOIN recipes r ON r.id = f.recipe_id
        WHERE f.user_id = ?
        ORDER BY f.created_at DESC
    """, (user_id,))
    rows = cur.fetchall()
    return [
        {"id": r[0], "menu_name": r[1], "category": r[2], "calorie": r[3], "created_at": r[4]}
        for r in rows
    ]


if __name__ == "__main__":
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    cur.execute("SELECT id, menu_name FROM recipes LIMIT 2")
    rows = cur.fetchall()
    if not rows:
        print("recipes 테이블에 데이터가 없습니다. 먼저 레시피를 채워주세요.")
    else:
        test_user_id = 14  # auth_agent 테스트로 만든 계정 재사용
        print(f"테스트 계정 user_id={test_user_id}\n")

        # 반복 실행해도 같은 결과가 나오도록 기존 테스트 즐겨찾기를 지운다.
        cur.execute("DELETE FROM favorites WHERE user_id = ?", (test_user_id,))
        conn.commit()

        for recipe_id, menu_name in rows:
            state = toggle_favorite(cur, test_user_id, recipe_id)
            print(f"[{recipe_id}] {menu_name} -> 즐겨찾기 추가: {state}")
        conn.commit()

        print("\n--- 즐겨찾기 목록 ---")
        for f in get_favorite_recipes(cur, test_user_id):
            print(f"  [{f['id']}] {f['menu_name']} | {f['category']} | {f['calorie']}kcal")

        # 하나는 다시 토글해서 삭제되는지도 확인
        first_id = rows[0][0]
        state = toggle_favorite(cur, test_user_id, first_id)
        conn.commit()
        print(f"\n{rows[0][1]} 다시 토글 -> 즐겨찾기 추가: {state} (False면 삭제된 것)")
        print("남은 즐겨찾기 개수:", len(get_favorite_recipes(cur, test_user_id)))

    conn.close()
