"""
User Recipe Agent [확장] - 유저가 직접 레시피 등록
- 로그인한 유저가 메뉴명/재료/조리순서를 입력하면, 기존 공공데이터 레시피와 같은 테이블
  구조(recipes/recipe_tags/recipe_ingredients)에 저장한다. 그래야 영양가이드/가격등급/
  분량환산 같은 다른 기능들이 유저 레시피에도 그대로 동작한다.
- Tagging Agent의 insert_recipe_with_tags()를 재사용한다 (source_api="user", submitted_by=user_id).
- 재료 텍스트는 Portion Agent가 이해하는 형식("이름 수량단위", 콤마로 구분)과 동일하게 입력받는다.
- 신뢰성 원칙: 유저가 등록한 레시피는 검증되지 않은 데이터라서, recommendation_agent.py의
  get_candidate_recipes()가 추천(좋아요) USER_RECIPE_MIN_LIKES회 이상 쌓이고 status='approved'인
  것만 다른 사용자에게 추천한다. 등록한 본인은 "내 레시피" 목록에서 상태와 무관하게 확인 가능하다.
- 중복 이름 처리(#35): 이미 같은 메뉴명(대소문자/공백 무시)의 승인된(approved) 레시피가 있으면,
  새로 등록한 레시피는 바로 공개되지 않고 status='pending'으로 저장되어 관리자 승인을 거쳐야 한다.
  기존에 없던 새 이름이면 바로 status='approved'로 저장된다 (관리자 허가 불필요).
"""

import json
import sqlite3

from tagging_agent import insert_recipe_with_tags, tag_allergy, tag_nutrition_group, extract_ingredient_names
from portion_agent import parse_ingredients_with_amounts

DB_PATH = "data/app.db"


def _normalize_name(name: str) -> str:
    return name.strip().replace(" ", "").lower()


def recipe_name_exists(cur, menu_name: str, exclude_recipe_id: int | None = None) -> bool:
    """
    이미 승인된 레시피 중에 같은 이름(공백/대소문자 무시)이 있는지 확인한다.
    exclude_recipe_id를 주면 그 레시피 자신은 비교 대상에서 뺀다 (수정 시 자기 자신과 비교되는 것 방지).
    """
    cur.execute("SELECT id, menu_name FROM recipes WHERE status = 'approved'")
    target = _normalize_name(menu_name)
    return any(
        _normalize_name(row[1] or "") == target
        for row in cur.fetchall()
        if exclude_recipe_id is None or row[0] != exclude_recipe_id
    )


def submit_user_recipe(
    cur,
    user_id: int,
    menu_name: str,
    category: str,
    calorie: float | None,
    ingredients_text: str,
    steps_text: str,
) -> tuple[int, str]:
    """
    유저 입력을 공공데이터 API와 같은 필드 이름(RCP_NM 등)으로 바꿔서
    insert_recipe_with_tags()에 그대로 넘긴다. 그 다음 재료 수량도 recipe_ingredients에 저장한다.
    반환값: (recipe_id, status) - status는 "approved" 또는 "pending"
    """
    status = "pending" if recipe_name_exists(cur, menu_name) else "approved"

    steps_list = [s.strip() for s in steps_text.split("\n") if s.strip()]

    fake_api_recipe = {
        "RCP_NM": menu_name,
        "RCP_WAY2": "사용자 등록",
        "RCP_PAT2": category or "미분류",
        "INFO_ENG": calorie,
        "RCP_PARTS_DTLS": ingredients_text,
    }
    for i, text in enumerate(steps_list, start=1):
        fake_api_recipe[f"MANUAL{i:02d}"] = text

    recipe_id = insert_recipe_with_tags(
        cur, fake_api_recipe, source_api="user", submitted_by=user_id, status=status
    )

    # 재료 수량도 저장해야 분량 환산/영양가이드/가격등급이 다른 레시피와 동일하게 동작한다.
    base_servings, items = parse_ingredients_with_amounts(ingredients_text)
    for item in items:
        cur.execute(
            "INSERT INTO recipe_ingredients (recipe_id, name, amount, unit, raw_text, base_servings) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (recipe_id, item["name"], item["amount"], item["unit"], item["raw_text"], base_servings)
        )

    return recipe_id, status


