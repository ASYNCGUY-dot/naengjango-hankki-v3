"""
관리자 전용 엔드포인트: 계정 승격 + 유저등록레시피/재료정보 승인 큐.

auth_agent.promote_to_admin, user_recipe_agent의 get_pending_recipes/approve_recipe/
reject_recipe, ingredient_submission_agent의 get_pending_ingredients/approve_ingredient/
reject_ingredient를 그대로 감싼다. "누가 첫 관리자가 되는가" 순환 문제는
auth_agent.promote_to_admin이 이미 해결해둔 방식(.env의 ADMIN_SECRET 코드를 아는
사람만 스스로 승격)을 그대로 쓴다.
"""

import sqlite3

from fastapi import APIRouter, Depends, HTTPException

from pydantic import BaseModel

from api.auth_token import get_current_user_id, require_self
from api.deps import get_db
from src.agents import auth_agent, ingredient_submission_agent, user_recipe_agent

router = APIRouter(prefix="/admin", tags=["admin"])


class PromoteRequest(BaseModel):
    code: str


class PromoteResponse(BaseModel):
    is_admin: bool


class PendingRecipe(BaseModel):
    id: int
    menu_name: str
    category: str | None
    calorie: float | None
    username: str


class PendingIngredient(BaseModel):
    id: int
    ingredient_name: str
    calorie: float | None
    carbs_g: float | None
    protein_g: float | None
    fat_g: float | None
    sodium_mg: float | None
    price_per_100g: float | None
    username: str


def _require_admin(cur: sqlite3.Cursor, user_id: int):
    cur.execute("SELECT is_admin FROM users WHERE id = ?", (user_id,))
    row = cur.fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="존재하지 않는 user_id입니다.")
    if not row[0]:
        raise HTTPException(status_code=403, detail="관리자 권한이 없습니다.")


@router.post("/promote", response_model=PromoteResponse)
def promote(
    user_id: int,
    body: PromoteRequest,
    cur: sqlite3.Cursor = Depends(get_db),
    current_user_id: int = Depends(get_current_user_id),
):
    require_self(user_id, current_user_id)
    cur.execute("SELECT id FROM users WHERE id = ?", (user_id,))
    if cur.fetchone() is None:
        raise HTTPException(status_code=404, detail="존재하지 않는 user_id입니다.")
    ok = auth_agent.promote_to_admin(cur, user_id, body.code)
    if not ok:
        raise HTTPException(status_code=401, detail="관리자 코드가 올바르지 않습니다.")
    return PromoteResponse(is_admin=True)


@router.get("/pending-recipes", response_model=list[PendingRecipe])
def pending_recipes(
    user_id: int,
    cur: sqlite3.Cursor = Depends(get_db),
    current_user_id: int = Depends(get_current_user_id),
):
    require_self(user_id, current_user_id)
    _require_admin(cur, user_id)
    return user_recipe_agent.get_pending_recipes(cur)


@router.post("/recipes/{recipe_id}/approve")
def approve_recipe(
    recipe_id: int,
    user_id: int,
    cur: sqlite3.Cursor = Depends(get_db),
    current_user_id: int = Depends(get_current_user_id),
):
    require_self(user_id, current_user_id)
    _require_admin(cur, user_id)
    user_recipe_agent.approve_recipe(cur, recipe_id)
    return {"approved": True}


@router.post("/recipes/{recipe_id}/reject")
def reject_recipe(
    recipe_id: int,
    user_id: int,
    cur: sqlite3.Cursor = Depends(get_db),
    current_user_id: int = Depends(get_current_user_id),
):
    require_self(user_id, current_user_id)
    _require_admin(cur, user_id)
    user_recipe_agent.reject_recipe(cur, recipe_id)
    return {"rejected": True}


@router.get("/pending-ingredients", response_model=list[PendingIngredient])
def pending_ingredients(
    user_id: int,
    cur: sqlite3.Cursor = Depends(get_db),
    current_user_id: int = Depends(get_current_user_id),
):
    require_self(user_id, current_user_id)
    _require_admin(cur, user_id)
    return ingredient_submission_agent.get_pending_ingredients(cur)


@router.post("/ingredients/{submission_id}/approve")
def approve_ingredient(
    submission_id: int,
    user_id: int,
    cur: sqlite3.Cursor = Depends(get_db),
    current_user_id: int = Depends(get_current_user_id),
):
    require_self(user_id, current_user_id)
    _require_admin(cur, user_id)
    ingredient_submission_agent.approve_ingredient(cur, submission_id)
    return {"approved": True}


@router.post("/ingredients/{submission_id}/reject")
def reject_ingredient(
    submission_id: int,
    user_id: int,
    cur: sqlite3.Cursor = Depends(get_db),
    current_user_id: int = Depends(get_current_user_id),
):
    require_self(user_id, current_user_id)
    _require_admin(cur, user_id)
    ingredient_submission_agent.reject_ingredient(cur, submission_id)
    return {"rejected": True}
