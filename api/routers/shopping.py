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
    # 누가 수수료를 받는지. 화면은 이 값으로 대가성 문구를 고른다.
    #   "site"   - 사이트 기본 키 (공식 레시피, 미승격 유저 레시피)
    #   "author" - 이 레시피 작성자의 키
    #   "none"   - 아무 키도 안 붙은 일반 검색 링크
    # 제휴 링크에는 고지가 붙어야 하는데 유저 레시피에서는 그 주체가 사이트가 아니라
    # 작성자다. 화면이 스스로 판단하면 서버와 어긋나므로 서버가 정해서 내려준다.
    earner: str
    author_name: str | None = None


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
    key_info = shopping_agent.get_shopping_key_for_recipe(cur, recipe)

    # 변환 요청은 한 번으로 묶이고, earner는 "붙일 작정"이 아니라 "실제로 붙었는가"로
    # 정해져서 돌아온다(shopping_agent.get_shopping_links_for 참고).
    result = shopping_agent.get_shopping_links_for([m["ingredient"] for m in missing], key_info)

    author_name = None
    if result["earner"] == "author" and key_info["author_id"]:
        cur.execute("SELECT username FROM users WHERE id = ?", (key_info["author_id"],))
        row = cur.fetchone()
        author_name = row[0] if row else None

    return ShoppingLinksResponse(
        links=[ShoppingLink(**link) for link in result["links"]],
        earner=result["earner"],
        author_name=author_name,
    )
