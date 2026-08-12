"""
Ingredient Favorite Agent [확장] - 재료 즐겨찾기 (#50)
- 레시피 즐겨찾기(favorite_agent.py, favorites 테이블)와는 완전히 별개의 기능/테이블이다.
- ingredient_catalog(재료 카탈로그)의 food_code를 기준으로 즐겨찾기한다.
"""

import sqlite3
from datetime import datetime

DB_PATH = "data/app.db"


def is_ingredient_favorited(cur, user_id: int, food_code: str) -> bool:
    cur.execute(
        "SELECT id FROM ingredient_favorites WHERE user_id = ? AND food_code = ?",
        (user_id, food_code)
    )
    return cur.fetchone() is not None


def add_ingredient_favorite(cur, user_id: int, food_code: str):
    if is_ingredient_favorited(cur, user_id, food_code):
        return
    cur.execute(
        "INSERT INTO ingredient_favorites (user_id, food_code, created_at) VALUES (?, ?, ?)",
        (user_id, food_code, datetime.now().isoformat())
    )


def remove_ingredient_favorite(cur, user_id: int, food_code: str):
    cur.execute(
        "DELETE FROM ingredient_favorites WHERE user_id = ? AND food_code = ?",
        (user_id, food_code)
    )


def toggle_ingredient_favorite(cur, user_id: int, food_code: str) -> bool:
    """즐겨찾기 상태를 뒤집고, 뒤집은 후의 상태(True=즐겨찾기됨)를 반환한다."""
    if is_ingredient_favorited(cur, user_id, food_code):
        remove_ingredient_favorite(cur, user_id, food_code)
        return False
    add_ingredient_favorite(cur, user_id, food_code)
    return True


def get_favorite_ingredients(cur, user_id: int) -> list[dict]:
    """즐겨찾기한 재료들을 ingredient_catalog와 조인해서, 표시에 필요한 정보와 함께 가져온다."""
    cur.execute("""
        SELECT c.food_code, c.name, c.db_group, c.energy_kcal, c.carbs_g, c.protein_g,
               c.fat_g, c.sodium_mg, c.calcium_mg, c.iron_mg, c.potassium_mg,
               c.vitamin_c_mg, c.vitamin_a_ug, c.zinc_mg
        FROM ingredient_favorites f
        JOIN ingredient_catalog c ON c.food_code = f.food_code
        WHERE f.user_id = ?
        ORDER BY f.created_at DESC
    """, (user_id,))
    columns = [
        "food_code", "name", "db_group", "energy_kcal", "carbs_g", "protein_g",
        "fat_g", "sodium_mg", "calcium_mg", "iron_mg", "potassium_mg",
        "vitamin_c_mg", "vitamin_a_ug", "zinc_mg",
    ]
    return [dict(zip(columns, row)) for row in cur.fetchall()]


if __name__ == "__main__":
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    test_user_id = 14
    cur.execute("SELECT food_code FROM ingredient_catalog LIMIT 1")
    row = cur.fetchone()
    if row is None:
        print("ingredient_catalog가 비어있어서 테스트를 건너뜁니다 (수집 스크립트를 먼저 실행하세요).")
    else:
        test_food_code = row[0]
        cur.execute("DELETE FROM ingredient_favorites WHERE user_id = ?", (test_user_id,))
        conn.commit()

        state1 = toggle_ingredient_favorite(cur, test_user_id, test_food_code)
        conn.commit()
        print(f"토글1: {state1} (True여야 정상)")

        state2 = toggle_ingredient_favorite(cur, test_user_id, test_food_code)
        conn.commit()
        print(f"토글2: {state2} (False여야 정상)")

        add_ingredient_favorite(cur, test_user_id, test_food_code)
        conn.commit()
        print("\n--- 즐겨찾기한 재료 ---")
        for ing in get_favorite_ingredients(cur, test_user_id):
            print(f"  {ing['name']} ({ing['energy_kcal']}kcal)")

    conn.close()
