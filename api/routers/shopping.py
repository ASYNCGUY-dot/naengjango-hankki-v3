"""
V1의 shopping_agent.py 로직을 HTTP 엔드포인트로 감싸는 얇은 래퍼.

get_shopping_links()는 아직 쿠팡파트너스 승인 전이라 실제 제휴(수수료) 링크가 아니라
네이버쇼핑/쿠팡 "검색 결과 페이지" URL만 만든다(shopping_agent.py 상단 주석 참고).
승인 후 COUPANG_ACCESS_KEY/COUPANG_SECRET_KEY를 설정하고 convert_to_coupang_partner_link()를
구현하면, 이 엔드포인트는 코드 변경 없이 자동으로 실제 트래킹 링크를 반환하게 된다.
"""

import sqlite3

from fastapi import APIRouter, Depends, HTTPException

from pydantic import BaseModel

from api.auth_token import get_current_user_id, require_self
from api.deps import get_db
from src.agents import pantry_agent, recommendation_agent, shopping_agent, substitution_agent

router = APIRouter(prefix="/recommendation/recipes", tags=["shopping"])


class ShoppingLink(BaseModel):
    ingredient: str
    naver: str
    coupang: str


class ShoppingLinksResponse(BaseModel):
    links: list[ShoppingLink]


@router.get("/{recipe_id}/shopping-links", response_model=ShoppingLinksResponse)
def get_shopping_links_for_missing(
    recipe_id: int,
    user_id: int,
    cur: sqlite3.Cursor = Depends(get_db),
    current_user_id: int = Depends(get_current_user_id),
):
    require_self(user_id, current_user_id)
    cur.execute("SELECT id FROM users WHERE id = ?", (user_id,))
    if cur.fetchone() is None:
        raise HTTPException(status_code=404, detail="존재하지 않는 user_id입니다.")

    recipe = recommendation_agent.get_recipe_by_id(cur, recipe_id)
    if recipe is None:
        raise HTTPException(status_code=404, detail="존재하지 않는 recipe_id입니다.")

    pantry_items = pantry_agent.get_pantry_ingredients(cur, user_id)
    user_ingredients = [item["name"] for item in pantry_items]

    missing = substitution_agent.get_missing_ingredients(cur, recipe_id, user_ingredients, recipe["menu_name"])
    access_key, secret_key = shopping_agent.get_shopping_key_for_recipe(cur, recipe)

    links = [
        ShoppingLink(ingredient=m["ingredient"], **shopping_agent.get_shopping_links(m["ingredient"], access_key, secret_key))
        for m in missing
    ]
    return ShoppingLinksResponse(links=links)
