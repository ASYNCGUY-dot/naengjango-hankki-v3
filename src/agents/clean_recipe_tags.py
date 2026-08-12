"""
Clean Recipe Tags [1회성 정리 스크립트] (#68)
- 문제: tagging_agent.py의 extract_ingredient_names()가 재료 텍스트를 "첫 숫자가 나오는
        지점까지만" 잘라내다 보니, "돼지고기(50g)" 같은 표기에서 여는 괄호 "(" 가 안 닫힌 채
        "돼지고기(" 로 저장되거나, "재료 돼지고기(삼겹살 200g)"처럼 섹션 라벨("재료 ", "육수 ",
        "[주재료]" 등)이 재료명 앞에 그대로 붙어 남는 경우가 실제 DB에서 다수 확인됐다
        (recipe_tags의 tag_type='ingredient' 고유값 2,444개 중 1,129개, 약 46%).
- 이 스크립트는 이미 저장된 recipe_tags만 정리한다. recipes/reviews/recipe_ingredients
  테이블은 전혀 건드리지 않는다 - tagging_agent.py를 처음부터 다시 실행하면 그 테이블들이
  전부 삭제되고 원본 JSON에서 새로 채워지는데, 그러면 그 사이에 쌓인 유저 등록 레시피와
  후기가 전부 사라진다. 그래서 "재정제"는 반드시 이 방식(기존 값만 UPDATE)으로 한다.
- tagging_agent.py의 clean_ingredient_name()과 같은 규칙을 그대로 재사용해서, 앞으로 새
  레시피가 들어올 때도(태깅 시점에 이미 정리됨) 같은 기준을 유지한다.
"""

import sqlite3
import sys
import os

sys.path.append(os.path.dirname(__file__))
from tagging_agent import clean_ingredient_name, DB_PATH


def clean_existing_ingredient_tags(cur) -> dict:
    """
    recipe_tags에서 tag_type='ingredient'인 행을 모두 읽어 clean_ingredient_name()으로
    다시 정리하고, 값이 바뀐 것만 UPDATE한다. 정리 후 같은 (recipe_id, tag_value)가
    중복되면(예: "돼지고기(50g)"와 "돼지고기(등심 50g)"이 둘 다 "돼지고기"로 정리되는 경우)
    중복 행은 지운다.
    반환: {"checked": 검사한 행 수, "updated": 값이 바뀐 행 수, "emptied": 정리 후 빈 문자열이
           된 행 수(삭제됨), "duplicates_removed": 정리 후 중복이라 지운 행 수}
    """
    cur.execute("SELECT id, recipe_id, tag_value FROM recipe_tags WHERE tag_type = 'ingredient'")
    rows = cur.fetchall()

    updated = 0
    emptied = 0
    for row_id, recipe_id, tag_value in rows:
        cleaned = clean_ingredient_name(tag_value)
        if cleaned == tag_value:
            continue
        if not cleaned:
            # 정리했더니 아무것도 안 남으면(극히 드문 경우) 의미 없는 태그이므로 지운다.
            cur.execute("DELETE FROM recipe_tags WHERE id = ?", (row_id,))
            emptied += 1
            continue
        cur.execute("UPDATE recipe_tags SET tag_value = ? WHERE id = ?", (cleaned, row_id))
        updated += 1

    # 정리 후 같은 레시피 안에 완전히 같은 재료명이 중복될 수 있어 하나만 남기고 지운다.
    cur.execute("""
        DELETE FROM recipe_tags
        WHERE tag_type = 'ingredient' AND id NOT IN (
            SELECT MIN(id) FROM recipe_tags
            WHERE tag_type = 'ingredient'
            GROUP BY recipe_id, tag_value
        )
    """)
    duplicates_removed = cur.rowcount if cur.rowcount and cur.rowcount > 0 else 0

    return {
        "checked": len(rows),
        "updated": updated,
        "emptied": emptied,
        "duplicates_removed": duplicates_removed,
    }


if __name__ == "__main__":
    print("주의: 실행 전 Streamlit을 완전히 종료했는지 확인하세요 (동시 접근 시 DB 손상 위험).")
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    # 미리보기: 실제로 몇 개가 바뀌는지 몇 개 예시와 함께 보여준다.
    cur.execute("SELECT DISTINCT tag_value FROM recipe_tags WHERE tag_type = 'ingredient'")
    before_samples = [v[0] for v in cur.fetchall() if clean_ingredient_name(v[0]) != v[0]][:10]
    print(f"\n정리될 값 예시 (최대 10개):")
    for v in before_samples:
        print(f"  {v!r} -> {clean_ingredient_name(v)!r}")

    result = clean_existing_ingredient_tags(cur)
    conn.commit()

    print(f"\n검사한 행: {result['checked']}개")
    print(f"정리해서 수정한 행: {result['updated']}개")
    print(f"정리 후 빈 값이라 삭제한 행: {result['emptied']}개")
    print(f"정리 후 중복이라 삭제한 행: {result['duplicates_removed']}개")

    conn.close()
    print("\n완료. app.py를 다시 실행해서 재료 매칭이 잘 되는지 확인하세요.")
