"""
피드백 - 앱이 어땠는지를 앱 안에서 받는다 (2026-08-22).

읽는 범위가 둘이다. `GET /feedback`은 본인 것만, `GET /feedback/all`은 관리자만
전부 본다. 사용자 테스트에서 남의 의견이 보이면 그쪽으로 끌려가기 때문이다.

레시피 후기(api/routers/review.py)와 다른 것이다. 후기는 레시피에 붙고, 이건
앱 전체에 대한 것이라 붙을 레시피가 없다.
"""

import sqlite3

from fastapi import APIRouter, Depends, HTTPException

from pydantic import BaseModel, Field

from api import usage_log
from api.auth_token import get_current_user_id, require_self
from api.deps import get_db
from src.agents import feedback_agent

router = APIRouter(prefix="/feedback", tags=["feedback"])


class FeedbackRequest(BaseModel):
    # 화면에도 maxLength가 있지만 그건 편의일 뿐이다(user_recipe.py와 같은 이유).
    body: str = Field(min_length=1, max_length=2000)


class FeedbackItem(BaseModel):
    id: int
    body: str
    created_at: str
    # 본인 조회에서는 항상 None이다. 관리자 조회에서만 채워진다.
    username: str | None


def _require_admin(cur: sqlite3.Cursor, user_id: int) -> None:
    cur.execute("SELECT is_admin FROM users WHERE id = ?", (user_id,))
    row = cur.fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="존재하지 않는 user_id입니다.")
    if not row[0]:
        raise HTTPException(status_code=403, detail="관리자 권한이 없습니다.")


@router.get("", response_model=list[FeedbackItem])
def list_mine(
    user_id: int,
    cur: sqlite3.Cursor = Depends(get_db),
    current_user_id: int = Depends(get_current_user_id),
):
    require_self(user_id, current_user_id)
    return feedback_agent.list_my_feedback(cur, user_id)


@router.get("/all", response_model=list[FeedbackItem])
def list_all(
    user_id: int,
    cur: sqlite3.Cursor = Depends(get_db),
    current_user_id: int = Depends(get_current_user_id),
):
    """관리자만. "/all"을 "/{...}"보다 먼저 등록할 필요는 없지만(경로 파라미터가
    없다) 순서를 지키는 편이 나중에 파라미터를 더할 때 안전하다(8.2 함정)."""
    require_self(user_id, current_user_id)
    _require_admin(cur, user_id)
    return feedback_agent.list_all_feedback(cur)


@router.post("", response_model=FeedbackItem)
def create(
    user_id: int,
    body: FeedbackRequest,
    cur: sqlite3.Cursor = Depends(get_db),
    current_user_id: int = Depends(get_current_user_id),
):
    require_self(user_id, current_user_id)
    feedback_id = feedback_agent.create_feedback(cur, user_id, body.body)
    usage_log.record(cur, usage_log.FEEDBACK_POST, user_id=user_id)

    for item in feedback_agent.list_my_feedback(cur, user_id):
        if item["id"] == feedback_id:
            return item
    raise HTTPException(status_code=500, detail="저장했지만 다시 읽지 못했습니다.")


@router.delete("/{feedback_id}")
def delete(
    feedback_id: int,
    user_id: int,
    cur: sqlite3.Cursor = Depends(get_db),
    current_user_id: int = Depends(get_current_user_id),
):
    require_self(user_id, current_user_id)
    if not feedback_agent.delete_my_feedback(cur, feedback_id, user_id):
        raise HTTPException(status_code=404, detail="본인이 쓴 글이 아니거나 존재하지 않습니다.")
    return {"deleted": True}
