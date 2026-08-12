"""
V1의 review_agent.py 로직을 HTTP 엔드포인트로 감싸는 얇은 래퍼.
save_review/get_reviews_for_recipe/summarize_reviews는 수정하지 않고 그대로 가져다 쓴다.
summarize_reviews는 OpenAI(gpt-4o-mini)를 호출하므로 캐시(review_summaries)가 있으면 재사용한다(agent 원본 동작).
"""

import sqlite3

from fastapi import APIRouter, Depends, HTTPException

from pydantic import BaseModel, Field

from api.auth_token import get_current_user_id, require_self
from api.deps import get_db
from src.agents import review_agent

router = APIRouter(prefix="/reviews", tags=["reviews"])


class ReviewRequest(BaseModel):
    user_id: int
    rating: int = Field(ge=1, le=5)
    review_text: str
    image_url: str | None = None


class ReviewItem(BaseModel):
    rating: int
    review_text: str
    created_at: str
    username: str
    image_url: str | None = None


class SummaryResponse(BaseModel):
    summary: str | None


def _require_recipe(cur: sqlite3.Cursor, recipe_id: int):
    cur.execute("SELECT id FROM recipes WHERE id = ?", (recipe_id,))
    if cur.fetchone() is None:
        raise HTTPException(status_code=404, detail="존재하지 않는 recipe_id입니다.")


@router.get("/{recipe_id}", response_model=list[ReviewItem])
def list_reviews(recipe_id: int, cur: sqlite3.Cursor = Depends(get_db)):
    _require_recipe(cur, recipe_id)
    return review_agent.get_reviews_for_recipe(cur, recipe_id)


@router.post("/{recipe_id}")
def create_review(
    recipe_id: int,
    body: ReviewRequest,
    cur: sqlite3.Cursor = Depends(get_db),
    current_user_id: int = Depends(get_current_user_id),
):
    require_self(body.user_id, current_user_id)
    _require_recipe(cur, recipe_id)
    cur.execute("SELECT id FROM users WHERE id = ?", (body.user_id,))
    if cur.fetchone() is None:
        raise HTTPException(status_code=404, detail="존재하지 않는 user_id입니다.")
    review_agent.save_review(cur, recipe_id, body.user_id, body.rating, body.review_text, body.image_url)
    return {"saved": True}


@router.get("/{recipe_id}/summary", response_model=SummaryResponse)
def get_summary(recipe_id: int, cur: sqlite3.Cursor = Depends(get_db)):
    _require_recipe(cur, recipe_id)
    summary = review_agent.summarize_reviews(cur, recipe_id)
    return SummaryResponse(summary=summary)
