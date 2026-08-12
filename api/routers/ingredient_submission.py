"""
V1의 ingredient_submission_agent.py 로직을 HTTP 엔드포인트로 감싸는 얇은 래퍼.
submit/update/get_my_ingredient_submissions/get_ingredient_submission_detail만 노출한다
- 관리자 승인 기능(get_pending_ingredients/approve_ingredient/reject_ingredient)은
  관리자 화면(별도 작업)에서 다룬다.

공식 API(ingredient_agent.match_nutrition)는 매번 실시간 호출이라 비용이 크므로,
official_match_exists 판단은 이미 로컬에 벌크 수집해둔 ingredient_catalog 테이블에서
정확히 일치하는 이름이 있는지만 가볍게 확인한다(#47에서 이미 구축해둔 캐시 재사용).
"""

import sqlite3

from fastapi import APIRouter, Depends, HTTPException

from pydantic import BaseModel

from api.auth_token import get_current_user_id, require_self
from api.deps import get_db
from src.agents import ingredient_submission_agent

router = APIRouter(prefix="/ingredient-submissions", tags=["ingredient-submission"])


class SubmissionRequest(BaseModel):
    ingredient_name: str
    calorie: float | None = None
    carbs_g: float | None = None
    protein_g: float | None = None
    fat_g: float | None = None
    sodium_mg: float | None = None
    price_per_100g: float | None = None


class SubmissionResponse(BaseModel):
    submission_id: int | None = None
    status: str


class MySubmissionItem(BaseModel):
    id: int
    ingredient_name: str
    calorie: float | None
    status: str


class MySubmissionDetail(BaseModel):
    ingredient_name: str
    calorie: float | None
    carbs_g: float | None
    protein_g: float | None
    fat_g: float | None
    sodium_mg: float | None
    price_per_100g: float | None


def _require_user(cur: sqlite3.Cursor, user_id: int):
    cur.execute("SELECT id FROM users WHERE id = ?", (user_id,))
    if cur.fetchone() is None:
        raise HTTPException(status_code=404, detail="존재하지 않는 user_id입니다.")


def _official_match_exists(cur: sqlite3.Cursor, ingredient_name: str) -> bool:
    cur.execute("SELECT 1 FROM ingredient_catalog WHERE name = ? LIMIT 1", (ingredient_name.strip(),))
    return cur.fetchone() is not None


@router.get("", response_model=list[MySubmissionItem])
def list_my_submissions(
    user_id: int,
    cur: sqlite3.Cursor = Depends(get_db),
    current_user_id: int = Depends(get_current_user_id),
):
    require_self(user_id, current_user_id)
    _require_user(cur, user_id)
    return ingredient_submission_agent.get_my_ingredient_submissions(cur, user_id)


@router.post("", response_model=SubmissionResponse)
def submit_ingredient(
    user_id: int,
    body: SubmissionRequest,
    cur: sqlite3.Cursor = Depends(get_db),
    current_user_id: int = Depends(get_current_user_id),
):
    require_self(user_id, current_user_id)
    _require_user(cur, user_id)
    official_match = _official_match_exists(cur, body.ingredient_name)
    status = ingredient_submission_agent.submit_ingredient_info(
        cur, user_id, body.ingredient_name, body.calorie, body.carbs_g, body.protein_g,
        body.fat_g, body.sodium_mg, body.price_per_100g, official_match_exists=official_match,
    )
    return SubmissionResponse(status=status)


@router.get("/{submission_id}", response_model=MySubmissionDetail)
def get_submission_detail(
    submission_id: int,
    user_id: int,
    cur: sqlite3.Cursor = Depends(get_db),
    current_user_id: int = Depends(get_current_user_id),
):
    require_self(user_id, current_user_id)
    _require_user(cur, user_id)
    detail = ingredient_submission_agent.get_ingredient_submission_detail(cur, submission_id, user_id)
    if detail is None:
        raise HTTPException(status_code=404, detail="본인이 등록한 재료 정보가 아니거나 존재하지 않습니다.")
    return detail


@router.put("/{submission_id}", response_model=SubmissionResponse)
def update_submission(
    submission_id: int,
    user_id: int,
    body: SubmissionRequest,
    cur: sqlite3.Cursor = Depends(get_db),
    current_user_id: int = Depends(get_current_user_id),
):
    require_self(user_id, current_user_id)
    _require_user(cur, user_id)
    status = ingredient_submission_agent.update_ingredient_submission(
        cur, submission_id, user_id, body.ingredient_name, body.calorie, body.carbs_g,
        body.protein_g, body.fat_g, body.sodium_mg, body.price_per_100g,
    )
    if status is None:
        raise HTTPException(status_code=404, detail="본인이 등록한 재료 정보가 아니거나 존재하지 않습니다.")
    return SubmissionResponse(submission_id=submission_id, status=status)