def update_user_recipe(
    cur,
    recipe_id: int,
    user_id: int,
    menu_name: str,
    category: str,
    calorie: float | None,
    ingredients_text: str,
    steps_text: str,
) -> str | None:
    """
    본인이 등록한 레시피 내용을 수정한다 (기존에는 삭제 후 재등록만 가능했음).
    recipe_id를 그대로 유지해서 이미 쌓인 즐겨찾기/추천(좋아요)이 끊기지 않도록 한다.
    메뉴명을 자기 자신이 아닌 다른 승인된 레시피와 겹치게 바꾸면, 다시 관리자 승인 대기(pending)로 바뀐다.
    본인 소유가 아니면 None을 반환한다.
    """
    cur.execute("SELECT id FROM recipes WHERE id = ? AND submitted_by = ?", (recipe_id, user_id))
    if cur.fetchone() is None:
        return None

    status = "pending" if recipe_name_exists(cur, menu_name, exclude_recipe_id=recipe_id) else "approved"

    steps_list = [s.strip() for s in steps_text.split("\n") if s.strip()]
    fake_api_recipe = {
        "RCP_NM": menu_name,
        "RCP_WAY2": "사용자 등록",
        "RCP_PAT2": category or "미분류",
        "INFO_ENG": calorie,
        "RCP_PARTS_DTLS": ingredients_text,
    }
    for i, text in enumerate(steps_list, start=1):
        fake_api_recipe[f"MANUAL{i:02d}"] = text

    nutrients = {
        "energy_kcal": calorie, "carbs_g": None, "protein_g": None, "fat_g": None, "sodium_mg": None,
    }
    steps_json = json.dumps([{"step": i, "text": t, "image": None} for i, t in enumerate(steps_list, start=1)],
                             ensure_ascii=False)

    cur.execute("""
        UPDATE recipes SET menu_name = ?, category = ?, calorie = ?, nutrients_json = ?,
                            steps_json = ?, status = ?
        WHERE id = ?
    """, (menu_name, category or "미분류", calorie, json.dumps(nutrients, ensure_ascii=False),
          steps_json, status, recipe_id))

    # 태그와 재료 수량은 기존 걸 지우고 새로 계산해서 다시 넣는다 (내용이 바뀌었을 수 있으므로).
    cur.execute("DELETE FROM recipe_tags WHERE recipe_id = ?", (recipe_id,))
    cur.execute("DELETE FROM recipe_ingredients WHERE recipe_id = ?", (recipe_id,))

    cur.execute("INSERT INTO recipe_tags (recipe_id, tag_type, tag_value) VALUES (?, ?, ?)",
                (recipe_id, "category", category or "미분류"))
    for allergen in tag_allergy(ingredients_text):
        cur.execute("INSERT INTO recipe_tags (recipe_id, tag_type, tag_value) VALUES (?, ?, ?)",
                    (recipe_id, "allergy", allergen))
    nutrition_tag = tag_nutrition_group(calorie, None, None, None)
    cur.execute("INSERT INTO recipe_tags (recipe_id, tag_type, tag_value) VALUES (?, ?, ?)",
                (recipe_id, "nutrition_group", nutrition_tag))
    for name in extract_ingredient_names(ingredients_text, menu_name):
        cur.execute("INSERT INTO recipe_tags (recipe_id, tag_type, tag_value) VALUES (?, ?, ?)",
                    (recipe_id, "ingredient", name))

    base_servings, items = parse_ingredients_with_amounts(ingredients_text)
    for item in items:
        cur.execute(
            "INSERT INTO recipe_ingredients (recipe_id, name, amount, unit, raw_text, base_servings) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (recipe_id, item["name"], item["amount"], item["unit"], item["raw_text"], base_servings)
        )

    return status


def get_my_recipes(cur, user_id: int) -> list[dict]:
    """이 유저가 등록한 레시피와, 각 레시피가 지금까지 받은 추천(좋아요) 수/승인 상태를 함께 가져온다."""
    cur.execute("""
        SELECT r.id, r.menu_name, r.category, r.calorie, r.status,
               (SELECT COUNT(*) FROM recipe_likes WHERE recipe_id = r.id) AS like_count
        FROM recipes r
        WHERE r.submitted_by = ?
        ORDER BY r.id DESC
    """, (user_id,))
    rows = cur.fetchall()
    return [
        {"id": r[0], "menu_name": r[1], "category": r[2], "calorie": r[3], "status": r[4], "like_count": r[5]}
        for r in rows
    ]


def get_my_recipe_detail(cur, recipe_id: int, user_id: int) -> dict | None:
    """
    수정 폼에 미리 채워 넣을 수 있도록, 본인이 등록한 레시피 하나를 원래 입력 형식(폼 텍스트)으로
    복원해서 가져온다. 재료는 recipe_ingredients.raw_text를 콤마로 이어 붙이고,
    조리 단계는 steps_json의 text만 줄바꿈으로 이어 붙인다.
    """
    cur.execute(
        "SELECT menu_name, category, calorie, steps_json FROM recipes WHERE id = ? AND submitted_by = ?",
        (recipe_id, user_id)
    )
    row = cur.fetchone()
    if row is None:
        return None
    menu_name, category, calorie, steps_json = row

    cur.execute("SELECT raw_text FROM recipe_ingredients WHERE recipe_id = ?", (recipe_id,))
    ingredients_text = ", ".join(r[0] for r in cur.fetchall() if r[0])

    try:
        steps = json.loads(steps_json) if steps_json else []
    except (json.JSONDecodeError, TypeError):
        steps = []
    steps_text = "\n".join(s.get("text", "") for s in steps)

    return {
        "menu_name": menu_name, "category": category, "calorie": calorie,
        "ingredients_text": ingredients_text, "steps_text": steps_text,
    }


