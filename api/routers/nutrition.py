"""
V1의 nutrition_target_agent.py 로직을 HTTP 엔드포인트로 감싸는 얇은 래퍼.

nutrition_target_agent.build_nutrition_fit()은 recipe_macro/recipe_micro를 인자로
받는 순수 계산 함수라, 레시피 재료로부터 이 두 값을 채우는 조립 코드가 필요하다.
- recipe_macro(단백질/나트륨)는 recipes.nutrients_json에 이미 있는 값을 그대로 쓴다.
- recipe_micro(칼슘/철/비타민A/비타민C/아연)는 ingredient_catalog_agent.match_nutrition_local()
  (이미 벌크 수집해둔 로컬 30만여 건 캐시, #47)로 재료 100g당 값을 찾아 실제 사용량(g)만큼
  환산해 합산한다. 조미료(is_staple)와 g 환산이 안 되는 재료, 매칭 안 되는 재료는 이 합계에서
  빠지므로 micro_is_partial로 부분 합계임을 표시한다 - price_agent가 재료비를 계산할 때 쓰는
  것과 동일한 원칙이다.
"""

import json
import sqlite3

from fastapi import APIRouter, Depends, HTTPException

from pydantic import BaseModel

from api.auth_token import get_current_user_id, require_self
from api.deps import get_db
from src.agents import ingredient_catalog_agent, nutrition_target_agent, portion_agent, recommendation_agent

router = APIRouter(prefix="/recommendation/recipes", tags=["nutrition"])

MICRO_KEYS = ["calcium_mg", "iron_mg", "vitamin_a_ug", "vitamin_c_mg", "zinc_mg"]


class NutritionRow(BaseModel):
    key: str
    label: str
    unit: str
    target: float
    provided: float
    pct_of_daily: int | None
    already_supplemented: bool


class SodiumRow(BaseModel):
    label: str
    unit: str
    limit: int
    provided: float
    pct_of_limit: int
    limit_adjusted: bool


class NutritionFitResponse(BaseModel):
    available: bool
    bracket_label: str
    is_estimated: bool
    rows: list[NutritionRow]
    sodium_row: SodiumRow | None
    micro_is_partial: bool
    condition_notes: list[str]


class IngredientDisplayItem(BaseModel):
    name: str
    display: str
    amount: float | None
    unit: str | None


def _build_recipe_micro(cur: sqlite3.Cursor, recipe_id: int, household_size: int) -> tuple[dict, bool]:
    base_servings, items = portion_agent.get_recipe_ingredients(cur, recipe_id)
    if not items:
        return {}, True

    scaled_items = portion_agent.scale_ingredients(items, base_servings, household_size)

    totals = {key: 0.0 for key in MICRO_KEYS}
    is_partial = False
    for item in scaled_items:
        name = item["name"]
        amount = item["amount"]
        unit = item["unit"]

        if recommendation_agent.is_staple(name):
            continue
        if amount is None or unit != "g":
            is_partial = True
            continue

        matched = ingredient_catalog_agent.match_nutrition_local(cur, name)
        if matched is None:
            is_partial = True
            continue

        for key in MICRO_KEYS:
            value = matched.get(key)
            if value is None:
                is_partial = True
                continue
            totals[key] += value * (amount / 100)

    recipe_micro = {key: value for key, value in totals.items() if value > 0}
    return recipe_micro, is_partial


@router.get("/{recipe_id}/nutrition-fit", response_model=NutritionFitResponse)
def get_nutrition_fit(
    recipe_id: int,
    user_id: int,
    cur: sqlite3.Cursor = Depends(get_db),
    current_user_id: int = Depends(get_current_user_id),
):
    require_self(user_id, current_user_id)
    profile = recommendation_agent.get_user_profile(cur, user_id)
    if profile is None:
        raise HTTPException(status_code=404, detail="존재하지 않는 user_id입니다.")

    cur.execute("SELECT nutrients_json FROM recipes WHERE id = ?", (recipe_id,))
    row = cur.fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="존재하지 않는 recipe_id입니다.")

    nutrients = json.loads(row[0]) if row[0] else {}
    recipe_macro = {}
    if nutrients.get("protein_g") not in (None, ""):
        recipe_macro["protein_g"] = float(nutrients["protein_g"])
    if nutrients.get("sodium_mg") not in (None, ""):
        recipe_macro["sodium_mg"] = float(nutrients["sodium_mg"])

    try:
        household_size = int(profile.get("household_size") or 1)
    except (TypeError, ValueError):
        household_size = 1

    recipe_micro, micro_is_partial = _build_recipe_micro(cur, recipe_id, household_size)

    result = nutrition_target_agent.build_nutrition_fit(
        age_group=profile.get("age_group"),
        gender=profile.get("gender"),
        supplements_text=profile.get("supplements") or "",
        recipe_macro=recipe_macro,
        recipe_micro=recipe_micro,
        micro_is_partial=micro_is_partial,
        medical_conditions_text=profile.get("medical_conditions") or "",
    )
    return result


@router.get("/{recipe_id}/ingredients", response_model=list[IngredientDisplayItem])
def get_recipe_ingredients_scaled(
    recipe_id: int,
    user_id: int,
    cur: sqlite3.Cursor = Depends(get_db),
    current_user_id: int = Depends(get_current_user_id),
):
    """가구원 수에 맞춰 환산된 재료 수량 목록. portion_agent.py 로직 그대로 재사용한다."""
    require_self(user_id, current_user_id)
    profile = recommendation_agent.get_user_profile(cur, user_id)
    if profile is None:
        raise HTTPException(status_code=404, detail="존재하지 않는 user_id입니다.")
    try:
        household_size = int(profile.get("household_size") or 1)
    except (TypeError, ValueError):
        household_size = 1

    base_servings, items = portion_agent.get_recipe_ingredients(cur, recipe_id)
    if not items:
        return []
    return portion_agent.scale_ingredients(items, base_servings, household_size)
