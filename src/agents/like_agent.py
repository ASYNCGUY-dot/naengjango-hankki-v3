"""
Like Agent - 레시피 추천(좋아요) 버튼
- 로그인한 사용자가 제공되는 레시피에 "추천"을 누를 수 있다 (한 유저가 같은 레시피에 중복 추천 불가).
- 이 추천수는 나중에 유저 등록 레시피가 AI 추천 후보 풀에 들어갈지 정하는 기준으로도 쓰인다
  (recommendation_agent.py의 get_candidate_recipes에서 참조).
"""

import sqlite3
from datetime import datetime

DB_PATH = "data/app.db"


def has_liked(cur, recipe_id: int, user_id: int) -> bool:
    cur.execute(
        "SELECT id FROM recipe_likes WHERE recipe_id = ? AND user_id = ?",
        (recipe_id, user_id)
    )
    return cur.fetchone() is not None


def get_like_count(cur, recipe_id: int) -> int:
    cur.execute("SELECT COUNT(*) FROM recipe_likes WHERE recipe_id = ?", (recipe_id,))
    return cur.fetchone()[0]


def get_popular_recipes(cur, limit: int = 10) -> list[dict]:
    """좋아요(추천)가 많은 순으로 승인된 레시피를 가져온다.
    "즐겨찾기" 화면의 "요즘 인기 있는 레시피" 섹션에서 쓴다(2026-07-21, #req5)."""
    cur.execute(
        """
        SELECT r.id, r.menu_name, r.category, r.calorie, COUNT(l.id) AS like_count
        FROM recipes r
        JOIN recipe_likes l ON l.recipe_id = r.id
        WHERE r.status = 'approved'
        GROUP BY r.id, r.menu_name, r.category, r.calorie
        ORDER BY like_count DESC, r.menu_name
        LIMIT ?
        """,
        (limit,)
    )
    rows = cur.fetchall()
    return [
        {"id": r[0], "menu_name": r[1], "category": r[2], "calorie": r[3], "like_count": r[4]}
        for r in rows
    ]


def toggle_like(cur, recipe_id: int, user_id: int) -> bool:
    """지금 상태의 반대로 바꾸고, 바뀐 뒤의 상태(True=추천함)를 반환한다."""
    if has_liked(cur, recipe_id, user_id):
        cur.execute(
            "DELETE FROM recipe_likes WHERE recipe_id = ? AND user_id = ?",
            (recipe_id, user_id)
        )
        return False
    cur.execute(
        "INSERT INTO recipe_likes (recipe_id, user_id, created_at) VALUES (?, ?, ?)",
        (recipe_id, user_id, datetime.now().isoformat())
    )
    return True


if __name__ == "__main__":
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    cur.execute("SELECT id, menu_name FROM recipes LIMIT 1")
    row = cur.fetchone()
    if row is None:
        print("recipes 테이블에 데이터가 없습니다. 먼저 레시피를 채워주세요.")
    else:
        recipe_id, menu_name = row
        test_user_id = 14
        print(f"테스트 레시피: [{recipe_id}] {menu_name} / 테스트 계정 user_id={test_user_id}\n")

        cur.execute("DELETE FROM recipe_likes WHERE recipe_id = ? AND user_id = ?", (recipe_id, test_user_id))
        conn.commit()

        print("추천 전 개수:", get_like_count(cur, recipe_id))
        state = toggle_like(cur, recipe_id, test_user_id)
        conn.commit()
        print(f"추천 토글 -> 추천함: {state}, 개수: {get_like_count(cur, recipe_id)}")

        state = toggle_like(cur, recipe_id, test_user_id)
        conn.commit()
        print(f"다시 토글 -> 추천함: {state} (False면 취소된 것), 개수: {get_like_count(cur, recipe_id)}")

    conn.close()