def delete_my_recipe(cur, recipe_id: int, user_id: int):
    """본인이 등록한 레시피만 지울 수 있도록 submitted_by까지 함께 확인한다."""
    cur.execute("SELECT id FROM recipes WHERE id = ? AND submitted_by = ?", (recipe_id, user_id))
    if cur.fetchone() is None:
        return False
    cur.execute("DELETE FROM recipe_tags WHERE recipe_id = ?", (recipe_id,))
    cur.execute("DELETE FROM recipe_ingredients WHERE recipe_id = ?", (recipe_id,))
    cur.execute("DELETE FROM recipe_likes WHERE recipe_id = ?", (recipe_id,))
    cur.execute("DELETE FROM favorites WHERE recipe_id = ?", (recipe_id,))
    cur.execute("DELETE FROM recipes WHERE id = ?", (recipe_id,))
    return True


# ---------- 관리자용: 승인 대기 레시피 처리 (#36) ----------
def get_pending_recipes(cur) -> list[dict]:
    cur.execute("""
        SELECT r.id, r.menu_name, r.category, r.calorie, u.username
        FROM recipes r
        LEFT JOIN users u ON u.id = r.submitted_by
        WHERE r.status = 'pending'
        ORDER BY r.id ASC
    """)
    rows = cur.fetchall()
    return [
        {"id": r[0], "menu_name": r[1], "category": r[2], "calorie": r[3], "username": r[4] or "(알 수 없음)"}
        for r in rows
    ]


def approve_recipe(cur, recipe_id: int):
    cur.execute("UPDATE recipes SET status = 'approved' WHERE id = ?", (recipe_id,))


def reject_recipe(cur, recipe_id: int):
    """승인 거절은 등록 자체를 취소하는 것과 같으므로 완전히 삭제한다."""
    cur.execute("DELETE FROM recipe_tags WHERE recipe_id = ?", (recipe_id,))
    cur.execute("DELETE FROM recipe_ingredients WHERE recipe_id = ?", (recipe_id,))
    cur.execute("DELETE FROM recipes WHERE id = ?", (recipe_id,))


if __name__ == "__main__":
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    test_user_id = 14  # auth_agent 테스트로 만든 계정 재사용

    # 반복 실행해도 같은 결과가 나오도록, 이 계정이 등록한 테스트 레시피를 먼저 지운다.
    for r in get_my_recipes(cur, test_user_id):
        delete_my_recipe(cur, r["id"], test_user_id)
    conn.commit()

    recipe_id, status = submit_user_recipe(
        cur,
        test_user_id,
        menu_name="초간단 두부계란볶음",
        category="반찬",
        calorie=250,
        ingredients_text="두부 200g, 계란 2개, 대파 20g, 식용유 1큰술, 소금 약간",
        steps_text="두부를 깍둑썰기 한다\n팬에 기름을 두르고 두부를 굽는다\n계란을 풀어 넣고 대파와 함께 볶는다\n소금으로 간을 맞춘다",
    )
    conn.commit()
    print(f"레시피 등록 완료: recipe_id={recipe_id}, status={status}")

    # 같은 이름으로 한 번 더 등록하면 pending이 되는지 확인
    dup_id, dup_status = submit_user_recipe(
        cur, test_user_id, "초간단 두부계란볶음", "반찬", 250,
        "두부 200g, 계란 2개", "볶는다",
    )
    conn.commit()
    print(f"중복 이름 재등록: recipe_id={dup_id}, status={dup_status} (pending이어야 정상)")
    delete_my_recipe(cur, dup_id, test_user_id)
    conn.commit()

    print("\n--- 내 레시피 목록 ---")
    for r in get_my_recipes(cur, test_user_id):
        print(f"  [{r['id']}] {r['menu_name']} | {r['category']} | {r['calorie']}kcal | "
              f"상태 {r['status']} | 추천 {r['like_count']}회")

    # recipe_ingredients에 잘 들어갔는지도 확인
    cur.execute("SELECT name, amount, unit FROM recipe_ingredients WHERE recipe_id = ?", (recipe_id,))
    print("\n--- 저장된 재료 ---")
    for name, amount, unit in cur.fetchall():
        print(f"  {name}: {amount}{unit}")

    conn.close()
