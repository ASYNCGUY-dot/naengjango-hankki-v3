"""
V1의 ingredient_catalog_agent.py 로직을 HTTP 엔드포인트로 감싸는 얇은 래퍼.
검색/카운트 함수(search_ingredient_catalog, count_ingredient_catalog)만 노출한다
- 벌크 수집(run_bulk_collect)은 이미 마이그레이션 때 다 채워진 30만여 건을 다시 받는
  작업이라 여기서는 다루지 않는다.
"""

import sqlite3

from fastapi import APIRouter, Depends

from pydantic import BaseModel

from api.auth_token import get_current_user_id, require_self
from api.deps import get_db
from src.agents import ingredient_catalog_agent, ingredient_favorite_agent

router = APIRouter(prefix="/ingredients", tags=["ingredients"])


class IngredientCatalogItem(BaseModel):
    food_code: str
    name: str
    db_group: str | None
    energy_kcal: float | None
    protein_g: float | None
    fat_g: float | None
    carbs_g: float | None
    sodium_mg: float | None


class IngredientSearchResponse(BaseModel):
    total: int
    items: list[dict]


@router.get("/search", response_model=IngredientSearchResponse)
def search_ingredients(
    keyword: str = "", limit: int = 20, offset: int = 0, cur: sqlite3.Cursor = Depends(get_db)
):
    total = ingredient_catalog_agent.count_ingredient_catalog(cur, keyword)
    items = ingredient_catalog_agent.search_ingredient_catalog(cur, keyword, limit, offset)
    return IngredientSearchResponse(total=total, items=items)


class ToggleResponse(BaseModel):
    favorited: bool


@router.post("/{user_id}/{food_code}/toggle", response_model=ToggleResponse)
def toggle_ingredient_favorite(
    user_id: int,
    food_code: str,
    cur: sqlite3.Cursor = Depends(get_db),
    current_user_id: int = Depends(get_current_user_id),
):
    require_self(user_id, current_user_id)
    favorited = ingredient_favorite_agent.toggle_ingredient_favorite(cur, user_id, food_code)
    return ToggleResponse(favorited=favorited)


@router.get("/{user_id}/favorites", response_model=list[dict])
def list_favorite_ingredients(
    user_id: int,
    cur: sqlite3.Cursor = Depends(get_db),
    current_user_id: int = Depends(get_current_user_id),
):
    require_self(user_id, current_user_id)
    return ingredient_favorite_agent.get_favorite_ingredients(cur, user_id)
