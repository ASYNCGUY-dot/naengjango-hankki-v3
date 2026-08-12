"""
Ingredient Submission Agent [확장] - 유저가 재료 영양/가격 정보 등록 (#34)
- 공식 API(식품영양성분DB, KAMIS)에 없는 재료명에 대해, 유저가 직접 영양성분/가격 정보를
  등록해서 다른 유저들도 볼 수 있는 공유 데이터로 만든다.
- 신뢰성 원칙: 이미 공식 API에서 정확히 매칭되거나, 이미 승인된 유저 등록 정보가 있는
  재료명이면("중복") 새 등록은 바로 반영되지 않고 관리자 승인을 거쳐야 한다.
  기존에 전혀 없던 새 재료명이면 관리자 허가 없이 바로 반영된다.
- ingredient_agent.match_nutrition()과 price_agent는 살아있는 API를 매번 호출하는 함수라서
  여기서는 "정확히 일치하는 공식 데이터가 있는지"만 가볍게 확인하고, 결과 자체는 이 테이블에만
  저장한다 (공식 DB에 실제로 쓰지 않음 - 우리가 통제할 수 있는 건 이 테이블뿐이다).
"""

import sqlite3
from datetime import datetime

DB_PATH = "data/app.db"


def _normalize_name(name: str) -> str:
    return name.strip().replace(" ", "").lower()


def approved_entry_exists(cur, ingredient_name: str) -> bool:
    """이미 승인된 유저 등록 정보가 있는지만 확인한다 (공식 API 존재 여부는 호출 비용이 있어 별도 처리)."""
    cur.execute("SELECT ingredient_name FROM ingredient_submissions WHERE status = 'approved'")
    target = _normalize_name(ingredient_name)
    return any(_normalize_name(row[0] or "") == target for row in cur.fetchall())


