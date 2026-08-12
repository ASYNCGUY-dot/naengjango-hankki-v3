"""
V1의 like_agent.py 로직을 HTTP 엔드포인트로 감싸는 얇은 래퍼.
toggle_like/get_like_count/has_liked는 수정하지 않고 그대로 가져다 쓴다.
"""

import sqlite3

from fastapi import APIRouter, Depends, HTTPException

from pydantic import BaseModel

from api.auth_token import get_current_user_id, require_self
from api.deps import get_db
from src.agents import like_agent

router = APIRouter(prefix="/recommendation/recipes", tags=["like"])


class LikeStatus(BaseModel):
    liked: bool
    like_count: int


class PopularRecipeItem(BaseModel):
    id: int
    menu_name: str
    category: str | None
    calorie: float | None
    like_count: int


@router.get("/popular", response_model=list[PopularRecipeItem])
def get_popular_recipes(limit: int = 10, cur: sqlite3.Cursor = Depends(get_db)):
    """즐겨찾기 화면의 "요즘 인기 있는 레시피" 섹션(2026-07-21, #req5) - 로그인 여부와
    무관하게 볼 수 있는 공개 정보라 인가를 요구하지 않는다(search_all_recipes와 동일한 방침)."""
    return like_agent.get_popular_recipes(cur, limit)


@router.get("/{recipe_id}/like", response_model=LikeStatus)
def get_like_status(
    recipe_id: int,
    user_id: int,
    cur: sqlite3.Cursor = Depends(get_db),
    current_user_id: int = Depends(get_current_user_id),
):
    require_self(user_id, current_user_id)
    cur.execute("SELECT id FROM users WHERE id = ?", (user_id,))
    if cur.fetchone() is None:
        raise HTTPException(status_code=404, detail="존재하지 않는 user_id입니다.")
    return LikeStatus(
        liked=like_agent.has_liked(cur, recipe_id, user_id),
        like_count=like_agent.get_like_count(cur, recipe_id),
    )


@router.post("/{recipe_id}/like/toggle", response_model=LikeStatus)
def toggle_like(
    recipe_id: int,
    user_id: int,
    cur: sqlite3.Cursor = Depends(get_db),
    current_user_id: int = Depends(get_current_user_id),
):
    require_self(user_id, current_user_id)
    cur.execute("SELECT id FROM users WHERE id = ?", (user_id,))
    if cur.fetchone() is None:
        raise HTTPException(status_code=404, detail="존재하지 않는 user_id입니다.")
    liked = like_agent.toggle_like(cur, recipe_id, user_id)
    return LikeStatus(liked=liked, like_count=like_agent.get_like_count(cur, recipe_id))
