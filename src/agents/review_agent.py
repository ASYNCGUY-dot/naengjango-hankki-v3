"""
Review Agent [선택] - 후기 저장 + 자동 요약
- 로그인한 사용자가 추천받은 레시피에 대해 별점+후기를 남길 수 있다.
- 레시피별로 쌓인 후기를 OpenAI로 요약해서 review_summaries에 캐시해둔다.
  (후기 개수가 이전과 같으면 다시 요약하지 않고 캐시를 그대로 쓴다 - 매번 LLM 호출 비용 방지)
"""

import os
import sqlite3
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
DB_PATH = "data/app.db"


def save_review(cur, recipe_id: int, user_id: int, rating: int, review_text: str, image_url: str | None = None):
    """image_url(선택)은 2026-07-18 목업 대비 재검토에서 추가한 사진 첨부 기능용 -
    기존 호출부(image_url 없이 호출)는 그대로 동작한다."""
    cur.execute(
        "INSERT INTO reviews (recipe_id, user_id, rating, review_text, created_at, image_url) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (recipe_id, user_id, rating, review_text, datetime.now().isoformat(), image_url)
    )


def get_reviews_for_recipe(cur, recipe_id: int) -> list[dict]:
    """
    username도 함께 가져온다 (#61, 후기 카드에 작성자 표시용).
    LEFT JOIN이라 탈퇴 등으로 계정이 사라져도 후기 자체는 그대로 보이고, username은 "익명"으로 처리한다.
    """
    cur.execute(
        """
        SELECT r.rating, r.review_text, r.created_at, u.username, r.image_url
        FROM reviews r
        LEFT JOIN users u ON u.id = r.user_id
        WHERE r.recipe_id = ?
        ORDER BY r.created_at DESC
        """,
        (recipe_id,)
    )
    rows = cur.fetchall()
    return [
        {"rating": r[0], "review_text": r[1], "created_at": r[2], "username": r[3] or "익명", "image_url": r[4]}
        for r in rows
    ]


def _call_openai_summary(prompt: str) -> str:
    from openai import OpenAI
    try:
        client = OpenAI(api_key=OPENAI_API_KEY)
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
        )
        return response.choices[0].message.content
    except Exception as e:
        return f"(요약 실패: {e})"


def _save_summary_cache(cur, recipe_id: int, summary: str, review_count: int):
    cur.execute("SELECT recipe_id FROM review_summaries WHERE recipe_id = ?", (recipe_id,))
    if cur.fetchone():
        cur.execute(
            "UPDATE review_summaries SET summary_text = ?, review_count = ?, updated_at = ? WHERE recipe_id = ?",
            (summary, review_count, datetime.now().isoformat(), recipe_id)
        )
    else:
        cur.execute(
            "INSERT INTO review_summaries (recipe_id, summary_text, review_count, updated_at) VALUES (?, ?, ?, ?)",
            (recipe_id, summary, review_count, datetime.now().isoformat())
        )


def summarize_reviews(cur, recipe_id: int) -> str | None:
    """
    해당 레시피의 후기를 요약한다. 후기가 하나도 없으면 None.
    이전과 후기 개수가 같으면 새로 요약하지 않고 캐시된 요약을 재사용한다.
    """
    reviews = get_reviews_for_recipe(cur, recipe_id)
    if not reviews:
        return None

    cur.execute(
        "SELECT summary_text, review_count FROM review_summaries WHERE recipe_id = ?",
        (recipe_id,)
    )
    cached = cur.fetchone()
    if cached and cached[1] == len(reviews):
        return cached[0]

    reviews_text = "\n".join(
        f"- 별점 {r['rating']}/5: {r['review_text']}" for r in reviews
    )
    prompt = f"""아래는 한 레시피에 달린 사용자 후기 목록입니다. 공통적으로 나오는 의견을
2~3개의 불릿 포인트로 요약해주세요. 각 줄은 "• "로 시작하고, 좋은 점과 아쉬운 점이 있다면
균형있게 나눠서 각각 한 줄로 적어주세요. 다른 설명 없이 불릿 목록만 출력하세요.

{reviews_text}
"""
    summary = _call_openai_summary(prompt)
    _save_summary_cache(cur, recipe_id, summary, len(reviews))
    return summary


if __name__ == "__main__":
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    cur.execute("SELECT id, menu_name FROM recipes LIMIT 1")
    row = cur.fetchone()
    if row is None:
        print("recipes 테이블에 데이터가 없습니다. 먼저 레시피를 채워주세요.")
    else:
        recipe_id, menu_name = row
        print(f"테스트 레시피: [{recipe_id}] {menu_name}\n")

        # 반복 실행해도 같은 결과가 나오도록, 테스트 계정(auth_agent 테스트로 만든 user_id=14)의
        # 기존 테스트 후기를 지우고 새로 저장한다.
        cur.execute("DELETE FROM reviews WHERE recipe_id = ? AND user_id = 14", (recipe_id,))
        cur.execute("DELETE FROM review_summaries WHERE recipe_id = ?", (recipe_id,))
        conn.commit()

        test_reviews = [
            (5, "정말 맛있었어요! 간단하고 좋아요."),
            (4, "괜찮은데 좀 짰어요. 소금을 줄이면 좋을 것 같아요."),
            (5, "재료도 구하기 쉽고 만들기 쉬웠습니다."),
        ]
        for rating, text in test_reviews:
            save_review(cur, recipe_id, 14, rating, text)
        conn.commit()

        summary = summarize_reviews(cur, recipe_id)
        conn.commit()

        print("--- 저장된 후기 ---")
        for r in get_reviews_for_recipe(cur, recipe_id):
            print(f"  별점 {r['rating']}: {r['review_text']}")
        print("\n--- 자동 요약 ---")
        print(summary)

    conn.close()
