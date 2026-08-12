"""
V1의 pantry_agent.py 로직을 HTTP 엔드포인트로 감싸는 얇은 래퍼.
add/remove/get_pantry_ingredients는 수정하지 않고 그대로 가져다 쓴다.
"""

import sqlite3

from fastapi import APIRouter, Depends, HTTPException

from pydantic import BaseModel

from api.auth_token import get_current_user_id, require_self
from api.deps import get_db
from src.agents import pantry_agent

router = APIRouter(prefix="/pantry", tags=["pantry"])


class PantryItemRequest(BaseModel):
    name: str
    expiry_date: str | None = None


class PantryItem(BaseModel):
    id: int
    name: str
    expiry_date: str | None


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