def submit_ingredient_info(
    cur,
    user_id: int,
    ingredient_name: str,
    calorie: float | None,
    carbs_g: float | None,
    protein_g: float | None,
    fat_g: float | None,
    sodium_mg: float | None,
    price_per_100g: float | None,
    official_match_exists: bool = False,
) -> str:
    """
    새 재료 정보를 등록한다. official_match_exists(공식 API에 이미 정확히 있는 재료인지)나
    이미 승인된 유저 등록이 있으면 status="pending", 완전히 새로운 이름이면 "approved".
    반환값: 최종 status
    """
    is_duplicate = official_match_exists or approved_entry_exists(cur, ingredient_name)
    status = "pending" if is_duplicate else "approved"

    cur.execute("""
        INSERT INTO ingredient_submissions
            (ingredient_name, submitted_by, calorie, carbs_g, protein_g, fat_g, sodium_mg,
             price_per_100g, status, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        ingredient_name.strip(), user_id, calorie, carbs_g, protein_g, fat_g, sodium_mg,
        price_per_100g, status, datetime.now().isoformat()
    ))
    return status


def get_approved_ingredient(cur, ingredient_name: str) -> dict | None:
    """레시피 화면에서 영양가이드를 보여줄 때, 공식 API보다 먼저 확인해볼 유저 등록 데이터."""
    cur.execute(
        "SELECT ingredient_name, calorie, carbs_g, protein_g, fat_g, sodium_mg, price_per_100g "
        "FROM ingredient_submissions WHERE status = 'approved'"
    )
    target = _normalize_name(ingredient_name)
    for row in cur.fetchall():
        if _normalize_name(row[0] or "") == target:
            return {
                "ingredient_name": row[0], "calorie": row[1], "carbs_g": row[2],
                "protein_g": row[3], "fat_g": row[4], "sodium_mg": row[5], "price_per_100g": row[6],
            }
    return None


def update_ingredient_submission(
    cur,
    submission_id: int,
    user_id: int,
    ingredient_name: str,
    calorie: float | None,
    carbs_g: float | None,
    protein_g: float | None,
    fat_g: float | None,
    sodium_mg: float | None,
    price_per_100g: float | None,
) -> str | None:
    """
    본인이 등록한 재료 정보를 수정한다 (기존에는 삭제 후 재등록만 가능했음).
    이름을 다른(자기 자신이 아닌) 승인된 항목과 겹치게 바꾸면 다시 관리자 승인 대기로 바뀐다.
    본인 소유가 아니면 None을 반환한다.
    """
    cur.execute("SELECT id FROM ingredient_submissions WHERE id = ? AND submitted_by = ?", (submission_id, user_id))
    if cur.fetchone() is None:
        return None

    cur.execute(
        "SELECT id, ingredient_name FROM ingredient_submissions WHERE status = 'approved' AND id != ?",
        (submission_id,)
    )
    target = _normalize_name(ingredient_name)
    is_duplicate = any(_normalize_name(row[1] or "") == target for row in cur.fetchall())
    status = "pending" if is_duplicate else "approved"

    cur.execute("""
        UPDATE ingredient_submissions
        SET ingredient_name = ?, calorie = ?, carbs_g = ?, protein_g = ?, fat_g = ?,
            sodium_mg = ?, price_per_100g = ?, status = ?, reviewed_at = NULL
        WHERE id = ?
    """, (
        ingredient_name.strip(), calorie, carbs_g, protein_g, fat_g,
        sodium_mg, price_per_100g, status, submission_id
    ))
    return status


def get_ingredient_submission_detail(cur, submission_id: int, user_id: int) -> dict | None:
    """수정 폼에 미리 채워 넣을 수 있도록, 본인이 등록한 재료 정보 하나를 가져온다."""
    cur.execute("""
        SELECT ingredient_name, calorie, carbs_g, protein_g, fat_g, sodium_mg, price_per_100g
        FROM ingredient_submissions WHERE id = ? AND submitted_by = ?
    """, (submission_id, user_id))
    row = cur.fetchone()
    if row is None:
        return None
    keys = ["ingredient_name", "calorie", "carbs_g", "protein_g", "fat_g", "sodium_mg", "price_per_100g"]
    return dict(zip(keys, row))


def get_my_ingredient_submissions(cur, user_id: int) -> list[dict]:
    cur.execute("""
        SELECT id, ingredient_name, calorie, status FROM ingredient_submissions
        WHERE submitted_by = ? ORDER BY id DESC
    """, (user_id,))
    rows = cur.fetchall()
    return [{"id": r[0], "ingredient_name": r[1], "calorie": r[2], "status": r[3]} for r in rows]


# ---------- 관리자용: 승인 대기 재료 처리 (#36) ----------
def get_pending_ingredients(cur) -> list[dict]:
    cur.execute("""
        SELECT s.id, s.ingredient_name, s.calorie, s.carbs_g, s.protein_g, s.fat_g,
               s.sodium_mg, s.price_per_100g, u.username
        FROM ingredient_submissions s
        LEFT JOIN users u ON u.id = s.submitted_by
        WHERE s.status = 'pending'
        ORDER BY s.id ASC
    """)
    rows = cur.fetchall()
    return [
        {
            "id": r[0], "ingredient_name": r[1], "calorie": r[2], "carbs_g": r[3],
            "protein_g": r[4], "fat_g": r[5], "sodium_mg": r[6], "price_per_100g": r[7],
            "username": r[8] or "(알 수 없음)",
        }
        for r in rows
    ]


def approve_ingredient(cur, submission_id: int):
    """승인하면, 같은 이름으로 이전에 승인돼 있던 정보는 replaced로 내리고 이번 것만 approved로 남긴다."""
    cur.execute("SELECT ingredient_name FROM ingredient_submissions WHERE id = ?", (submission_id,))
    row = cur.fetchone()
    if row is None:
        return
    name = row[0]

    cur.execute("SELECT id, ingredient_name FROM ingredient_submissions WHERE status = 'approved'")
    target = _normalize_name(name)
    for old_id, old_name in cur.fetchall():
        if _normalize_name(old_name or "") == target:
            cur.execute("UPDATE ingredient_submissions SET status = 'replaced' WHERE id = ?", (old_id,))

    cur.execute(
        "UPDATE ingredient_submissions SET status = 'approved', reviewed_at = ? WHERE id = ?",
        (datetime.now().isoformat(), submission_id)
    )


def reject_ingredient(cur, submission_id: int):
    cur.execute(
        "UPDATE ingredient_submissions SET status = 'rejected', reviewed_at = ? WHERE id = ?",
        (datetime.now().isoformat(), submission_id)
    )


if __name__ == "__main__":
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    test_user_id = 14
    cur.execute("DELETE FROM ingredient_submissions WHERE submitted_by = ?", (test_user_id,))
    conn.commit()

    status1 = submit_ingredient_info(
        cur, test_user_id, "테스트재료A", 120, 20, 5, 2, 100, 350
    )
    conn.commit()
    print(f"신규 재료명 등록 -> status={status1} (approved여야 정상)")

    status2 = submit_ingredient_info(
        cur, test_user_id, "테스트재료A", 130, 22, 6, 2, 110, 360
    )
    conn.commit()
    print(f"같은 이름 재등록 -> status={status2} (pending이어야 정상)")

    print("\n--- 내 등록 목록 ---")
    for s in get_my_ingredient_submissions(cur, test_user_id):
        print(f"  [{s['id']}] {s['ingredient_name']} ({s['calorie']}kcal) - {s['status']}")

    print("\n--- 승인된 재료 조회 ---")
    print(get_approved_ingredient(cur, "테스트재료A"))

    conn.close()
