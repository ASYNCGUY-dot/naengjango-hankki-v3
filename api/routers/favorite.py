"""
V1의 favorite_agent.py 로직을 HTTP 엔드포인트로 감싸는 얇은 래퍼.
toggle_favorite/get_favorite_recipes는 수정하지 않고 그대로 가져다 쓴다.
"""

import sqlite3

from fastapi import APIRouter, Depends, HTTPException

from pydantic import BaseModel

from api.auth_token import get_current_user_id, require_self
from api.deps import get_db
from src.agents import favorite_agent

router = APIRouter(prefix="/favorites", tags=["favorites"])


class FavoriteItem(BaseModel):
    id: int
    menu_name: str
    category: str | None
    calorie: float | None
    created_at: str


class ToggleResponse(BaseModel):
    favorited: bool


def _require_user(cur: sqlite3.Cursor, user_id: int):
    cur.execute("SELECT id FROM users WHERE id = ?", (user_id,))
    if cur.fetchone() is None:
        raise HTTPException(status_code=404, detail="존재하지 않는 user_id입니다.")


def _require_recipe(cur: sqlite3.Cursor, recipe_id: int):
    cur.execute("SELECT id FROM recipes WHERE id = ?", (recipe_id,))
    if cur.fetchone() is None:
        raise HTTPException(status_code=404, detail="존재하지 않는 recipe_id입니다.")


@router.get("/{user_id}", response_model=list[FavoriteItem])
def list_favorites(
    user_id: int,
    cur: sqlite3.Cursor = Depends(get_db),
    current_user_id: int = Depends(get_current_user_id),
):
    require_self(user_id, current_user_id)
    _require_user(cur, user_id)
    return favorite_agent.get_favorite_recipes(cur, user_id)


@router.post("/{user_id}/{recipe_id}/toggle", response_model=ToggleResponse)
def toggle(
    user_id: int,
    recipe_id: int,
    cur: sqlite3.Cursor = Depends(get_db),
    current_user_id: int = Depends(get_current_user_id),
):
    require_self(user_id, current_user_id)
    _require_user(cur, user_id)
    _require_recipe(cur, recipe_id)
    favorited = favorite_agent.toggle_favorite(cur, user_id, recipe_id)
    return ToggleResponse(favorited=favorited)
