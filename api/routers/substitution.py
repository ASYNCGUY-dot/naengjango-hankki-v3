"""
V1의 substitution_agent.py 로직을 HTTP 엔드포인트로 감싸는 얇은 래퍼.
get_missing_ingredients/get_ingredient_coverage는 수정하지 않고 그대로 가져다 쓴다.
"""

import sqlite3

from fastapi import APIRouter, Depends, HTTPException

from pydantic import BaseModel

from api.auth_token import get_current_user_id, require_self
from api.deps import get_db
from src.agents import pantry_agent, substitution_agent

router = APIRouter(prefix="/recommendation/recipes", tags=["substitution"])


class MissingIngredient(BaseModel):
    ingredient: str
    suggestion: str
    type: str


class Coverage(BaseModel):
    total: int
    matched: int
    missing: int
    coverage_pct: int | None


class SubstitutionResponse(BaseModel):
    coverage: Coverage
    missing_ingredients: list[MissingIngredient]


@router.get("/{recipe_id}/substitution", response_model=SubstitutionResponse)
def get_substitution_info(
    recipe_id: int,
    user_id: int,
    cur: sqlite3.Cursor = Depends(get_db),
    current_user_id: int = Depends(get_current_user_id),
):
    require_self(user_id, current_user_id)
    cur.execute("SELECT id FROM users WHERE id = ?", (user_id,))
    if cur.fetchone() is None:
        raise HTTPException(status_code=404, detail="존재하지 않는 user_id입니다.")

    cur.execute("SELECT menu_name FROM recipes WHERE id = ?", (recipe_id,))
    row = cur.fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="존재하지 않는 recipe_id입니다.")
    menu_name = row[0]

    pantry_items = pantry_agent.get_pantry_ingredients(cur, user_id)
    user_ingredients = [item["name"] for item in pantry_items]

    coverage = substitution_agent.get_ingredient_coverage(cur, recipe_id, user_ingredients)
    missing = substitution_agent.get_missing_ingredients(cur, recipe_id, user_ingredients, menu_name)

    return SubstitutionResponse(coverage=coverage, missing_ingredients=missing)
