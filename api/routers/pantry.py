"""
V1의 pantry_agent.py 로직을 HTTP 엔드포인트로 감싸는 얇은 래퍼.
add/remove/get_pantry_ingredients는 수정하지 않고 그대로 가져다 쓴다.
"""

import sqlite3

from fastapi import APIRouter, Depends, HTTPException, Query

from pydantic import BaseModel

from api import usage_log
from api.auth_token import get_current_user_id, require_self
from api.deps import get_db
from src.agents import pantry_agent, recommendation_agent

router = APIRouter(prefix="/pantry", tags=["pantry"])


class PantryItemRequest(BaseModel):
    name: str
    expiry_date: str | None = None


class PantryItem(BaseModel):
    id: int
    name: str
    expiry_date: str | None


class IngredientSuggestion(BaseModel):
    name: str
    # 몇 개의 레시피가 쓰는 재료인지. 화면이 "118개 레시피"처럼 보여주면 사용자가 어느
    # 표기를 골라야 추천이 잘 되는지 알 수 있다.
    recipe_count: int


# "/suggest"는 "/{user_id}"보다 먼저 등록해야 한다(8.2 함정).
@router.get("/suggest", response_model=list[IngredientSuggestion])
def suggest_ingredients(
    keyword: str = Query(default="", max_length=40),
    limit: int = Query(default=8, ge=1, le=20),
    cur: sqlite3.Cursor = Depends(get_db),
):
    """냉장고 입력창의 자동완성.

    인가가 없다 - 재료 이름은 개인 정보가 아니고, 로그인 전 데모에서도 쓸 수 있어야 한다.

    영양 카탈로그가 아니라 레시피 태그에서 뽑는다. 추천이 실제로 비교하는 대상이 그것이라,
    여기서 고른 이름은 반드시 어딘가에 매칭된다. 손으로 치면 "돼지 고기"처럼 어디에도 안
    맞는 값이 들어가고, 그러면 지인 테스트에서 "추천이 별로다"라는 말이 나와도 알고리즘
    문제인지 입력 문제인지 갈라낼 수 없다.
    """
    return recommendation_agent.suggest_ingredient_names(cur, keyword, limit)


def _require_user(cur: sqlite3.Cursor, user_id: int):
    cur.execute("SELECT id FROM users WHERE id = ?", (user_id,))
    if cur.fetchone() is None:
        raise HTTPException(status_code=404, detail="존재하지 않는 user_id입니다.")


@router.get("/{user_id}", response_model=list[PantryItem])
def list_pantry(
    user_id: int,
    cur: sqlite3.Cursor = Depends(get_db),
    current_user_id: int = Depends(get_current_user_id),
):
    require_self(user_id, current_user_id)
    _require_user(cur, user_id)
    return pantry_agent.get_pantry_ingredients(cur, user_id)


@router.post("/{user_id}")
def add_pantry(
    user_id: int,
    body: PantryItemRequest,
    cur: sqlite3.Cursor = Depends(get_db),
    current_user_id: int = Depends(get_current_user_id),
):
    require_self(user_id, current_user_id)
    _require_user(cur, user_id)
    pantry_agent.add_pantry_ingredient(cur, user_id, body.name, body.expiry_date)
    # ingredients 테이블에는 시각이 없어서 "언제 넣었나"를 여기서만 알 수 있다.
    usage_log.record(cur, usage_log.PANTRY_ADD, user_id=user_id)
    return {"added": True}


class ExpiryUpdateRequest(BaseModel):
    expiry_date: str | None = None


@router.put("/{user_id}/{ingredient_id}")
def update_pantry_expiry(
    user_id: int,
    ingredient_id: int,
    body: ExpiryUpdateRequest,
    cur: sqlite3.Cursor = Depends(get_db),
    current_user_id: int = Depends(get_current_user_id),
):
    """냉장고 화면 개편(2026-07-19): 목록에서 유통기한을 바로 수정할 수 있게 한다."""
    require_self(user_id, current_user_id)
    _require_user(cur, user_id)
    ok = pantry_agent.update_pantry_expiry(cur, ingredient_id, user_id, body.expiry_date)
    if not ok:
        raise HTTPException(status_code=404, detail="본인의 재료가 아니거나 존재하지 않습니다.")
    return {"updated": True}


@router.delete("/{user_id}/{ingredient_id}")
def remove_pantry(
    user_id: int,
    ingredient_id: int,
    cur: sqlite3.Cursor = Depends(get_db),
    current_user_id: int = Depends(get_current_user_id),
):
    require_self(user_id, current_user_id)
    _require_user(cur, user_id)
    pantry_agent.remove_pantry_ingredient(cur, ingredient_id, user_id)
    return {"removed": True}
