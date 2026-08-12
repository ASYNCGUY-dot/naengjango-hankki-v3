"""
V1의 user_recipe_agent.py 로직을 HTTP 엔드포인트로 감싸는 얇은 래퍼.
submit/update/get_my_recipes/get_my_recipe_detail/delete만 노출한다 - 관리자 승인
기능(get_pending_recipes/approve_recipe/reject_recipe)은 관리자 화면이 아직 없어서
이번 범위에서는 다루지 않는다.
"""

import sqlite3

from fastapi import APIRouter, Depends, HTTPException

from pydantic import BaseModel

from api.auth_token import get_current_user_id, require_self
from api.deps import get_db
from src.agents import user_recipe_agent

router = APIRouter(prefix="/my-recipes", tags=["user-recipes"])


class RecipeSubmitRequest(BaseModel):
    menu_name: str
    category: str
    calorie: float | None = None
    ingredients_text: str
    steps_text: str


class RecipeSubmitResponse(BaseModel):
    recipe_id: int
    status: str


class MyRecipeItem(BaseModel):
    id: int
    menu_name: str
    category: str | None
    calorie: float | None
    status: str
    like_count: int


class MyRecipeDetail(BaseModel):
    menu_name: str
    category: str | None
    calorie: float | None
    ingredients_text: str
    steps_text: str


def _require_user(cur: sqlite3.Cursor, user_id: int):
    cur.execute("SELECT id FROM users WHERE id = ?", (user_id,))
    if cur.fetchone() is None:
        raise HTTPException(status_code=404, detail="존재하지 않는 user_id입니다.")


@router.get("", response_model=list[MyRecipeItem])
def list_my_recipes(
    user_id: int,
    cur: sqlite3.Cursor = Depends(get_db),
    current_user_id: int = Depends(get_current_user_id),
):
    require_self(user_id, current_user_id)
    _require_user(cur, user_id)
    return user_recipe_agent.get_my_recipes(cur, user_id)


@router.post("", response_model=RecipeSubmitResponse)
def submit_recipe(
    user_id: int,
    body: RecipeSubmitRequest,
    cur: sqlite3.Cursor = Depends(get_db),
    current_user_id: int = Depends(get_current_user_id),
):
    require_self(user_id, current_user_id)
    _require_user(cur, user_id)
    recipe_id, status = user_recipe_agent.submit_user_recipe(
        cur, user_id, body.menu_name, body.category, body.calorie,
        body.ingredients_text, body.steps_text,
    )
    return RecipeSubmitResponse(recipe_id=recipe_id, status=status)


@router.get("/{recipe_id}", response_model=MyRecipeDetail)
def get_recipe_detail(
    recipe_id: int,
    user_id: int,
    cur: sqlite3.Cursor = Depends(get_db),
    current_user_id: int = Depends(get_current_user_id),
):
    require_self(user_id, current_user_id)
    _require_user(cur, user_id)
    detail = user_recipe_agent.get_my_recipe_detail(cur, recipe_id, user_id)
    if detail is None:
        raise HTTPException(status_code=404, detail="본인이 등록한 레시피가 아니거나 존재하지 않습니다.")
    return detail


@router.put("/{recipe_id}", response_model=RecipeSubmitResponse)
def update_recipe(
    recipe_id: int,
    user_id: int,
    body: RecipeSubmitRequest,
    cur: sqlite3.Cursor = Depends(get_db),
    current_user_id: int = Depends(get_current_user_id),
):
    require_self(user_id, current_user_id)
    _require_user(cur, user_id)
    status = user_recipe_agent.update_user_recipe(
        cur, recipe_id, user_id, body.menu_name, body.category, body.calorie,
        body.ingredients_text, body.steps_text,
    )
    if status is None:
        raise HTTPException(status_code=404, detail="본인이 등록한 레시피가 아니거나 존재하지 않습니다.")
    return RecipeSubmitResponse(recipe_id=recipe_id, status=status)


@router.delete("/{recipe_id}")
def delete_recipe(
    recipe_id: int,
    user_id: int,
    cur: sqlite3.Cursor = Depends(get_db),
    current_user_id: int = Depends(get_current_user_id),
):
    require_self(user_id, current_user_id)
    _require_user(cur, user_id)
    ok = user_recipe_agent.delete_my_recipe(cur, recipe_id, user_id)
    if not ok:
        raise HTTPException(status_code=404, detail="본인이 등록한 레시피가 아니거나 존재하지 않습니다.")
    return {"deleted": True}
