"""
V1의 seasonal_agent.py 로직을 HTTP 엔드포인트로 감싸는 얇은 래퍼.
get_current_season_ingredients/find_seasonal_matches는 수정하지 않고 그대로 가져다 쓴다.
"""

import sqlite3
from datetime import date

from fastapi import APIRouter, Depends, HTTPException

from pydantic import BaseModel

from api.auth_token import get_current_user_id, require_self
from api.deps import get_db
from src.agents import pantry_agent, seasonal_agent

router = APIRouter(prefix="/seasonal", tags=["seasonal"])


class SeasonalResponse(BaseModel):
    month: int
    ingredients: list[str]


@router.get("/current", response_model=SeasonalResponse)
def get_current_season(month: int | None = None):
    resolved_month = month or date.today().month
    return SeasonalResponse(
        month=resolved_month,
        ingredients=seasonal_agent.get_current_season_ingredients(resolved_month),
    )


class SeasonalMatchResponse(BaseModel):
    month: int
    seasonal_ingredients: list[str]
    matches: list[str]


@router.get("/{user_id}/matches", response_model=SeasonalMatchResponse)
def get_seasonal_matches(
    user_id: int,
    month: int | None = None,
    cur: sqlite3.Cursor = Depends(get_db),
    current_user_id: int = Depends(get_current_user_id),
):
    require_self(user_id, current_user_id)
    cur.execute("SELECT id FROM users WHERE id = ?", (user_id,))
    if cur.fetchone() is None:
        raise HTTPException(status_code=404, detail="존재하지 않는 user_id입니다.")

    resolved_month = month or date.today().month

    pantry_items = pantry_agent.get_pantry_ingredients(cur, user_id)
    user_ingredients = [item["name"] for item in pantry_items]

    matches = seasonal_agent.find_seasonal_matches(user_ingredients, resolved_month)
    return SeasonalMatchResponse(
        month=resolved_month,
        seasonal_ingredients=seasonal_agent.get_current_season_ingredients(resolved_month),
        matches=matches,
    )
